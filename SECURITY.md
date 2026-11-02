# Security policy

## Supported versions

Only the latest release on the `main` branch gets security fixes.

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report it privately with GitHub's [private vulnerability reporting](https://github.com/5aahil/aldleaf-pdf2epub/security/advisories/new) instead. Include:

- what the problem is and how it can be triggered;
- the Aldleaf version and your Python and PyMuPDF versions;
- if a file is needed, a **synthetic** PDF that reproduces the problem. Never attach a purchased book or anything containing personal data.

You'll get a reply within 7 days. Once the problem is fixed, you'll be credited in the changelog if you want to be.

## What counts

- Crafted PDFs that make Aldleaf run code, read or write files outside the folders it was given, or hang the machine.
- Personal data (for example a buyer stamp) ending up in an EPUB when `--stamp` was not used.
- Anything that would let Aldleaf bypass copy protection. Aldleaf must refuse encrypted PDFs.
