import json, os, pytest
from bidkit import config


def test_loads_example_config():
    here = os.path.dirname(os.path.abspath(__file__))
    ex = os.path.join(os.path.dirname(here), "examples", "opportunity.example.json")
    opp = config.load(ex)
    assert opp.id == "EXAMPLE-000"
    assert "_comment" not in opp.data                    # comments stripped
    assert "_comment" not in opp["format"]
    assert opp["format"]["min_font_pt"] == 10


def test_resolve_relative_and_absolute(opp_dir):
    opp = config.load(os.path.join(opp_dir, "opportunity.json"))
    assert opp.resolve("rfp/req.xlsx") == os.path.join(os.path.abspath(opp_dir), "rfp", "req.xlsx")
    assert opp.resolve("/abs/path.pdf") == "/abs/path.pdf"
    assert opp.resolve("") == ""


def test_workbook_and_form_lookup(opp_dir):
    opp = config.load(os.path.join(opp_dir, "opportunity.json"))
    assert opp.workbook("R")["header_row"] == 2
    assert opp.form("F")["page"] == 1
    with pytest.raises(config.ConfigError):
        opp.workbook("NOPE")


def test_missing_required_key_reports_path(tmp_path):
    bad = {"id": "X", "format": {}, "fonts": {}, "folders": {}}
    p = tmp_path / "opportunity.json"; p.write_text(json.dumps(bad))
    with pytest.raises(config.ConfigError) as e:
        config.load(str(p))
    assert "format." in str(e.value)


def test_invalid_json(tmp_path):
    p = tmp_path / "opportunity.json"; p.write_text("{not json")
    with pytest.raises(config.ConfigError):
        config.load(str(p))


def test_cli_summary(opp_dir, capsys):
    rc = config.main([os.path.join(opp_dir, "opportunity.json")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "OPP-001" in out and "workbooks: ['R']" in out
