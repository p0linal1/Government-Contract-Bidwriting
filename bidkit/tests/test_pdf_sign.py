import json, os, re
import fitz, pytest
from bidkit import config, pdf_sign


def _norm(s): return re.sub(r"\s+", " ", s.replace("\xa0", " "))


def test_discovers_all_four_fields_on_fixture(opp_dir):
    opp = config.load(os.path.join(opp_dir, "opportunity.json"))
    form = opp.form("F")
    doc = fitz.open(opp.resolve(form["path"]))
    coords = pdf_sign.discover(doc[0], form["fields"])
    assert set(coords) == {"printed_name", "company", "signature", "date"}
    # fixture: lines at y220 (name/company) and y300 (sig/date); left col x72, right col x360
    assert abs(coords["printed_name"]["x"] - 76) < 2 and abs(coords["printed_name"]["y"] - 216) < 6
    assert abs(coords["company"]["x"] - 364) < 2
    assert abs(coords["signature"]["y"] - 296) < 6 and coords["signature"]["y"] > coords["printed_name"]["y"]
    assert abs(coords["date"]["x"] - 364) < 2


def test_sign_writes_values_and_leaves_date_blank(opp_dir):
    opp = config.load(os.path.join(opp_dir, "opportunity.json"))
    out, coords, written = pdf_sign.sign(opp, "F")
    assert os.path.exists(out) and out.endswith("(signed).pdf")
    keys = [k for k, _ in written]
    assert "printed_name" in keys and "company" in keys and "signature" in keys and "note" in keys
    assert "date" not in keys
    t = _norm(fitz.open(out)[0].get_text())
    assert "Test Person, Principal" in t and "Test LLC" in t
    assert "(original signature on submission)" in t
    # original untouched
    assert "Test Person" not in fitz.open(opp.resolve(opp.form("F")["path"]))[0].get_text()


def test_sign_with_date(opp_dir):
    opp = config.load(os.path.join(opp_dir, "opportunity.json"))
    out, coords, written = pdf_sign.sign(opp, "F", date="09/16/2026")
    assert ("date", "09/16/2026") in written
    assert "09/16/2026" in _norm(fitz.open(out)[0].get_text())


def test_signature_image_used_when_configured(opp_dir, tmp_path):
    opp_path = os.path.join(opp_dir, "opportunity.json")
    cfg = json.load(open(opp_path))
    # make a tiny PNG signature
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 120, 30), False); pix.clear_with(0)
    sig = os.path.join(opp_dir, "sig.png"); pix.save(sig)
    cfg["signer"]["signature_image"] = "sig.png"
    json.dump(cfg, open(opp_path, "w"))
    opp = config.load(opp_path)
    out, coords, written = pdf_sign.sign(opp, "F")
    assert any(k == "signature" and v.startswith("<image") for k, v in written)
    assert len(fitz.open(out)[0].get_images()) == 1


def test_ambiguous_label_refuses_and_lists_candidates(tmp_path):
    # two identical "Signature" blocks with lines -> ambiguous
    p = str(tmp_path / "amb.pdf")
    d = fitz.open(); pg = d.new_page(width=612, height=792)
    for y in (200, 400):
        pg.insert_text((72, y), "_" * 30, fontsize=11, fontname="helv")
        pg.insert_text((72, y + 14), "Signature", fontsize=9, fontname="helv")
    d.save(p); d.close()
    with pytest.raises(pdf_sign.DiscoveryError) as e:
        pdf_sign.discover(fitz.open(p)[0], {"signature": "Signature"})
    assert "ambiguous" in str(e.value) and "2 candidates" in str(e.value)


def test_coords_override_bypasses_discovery(opp_dir):
    opp = config.load(os.path.join(opp_dir, "opportunity.json"))
    out, coords, written = pdf_sign.sign(opp, "F", coords_override={"signature": [100, 500]})
    assert coords == {"signature": {"x": 100, "y": 500}}
    assert ("signature", "Test Person") in written


def test_cli_probe_and_failure_exit(opp_dir, capsys):
    opp_path = os.path.join(opp_dir, "opportunity.json")
    assert pdf_sign.main([opp_path, "F", "--probe"]) == 0
    out = capsys.readouterr().out
    assert "LINE" in out and "LABEL signature" in out
    # break discovery: label that doesn't exist
    cfg = json.load(open(opp_path)); cfg["forms"]["F"]["fields"]["signature"] = "Autograph"
    json.dump(cfg, open(opp_path, "w"))
    assert pdf_sign.main([opp_path, "F"]) == 1
    assert "DISCOVERY FAILED" in capsys.readouterr().out


# ------------------------------------------------------------------ real-form regressions
from conftest import real_sample
A7 = real_sample("26-013-BIPIN", "rfp", "A7- Certifications and Assurances Form.pdf")
A11 = real_sample("26-013-BIPIN", "rfp", "A11 - Federal Funding.pdf")
FIELDS = {"printed_name": "Printed Name", "company": "Company Name", "signature": "Signature", "date": "Date"}


@pytest.mark.skipif(not A7, reason="real A7 not present")
def test_real_a7_matches_hand_measured_coords():
    """Historical sign_forms.py placed name at (76,222) and signature at (76,284) on page 2."""
    coords = pdf_sign.discover(fitz.open(A7)[1], FIELDS)
    assert abs(coords["printed_name"]["x"] - 76) <= 2 and abs(coords["printed_name"]["y"] - 222) <= 3
    assert abs(coords["company"]["x"] - 364) <= 2
    assert abs(coords["signature"]["x"] - 76) <= 2 and abs(coords["signature"]["y"] - 284) <= 3
    assert abs(coords["date"]["x"] - 364) <= 2 and abs(coords["date"]["y"] - 284) <= 3


@pytest.mark.skipif(not A11, reason="real A11 not present")
def test_real_a11_matches_hand_measured_coords():
    """Historical sign_forms.py placed name at (94,585) and signature at (94,647) on page 5."""
    coords = pdf_sign.discover(fitz.open(A11)[4], FIELDS)
    assert abs(coords["printed_name"]["x"] - 94) <= 2 and abs(coords["printed_name"]["y"] - 585) <= 3
    assert abs(coords["signature"]["x"] - 94) <= 2 and abs(coords["signature"]["y"] - 647) <= 3
    assert abs(coords["date"]["x"] - 382) <= 2
