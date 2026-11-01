# Accessibility

## The EPUBs pdf2epub makes

Accessible ebooks are a core goal, not an extra. Every EPUB pdf2epub builds has:

- a real structure: headings, sections with `epub:type` and DPUB-ARIA roles, a linked contents page and landmarks;
- print page markers and a page list, so readers using assistive technology can follow page references;
- text alternatives for artwork (adaptive SVG badges carry a `<title>`; images carry `alt` text) and labelled chats and emails;
- reader control over fonts, sizes and colours: no forced text colours or backgrounds, so dark, sepia and high-contrast modes work;
- schema.org accessibility metadata, and output that passes the DAISY Ace checker on our test books.

Alt text is generated from nearby captions where possible, otherwise it says "Illustration". Authors should review it in the config (`art_alt`) before publishing.

## The project itself

The documentation and the project page use plain language, real headings, alt text for every image and colours that work in light and dark mode.

## Reporting barriers

If something in an EPUB, the docs or the project page is hard to use with your setup, please [open an accessibility issue](https://github.com/5aahil/pdf2epub-kit/issues/new?template=accessibility.yml). Accessibility problems are treated as bugs.
