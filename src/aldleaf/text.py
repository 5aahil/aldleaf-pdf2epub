"""Text helpers: normalisation, inline runs, line joining, roman numerals."""
import html
import re
import unicodedata

from .i18n import joins_without_space, repair_text_layer

ROMAN_RE = re.compile(r"^(?=[ivxlcdm]+$)m{0,3}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$", re.I)
TERMINAL = tuple('.!?…:;"”’\')*]。！？．」』）】〉》।॥၊။።')
WORD_RE = re.compile(r"[^\W_]+(?:[’'][^\W_]+)*")


def esc(t):
    return html.escape(t, quote=False)


def esc_attr(t):
    return html.escape(t, quote=True)


def norm(t):
    """Normalise PDF text: NFC, ligatures, soft hyphens, exotic spaces."""
    t = unicodedata.normalize("NFC", t)
    t = repair_text_layer(t)
    t = t.replace("­", "")
    for a, b in (("ﬀ", "ff"), ("ﬁ", "fi"), ("ﬂ", "fl"), ("ﬃ", "ffi"), ("ﬄ", "ffl")):
        t = t.replace(a, b)
    t = re.sub(r"[ -   　\t ]", " ", t)
    t = t.replace("​", "").replace("‌", "").replace("﻿", "")
    return t


def words(t):
    return WORD_RE.findall(t.replace("-", " ").replace("—", " ").replace("–", " "))


# ---------------------------------------------------------------- roman numerals
_ROMAN_VALS = [(1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
               (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]


def is_folio(t):
    t = t.strip()
    return bool(t) and (t.isdigit() or bool(ROMAN_RE.match(t)))


def roman_to_int(s):
    vals = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    s = s.lower()
    total = 0
    for a, b in zip(s, s[1:] + " "):
        v = vals[a]
        total += -v if b != " " and vals.get(b, 0) > v else v
    return total


def int_to_roman(n, upper=False):
    out = ""
    for v, r in _ROMAN_VALS:
        while n >= v:
            out += r
            n -= v
    return out.upper() if upper else out


def shift_label(label, delta):
    """'5' + -2 -> '3'; 'ix' + -2 -> 'vii'. None if it would drop below 1."""
    if label.isdigit():
        v = int(label) + delta
        return str(v) if v >= 1 else None
    v = roman_to_int(label) + delta
    return int_to_roman(v, label.isupper()) if v >= 1 else None


# ---------------------------------------------------------------- inline runs
# A run is (text, style). style is a frozenset of {"i","b","samp","sup"},
# or ("PB", label) for a print page marker.

def is_marker(run):
    return isinstance(run[1], tuple)


def runs_text(runs):
    return "".join(t for t, st in runs if not isinstance(st, tuple))


def strip_runs(runs):
    runs = list(runs)
    while runs and not is_marker(runs[0]) and runs[0][0].strip() == "":
        runs.pop(0)
    while runs and not is_marker(runs[-1]) and runs[-1][0].strip() == "":
        runs.pop()
    for idx in (0, -1):
        if runs and not is_marker(runs[idx]):
            t = runs[idx][0].lstrip() if idx == 0 else runs[idx][0].rstrip()
            runs[idx] = (t, runs[idx][1])
    return runs


def pagebreak_html(label):
    if not label:
        return ""
    return (f'<span epub:type="pagebreak" role="doc-pagebreak" id="page-{esc_attr(label)}" '
            f'aria-label="Page {esc_attr(label)}"></span>')


def render_runs(runs):
    """Runs -> XHTML. Merges equal styles, keeps spaces outside tags, \\n -> <br/>."""
    out, cur_t, cur_st = [], "", None

    def flush():
        nonlocal cur_t, cur_st
        if cur_t:
            t = esc(re.sub(r" {2,}", " ", cur_t))
            st = cur_st or frozenset()
            lead = t[: len(t) - len(t.lstrip(" "))]
            trail = t[len(t.rstrip(" ")):]
            core = t.strip(" ")
            if core:
                if "sup" in st:
                    core = f"<sup>{core}</sup>"
                if "i" in st:
                    core = f"<i>{core}</i>"
                if "b" in st:
                    core = f"<b>{core}</b>"
                if "samp" in st:
                    core = f"<samp>{core}</samp>"
            out.append(lead + core + trail)
        cur_t, cur_st = "", None

    for t, st in runs:
        if isinstance(st, tuple):
            flush()
            out.append(pagebreak_html(st[1]))
            continue
        if cur_st is None:
            cur_st = st
        if st != cur_st and t.strip() != "":
            flush()
            cur_st = st
        cur_t += t
    flush()
    return "".join(out).strip().replace("\n", "<br/>")


class Dehyphenator:
    """Decides whether a hyphen at a line end is a layout hyphen (drop it) or part
    of the word (keep it). Only drops hyphens if the edition was auto-hyphenated."""

    def __init__(self, auto_hyphenated):
        self.auto = auto_hyphenated
        self.words = set()
        self.hyph = set()
        self.inner = set()     # Korean words seen whole, inside a line
        # True when the PDF writes the space at the end of a line that ends a word
        # (browsers do). Then a line without one broke inside a word.
        self.line_end_spaces = False

    def learn(self, text):
        for w in re.findall(r"[^\W\d_]+(?:-[^\W\d_]+)+", text):
            self.hyph.add(w.lower())
        for w in re.findall(r"[^\W\d_]+", text):
            self.words.add(w.lower())
        inner = text.split()[1:-1]   # words inside a line are never cut by a line break
        for w in inner:
            m = _HANGUL_WORD.fullmatch(w.strip(".,!?;:\"'()[]“”‘’…"))
            if m:
                self.inner.add(m.group(0))

    def drop(self, a, b):
        if not self.auto:
            return False
        joined, hy = (a + b).lower(), (a + "-" + b).lower()
        if hy in self.hyph:
            return False
        return joined in self.words or len(a) >= 2


_KO_PARTICLES = {"를", "을", "는", "은", "의", "와", "과", "로", "으로", "도", "에", "에서", "에게", "만",
                 "부터", "까지", "처럼", "보다", "께서", "한테", "라고", "이라고"}
_HANGUL = re.compile(r"[\uac00-\ud7af]+$")
_HANGUL_START = re.compile(r"^[\uac00-\ud7af]+")


_HANGUL_WORD = re.compile(r"[\uac00-\ud7a3]+")


def _is_hangul(c):
    return "\uac00" <= c <= "\ud7a3"


def _split_hangul(prev, nxt, dh):
    """Korean lines may break inside a word (between syllables). Decide from the
    book's own vocabulary and from what Korean grammar allows."""
    a, b = _HANGUL.search(prev), _HANGUL_START.match(nxt)
    if not a or not b:
        return False
    a, b = a.group(0), b.group(0)
    joined = (a + b).lower()
    rest = nxt[len(b):len(b) + 1]
    if joined in dh.inner or (not dh.inner and joined in dh.words):
        return True                # the unbroken word appears whole elsewhere
    # a particle or ending can't stand alone, so the line broke inside a word
    if b in _KO_PARTICLES and (not rest or rest.isspace() or rest in ".,!?;:"):
        return True
    if b == "지" and re.match(r"\s+(않|못|말)", nxt[len(b):]):   # '-지 않다', '-지 못하다'
        return True
    if b[0] in _KO_BOUND:          # tense syllables never start a word
        return True
    if b == "다" and rest in ".!?":
        return True
    if not dh.inner or a in dh.inner or b in dh.inner:
        return False               # a word of its own on either side: a real space
    if len(a) >= 2 and a[-1] in _KO_CLOSING:
        return False               # the line ended on a particle that closes a word
    return True                    # neither half is a word anywhere in the book


_KO_BOUND = set("었았였렸겠셨웠")
_KO_CLOSING = set("은는을를의에도만와과")


def append_line(runs, line_runs, dh, forced_break=False):
    """Append a line's runs to a paragraph's runs, joining with a space,
    a forced line break, or a removed layout hyphen."""
    if not runs:
        runs.extend(line_runs)
        return
    prev_raw, nxt_raw = runs_text(runs), runs_text(line_runs)
    prev = prev_raw.rstrip()
    nxt = nxt_raw.lstrip()
    real_space = prev_raw[-1:].isspace() or nxt_raw[:1].isspace()   # Thai phrases end in a real space
    i = len(runs) - 1
    while i >= 0 and is_marker(runs[i]):
        i -= 1
    if i >= 0:
        runs[i] = (runs[i][0].rstrip(), runs[i][1])
    lr = list(line_runs)
    for j, r in enumerate(lr):
        if not is_marker(r):
            lr[j] = (r[0].lstrip(), r[1])
            break
    if forced_break:
        runs.append(("\n", frozenset()))
    elif re.search(r"[^\W\d_]-$", prev) and not prev.endswith("--") and nxt[:1].islower():
        a = re.search(r"([^\W\d_]+)-$", prev).group(1)
        b = re.match(r"([^\W\d_]+)", nxt).group(1)
        if dh is not None and dh.drop(a, b) and i >= 0:
            runs[i] = (runs[i][0][:-1], runs[i][1])
    elif prev.endswith(("—", "–", "/")) or (prev and nxt and not real_space and joins_without_space(prev[-1], nxt[0])):
        pass
    elif (prev and nxt and dh is not None and dh.line_end_spaces and not real_space
          and _is_hangul(prev[-1]) and _is_hangul(nxt[0])):
        pass
    elif prev and nxt and dh is not None and _split_hangul(prev, nxt, dh):
        pass
    else:
        runs.append((" ", runs[i][1] if i >= 0 else frozenset()))
    runs.extend(lr)
