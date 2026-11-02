"""Analyse a PDF and propose a style map (book config) for the author to confirm."""
import collections
import re
import statistics

from .model import family, is_mono_font, is_sans_font
from .text import is_folio, shift_label, words

ROLES = ("body", "heading", "subheading", "note", "screen", "chat", "chat_label", "email",
         "blockquote", "scene_break", "caption", "footnote", "dropcap", "verse", "ignore")

SECTION_TYPES = {
    # keyword (lower-case, start of title) -> (section type, epub:type, matter)
    "contents": ("toc", "toc", "front"),
    "table of contents": ("toc", "toc", "front"),
    "copyright": ("copyright", "copyright-page", "front"),
    "dedication": ("chapter", "dedication", "front"),
    "epigraph": ("chapter", "epigraph", "front"),
    "foreword": ("chapter", "foreword", "front"),
    "preface": ("chapter", "preface", "front"),
    "introduction": ("chapter", "introduction", "front"),
    "prologue": ("chapter", "prologue", "body"),
    "epilogue": ("chapter", "epilogue", "body"),
    "afterword": ("chapter", "afterword", "back"),
    "acknowledg": ("chapter", "acknowledgments", "back"),
    "thank you": ("chapter", "acknowledgments", "back"),
    "about the author": ("chapter", "afterword", "back"),
    "about the authors": ("chapter", "afterword", "back"),
    "about": ("chapter", "afterword", "back"),
    "glossary": ("chapter", "glossary", "back"),
    "appendix": ("chapter", "appendix", "back"),
    "notes": ("chapter", "endnotes", "back"),
    "bibliography": ("chapter", "bibliography", "back"),
    "index": ("chapter", "index", "back"),
}

FILENAME_TITLE = re.compile(r"(\.indd|\.docx?|\.pages|\.qxp|^untitled|^microsoft word|^document\d*$)", re.I)
SYMBOLS = set("*#~•·◆◇❖❧☙⁂§°+=_-—–. ")


def _mode(vals, default=None):
    vals = [v for v in vals if v is not None]
    if not vals:
        return default
    return collections.Counter(vals).most_common(1)[0][0]


def _pct(vals, q, default=0.0):
    vals = sorted(vals)
    if not vals:
        return default
    return vals[min(len(vals) - 1, max(0, int(round(q * (len(vals) - 1)))))]


def _inside(line, rect, pad=2):
    return (rect.x0 - pad <= line.x0 and line.x1 <= rect.x1 + pad
            and rect.y0 - pad <= line.y0 and line.y1 <= rect.y1 + pad)


def detect_geometry(pages, body_key):
    body = [l for pg in pages for l in pg.lines if l.key == body_key]
    gaps = []
    for pg in pages:
        bl = [l for l in pg.lines if l.key == body_key]
        for a, b in zip(bl, bl[1:]):
            g = round(b.y0 - a.y0, 1)
            if 0 < g < 60:
                gaps.append(g)
    leading = _mode(gaps, 14.0)
    bigger = [g for g in gaps if leading * 1.08 < g < leading * 1.9]
    para_gap = _mode(bigger, leading)
    margins = {"odd": [], "even": []}
    for pg in pages:
        xs = [round(l.x0) for l in pg.lines if l.key == body_key]
        if len(xs) >= 4:
            margins["odd" if pg.n % 2 else "even"].append(_mode(xs))
    m_odd = _mode(margins["odd"], None)
    m_even = _mode(margins["even"], None)
    m_odd = m_odd if m_odd is not None else (m_even or 36)
    m_even = m_even if m_even is not None else m_odd
    indents = []
    for pg in pages:
        m = m_odd if pg.n % 2 else m_even
        bl = [l for l in pg.lines if l.key == body_key]
        for a, l in zip(bl, bl[1:]):
            # a first-line indent follows a line that ended a sentence; list items don't count
            if not a.text.rstrip().endswith(('.', '!', '?', '"', '”', "'", '’', ':')):
                continue
            if re.match(r"^\s*([•·◦▪‣●○■□–-]|\(?\d{1,3}[.)])\s", l.text):
                continue
            d = round(l.x0 - m)
            if 3 <= d <= 40:
                indents.append(d)
    indent = _mode(indents, 0)
    widths = [l.width for l in body]
    text_width = _pct(widths, 0.98, 300.0)
    top = _pct([l.y0 for l in body], 0.01, 40.0)
    bottom = _pct([l.y1 for l in body], 0.99, pages[0].height - 40 if pages else 600)
    return {
        "page_width": round(pages[0].width, 1) if pages else 0,
        "page_height": round(pages[0].height, 1) if pages else 0,
        "leading": leading,
        "paragraph_gap": para_gap,
        "indent": indent,
        "margin_odd": m_odd,
        "margin_even": m_even,
        "text_width": round(text_width, 1),
        "body_top": round(top, 1),
        "body_bottom": round(bottom, 1),
    }


def split_running_heads(pages, geo, body_size=None):
    """Move running heads/feet out of the content and read printed page numbers.
    Works by position (outside the body text area), not by font size."""
    top, bottom = geo["body_top"], geo["body_bottom"]
    repeats = collections.Counter()
    for pg in pages:
        for l in pg.lines:
            if l.y1 < top - 1 or l.y0 > bottom + 1:
                repeats[re.sub(r"\d+", "#", l.text.strip().lower())] += 1
    for pg in pages:
        keep = []
        for l in pg.lines:
            t = l.text.strip()
            lead = geo.get("leading", 12)
            in_head = l.y1 < top - lead * 0.3
            in_foot = l.y0 > bottom + lead * 0.5
            if (in_head or in_foot) and is_folio(t):
                pg.printed_label = t
                (pg.header if in_head else pg.footer).append(l)
                continue
            small = body_size is not None and l.size <= body_size * 0.95
            repeated = repeats[re.sub(r"\d+", "#", t.lower())] >= 3
            if (in_foot and repeated) or (in_head and (repeated or (small and len(pg.lines) > 6))):
                (pg.header if in_head else pg.footer).append(l)
                continue
            keep.append(l)
        pg.lines = keep


def infer_labels(pages, max_dist=6):
    """Give unnumbered pages (chapter openers, blanks, art pages) the number they
    would have in print, counted from the nearest printed number."""
    known = [(i, pg.printed_label) for i, pg in enumerate(pages) if pg.printed_label]
    used = {l for _, l in known}
    for i, pg in enumerate(pages):
        if pg.printed_label:
            pg.label = pg.printed_label
            continue
        nxt = next(((j, l) for j, l in known if j > i), None)
        prv = next(((j, l) for j, l in reversed(known) if j < i), None)
        cand = None
        if nxt and nxt[0] - i <= max_dist:
            cand = shift_label(nxt[1], i - nxt[0])
        if cand is None and prv and i - prv[0] <= max_dist:
            cand = shift_label(prv[1], i - prv[0])
        if cand and cand not in used:
            pg.label = cand
            pg.label_inferred = True
            used.add(cand)


def guess_roles(pages, body_key, geo=None):
    """Guess what each font@size style is used for. The author confirms or edits."""
    chars = collections.Counter()
    samples, page_sets, inside_fill, symbol_only = {}, collections.defaultdict(set), collections.Counter(), collections.Counter()
    has_email_hdr = collections.Counter()
    lines_n = collections.Counter()
    whole_line = collections.Counter()     # line made only of this style
    in_flow = collections.Counter()        # body text above and below on the same page
    bottom_zone = collections.Counter()    # near the bottom of the text area
    starts_num = collections.Counter()     # starts with a note number/symbol
    short_chars = collections.Counter()    # 1-2 character lines (drop caps)
    width_sum = collections.Counter()
    text_w = (geo or {}).get("text_width", 300) or 300
    body_bottom = (geo or {}).get("body_bottom", 10 ** 6)
    body_top = (geo or {}).get("body_top", 0)
    for pg in pages:
        body_y = [l.y0 for l in pg.lines if l.key == body_key]
        for l in pg.lines:
            t = l.text.strip()
            chars[l.key] += len(t)
            lines_n[l.key] += 1
            page_sets[l.key].add(pg.n)
            samples.setdefault(l.key, t[:48])
            width_sum[l.key] += l.width
            if all(s.key == l.key or not s.t.strip() for s in l.spans):
                whole_line[l.key] += 1
            if body_y and min(body_y) < l.y0 < max(body_y):
                in_flow[l.key] += 1
            span = max(1.0, body_bottom - body_top)
            if l.y0 > body_top + span * 0.72:
                bottom_zone[l.key] += 1
            if re.match(r"^[\d*†‡§]{1,3}[\s.)]", t):
                starts_num[l.key] += 1
            if len(t) <= 2 and t.isalpha():
                short_chars[l.key] += 1
            if any(_inside(l, r) for r, lum in pg.fills if r.height < 300):
                inside_fill[l.key] += 1
            if t and set(t) <= SYMBOLS and len(t) <= 12 and any(c in t for c in "*#~•◆◇❖❧☙⁂§"):
                symbol_only[l.key] += 1
            if re.match(r"^(From|To|Subject|Sent|Date|Cc):\s", t):
                has_email_hdr[l.key] += 1
    body_font = body_key.split("@")[0]
    body_size = float(body_key.split("@")[1])
    body_fam = family(body_font)
    styles = []
    for key, n in chars.most_common():
        font, size = key.split("@")
        size = float(size)
        fam = family(font)
        nl = max(1, lines_n[key])
        bold = any(w in font.lower() for w in ("bold", "black", "heavy", "semibold"))
        avg_w = width_sum[key] / nl
        if key == body_key:
            role = "body"
        elif short_chars[key] >= nl * 0.8 and size >= body_size * 1.8:
            role = "dropcap"
        elif symbol_only[key] >= max(1, nl * 0.8):
            role = "scene_break"
        elif is_mono_font(font):
            role = "screen"
        elif inside_fill[key] >= nl * 0.6 and is_sans_font(font):
            role = "chat"
        elif is_sans_font(font) and size < body_size * 0.9 and any(inside_fill[k] for k in chars if is_sans_font(k)):
            role = "chat_label"
        elif size >= body_size * 1.35 and in_flow[key] < nl * 0.5:
            role = "heading"
        elif size >= body_size * 1.08 and in_flow[key] >= nl * 0.5 and whole_line[key] >= nl * 0.8:
            role = "subheading"     # in-text headings in nonfiction
        elif (fam == body_fam and bold and abs(size - body_size) <= 0.6 and whole_line[key] >= nl * 0.9
              and avg_w < text_w * 0.7 and in_flow[key] >= nl * 0.5 and nl >= 2 and n / nl < 60):
            role = "subheading"     # bold run-in headings set at body size
        elif fam == body_fam and abs(size - body_size) <= 0.3:
            role = "body"           # italic/bold variants of the body face
        elif has_email_hdr[key]:
            role = "email"
        elif (size < body_size * 0.92 and bottom_zone[key] >= nl * 0.7 and starts_num[key] >= 1):
            role = "footnote"
        elif size > body_size * 1.05:
            role = "note"           # opening-page text: bylines, dedications, warnings
        elif size >= body_size * 0.85:
            role = "blockquote"
        else:
            role = "caption"
        styles.append({"style": key, "role": role, "chars": n,
                       "pages": _page_ranges(sorted(page_sets[key]))[:6], "sample": samples[key]})
    return styles


def detect_profile(pages, body_key, geo, sections):
    """What kind of book is this, and how is its text set?"""
    body = [l for pg in pages for l in pg.lines if l.key == body_key]
    tw = geo["text_width"] or 1
    full = sum(1 for l in body if l.width >= tw * 0.97)
    if body and statistics.median([l.width for l in body]) < tw * 0.75:
        full = 0
    justified = bool(body) and full / len(body) > 0.45
    short = sum(1 for l in body if l.width < tw * 0.6)
    indent = geo.get("indent", 0)
    spaced = geo["paragraph_gap"] > geo["leading"] * 1.08
    if indent and spaced:
        pstyle = "both"
    elif indent:
        pstyle = "indent"
    else:
        pstyle = "spaced"
    bylines = len({s.get("author") for s in sections if s.get("author")})
    chapters = [s for s in sections if s["type"] == "chapter"]
    usable = (geo.get("page_width") or tw) - geo.get("margin_odd", 0) - geo.get("margin_even", 0)
    med = statistics.median([l.width for l in body]) if body else tw
    if body and med < usable * 0.55 and not justified:
        kind = "poetry"
    elif bylines >= 3:
        kind = "anthology"
    else:
        kind = "prose"
    return {"book_kind": kind, "paragraph_style": pstyle,
            "alignment": "justified" if justified else "ragged"}


def _page_ranges(ns):
    out, start, prev = [], None, None
    for n in ns:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append(f"{start}" if start == prev else f"{start}-{prev}")
            start = prev = n
    if start is not None:
        out.append(f"{start}" if start == prev else f"{start}-{prev}")
    return out


def _join_heading(block):
    """'Chapter 1' + 'The Beginning' -> 'Chapter 1: The Beginning'; wrapped lines of
    one title are joined with a space."""
    out = ""
    for i, l in enumerate(block):
        t = _clean_title(l.text)
        if not out:
            out = t
        elif l.key != block[i - 1].key and not out.endswith((":", ".", "!", "?", "—", "-")):
            out += ": " + t
        else:
            out += " " + t
    return _clean_title(out)


def _clean_title(t):
    t = re.sub(r"\s+", " ", t).strip()
    return t


def detect_sections(pages, role_of, book_title_hint):
    """Find where sections start: pages with a heading-role line in the top part."""
    heading_sizes = sorted({float(k.split("@")[1]) for k, r in role_of.items() if r == "heading"}, reverse=True)
    starts = []
    for pg in pages:
        hl = [l for l in pg.lines if role_of.get(l.key) == "heading" and l.y0 < pg.height * 0.7]
        if not hl:
            continue
        # a heading block = consecutive heading lines near the first one
        hl = [l for l in hl if not re.match(r"^\s*by[:\s]", l.text.strip(), re.I)]
        if not hl:
            continue
        first = hl[0]
        above = [l for l in pg.lines if l.y1 <= first.y0 + 1 and first.y0 - l.y0 < 60
                 and re.match(r"^(chapter|part|book|act|section)\s+[\w-]+$", l.text.strip(), re.I)]
        # the title = lines of (about) the same size as the first heading line, close together
        block = [l for l in hl if l.y0 - first.y0 < 120 and abs(l.size - first.size) <= first.size * 0.3]
        title = _join_heading(above[-1:] + block)
        if not title or is_folio(title):
            continue
        starts.append((pg.n, title))
    sections = []
    # front pages before the first heading
    first_start = starts[0][0] if starts else len(pages) + 1
    for i, (n, title) in enumerate(starts):
        end = (starts[i + 1][0] - 1) if i + 1 < len(starts) else len(pages)
        low = title.lower()
        stype, etype, matter = "chapter", "chapter", "body"
        for kw, v in SECTION_TYPES.items():
            if low.startswith(kw):
                stype, etype, matter = v
                break
        if book_title_hint and _similar(title, book_title_hint) and n <= 8:
            stype, etype, matter = "titlepage", "titlepage", "front"
        sections.append({"type": stype, "epub_type": etype, "matter": matter, "title": title,
                         "pages": [n, end]})
    # copyright page among the front pages
    pre = []
    for pg in pages[:first_start - 1]:
        txt = " ".join(l.text for l in pg.lines)
        if re.search(r"(©|copyright|all rights reserved|isbn)", txt, re.I):
            pre.append({"type": "copyright", "epub_type": "copyright-page", "matter": "front",
                        "title": "Copyright", "pages": [pg.n, pg.n]})
    # a copyright page can also sit between title pages (after the first heading)
    for s in list(sections):
        if s["type"] == "titlepage":
            for n in range(s["pages"][0] + 1, s["pages"][1] + 1):
                txt = " ".join(l.text for l in pages[n - 1].lines)
                if re.search(r"(©|all rights reserved|isbn)", txt, re.I):
                    end = s["pages"][1]
                    s["pages"][1] = n - 1
                    sections.insert(sections.index(s) + 1, {
                        "type": "copyright", "epub_type": "copyright-page", "matter": "front",
                        "title": "Copyright", "pages": [n, end]})
                    break
    # merge consecutive title pages
    merged = []
    for s in pre + sections:
        if merged and s["type"] == "titlepage" and merged[-1]["type"] == "titlepage":
            merged[-1]["pages"][1] = s["pages"][1]
            continue
        merged.append(s)
    # an epigraph page: short page of non-body text inside front matter, no heading
    out = []
    first_body = next((s["pages"][0] for s in merged if s.get("matter") == "body"), len(pages) + 1)
    for s in merged:
        out.append(s)
        if s["type"] in ("toc",) or s["pages"][0] >= first_body:
            continue
        for n in range(s["pages"][0] + 1, s["pages"][1] + 1):
            ls = pages[n - 1].lines
            if 0 < len(ls) <= 14 and all(role_of.get(l.key) not in ("body", "heading") for l in ls) \
                    and sum(len(l.text) for l in ls) > 40:
                end = s["pages"][1]
                s["pages"][1] = n - 1
                out.append({"type": "chapter", "epub_type": "epigraph", "matter": "front",
                            "title": "", "pages": [n, end]})
                break
    merged = out
    # back-matter groups: "Thank You Patrons!" followed by "Gold Patrons", "Silver Patrons"
    grouped = []
    for s in merged:
        prev = grouped[-1] if grouped else None
        if (prev is not None and prev.get("matter") == "back" and s["type"] == "chapter"
                and _shared_word(prev["title"], s["title"])):
            prev["pages"][1] = s["pages"][1]
            prev.setdefault("subsections", []).append({"title": s["title"], "page": s["pages"][0]})
            continue
        grouped.append(s)
    merged = grouped
    # contents pages: many lines ending in page numbers / dot leaders
    for s in merged:
        if s["type"] == "chapter":
            lines = [l for n in range(s["pages"][0], s["pages"][1] + 1) for l in pages[n - 1].lines]
            leader = sum(1 for l in lines if re.search(r"(\.{4,}|…{2,}|\s{3,})\s*[0-9ivxlc]+\s*$", l.text))
            if lines and leader >= max(3, len(lines) * 0.3):
                s.update(type="toc", epub_type="toc", matter="front")
    return merged


def _shared_word(a, b):
    wa = {w for w in re.findall(r"[a-z]{5,}", a.lower())}
    wb = {w for w in re.findall(r"[a-z]{5,}", b.lower())}
    return bool(wa & wb)


def _similar(a, b):
    na = re.sub(r"[^a-z0-9]", "", a.lower())
    nb = re.sub(r"[^a-z0-9]", "", b.lower())
    return bool(na) and bool(nb) and (na.startswith(nb[:12]) or nb.startswith(na[:12]))


def detect_bylines(pages, sections):
    for s in sections:
        if s["type"] != "chapter":
            continue
        for n in range(s["pages"][0], min(s["pages"][0] + 1, s["pages"][1]) + 1):
            for l in pages[n - 1].lines[:12]:
                m = re.match(r"^\s*by[:\s]\s*(.+)$", l.text.strip(), re.I)
                if m and len(m.group(1)) < 60:
                    s["author"] = m.group(1).strip()
                    break
            if "author" in s:
                break


def detect_hyphenation(pages):
    """Was the print set with automatic hyphenation? Count line-end hyphens whose
    joined form also appears as a word elsewhere."""
    vocab = collections.Counter()
    ends = []
    for pg in pages:
        for a, b in zip(pg.lines, pg.lines[1:]):
            m = re.search(r"([A-Za-z]{2,})-$", a.text.rstrip())
            n = re.match(r"([a-z]{2,})", b.text.lstrip())
            if m and n:
                ends.append((m.group(1) + n.group(1)).lower())
        for l in pg.lines:
            for w in re.findall(r"[A-Za-z]+", l.text):
                vocab[w.lower()] += 1
    if not ends:
        return False
    hits = sum(1 for w in ends if vocab[w] > 0)
    lines = sum(len(pg.lines) for pg in pages)
    return len(ends) > lines * 0.01 and hits / len(ends) > 0.4


def _copyright_facts(pages):
    """Publisher, year and first ISBN from a copyright page, if there is one."""
    for pg in pages[:12]:
        txt = " ".join(l.text for l in pg.lines)
        if not re.search(r"(©|copyright|all rights reserved)", txt, re.I):
            continue
        pub = ""
        m = re.search(r"(?:©|copyright)\s*(?:©\s*)?(\d{4})?\s*(?:by\s+)?([A-Z][\w&.,' -]{2,60}?)(?:\.|\s{2,}|$| All)", txt, re.I)
        year = ""
        if m:
            year = m.group(1) or ""
            pub = m.group(2).strip(" ,.")
        y = re.search(r"\b(19|20)\d{2}\b", txt)
        if not year and y:
            year = y.group(0)
        i = re.search(r"97[89][\d-]{10,16}", txt)
        return pub, year, (re.sub(r"[^0-9]", "", i.group(0)) if i else "")
    return "", "", ""


def analyze(doc, pages, stamp=None):
    chars = collections.Counter()
    for pg in pages:
        for l in pg.lines:
            chars[l.key] += len(l.text.strip())
    if not chars:
        raise ValueError("No text found. This looks like a scanned PDF; Aldleaf needs a text-based PDF.")
    body_key = chars.most_common(1)[0][0]
    geo = detect_geometry(pages, body_key)
    geo["body_size"] = float(body_key.split("@")[1])
    split_running_heads(pages, geo, geo["body_size"])
    infer_labels(pages)
    styles = guess_roles(pages, body_key, geo)
    role_of = {s["style"]: s["role"] for s in styles}
    meta_title = (doc.metadata or {}).get("title") or ""
    if FILENAME_TITLE.search(meta_title) or not meta_title.strip():
        meta_title = ""
    title_hint = meta_title
    if not title_hint:
        # the fullest version of the first heading on the opening pages (half-title vs title page)
        cands = []
        for pg in pages[:8]:
            hl = [l for l in pg.lines if role_of.get(l.key) == "heading"]
            if hl:
                cands.append(_join_heading(hl).rstrip(":"))
        if cands:
            first = cands[0]
            title_hint = max((c for c in cands if _similar(c, first)), key=len, default=first)
    pub, year, isbn = _copyright_facts(pages)
    sections = detect_sections(pages, role_of, title_hint)
    detect_bylines(pages, sections)
    author = (doc.metadata or {}).get("author") or ""
    section_authors = [s.get("author") for s in sections if s.get("author")]
    if not author and section_authors:
        common = collections.Counter(section_authors).most_common(1)[0]
        if common[1] >= len(section_authors) * 0.6:
            author = common[0]
    config = {
        "aldleaf": 1,
        "metadata": {
            "title": title_hint or "Untitled",
            "subtitle": "",
            "authors": [author] if author else [],
            "publisher": pub,
            "language": "en",
            "date": year,
            "isbn": isbn,
            "description": "",
            "subjects": [],
        },
        "options": {
            "cover": None,
            "cover_page": 1,
            "stamp": False,
            "stamp_detected": bool(stamp),
            "auto_hyphenated": detect_hyphenation(pages),
            "fonts": {},
            "art": "auto",          # auto: grey vector art -> adaptive SVG; png: always pictures
            "short_line": 0.75,
            "scene_break_gap": round(max(geo["leading"] * 2.0, geo["paragraph_gap"] * 1.6), 1),
            "page_list": True,
            "scene_breaks": "as_printed",
            **detect_profile(pages, body_key, geo, sections),
        },
        "geometry": geo,
        "styles": styles,
        "sections": sections,
        "page_labels": {
            "printed": sum(1 for p in pages if p.printed_label),
            "inferred": sum(1 for p in pages if p.label_inferred),
            "overrides": {},
        },
    }
    return config


def summarize(config):
    """Human-readable summary of a proposed config (for the CLI and the skill)."""
    out = []
    m = config["metadata"]
    out.append(f"Title: {m['title']}   Authors: {', '.join(m['authors']) or '(none found)'}")
    g = config["geometry"]
    out.append(f"Layout: {g['page_width']}x{g['page_height']} pt, leading {g['leading']}, "
               f"paragraph gap {g['paragraph_gap']}, indent {g['indent']}, text width {g['text_width']}")
    out.append("Styles (font@size -> role):")
    for s in config["styles"][:20]:
        out.append(f"  {s['style']:<38} {s['role']:<12} {s['chars']:>8} chars  p{','.join(s['pages'][:3])}")
    out.append("Sections:")
    for s in config["sections"]:
        a = f" (by {s['author']})" if s.get("author") else ""
        out.append(f"  p{s['pages'][0]}-{s['pages'][1]:<5} {s['type']:<10} {s['title'][:50]}{a}")
    pl = config["page_labels"]
    out.append(f"Page numbers: {pl['printed']} printed, {pl['inferred']} inferred")
    o = config["options"]
    out.append(f"Auto-hyphenated print: {o['auto_hyphenated']}   Buyer/licence stamp found: {o['stamp_detected']}")
    return "\n".join(out)
