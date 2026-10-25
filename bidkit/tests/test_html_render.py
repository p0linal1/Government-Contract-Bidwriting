import os
import pytest
import fitz
from bidkit import html_render


def test_md_to_html_table_has_fixed_column_widths():
    md = "| A | B | C | D |\n|---|---|---|---|\n| 1 | 2 | 3 | 4 |\n"
    body = html_render.md_to_html_body(md)
    assert "<table>" in body and "<colgroup>" in body
    # 4-column preset widths present so the narrow first column cannot bleed
    for w in ("20%", "46%", "16%", "18%"):
        assert w in body
    assert body.count("<td>") == 4 and body.count("<th>") == 4


def test_col_widths_presets_and_fallback():
    assert html_render._col_widths(2) == ["34%", "66%"]
    assert html_render._col_widths(5) == ["17%", "40%", "13%", "15%", "15%"]
    # unknown count falls back to an even split that still sums near 100
    assert html_render._col_widths(6) == ["16%"] * 6


def test_inline_fixes_leaking_underscores_and_bold():
    out = html_render._inline("plain _em_ and **bold** text")
    assert "<em>em</em>" in out and "<strong>bold</strong>" in out
    assert "_em_" not in out                      # the leaking-underscore bug is fixed


def test_inline_converts_em_dash_to_comma():
    # em-dash becomes a comma (house style); the dash char must be gone
    out = html_render._inline("one\u2014two")
    assert "\u2014" not in out and "one, two" in out


def test_inline_escapes_html():
    assert "&lt;script&gt;" in html_render._inline("<script>")


def test_bullets_and_ordered_lists():
    md = "- one\n- two\n\n1. first\n2. second\n"
    body = html_render.md_to_html_body(md)
    assert body.count("<li>") == 4 and "<ul>" in body and "<ol>" in body


def test_build_html_respects_font_and_page_size():
    doc = html_render.build_html("# Title\n\ntext", font="Arial", page_size="a4", margin_in=1.0)
    assert "Arial" in doc and "210mm 297mm" in doc


def test_find_chrome_raises_when_missing():
    with pytest.raises(FileNotFoundError):
        html_render.find_chrome("/no/such/chrome/binary")


# ----- end-to-end render only if a Chrome binary is actually available -----
def _chrome_available():
    try:
        html_render.find_chrome(None)
        return True
    except FileNotFoundError:
        return False


@pytest.mark.skipif(not _chrome_available(), reason="no Chrome/Chromium on this machine")
def test_render_produces_pdf_with_extractable_table_text(tmp_path):
    md = ("## Pricing\n\n| Item | Description | Qty | Price |\n|---|---|---|---|\n"
          "| Widget | A small widget | 2 | 10 |\n| Gadget | A larger gadget | 1 | 25 |\n")
    src = tmp_path / "in.md"; src.write_text(md, encoding="utf-8")
    out = tmp_path / "out.pdf"
    pdf, ntables = html_render.render(str(src), str(out))
    assert ntables == 1 and os.path.exists(out)
    d = fitz.open(str(out))
    full = " ".join(d[i].get_text() for i in range(d.page_count))
    d.close()
    for token in ("Pricing", "Widget", "Gadget", "Description"):
        assert token in full
