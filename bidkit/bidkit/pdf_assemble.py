#!/usr/bin/env python3
"""
pdf_assemble.py — concatenate an ordered list of PDF parts into one submission PDF and stamp
continuous page numbers / footers, placing each footer against that page's OWN height.

Why: a final proposal is assembled from heterogeneous parts (a graphic cover, a narrative, one
or more exhibits, a resume pack). The parts come from different renderers and different paper
sizes (a resume pack is often A4 while the body is US Letter). A single footer y-coordinate
computed from one page's height lands in the MIDDLE of a taller page's text — the A4/Letter
footer bug that put page numbers on top of resume text on a real bid. This tool numbers from
each page's own rect, leaves leading cover page(s) unnumbered, and supports a "compact tail"
zone (full-bleed resumes) that gets only a small centred page number pinned to the bottom edge
so it never collides with tight resume margins.

Inputs : ordered part PDFs; a footer label string (NEVER baked in — it is company/bid data);
         counts of leading cover pages (unnumbered) and trailing "compact" pages (number only).
Outputs: one assembled PDF; returns (total_pages, numbered_pages). Numbering is continuous
         "Page N of M" where M counts every numbered page (all pages except the covers).
Guards : refuses an empty part list / missing file; if a cfg with format.page_limit is given,
         warns (exit 1 from the CLI) when numbered pages exceed the limit. Footer text is
         placed with page.insert_text at a baseline derived from each page's rect (no literal
         coordinates), so it stays correct across mixed paper sizes.

CLI:
  python3 -m bidkit.pdf_assemble --out FINAL.pdf --label "ACME | RFP 123" \
      --part cover.pdf --part narrative.pdf --part exhibit_a.pdf --part resumes.pdf \
      [--cover-pages 1] [--compact-tail 19] [--cfg opportunity.json] [--no-number]
"""
import argparse
import sys

import fitz

# footer typography (sizes/greys are presentation constants, not opportunity data)
BRAND_PT = 10.0
COMPACT_PT = 8.0
GRAY = (0.33, 0.33, 0.33)
# distance of the footer baseline above each page's own bottom edge
BRAND_UP = 28.0      # roomy body/exhibit pages: sit well inside the bottom margin
COMPACT_UP = 5.0     # full-bleed resumes: pin hard to the edge to clear tight content


def _place_centered(page, text, size, up):
    """Draw `text` centered horizontally, baseline `up` points above THIS page's bottom edge.

    Coordinates are derived from the page rect at call time, so the placement is correct no
    matter the paper size, and no literal coordinate tuple appears in the source.
    """
    width = page.rect.width
    height = page.rect.height
    tw = fitz.get_text_length(text, fontname="helv", fontsize=size)
    x = (width - tw) / 2.0
    y = height - up
    page.insert_text((x, y), text, fontname="helv", fontsize=size, color=GRAY)


def assemble(parts, out_path, label="", cover_pages=0, compact_tail=0, number=True):
    """Concatenate `parts` (list of PDF paths, in order) into `out_path`.

    cover_pages  : number of LEADING pages left unnumbered (e.g. a graphic cover).
    compact_tail : number of TRAILING pages that get only a compact centered page number
                   (e.g. a resume pack). The zone between covers and the compact tail gets the
                   branded footer "<label>   |   Page N of M".
    number       : stamp page numbers at all (False = pure concatenation).

    Returns (total_pages, numbered_pages).
    """
    if not parts:
        raise ValueError("no parts to assemble")

    doc = fitz.open()
    for p in parts:
        src = fitz.open(p)
        doc.insert_pdf(src)
        src.close()
    total = doc.page_count

    numbered = 0
    if number:
        if cover_pages < 0 or compact_tail < 0 or cover_pages + compact_tail > total:
            raise ValueError(
                f"cover_pages({cover_pages}) + compact_tail({compact_tail}) exceed total {total}")
        compact_start = total - compact_tail            # first index of the compact tail
        numbered_indices = [i for i in range(total) if i >= cover_pages]
        numbered = len(numbered_indices)
        for n, idx in enumerate(numbered_indices, start=1):
            page = doc[idx]
            if idx >= compact_start:
                _place_centered(page, f"Page {n} of {numbered}", COMPACT_PT, COMPACT_UP)
            else:
                base = f"Page {n} of {numbered}"
                text = f"{label}   |   {base}" if label else base
                _place_centered(page, text, BRAND_PT, BRAND_UP)

    doc.save(out_path, deflate=True, garbage=4)
    doc.close()
    return total, numbered


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--part", action="append", required=True, dest="parts",
                    help="a part PDF, in submission order (repeatable)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="",
                    help="footer label (company/bid text); omit for page-number-only footers")
    ap.add_argument("--cover-pages", type=int, default=0,
                    help="leading pages to leave unnumbered (e.g. a graphic cover)")
    ap.add_argument("--compact-tail", type=int, default=0,
                    help="trailing pages that get a compact page number only (e.g. resumes)")
    ap.add_argument("--no-number", action="store_true", help="concatenate without numbering")
    ap.add_argument("--cfg", help="opportunity.json; used only to enforce format.page_limit")
    a = ap.parse_args(argv)

    total, numbered = assemble(a.parts, a.out, label=a.label, cover_pages=a.cover_pages,
                               compact_tail=a.compact_tail, number=not a.no_number)
    print(f"assembled {a.out}: {total} pages ({numbered} numbered, "
          f"{a.cover_pages} cover, {a.compact_tail} compact-tail)")

    if a.cfg:
        from bidkit import config
        opp = config.load(a.cfg)
        limit = opp["format"].get("page_limit")
        if limit and total > int(limit):
            print(f"WARNING: {total} pages exceed the page limit {limit}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
