import json, os, re
import fitz
from bidkit import config, pdf_render


def _norm(s):
    # PyMuPDF extracts TTF-rendered spaces as NBSP (\xa0); normalise so regexes match.
    return re.sub(r"\s+", " ", s.replace("\xa0", " "))


def _spans(pdf):
    d = fitz.open(pdf); out = []
    for i in range(d.page_count):
        for b in d[i].get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                for s in l.get("spans", []):
                    if s["text"].strip():
                        out.append((i, s["font"], round(s["size"], 1), _norm(s["text"])))
    d.close(); return out


def test_render_is_arial_only_and_min_size(opp_dir, sample_md, tmp_path):
    opp = config.load(os.path.join(opp_dir, "opportunity.json"))
    out = str(tmp_path / "out.pdf")
    pages, placed = pdf_render.render(sample_md, out, opp)
    spans = _spans(out)
    assert spans, "no text rendered"
    fams = {f for _, f, _, _ in spans}
    assert all("Arial" in f for f in fams), fams
    assert min(sz for _, _, sz, _ in spans) >= 10.0


def test_numbering_starts_at_part_i_and_excludes_cover_and_resumes(opp_dir, sample_md, tmp_path):
    opp = config.load(os.path.join(opp_dir, "opportunity.json"))
    out = str(tmp_path / "out.pdf")
    pages, placed = pdf_render.render(sample_md, out, opp)
    # sample_md: p0 Cover Letter | p1 PART I | p2 Resumes | p3 PART IV  (pagebreaks between)
    assert pages == 4
    markers = json.load(open(str(tmp_path / "out.markers.json")))
    secs = [p["section"] for p in markers["pages"]]
    assert secs == ["Cover Letter", "PART I", "Resumes", "PART IV"]
    numbered_idx = [p["index"] for p in markers["numbered"]]
    assert numbered_idx == [1, 3]                       # cover + resumes unnumbered
    assert [(p["n"], p["total"]) for p in markers["numbered"]] == [(1, 2), (2, 2)]
    # footers physically present only on those pages
    d = fitz.open(out)
    footers = {i: bool(re.search(r"Page \d+ of \d+", _norm(d[i].get_text()))) for i in range(d.page_count)}
    assert footers == {0: False, 1: True, 2: False, 3: True}


def test_footer_text_respects_min_size(opp_dir, sample_md, tmp_path):
    opp = config.load(os.path.join(opp_dir, "opportunity.json"))
    out = str(tmp_path / "out.pdf")
    pdf_render.render(sample_md, out, opp, footer_label="RFP 000")
    footer_spans = [(sz, t) for _, _, sz, t in _spans(out) if "Page " in t and " of " in t]
    assert footer_spans and all(sz >= 10.0 for sz, _ in footer_spans)


def test_strip_notes_keeps_control_markers():
    md = "a <!-- TODO fix --> b\n<!-- PAGEBREAK -->\n<!-- IMAGE sig.png 120 -->\n<!-- formatting target: 24pp -->"
    s = pdf_render.strip_notes(md)
    assert "TODO" not in s and "formatting target" not in s
    assert "<!-- PAGEBREAK -->" in s and "<!-- IMAGE sig.png 120 -->" in s


def test_body_margins_respected(opp_dir, sample_md, tmp_path):
    opp = config.load(os.path.join(opp_dir, "opportunity.json"))
    out = str(tmp_path / "out.pdf")
    pdf_render.render(sample_md, out, opp, footer=False)
    d = fitz.open(out)
    for i in range(d.page_count):
        r = d[i].rect
        for b in d[i].get_text("dict")["blocks"]:
            x0, y0, x1, y1 = b["bbox"]
            assert x0 >= 54 - 0.5 and x1 <= r.width - 54 + 0.5
            assert y0 >= 54 - 12 and y1 <= r.height - 54 + 0.5   # glyph ascent tolerance on top


def test_cli_warns_when_over_limit(opp_dir, sample_md, tmp_path, capsys):
    opp_path = os.path.join(opp_dir, "opportunity.json")
    cfg = json.load(open(opp_path)); cfg["format"]["page_limit"] = 1
    json.dump(cfg, open(opp_path, "w"))
    rc = pdf_render.main([sample_md, str(tmp_path / "o.pdf"), "--cfg", opp_path])
    assert rc == 1 and "exceed" in capsys.readouterr().out
