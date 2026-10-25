import json, os
import fitz, pytest
from bidkit import config, pdf_render, pdf_verify


def _fmt(opp_dir):
    return config.load(os.path.join(opp_dir, "opportunity.json"))["format"]


def test_rendered_doc_passes(opp_dir, sample_md, tmp_path):
    opp = config.load(os.path.join(opp_dir, "opportunity.json"))
    out = str(tmp_path / "ok.pdf")
    pdf_render.render(sample_md, out, opp)
    ok, findings, summary = pdf_verify.verify(out, opp["format"])
    assert ok, findings
    assert summary["blank_pages"] == [] and summary["error_pages"] == 0
    assert summary["min_font_pt"] >= 10.0
    assert summary["fonts_not_allowed"] == []
    assert summary["numbered_pages"] == 2 and summary["numbered_total_label"] == 2


def test_blank_image_pdf_fails_text_check(opp_dir, blank_image_pdf):
    ok, findings, summary = pdf_verify.verify(blank_image_pdf, _fmt(opp_dir))
    assert not ok
    assert summary["blank_pages"] == [1]
    assert any(f.startswith("TEXT") for f in findings)


def test_wrong_font_family_fails(opp_dir, tmp_path):
    p = str(tmp_path / "times.pdf")
    d = fitz.open(); pg = d.new_page(width=612, height=792)
    pg.insert_text((72, 100), "Rendered in Times", fontsize=11, fontname="tiro")   # base-14 Times-Roman
    d.save(p); d.close()
    ok, findings, summary = pdf_verify.verify(p, _fmt(opp_dir))
    assert not ok
    assert any(f.startswith("FONTS") for f in findings)
    assert summary["fonts_not_allowed"] and "Times" in summary["fonts_not_allowed"][0]


def test_small_footer_text_fails_minsize(opp_dir, tmp_path):
    p = str(tmp_path / "small.pdf")
    d = fitz.open(); pg = d.new_page(width=612, height=792)
    pg.insert_font(fontfile="/System/Library/Fonts/Supplemental/Arial.ttf", fontname="ar")
    pg.insert_text((72, 100), "Body text at eleven", fontsize=11, fontname="ar")
    pg.insert_text((72, 770), "tiny footer", fontsize=7, fontname="ar")
    d.save(p); d.close()
    ok, findings, summary = pdf_verify.verify(p, _fmt(opp_dir))
    assert not ok
    assert summary["min_font_pt"] == 7.0
    assert any(f.startswith("MINSIZE") for f in findings)


def test_visible_page_numbers_over_limit_fail(opp_dir, sample_md, tmp_path):
    opp = config.load(os.path.join(opp_dir, "opportunity.json"))
    out = str(tmp_path / "over.pdf")
    # number EVERY page from the cover (the BIPIN mistake) and set a limit of 2
    pdf_render.render(sample_md, out, opp, number_from="Cover Letter", exclude=[])
    fmt = dict(opp["format"]); fmt["page_limit"] = 2
    ok, findings, summary = pdf_verify.verify(out, fmt)
    assert not ok and summary["numbered_max"] == 4
    assert any(f.startswith("PAGES") for f in findings)


def test_skip_checks_for_agency_forms(opp_dir, flat_form_pdf):
    # agency form is Helvetica (not Arial) and small labels — must be verifiable for text/errors only
    fmt = _fmt(opp_dir)
    ok_all, findings_all, _ = pdf_verify.verify(flat_form_pdf, fmt)
    assert not ok_all                                    # fonts/minsize would flag it
    ok, findings, _ = pdf_verify.verify(flat_form_pdf, fmt, checks=("text", "errors"))
    assert ok, findings


def test_cli_exit_codes(opp_dir, sample_md, blank_image_pdf, tmp_path):
    opp_path = os.path.join(opp_dir, "opportunity.json")
    opp = config.load(opp_path)
    good = str(tmp_path / "good.pdf"); pdf_render.render(sample_md, good, opp)
    assert pdf_verify.main([good, "--cfg", opp_path]) == 0
    assert pdf_verify.main([blank_image_pdf, "--cfg", opp_path]) == 1


from conftest import real_sample
REAL_CORRUPT = real_sample("26-013-BIPIN", "final-draft", "redlines", "A9 - Goods and Services Agreement Final.pdf")

@pytest.mark.skipif(not REAL_CORRUPT, reason="real corrupt sample not present")
def test_real_corrupt_bipin_a9_is_caught(opp_dir):
    """Regression against the actual blank-page PDF that nearly shipped."""
    ok, findings, summary = pdf_verify.verify(REAL_CORRUPT, _fmt(opp_dir), checks=("text", "errors"))
    assert not ok
    assert summary["blank_pages"], "expected blank pages on the corrupt A9"


def test_word_style_spaced_footer_is_recognised(opp_dir, tmp_path):
    """Word footers extract as 'P a g e | 7'; the verifier must still read the page number."""
    p = str(tmp_path / "word.pdf")
    d = fitz.open()
    for n in (1, 2, 30):
        pg = d.new_page(width=612, height=792)
        pg.insert_font(fontfile="/System/Library/Fonts/Supplemental/Arial.ttf", fontname="ar")
        pg.insert_text((72, 100), "Body", fontsize=11, fontname="ar")
        pg.insert_text((72, 770), f"P a g e | {n}   RFP 00-000", fontsize=10, fontname="ar")
    d.save(p); d.close()
    fmt = dict(_fmt(opp_dir)); fmt["page_limit"] = 24
    ok, findings, summary = pdf_verify.verify(p, fmt)
    assert summary["numbered_pages"] == 3 and summary["numbered_max"] == 30
    assert not ok and any(f.startswith("PAGES") and "30" in f for f in findings)


def test_allow_blank_cover_page(opp_dir, tmp_path):
    p = str(tmp_path / "cover.pdf")
    d = fitz.open()
    pg = d.new_page(width=612, height=792)                              # image-only cover
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), False); pix.clear_with(200)
    pg.insert_image(fitz.Rect(100, 100, 500, 500), pixmap=pix)
    pg2 = d.new_page(width=612, height=792)
    pg2.insert_font(fontfile="/System/Library/Fonts/Supplemental/Arial.ttf", fontname="ar")
    pg2.insert_text((72, 100), "Body text", fontsize=11, fontname="ar")
    d.save(p); d.close()
    fmt = _fmt(opp_dir)
    ok, findings, summary = pdf_verify.verify(p, fmt, checks=("text", "errors"))
    assert not ok and summary["blank_pages"] == [1]
    ok2, findings2, summary2 = pdf_verify.verify(p, fmt, checks=("text", "errors"), allow_blank={1})
    assert ok2 and summary2["blank_pages"] == []
    # allow_blank must NOT excuse a fully blank document
    ok3, _, summary3 = pdf_verify.verify(p, fmt, checks=("text", "errors"), allow_blank={2})
    assert not ok3 and summary3["blank_pages"] == [1]
