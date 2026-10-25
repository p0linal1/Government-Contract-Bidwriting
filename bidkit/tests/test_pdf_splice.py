import fitz
import pytest
from bidkit import pdf_splice


def _make_pdf(path, n, size=(612, 792), tag="native"):
    d = fitz.open()
    for i in range(n):
        p = d.new_page(width=size[0], height=size[1])
        p.insert_text((72, 100), f"{tag} page {i+1}", fontsize=12)
    d.save(str(path)); d.close()


def _page_texts(pdf):
    d = fitz.open(pdf); out = [d[i].get_text() for i in range(d.page_count)]; d.close(); return out


def test_splice_replaces_front_keeps_length(tmp_path):
    built = tmp_path / "built.pdf"; signed = tmp_path / "signed.pdf"
    _make_pdf(built, 50, tag="native")
    _make_pdf(signed, 14, tag="signed")           # scanned front = first 14 pages
    out = tmp_path / "final.pdf"
    total, fp, mism = pdf_splice.splice(str(signed), str(built), str(out))
    assert total == 50 and fp == 14 and mism == []
    texts = _page_texts(str(out))
    assert all("signed" in texts[i] for i in range(14))     # front from the scan
    assert all("native" in texts[i] for i in range(14, 50))  # back from the build


def test_front_pages_subset(tmp_path):
    built = tmp_path / "b.pdf"; signed = tmp_path / "s.pdf"
    _make_pdf(built, 10, tag="native"); _make_pdf(signed, 5, tag="signed")
    out = tmp_path / "o.pdf"
    total, fp, _ = pdf_splice.splice(str(signed), str(built), str(out), front_pages=3)
    assert total == 10 and fp == 3
    texts = _page_texts(str(out))
    assert "signed" in texts[2] and "native" in texts[3]


def test_paper_size_mismatch_flagged(tmp_path):
    """A4 scan spliced onto a Letter body must be reported, not silently accepted."""
    built = tmp_path / "b.pdf"; signed = tmp_path / "s.pdf"
    _make_pdf(built, 6, size=(612, 792), tag="native")
    _make_pdf(signed, 2, size=(595, 842), tag="signed")   # A4 front
    out = tmp_path / "o.pdf"
    total, fp, mism = pdf_splice.splice(str(signed), str(built), str(out))
    assert total == 6 and fp == 2
    assert len(mism) == 2
    assert mism[0][1] == (595, 842) and mism[0][2] == (612, 792)


def test_rejects_front_pages_exceeding_front(tmp_path):
    built = tmp_path / "b.pdf"; signed = tmp_path / "s.pdf"
    _make_pdf(built, 10); _make_pdf(signed, 3)
    with pytest.raises(ValueError):
        pdf_splice.splice(str(signed), str(built), str(tmp_path / "o.pdf"), front_pages=5)


def test_rejects_front_pages_exceeding_back(tmp_path):
    built = tmp_path / "b.pdf"; signed = tmp_path / "s.pdf"
    _make_pdf(built, 3); _make_pdf(signed, 10)
    with pytest.raises(ValueError):
        pdf_splice.splice(str(signed), str(built), str(tmp_path / "o.pdf"), front_pages=5)


def test_full_front_equal_length_replaces_everything(tmp_path):
    built = tmp_path / "b.pdf"; signed = tmp_path / "s.pdf"
    _make_pdf(built, 4, tag="native"); _make_pdf(signed, 4, tag="signed")
    out = tmp_path / "o.pdf"
    total, fp, _ = pdf_splice.splice(str(signed), str(built), str(out))
    assert total == 4 and fp == 4
    assert all("signed" in t for t in _page_texts(str(out)))
