"""Generate a small synthetic book PDF for tests. All text is invented filler.

Layout features covered: title page, copyright page with a tiny buyer stamp,
contents page with dot leaders, chapter openers with byline and content
warning, running heads, page numbers, first-line indents, a paragraph that
continues across a page break, italics, a printed scene break, a blank-space
scene break, monospace screen text, chat bubbles (incoming/outgoing) and an
email with a signature.
"""
import sys

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf

W, H = 432, 648
LEFT = {1: 63, 0: 36}          # odd / even page margin
TEXTW = 333
LEAD = 15
BODY = 10.5
STAMP = "buyer@example.com 01 Jan 2026"

FILLER = ("The lighthouse keeper counted the steps every evening, though the number never changed. "
          "Salt had worked into the railings and the brass had gone green at the edges. "
          "Below, the harbour lights blinked on one after another like a slow conversation. "
          "She wrote the weather in a ledger that nobody had asked to read in years. ")


def wrap(text, width_chars=68):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width_chars:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


class Book:
    def __init__(self):
        self.doc = pymupdf.open()
        self.page = None
        self.n = 0
        self.y = 0
        self.folio = None
        self.head = None

    def new_page(self, folio=None, head=None):
        self.page = self.doc.new_page(width=W, height=H)
        self.n += 1
        self.folio, self.head = folio, head
        self.page.insert_text((3, 6), STAMP, fontsize=3, fontname="helv")
        if head:
            self.page.insert_text((W / 2 - len(head) * 2.2, 30), head, fontsize=9, fontname="tiit")
        if folio is not None:
            self.page.insert_text((W / 2 - 4, 610), str(folio), fontsize=9, fontname="tiro")
        self.y = 60
        return self.page

    @property
    def left(self):
        return LEFT[self.n % 2]

    def line(self, text, x_off=0, font="tiro", size=BODY, color=(0, 0, 0)):
        self.page.insert_text((self.left + x_off, self.y), text, fontsize=size, fontname=font, color=color)
        self.y += LEAD

    def para(self, text, cont_folio=None, cont_head=None, first_indent=True):
        for i, ln in enumerate(wrap(text)):
            if self.y > 585:
                self.new_page(cont_folio, cont_head)
            self.line(ln, x_off=9 if (i == 0 and first_indent) else 0)
        self.y += 4.5

    def chapter_opener(self, title, author, warning):
        self.new_page()
        self.page.insert_text((self.left, 150), title, fontsize=26, fontname="tibo")
        self.page.insert_text((self.left, 185), f"By: {author}", fontsize=16, fontname="tiit")
        self.page.insert_text((self.left, 300), "Trigger Warnings:", fontsize=13, fontname="tiro")
        self.page.insert_text((self.left, 318), warning, fontsize=11, fontname="tiit")
        # an invented "rating" stamp: grey vector shapes (becomes an adaptive SVG)
        x, y = self.left + 120, 380
        self.page.draw_rect(pymupdf.Rect(x, y, x + 70, y + 70), color=(0.1, 0.1, 0.1), fill=(1, 1, 1), width=4)
        self.page.draw_circle((x + 35, y + 35), 22, color=None, fill=(0.15, 0.15, 0.15))
        self.page.draw_circle((x + 35, y + 35), 10, color=None, fill=(0.6, 0.6, 0.6))
        if "Signals" in title:
            # a coloured ornament: stays a picture
            self.page.draw_circle((x + 160, y + 35), 18, color=None, fill=(0.8, 0.2, 0.1))

    def bubble(self, label, text, outgoing):
        x0 = 200 if outgoing else self.left
        lab_x = 360 if outgoing else self.left
        self.page.insert_text((lab_x, self.y), label, fontsize=8, fontname="helv", color=(0.4, 0.4, 0.4))
        self.y += 6
        rect = pymupdf.Rect(x0, self.y, x0 + 170, self.y + 24)
        fill = (0.3, 0.3, 0.3) if outgoing else (0.92, 0.92, 0.92)
        self.page.draw_rect(rect, color=None, fill=fill)
        self.page.insert_text((x0 + 8, self.y + 15), text, fontsize=10, fontname="helv",
                              color=(1, 1, 1) if outgoing else (0, 0, 0))
        self.y += 40


def make(path):
    b = Book()
    # 1 title page
    b.new_page()
    b.page.insert_text((80, 250), "The Quiet Harbour", fontsize=30, fontname="tibo")
    # 2 copyright
    b.new_page()
    for t in ["Copyright © 2026 by Example Press", "All rights reserved.", "",
              "ISBN: 978-0-00-000000-0", "", "Example Press", "1 Sample Street", "Nowhere"]:
        if t:
            b.page.insert_text((b.left, b.y), t, fontsize=9, fontname="tiit")
        b.y += 13 if t else 10
    # 3 contents
    b.new_page()
    b.page.insert_text((b.left, 80), "Contents", fontsize=26, fontname="tibo")
    b.y = 130
    for t, p in (("The Keeper", "1"), ("Signals", "5")):
        b.line(f"{t} {'.' * 60} {p}")
    # 4 chapter 1 opener (unnumbered, prints as 1)
    b.chapter_opener("The Keeper", "Ada Example", "Isolation, Storms")
    # 5.. chapter 1 body
    b.new_page(2, "The Keeper")
    b.para(FILLER * 2, 3, "The Quiet Harbour")
    b.para("She said the word " + "out loud" + " and it sounded strange in the empty room. " + FILLER,
           3, "The Quiet Harbour")
    # italic line
    b.page.insert_text((b.left + 9, b.y), "Nobody answered.", fontsize=BODY, fontname="tiit")
    b.y += LEAD + 4.5
    # printed scene break
    b.page.insert_text((b.left + 150, b.y + 4), "* * *", fontsize=16, fontname="tibo")
    b.y += 30
    b.para(FILLER * 3, 3, "The Quiet Harbour")   # crosses into the next page
    # screen text
    b.y += 6
    if b.y > 540:
        b.new_page(4, "The Keeper")
    for t in ["SYSTEM CHECK: lamp rotation nominal.", "Next service in 14 days."]:
        b.page.insert_text((b.left, b.y), t, fontsize=9, fontname="cour")
        b.y += LEAD
    b.y += 6
    b.para(FILLER, 4, "The Keeper")
    # blank-space scene break (large gap)
    b.y += 30
    b.para("Morning came grey and quiet. " + FILLER, 4, "The Keeper")
    # chapter 2
    b.chapter_opener("Signals", "Ben Example", "Loneliness")
    b.new_page(6, "Signals")
    b.para("The phone lit up on the table. " + FILLER, 7, "The Quiet Harbour")
    b.bubble("Mara:", "Are you still out at the light?", outgoing=False)
    b.bubble("Me:", "Yes. Storm coming in tonight.", outgoing=True)
    b.para("He put the phone face down and looked at the sea. " + FILLER, 7, "The Quiet Harbour")
    for t in ["From: Harbour Office <office@example.org>", "Sent: Monday, 9:02 am", "To: Keeper",
              "Subject: Lamp schedule"]:
        b.line(t)
    b.y += 9
    b.line("The new schedule starts next week. Please confirm that the")
    b.line("lamp has been serviced before Friday.")
    b.y += 9
    b.line("Sam Example")
    b.line("Harbour Office")
    b.y += 9
    b.para("He did not reply. " + FILLER, 7, "The Quiet Harbour")
    b.doc.save(path)
    return path


if __name__ == "__main__":
    make(sys.argv[1] if len(sys.argv) > 1 else "sample.pdf")
