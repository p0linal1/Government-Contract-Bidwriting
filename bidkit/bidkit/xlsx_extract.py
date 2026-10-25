#!/usr/bin/env python3
"""
xlsx_extract.py — dump requirement rows from an agency workbook to JSON for drafting, and
SURFACE the blank-number rows so a human can tell section headers from real requirements.

Why: agency workbooks use a blank "#" cell for section headers ("Reports", "Searches and
Queries") — but authors sometimes forget to number a real requirement (seen on a prior bid:
an unnumbered "Provide an inmate contact report…" row). An extractor that treats blank-# as header
silently drops those. This tool writes them to `unnumbered.json` with a heuristic guess so
they are reviewed, never lost.

Inputs : opportunity.json, workbook key (e.g. A1)
Outputs: <extract>/<key>-requirements.json   numbered rows: tab,row,num,requirement,response,comment
         <extract>/<key>-unnumbered.json      blank-# rows: tab,row,text,words,guess (header|requirement?)
Guards : unnumbered-but-real requirement rows (trap 4 in bid-tooling.md)

CLI:  python3 -m bidkit.xlsx_extract <opportunity.json> <wb-key> [--json-only]
"""
import json, os, re, sys, warnings
warnings.filterwarnings("ignore")
import openpyxl
from . import config

REQ_STARTS = ("provide", "ability", "able to", "the system", "system shall", "solution shall",
              "vendor shall", "support", "allow", "display", "generate", "track", "record",
              "capture", "maintain", "enable", "please", "describe", "identify")


def guess_kind(text):
    """Heuristic only — a human decides. Headers are short category labels; requirements are
    sentences. Returns 'header' or 'requirement?'."""
    t = text.strip()
    words = len(t.split())
    low = t.lower()
    if words >= 8:
        return "requirement?"
    if low.startswith(REQ_STARTS) and words >= 4:
        return "requirement?"
    if t.endswith((".", "?", ":")) and words >= 5:
        return "requirement?"
    return "header"


def extract_workbook(opp, key):
    wbcfg = opp.workbook(key)
    path = opp.resolve(wbcfg["path"])
    cols = wbcfg["cols"]
    header_row = int(wbcfg["header_row"])
    skip = {t.strip().lower() for t in wbcfg.get("skip_tabs", [])}
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    rows, unnumbered = [], []
    for ws in wb.worksheets:
        if ws.title.strip().lower() in skip:
            continue
        for r in range(header_row + 1, ws.max_row + 1):
            num = ws.cell(r, cols["num"]).value
            req = ws.cell(r, cols["req"]).value
            if req is None or str(req).strip() == "":
                continue
            if num is None or str(num).strip() == "":
                text = str(req).strip()
                unnumbered.append({"tab": ws.title, "row": r, "text": text,
                                   "words": len(text.split()), "guess": guess_kind(text)})
                continue
            rows.append({"tab": ws.title, "row": r, "num": str(num).strip(),
                         "requirement": str(req).strip(), "response": "", "comment": ""})
    wb.close()
    return rows, unnumbered


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cfg", help="opportunity.json"); ap.add_argument("wb", help="workbook key, e.g. A1")
    a = ap.parse_args(argv)
    opp = config.load(a.cfg); key = a.wb
    rows, unnumbered = extract_workbook(opp, key)
    out_dir = opp.folder("extract", create=True)
    p_req = os.path.join(out_dir, f"{key}-requirements.json")
    p_un = os.path.join(out_dir, f"{key}-unnumbered.json")
    with open(p_req, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2, ensure_ascii=False)
    with open(p_un, "w", encoding="utf-8") as fh:
        json.dump(unnumbered, fh, indent=2, ensure_ascii=False)
    print(f"{key}: {len(rows)} numbered requirement rows -> {p_req}")
    flagged = [u for u in unnumbered if u["guess"] != "header"]
    print(f"{key}: {len(unnumbered)} blank-number rows -> {p_un}  "
          f"({len(flagged)} look like REAL requirements — review before filling)")
    for u in flagged:
        print(f"   REVIEW [{u['tab']}] row {u['row']} ({u['words']} words): {u['text'][:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
