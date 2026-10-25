"""
_xlsx_common.py — low-level xlsx (OOXML) helpers shared by xlsx_extract / xlsx_fill / xlsx_verify.

Everything here operates on the raw zip + sheet XML so that we never round-trip a workbook
through openpyxl.save() (which strips x14 dropdown validations). openpyxl is used for
READING only (data_only=True).
"""
import re, zipfile
from xml.etree import ElementTree as ET

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"

CELL_RE = re.compile(r'<c r="([A-Z]+)(\d+)"[^>]*?(?:/>|>.*?</c>)', re.DOTALL)
CELL_SPLIT_RE = re.compile(r'<c r="[A-Z]+\d+"[^>]*?(?:/>|>.*?</c>)', re.DOTALL)
ROW_RE = re.compile(r'(<row r="(\d+)"[^>]*>)(.*?)(</row>)', re.DOTALL)
X14_DV_RE = re.compile(r'<x14:dataValidation[ >]')
PLAIN_DV_RE = re.compile(r'<dataValidation[ >]')


# ------------------------------------------------------------------ column math
def col_to_num(col):
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch) - 64)
    return n


def num_to_col(n):
    s = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        s = chr(65 + rem) + s
    return s


def split_ref(ref):
    m = re.match(r"([A-Z]+)(\d+)$", ref)
    if not m:
        raise ValueError(f"bad cell ref {ref!r}")
    return m.group(1), int(m.group(2))


# ------------------------------------------------------------------ package access
def read_package(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        contents = {n: z.read(n) for n in names}
    return names, contents


def write_package(path, names, contents):
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.writestr(n, contents[n])
    import os
    os.replace(tmp, path)


def sheet_xml_map(contents):
    """{sheet title: 'xl/worksheets/sheetN.xml'} from workbook.xml + its rels."""
    wbx = ET.fromstring(contents["xl/workbook.xml"])
    rels = ET.fromstring(contents["xl/_rels/workbook.xml.rels"])
    rid = {r.get("Id"): r.get("Target") for r in rels.findall(f"{{{NS_PKG}}}Relationship")}
    out = {}
    sheets = wbx.find(f"{{{NS_MAIN}}}sheets")
    for sh in sheets.findall(f"{{{NS_MAIN}}}sheet"):
        r_id = sh.get(f"{{{NS_REL}}}id")
        target = rid[r_id]
        target = target.lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        out[sh.get("name")] = target
    return out


# ------------------------------------------------------------------ merges
def merge_map(sheet_xml):
    """Return (anchors, merged_away) as sets of (col, row) from <mergeCells>."""
    anchors, away = set(), set()
    m = re.search(r"<mergeCells.*?</mergeCells>", sheet_xml, re.DOTALL)
    if not m:
        return anchors, away
    for ref in re.findall(r'<mergeCell ref="([^"]+)"', m.group(0)):
        a, b = ref.split(":")
        ac, ar = split_ref(a); bc, br = split_ref(b)
        anchors.add((ac, ar))
        for r in range(ar, br + 1):
            for c in range(col_to_num(ac), col_to_num(bc) + 1):
                cell = (num_to_col(c), r)
                if cell != (ac, ar):
                    away.add(cell)
    return anchors, away


# ------------------------------------------------------------------ rows / cells
def iter_rows(sheet_xml):
    """Yield (match, rownum, open_tag, body, close_tag) for each <row>."""
    for m in ROW_RE.finditer(sheet_xml):
        yield m, int(m.group(2)), m.group(1), m.group(3), m.group(4)


def row_cells(body):
    return CELL_SPLIT_RE.findall(body)


def cell_col(cell_xml):
    return re.match(r'<c r="([A-Z]+)\d+"', cell_xml).group(1)


def out_of_order_rows(sheet_xml):
    bad = []
    for _, rownum, _, body, _ in iter_rows(sheet_xml):
        cols = [col_to_num(cell_col(c)) for c in row_cells(body)]
        if cols != sorted(cols):
            bad.append(rownum)
    return bad


def sort_row_cells(body):
    cells = row_cells(body)
    cells_sorted = sorted(cells, key=lambda c: col_to_num(cell_col(c)))
    return "".join(cells_sorted), cells_sorted != cells


def count_validations(sheet_xml):
    return len(X14_DV_RE.findall(sheet_xml)), len(PLAIN_DV_RE.findall(sheet_xml))


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def inline_str_cell(ref, text):
    return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{esc(text)}</t></is></c>'


def set_cell(sheet_xml, ref, text):
    """Insert/replace an inline-string cell, keeping the row's cells in column order.
    Creates the row (appended before </sheetData>) if missing. Returns new xml."""
    col, row = split_ref(ref)
    for m, rownum, open_t, body, close_t in iter_rows(sheet_xml):
        if rownum != row:
            continue
        body = re.sub(rf'<c r="{ref}"[^>]*?/>', "", body)
        body = re.sub(rf'<c r="{ref}"[^>]*?>.*?</c>', "", body, flags=re.DOTALL)
        cells = row_cells(body)
        cells.append(inline_str_cell(ref, text))
        cells.sort(key=lambda c: col_to_num(cell_col(c)))
        # keep the row's spans attribute honest (optional in OOXML; drop it to avoid lying)
        open_t2 = re.sub(r'\sspans="[^"]*"', "", open_t)
        return sheet_xml[:m.start()] + open_t2 + "".join(cells) + close_t + sheet_xml[m.end():]
    # row missing: insert in row order before </sheetData>
    newrow = f'<row r="{row}">{inline_str_cell(ref, text)}</row>'
    # find the first existing row with a larger number to insert before it
    for m, rownum, *_ in iter_rows(sheet_xml):
        if rownum > row:
            return sheet_xml[:m.start()] + newrow + sheet_xml[m.start():]
    return re.sub(r"(</sheetData>)", newrow + r"\1", sheet_xml, count=1)
