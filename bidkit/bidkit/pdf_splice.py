#!/usr/bin/env python3
"""
pdf_splice.py — replace the first N pages of a built PDF with a signed/scanned front, keeping
the rest of the built document, and verify the splice.

Why: an RFP usually requires a WET (original) signature on the cover letter. The workflow that
actually happens: render the full document, the principal prints the front matter, signs by
hand, and scans those pages back in. The scanned front (image-only, often fewer pages than the
whole document) must be spliced onto the native back so the submission is signed AND complete.
Doing this by hand risks dropping pages, duplicating the boundary page, or ending up with the
wrong total. This tool does the splice deterministically and verifies it.

Inputs : front PDF (the signed/scanned pages, in document order from page 1) and back PDF (the
         full built document). front_pages = how many leading pages the front replaces.
Outputs: spliced PDF = front[0:front_pages] + back[front_pages:]; returns the new page count.
Guards : front must have at least `front_pages` pages; the result page count must equal the
         back's page count (a dropped/added page is a hard error); warns if a spliced page's
         size differs from the page it replaces (A4 scan onto a Letter body, a real foot-gun).

CLI:
  python3 -m bidkit.pdf_splice --front signed.pdf --back built.pdf --out final.pdf \
      [--front-pages N]   # default: all pages of --front
"""
import argparse
import sys

import fitz


def splice(front_path, back_path, out_path, front_pages=None):
    """Build front[0:front_pages] + back[front_pages:] -> out_path.

    front_pages defaults to the full length of the front PDF (the common case: the scanned
    front covers exactly the pages it replaces).

    Returns (total_pages, front_pages_used, size_mismatches) where size_mismatches is a list of
    (page_index, front_size, back_size) tuples where the spliced page's paper size differs from
    the native page it replaced.
    """
    front = fitz.open(front_path)
    back = fitz.open(back_path)
    n_front_avail = front.page_count
    n_back = back.page_count

    fp = n_front_avail if front_pages is None else front_pages
    if fp < 1:
        raise ValueError("front_pages must be >= 1")
    if fp > n_front_avail:
        raise ValueError(f"front has {n_front_avail} pages, need {fp}")
    if fp > n_back:
        raise ValueError(f"front_pages {fp} exceeds back page count {n_back}")

    # record sizes to flag paper-size mismatches at the splice
    mismatches = []
    for i in range(fp):
        fs = (round(front[i].rect.width), round(front[i].rect.height))
        bs = (round(back[i].rect.width), round(back[i].rect.height))
        if fs != bs:
            mismatches.append((i, fs, bs))

    out = fitz.open()
    out.insert_pdf(front, from_page=0, to_page=fp - 1)
    if fp < n_back:
        out.insert_pdf(back, from_page=fp, to_page=n_back - 1)
    total = out.page_count

    # hard invariant: splicing must not change the document length
    if total != n_back:
        out.close(); front.close(); back.close()
        raise AssertionError(f"spliced total {total} != back total {n_back} (pages dropped/added)")

    out.save(out_path, deflate=True, garbage=4)
    out.close(); front.close(); back.close()
    return total, fp, mismatches


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--front", required=True, help="signed/scanned front pages (from page 1)")
    ap.add_argument("--back", required=True, help="the full built document")
    ap.add_argument("--out", required=True)
    ap.add_argument("--front-pages", type=int, default=None,
                    help="how many leading pages the front replaces (default: all of --front)")
    a = ap.parse_args(argv)

    total, fp, mismatches = splice(a.front, a.back, a.out, front_pages=a.front_pages)
    print(f"spliced {a.out}: {total} pages (front {fp} + back {total - fp})")
    if mismatches:
        print("WARNING: paper-size mismatch at spliced page(s):")
        for idx, fs, bs in mismatches:
            print(f"  page {idx + 1}: front {fs[0]}x{fs[1]} vs native {bs[0]}x{bs[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
