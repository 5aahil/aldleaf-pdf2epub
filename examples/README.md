# Examples

Generate the synthetic sample books used in the tests (invented text only) and convert them:

```
python tests/make_sample.py sample.pdf          # anthology with chats, emails, screen text
python -c "import sys; sys.path.insert(0,'tests'); import fixtures; fixtures.novel('novel.pdf'); fixtures.nonfiction('nonfiction.pdf'); fixtures.poetry('poetry.pdf')"
pdf2epub convert sample.pdf
```

Generated PDFs, EPUBs and configs are git-ignored.
