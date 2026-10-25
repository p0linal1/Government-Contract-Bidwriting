import json, os
from bidkit import config, xlsx_extract


def test_extract_numbered_rows_and_surfaces_unnumbered(opp_dir):
    opp = config.load(os.path.join(opp_dir, "opportunity.json"))
    rows, unnumbered = xlsx_extract.extract_workbook(opp, "R")

    # two requirement tabs x 5 numbered rows each
    assert len(rows) == 10
    assert {r["tab"] for r in rows} == {"General", "Reporting"}
    assert all(r["response"] == "" and r["comment"] == "" for r in rows)
    nums = [r["num"] for r in rows if r["tab"] == "General"]
    assert nums == ["1", "2", "3", "4", "5"]

    # blank-# rows: 2 true headers + 1 real requirement, per tab
    per_tab = [u for u in unnumbered if u["tab"] == "General"]
    assert len(per_tab) == 3
    kinds = {u["row"]: u["guess"] for u in per_tab}
    assert kinds[3] == "header"          # "General Requirements"
    assert kinds[8] == "header"          # "Searches and Queries"
    assert kinds[6] == "requirement?"    # the forgotten-number inmate contact report


def test_cli_writes_both_json_files(opp_dir, capsys):
    rc = xlsx_extract.main([os.path.join(opp_dir, "opportunity.json"), "R"])
    assert rc == 0
    out_dir = os.path.join(opp_dir, "deliverables", "bid", "extract")
    reqs = json.load(open(os.path.join(out_dir, "R-requirements.json")))
    un = json.load(open(os.path.join(out_dir, "R-unnumbered.json")))
    assert len(reqs) == 10 and len(un) == 6
    printed = capsys.readouterr().out
    assert "REVIEW" in printed and "inmate contact report" in printed


def test_guess_kind_heuristics():
    g = xlsx_extract.guess_kind
    assert g("Reports") == "header"
    assert g("Searches and Queries") == "header"
    assert g("Cloud and SaaS operations (as applicable)") == "header"
    assert g("Provide a Booking Report on all persons booked for a date range.") == "requirement?"
    assert g("Please answer current compliance for the following (Yes / No)") == "requirement?"
