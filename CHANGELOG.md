# Changelog

## 0.2.0
- **Renamed to Aldleaf** (earlier pdf2epub-kit), after the Aldine leaf ❦. The name `pdf2epub` was used by many other projects and by a different package on PyPI.
  - Repository and project page: `5aahil/aldleaf-pdf2epub`. GitHub forwards the old repository address.
  - Command: `aldleaf` (was `pdf2epub`). Book configs: `*.aldleaf.yaml`; existing `*.pdf2epub.yaml` files are still picked up.
  - Claude plugin: `aldleaf` (was `pdf2epub`).
- New logo and plugin icon: the Aldine leaf drawn as an "e".
- Project page: search-friendly title and description, structured data, sitemap.
- The pdf-to-epub Claude skill now ships in this repo (`plugin/`), installable as a Claude Code plugin or as a zip for the Claude app.
- Plugin icon, listing metadata and a privacy policy (`PRIVACY.md`); submitted to the Claude plugin directory.

## 0.1.0
- Adaptive SVG artwork (grey vector badges/stamps/logos follow the reader theme; Kindle PNG fallback).
- Project page (GitHub Pages) with feature images from the synthetic samples.
- First release: analyze, build, check, convert; style-map config; anthology, novel, nonfiction and poetry layouts;
  chats, emails, screen text, footnotes, lists, drop caps, two-column lists; print page list with inferred numbers;
  EPUBCheck, letter-level completeness, lints, visual report, reference comparison.
