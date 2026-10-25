import os
import fitz
from bidkit import pdf_redact


def _text(p): return "".join(pg.get_text() for pg in fitz.open(p))


def test_detect_finds_all_contact_types():
    t = ("Jane Doe | jane.doe.personal@gmail.com | (555) 123-4567 | +1 555.987.6543\n"
         "linkedin.com/in/janedoe github.com/janedoe https://janedoe.dev www.jane.io")
    hits = pdf_redact.detect(t)
    assert "jane.doe.personal@gmail.com" in hits
    assert any("555" in h and "123" in h for h in hits)
    assert "linkedin.com/in/janedoe" in hits and "github.com/janedoe" in hits
    assert "https://janedoe.dev" in hits and "www.jane.io" in hits


def test_scrub_removes_underlying_text_and_overlays_company_email(resume_pdf, tmp_path):
    out = str(tmp_path / "scrubbed.pdf")
    res = pdf_redact.scrub(resume_pdf, out, "jane@example.com")
    after = _text(out)
    assert "jane.doe.personal@gmail.com" not in after
    assert "555" not in after                     # phone gone
    assert "linkedin.com" not in after and "github.com" not in after and "janedoe.dev" not in after
    assert "jane@example.com" in after            # replacement overlaid
    assert "Senior engineer" in after             # body untouched
    assert res["survivors"] == [] and res["replacement_at"] is not None
    assert res["replacement_at"][0] == 1


def test_white_box_is_not_enough_but_redaction_is(resume_pdf, tmp_path):
    """Demonstrate the trap: a white rectangle leaves the text extractable; redaction removes it."""
    boxed = str(tmp_path / "boxed.pdf")
    d = fitz.open(resume_pdf); pg = d[0]
    for r in pg.search_for("jane.doe.personal@gmail.com"):
        pg.draw_rect(r, color=(1, 1, 1), fill=(1, 1, 1))
    d.save(boxed); d.close()
    assert "jane.doe.personal@gmail.com" in _text(boxed)           # still there!
    out = str(tmp_path / "redacted.pdf")
    pdf_redact.scrub(resume_pdf, out, "jane@example.com")
    assert "jane.doe.personal@gmail.com" not in _text(out)


def test_keep_contact_leaves_everything(resume_pdf, tmp_path):
    out = str(tmp_path / "kept.pdf")
    res = pdf_redact.scrub(resume_pdf, out, "jane@example.com", keep_contact=True)
    assert res["removed"] == []
    assert "jane.doe.personal@gmail.com" in _text(out)


def test_keep_substring_preserves_company_email(tmp_path):
    p = str(tmp_path / "r.pdf")
    d = fitz.open(); pg = d.new_page()
    pg.insert_text((72, 100), "Bob Roe | bob@example.com | bob.roe77@yahoo.com", fontsize=10, fontname="helv")
    d.save(p); d.close()
    out = str(tmp_path / "o.pdf")
    res = pdf_redact.scrub(p, out, "bob@example.com", keep=["@example.com"])
    after = _text(out)
    assert "bob@example.com" in after and "yahoo" not in after
    assert "bob@example.com" in res["kept"]


def test_dry_run_changes_nothing(resume_pdf, tmp_path):
    before = open(resume_pdf, "rb").read()
    res = pdf_redact.scrub(resume_pdf, str(tmp_path / "x.pdf"), "jane@example.com", dry_run=True)
    assert res["removed"] and not os.path.exists(str(tmp_path / "x.pdf"))
    assert open(resume_pdf, "rb").read() == before


def test_cli(resume_pdf, opp_dir, tmp_path, capsys):
    out = str(tmp_path / "cli.pdf")
    rc = pdf_redact.main([resume_pdf, "--firstname", "Jane", "--cfg", os.path.join(opp_dir, "opportunity.json"), "--out", out])
    assert rc == 0
    o = capsys.readouterr().out
    assert "removed p1" in o and "overlay jane@example.com" in o
    assert "jane@example.com" in _text(out)
