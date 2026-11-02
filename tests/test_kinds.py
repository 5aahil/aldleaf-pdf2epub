"""The converter adapts to the kind of book; it is not tuned to one title."""
import re
import zipfile

import pytest

import fixtures
from aldleaf.analyze import analyze
from aldleaf.build import build
from aldleaf.model import load


def run(tmp_path, maker):
    pdf = str(tmp_path / f"{maker.__name__}.pdf")
    maker(pdf)
    doc, pages, stamp = load(pdf)
    cfg = analyze(doc, pages, stamp)
    out, report = build(pdf, cfg, str(tmp_path / f"{maker.__name__}.epub"))
    z = zipfile.ZipFile(out)
    body = "\n".join(z.read(n).decode() for n in sorted(z.namelist())
                     if n.startswith("OEBPS/text/s") and n.endswith(".xhtml"))
    return cfg, report, body


def letters_ok(report):
    for s in report["sections"]:
        assert abs(s["epub_letters"] - s["pdf_letters"]) <= max(3, s["pdf_letters"] * 0.002), s


def test_novel(tmp_path):
    cfg, report, body = run(tmp_path, fixtures.novel)
    o = cfg["options"]
    assert o["book_kind"] == "prose"
    assert o["paragraph_style"] == "indent" and o["alignment"] == "justified"
    assert o["auto_hyphenated"] is True                       # layout hyphens get removed
    titles = [s["title"] for s in cfg["sections"] if s["type"] == "chapter"]
    assert titles == ["Chapter 1: Low Tide", "Chapter 2: The Long Night"]
    assert "Everything beneath" in body                       # drop cap glued back to its word
    assert not re.search(r"[a-z]- [a-z]", re.sub(r"<[^>]+>", "", body))   # no stray layout hyphens
    letters_ok(report)


def test_nonfiction(tmp_path):
    cfg, report, body = run(tmp_path, fixtures.nonfiction)
    o = cfg["options"]
    assert o["paragraph_style"] == "spaced" and o["alignment"] == "ragged"
    roles = {s["style"]: s["role"] for s in cfg["styles"]}
    assert roles["Helvetica-Bold@10.5"] == "subheading"
    assert roles["Helvetica@8"] == "footnote"
    assert '<h2 class="sub">Why it matters</h2>' in body
    assert '<ul class="list">' in body and "<li>Watch the pressure.</li>" in body
    assert '<ol class="list">' in body and "<li>Open the logbook.</li>" in body
    assert 'epub:type="noteref"' in body and 'epub:type="footnote"' in body
    letters_ok(report)


def test_poetry(tmp_path):
    cfg, report, body = run(tmp_path, fixtures.poetry)
    assert cfg["options"]["book_kind"] == "poetry"
    assert "lantern lit<br/>for boats" in body                # verse keeps its line breaks
    assert body.count('class="verse') >= 8                  # one paragraph per stanza
    letters_ok(report)
