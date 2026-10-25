#!/usr/bin/env python3
"""
pdf_sign.py — fill the signature block of a FLAT agency PDF (no AcroForm fields) by
LABEL-ANCHORED discovery instead of hand-measured pixel coordinates.

Why: on both prior bids every form's signature/date/name positions were measured by hand and
typed into a script — slow, error-prone, and re-done per form. Agency forms follow a stable
visual grammar: a run of underscores forms the line, and the field label ("Signature", "Date",
"Printed Name & Title", "Company Name") is printed just BELOW that line, left-aligned with it.
This module finds each label word via page.get_text("words"), then picks the underscore run
whose x-range covers the label's left edge and whose bottom sits just above the label — and
writes the value on that line's baseline. A `--coords` JSON override exists for forms where
discovery is ambiguous (the tool refuses and lists candidates rather than guessing).

Signature policy (bid-tooling.md trap 8): a TYPED signature (italic) or signature IMAGE is
placed for the electronic copy and annotated with the configured note, e.g.
"(original signature on submission)". The DATE is left blank unless --date is given; the
principal applies the original/wet signature and date by hand before submission.

Config (opportunity.json):
  forms.<KEY>: {path, page (1-based), fields:{printed_name:"Printed Name", company:"Company Name",
                signature:"Signature", date:"Date"}, signature_note}
  signer:      {printed, company, typed_signature, signature_image (optional), date}

CLI:
  python3 -m bidkit.pdf_sign <opportunity.json> <FORM-KEY> [--out FILE] [--date MM/DD/YYYY]
        [--coords '{"signature":[x,y],"date":[x,y],...}'] [--probe]
  --probe prints every underscore line and label found on the page and exits (for building coords).
"""
import argparse, json, os, re, sys
import fitz
from . import config

MIN_UNDERSCORES = 5


class DiscoveryError(Exception):
    pass


def page_geometry(page):
    """Return (lines, words). lines: list of dict(x0,y0,x1,y1,len). words: PyMuPDF words."""
    words = page.get_text("words")
    lines = []
    for w in words:
        t = w[4]
        if len(t) >= MIN_UNDERSCORES and set(t) <= set("_"):
            lines.append({"x0": w[0], "y0": w[1], "x1": w[2], "y1": w[3], "len": len(t)})
    # also treat drawn horizontal rules as lines (some forms draw them instead of typing _)
    try:
        for dr in page.get_drawings():
            r = dr.get("rect")
            if r and r.width >= 60 and r.height <= 2.5:
                lines.append({"x0": r.x0, "y0": r.y0 - 12, "x1": r.x1, "y1": r.y1 + 2, "len": 0})
    except Exception:
        pass
    return lines, words


def find_label(words, label):
    """Find occurrences of the label's FIRST word (case-insensitive, punctuation-stripped).
    Returns list of (x0, y0, x1, y1)."""
    first = re.sub(r"[^A-Za-z0-9]", "", label.split()[0]).lower()
    hits = []
    for w in words:
        if re.sub(r"[^A-Za-z0-9]", "", w[4]).lower() == first:
            hits.append((w[0], w[1], w[2], w[3]))
    return hits


def line_for_label(lines, lab, max_gap=30):
    """Pick the underscore line whose x-range covers the label's left edge and whose bottom is
    within max_gap pt ABOVE the label's top. Ties -> nearest vertically."""
    lx0, ly0 = lab[0], lab[1]
    cands = [ln for ln in lines
             if ln["x0"] - 6 <= lx0 <= ln["x1"] and 0 <= ly0 - ln["y1"] <= max_gap]
    if not cands:
        return None
    return min(cands, key=lambda ln: ly0 - ln["y1"])


def discover(page, fields):
    """fields: {logical: label}. Returns {logical: {"x":..,"y":..,"line":{...}}} or raises
    DiscoveryError listing candidates."""
    lines, words = page_geometry(page)
    out, problems = {}, []
    for logical, label in fields.items():
        hits = find_label(words, label)
        # disambiguate multiple label hits by requiring a line above each; keep those with a line
        resolved = [(h, line_for_label(lines, h)) for h in hits]
        resolved = [(h, ln) for h, ln in resolved if ln]
        # if the label has 2+ words, prefer hits where the next word also matches
        if len(label.split()) > 1 and len(resolved) > 1:
            second = re.sub(r"[^A-Za-z0-9]", "", label.split()[1]).lower()
            narrowed = []
            for h, ln in resolved:
                nxt = [w for w in words if abs(w[1] - h[1]) < 3 and w[0] > h[2] and w[0] - h[2] < 12]
                if nxt and re.sub(r"[^A-Za-z0-9]", "", nxt[0][4]).lower() == second:
                    narrowed.append((h, ln))
            if narrowed:
                resolved = narrowed
        if not resolved:
            problems.append(f"{logical}: label {label!r} -> {len(hits)} word hit(s), none with a line above")
            continue
        if len(resolved) > 1:
            problems.append(f"{logical}: label {label!r} ambiguous, {len(resolved)} candidates at "
                            + ", ".join(f"(x{h[0]:.0f},y{h[1]:.0f})" for h, _ in resolved))
            continue
        h, ln = resolved[0]
        out[logical] = {"x": ln["x0"] + 4, "y": ln["y1"] - 4, "line": ln}
    if problems:
        raise DiscoveryError("; ".join(problems))
    return out


def place_values(page, coords, signer, note, date=None, base_dir=""):
    """Overlay values at discovered/overridden coordinates. Returns list of what was written."""
    written = []
    dark = (0, 0, 0.55)
    def txt(key, s, size=11, italic=False):
        if key not in coords or not s: return
        x, y = coords[key]["x"], coords[key]["y"]
        page.insert_text((x, y), s, fontsize=size, fontname="heit" if italic else "helv", color=dark)
        written.append((key, s))
    txt("printed_name", signer.get("printed", ""))
    txt("company", signer.get("company", ""))
    if "signature" in coords:
        img = signer.get("signature_image", "")
        img_path = os.path.join(base_dir, img) if img and not os.path.isabs(img) else img
        c = coords["signature"]
        if img_path and os.path.exists(img_path):
            ln = c.get("line") or {"x0": c["x"] - 4, "x1": c["x"] + 150, "y1": c["y"] + 4}
            w = min(150, ln["x1"] - ln["x0"] - 8)
            pix = fitz.Pixmap(img_path); h = w * pix.height / max(pix.width, 1)
            page.insert_image(fitz.Rect(c["x"], c["y"] - h + 2, c["x"] + w, c["y"] + 2),
                              filename=img_path, keep_proportion=True, overlay=True)
            written.append(("signature", f"<image {os.path.basename(img_path)}>"))
        else:
            txt("signature", signer.get("typed_signature", ""), size=13, italic=True)
        if note:
            # note goes on the date line if present, else just right of the signature
            if "date" in coords and not date:
                nx, ny = coords["date"]["x"], coords["date"]["y"]
            else:
                nx, ny = c["x"] + 160, c["y"]
            page.insert_text((nx, ny), note, fontsize=7, fontname="helv", color=dark)
            written.append(("note", note))
    if date and "date" in coords:
        txt("date", date)
    return written


def sign(opp, form_key, out_path=None, date=None, coords_override=None):
    form = opp.form(form_key); signer = opp.get("signer", {})
    src = opp.resolve(form["path"])
    pno = int(form["page"]) - 1
    doc = fitz.open(src); page = doc[pno]
    if coords_override:
        coords = {k: {"x": v[0], "y": v[1]} for k, v in coords_override.items()}
    else:
        coords = discover(page, form["fields"])
    written = place_values(page, coords, signer, form.get("signature_note", ""), date=date,
                           base_dir=opp.base_dir)
    if not out_path:
        stem = re.sub(r"\.pdf$", "", os.path.basename(src))
        out_path = os.path.join(opp.folder("draft", create=True), f"{stem} (signed).pdf")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    doc.save(out_path); doc.close()
    return out_path, coords, written


def probe(opp, form_key):
    form = opp.form(form_key)
    doc = fitz.open(opp.resolve(form["path"])); page = doc[int(form["page"]) - 1]
    lines, words = page_geometry(page)
    print(f"page {form['page']} size {page.rect}")
    for ln in sorted(lines, key=lambda l: (l["y0"], l["x0"])):
        print(f"  LINE  x{ln['x0']:.0f}-{ln['x1']:.0f}  y{ln['y0']:.0f}-{ln['y1']:.0f}  len={ln['len']}")
    for logical, label in form["fields"].items():
        for h in find_label(words, label):
            ln = line_for_label(lines, h)
            tgt = f"-> line y{ln['y1']:.0f} baseline {ln['y1']-4:.0f}" if ln else "-> NO LINE ABOVE"
            print(f"  LABEL {logical:13s} {label!r:24s} at (x{h[0]:.0f}, y{h[1]:.0f}) {tgt}")
    doc.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cfg"); ap.add_argument("form")
    ap.add_argument("--out"); ap.add_argument("--date")
    ap.add_argument("--coords", help='JSON {"signature":[x,y],...} to bypass discovery')
    ap.add_argument("--probe", action="store_true")
    a = ap.parse_args(argv)
    opp = config.load(a.cfg)
    if a.probe:
        probe(opp, a.form); return 0
    try:
        out, coords, written = sign(opp, a.form, out_path=a.out, date=a.date,
                                    coords_override=json.loads(a.coords) if a.coords else None)
    except DiscoveryError as e:
        print(f"DISCOVERY FAILED for {a.form}: {e}")
        print("Run with --probe to see lines/labels, then pass --coords.")
        return 1
    print(f"{a.form}: signed -> {out}")
    for k, v in written: print(f"   {k:13s} {v}")
    if not a.date:
        print("   date          (left blank — dated on send day; original signature is a human step)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
