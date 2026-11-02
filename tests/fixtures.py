"""Synthetic books of different kinds for tests. All text is invented filler.

novel()      US Letter, Word-style export: no running heads, centred page numbers,
             "Chapter 1" + title headings, drop caps, automatic hyphenation,
             justified text, first-line indents and no paragraph spacing.
nonfiction() A5, ragged-right block paragraphs (spacing, no indents), bold
             subheadings, bullet and numbered lists, footnotes with superscripts.
poetry()     6x9 in, short verse lines in stanzas.
"""
try:
    import pymupdf
except ImportError:
    import fitz as pymupdf

WORDS = ("morning harbour lantern weather quietly remembered beneath everything "
         "particular conversation afterwards understanding windowsill").split()
SENT = [
    "The morning arrived quietly over the harbour and nobody remembered the lantern.",
    "Everything beneath the windowsill was particular in a way that resisted understanding.",
    "Afterwards the conversation turned to weather, as conversations in small towns always do.",
    "She remembered the lantern only when the harbour had gone completely dark.",
    "There was a particular understanding between them that needed no conversation.",
]


def para_text(n, seed=0):
    return " ".join(SENT[(seed + i) % len(SENT)] for i in range(n))


def measure(text, size, font="tiro"):
    return pymupdf.get_text_length(text, fontname=font, fontsize=size)


def wrap(text, width, size, font="tiro", hyphenate=False, first_indent=0.0):
    """Greedy line breaking; optionally hyphenate long words like a layout program."""
    words = text.split()
    lines, cur = [], ""
    avail = width - first_indent
    i = 0
    while i < len(words):
        w = words[i]
        trial = (cur + " " + w).strip()
        if measure(trial, size, font) <= avail:
            cur = trial
            i += 1
            continue
        if hyphenate and len(w) >= 8 and w.isalpha():
            head = w[: len(w) // 2]
            t2 = (cur + " " + head + "-").strip()
            if measure(t2, size, font) <= avail:
                lines.append(t2)
                words[i] = w[len(w) // 2:]
                cur, avail = "", width
                continue
        lines.append(cur)
        cur, avail = "", width
    if cur:
        lines.append(cur)
    return lines


class Doc:
    def __init__(self, w, h, margin, size, lead, font="tiro"):
        self.doc = pymupdf.open()
        self.w, self.h, self.m, self.size, self.lead, self.font = w, h, margin, size, lead, font
        self.tw = w - 2 * margin
        self.page = None
        self.y = 0
        self.folio = 0

    def new_page(self, numbered=True):
        self.page = self.doc.new_page(width=self.w, height=self.h)
        self.folio += 1
        if numbered:
            s = str(self.folio)
            self.page.insert_text((self.w / 2 - measure(s, 10) / 2, self.h - 36), s, fontsize=10, fontname="tiro")
        self.y = self.m + 10
        return self.page

    def room(self, need=1):
        if self.y + need * self.lead > self.h - self.m - 10:
            self.new_page()

    def text_line(self, s, x=0, font=None, size=None, justify=False):
        size = size or self.size
        font = font or self.font
        if justify and " " in s:
            # spread words to the full width like justified print
            ws = s.split(" ")
            natural = sum(measure(w, size, font) for w in ws)
            gap = (self.tw - x - natural) / (len(ws) - 1)
            cx = self.m + x
            for w in ws:
                self.page.insert_text((cx, self.y), w, fontsize=size, fontname=font)
                cx += measure(w, size, font) + gap
        else:
            self.page.insert_text((self.m + x, self.y), s, fontsize=size, fontname=font)
        self.y += self.lead


def novel(path):
    d = Doc(612, 792, 72, 12, 16)
    d.new_page(numbered=False)
    d.page.insert_text((150, 300), "The Lantern Keeper", fontsize=34, fontname="tibo")
    d.page.insert_text((230, 350), "A Novel", fontsize=16, fontname="tiit")
    d.new_page(numbered=False)
    d.page.insert_text((72, 120), "Copyright © 2025 Example Books. All rights reserved.", fontsize=9, fontname="tiro")
    for ch, title in ((1, "Low Tide"), (2, "The Long Night")):
        d.new_page()
        d.page.insert_text((72, 200), f"Chapter {ch}", fontsize=14, fontname="tiro")
        d.page.insert_text((72, 230), title, fontsize=24, fontname="tibo")
        d.y = 290
        # drop cap paragraph
        text = para_text(4, ch)
        d.page.insert_text((72, d.y + 20), text[0], fontsize=40, fontname="tibo")
        lines = wrap(text[1:], d.tw - 34, 12, hyphenate=True)
        for k, ln in enumerate(lines):
            x = 34 if k < 2 else 0
            if k == 2:
                lines2 = wrap(" ".join(lines[2:]), d.tw, 12, hyphenate=True)
                for j, l2 in enumerate(lines2):
                    d.room()
                    d.text_line(l2, justify=j < len(lines2) - 1)
                break
            d.text_line(ln, x=x, justify=True)
        for p in range(9):
            lines = wrap(para_text(5, p + ch), d.tw, 12, hyphenate=True, first_indent=18)
            for k, ln in enumerate(lines):
                d.room()
                d.text_line(ln, x=18 if k == 0 else 0, justify=k < len(lines) - 1)
    d.doc.save(path)
    return path


def nonfiction(path, drawn_bullets=False):
    d = Doc(420, 595, 50, 10.5, 14, font="helv")
    d.new_page(numbered=False)
    d.page.insert_text((60, 220), "Field Notes on Weather", fontsize=26, fontname="hebo")
    d.new_page()
    d.page.insert_text((50, 110), "Introduction", fontsize=22, fontname="hebo")
    d.y = 150
    note_no = 0

    def block_para(text, note=None):
        nonlocal note_no
        lines = wrap(text, d.tw, 10.5, font="helv")
        for k, ln in enumerate(lines):
            d.room()
            d.text_line(ln, font="helv")
            if note and k == len(lines) - 1:
                note_no += 1
                x = d.m + measure(ln, 10.5, "helv") + 1
                d.page.insert_text((x, d.y - d.lead - 4), str(note_no), fontsize=6.5, fontname="helv")
                d.page.insert_text((d.m, d.h - 70), f"{note_no} {note}", fontsize=8, fontname="helv")
        d.y += 8

    block_para(para_text(3, 1), note="An invented source, cited only for testing.")
    block_para(para_text(2, 2))
    d.room(3)
    d.y += 6
    d.text_line("Why it matters", font="hebo")
    d.y += 4
    block_para(para_text(2, 3))
    for item in ("Watch the pressure.", "Write down the wind.", "Check the tide tables."):
        d.room()
        if drawn_bullets:   # like a web browser: a small filled dot, no bullet character
            d.page.draw_circle((d.m + 8, d.y - 3.5), 1.6, color=None, fill=(0, 0, 0))
        else:
            d.page.insert_text((d.m + 6, d.y), "•", fontsize=10.5, fontname="helv")
        d.page.insert_text((d.m + 18, d.y), item, fontsize=10.5, fontname="helv")
        d.y += d.lead
    d.y += 8
    block_para(para_text(2, 4))
    for n, item in enumerate(("Open the logbook.", "Record the time.", "Sign the entry."), 1):
        d.room()
        d.page.insert_text((d.m + 6, d.y), f"{n}.", fontsize=10.5, fontname="helv")
        d.page.insert_text((d.m + 22, d.y), item, fontsize=10.5, fontname="helv")
        d.y += d.lead
    d.y += 8
    d.room(3)
    d.text_line("What comes next", font="hebo")
    d.y += 4
    for s in range(3):
        block_para(para_text(3, s))
    d.doc.save(path)
    return path


def poetry(path):
    d = Doc(432, 648, 72, 11, 15)
    d.new_page(numbered=False)
    d.page.insert_text((90, 250), "Small Weather", fontsize=28, fontname="tibo")
    stanzas = [["The harbour keeps its lantern lit", "for boats that never come,",
                "and every gull that circles it", "is counting to the sum."],
               ["Beneath the sill the morning waits", "with nothing much to say;",
                "the weather leans against the gates", "and quietly goes away."]]
    for t in ("Lantern", "Sill"):
        d.new_page()
        d.page.insert_text((72, 140), t, fontsize=20, fontname="tibo")
        d.y = 190
        for st in stanzas * 2:
            for ln in st:
                d.text_line(ln)
            d.y += 12
    d.doc.save(path)
    return path
