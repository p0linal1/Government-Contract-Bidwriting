import re
import fitz
import pytest
from bidkit import pdf_assemble


def _make_pdf(path, n, size=(612, 792), text_prefix="body"):
    d = fitz.open()
    for i in range(n):
        p = d.new_page(width=size[0], height=size[1])
        p.insert_text((72, 100), f"{text_prefix} {i+1}", fontsize=12)
    d.save(str(path)); d.close()


def _footers(pdf):
    """Return {page_index: 'Page N of M' or None} for the stamped footer on each page."""
    d = fitz.open(pdf)
    out = {}
    for i in range(d.page_count):
        t = d[i].get_text().replace("\xa0", " ")
        m = re.search(r"Page (\d+) of (\d+)", t)
        out[i] = (int(m.group(1)), int(m.group(2))) if m else None
    d.close()
    return out


def test_assemble_concatenates_and_numbers_all_but_cover(tmp_path):
    cover = tmp_path / "cover.pdf"; body = tmp_path / "body.pdf"
    _make_pdf(cover, 1, text_prefix="cover")
    _make_pdf(body, 4, text_prefix="body")
    out = tmp_path / "out.pdf"
    total, numbered = pdf_assemble.assemble([str(cover), str(body)], str(out),
                                            label="ACME | RFP 1", cover_pages=1)
    assert total == 5 and numbered == 4
    f = _footers(str(out))
    assert f[0] is None                      # cover unnumbered
    assert f[1] == (1, 4) and f[4] == (4, 4)  # continuous 1..4 of 4


def test_label_appears_on_branded_pages_only(tmp_path):
    cover = tmp_path / "c.pdf"; body = tmp_path / "b.pdf"; tail = tmp_path / "t.pdf"
    _make_pdf(cover, 1); _make_pdf(body, 2); _make_pdf(tail, 2)
    out = tmp_path / "o.pdf"
    pdf_assemble.assemble([str(cover), str(body), str(tail)], str(out),
                          label="ACME | RFP 1", cover_pages=1, compact_tail=2)
    d = fitz.open(str(out))
    texts = [d[i].get_text().replace("\xa0", " ") for i in range(d.page_count)]
    d.close()
    # branded zone (pages idx1,2) carry the label; compact tail (idx3,4) carry number only
    assert "ACME | RFP 1" in texts[1] and "ACME | RFP 1" in texts[2]
    assert "ACME | RFP 1" not in texts[3] and "ACME | RFP 1" not in texts[4]
    assert "Page 3 of 4" in texts[3] and "Page 4 of 4" in texts[4]


def test_footer_placed_near_each_pages_own_bottom_mixed_sizes(tmp_path):
    """The A4/Letter bug: a footer must sit near EACH page's own bottom edge, not a fixed y."""
    letter = tmp_path / "letter.pdf"; a4 = tmp_path / "a4.pdf"
    _make_pdf(letter, 1, size=(612, 792))
    _make_pdf(a4, 2, size=(595, 842))            # taller A4 pages (like a resume pack)
    out = tmp_path / "o.pdf"
    pdf_assemble.assemble([str(letter), str(a4)], str(out),
                          label="ACME", cover_pages=0, compact_tail=2)
    d = fitz.open(str(out))
    for i in range(d.page_count):
        H = d[i].rect.height
        rects = d[i].search_for("Page")
        assert rects, f"no page number on page {i+1}"
        y = rects[0].y0
        # footer must be within the bottom ~40pt of THIS page (not stamped mid-page)
        assert y > H - 40, f"footer on page {i+1} at y={y:.0f} not near bottom of H={H:.0f}"
    d.close()


def test_no_number_mode_is_pure_concatenation(tmp_path):
    a = tmp_path / "a.pdf"; b = tmp_path / "b.pdf"
    _make_pdf(a, 2); _make_pdf(b, 3)
    out = tmp_path / "o.pdf"
    total, numbered = pdf_assemble.assemble([str(a), str(b)], str(out), number=False)
    assert total == 5 and numbered == 0
    assert all(v is None for v in _footers(str(out)).values())


def test_rejects_bad_zone_counts(tmp_path):
    a = tmp_path / "a.pdf"; _make_pdf(a, 3)
    out = tmp_path / "o.pdf"
    with pytest.raises(ValueError):
        pdf_assemble.assemble([str(a)], str(out), cover_pages=2, compact_tail=2)  # 2+2 > 3


def test_rejects_empty_parts(tmp_path):
    with pytest.raises(ValueError):
        pdf_assemble.assemble([], str(tmp_path / "o.pdf"))
