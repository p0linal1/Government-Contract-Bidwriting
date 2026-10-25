#!/usr/bin/env python3
"""
xlsx_verify.py — assert a filled workbook is structurally sound and complete before it goes
into a SUBMIT folder. Non-zero exit on any failure so it can gate a pipeline.

Checks (each maps to a trap that cost real time on a prior bid):
  order        0 rows with <c> cells out of column order   (Excel strips such rows on open)
  validations  x14 dropdown-validation count == reference  (openpyxl.save strips them)
  merged       0 values stored in merged-away cells        (hidden values / repair warning)
  blanks       0 numbered requirement rows with an empty response  (needs --cfg + --wb)
  placeholders 0 cells still containing template placeholder strings (e.g. "Y / N / NA")

--repair   re-sorts each row's cells by column (content-preserving) and re-runs the checks.
--ref FILE compare validation counts against this file (default: the workbook itself, i.e. the
           check only asserts validations exist somewhere if the workbook is known to have them;
           pass the pristine rfp/ original for a real comparison).

CLI:
  python3 -m bidkit.xlsx_verify <file.xlsx>... [--repair] [--ref pristine.xlsx]
                                 [--cfg opportunity.json --wb KEY]   # enables blanks/placeholders
"""
import argparse, os, sys, warnings
warnings.filterwarnings("ignore")
import openpyxl
from . import config
from ._xlsx_common import (read_package, write_package, sheet_xml_map, merge_map, iter_rows,
                           row_cells, cell_col, out_of_order_rows, sort_row_cells,
                           count_validations, split_ref)

DEFAULT_PLACEHOLDERS = ["Y / N / NA", "If Yes include", "If yes explain", "If yes decribe",
                        "If Yes include Price"]


def repair_order(path):
    names, contents = read_package(path)
    smap = sheet_xml_map(contents)
    fixed_sheets = 0
    for sp in smap.values():
        if sp not in contents: continue
        xml = contents[sp].decode("utf-8"); out = []; pos = 0; changed = False
        for m, rownum, open_t, body, close_t in iter_rows(xml):
            out.append(xml[pos:m.start()])
            new_body, ch = sort_row_cells(body)
            changed = changed or ch
            out.append(open_t + new_body + close_t); pos = m.end()
        out.append(xml[pos:])
        if changed:
            contents[sp] = "".join(out).encode("utf-8"); fixed_sheets += 1
    if fixed_sheets:
        write_package(path, names, contents)
    return fixed_sheets


def merged_away_values(sheet_xml):
    """Cells that carry a value (<v> or <is>) but sit inside a merged range off-anchor."""
    _, away = merge_map(sheet_xml)
    if not away: return []
    bad = []
    for _, rownum, _, body, _ in iter_rows(sheet_xml):
        for c in row_cells(body):
            if ("<v>" in c or "<is>" in c):
                col = cell_col(c)
                if (col, rownum) in away:
                    bad.append(f"{col}{rownum}")
    return bad


def verify(path, ref=None, wbcfg=None):
    """Return (ok, findings:list[str], summary:dict)."""
    findings = []
    names, contents = read_package(path)
    smap = sheet_xml_map(contents)
    # order + merged + validations
    x14_total = 0; ooo_total = 0; merged_total = 0
    for title, sp in smap.items():
        if sp not in contents: continue
        xml = contents[sp].decode("utf-8")
        ooo = out_of_order_rows(xml)
        if ooo:
            ooo_total += len(ooo)
            findings.append(f"ORDER {title}: {len(ooo)} out-of-order rows (e.g. {ooo[:5]})")
        mv = merged_away_values(xml)
        if mv:
            merged_total += len(mv)
            findings.append(f"MERGED {title}: values in merged-away cells {mv[:8]}")
        x14_total += count_validations(xml)[0]
    if ref:
        rn, rc = read_package(ref)
        ref_total = sum(count_validations(rc[p].decode("utf-8"))[0] for p in sheet_xml_map(rc).values() if p in rc)
        if ref_total != x14_total:
            findings.append(f"VALIDATIONS: {x14_total} x14 dropdown validations, reference has {ref_total}")
    # blanks + placeholders (need the workbook layout)
    blanks = 0; placeholders_found = []
    if wbcfg:
        header_row = int(wbcfg["header_row"])
        skip = {t.strip().lower() for t in wbcfg.get("skip_tabs", [])}
        ph_list = wbcfg.get("placeholders", DEFAULT_PLACEHOLDERS)
        # The blank-response check assumes the uniform requirement layout (#, Requirement,
        # Response, Comments). Form-style workbooks (label + value grids, e.g. reference /
        # deployment / support histories) set "form_style": true and skip it — their
        # completeness is a human judgment; placeholders and structure are still checked.
        if not wbcfg.get("form_style"):
            cols = wbcfg["cols"]
            wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
            for ws in wb.worksheets:
                if ws.title.strip().lower() in skip: continue
                for r in range(header_row + 1, ws.max_row + 1):
                    num = ws.cell(r, cols["num"]).value; req = ws.cell(r, cols["req"]).value
                    if req and str(req).strip() and num and str(num).strip():
                        resp = ws.cell(r, cols["resp"]).value
                        if not (resp and str(resp).strip()):
                            blanks += 1
                            if blanks <= 10:
                                findings.append(f"BLANK {ws.title} row {r} (#{num}) has no response")
            wb.close()
        # placeholders: scan every cell of every sheet (form-style tabs included)
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for c in row:
                    v = c.value
                    if isinstance(v, str) and any(p in v for p in ph_list):
                        placeholders_found.append(f"{ws.title}!{c.coordinate}")
        wb.close()
        if blanks > 10:
            findings.append(f"BLANK: ... {blanks} total blank responses")
        if placeholders_found:
            findings.append(f"PLACEHOLDER: template text still present in {placeholders_found[:10]}"
                            + (f" (+{len(placeholders_found)-10} more)" if len(placeholders_found) > 10 else ""))
    summary = {"x14_validations": x14_total, "out_of_order_rows": ooo_total,
               "merged_away_values": merged_total, "blank_responses": blanks,
               "placeholders": len(placeholders_found)}
    return (not findings), findings, summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--repair", action="store_true")
    ap.add_argument("--ref", help="pristine workbook to compare validation counts against")
    ap.add_argument("--cfg", help="opportunity.json (enables blank/placeholder checks with --wb)")
    ap.add_argument("--wb", help="workbook key in the config")
    a = ap.parse_args(argv)
    wbcfg = None
    if a.cfg and a.wb:
        wbcfg = config.load(a.cfg).workbook(a.wb)
    rc = 0
    for f in a.files:
        if a.repair:
            fixed = repair_order(f)
            print(f"{os.path.basename(f)}: repaired {fixed} sheet(s)")
        ok, findings, summary = verify(f, ref=a.ref, wbcfg=wbcfg)
        status = "PASS" if ok else "FAIL"
        print(f"{status} {os.path.basename(f)}  {summary}")
        for line in findings:
            print(f"   {line}")
        if not ok: rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
