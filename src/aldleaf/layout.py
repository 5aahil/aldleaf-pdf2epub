"""Turn the lines of a page range into semantic blocks using the confirmed style map."""
import re

from .text import (TERMINAL, append_line, is_marker, runs_text, strip_runs)

EMAIL_HDR = re.compile(r"^(From|Sent|To|Cc|CC|Bcc|Subject|Date):")
WARN_HDR = re.compile(r"^(trigger|content)\s+warnings?:?$", re.I)
BYLINE = re.compile(r"^\s*by[:\s]\s*\S", re.I)
SYMBOLS = set("*#~•·◆◇❖❧☙⁂§°+=_-—–. ")
LIST_RE = re.compile(r"^\s*(?:([•·◦▪‣●○■□–-])|(\(?\d{1,3}[.)]|\(?[a-z][.)]))\s+\S")
NOTE_RE = re.compile(r"^\s*([\d]{1,3}|[*†‡§¶]{1,3})[.)]?\s+")


class Block:
    def __init__(self, kind, **kw):
        self.kind = kind
        self.__dict__.update(kw)

    def __repr__(self):
        return f"<Block {self.kind}>"


def line_runs(line, in_mono=False):
    runs = []
    for s in line.spans:
        st = set()
        if s.italic:
            st.add("i")
        if s.bold:
            st.add("b")
        if s.mono and not in_mono:
            st.add("samp")
        if s.sup:
            st.add("sup")
        runs.append((s.t, frozenset(st)))
    return runs


def is_forced_break(prev, nxt, wrap, short_line):
    """Was `prev` ended on purpose (signature, list item, short reply) rather than
    wrapped by the layout? The next word must have fitted on it, and it must end a
    sentence or be clearly short. Works for justified and ragged-right text."""
    pt, nt = prev.text.rstrip(), nxt.text.strip()
    if not pt or not nt or wrap <= 0:
        return False
    first = nt.split(" ")[0]
    cw = max(prev.width / max(len(pt.strip()), 1), nxt.width / max(len(nt), 1))
    if prev.width + cw * (len(first) + 1) >= wrap * 0.98:
        return False
    return prev.width < wrap * short_line or pt.endswith(TERMINAL)


def continues_at_page_top(prev_line, prev_text, wrap):
    """At a page break inside a block without first-line indents (emails, screen
    text): the paragraph carries on unless the last line ended a sentence AND
    stopped clearly short of the full width."""
    if prev_line is None:
        return False
    if not prev_text.rstrip().endswith(TERMINAL):
        return True
    return prev_line.width >= wrap * 0.85


class Layout:
    def __init__(self, pages, config, dh, stats):
        self.pages = pages
        self.cfg = config
        self.geo = config["geometry"]
        self.opt = config["options"]
        self.role_of = {s["style"]: s["role"] for s in config["styles"]}
        self.dh = dh
        self.stats = stats
        for k in ("forced_breaks", "space_breaks", "joined_returns", "figures"):
            stats.setdefault(k, 0)

    # ------------------------------------------------------------ helpers
    def role(self, line):
        return self.role_of.get(line.key, "body")

    def margin(self, pg):
        body = [round(l.x0) for l in pg.lines if self.role(l) == "body"]
        default = self.geo["margin_odd"] if pg.n % 2 else self.geo["margin_even"]
        if len(body) < 3:
            return default
        m = min(set(body), key=lambda v: (-body.count(v), v))
        return m if abs(m - default) < self.geo.get("indent", 0) + 4 or m < default else default

    def measured_wrap(self, pages, roles, cond=lambda l: True):
        """Widest line the layout wrapped (followed by another line of the same
        block): the real text width, measured from this book."""
        ws = []
        for pg in pages:
            L = [l for l in pg.lines if self.role(l) in roles and cond(l)]
            for a, b in zip(L, L[1:]):
                if 0 < b.y0 - a.y0 < self.geo["leading"] * 1.15:
                    ws.append(a.width)
        return max(ws) if ws else self.geo["text_width"]

    def bubble_of(self, pg, line):
        for r, lum in pg.fills:
            if r.height < 400 and r.x0 - 2 <= line.x0 and line.x1 <= r.x1 + 2 and r.y0 - 2 <= line.y0 and line.y1 <= r.y1 + 2:
                return r, lum
        return None, None

    def art_regions(self, pg):
        """Vector artwork worth keeping (badges, logos, ornaments), as rectangles."""
        top, bottom = self.geo["body_top"], self.geo["body_bottom"]
        chat_rects = set()
        for l in pg.lines:
            r, _ = self.bubble_of(pg, l)
            if r is not None:
                chat_rects.add((round(r.x0), round(r.y0), round(r.x1), round(r.y1)))
        rects = []
        for d in pg.drawings:
            r = d.get("rect")
            if r is None or r.width < 1.5 or r.height < 1.5:
                continue  # hairlines and rules
            if r.width > pg.width * 0.9 and r.height > pg.height * 0.9:
                continue  # page background
            if (round(r.x0), round(r.y0), round(r.x1), round(r.y1)) in chat_rects:
                continue
            if any(rr.contains(r) for rr, lum in pg.fills if (round(rr.x0), round(rr.y0), round(rr.x1), round(rr.y1)) in chat_rects):
                continue
            if r.y1 < top - 4 or r.y0 > bottom + 4:
                continue  # running head/foot decoration
            rects.append(r)
        # cluster nearby shapes
        clusters = []
        for r in rects:
            for c in clusters:
                cc = c[0]
                if (r.x0 < cc.x1 + 12 and cc.x0 < r.x1 + 12 and r.y0 < cc.y1 + 12 and cc.y0 < r.y1 + 12):
                    c[0] = cc | r
                    c[1] += 1
                    break
            else:
                clusters.append([r, 1])
        out = [c[0] for c in clusters if c[0].width >= 16 and c[0].height >= 16]
        out += [r for r in pg.images]
        return out

    # ------------------------------------------------------------ main
    def blocks(self, first, last, opening=False):
        rng = self.pages[first - 1:last]
        L = self.geo["leading"]
        new_para_gap = L * 1.12 if self.geo["paragraph_gap"] > L * 1.08 else L * 1.5
        indent_min = max(3.0, self.geo["indent"] * 0.6) if self.geo["indent"] else 999
        short = self.opt.get("short_line", 0.75)
        scene_gap = self.opt.get("scene_break_gap", L * 2)
        col_wrap = self.measured_wrap(rng, ("body", "email", "blockquote"))
        mono_wrap = self.measured_wrap(rng, ("screen",))
        chat_wrap = {
            "me": self.measured_wrap(rng, ("chat",), lambda l: l.light),
            "them": self.measured_wrap(rng, ("chat",), lambda l: not l.light),
        }

        poetry = self.opt.get("book_kind") == "poetry"
        spaced = self.opt.get("paragraph_style") == "spaced"
        blocks, cur, prev = [], None, None
        in_opening = opening
        drop = None            # pending drop cap: (letter runs, bottom y)
        for pg in rng:
            # keep the reading order of lines (columns!); slot artwork in by position
            events = [("line", l.y0, l) for l in pg.lines]
            for r in sorted(self.art_regions(pg), key=lambda r: r.y0):
                at = next((i for i, e in enumerate(events) if e[0] == "line" and e[1] > r.y0), len(events))
                events.insert(at, ("art", r.y0, r))
            if not events:
                if pg.label:
                    blocks.append(Block("marker", runs=[("", ("PB", pg.label))]))
                continue
            margin = self.margin(pg)
            page_top = True
            pending = ("PB", pg.label) if (pg.label and self.opt.get("page_list", True)) else None

            for kind, _y, obj in events:
                if kind == "art":
                    if pending:
                        blocks.append(Block("marker", runs=[("", pending)]))
                        pending = None
                    blocks.append(Block("figure", page=pg.n, rect=obj))
                    self.stats["figures"] += 1
                    cur = None
                    continue
                ln = obj
                role = self.role(ln)
                t = ln.text.strip()
                gap = (ln.y0 - prev.y0) if (prev is not None and not page_top) else None
                indent = ln.x0 - margin
                runs = line_runs(ln, in_mono=(role == "screen"))
                if pending:
                    runs = [("", pending)] + runs
                    pending = None

                # ---- section opening material (title page of a chapter)
                if role == "heading" and pg.n == first:
                    mk = [r for r in runs if is_marker(r)]
                    if mk:
                        blocks.append(Block("marker", runs=mk))
                    prev, page_top = ln, False
                    continue
                if role == "heading":      # a later heading inside a grouped section
                    if cur is not None and cur.kind == "h2" and gap is not None and gap < L * 2.5:
                        append_line(cur.runs, runs, self.dh)
                    else:
                        cur = Block("h2", runs=runs)
                        blocks.append(cur)
                    prev, page_top = ln, False
                    continue
                if in_opening and re.match(r"^(chapter|part|book|act|section)\s+[\w-]+$", t, re.I):
                    mk = [r for r in runs if is_marker(r)]      # part of the section title
                    if mk:
                        blocks.append(Block("marker", runs=mk))
                    prev, page_top = ln, False
                    continue
                if role == "dropcap":
                    drop = (runs, ln.y1)
                    prev, page_top = ln, False
                    continue
                if role == "footnote":
                    m = NOTE_RE.match(t)
                    if m or cur is None or cur.kind != "fnote":
                        num = m.group(1) if m else ""
                        r2 = list(runs)
                        if m:   # drop the printed number; the note gets a back-link instead
                            cut = len(m.group(0))
                            for j, (tx, st) in enumerate(r2):
                                if is_marker((tx, st)):
                                    continue
                                if cut <= 0:
                                    break
                                take = min(cut, len(tx))
                                r2[j] = (tx[take:], st)
                                cut -= take
                        cur = Block("fnote", num=num, runs=r2)
                        blocks.append(cur)
                    else:
                        append_line(cur.runs, runs, self.dh)
                    prev, page_top = ln, False
                    continue
                if role == "subheading":
                    cur = Block("h2", runs=runs)
                    blocks.append(cur)
                    prev, page_top = ln, False
                    continue
                if in_opening and BYLINE.match(t) and len(t) < 70:
                    mk = [r for r in runs if is_marker(r)]
                    if mk:
                        blocks.append(Block("marker", runs=mk))
                    prev, page_top = ln, False
                    continue
                if in_opening and WARN_HDR.match(t):
                    cur = Block("cw", head=runs, runs=[])
                    blocks.append(cur)
                    prev, page_top = ln, False
                    continue
                if in_opening and role in ("note", "blockquote", "caption") or (in_opening and cur is not None and cur.kind == "cw" and role != "body"):
                    if cur is not None and cur.kind == "cw":
                        append_line(cur.runs, runs, self.dh)
                    elif cur is not None and cur.kind == "note" and gap is not None and gap < new_para_gap * 1.05:
                        append_line(cur.runs, runs, self.dh)
                    else:
                        cur = Block("note", runs=list(runs))
                        blocks.append(cur)
                    prev, page_top = ln, False
                    continue
                if role == "body":
                    in_opening = False

                # ---- email headers can be set in any text style
                if role in ("body", "blockquote", "email") and indent < 2 and EMAIL_HDR.match(t) and (
                        t.startswith("From:") or (cur is not None and cur.kind == "email" and cur.in_header)):
                    role = "email_hdr"

                if role == "ignore":
                    prev, page_top = ln, False
                    continue

                if role == "scene_break" or (t and set(t) <= SYMBOLS and len(t) <= 12 and abs(ln.cx - (margin + col_wrap / 2)) < 40):
                    mk = [r for r in runs if is_marker(r)]
                    if mk:
                        blocks.append(Block("marker", runs=mk))
                    cur = Block("hr", glyph=re.sub(r"\s+", " ", t))   # the author's own marker
                    blocks.append(cur)

                elif role == "email_hdr":
                    if cur is None or cur.kind != "email" or t.startswith("From:"):
                        cur = Block("email", header=[], paras=[], in_header=True, last=None)
                        blocks.append(cur)
                    cur.header.append(list(runs))
                    cur.last = ln

                elif cur is not None and cur.kind == "email" and role in ("body", "email", "blockquote") and indent < 3:
                    if cur.in_header and cur.header and gap is not None and gap < L * 1.12:
                        append_line(cur.header[-1], runs, self.dh)      # wrapped header line
                    else:
                        cur.in_header = False
                        if not cur.paras or (gap is not None and gap > new_para_gap):
                            cur.paras.append(list(runs))
                        elif page_top:
                            if continues_at_page_top(cur.last, runs_text(cur.paras[-1]), col_wrap):
                                append_line(cur.paras[-1], runs, self.dh)
                            else:
                                cur.paras.append(list(runs))
                        else:
                            fb = is_forced_break(prev, ln, col_wrap, short)
                            self.stats["forced_breaks"] += fb
                            append_line(cur.paras[-1], runs, self.dh, forced_break=fb)
                    cur.last = ln

                elif role == "screen":
                    centered = indent > 20 and abs(ln.cx - (margin + col_wrap / 2)) < 30
                    cont = cur is not None and cur.kind == "screen" and (
                        (gap is not None and gap < L * 1.12) or
                        (page_top and continues_at_page_top(cur.last, runs_text(cur.runs), mono_wrap)))
                    if cont:
                        fb = (not page_top) and is_forced_break(prev, ln, mono_wrap, short)
                        self.stats["forced_breaks"] += fb
                        append_line(cur.runs, runs, self.dh, forced_break=fb)
                    else:
                        cur = Block("screen", runs=list(runs), center=centered)
                        blocks.append(cur)
                    cur.last = ln

                elif role == "chat_label":
                    side = "me" if ln.x0 > pg.width * 0.45 else "them"
                    cur = Block("chat", label=strip_runs(runs), side=side, bubbles=[], bubble_rects=[])
                    blocks.append(cur)

                elif role == "chat":
                    rect, lum = self.bubble_of(pg, ln)
                    if ln.light or (lum is not None and lum < 0.6):
                        side = "me"
                    elif rect is None and ln.cx > pg.width * 0.6:
                        side = "me"
                    else:
                        side = "them"
                    if cur is not None and cur.kind == "chat" and cur.side == side:
                        same_bubble = cur.bubbles and (
                            (rect is not None and cur.bubble_rects and cur.bubble_rects[-1] == rect) or
                            (rect is None and gap is not None and gap < L * 1.12))
                        if same_bubble:
                            wrap = (rect.width - 2 * max(0.0, ln.x0 - rect.x0)) if rect is not None else chat_wrap[side]
                            fb = is_forced_break(prev, ln, wrap, short)
                            self.stats["forced_breaks"] += fb
                            append_line(cur.bubbles[-1], runs, self.dh, forced_break=fb)
                        else:
                            cur.bubbles.append(list(runs))
                            cur.bubble_rects.append(rect)
                    else:
                        cur = Block("chat", label=None, side=side, bubbles=[list(runs)], bubble_rects=[rect])
                        blocks.append(cur)

                elif role in ("blockquote", "email", "note") and not (cur is not None and cur.kind == "p" and page_top):
                    if cur is not None and cur.kind == "quote" and (
                            (gap is not None and gap < new_para_gap) or
                            (page_top and continues_at_page_top(cur.last, runs_text(cur.paras[-1]), col_wrap))):
                        fb = (not page_top) and is_forced_break(prev, ln, col_wrap, short)
                        self.stats["forced_breaks"] += fb
                        append_line(cur.paras[-1], runs, self.dh, forced_break=fb)
                    elif cur is not None and cur.kind == "quote" and gap is not None and gap < new_para_gap * 2:
                        cur.paras.append(list(runs))
                    else:
                        cur = Block("quote", paras=[list(runs)])
                        blocks.append(cur)
                    cur.last = ln

                elif role == "caption":
                    cur = Block("caption", runs=list(runs))
                    blocks.append(cur)

                else:  # body text (and anything unassigned)
                    centered = indent > 40 and abs(ln.cx - (margin + col_wrap / 2)) < 25
                    if drop is not None:
                        # drop cap: glue the big letter to the first word; lines beside it are not indents
                        lr, dbottom = drop
                        letters = [(tx.strip(), frozenset()) for tx, st in lr if not is_marker((tx, st))]
                        runs = [r for r in runs if is_marker(r)] + letters + [r for r in runs if not is_marker(r)]
                        drop = None
                        cur = Block("p", runs=list(runs), indent=False, center=False, last=ln, dropcap=True)
                        blocks.append(cur)
                        cur.drop_bottom = dbottom
                        prev, page_top = ln, False
                        continue
                    beside_drop = (cur is not None and cur.kind == "p" and getattr(cur, "dropcap", False)
                                   and ln.y0 < getattr(cur, "drop_bottom", 0) + 2)
                    m_list = LIST_RE.match(t)
                    is_new = True
                    if beside_drop:
                        is_new = False
                    elif cur is not None and cur.kind in ("p", "li") and not getattr(cur, "center", False):
                        if page_top:
                            if spaced or cur.kind == "li":
                                is_new = not continues_at_page_top(getattr(cur, "last", None), runs_text(cur.runs), col_wrap)
                            else:
                                is_new = indent >= indent_min
                        elif gap is not None and gap < new_para_gap and (indent < indent_min or cur.kind == "li"):
                            is_new = False
                        if m_list and not page_top:
                            is_new = True
                    if poetry and not is_new and cur is not None and cur.kind == "p":
                        append_line(cur.runs, runs, self.dh, forced_break=True)   # verse keeps its lines
                        cur.last = ln
                    elif m_list and is_new:
                        cur = Block("li", runs=list(runs), ordered=bool(m_list.group(2)), last=ln,
                                    marker=(m_list.group(1) or m_list.group(2)))
                        blocks.append(cur)
                    elif not is_new:
                        append_line(cur.runs, runs, self.dh)
                        cur.last = ln
                    else:
                        prev_txt = runs_text(cur.runs).rstrip() if (cur is not None and cur.kind == "p") else ""
                        if (cur is not None and cur.kind == "p" and prev_txt and not prev_txt.endswith(TERMINAL)
                                and re.match(r"[a-z]", t) and not centered and not poetry):
                            append_line(cur.runs, runs, self.dh)   # stray paragraph return mid-sentence
                            self.stats["joined_returns"] += 1
                        else:
                            if cur is not None and cur.kind == "p" and gap is not None and gap >= scene_gap:
                                blocks.append(Block("hr", space=True))
                                self.stats["space_breaks"] += 1
                            cur = Block("p", runs=list(runs), indent=indent >= indent_min, center=centered,
                                        last=ln, verse=poetry)
                            blocks.append(cur)
                prev = ln
                page_top = False
            if pending:
                blocks.append(Block("marker", runs=[("", pending)]))
        return blocks
