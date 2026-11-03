# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-11-03
- **Renamed to Aldleaf** (earlier pdf2epub-kit), after the Aldine leaf ❦. The name `pdf2epub` was used by many other projects and by a different package on PyPI.
  - Repository and project page: `5aahil/aldleaf-pdf2epub`. GitHub forwards the old repository address.
  - Command: `aldleaf` (was `pdf2epub`). Book configs: `*.aldleaf.yaml`; existing `*.pdf2epub.yaml` files are still picked up.
  - Claude plugin: `aldleaf` (was `pdf2epub`). Skill: `aldleaf` (was `pdf-to-epub`), with `pdf2epub` and `pdf-to-epub` as shortcuts; in Claude Code run `/aldleaf:aldleaf`, `/aldleaf:pdf2epub` or `/aldleaf:pdf-to-epub`.
  - Claude app download: `aldleaf-skill.zip`.
- **Books in any horizontal, left-to-right language**, tested word for word in 27 languages as anthologies, novels, nonfiction and poetry (European, Greek, Cyrillic, Hindi, Marathi, Punjabi, Bengali, Tamil, Thai, Chinese Simplified and Traditional, Japanese, Korean); see `docs/languages.md`.
  - The book's language is detected (from the PDF, its script and its words) instead of always `en`.
  - Chapter labels, bylines, content warnings, e-mail headers and section titles (foreword, contents, acknowledgements, …) are recognised in these languages; Aldleaf's own labels follow the book's language.
  - Lines in Chinese, Japanese and Thai join without spaces; Korean words split across lines are rejoined, decided from the book's own vocabulary and Korean grammar.
  - Text-layer check: doubled Indic marks are repaired, damaged words are reported, and the build no longer claims success for a damaged PDF.
  - Right-to-left and vertical books are refused with a clear message instead of a broken EPUB.
- Fixed: a book without detected chapters produced an invalid EPUB (empty table of contents); errors now print a clear message instead of a traceback; bylines are no longer confused with titles that start with 'De', 'Da' or 'Di'; a ruled frame around text, such as a content-warning box, is no longer turned into an empty picture; bullets drawn as dots (as web browsers export them) become list items; list numbers stored in pieces are removed; poetry is recognised when its lines are long or all the same width (Chinese, Japanese); justified Thai lines are no longer split into separate paragraphs; titles and subheadings starting with 'By', 'De', 'Par' and similar words are no longer read as bylines unless a name follows; browser-exported PDFs with unnamed Type 3 fonts are read as one font.
- German README (`README.de.md`).
- New logo and plugin icon: the original page-to-book mark with an upright Aldine leaf, with a dark-theme version.
- README and project page: a Languages section with two new images and the plan for the next versions (right-to-left books, vertical text, books in more than one language).
- Project page: search-friendly title and description, structured data, sitemap; German version (`/de/`) with German images and an EN/DE switch; an About the name section; a header that stays at the top while scrolling, with a sidebar menu on phones and tablets.
- The pdf-to-epub Claude skill now ships in this repo (`plugin/`), installable as a Claude Code plugin or as a zip for the Claude app.
- Plugin icon, listing metadata and a privacy policy (`PRIVACY.md`); submitted to the Claude plugin directory.

## [0.1.0] - 2026-11-01
- Adaptive SVG artwork (grey vector badges/stamps/logos follow the reader theme; Kindle PNG fallback).
- Project page (GitHub Pages) with feature images from the synthetic samples.
- First release: analyze, build, check, convert; style-map config; anthology, novel, nonfiction and poetry layouts;
  chats, emails, screen text, footnotes, lists, drop caps, two-column lists; print page list with inferred numbers;
  EPUBCheck, letter-level completeness, lints, visual report, reference comparison.
