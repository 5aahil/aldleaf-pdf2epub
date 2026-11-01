# Contributing

1. Read [docs/privacy.md](docs/privacy.md) first. No real books, PDFs, EPUBs, configs or personal data in the repository, issues or pull requests.
2. Reproduce a layout problem with a **synthetic** fixture in `tests/fixtures.py` (invented text only), then fix it.
3. `pip install -e ".[dev]" && pytest`. Every change keeps all tests green.
4. Keep the converter general. Detect things from measurements of the PDF, not from one book's fonts or page numbers. Book-specific choices belong in the config file, not in the code.
