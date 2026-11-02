"""Blocks -> XHTML, plus the stylesheet."""
import re

from .i18n import EMAIL_FIELD_WORDS
from .text import esc, render_runs, runs_text, strip_runs

XHTML_HEAD = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{lang}" xml:lang="{lang}">
<head>
<meta charset="UTF-8"/>
<title>{title}</title>
<link rel="stylesheet" type="text/css" href="../css/book.css"/>
</head>
<body{body_attr}>
"""


def xhtml(title, body, lang="en", epub_type=None, body_class=None):
    attr = f' epub:type="{epub_type}"' if epub_type else ""
    if body_class:
        attr += f' class="{body_class}"'
    return XHTML_HEAD.format(lang=lang, title=esc(title), body_attr=attr) + body + "\n</body>\n</html>\n"


def _strip_bullet(runs, marker):
    """Remove the printed bullet or number, even when the PDF stores it in pieces
    ("1" and ". ")."""
    runs = strip_runs(runs)
    text = "".join(t for t, st in runs if not isinstance(st, tuple))
    m = re.match(r"^\s*" + re.escape(marker) + r"\s*", text)
    if not m:
        return runs
    cut = m.end()
    for j, (t, st) in enumerate(runs):
        if cut <= 0:
            break
        if isinstance(st, tuple):
            continue
        take = min(cut, len(t))
        runs[j] = (t[take:], st)
        cut -= take
    return runs


def blocks_to_html(blocks, figure_src, sid="s", scene_style="as_printed", lab=None):
    """figure_src(block) -> (href, alt, width%) for figure blocks.
    Footnotes are collected and placed at the end as pop-up notes."""
    from .i18n import labels
    lab = lab or labels("en")
    out, prev = [], None
    notes = [b for b in blocks if b.kind == "fnote"]
    blocks = [b for b in blocks if b.kind != "fnote"]
    open_list = None
    for b in blocks:
        k = b.kind
        if open_list and k != "li":
            out.append(f"</{open_list}>")
            open_list = None
        if k == "li":
            tag = "ol" if b.ordered else "ul"
            if open_list != tag:
                if open_list:
                    out.append(f"</{open_list}>")
                out.append(f'<{tag} class="list">')
                open_list = tag
            body = _strip_bullet(b.runs, b.marker)
            out.append(f"<li>{render_runs(body)}</li>")
            prev = b
            continue
        if k == "p":
            cls = []
            if getattr(b, "verse", False):
                cls.append("verse")
            if b.center:
                cls.append("center")
            elif not b.indent or prev is None or prev.kind in ("figure", "h2"):
                cls.append("noindent")
            c = f' class="{" ".join(cls)}"' if cls else ""
            out.append(f"<p{c}>{render_runs(strip_runs(b.runs))}</p>")
        elif k == "h2":
            plain = [(t, st - {"b"}) if not isinstance(st, tuple) else (t, st) for t, st in strip_runs(b.runs)]
            out.append(f'<h2 class="sub">{render_runs(plain)}</h2>')
        elif k == "hr":
            # scene breaks follow the author: their own printed marker, or blank space
            glyph = getattr(b, "glyph", None)
            if scene_style == "ornament" or (glyph is None and not getattr(b, "space", False)):
                out.append('<hr class="scene"/>')
            elif glyph:
                out.append(f'<div class="scene-break" role="separator" aria-label="{lab["scene_break"]}">'
                           f'<p aria-hidden="true">{esc(glyph)}</p></div>')
            else:
                out.append('<hr class="scene space"/>')
        elif k == "marker":
            out.append(render_runs(b.runs))
        elif k == "note":
            out.append(f'<p class="note">{render_runs(strip_runs(b.runs))}</p>')
        elif k == "cw":
            out.append(f'<div class="cw" role="doc-notice" aria-label="{lab["warnings"]}">'
                       f'<p class="cw-head">{render_runs(strip_runs(b.head))}</p>'
                       f'<p class="cw-list">{render_runs(strip_runs(b.runs))}</p></div>')
        elif k == "screen":
            c = "screen center" if b.center else "screen"
            out.append(f'<p class="{c}"><samp>{render_runs(strip_runs(b.runs))}</samp></p>')
        elif k == "chat":
            parts = [f'<div class="chat {b.side}">']
            if b.label:
                parts.append(f'<p class="sender">{render_runs(b.label)}</p>')
            for bub in b.bubbles:
                parts.append(f'<p class="bubble">{render_runs(strip_runs(bub))}</p>')
            parts.append("</div>")
            out.append("".join(parts))
        elif k == "email":
            parts = ['<div class="email">']
            if b.header:
                parts.append('<div class="email-head">')
                for h in b.header:
                    r = render_runs(strip_runs(h))
                    r = re.sub(r"^((?:<span[^>]*></span>)*)(" + EMAIL_FIELD_WORDS + r"):", r"\1<b>\2:</b>", r)
                    parts.append(f"<p>{r}</p>")
                parts.append("</div>")
            for p in b.paras:
                if runs_text(p).strip() or any(isinstance(s, tuple) for _, s in p):
                    parts.append(f"<p>{render_runs(strip_runs(p))}</p>")
            parts.append("</div>")
            out.append("".join(parts))
        elif k == "quote":
            out.append('<blockquote class="aside">' + "".join(
                f"<p>{render_runs(strip_runs(p))}</p>" for p in b.paras) + "</blockquote>")
        elif k == "caption":
            out.append(f'<p class="caption">{render_runs(strip_runs(b.runs))}</p>')
        elif k == "figure":
            out.append(figure_src(b))
        prev = b
    if open_list:
        out.append(f"</{open_list}>")
    html = "\n".join(out)
    if notes:
        html = link_notes(html, notes, sid)
    return html


def link_notes(html, notes, sid):
    """Turn superscript note numbers into pop-up note links (Apple Books and Kindle
    both support epub:type noteref/footnote with links in both directions)."""
    asides, used = [], set()
    pos = 0
    out = []
    for i, n in enumerate(notes):
        nid = f"{sid}-fn{i + 1}"
        num = n.num or str(i + 1)
        pat = re.compile(r"<sup>" + re.escape(num) + r"</sup>")
        m = pat.search(html, pos)
        if m:
            out.append(html[pos:m.start()])
            out.append(f'<a epub:type="noteref" role="doc-noteref" id="{nid}-ref" href="#{nid}"><sup>{esc(num)}</sup></a>')
            pos = m.end()
            back = f'<a href="#{nid}-ref" role="doc-backlink">{esc(num)}</a> '
        else:
            back = f"{esc(num)} " if num else ""
        asides.append(f'<aside epub:type="footnote" role="doc-footnote" id="{nid}" class="footnote">'
                      f"<p>{back}{render_runs(strip_runs(n.runs))}</p></aside>")
    out.append(html[pos:])
    return "".join(out) + "\n" + "\n".join(asides)


FONT_FACE = '@font-face {{ font-family: "{fam}"; font-weight: {w}; font-style: {s}; src: url(../fonts/{file}); }}'

CSS_BASE = r"""
body { margin: 0; padding: 0; }
:lang(zh) p, :lang(ja) p, :lang(ko) p { line-break: strict; }
:lang(th) p { line-break: auto; }
p { margin: 0; text-indent: 1.2em; line-height: 1.4; text-align: justify;
    -webkit-hyphens: auto; -epub-hyphens: auto; hyphens: auto; orphans: 2; widows: 2; }
p.noindent { text-indent: 0; }
p.center { text-indent: 0; text-align: center; }
h1, h2 { font-weight: normal; line-height: 1.2; -webkit-hyphens: none; hyphens: none;
    page-break-after: avoid; break-after: avoid; }
h1 { font-size: 1.9em; text-align: left; margin: 3em 0 0.6em 0; }
h2 { font-size: 1.4em; margin: 1.5em 0 0.8em 0; }
h2.sub { text-align: left; font-size: 1.2em; margin: 1.4em 0 0.6em 0; }
body.spaced p { text-indent: 0; margin-bottom: 0.75em; }
body.spaced p.verse { margin-bottom: 1em; }
.byline { font-style: italic; font-size: 1.25em; text-indent: 0; text-align: left; margin: 0 0 1.6em 0; }
p.note { font-style: italic; text-indent: 0; text-align: left; margin: 0 0 1em 0; }
.cw { margin: 1.6em 0 1.4em 0; padding: 0.6em 0.8em; border: 1px solid; border-radius: 0.3em;
    page-break-inside: avoid; break-inside: avoid; }
.cw p { text-indent: 0; text-align: left; }
.cw-list { font-style: italic; }
.section-head { margin-bottom: 1.5em; }
hr.scene { border: 0; border-top: 1px solid; width: 18%; margin: 1.4em auto; height: 0; }
hr.scene.space { border-top: 0; margin: 1.2em auto; }
div.scene-break { margin: 1.2em 0; page-break-inside: avoid; break-inside: avoid; }
div.scene-break p { text-indent: 0; text-align: center; margin: 0; }
samp { font-family: monospace; font-size: 0.86em; }
p.screen { text-indent: 0; text-align: left; margin: 0.8em 0; line-height: 1.45; -webkit-hyphens: none; hyphens: none; }
p.screen.center { text-align: center; }
div.chat { margin: 0.9em 0; page-break-inside: avoid; break-inside: avoid; }
div.chat p { text-indent: 0; text-align: left; -webkit-hyphens: none; hyphens: none; font-family: sans-serif; }
div.chat p.sender { font-size: 0.72em; margin: 0 0 0.25em 0; opacity: 0.75; }
div.chat p.bubble { font-size: 0.88em; line-height: 1.35; border: 1px solid; border-radius: 0.8em;
    padding: 0.45em 0.75em; margin: 0 0 0.4em 0; }
div.chat.them { margin-right: 22%; margin-left: 0; }
div.chat.me { margin-left: 22%; margin-right: 0; }
div.chat.me p.sender { text-align: right; }
div.chat.me p.bubble { border-width: 2px; }
div.email { margin: 1.2em 0; padding: 0.8em 1em; border: 1px solid; }
div.email p { text-indent: 0; text-align: left; margin: 0 0 0.7em 0; }
div.email p:last-child { margin-bottom: 0; }
div.email .email-head { border-bottom: 1px solid; padding-bottom: 0.5em; margin-bottom: 0.8em; }
div.email .email-head p { margin: 0; font-size: 0.92em; -webkit-hyphens: none; hyphens: none; }
blockquote.aside { margin: 1em 5%; }
blockquote.aside p { text-indent: 0; margin: 0 0 0.6em 0; }
p.verse { text-indent: 0; text-align: left; margin: 0 0 1em 0; -webkit-hyphens: none; hyphens: none; }
ul.list, ol.list { margin: 0.6em 0 0.8em 1.4em; padding: 0; }
ul.list li, ol.list li { margin: 0 0 0.3em 0; line-height: 1.4; }
aside.footnote { font-size: 0.85em; margin: 0.6em 0; }
aside.footnote p { text-indent: 0; text-align: left; }
p.caption { text-indent: 0; text-align: center; font-size: 0.85em; margin: 0.3em 0 1em 0; }
div.figure { text-align: center; margin: 1em 0; page-break-inside: avoid; break-inside: avoid; }
div.figure img { max-width: 100%; height: auto; }
div.figure.art { margin-left: auto; margin-right: auto; }
div.figure.art svg { display: block; width: 100%; height: auto; }
img.kf8-fallback { display: none; }
@media amzn-kf8 { div.figure.art svg { display: none; } img.kf8-fallback { display: block; width: 100%; } }
.title-page { text-align: center; }
.title-page h1 { text-align: center; font-size: 2.3em; margin: 2.5em 0 0.3em 0; }
.title-page p { text-align: center; text-indent: 0; }
.title-page .subtitle { font-size: 1.3em; }
.title-page .author { margin-top: 1.5em; font-size: 1.2em; }
.title-page .publisher { margin-top: 2em; font-size: 0.9em; }
.copyright p { text-indent: 0; text-align: left; font-size: 0.85em; margin: 0 0 0.9em 0; -webkit-hyphens: none; hyphens: none; }
.copyright p.licence { margin-top: 2em; }
ol.contents { list-style: none; padding: 0; margin: 0; }
ol.contents li { margin: 0 0 0.7em 0; }
ol.contents .author { display: block; font-size: 0.85em; font-style: italic; }
ol.contents a { text-decoration: none; }
.cover { text-align: center; margin: 0; padding: 0; }
.cover img { height: 100%; max-width: 100%; }
@media amzn-kf8 { .cover img { height: auto; width: 100%; } }
"""

ROLE_SELECTORS = {
    "body": "body",
    "heading": "h1, h2",
    "screen": "samp",
    "chat": "div.chat p",
    "email": "div.email",
}


def build_css(font_files):
    """font_files: {role: {"family": name, "faces": [(file, weight, style)]}}"""
    faces, rules = [], []
    for role, spec in font_files.items():
        fam = spec["family"]
        for file, w, s in spec["faces"]:
            faces.append(FONT_FACE.format(fam=fam, w=w, s=s, file=file))
        sel = ROLE_SELECTORS.get(role)
        if sel:
            generic = {"screen": "monospace", "chat": "sans-serif"}.get(role, "serif")
            rules.append(f'{sel} {{ font-family: "{fam}", {generic}; }}')
    return '@charset "UTF-8";\n' + "\n".join(faces) + "\n" + CSS_BASE.strip() + "\n" + "\n".join(rules) + "\n"
