"""Command line: pdf2epub analyze | build | check | convert | fetch-epubcheck"""
import argparse
import json
import os
import sys

import yaml

from . import __version__
from .analyze import analyze, summarize
from .build import build
from .check import check, fetch_epubcheck
from .model import load

HEADER = """# pdf2epub book config. Review it, fix anything wrong, then run `pdf2epub build`.
# It contains short text samples from your PDF: keep it out of public repositories.
# Roles: body heading subheading note screen chat chat_label email blockquote scene_break caption ignore
# Section types: titlepage copyright toc chapter   (epub_type: chapter foreword preface introduction
#   prologue epilogue afterword acknowledgments dedication epigraph glossary appendix endnotes bibliography index)
"""


def _default_config_path(pdf):
    return os.path.splitext(pdf)[0] + ".pdf2epub.yaml"


def _default_epub_path(pdf):
    return os.path.splitext(pdf)[0] + ".epub"


def cmd_analyze(a):
    doc, pages, stamp = load(a.pdf)
    cfg = analyze(doc, pages, stamp)
    out = a.output or _default_config_path(a.pdf)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(HEADER)
        yaml.safe_dump(cfg, fh, sort_keys=False, allow_unicode=True, width=110)
    print(summarize(cfg))
    print(f"\nWrote {out}. Review it, then: pdf2epub build {a.pdf!r} -c {out!r}")
    return 0


def _load_cfg(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def cmd_build(a, then_check=True):
    cfg_path = a.config or _default_config_path(a.pdf)
    if not os.path.exists(cfg_path):
        print(f"No config at {cfg_path}. Run `pdf2epub analyze` first (or `pdf2epub convert`).")
        return 2
    cfg = _load_cfg(cfg_path)
    if a.cover:
        cfg["options"]["cover"] = a.cover
    if a.stamp:
        cfg["options"]["stamp"] = True
    out = a.output or _default_epub_path(a.pdf)
    path, report = build(a.pdf, cfg, out)
    rep_path = os.path.splitext(out)[0] + ".build.json"
    with open(rep_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    print(f"Built {path}: {report['toc_entries']} TOC entries, {report['page_markers']} print page markers, "
          f"{report['images']} images, {report['fonts']} fonts")
    if then_check and not a.no_check:
        ok, text = check(out, report, a.pdf, cfg, visual_dir=(a.visual if getattr(a, "visual", None) else None),
                         reference=getattr(a, "reference", None))
        qa = os.path.splitext(out)[0] + "_QA.txt"
        with open(qa, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(text)
        return 0 if ok else 1
    return 0


def cmd_check(a):
    report = None
    rp = os.path.splitext(a.epub)[0] + ".build.json"
    if os.path.exists(rp):
        with open(rp, encoding="utf-8") as fh:
            report = json.load(fh)
    cfg = _load_cfg(a.config) if a.config else None
    ok, text = check(a.epub, report, a.pdf, cfg, visual_dir=a.visual, reference=a.reference)
    print(text)
    return 0 if ok else 1


def cmd_convert(a):
    cfg_path = a.config or _default_config_path(a.pdf)
    if not os.path.exists(cfg_path):
        a.output_cfg = cfg_path
        ns = argparse.Namespace(pdf=a.pdf, output=cfg_path)
        cmd_analyze(ns)
    a.config = cfg_path
    return cmd_build(a)


def cmd_fetch(_a):
    jar = fetch_epubcheck()
    print(f"EPUBCheck ready: {jar}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="pdf2epub", description="Turn text-based PDF books into clean EPUB 3.")
    p.add_argument("--version", action="version", version=f"pdf2epub-kit {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("analyze", help="propose a book config (style map, sections, page numbers)")
    s.add_argument("pdf")
    s.add_argument("-o", "--output", help="config path (default: <pdf>.pdf2epub.yaml)")
    s.set_defaults(func=cmd_analyze)

    for name, fn, hlp in (("build", cmd_build, "build the EPUB from the PDF and a config, then check it"),
                          ("convert", cmd_convert, "analyze (if no config yet) + build + check in one go")):
        s = sub.add_parser(name, help=hlp)
        s.add_argument("pdf")
        s.add_argument("-c", "--config")
        s.add_argument("-o", "--output", help="EPUB path (default: next to the PDF)")
        s.add_argument("--cover", help="cover image (jpg/png), overrides the config")
        s.add_argument("--stamp", action="store_true",
                       help="copy a detected buyer/licence stamp to the copyright page (off by default)")
        s.add_argument("--no-check", action="store_true")
        s.add_argument("--visual", metavar="DIR", help="also write a side-by-side visual report (needs Playwright)")
        s.add_argument("--reference", metavar="EPUB", help="compare structure with a reference EPUB (no text is compared)")
        s.set_defaults(func=fn)

    s = sub.add_parser("check", help="validate an EPUB (EPUBCheck, lints, completeness if a build report exists)")
    s.add_argument("epub")
    s.add_argument("--pdf")
    s.add_argument("-c", "--config")
    s.add_argument("--visual", metavar="DIR")
    s.add_argument("--reference", metavar="EPUB", help="compare structure with a reference EPUB")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("fetch-epubcheck", help="download EPUBCheck (needs Java to run)")
    s.set_defaults(func=cmd_fetch)

    a = p.parse_args(argv)
    try:
        return a.func(a)
    except PermissionError as e:
        print(f"Error: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
