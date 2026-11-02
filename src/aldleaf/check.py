"""Quality checks: EPUBCheck, completeness against the PDF, structural lints,
and an optional side-by-side visual report."""
import html as _html
import io
import os
import re
import shutil
import subprocess
import urllib.request
import zipfile

from .text import words

EPUBCHECK_VERSION = "5.3.0"
EPUBCHECK_URL = f"https://github.com/w3c/epubcheck/releases/download/v{EPUBCHECK_VERSION}/epubcheck-{EPUBCHECK_VERSION}.zip"
CACHE = os.path.join(os.path.expanduser("~"), ".cache", "aldleaf")


def find_epubcheck():
    jar = os.environ.get("EPUBCHECK_JAR")
    if jar and os.path.exists(jar):
        return jar
    cand = os.path.join(CACHE, f"epubcheck-{EPUBCHECK_VERSION}", "epubcheck.jar")
    return cand if os.path.exists(cand) else None


def fetch_epubcheck():
    os.makedirs(CACHE, exist_ok=True)
    data = urllib.request.urlopen(EPUBCHECK_URL, timeout=120).read()
    zipfile.ZipFile(io.BytesIO(data)).extractall(CACHE)
    return find_epubcheck()


def run_epubcheck(epub_path):
    jar = find_epubcheck()
    if not jar or not shutil.which("java"):
        return None, "EPUBCheck not available (needs Java; run `aldleaf fetch-epubcheck`)."
    p = subprocess.run(["java", "-jar", jar, epub_path], capture_output=True, text=True)
    out = p.stdout + p.stderr
    msgs = [l for l in out.splitlines() if re.match(r"^(ERROR|WARNING|FATAL)", l)]
    summary = next((l for l in out.splitlines() if l.startswith("Messages:")), "")
    ok = p.returncode == 0 and not any(m.startswith(("ERROR", "FATAL")) for m in msgs)
    return ok, (summary + ("\n" + "\n".join(msgs[:40]) if msgs else ""))


def lint_epub(epub_path):
    """Structural lints that catch typical PDF-conversion mistakes."""
    z = zipfile.ZipFile(epub_path)
    issues = []
    for name in z.namelist():
        if not name.endswith(".xhtml") or name.endswith("nav.xhtml"):
            continue
        x = z.read(name).decode("utf-8")
        body = x[x.find("<body"):]
        paras = re.findall(r"<p[^>]*>(.*?)</p>", body, re.S)
        for p in paras:
            t = _html.unescape(re.sub(r"<[^>]+>", "", p))
            n = len(words(t))
            if n > 900:
                issues.append(f"{name}: very long paragraph ({n} words), possible missed paragraph breaks: {t[:50]!r}")
        # runs of very short paragraphs often mean unjoined wrapped lines
        short = 0
        for p in paras:
            t = _html.unescape(re.sub(r"<[^>]+>", "", p)).strip()
            if t and len(t) < 45 and not t.endswith((".", "!", "?", "”", '"', ":", "…")) and t[:1].islower():
                short += 1
        if short >= 5:
            issues.append(f"{name}: {short} short paragraphs starting lower-case, possible unjoined line wraps")
        if re.search(r"\w-\s+[a-z]{2,}", re.sub(r"<[^>]+>", "", body)) and False:
            pass
        lone_digits = re.findall(r"<p[^>]*>\s*(\d{1,4}|[ivxlc]{1,6})\s*</p>", body)
        if lone_digits:
            issues.append(f"{name}: {len(lone_digits)} paragraph(s) that are just a number, possible leftover page numbers")
    return issues


FEATURES = {
    "paragraphs": r"<p[\s>]",
    "scene breaks": r'<hr[\s/>]|class="scene-break"',
    "chat groups": r'<div class="chat[ "]',
    "chat bubbles": r'class="bubble"',
    "emails": r'<div class="email"',
    "screen text": r'<samp[\s>]',
    "images": r"<img[\s]|<svg[\s]",
    "line breaks": r"<br\s*/?>",
    "italic runs": r"<i[\s>]|<em[\s>]",
    "page markers": r'epub:type="pagebreak"',
}


def epub_profile(epub_path):
    """Structural fingerprint of an EPUB: section titles, words and feature counts
    per section, TOC and page-list sizes. Contains no running text."""
    import posixpath
    z = zipfile.ZipFile(epub_path)
    names = z.namelist()
    opf_name = next(n for n in names if n.endswith(".opf"))
    opf = z.read(opf_name).decode("utf-8")
    base = posixpath.dirname(opf_name)
    items = dict(re.findall(r'<item[^>]*id="([^"]+)"[^>]*href="([^"]+)"', opf))
    items.update({i: h for h, i in re.findall(r'<item[^>]*href="([^"]+)"[^>]*id="([^"]+)"', opf)})
    spine = re.findall(r'<itemref[^>]*idref="([^"]+)"', opf)
    sections = []
    totals = {k: 0 for k in FEATURES}
    for idref in spine:
        href = items.get(idref)
        if not href:
            continue
        path = posixpath.normpath(posixpath.join(base, href))
        if path not in names:
            continue
        x = z.read(path).decode("utf-8", "replace")
        body = x[x.find("<body"):]
        h = re.search(r"<h1[^>]*>(.*?)</h1>", body, re.S)
        title = _html.unescape(re.sub(r"<[^>]+>", "", h.group(1))).strip() if h else ""
        feats = {k: len(re.findall(v, body)) for k, v in FEATURES.items()}
        for k, v in feats.items():
            totals[k] += v
        sections.append({"title": title, "words": len(words(_html.unescape(re.sub(r"<[^>]+>", " ", body)))), **feats})
    nav = next((z.read(n).decode("utf-8") for n in names if re.search(r"nav\.x?html$", n)), "")
    pl = re.search(r'epub:type="page-list".*?</nav>', nav, re.S)
    toc = re.search(r'epub:type="toc".*?</nav>', nav, re.S)
    return {"sections": sections, "totals": totals,
            "page_list": len(re.findall(r"<a ", pl.group(0))) if pl else 0,
            "toc": len(re.findall(r"<a ", toc.group(0))) if toc else 0}


def _norm_title(t):
    return re.sub(r"[^a-z0-9]", "", t.lower())


def compare_profiles(ours, ref, tolerance=0.01):
    """Compare our EPUB with a reference EPUB (e.g. a hand-made edition).
    Returns report lines; '!!' marks differences worth a look."""
    out = [f"Reference comparison: TOC {ours['toc']} vs {ref['toc']}, "
           f"page list {ours['page_list']} vs {ref['page_list']}"]
    refs = {_norm_title(s["title"]): s for s in ref["sections"] if s["title"]}
    matched = 0
    for s in ours["sections"]:
        r = refs.get(_norm_title(s["title"])) if s["title"] else None
        if not r:
            continue
        matched += 1
        diffs = []
        if abs(s["words"] - r["words"]) > max(5, r["words"] * tolerance):
            diffs.append(f"words {s['words']} vs {r['words']}")
        for k in FEATURES:
            if k in ("italic runs", "paragraphs", "page markers", "line breaks", "images"):
                continue
            if s[k] != r[k]:
                diffs.append(f"{k} {s[k]} vs {r[k]}")
        if abs(s["paragraphs"] - r["paragraphs"]) > max(3, r["paragraphs"] * 0.03):
            diffs.append(f"paragraphs {s['paragraphs']} vs {r['paragraphs']}")
        out.append(("  !! " if diffs else "  OK ") + f"{s['title'][:40]}" + (": " + "; ".join(diffs) if diffs else ""))
    out.append(f"  matched {matched} of {len([s for s in ref['sections'] if s['title']])} reference sections by title")
    t1, t2 = ours["totals"], ref["totals"]
    out.append("  totals (ours vs reference): " + ", ".join(f"{k} {t1[k]}/{t2[k]}" for k in FEATURES))
    return out


def visual_report(epub_path, pdf_path, config, out_dir, max_sections=12):
    """Side-by-side HTML: the PDF's first page of each section next to the EPUB
    page as rendered by Chromium. Needs `pip install playwright` + a Chromium."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, "Visual report needs Playwright: pip install playwright && playwright install chromium"
    from .model import pymupdf
    os.makedirs(out_dir, exist_ok=True)
    tmp = os.path.join(out_dir, "_epub")
    shutil.rmtree(tmp, ignore_errors=True)
    zipfile.ZipFile(epub_path).extractall(tmp)
    doc = pymupdf.open(pdf_path)
    texts = sorted(f for f in os.listdir(os.path.join(tmp, "OEBPS", "text")) if f.startswith("s"))
    secs = [s for s in config["sections"] if s["type"] not in ("toc",)]
    rows = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 420, "height": 680})
        for i, (f, s) in enumerate(zip(texts, secs)):
            if i >= max_sections:
                break
            page.goto("file://" + os.path.abspath(os.path.join(tmp, "OEBPS", "text", f)))
            page.add_style_tag(content="body{margin:24px}")
            shot = os.path.join(out_dir, f"epub_{i:02d}.png")
            page.screenshot(path=shot)
            pn = (s.get("pages") or [1])[0]
            pdf_png = os.path.join(out_dir, f"pdf_{i:02d}.png")
            n = min(pn + (1 if s["type"] == "chapter" else 0), doc.page_count)
            doc[n - 1].get_pixmap(dpi=90).save(pdf_png)
            rows.append(f'<tr><td><b>{_html.escape(s.get("title", ""))}</b><br/>PDF page {n}<br/>'
                        f'<img src="{os.path.basename(pdf_png)}" width="400"/></td>'
                        f'<td>EPUB<br/><img src="{os.path.basename(shot)}" width="400"/></td></tr>')
        b.close()
    rep = os.path.join(out_dir, "visual_report.html")
    with open(rep, "w", encoding="utf-8") as fh:
        fh.write("<!doctype html><meta charset='utf-8'><title>Aldleaf visual check</title>"
                 "<table border=1 cellpadding=6>" + "".join(rows) + "</table>")
    return rep, None


def check(epub_path, build_report=None, pdf_path=None, config=None, visual_dir=None, reference=None):
    """Run all checks. Returns (passed: bool, text report)."""
    lines, problems = [], 0
    ok, msg = run_epubcheck(epub_path)
    if ok is None:
        lines.append("EPUBCheck: skipped. " + msg)
    else:
        lines.append(f"EPUBCheck: {'passed' if ok else 'FAILED'}  {msg}")
        problems += 0 if ok else 1
    if build_report:
        lines.append("Text completeness (PDF vs EPUB, every letter accounted for):")
        for s in build_report.get("sections", []):
            # compare letters (not words): drop caps and joined hyphens change word counts only
            pl, el = s.get("pdf_letters", 0), s.get("epub_letters", 0)
            ok_s = abs(el - pl) <= max(3, pl * 0.002)
            problems += 0 if ok_s else 1
            lines.append(f"  {'OK ' if ok_s else '!! '}p{s['pages'][0]}-{s['pages'][1]} {s['title'][:40]}: "
                         f"PDF {s['pdf_words']} words / {pl} letters, EPUB {s['epub_words']} words / {el} letters")
        miss = build_report.get("missing_markers") or []
        lines.append(f"Print page markers: {build_report.get('page_markers', 0)} of "
                     f"{build_report.get('numbered_pages', 0)} numbered pages "
                     f"({build_report.get('inferred_labels', 0)} inferred for unnumbered pages)")
        if miss:
            problems += 1
            lines.append(f"  !! missing: {', '.join(miss[:30])}")
        st = build_report.get("stats", {})
        lines.append(f"Kept manual line breaks: {st.get('forced_breaks', 0)}; blank-space scene breaks: "
                     f"{st.get('space_breaks', 0)}; joined stray paragraph returns: {st.get('joined_returns', 0)}; "
                     f"figures: {st.get('figures', 0)}")
    if build_report and build_report.get("text_layer"):
        tl = build_report["text_layer"]
        if tl.get("damaged_words"):
            problems += 1
            lines.append(f"Text layer: !! {tl['damaged_words']} word(s) look damaged in the PDF itself "
                         "(what you copy differs from what you see). Re-export the PDF from your writing or layout "
                         "program with embedded fonts, then convert again. Examples: " + "; ".join(tl.get("examples", [])[:5]))
        else:
            lines.append("Text layer: OK")
        if tl.get("repaired"):
            lines.append(f"  repaired {tl['repaired']} doubled vowel sign(s) left by the PDF's ligatures")
    issues = lint_epub(epub_path)
    lines.append(f"Lints: {len(issues)} warning(s)")
    lines.extend("  - " + i for i in issues[:40])
    if reference:
        lines.extend(compare_profiles(epub_profile(epub_path), epub_profile(reference)))
    if visual_dir and pdf_path and config:
        rep, err = visual_report(epub_path, pdf_path, config, visual_dir)
        lines.append(f"Visual report: {rep}" if rep else f"Visual report: skipped. {err}")
    lines.append("Result: " + ("all checks passed" if problems == 0 else f"{problems} problem(s)"))
    return problems == 0, "\n".join(lines)
