---
name: "pdf-to-epub"
description: "Convert a text-based PDF book into a clean, validated EPUB 3 for Apple Books and Kindle with pdf2epub-kit: analyze, confirm the style map, build, check, deliver."
---

# PDF to EPUB (pdf2epub-kit)

Use this when someone wants a proper EPUB (Apple Books, Kindle via Send to Kindle, Kobo) from a PDF book, or wants an existing conversion checked.

The toolkit lives at https://github.com/5aahil/pdf2epub-kit (MIT). It reads the PDF's layout (fonts, sizes, positions, drawn shapes) instead of flattening text. It proposes a book config, which the user confirms, and then it builds and checks the EPUB.

## 0. Rights and privacy first (always)

- **Ask whose book it is** if that isn't clear.
  - **The user wrote or publishes it:** do the full workflow and deliver the EPUB.
  - **It's the user's purchased copy of someone else's book:** help fully with analysis, the config, the checks and fixes. The final EPUB must be built by the user on their own computer from their own copy, so give them the exact commands. Do not send them a full EPUB of a copyrighted book you produced, and do not paste book text beyond short samples needed to discuss a fix.
- **Copy protection:** if the PDF is encrypted or password-protected, stop. The toolkit refuses it and you must not try to remove protection. Suggest asking the seller for an unprotected copy.
- **Buyer stamps:** shop PDFs often carry a buyer stamp (email and purchase date) on every page.
  - The toolkit detects the stamp and leaves it out by default. `--stamp` adds one "Licensed to ..." line on the copyright page, but only if the user asks.
  - Treat PDFs, EPUBs, `*.pdf2epub.yaml` configs, build reports and screenshots as personal or copyrighted data. Never commit them to a repo, never publish them as an artifact, never paste the stamp anywhere.
- **Scanned PDFs (no text layer):** these aren't supported. Say so plainly; OCR is out of scope.

## 1. Install

```
pip install git+https://github.com/5aahil/pdf2epub-kit   # needs Python 3.10+
pdf2epub fetch-epubcheck                                  # validator; needs Java (java -version)
```

- If GitHub isn't reachable, ask the user to attach the pdf2epub-kit zip and run `pip install ./pdf2epub-kit`.
- Optional, for visual reports: `pip install playwright` (use an existing Chromium if one is installed).
- Work on a copy of the PDF in its own folder.

## 2. Analyse

`pdf2epub analyze book.pdf` prints a summary and writes `book.pdf2epub.yaml`. Then verify the guesses against the PDF itself, never from the summary alone:

- **Look at the pages.** Render key pages with PyMuPDF (`page.get_pixmap(dpi=70)`) and view them:
  - the first page of every detected section;
  - one page for each style that isn't `body`;
  - any page with chats, emails, screen text, lists or footnotes.
- **Styles:** check each `font@size` role (body, heading, subheading, note, screen, chat, chat_label, email, blockquote, footnote, dropcap, scene_break, caption, ignore).
- **Sections:** check titles, types, `epub_type`, page ranges and per-story authors. Split, merge or retitle where the PDF shows otherwise.
- **Profile:**
  - `book_kind`: prose, anthology or poetry.
  - `paragraph_style`: indent, spaced or both.
  - `alignment`.
  - `auto_hyphenated`: if false, every line-end hyphen is a real compound.
- **Metadata:** title, authors, publisher, date, the print ISBN, and `language`. A wrong or missing language breaks Kindle delivery.
- **Scene breaks:** these follow the author. Keep `scene_breaks: as_printed` (the author's own marker, or blank space) unless the user explicitly wants one uniform ornament. Never add or remove breaks because of book kind.

Show the user a short summary of what you found and what you changed. Ask only about real decisions:

- which ISBN is the print one;
- a cover image (about 1600x2560 px);
- fonts they are licensed to embed;
- whether to add the stamp line;
- anything ambiguous in the structure.

## 3. Build and check

```
pdf2epub build book.pdf -c book.pdf2epub.yaml [--cover cover.jpg] [--visual qa_visual] [--reference their.epub]
```

The build writes `book.epub`, `book_QA.txt` and `book.build.json`, and runs the checks:

- EPUBCheck: must show 0 errors.
- Text completeness per section: every letter is compared with the PDF.
- Print page-marker coverage.
- Lints: leftover page numbers, unjoined wraps, missed paragraph breaks.

Optional checks:

- `--visual`: side-by-side PDF and EPUB screenshots.
- `--reference`: structural comparison with another EPUB (sections, chats, emails, scene breaks, page markers; no text).

If something is off:

- **First fix the config** (roles, sections, options) and rebuild.
- **Only if a real layout pattern is unsupported:** reproduce it with a synthetic fixture in the toolkit's `tests/fixtures.py` (invented text only), fix the code, and keep `pytest` green.
- **Visually check** a few rendered EPUB pages against the PDF yourself: one normal chapter, every special layout, a story or chapter opener, and back matter, in light and dark mode at phone width.

## 4. Deliver

- **User's own book:** send the EPUB and the QA report as files (never as a published artifact).
- **Someone else's book:** send the confirmed config and the exact build command, and say what the QA output should look like (`Result: all checks passed`).

In both cases, give the 10-minute device check:

1. **Apple Books:** cover and contents; one chapter in White and Night themes, with the Original font and a system font; "Show printed page numbers".
2. **Kindle:** upload at amazon.com/sendtokindle (not USB sideloading); check cover and contents, and special layouts with Publisher Font off and on.

## Known limits

- Not supported: scanned PDFs, multi-column body text, complex tables and maths.
- Kindle shows its own page estimates for sent books, not print page numbers.
- Embedded fonts may be ignored on Kindle. The layout never depends on them.