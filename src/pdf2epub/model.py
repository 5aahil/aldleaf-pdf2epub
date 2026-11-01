"""Read a text-based PDF into pages of styled lines, drawings and images."""
import re

try:
    import pymupdf
except ImportError:  # PyMuPDF < 1.24
    import fitz as pymupdf

from .text import norm

MONO_HINTS = ("mono", "courier", "consol", "menlo", "code", "inconsolata", "typewriter", "andale")
SANS_HINTS = ("sans", "helvetica", "arial", "figtree", "inter", "roboto", "lato", "opensans",
              "open sans", "montserrat", "verdana", "segoe", "calibri", "avenir", "futura", "gill",
              "frutiger", "myriad", "source sans", "noto sans", "poppins", "nunito", "raleway")


def base_font(name):
    """'ABCDEF+Baskervville-MediumItalic' -> 'Baskervville-MediumItalic'"""
    return re.sub(r"^[A-Z]{6}\+", "", name or "")


def family(name):
    """'Baskervville-MediumItalic' -> 'baskervville'"""
    n = base_font(name)
    n = re.split(r"[-,]", n)[0]
    return re.sub(r"(MT|PS|Std|Pro|LT)$", "", n).lower()


def is_mono_font(name):
    n = base_font(name).lower()
    return any(h in n for h in MONO_HINTS)


def is_sans_font(name):
    n = base_font(name).lower()
    return any(h in n for h in SANS_HINTS) and not is_mono_font(name)


def style_key(font, size):
    return f"{base_font(font)}@{round(size * 2) / 2:g}"


class Span:
    __slots__ = ("t", "font", "size", "italic", "bold", "mono", "sup", "color", "key")

    def __init__(self, s):
        self.t = norm(s["text"])
        self.font = base_font(s["font"])
        self.size = s["size"]
        fl = s["flags"]
        low = self.font.lower()
        self.italic = bool(fl & 2) or "italic" in low or "oblique" in low
        self.bold = bool(fl & 16) or any(w in low for w in ("bold", "black", "heavy"))
        self.mono = is_mono_font(self.font)
        self.sup = bool(fl & 1)
        self.color = s["color"]
        self.key = style_key(self.font, self.size)


class Line:
    def __init__(self, page_no, bbox, spans):
        self.page = page_no
        self.x0, self.y0, self.x1, self.y1 = bbox
        self.spans = spans
        self.text = "".join(s.t for s in spans)
        dom = max(spans, key=lambda s: len(s.t.strip()) or 0.01)
        self.font, self.size, self.color, self.key = dom.font, dom.size, dom.color, dom.key
        self.role = None       # assigned from the style map
        self.light = _is_light(self.color)

    @property
    def width(self):
        return self.x1 - self.x0

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2

    def __repr__(self):
        return f"<Line p{self.page} {self.key} {self.role} {self.text[:30]!r}>"


def _is_light(color):
    r, g, b = (color >> 16) & 255, (color >> 8) & 255, color & 255
    return (0.299 * r + 0.587 * g + 0.114 * b) > 200


class Page:
    def __init__(self, n, width, height):
        self.n = n
        self.width = width
        self.height = height
        self.lines = []        # content lines (reading order)
        self.header = []       # running heads removed from content
        self.footer = []       # running feet removed from content
        self.printed_label = None
        self.label = None
        self.label_inferred = False
        self.fills = []        # filled rectangles (chat bubbles, boxes): (rect, luminance)
        self.drawings = []     # raw drawings (for art)
        self.images = []       # raster image rects

    @property
    def blank(self):
        return not self.lines and not self.drawings and not self.images


def _merge_row_fragments(lines, max_gap=30):
    """A bullet or list number set apart with a tab comes out as its own fragment on
    the same baseline: glue such fragments back into one line."""
    out = []
    for l in lines:
        p = out[-1] if out else None
        if (p is not None and abs(p.y1 - l.y1) < 1.5 and 0 <= l.x0 - p.x1 < max_gap
                and len(p.text.strip()) <= 4):
            sp = p.spans + [Span.__new__(Span)] + l.spans
            filler = sp[len(p.spans)]
            for attr in Span.__slots__:
                setattr(filler, attr, getattr(l.spans[0], attr))
            filler.t = " "
            merged = Line(p.page, (p.x0, min(p.y0, l.y0), l.x1, max(p.y1, l.y1)), sp)
            merged.font, merged.size, merged.color, merged.key = l.font, l.size, l.color, l.key
            merged.light = l.light
            out[-1] = merged
            continue
        out.append(l)
    return out


def _column_order(lines, page_width):
    """Two-column pages (name lists, glossaries): read the left column, then the
    right one. Detected when many lines share a baseline with a line that starts
    in the right half of the page."""
    mid = page_width * 0.45
    rows = {}
    for l in lines:
        rows.setdefault(round(l.y0), []).append(l)
    paired = sum(1 for r in rows.values() if len(r) >= 2 and any(x.x0 < mid for x in r) and any(x.x0 >= mid for x in r))
    if paired < 5 or paired < len(rows) * 0.4:
        return lines
    paired_ys = [y for y, r in rows.items() if len(r) >= 2]
    top, bottom = min(paired_ys), max(paired_ys)
    before = [l for l in lines if round(l.y0) < top]
    after = [l for l in lines if round(l.y0) > bottom]
    inside = [l for l in lines if top <= round(l.y0) <= bottom]
    left = [l for l in inside if l.x0 < mid]
    right = [l for l in inside if l.x0 >= mid]
    return before + left + right + after


def load(pdf_path):
    """Open a PDF and return (doc, pages, stamp_text). Raises on encrypted PDFs."""
    doc = pymupdf.open(pdf_path)
    if doc.needs_pass or doc.is_encrypted:
        raise PermissionError(
            "This PDF is encrypted or password-protected. pdf2epub does not remove copy "
            "protection. Use an unprotected copy you have the rights to.")
    pages = []
    tiny_texts = {}
    for pi, p in enumerate(doc):
        pg = Page(pi + 1, p.rect.width, p.rect.height)
        td = p.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
        seen = set()
        lines = []
        for b in td["blocks"]:
            if b["type"] != 0:
                continue
            for l in b["lines"]:
                if abs(l.get("dir", (1, 0))[1]) > 0.1:   # rotated text (spines, stamps)
                    continue
                sp = [Span(s) for s in l["spans"] if s["text"] != ""]
                if not sp:
                    continue
                ln = Line(pi + 1, l["bbox"], sp)
                if not ln.text.strip():
                    continue
                key = (round(ln.x0), round(ln.y0), ln.text)
                if key in seen:            # faux-bold double printing
                    continue
                seen.add(key)
                if ln.size < 5:            # buyer stamps, watermarks, slugs
                    tiny_texts.setdefault(ln.text.strip(), set()).add(pi)
                    continue
                lines.append(ln)
        lines.sort(key=lambda l: (round(l.y0), l.x0))
        lines = _merge_row_fragments(lines)
        pg.lines = _column_order(lines, p.rect.width)
        try:
            dr = p.get_drawings()
        except Exception:
            dr = []
        pg.drawings = dr
        for d in dr:
            f = d.get("fill")
            r = d.get("rect")
            if f is not None and r is not None and r.width > 8 and r.height > 8:
                lum = 0.299 * f[0] + 0.587 * f[1] + 0.114 * f[2]
                pg.fills.append((r, lum))
        try:
            for info in p.get_image_info():
                r = pymupdf.Rect(info["bbox"])
                if r.width > 36 and r.height > 36:
                    pg.images.append(r)
        except Exception:
            pass
        pages.append(pg)
    stamp = None
    if tiny_texts:
        t, ps = max(tiny_texts.items(), key=lambda kv: len(kv[1]))
        if len(ps) >= max(2, len(pages) // 2):
            stamp = t
    return doc, pages, stamp
