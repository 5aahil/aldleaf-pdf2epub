"""Artwork: vector badges, stamps, logos and ornaments from the PDF.

Monochrome vector art becomes an *adaptive inline SVG*: the shapes are used as a
luminance mask over one rectangle filled with `currentColor`. Dark ink stays
opaque, mid-greys become partly transparent, white disappears. So the mark is
dark on white and sepia pages and light on night pages, with no white box, and
it stays sharp at any size. A transparent PNG goes alongside as the fallback for
Kindle (which may not render inline SVG reliably).

Colour artwork and raster images are kept as images.
"""
from .text import esc


def _f(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def _is_grey(c, tol=0.06):
    return c is None or (abs(c[0] - c[1]) < tol and abs(c[1] - c[2]) < tol)


def drawings_in(page_drawings, rect, pad=1.0):
    out = []
    for d in page_drawings:
        r = d.get("rect")
        if r is None:
            continue
        if r.x0 >= rect.x0 - pad and r.x1 <= rect.x1 + pad and r.y0 >= rect.y0 - pad and r.y1 <= rect.y1 + pad:
            out.append(d)
    return out


def is_monochrome(drawings):
    """True if every fill and stroke is a grey (any shade): safe to recolour."""
    if not drawings:
        return False
    for d in drawings:
        if not _is_grey(d.get("fill")) or not _is_grey(d.get("color")):
            return False
    return True


def adaptive_svg(drawings, rect, uid, label):
    """Inline SVG that paints the artwork in the reader's text colour."""
    ox, oy = rect.x0, rect.y0
    P = lambda pt: f"{_f(pt.x - ox)} {_f(pt.y - oy)}"
    paths = []
    for x in drawings:
        d, cur = [], None
        for it in x.get("items", []):
            op = it[0]
            if op == "re":
                rc, orient = it[1], (it[2] if len(it) > 2 else 1)
                pts = [rc.tl, rc.tr, rc.br, rc.bl] if orient != -1 else [rc.tl, rc.bl, rc.br, rc.tr]
                d.append("M" + P(pts[0]) + "".join("L" + P(q) for q in pts[1:]) + "Z")
                cur = None
                continue
            if op == "qu":
                q = it[1]
                d.append("M" + P(q.ul) + "L" + P(q.ur) + "L" + P(q.lr) + "L" + P(q.ll) + "Z")
                cur = None
                continue
            start = it[1]
            if cur is None or abs(cur.x - start.x) > 0.01 or abs(cur.y - start.y) > 0.01:
                d.append("M" + P(start))
            if op == "l":
                d.append("L" + P(it[2]))
                cur = it[2]
            elif op == "c":
                d.append("C" + P(it[2]) + " " + P(it[3]) + " " + P(it[4]))
                cur = it[4]
        if not d:
            continue
        if x.get("closePath"):
            d.append("Z")
        attrs = []
        f = x.get("fill")
        if f is not None:
            v = max(0, min(255, round(255 * (1 - _lum(f)) / 0.98)))   # ink amount -> mask opacity
            attrs.append(f'fill="rgb({v},{v},{v})"')
            if x.get("even_odd"):
                attrs.append('fill-rule="evenodd"')
        else:
            attrs.append('fill="none"')
        c = x.get("color")
        if c is not None and x.get("width"):
            v = max(0, min(255, round(255 * (1 - _lum(c)) / 0.98)))
            attrs.append(f'stroke="rgb({v},{v},{v})" stroke-width="{_f(x["width"])}"')
            if x.get("lineCap"):
                cap = {0: "butt", 1: "round", 2: "square"}.get(max(x["lineCap"]) if isinstance(x["lineCap"], (tuple, list)) else x["lineCap"], "butt")
                attrs.append(f'stroke-linecap="{cap}"')
        paths.append(f'<path d="{"".join(d)}" {" ".join(attrs)}/>')
    w, h = _f(rect.width), _f(rect.height)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="art-svg" viewBox="0 0 {w} {h}" '
            f'role="img" aria-labelledby="{uid}-t"><title id="{uid}-t">{esc(label)}</title>'
            f'<defs><mask id="{uid}-m" maskUnits="userSpaceOnUse" x="0" y="0" width="{w}" height="{h}">'
            f'<rect x="0" y="0" width="{w}" height="{h}" fill="black"/>{"".join(paths)}</mask></defs>'
            f'<rect x="0" y="0" width="{w}" height="{h}" fill="currentColor" mask="url(#{uid}-m)"/></svg>')
