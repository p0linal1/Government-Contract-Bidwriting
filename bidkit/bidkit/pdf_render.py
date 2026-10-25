#!/usr/bin/env python3
"""
pdf_render.py — render a Markdown bid document to a format-compliant PDF with PyMuPDF and the
REAL TTF files for the required font family (no pandoc/weasyprint on the box).

Why: format compliance is scored (a prior RFP: wrong family or <10pt = 50% penalty), and the
page limit excludes cover letter / covers / tab pages / resumes / reference letters. A renderer
that numbers every page after the cover made a 17-page body look like 34 pages. This renderer:
  - uses exactly the TTFs named in config (family allowlist is then provable by pdf_verify),
  - enforces body size ≥ min, margins, and page size from config,
  - starts "Page N of M" at the first COUNTED heading (`numbered_from_heading`) and leaves
    pages inside excluded sections (`exclude_numbering_headings`) UNNUMBERED — M counts only
    numbered pages,
  - strips drafting comments (<!-- ... -->) except the control markers below,
  - writes a sidecar <out>.markers.json with page indexes per section for downstream tools.

Markdown supported: #/##/### headings, - bullets, 1. numbered lists, | tables |, **bold**,
*italic*, --- rules, paragraphs, <!-- PAGEBREAK -->, <!-- IMAGE path width -->.

CLI:
  python3 -m bidkit.pdf_render <in.md> <out.pdf> --cfg <opportunity.json>
        [--number-from "PART I"] [--exclude-numbering "Cover Letter" "Resumes" ...]
        [--no-footer] [--footer-label "RFP 00-000"]
  (--number-from / --exclude-numbering default to config format.numbered_from_heading /
   format.exclude_numbering_headings)
"""
import argparse, json, os, re, sys
import fitz
from . import config

PAGE_SIZES = {"letter": (612, 792), "a4": (595, 842), "legal": (612, 1008)}
FONT_ALIAS = {"reg": "regular", "bold": "bold", "ital": "italic", "bi": "bold_italic"}


class Renderer:
    def __init__(self, out, fonts, page_size="letter", margin_in=0.75, body_pt=11,
                 min_pt=10, footer_label=""):
        self.out = out
        self.fonts = fonts                       # {regular,bold,italic,bold_italic: path}
        self.page_w, self.page_h = PAGE_SIZES.get(page_size, PAGE_SIZES["letter"])
        self.margin = margin_in * 72.0
        self.content_w = self.page_w - 2 * self.margin
        self.body = float(body_pt)
        self.min_pt = float(min_pt)
        self.small = max(self.min_pt, 10.0)     # tables/footers never below the minimum
        self.leading = round(self.body * 1.36, 1)
        self.footer_label = footer_label
        self.doc = fitz.open()
        self.pages = []                          # list of dicts: {page, section}
        self.section = None                      # current top-level heading text
        self._font_cache = {}
        self._new_page()

    # ---------------------------------------------------------------- page mgmt
    def _new_page(self):
        page = self.doc.new_page(width=self.page_w, height=self.page_h)
        for alias, key in FONT_ALIAS.items():
            page.insert_font(fontfile=self.fonts[key], fontname="f-" + alias)
        self.page = page
        self.y = self.margin
        self.pages.append({"page": page, "section": self.section})

    def _space(self, h):
        if self.y + h > self.page_h - self.margin:
            self._new_page()

    def _fname(self, bold, ital):
        return "f-" + ("bi" if bold and ital else "bold" if bold else "ital" if ital else "reg")

    def _font_obj(self, bold, ital):
        alias = self._fname(bold, ital)[2:]
        if alias not in self._font_cache:
            self._font_cache[alias] = fitz.Font(fontfile=self.fonts[FONT_ALIAS[alias]])
        return self._font_cache[alias]

    def _wid(self, text, size, bold=False, ital=False):
        return self._font_obj(bold, ital).text_length(text, size)

    # ---------------------------------------------------------------- inline runs
    @staticmethod
    def _runs(text):
        runs, buf, bold, ital, i = [], "", False, False, 0
        while i < len(text):
            if text.startswith("**", i):
                if buf: runs.append((buf, bold, ital)); buf = ""
                bold = not bold; i += 2; continue
            if text[i] == "*":
                if buf: runs.append((buf, bold, ital)); buf = ""
                ital = not ital; i += 1; continue
            buf += text[i]; i += 1
        if buf: runs.append((buf, bold, ital))
        return runs

    def _emit_line(self, runs, size, x0):
        x = x0
        for txt, b, it in runs:
            if not txt: continue
            self.page.insert_text((x, self.y), txt, fontsize=size, fontname=self._fname(b, it),
                                  color=(0, 0, 0))
            x += self._wid(txt, size, b, it)

    # ---------------------------------------------------------------- blocks
    def paragraph(self, text, size=None, indent=0, bullet=None, gap_after=6):
        size = size or self.body
        runs = self._runs(text)
        x0 = self.margin + indent; avail = self.content_w - indent
        if bullet:
            avail -= 14; x0 += 14
        line, line_w = [], 0.0
        space_w = self._wid(" ", size)
        first = [True]

        def flush():
            nonlocal line, line_w
            self._space(self.leading)
            if bullet and first[0]:
                self.page.insert_text((self.margin + indent, self.y), bullet, fontsize=size,
                                      fontname="f-reg", color=(0, 0, 0))
            self._emit_line(line, size, x0)
            self.y += self.leading
            line, line_w = [], 0.0
            first[0] = False

        for txt, b, it in runs:
            for word in re.findall(r"\S+|\s+", txt):
                if word.isspace():
                    if line: line.append((" ", b, it)); line_w += space_w
                    continue
                ww = self._wid(word, size, b, it)
                if line_w + ww > avail and line:
                    flush()
                line.append((word, b, it)); line_w += ww
        if line: flush()
        self.y += gap_after

    def heading(self, text, level):
        clean = re.sub(r"\*", "", text).strip()
        if level == 1:
            # Section ownership rule for page numbering: a level-1 heading claims the current
            # page if nothing has been drawn on it yet (fresh page / after a PAGEBREAK);
            # otherwise the page keeps its existing section and the new section owns pages
            # from the next page break onward. Bid docs put <!-- PAGEBREAK --> before each
            # major section, so this matches real usage and keeps exclusions unambiguous.
            page_is_fresh = self.y <= self.margin + 0.5
            self.section = clean
            if page_is_fresh:
                self.pages[-1]["section"] = clean
        sizes = {1: round(self.body * 1.55), 2: round(self.body * 1.18), 3: round(self.body * 1.05, 1)}
        size = sizes.get(level, self.body)
        self.y += 8 if level <= 2 else 5
        self._space(self.leading + 6)
        self._emit_line([(clean, True, False)], size, self.margin)
        self.y += size + 3
        if level == 1:
            self.page.draw_line((self.margin, self.y - 2), (self.page_w - self.margin, self.y - 2), width=1)
            self.y += 14

    def rule(self):
        self._space(10)
        self.page.draw_line((self.margin, self.y), (self.page_w - self.margin, self.y),
                            color=(0.6, 0.6, 0.6), width=0.5)
        self.y += 10

    def image(self, path, width):
        if not os.path.exists(path):
            self.paragraph(f"[missing image: {path}]"); return
        pix = fitz.Pixmap(path)
        h = width * pix.height / max(pix.width, 1)
        self._space(h + 4)
        self.page.insert_image(fitz.Rect(self.margin, self.y, self.margin + width, self.y + h), filename=path)
        self.y += h + 4

    def table(self, rows):
        ncol = max(len(r) for r in rows)
        widths = self._col_widths(rows, ncol)
        size = self.small; lh = round(size * 1.3, 1)
        for ri, row in enumerate(rows):
            row = row + [""] * (ncol - len(row))
            bold = ri == 0
            cell_lines = [self._wrap_plain(c, widths[ci] - 8, size, bold) for ci, c in enumerate(row)]
            rh = max(len(cl) for cl in cell_lines) * lh + 4
            self._space(rh)
            x = self.margin; top = self.y
            for ci in range(ncol):
                self.page.draw_rect(fitz.Rect(x, top - 2, x + widths[ci], top - 2 + rh),
                                    color=(0.7, 0.7, 0.7), width=0.4)
                cy = top + size
                for ln in cell_lines[ci]:
                    self.page.insert_text((x + 4, cy), ln, fontsize=size,
                                          fontname="f-bold" if bold else "f-reg", color=(0, 0, 0))
                    cy += lh
                x += widths[ci]
            self.y = top - 2 + rh
        self.y += 6

    def _col_widths(self, rows, ncol):
        base = {1: [1.0], 2: [0.62, 0.38], 3: [0.30, 0.45, 0.25]}.get(ncol, [0.10, 0.45, 0.10, 0.35])
        base = (base + [1.0 / ncol] * ncol)[:ncol]
        s = sum(base)
        return [self.content_w * b / s for b in base]

    def _wrap_plain(self, text, width, size, bold):
        text = re.sub(r"\*\*|\*", "", text)
        lines, cur = [], ""
        for w in text.split():
            t = (cur + " " + w).strip()
            if self._wid(t, size, bold) > width and cur:
                lines.append(cur); cur = w
            else:
                cur = t
        if cur: lines.append(cur)
        return lines or [""]

    # ---------------------------------------------------------------- numbering
    def number_pages(self, number_from, exclude):
        """Number pages from the first page whose section matches `number_from`, skipping pages
        whose section matches any `exclude` heading. Returns list of (page_index, n, total)."""
        def match(sec, needle):
            return bool(sec) and needle.lower() in sec.lower()
        started = False; eligible = []
        for idx, info in enumerate(self.pages):
            sec = info["section"]
            if not started and (number_from is None or match(sec, number_from)):
                started = True
            if not started: continue
            if any(match(sec, ex) for ex in exclude): continue
            eligible.append(idx)
        total = len(eligible)
        fnt = self._font_obj(False, False); size = self.small
        placed = []
        for n, idx in enumerate(eligible, start=1):
            p = self.doc[idx]
            label = f"Page {n} of {total}"
            if self.footer_label:
                label = f"{self.footer_label}  |  {label}"
            w = fnt.text_length(label, size)
            # footer baseline sits inside the bottom margin band, but no lower than 0.5in
            y = self.page_h - max(self.margin * 0.62, 36)
            p.insert_text(((self.page_w - w) / 2, y), label, fontsize=size, fontname="f-reg",
                          color=(0.3, 0.3, 0.3))
            placed.append((idx, n, total))
        return placed

    def save(self):
        self.doc.save(self.out, deflate=True, garbage=3)


# -------------------------------------------------------------------- markdown parsing
CONTROL_MARKERS = ("PAGEBREAK", "IMAGE")


def strip_notes(md):
    """Remove HTML comments except recognised control markers."""
    def keep(m):
        body = m.group(1).strip()
        return m.group(0) if body.split(" ")[0] in CONTROL_MARKERS else ""
    return re.sub(r"<!--(.*?)-->", keep, md, flags=re.DOTALL)


def parse_md(md):
    lines = md.split("\n"); i = 0
    def cont(ln):
        s = ln.strip()
        return s and not re.match(r"^(#|\||- |\d+\.\s|---$|<!--)", s)
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            i += 1; continue
        m = re.match(r"^<!--\s*PAGEBREAK\s*-->$", s)
        if m: yield ("pagebreak", None); i += 1; continue
        m = re.match(r"^<!--\s*IMAGE\s+(\S+)(?:\s+(\d+))?\s*-->$", s)
        if m: yield ("image", (m.group(1), int(m.group(2) or 150))); i += 1; continue
        if s.startswith("### "): yield ("h3", s[4:]); i += 1; continue
        if s.startswith("## "): yield ("h2", s[3:]); i += 1; continue
        if s.startswith("# "): yield ("h1", s[2:]); i += 1; continue
        if s == "---": yield ("rule", None); i += 1; continue
        if s.startswith("|"):
            tbl = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = lines[i].strip().strip("|")
                if set(row) <= set("-: |"):
                    i += 1; continue
                tbl.append([c.strip() for c in row.split("|")]); i += 1
            if tbl: yield ("table", tbl)
            continue
        m = re.match(r"^(\d+)\.\s+(.*)", s)
        if m:
            text = m.group(2); i += 1
            while i < len(lines) and cont(lines[i]): text += " " + lines[i].strip(); i += 1
            yield ("num", (m.group(1), text)); continue
        if s.startswith("- ") or s.startswith("* "):
            text = s[2:]; i += 1
            while i < len(lines) and cont(lines[i]): text += " " + lines[i].strip(); i += 1
            yield ("bullet", text); continue
        text = s; i += 1
        while i < len(lines) and cont(lines[i]): text += " " + lines[i].strip(); i += 1
        yield ("para", text)


def render(md_path, out_pdf, opp, number_from=None, exclude=None, footer=True, footer_label="",
           base_dir=None):
    fmt = opp["format"]
    number_from = number_from if number_from is not None else fmt.get("numbered_from_heading")
    exclude = exclude if exclude is not None else fmt.get("exclude_numbering_headings", [])
    with open(md_path, encoding="utf-8") as fh:
        md = strip_notes(fh.read())
    r = Renderer(out_pdf, opp["fonts"], page_size=fmt.get("page_size", "letter"),
                 margin_in=float(fmt.get("margin_in", 0.75)), body_pt=fmt.get("body_font_pt", 11),
                 min_pt=fmt.get("min_font_pt", 10), footer_label=footer_label)
    base_dir = base_dir or os.path.dirname(os.path.abspath(md_path))
    for kind, payload in parse_md(md):
        if kind == "pagebreak": r._new_page()
        elif kind == "image":
            p = payload[0] if os.path.isabs(payload[0]) else os.path.join(base_dir, payload[0])
            r.image(p, payload[1])
        elif kind == "h1": r.heading(payload, 1)
        elif kind == "h2": r.heading(payload, 2)
        elif kind == "h3": r.heading(payload, 3)
        elif kind == "rule": r.rule()
        elif kind == "table": r.table(payload)
        elif kind == "num": r.paragraph(payload[1], bullet=payload[0] + ".", indent=6)
        elif kind == "bullet": r.paragraph(payload, bullet="\u2022", indent=6)
        elif kind == "para": r.paragraph(payload)
    placed = r.number_pages(number_from, exclude) if footer else []
    r.save()
    markers = {"pages": [{"index": i, "section": info["section"]} for i, info in enumerate(r.pages)],
               "numbered": [{"index": i, "n": n, "total": t} for i, n, t in placed],
               "number_from": number_from, "exclude": exclude}
    with open(re.sub(r"\.pdf$", "", out_pdf) + ".markers.json", "w", encoding="utf-8") as fh:
        json.dump(markers, fh, indent=2)
    return r.doc.page_count, placed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("md"); ap.add_argument("out")
    ap.add_argument("--cfg", required=True)
    ap.add_argument("--number-from")
    ap.add_argument("--exclude-numbering", nargs="*")
    ap.add_argument("--no-footer", action="store_true")
    ap.add_argument("--footer-label", default="")
    a = ap.parse_args(argv)
    opp = config.load(a.cfg)
    pages, placed = render(a.md, a.out, opp, number_from=a.number_from, exclude=a.exclude_numbering,
                           footer=not a.no_footer, footer_label=a.footer_label)
    total = placed[0][2] if placed else 0
    print(f"rendered {a.out}: {pages} pages, {total} numbered (limit {opp['format'].get('page_limit')})")
    if opp["format"].get("page_limit") and total > int(opp["format"]["page_limit"]):
        print("WARNING: numbered pages exceed the page limit"); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
