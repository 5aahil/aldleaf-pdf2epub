# Privacy policy

This policy covers the Aldleaf toolkit and its companion Claude skill, `pdf-to-epub` (the "Aldleaf" plugin). Last updated: 3 November 2026.

## Short version

Aldleaf collects nothing. It has no accounts, no analytics, no tracking and no server of its own. Your PDFs, EPUBs, configs and reports stay on your own computer.

## What the toolkit does with your files

- It reads the PDF you give it and writes the EPUB, a book config (`*.aldleaf.yaml`), a QA report and a build report next to it, on your own machine.
- It sends none of these anywhere.
- Shop PDFs often carry a buyer stamp (your email and purchase date). The toolkit detects it and leaves it out of the EPUB. It adds one "Licensed to ..." line only if you ask for it with `--stamp`.

## Network use

The toolkit itself only goes online in these cases, and only when you run them:

- **Installing:** `pip install` downloads the toolkit from GitHub and its dependencies from PyPI.
- **`aldleaf fetch-epubcheck`:** downloads the official EPUBCheck validator from its GitHub release (w3c/epubcheck).
- **Optional visual reports:** installing Playwright downloads a browser. The reports themselves are made locally.

No book content, file names or personal data are sent in any of these requests.

## Using the skill with Claude

The skill is a set of instructions for Claude. It doesn't collect anything either. When you use it, Claude works with your files in your Claude session, so what you share in that session is handled by Anthropic under [Anthropic's privacy policy](https://www.anthropic.com/legal/privacy), not by this project. The skill tells Claude to keep PDFs, EPUBs, configs and buyer stamps private: never commit them to a repository, never publish them, and never paste the stamp anywhere.

## Copy protection and rights

Encrypted or password-protected PDFs are refused. Aldleaf never removes copy protection. Use it on books you wrote or publish, or on your own copy of a book for your own devices.

## Contact

Questions or concerns: open an issue at https://github.com/5aahil/aldleaf-pdf2epub/issues. Please never attach real books or personal data to an issue.
