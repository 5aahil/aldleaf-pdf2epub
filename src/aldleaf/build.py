"""Build an EPUB 3 from a PDF and a confirmed book config."""
import datetime
import os
import re
import uuid
import zipfile

from . import __version__
from .analyze import infer_labels, split_running_heads
from .art import adaptive_svg, drawings_in, is_monochrome
from .layout import Layout, line_runs
from .model import load, pymupdf
from .i18n import byline_text, labels, page_label, text_layer_issues
from .render import blocks_to_html, build_css, xhtml
from .text import (Dehyphenator, append_line, esc, esc_attr, is_folio, pagebreak_html,
                   render_runs, strip_runs, words)

MATTER = {"front": "frontmatter", "body": "bodymatter", "back": "backmatter"}
ROLE_FOR_EPUB_TYPE = {
    "chapter": "doc-chapter", "foreword": "doc-foreword", "preface": "doc-preface",
    "introduction": "doc-introduction", "prologue": "doc-prologue", "epilogue": "doc-epilogue",
    "afterword": "doc-afterword", "acknowledgments": "doc-acknowledgments",
    "dedication": "doc-dedication", "epigraph": "doc-epigraph", "glossary": "doc-glossary",
    "appendix": "doc-appendix", "endnotes": "doc-endnotes", "bibliography": "doc-bibliography",
    "index": "doc-index",
}


def _letters(t):
    return sum(1 for c in t if c.isalnum())


def _page_text_words(pages, a, b):
    return sum(len(words(l.text)) for pg in pages[a - 1:b] for l in pg.lines)


def _page_letters(pages, a, b):
    return sum(_letters(l.text) for pg in pages[a - 1:b] for l in pg.lines)


def _html_text(x):
    import html as _h
    body = x[x.index("<body"):] if "<body" in x else x
    body = re.sub(r'<p class="byline">([^<\s]+) ', r'<p class="byline">\1: ', body)
    body = re.sub(r"<svg.*?</svg>", " ", body, flags=re.S)       # artwork titles are alt text, not book text
    return _h.unescape(re.sub(r"<[^>]+>", " ", body))


def _html_words(x):
    return len(words(_html_text(x)))


def build(pdf_path, config, out_path, stamp=None, log=print):
    """Returns (out_path, report dict)."""
    doc, pages, detected_stamp = load(pdf_path)
    meta, opt, geo = config["metadata"], config["options"], config["geometry"]
    lang = meta.get("language") or "en"
    lab = labels(lang)
    split_running_heads(pages, geo, geo.get("body_size"))
    infer_labels(pages)
    for k, v in (config.get("page_labels", {}).get("overrides") or {}).items():
        pages[int(k) - 1].label = str(v)
    if not opt.get("page_list", True):
        for pg in pages:
            pg.label = None
    role_of = {s["style"]: s["role"] for s in config["styles"]}
    for pg in pages:
        for l in pg.lines:
            l.role = role_of.get(l.key, "body")

    dh = Dehyphenator(bool(opt.get("auto_hyphenated")))
    for pg in pages:
        for l in pg.lines:
            dh.learn(re.sub(r"\S+-$", "", l.text.rstrip()))
    body = [l.text for pg in pages for l in pg.lines if l.role == "body" and len(l.text.strip()) > 8]
    dh.line_end_spaces = bool(body) and sum(t[-1:].isspace() for t in body) / len(body) >= 0.3

    stats = {}
    layout = Layout(pages, config, dh, stats)
    files, images, pagelist, used_labels = [], [], [], set()
    report = {"sections": [], "problems": []}

    def collect(href, x):
        for m in re.finditer(r'id="page-([^"]+)"', x):
            lab = m.group(1)
            if lab not in used_labels:
                used_labels.add(lab)
                pagelist.append((lab, f"{href}#page-{lab}"))

    img_count = [0]

    art_mode = opt.get("art", "auto")      # auto | svg | png
    alt_overrides = opt.get("art_alt") or {}

    def figure_src(b):
        """Return the XHTML for one piece of artwork."""
        img_count[0] += 1
        k = img_count[0]
        name = f"fig{k:03d}.png"
        p = doc[b.page - 1]
        r = pymupdf.Rect(b.rect.x0 - 1, b.rect.y0 - 1, b.rect.x1 + 1, b.rect.y1 + 1)
        near = [l for l in pages[b.page - 1].lines if l.role == "caption" and 0 <= l.y0 - b.rect.y1 < 40]
        alt = alt_overrides.get(f"{b.page}") or (near[0].text.strip() if near else "") or "Illustration"
        pct = max(10, min(100, round(100 * b.rect.width / max(geo["text_width"], 1))))
        is_raster = any(r.intersects(ir) for ir in pages[b.page - 1].images)
        dr = drawings_in(pages[b.page - 1].drawings, r)
        if art_mode != "png" and not is_raster and is_monochrome(dr):
            # adaptive SVG (follows the reader's theme) + transparent PNG fallback for Kindle
            png = p.get_pixmap(clip=r, dpi=300, alpha=True).tobytes("png")
            images.append((f"img{k:03d}", f"images/{name}", png, "image/png", None))
            svg = adaptive_svg(dr, r, f"art{k:03d}", alt)
            stats["svg_art"] = stats.get("svg_art", 0) + 1
            return (f'<div class="figure art" style="width: {pct}%">{svg}'
                    f'<img class="kf8-fallback" src="../images/{name}" alt="{esc_attr(alt)}"/></div>')
        png = p.get_pixmap(clip=r, dpi=300, alpha=False).tobytes("png")
        images.append((f"img{k:03d}", f"images/{name}", png, "image/png", None))
        return f'<div class="figure"><img src="../images/{name}" alt="{esc_attr(alt)}" style="width: {pct}%"/></div>' 

    # ---- cover
    cover_path = opt.get("cover")
    if cover_path and os.path.exists(cover_path):
        data = open(cover_path, "rb").read()
        ext = os.path.splitext(cover_path)[1].lower()
        mt = "image/png" if ext == ".png" else "image/jpeg"
        cname = "cover.png" if ext == ".png" else "cover.jpg"
    else:
        cp = doc[max(0, int(opt.get("cover_page") or 1) - 1)]
        clip = cp.rect
        if detected_stamp:  # keep the buyer stamp off the cover
            stamp_lines = [l for l in cp.get_text("dict")["blocks"] if l.get("type") == 0]
            ys = [b["bbox"][3] for b in stamp_lines if any(s["size"] < 5 for ln in b["lines"] for s in ln["spans"])]
            if ys and max(ys) < cp.rect.height * 0.1:
                clip = pymupdf.Rect(cp.rect.x0, max(ys) + 2, cp.rect.x1, cp.rect.y1)
        zoom = 2560 / clip.height
        pix = cp.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, alpha=False)
        data, mt, cname = pix.tobytes("jpg", jpg_quality=88), "image/jpeg", "cover.jpg"
    images.append(("cover-image", f"images/{cname}", data, mt, "cover-image"))
    files.append(dict(id="cover", href="text/cover.xhtml", toc=None, xml=xhtml(
        lab["cover"], f'<section class="cover" epub:type="cover"><img role="doc-cover" src="../images/{cname}" '
                 f'alt="Cover: {esc_attr(meta["title"])}"/></section>', lang)))

    sections = config["sections"]
    has_titlepage = any(s["type"] == "titlepage" for s in sections)
    if not has_titlepage:
        sections = [{"type": "titlepage", "pages": None, "title": meta["title"], "matter": "front"}] + sections

    first_body_href = None
    n_sec = 0
    for s in sections:
        st = s["type"]
        a, b = (s["pages"] or [0, 0])
        if st == "toc" or s.get("skip"):
            # regenerated below; keep the page markers in order
            marks = "".join(pagebreak_html(pg.label) for pg in pages[a - 1:b] if pg.label) if a else ""
            files.append(dict(id="contents", href="text/contents.xhtml", toc=None, xml=None, marks=marks))
            continue
        n_sec += 1
        sid = f"s{n_sec:03d}"
        href = f"text/{sid}.xhtml"
        if st == "titlepage":
            marks = "".join(pagebreak_html(pg.label) for pg in pages[a - 1:b] if pg.label) if a else ""
            arts = ""
            if a:
                for pg in pages[a - 1:b]:
                    for r in layout.art_regions(pg):
                        fb = type("F", (), {"page": pg.n, "rect": r})
                        arts += figure_src(fb)
            body = (f'<section class="title-page" epub:type="titlepage">{marks}<h1>{esc(meta["title"])}</h1>'
                    + (f'<p class="subtitle">{esc(meta["subtitle"])}</p>' if meta.get("subtitle") else "")
                    + (f'<p class="author">{esc(", ".join(meta["authors"]))}</p>' if meta.get("authors") else "")
                    + arts
                    + (f'<p class="publisher">{esc(meta["publisher"])}</p>' if meta.get("publisher") else "")
                    + "</section>")
            x = xhtml(meta["title"], body, lang, "frontmatter")
            files.append(dict(id=sid, href=href, toc=None, xml=x, kind="titlepage"))
            collect(href, x)
            continue
        if st == "copyright":
            paras = []
            for pg in pages[a - 1:b]:
                paras.append(pagebreak_html(pg.label))
                groups, prevl = [], None
                for l in pg.lines:
                    if prevl is None or l.y0 - prevl.y0 > geo["leading"] * 1.15 + 2:
                        groups.append([])
                    groups[-1].append(l)
                    prevl = l
                from .layout import is_forced_break
                for g in groups:
                    runs, prevl = [], None
                    wrap = max(l.width for l in g)
                    for l in g:
                        fb = prevl is not None and is_forced_break(prevl, l, wrap, opt.get("short_line", 0.75))
                        append_line(runs, line_runs(l), dh, forced_break=fb)
                        prevl = l
                    paras.append(f"<p>{render_runs(strip_runs(runs))}</p>")
            stamp_text = stamp if stamp is not None else (detected_stamp if opt.get("stamp") else None)
            if stamp_text:
                m = re.match(r"^(\S+@\S+)\s+(.+)$", stamp_text)
                lic = lab["licensed"].format(who=m.group(1), when=m.group(2)) if m else lab["licensed_short"].format(who=stamp_text)
                paras.append(f'<p class="licence">{esc(lic)}</p>')
            x = xhtml(lab["copyright"], '<section class="copyright" epub:type="copyright-page">' + "\n".join(paras) + "</section>", lang, "frontmatter")
            files.append(dict(id=sid, href=href, toc=None, xml=x))
            collect(href, x)
            continue
        # chapter-like section
        etype = s.get("epub_type", "chapter")
        role = ROLE_FOR_EPUB_TYPE.get(etype)
        role_attr = f' role="{role}"' if role else ""
        title = s.get("title") or ""
        author = s.get("author")
        blocks = layout.blocks(a, b, opening=True)
        head = f'<header class="section-head"><h1 id="{sid}-t">{esc(title)}</h1>'
        if author:
            head += f'<p class="byline">{esc(byline_text(lab, author))}</p>'
        head += "</header>"
        body_html = blocks_to_html(blocks, figure_src, sid, opt.get("scene_breaks", "as_printed"), lab)
        x = xhtml(title or "Section", f'<section epub:type="{etype}"{role_attr} aria-labelledby="{sid}-t">'
                  + head + "\n" + body_html + "\n</section>", lang, MATTER.get(s.get("matter", "body")),
                  body_class=("spaced" if opt.get("paragraph_style") == "spaced" else None))
        files.append(dict(id=sid, href=href, toc=title, author=author, xml=x))
        collect(href, x)
        if s.get("matter", "body") == "body" and first_body_href is None:
            first_body_href = href
        pdf_w = _page_text_words(pages, a, b)
        epub_w = _html_words(x)
        report["sections"].append({"title": title, "pages": [a, b], "pdf_words": pdf_w, "epub_words": epub_w,
                                   "pdf_letters": _page_letters(pages, a, b),
                                   "epub_letters": _letters(_html_text(x)) - _letters(title) * 0})

    # ---- contents page
    if not any(f.get("toc") for f in files):
        # no chapters found: the reading system still needs one table-of-contents entry
        first = next((f for f in files if f["id"] not in ("cover",)), None)
        if first is not None:
            first["toc"] = meta["title"]
    lis = []
    for f in files:
        if f.get("toc"):
            au = f'<span class="author">{esc(f["author"])}</span>' if f.get("author") else ""
            lis.append(f'<li><a href="{os.path.basename(f["href"])}">{esc(f["toc"])}</a>{au}</li>')
    contents = [f for f in files if f["id"] == "contents"]
    ctoc = ('<nav epub:type="toc" role="doc-toc" id="contents-page"><h1>' + esc(lab["contents"]) + '</h1>'
            '<ol class="contents">' + "".join(lis) + "</ol></nav>")
    if contents:
        for c in contents:
            c["xml"] = xhtml(lab["contents"], c.get("marks", "") + ctoc, lang, "frontmatter")
        # keep only the first contents file
        seen = False
        new = []
        for f in files:
            if f["id"] == "contents":
                if seen:
                    continue
                seen = True
            new.append(f)
        files = new
    else:
        idx = next((i for i, f in enumerate(files) if f.get("kind") == "titlepage"), 0) + 1
        files.insert(idx, dict(id="contents", href="text/contents.xhtml", toc=None,
                               xml=xhtml(lab["contents"], ctoc, lang, "frontmatter")))
    # rebuild page list in spine order
    pagelist, used_labels = [], set()
    for f in files:
        collect(f["href"], f["xml"])
    if lab["page"] != "Page":
        for f in files:
            f["xml"] = re.sub(r'aria-label="Page ([^"]*)"', lambda m: 'aria-label="' + esc_attr(page_label(lab, m.group(1))) + '"', f["xml"])
    first_body_href = first_body_href or next((f["href"] for f in files if f.get("toc")), "text/contents.xhtml")

    # ---- nav / ncx / opf
    book_id = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, "aldleaf:" + meta["title"] + "|" + ",".join(meta.get("authors") or [])))
    nav_toc = "".join(
        f'<li><a href="{f["href"]}">{esc(f["toc"])}{(", " + esc(byline_text(lab, f['author']))) if f.get("author") else ""}</a></li>'
        for f in files if f.get("toc"))
    nav_pl = "".join(f'<li><a href="{h}">{esc(l)}</a></li>' for l, h in pagelist)
    titlepage_href = next((f["href"] for f in files if f.get("kind") == "titlepage"), None)
    landmarks = ['<li><a epub:type="cover" href="text/cover.xhtml">' + esc(lab["cover"]) + '</a></li>']
    if titlepage_href:
        landmarks.append(f'<li><a epub:type="titlepage" href="{titlepage_href}">{esc(lab["titlepage"])}</a></li>')
    landmarks.append('<li><a epub:type="toc" href="text/contents.xhtml">' + esc(lab["contents"]) + '</a></li>')
    landmarks.append(f'<li><a epub:type="bodymatter" href="{first_body_href}">{esc(lab["start"])}</a></li>')
    nav = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{lang}" xml:lang="{lang}">
<head><meta charset="UTF-8"/><title>Navigation</title></head>
<body>
<nav epub:type="toc" role="doc-toc" id="toc"><h1>{esc(lab["contents"])}</h1><ol>{nav_toc}</ol></nav>
<nav epub:type="landmarks" id="landmarks" hidden=""><h2>Landmarks</h2><ol>{"".join(landmarks)}</ol></nav>
{f'<nav epub:type="page-list" role="doc-pagelist" id="page-list" hidden=""><h2>Pages</h2><ol>{nav_pl}</ol></nav>' if pagelist else ""}
</body>
</html>
"""
    nps, n = [], 0
    for f in files:
        if f.get("toc"):
            n += 1
            lbl = f["toc"] + ((", " + byline_text(lab, f['author'])) if f.get("author") else "")
            nps.append(f'<navPoint id="np{n}" playOrder="{n}"><navLabel><text>{esc(lbl)}</text></navLabel><content src="{f["href"]}"/></navPoint>')
    pts = "".join(
        f'<pageTarget id="pt{k}" type="{"normal" if l.isdigit() else "front"}" value="{k + 1}" playOrder="{n + k + 1}">'
        f'<navLabel><text>{esc(l)}</text></navLabel><content src="{h}"/></pageTarget>' for k, (l, h) in enumerate(pagelist))
    ncx = f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" xml:lang="{lang}">
<head><meta name="dtb:uid" content="{book_id}"/><meta name="dtb:depth" content="1"/>
<meta name="dtb:totalPageCount" content="{len(pagelist)}"/><meta name="dtb:maxPageNumber" content="0"/></head>
<docTitle><text>{esc(meta["title"])}</text></docTitle>
<navMap>{"".join(nps)}</navMap>
{f'<pageList><navLabel><text>Pages</text></navLabel>{pts}</pageList>' if pagelist else ""}
</ncx>
"""
    # fonts
    font_files, font_items = {}, []
    for role, spec in (opt.get("fonts") or {}).items():
        faces = []
        for (style_name, w, sty) in (("regular", "normal", "normal"), ("italic", "normal", "italic"),
                                     ("bold", "bold", "normal"), ("bolditalic", "bold", "italic")):
            pth = spec.get(style_name) if isinstance(spec, dict) else None
            if pth and os.path.exists(pth):
                fn = os.path.basename(pth)
                faces.append((fn, w, sty))
                font_items.append((fn, open(pth, "rb").read()))
        if faces:
            font_files[role] = {"family": spec.get("family") or f"Book{role.title()}", "faces": faces}
    css = build_css(font_files)

    modified = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    authors = meta.get("authors") or []
    contributors = []
    for f in files:
        if f.get("author") and f["author"] not in authors and f["author"] not in contributors:
            contributors.append(f["author"])
    creators = "".join(
        f'<dc:creator id="cre{k}">{esc(a)}</dc:creator><meta refines="#cre{k}" property="role" scheme="marc:relators">aut</meta>'
        for k, a in enumerate(authors))
    contribs = "".join(
        f'<dc:contributor id="con{k}">{esc(a)}</dc:contributor><meta refines="#con{k}" property="role" scheme="marc:relators">aut</meta>'
        for k, a in enumerate(contributors))
    if not authors and meta.get("publisher"):
        creators = f'<dc:creator id="cre0">{esc(meta["publisher"])}</dc:creator><meta refines="#cre0" property="role" scheme="marc:relators">edt</meta>'
    subjects = "".join(f"<dc:subject>{esc(s)}</dc:subject>" for s in meta.get("subjects") or [])
    isbn = re.sub(r"[^0-9Xx]", "", meta.get("isbn") or "")
    src = ""
    if pagelist:
        src_val = f"urn:isbn:{isbn}" if isbn else f"{esc(meta['title'])}, PDF edition (page numbers follow this edition)"
        src = f'<dc:source id="src">{src_val}</dc:source><meta refines="#src" property="source-of">pagination</meta>'
    manifest = ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
                '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
                '<item id="css" href="css/book.css" media-type="text/css"/>']
    for f in files:
        props = ' properties="svg"' if "<svg" in (f["xml"] or "") else ""
        manifest.append(f'<item id="{f["id"]}" href="{f["href"]}" media-type="application/xhtml+xml"{props}/>')
    for (i, h, _b, mt, props) in images:
        manifest.append(f'<item id="{i}" href="{h}" media-type="{mt}"' + (f' properties="{props}"' if props else "") + "/>")
    for k, (fn, _d) in enumerate(font_items):
        mt = "font/otf" if fn.lower().endswith(".otf") else "font/ttf"
        manifest.append(f'<item id="font{k}" href="fonts/{fn}" media-type="{mt}"/>')
    spine = "".join(f'<itemref idref="{f["id"]}"/>' for f in files)
    a11y = "".join(f'<meta property="schema:{k}">{v}</meta>' for k, v in [
        ("accessMode", "textual"), ("accessMode", "visual"), ("accessModeSufficient", "textual"),
        ("accessibilityFeature", "tableOfContents"), ("accessibilityFeature", "readingOrder"),
        ("accessibilityFeature", "structuralNavigation"), ("accessibilityFeature", "alternativeText")]
        + ([("accessibilityFeature", "pageBreakMarkers"), ("accessibilityFeature", "pageNavigation")] if pagelist else [])
        + [("accessibilityHazard", "none"),
           ("accessibilitySummary", "Reflowable text with structured headings and a navigable table of contents. "
                                    "Special layouts such as chats, emails and on-screen text are marked up as labelled text.")])
    opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="{lang}" prefix="ibooks: http://vocabulary.itunes.apple.com/rdf/ibooks/vocabulary-extensions-1.0/">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="bookid">{book_id}</dc:identifier>
<dc:title id="title">{esc(meta["title"])}</dc:title>
<meta refines="#title" property="title-type">main</meta>
{creators}{contribs}
{f"<dc:publisher>{esc(meta['publisher'])}</dc:publisher>" if meta.get("publisher") else ""}
{f"<dc:date>{esc(str(meta['date']))}</dc:date>" if meta.get("date") else ""}
<dc:language>{esc(lang)}</dc:language>
{subjects}
{f"<dc:description>{esc(meta['description'])}</dc:description>" if meta.get("description") else ""}
{src}
<meta property="dcterms:modified">{modified}</meta>
{'<meta property="ibooks:specified-fonts">true</meta>' if font_items else ""}
{a11y}
<meta name="cover" content="cover-image"/>
<meta name="generator" content="Aldleaf {__version__}"/>
</metadata>
<manifest>
{chr(10).join(manifest)}
</manifest>
<spine toc="ncx">{spine}</spine>
<guide><reference type="cover" title="{esc_attr(lab["cover"])}" href="text/cover.xhtml"/><reference type="toc" title="{esc_attr(lab["contents"])}" href="text/contents.xhtml"/></guide>
</package>
"""
    container = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with zipfile.ZipFile(out_path, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)

        def w(name, data):
            z.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
        w("META-INF/container.xml", container)
        if font_items:
            w("META-INF/com.apple.ibooks.display-options.xml",
              '<?xml version="1.0" encoding="UTF-8"?>\n<display_options><platform name="*"><option name="specified-fonts">true</option></platform></display_options>\n')
        w("OEBPS/content.opf", opf)
        w("OEBPS/nav.xhtml", nav)
        w("OEBPS/toc.ncx", ncx)
        w("OEBPS/css/book.css", css)
        for f in files:
            w(f"OEBPS/{f['href']}", f["xml"])
        for (_i, h, data, _mt, _p) in images:
            z.writestr(f"OEBPS/{h}", data, compress_type=zipfile.ZIP_STORED)
        for fn, data in font_items:
            w(f"OEBPS/fonts/{fn}", data)

    numbered = [pg.label for pg in pages if pg.label]
    report.update({
        "toc_entries": sum(1 for f in files if f.get("toc")),
        "page_markers": len(pagelist),
        "numbered_pages": len(numbered),
        "missing_markers": [l for l in numbered if l not in used_labels],
        "inferred_labels": sum(1 for pg in pages if pg.label_inferred),
        "images": len(images),
        "fonts": len(font_items),
        "stats": stats,
        "stamp_detected": bool(detected_stamp),
        "language": lang,
    })
    raw = "\n".join(pg.raw_text for pg in pages)
    bad, examples = text_layer_issues(raw)
    from .i18n import _DOUBLE_SIGN
    report["text_layer"] = {"damaged_words": bad, "examples": examples, "repaired": len(_DOUBLE_SIGN.findall(raw))}
    return out_path, report
