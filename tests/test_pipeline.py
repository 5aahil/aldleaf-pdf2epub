import os
import re
import shutil
import zipfile

import pytest

from make_sample import make
from pdf2epub.analyze import analyze
from pdf2epub.build import build
from pdf2epub.check import check, find_epubcheck
from pdf2epub.model import load
from pdf2epub.text import Dehyphenator, append_line, int_to_roman, roman_to_int, shift_label


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    d = tmp_path_factory.mktemp("book")
    pdf = str(d / "sample.pdf")
    make(pdf)
    doc, pages, stamp = load(pdf)
    cfg = analyze(doc, pages, stamp)
    out = str(d / "sample.epub")
    path, report = build(pdf, cfg, out)
    z = zipfile.ZipFile(path)
    texts = {n: z.read(n).decode("utf-8") for n in z.namelist() if n.endswith((".xhtml", ".opf", ".ncx"))}
    return dict(pdf=pdf, cfg=cfg, epub=path, report=report, texts=texts, stamp=stamp)


def chapter(sample, title):
    for n, x in sample["texts"].items():
        if f">{title}</h1>" in x:
            return x
    raise AssertionError(f"chapter {title!r} not found")


def test_roman_helpers():
    assert roman_to_int("xlii") == 42 and int_to_roman(42) == "xlii"
    assert shift_label("5", -2) == "3" and shift_label("ix", -2) == "vii" and shift_label("1", -1) is None


def test_dehyphenation_keeps_real_compounds():
    dh = Dehyphenator(auto_hyphenated=False)
    runs = [("in-", frozenset())]
    append_line(runs, [("depth", frozenset())], dh)
    assert "".join(t for t, _ in runs) == "in-depth"


def test_analysis_finds_structure(sample):
    cfg = sample["cfg"]
    types = [s["type"] for s in cfg["sections"]]
    assert types == ["titlepage", "copyright", "toc", "chapter", "chapter"]
    chapters = [s for s in cfg["sections"] if s["type"] == "chapter"]
    assert [c["title"] for c in chapters] == ["The Keeper", "Signals"]
    assert [c.get("author") for c in chapters] == ["Ada Example", "Ben Example"]
    roles = {s["style"]: s["role"] for s in cfg["styles"]}
    assert roles["Times-Roman@10.5"] == "body"
    assert roles["Courier@9"] == "screen"
    assert roles["Helvetica@10"] == "chat"
    assert roles["Helvetica@8"] == "chat_label"
    assert cfg["options"]["auto_hyphenated"] is False
    assert cfg["options"]["stamp_detected"] is True
    assert cfg["options"]["stamp"] is False          # opt-in only


def test_no_running_heads_or_folios_in_text(sample):
    x = chapter(sample, "The Keeper")
    body = re.sub(r"<[^>]+>", " ", x[x.index("</header>"):])
    assert "The Quiet Harbour" not in body


def test_paragraph_continues_across_page(sample):
    x = chapter(sample, "The Keeper")
    # every paragraph ends with sentence punctuation (no paragraph split at a page break)
    for p in re.findall(r"<p(?: class=\"(?:noindent|center)\")?>(.*?)</p>", x[x.index("</header>"):], re.S):
        t = re.sub(r"<[^>]+>", "", p).strip()
        if t:
            assert t.endswith((".", "?", "!", ":")), t[-40:]


def test_special_blocks(sample):
    k = chapter(sample, "The Keeper")
    s = chapter(sample, "Signals")
    assert k.count('class="scene-break"') == 1                  # the author's printed marker
    assert k.count('<hr class="scene space"/>') == 1            # the author's blank-space break
    assert '<p class="screen"><samp>' in k
    assert "<i>Nobody answered.</i>" in k
    assert '<div class="cw" role="doc-notice"' in k
    assert '<div class="chat them"><p class="sender">Mara:</p>' in s
    assert '<div class="chat me"><p class="sender">Me:</p>' in s
    assert "<b>From:</b>" in s and "<b>Subject:</b>" in s
    assert "Sam Example<br/>Harbour Office" in s                 # signature keeps its break
    assert "confirm that the lamp" in s                         # wrapped email line joined


def test_page_list_and_inferred_numbers(sample):
    r = sample["report"]
    assert r["missing_markers"] == []
    assert r["inferred_labels"] >= 2                             # chapter openers get numbers
    nav = sample["texts"]["OEBPS/nav.xhtml"]
    assert 'epub:type="page-list"' in nav


def test_stamp_never_copied_by_default(sample):
    for x in sample["texts"].values():
        assert "buyer@example.com" not in x


def test_stamp_opt_in(sample, tmp_path):
    cfg = dict(sample["cfg"])
    cfg["options"] = dict(cfg["options"], stamp=True)
    out, _ = build(sample["pdf"], cfg, str(tmp_path / "stamped.epub"))
    z = zipfile.ZipFile(out)
    assert any("Licensed to buyer@example.com" in z.read(n).decode() for n in z.namelist() if n.endswith(".xhtml"))


def test_completeness(sample):
    for s in sample["report"]["sections"]:
        assert abs(s["epub_words"] - s["pdf_words"]) <= 2, s


@pytest.mark.skipif(not (find_epubcheck() and shutil.which("java")), reason="EPUBCheck/Java not installed")
def test_epubcheck_clean(sample):
    ok, text = check(sample["epub"], sample["report"])
    assert ok, text


def test_encrypted_pdf_refused(tmp_path):
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf
    d = pymupdf.open()
    d.new_page().insert_text((72, 72), "locked")
    p = str(tmp_path / "locked.pdf")
    d.save(p, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="x", owner_pw="y")
    with pytest.raises(PermissionError):
        load(p)


def test_adaptive_svg_art(sample):
    k = chapter(sample, "The Keeper")
    s = chapter(sample, "Signals")
    assert '<svg xmlns="http://www.w3.org/2000/svg" class="art-svg"' in k      # grey stamp -> adaptive SVG
    assert 'fill="currentColor" mask="url(#' in k                               # painted in the text colour
    assert 'class="kf8-fallback"' in k                                          # Kindle PNG fallback
    assert '<div class="figure"><img' in s                                      # colour ornament stays an image
    opf = sample["texts"]["OEBPS/content.opf"]
    assert 'properties="svg"' in opf
