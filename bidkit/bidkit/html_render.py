#!/usr/bin/env python3
"""
html_render.py — render a Markdown bid document to PDF through HTML + headless Chrome, for
documents with WIDE multi-column tables that the PyMuPDF renderer (pdf_render.py) lays out
poorly.

Why: pdf_render.py is the default and gives provable font/size/numbering compliance. But its
table layout is naive: on a real bid, 4- and 5-column pricing tables came out with the narrow
first column bleeding into the second and the table colliding with the following paragraph, and
`_italic_` underscores leaked as literal text. Chrome's HTML table engine (fixed column widths,
cell padding, borders, wrapping) renders those cleanly. This module is the escape hatch for
table-heavy exhibits: same Arial/1in-margin look, correct columns. Use pdf_render.py for prose;
use this for table-heavy exhibits, then verify the output with pdf_verify.py.

Inputs : markdown (a subset: ##/### headings, pipe tables, - bullets, 1. ordered, **bold**,
         _italic_/*italic*, blank-line paragraphs; HTML comments stripped); a font family name
         and page size (defaults Arial / letter, overridable or from a cfg).
Outputs: a PDF with no browser header/footer (page numbers are added later by pdf_assemble.py).
Guards : requires a Chrome/Chromium binary (discovered on PATH / common macOS + Linux
         locations, or --chrome); em-dashes in table/prose text are converted to commas to
         respect the house style; column widths adapt to the column count so labels never
         collide.

CLI:
  python3 -m bidkit.html_render <in.md> <out.pdf> [--font "Arial"] [--page-size letter|a4|legal]
        [--margin-in 1.0] [--body-pt 11] [--chrome /path/to/chrome] [--keep-html out.html]
        [--cfg opportunity.json]   # cfg supplies page_size/margin_in/body_font_pt if present
"""
import argparse
import html as _html
import os
import re
import shutil
import subprocess
import sys
import tempfile

PAGE_DIMS_IN = {"letter": "8.5in 11in", "a4": "210mm 297mm", "legal": "8.5in 14in"}

CHROME_CANDIDATES = [
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


def find_chrome(explicit=None):
    """Return a usable Chrome/Chromium binary path, or raise."""
    if explicit:
        if os.path.exists(explicit) or shutil.which(explicit):
            return explicit
        raise FileNotFoundError(f"chrome not found at {explicit}")
    for cand in CHROME_CANDIDATES:
        hit = shutil.which(cand) if "/" not in cand else (cand if os.path.exists(cand) else None)
        if hit:
            return hit
    raise FileNotFoundError(
        "no Chrome/Chromium found; pass --chrome /path/to/chrome")


# ----------------------------------------------------------------- markdown -> HTML
def _inline(text):
    """Escape, then apply **bold** and _italic_/*italic*; em-dash -> comma (house style)."""
    t = _html.escape(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<em>\1</em>", t)      # fixes leaking underscores
    t = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", t)
    t = t.replace("\u2014", ", ")
    return t


def _is_table_row(s):
    return s.startswith("|") and s.count("|") >= 2


def _col_widths(ncol):
    """Fixed column-width strategy so a narrow label column never bleeds into the next."""
    presets = {
        2: ["34%", "66%"],
        3: ["26%", "50%", "24%"],
        4: ["20%", "46%", "16%", "18%"],
        5: ["17%", "40%", "13%", "15%", "15%"],
    }
    return presets.get(ncol, [f"{100 // ncol}%"] * ncol)


def _render_table(rows):
    def cells(r):
        return [c.strip() for c in r.strip().strip("|").split("|")]
    header = cells(rows[0])
    ncol = len(header)
    body = [cells(r) for r in rows[2:]]           # rows[1] is the |---| separator
    widths = _col_widths(ncol)
    out = ["<table>",
           "<colgroup>" + "".join(f'<col style="width:{w}">' for w in widths[:ncol]) + "</colgroup>",
           "<thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in header) + "</tr></thead>",
           "<tbody>"]
    for d in body:
        d = (d + [""] * ncol)[:ncol]
        out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in d) + "</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def md_to_html_body(md):
    md = re.sub(r"<!--.*?-->", "", md, flags=re.DOTALL)
    lines = md.split("\n")
    i, n, body = 0, len(md.split("\n")), []
    while i < n:
        s = lines[i].strip()
        if not s or s == "---":
            i += 1; continue
        m1 = re.match(r"^#\s+(.*)$", s)
        m2 = re.match(r"^##\s+(.*)$", s)
        m3 = re.match(r"^###\s+(.*)$", s)
        if m1 or m2:
            body.append(f'<h1 class="section">{_inline((m1 or m2).group(1))}</h1>'); i += 1; continue
        if m3:
            body.append(f'<h2 class="sub">{_inline(m3.group(1))}</h2>'); i += 1; continue
        if _is_table_row(s):
            rows = []
            while i < n and _is_table_row(lines[i].strip()):
                rows.append(lines[i].strip()); i += 1
            if len(rows) >= 2:
                body.append(_render_table(rows))
            continue
        if s.startswith("- "):
            items = []
            while i < n and lines[i].strip().startswith("- "):
                cur = lines[i].strip()[2:]; i += 1
                while (i < n and lines[i].strip()
                       and not lines[i].strip().startswith("- ")
                       and not re.match(r"^(#|\d+\.\s|---|\|)", lines[i].strip())):
                    cur += " " + lines[i].strip(); i += 1
                items.append(cur)
            body.append("<ul>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + "</ul>"); continue
        if re.match(r"^\d+\.\s", s):
            items = []
            while i < n and re.match(r"^\d+\.\s", lines[i].strip()):
                cur = re.sub(r"^\d+\.\s", "", lines[i].strip()); i += 1
                while (i < n and lines[i].strip()
                       and not re.match(r"^(#|-\s|\d+\.\s|---|\|)", lines[i].strip())):
                    cur += " " + lines[i].strip(); i += 1
                items.append(cur)
            body.append("<ol>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + "</ol>"); continue
        para = [s]; i += 1
        while i < n and lines[i].strip() and not re.match(r"^(#|-\s|\d+\.\s|---|\|)", lines[i].strip()):
            para.append(lines[i].strip()); i += 1
        body.append(f"<p>{_inline(' '.join(para))}</p>")
    return "\n".join(body)


def build_html(md, font="Arial", page_size="letter", margin_in=1.0, body_pt=11):
    dims = PAGE_DIMS_IN.get(page_size, PAGE_DIMS_IN["letter"])
    body = md_to_html_body(md)
    css = """
      @page { size: %(dims)s; margin: %(margin).2fin; }
      html,body { margin:0; padding:0; }
      body { font-family: %(font)s, "Helvetica Neue", sans-serif; font-size: %(body).1fpt;
             line-height: 1.36; color:#1a1a1a; }
      h1.section { font-size: 14pt; font-weight:700; color:#17335c; margin: 15pt 0 7pt 0;
                   padding-bottom: 4pt; border-bottom: 2px solid #2f7fd0; break-after: avoid; }
      h1.section:first-of-type { margin-top: 0; }
      h2.sub { font-size: 11.5pt; font-weight:700; color:#17335c; margin: 11pt 0 5pt 0; break-after: avoid; }
      p { margin: 0 0 7pt 0; }
      ul, ol { margin: 0 0 7pt 0; padding-left: 22pt; }
      li { margin: 0 0 4pt 0; }
      strong { color:#14243a; } em { font-style: italic; }
      table { width: 100%%; border-collapse: collapse; table-layout: fixed; margin: 5pt 0 11pt 0;
              font-size: 9.5pt; line-height: 1.28; page-break-inside: auto; }
      th, td { border: 0.75pt solid #9aa6b4; padding: 4pt 7pt; text-align: left; vertical-align: top;
               word-wrap: break-word; overflow-wrap: break-word; }
      th { background: #e8eef6; color:#17335c; font-weight:700; }
      tr { page-break-inside: avoid; }
    """ % {"dims": dims, "margin": margin_in, "font": font, "body": float(body_pt)}
    return f"<!doctype html>\n<html><head><meta charset=\"utf-8\"><style>{css}</style></head>\n<body>\n{body}\n</body></html>"


def render(md_path, out_pdf, font="Arial", page_size="letter", margin_in=1.0, body_pt=11,
           chrome=None, keep_html=None):
    with open(md_path, encoding="utf-8") as fh:
        md = fh.read()
    doc_html = build_html(md, font=font, page_size=page_size, margin_in=margin_in, body_pt=body_pt)
    chrome_bin = find_chrome(chrome)

    if keep_html:
        html_path = keep_html
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(doc_html)
        cleanup = False
    else:
        fd, html_path = tempfile.mkstemp(suffix=".html")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(doc_html)
        cleanup = True

    out_pdf = os.path.abspath(out_pdf)
    try:
        subprocess.run(
            [chrome_bin, "--headless", "--disable-gpu", "--no-sandbox",
             "--no-pdf-header-footer", f"--print-to-pdf={out_pdf}",
             "file://" + os.path.abspath(html_path)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        if cleanup:
            try:
                os.unlink(html_path)
            except OSError:
                pass
    if not os.path.exists(out_pdf):
        raise RuntimeError("Chrome did not produce an output PDF")
    return out_pdf, doc_html.count("<table>")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("md"); ap.add_argument("out")
    ap.add_argument("--font", default="Arial")
    ap.add_argument("--page-size", default="letter", choices=list(PAGE_DIMS_IN))
    ap.add_argument("--margin-in", type=float, default=1.0)
    ap.add_argument("--body-pt", type=float, default=11.0)
    ap.add_argument("--chrome", default=None)
    ap.add_argument("--keep-html", default=None)
    ap.add_argument("--cfg", help="opportunity.json; supplies page_size/margin_in/body_font_pt")
    a = ap.parse_args(argv)

    font, page_size, margin_in, body_pt = a.font, a.page_size, a.margin_in, a.body_pt
    if a.cfg:
        from bidkit import config
        fmt = config.load(a.cfg)["format"]
        page_size = fmt.get("page_size", page_size)
        margin_in = float(fmt.get("margin_in", margin_in))
        body_pt = float(fmt.get("body_font_pt", body_pt))
        allow = fmt.get("font_family_allow") or []
        if allow:
            font = allow[0]

    out, ntables = render(a.md, a.out, font=font, page_size=page_size, margin_in=margin_in,
                          body_pt=body_pt, chrome=a.chrome, keep_html=a.keep_html)
    print(f"rendered {out} via Chrome ({ntables} table(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
