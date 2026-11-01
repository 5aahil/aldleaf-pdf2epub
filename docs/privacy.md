# Privacy and rights rules

These rules apply to the repository, to issues and pull requests, and to anyone (or any AI assistant) working on it.

## Rule 1: no personal data and no books in the repository, ever

- Shop PDFs often carry a **buyer stamp on every page**: the buyer's email address and purchase date.
  - pdf2epub reads it **at run time only**.
  - It leaves the stamp out of the EPUB unless `--stamp` is used. Then it writes one "Licensed to …" line on the copyright page.
- So **source PDFs, generated EPUBs, configs (`*.pdf2epub.yaml`), build reports, extracted text or images, and QA screenshots are personal or copyrighted data**.
  - `.gitignore` excludes them. Do not weaken those rules, and do not `git add -f` them.
- **Never hard-code an email address, a name or a purchase date** in code, docs, tests, fixtures, commit messages or issues. Use placeholders such as `buyer@example.com`.
- **Test fixtures are synthetic.** `tests/fixtures.py` and `tests/make_sample.py` generate books from invented filler text. Do not add real books or excerpts.
- Before every push, run this from the repo root. It must print nothing:
  ```
  git grep -nIE "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}" -- . ':!docs/privacy.md' ':!**/OFL*.txt' | grep -v "@example\.\(com\|org\)"
  ```
  CI runs the same check.

## Rights

- pdf2epub is for authors and publishers converting their own books, and for readers converting their own purchased copy for their own devices.
- It refuses encrypted or password-protected PDFs and never removes copy protection.
- Do not distribute EPUBs made from other people's books.
