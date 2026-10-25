#!/usr/bin/env python3
"""
pdf_verify.py — assert a PDF is fit to enter a SUBMIT folder. Non-zero exit on any failure.

Why: on a prior bid the signed agreement PDF looked like a normal 794 KB file but every page was
an image-only page with 0 extractable text and MuPDF "zlib error: incorrect header check" — a
Preview flatten / bad copy. It had been dismissed as "noisy extraction". And format rules are
scored: non-Arial or <10pt = 50% penalty, footers and table text included; page limits exclude
cover letter/resumes but a footer that numbers every page makes the doc LOOK over the limit.

Checks:
  text      every page has extractable text (chars > 0)          — blank/flattened pages
  errors    no MuPDF warnings/errors while rendering each page   — corrupt streams (FAIL, not noise)
  fonts     every span's font family is in the allowlist          — family penalty
  minsize   every span's size ≥ min_font_pt (footers/tables too)  — size penalty
  pages     total pages, and the visible "Page N of M" range ≤ page_limit
  margins   body text bbox ≥ margin on all edges (ignoring a configurable header/footer band)

Whitespace note: PyMuPDF extracts TTF spaces as NBSP (\\xa0); text is normalised before regex.

CLI:
  python3 -m bidkit.pdf_verify <file.pdf>... --cfg <opportunity.json>
        [--skip text,errors,fonts,minsize,pages,margins] [--json]
  (use --skip for agency-authored forms you must not alter, e.g. `--skip fonts,minsize,margins`)
"""
import argparse, json, os, re, sys
import fitz
from . import config

ALL_CHECKS = ("text", "errors", "fonts", "minsize", "pages", "margins")


def norm(s):
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def verify(path, fmt, checks=ALL_CHECKS, allow_blank=()):
    """Return (ok, findings, summary). fmt = opportunity['format'].
    allow_blank: 1-based page numbers that may legitimately have no extractable text (e.g. an
    image-only cover page). Any OTHER blank page is still a failure — a whole-document blank
    is corruption, not a cover."""
    findings, summary = [], {"file": os.path.basename(path)}
    allow_blank = set(allow_blank or ())
    allow = [a.lower() for a in fmt.get("font_family_allow", [])]
    min_pt = float(fmt.get("min_font_pt", 0))
    margin = float(fmt.get("margin_in", 0)) * 72.0
    band = float(fmt.get("header_footer_band_pt", 40))
    limit = fmt.get("page_limit")

    fitz.TOOLS.mupdf_warnings(reset=True)
    try:
        doc = fitz.open(path)
    except Exception as e:
        return False, [f"OPEN: cannot open PDF: {e}"], summary
    summary["pages"] = doc.page_count
    blank_pages, err_pages = [], []
    bad_fonts, small_spans = {}, []
    min_seen = 999.0
    margin_viol = []
    page_nums = []
    for i in range(doc.page_count):
        pg = doc[i]
        fitz.TOOLS.mupdf_warnings(reset=True)
        text = pg.get_text()
        d = pg.get_text("dict")
        # force a render so stream errors surface even when text extraction is silent
        try:
            pg.get_pixmap(dpi=20)
        except Exception as e:
            err_pages.append((i + 1, str(e)))
        w = fitz.TOOLS.mupdf_warnings()
        if w and "errors" in checks:
            err_pages.append((i + 1, w.strip().splitlines()[0][:100]))
        if "text" in checks and len(text.strip()) == 0 and (i + 1) not in allow_blank:
            blank_pages.append(i + 1)
        r = pg.rect
        xs, ys_body = [], []
        for b in d["blocks"]:
            for l in b.get("lines", []):
                for s in l.get("spans", []):
                    t = s["text"].strip()
                    if not t: continue
                    fam = s["font"]; sz = round(s["size"], 1)
                    min_seen = min(min_seen, sz)
                    if "fonts" in checks and allow and not any(a in fam.lower() for a in allow):
                        bad_fonts.setdefault(fam, []).append(i + 1)
                    if "minsize" in checks and min_pt and sz < min_pt - 0.05:
                        small_spans.append((i + 1, fam, sz, t[:40]))
                    x0, y0, x1, y1 = s["bbox"]
                    xs += [x0, x1]
                    # margins: ignore header/footer bands
                    if band < y0 and y1 < r.height - band:
                        ys_body += [y0, y1]
        if "margins" in checks and margin and xs:
            L, R = min(xs), r.width - max(xs)
            T = min(ys_body) if ys_body else margin
            B = (r.height - max(ys_body)) if ys_body else margin
            tol = 2.0
            if L < margin - tol or R < margin - tol or T < margin - tol - 10 or B < margin - tol:
                margin_viol.append((i + 1, round(L), round(R), round(T), round(B)))
        # Visible page number. Two common footer grammars:
        #   "Page N of M"      (our renderer)
        #   "Page N" / "P a g e | N" (Word footers; letters often spaced by the extractor)
        nt = norm(text)
        nt_words = re.sub(r"\bP a g e\b", "Page", nt)          # collapse spaced "P a g e"
        m = re.search(r"Page\s*\|?\s*(\d+)\s+of\s+(\d+)", nt_words)
        if m:
            page_nums.append((i + 1, int(m.group(1)), int(m.group(2))))
        else:
            m = re.search(r"Page\s*\|?\s*(\d+)\b", nt_words)
            if m:
                page_nums.append((i + 1, int(m.group(1)), 0))
    doc.close()

    summary.update({"blank_pages": blank_pages, "error_pages": len(err_pages),
                    "min_font_pt": None if min_seen == 999.0 else min_seen,
                    "fonts_not_allowed": sorted(bad_fonts.keys()),
                    "numbered_pages": len(page_nums),
                    "numbered_max": max((n for _, n, _ in page_nums), default=0),
                    "numbered_total_label": max((t for _, _, t in page_nums), default=0)})

    if blank_pages:
        findings.append(f"TEXT: {len(blank_pages)} page(s) with no extractable text: {blank_pages[:10]}")
    if err_pages:
        findings.append(f"ERRORS: MuPDF reported problems on {len(err_pages)} page(s): "
                        + "; ".join(f"p{p}: {m}" for p, m in err_pages[:3]))
    if bad_fonts:
        for fam, pages in bad_fonts.items():
            findings.append(f"FONTS: {fam!r} not in allowlist {allow} (pages {sorted(set(pages))[:8]})")
    if small_spans:
        p, fam, sz, t = small_spans[0]
        findings.append(f"MINSIZE: {len(small_spans)} span(s) below {min_pt}pt, e.g. p{p} {sz}pt {fam} {t!r}")
    if "pages" in checks and limit:
        if page_nums and summary["numbered_max"] > int(limit):
            findings.append(f"PAGES: visible page numbers reach {summary['numbered_max']} > limit {limit}")
        if not page_nums and summary["pages"] > int(limit):
            findings.append(f"PAGES: {summary['pages']} pages, no page numbering found, limit {limit} "
                            f"(cannot tell which pages are excluded)")
    if margin_viol:
        p, L, R, T, B = margin_viol[0]
        findings.append(f"MARGINS: {len(margin_viol)} page(s) inside {margin:.0f}pt margin, e.g. p{p} L={L} R={R} T={T} B={B}")
    return (not findings), findings, summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--cfg", required=True)
    ap.add_argument("--skip", default="", help="comma list of checks to skip")
    ap.add_argument("--allow-blank", default="", help="comma list of 1-based pages allowed to have no text (e.g. image cover: 1)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    fmt = config.load(a.cfg)["format"]
    checks = tuple(c for c in ALL_CHECKS if c not in {s.strip() for s in a.skip.split(",") if s.strip()})
    allow_blank = {int(p) for p in a.allow_blank.split(",") if p.strip().isdigit()}
    rc = 0; results = []
    for f in a.files:
        ok, findings, summary = verify(f, fmt, checks, allow_blank=allow_blank)
        results.append({"ok": ok, "findings": findings, "summary": summary})
        if not a.json:
            print(f"{'PASS' if ok else 'FAIL'} {os.path.basename(f)}  pages={summary.get('pages')} "
                  f"min_font={summary.get('min_font_pt')} numbered={summary.get('numbered_pages')}"
                  f"/{summary.get('numbered_total_label')}")
            for line in findings: print(f"   {line}")
        if not ok: rc = 1
    if a.json: print(json.dumps(results, indent=2))
    return rc


if __name__ == "__main__":
    sys.exit(main())
