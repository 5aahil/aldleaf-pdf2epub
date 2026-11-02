# The book config (`*.aldleaf.yaml`)

`aldleaf analyze` writes this file. Everything in it is a proposal: edit it, then run `aldleaf build`. The file contains short text samples from your PDF, so keep it out of public repositories (`.gitignore` already excludes `*.aldleaf.yaml`).

## metadata

| key | meaning |
|---|---|
| `title`, `subtitle` | the book title (taken from the fullest heading on the opening pages) |
| `authors` | book-level authors. For anthologies leave it empty or put the editor; story authors become contributors |
| `publisher`, `date`, `isbn` | read from the copyright page when possible. Use the **print** ISBN if you want page numbers tied to that edition |
| `language` | BCP 47 code: `en`, `de`, `fr`, … Kindle rejects books with a wrong or missing language |
| `description`, `subjects` | optional store-style metadata |

## options

| key | default | meaning |
|---|---|---|
| `book_kind` | detected | `prose`, `anthology` or `poetry`. Poetry keeps every line break |
| `paragraph_style` | detected | `indent`, `spaced` or `both`: how a new paragraph is recognised |
| `alignment` | detected | `justified` or `ragged`, which affects how deliberate line breaks are told from wraps |
| `auto_hyphenated` | detected | `true` = remove layout hyphens at line ends. `false` = every line-end hyphen is part of the word |
| `scene_breaks` | `as_printed` | `as_printed` keeps the author's own marker or blank space. `ornament` uses one centred rule everywhere |
| `short_line` | `0.75` | a line shorter than this share of the text width counts as deliberately ended (signature, list line, short reply) |
| `scene_break_gap` | measured | vertical gap (pt) between paragraphs that counts as a blank-space scene break |
| `cover` | none | path to a cover image (JPG/PNG, about 1600×2560 px). Without it, `cover_page` is rendered |
| `stamp` | `false` | copy a detected buyer stamp to the copyright page as "Licensed to …" |
| `fonts` | `{}` | optional embedded fonts per role, see below |
| `page_list` | `true` | add print page markers and the page list |

### Embedding fonts

Aldleaf never copies fonts out of the PDF, because subset fonts in a PDF are licensed for that PDF only. To use the print fonts, point to font files you are licensed to embed (for example the SIL Open Font License fonts from Google Fonts):

```yaml
fonts:
  body:    {family: Baskervville, regular: fonts/Baskervville-Medium.ttf, italic: fonts/Baskervville-MediumItalic.ttf,
            bold: fonts/Baskervville-Bold.ttf, bolditalic: fonts/Baskervville-BoldItalic.ttf}
  heading: {family: IM Fell English SC, regular: fonts/IMFellEnglishSC-Regular.ttf}
  screen:  {family: JetBrains Mono, regular: fonts/JetBrainsMono-Medium.ttf, bold: fonts/JetBrainsMono-ExtraBold.ttf}
  chat:    {family: Figtree, regular: fonts/Figtree-Light.ttf, bold: fonts/Figtree-SemiBold.ttf}
```

Use static (non-variable) TTF/OTF files. Kindle shows them under "Publisher Font"; Apple Books shows them as "Original".

## styles

One entry per `font@size`, with `chars` (how much text uses it), `pages` and a `sample`. Set `role` to one of:

| role | becomes |
|---|---|
| `body` | paragraphs (italic and bold variants of the body face stay inline) |
| `heading` | a section title. A heading on a section's first page starts the section; later ones become `h2` |
| `subheading` | an in-text `h2` (nonfiction) |
| `note` | opening-page text: dedications, story notes |
| `screen` | on-screen / AI / code text in monospace |
| `chat`, `chat_label` | message bubbles and their sender/time labels |
| `email` | email text (headers such as From:/To:/Subject: are detected in any style) |
| `blockquote` | letters, quotations, inserted documents |
| `footnote` | notes at the page foot, which become pop-up footnotes linked from their superscript number |
| `dropcap` | a large initial letter, glued back onto its word |
| `scene_break` | a printed scene-break marker |
| `caption` | small text near images |
| `ignore` | leave out (e.g. decorative text) |

## sections

```yaml
- type: chapter            # titlepage | copyright | toc | chapter
  epub_type: chapter       # chapter foreword preface introduction prologue epilogue afterword
                           # acknowledgments dedication epigraph glossary appendix endnotes bibliography index
  matter: body             # front | body | back
  title: "Chapter 1: Low Tide"
  author: Ada Example      # anthologies: shown as byline and as contributor
  pages: [15, 38]          # PDF page numbers (1-based), inclusive
```

- `toc` sections are not copied: the contents page is rebuilt with links.
- Back-matter sections that belong together (for example "Thank You" followed by several "… Patrons" lists) are grouped into one section with `h2` subsections.
- Delete, split or retitle sections freely.

## page_labels

- `printed`: how many print page numbers were read from the PDF.
- `inferred`: how many unnumbered pages (chapter openers, blanks, art pages) were given the number they would have had in print.
- `overrides`: fix single pages, e.g. `{17: "5"}` (PDF page → print label).
