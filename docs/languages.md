# Languages

Aldleaf converts books in any language written **horizontally, left to right**. It never translates your text. It does three language-aware things:

- **Detects the book's language** (declared in the PDF, or worked out from the script and the words) and writes it into the EPUB. Ebook stores, Kindle and screen readers need this to pick the right fonts, hyphenation and pronunciation. The `analyze` summary says how the language was found; if it says "not detected", set `language` in the config.
- **Recognises layout words in your language:** chapter labels ("Kapitel 3", "Capítulo IV", "第1章", "अध्याय १"), bylines ("Par …", "लेखक: …", "作者：…"), content-warning boxes and e-mail headers.
- **Writes its own few labels in your language:** the contents heading, cover and title-page names, the byline prefix and the page markers screen readers announce ("Seite 5", "第5页", "5쪽").

## Tested languages

Every language below was tested with invented sample books exported to PDF the way a browser or word processor does it: an anthology (bylines, content warnings, scene breaks), a novel (chapter labels, first-line indents, drop caps in Latin, Greek and Cyrillic), nonfiction (subheadings, bullet and numbered lists, a footnote) and poetry (line breaks and stanzas). Each book was converted, and the EPUB text was compared word for word with the original text.

| Script | Languages | Result |
|---|---|---|
| Latin | English, German, French, Spanish, Portuguese, Italian, Dutch, Swedish, Danish, Norwegian, Finnish, Polish, Czech, Romanian, Hungarian, Turkish | exact |
| Greek, Cyrillic | Greek, Russian, Ukrainian | exact |
| Devanagari | Hindi, Marathi | exact |
| Gurmukhi | Punjabi | exact |
| Bengali | Bengali | exact |
| Tamil | Tamil | exact |
| Chinese | Simplified, Traditional | exact |
| Japanese, Korean | Japanese, Korean | exact |
| Thai | Thai | works, but check the text (see below) |

Spanish and Portuguese cover both European and Latin American usage. Other languages in these scripts (Catalan, Slovak, Bulgarian, Gujarati, Telugu, Kannada, Malayalam, Sinhala, Nepali and more) use the same code paths; the language may need to be set by hand in the config, and Aldleaf's own labels fall back to English.

## The PDF's hidden text layer

Aldleaf reads the text a PDF stores behind what you see. For most PDFs that text is exact. For scripts that combine letters into ligatures (Hindi, Bengali, Punjabi, Thai and others), some programs store it imperfectly. Aldleaf handles this as follows:

- **Repairs** the one fault that is always safe to fix: a vowel sign or other mark stored twice. The QA report says how many it repaired.
- **Warns** in the `analyze` summary and the QA report when words look damaged: unreadable characters, stray symbols inside a word, a vowel sign without a letter. The build then does not report "all checks passed". Re-export the PDF from your writing or layout program with fonts embedded and convert it again.
- **Thai, Lao, Khmer and Burmese:** some PDF exports drop tone marks or spaces at line ends, and that can't be detected from the PDF alone. Read a few pages of the EPUB before publishing.
- **Bold text made by the exporting program:** when a font has no bold weight, some programs fake one and can store the letters imperfectly (a Bengali ্র mark, for example). Check headings in these scripts.

## Lines without spaces

Chinese, Japanese and Thai don't put spaces between words, so Aldleaf joins their wrapped lines without adding one, and keeps real spaces (Thai uses them between phrases). Korean does use spaces but may wrap inside a word (browsers break between any two syllables). Aldleaf decides each break from the book itself: it joins the halves when the whole word appears elsewhere in the book, when the next line starts with a particle or ending (를, 부터, 었다, …), or when neither half is a word of its own, and keeps the space when either half is.

## Not supported yet

- **Right-to-left scripts** (Arabic, Hebrew, Persian, Urdu): detected and refused with a clear message.
- **Vertical Chinese or Japanese text:** detected and refused with a clear message.
- **Books in more than one language:** the whole book gets one language tag, so passages in a second language are read and hyphenated as the main language.

## Planned next

- Right-to-left books (Urdu, Arabic, Persian, Hebrew).
- Vertical Chinese and Japanese text.
- Books in more than one language: bilingual editions, translations printed next to the original, an author's passages in another language, or a mythology retelling that quotes the original verses. Each passage will keep its own language tag.
