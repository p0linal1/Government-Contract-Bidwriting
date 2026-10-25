import os, re, shutil, warnings
warnings.filterwarnings("ignore")
from bidkit import config, xlsx_extract, xlsx_fill, xlsx_verify
from bidkit._xlsx_common import read_package, write_package, sheet_xml_map, out_of_order_rows


def _opp(opp_dir):
    return config.load(os.path.join(opp_dir, "opportunity.json"))


def _filled(opp_dir, response="Meets Requirement"):
    opp = _opp(opp_dir)
    rows, _ = xlsx_extract.extract_workbook(opp, "R")
    for r in rows:
        r["response"] = response; r["comment"] = "ok"
    res, dst = xlsx_fill.fill_responses(opp, "R", rows)
    return opp, dst


def _inject_out_of_order(path):
    """Swap the first two cells of every row in every sheet to simulate the historical bug."""
    names, contents = read_package(path)
    for sp in sheet_xml_map(contents).values():
        xml = contents[sp].decode()
        def swap(m):
            open_t, body, close_t = m.group(1), m.group(3), m.group(4)
            cells = re.findall(r'<c r="[A-Z]+\d+"[^>]*?(?:/>|>.*?</c>)', body, re.DOTALL)
            if len(cells) >= 2:
                cells[0], cells[-1] = cells[-1], cells[0]
            return open_t + "".join(cells) + close_t
        xml = re.sub(r'(<row r="(\d+)"[^>]*>)(.*?)(</row>)', swap, xml, flags=re.DOTALL)
        contents[sp] = xml.encode()
    write_package(path, names, contents)


def test_clean_filled_workbook_passes(opp_dir):
    opp, dst = _filled(opp_dir)
    src = opp.resolve(opp.workbook("R")["path"])
    ok, findings, summary = xlsx_verify.verify(dst, ref=src, wbcfg=opp.workbook("R"))
    assert ok, findings
    assert summary["blank_responses"] == 0 and summary["out_of_order_rows"] == 0
    assert summary["x14_validations"] == 2


def test_detects_and_repairs_out_of_order(opp_dir):
    opp, dst = _filled(opp_dir)
    _inject_out_of_order(dst)
    names, contents = read_package(dst)
    assert any(out_of_order_rows(contents[p].decode()) for p in sheet_xml_map(contents).values())
    ok, findings, summary = xlsx_verify.verify(dst)
    assert not ok and summary["out_of_order_rows"] > 0
    assert any(f.startswith("ORDER") for f in findings)
    fixed = xlsx_verify.repair_order(dst)
    assert fixed >= 1
    ok2, findings2, summary2 = xlsx_verify.verify(dst)
    assert ok2 and summary2["out_of_order_rows"] == 0


def test_detects_blank_responses(opp_dir):
    opp = _opp(opp_dir)
    src = opp.resolve(opp.workbook("R")["path"])
    ok, findings, summary = xlsx_verify.verify(src, wbcfg=opp.workbook("R"))   # unfilled original
    assert not ok and summary["blank_responses"] == 10
    assert any("BLANK" in f for f in findings)


def test_detects_placeholders(opp_dir):
    opp, dst = _filled(opp_dir)
    # leave a template placeholder in a form-style cell
    xlsx_fill.fill_cells(dst, dst, {"General": {"C10": "Y / N / NA  if Yes include counts"}})
    ok, findings, summary = xlsx_verify.verify(dst, wbcfg=opp.workbook("R"))
    assert not ok and summary["placeholders"] == 1
    assert any("PLACEHOLDER" in f and "General!C10" in f for f in findings)


def test_detects_merged_away_values(opp_dir):
    opp, dst = _filled(opp_dir)
    # bypass the fill guard and force a value into merged-away D10 via raw XML
    from bidkit._xlsx_common import set_cell
    names, contents = read_package(dst)
    smap = sheet_xml_map(contents)
    xml = contents[smap["General"]].decode()
    contents[smap["General"]] = set_cell(xml, "D10", "hidden").encode()
    write_package(dst, names, contents)
    ok, findings, summary = xlsx_verify.verify(dst)
    assert not ok and summary["merged_away_values"] == 1
    assert any("MERGED" in f and "D10" in f for f in findings)


def test_detects_stripped_validations_vs_reference(opp_dir, tmp_path):
    opp, dst = _filled(opp_dir)
    src = opp.resolve(opp.workbook("R")["path"])
    # simulate the openpyxl.save() disaster: round-trip through openpyxl
    import openpyxl
    wb = openpyxl.load_workbook(dst); stripped = str(tmp_path / "stripped.xlsx"); wb.save(stripped)
    ok, findings, summary = xlsx_verify.verify(stripped, ref=src)
    assert not ok and summary["x14_validations"] == 0
    assert any("VALIDATIONS" in f for f in findings)


def test_cli_exit_codes(opp_dir):
    opp, dst = _filled(opp_dir)
    src = opp.resolve(opp.workbook("R")["path"])
    assert xlsx_verify.main([dst, "--ref", src, "--cfg", os.path.join(opp_dir, "opportunity.json"), "--wb", "R"]) == 0
    assert xlsx_verify.main([src, "--cfg", os.path.join(opp_dir, "opportunity.json"), "--wb", "R"]) == 1


def test_form_style_skips_blank_check_but_keeps_placeholders(opp_dir):
    """Form-style workbooks (label+value grids) have no uniform response column; the blank
    check must not fire, but placeholders and structure are still enforced."""
    opp = _opp(opp_dir)
    src = opp.resolve(opp.workbook("R")["path"])
    form_cfg = {"path": opp.workbook("R")["path"], "header_row": 2, "form_style": True,
                "skip_tabs": ["Instructions", "Control"], "placeholders": ["Y / N / NA"]}
    ok, findings, summary = xlsx_verify.verify(src, wbcfg=form_cfg)      # unfilled -> would be 10 blanks
    assert ok and summary["blank_responses"] == 0
    # but a leftover placeholder still fails
    dst = os.path.join(opp_dir, "form.xlsx")
    xlsx_fill.fill_cells(src, dst, {"General": {"C4": "Y / N / NA  if Yes include counts"}})
    ok2, findings2, summary2 = xlsx_verify.verify(dst, wbcfg=form_cfg)
    assert not ok2 and summary2["placeholders"] == 1


def test_config_accepts_form_style_without_cols(tmp_path):
    import json
    from bidkit import config as cfgmod
    cfg = {"id": "X", "format": {"font_family_allow": ["Arial"], "min_font_pt": 10, "margin_in": 0.75,
                                 "page_size": "letter", "page_limit": 24},
           "fonts": {"regular": "a", "bold": "b", "italic": "c", "bold_italic": "d"},
           "folders": {}, "workbooks": {"F": {"path": "x.xlsx", "header_row": 2, "form_style": True}}}
    p = tmp_path / "opportunity.json"; p.write_text(json.dumps(cfg))
    assert cfgmod.load(str(p)).workbook("F")["form_style"] is True
