#!/usr/bin/env python3
"""
pdf_redact.py — scrub personal contact info from a resume PDF by TRUE redaction and overlay a
company email in its place.

Why: bid resumes for named staff must not leak personal emails/phones/GitHub/LinkedIn, and a
white box over the text is NOT a redaction — the original string stays in the content stream
and is extractable (and searchable by the agency). PyMuPDF's add_redact_annot +
apply_redactions physically removes the glyphs. The historical scrubber needed a hand-written
needle list per resume; this one AUTO-DETECTS emails, phone numbers, and profile/personal URLs,
so a new resume needs no per-file code.

Behaviour:
  - detects: emails; phone numbers (US/intl formats); URLs and bare domains for linkedin.com,
    github.com, gitlab.com, twitter/x.com, medium.com, personal sites (any http(s):// or www.);
  - redacts every hit; overlays `<firstname>@<domain>` at the FIRST email hit's position
    (or, if the resume had no email, just right of the name line);
  - --keep-contact: redact nothing (used for the principal, who keeps real contact);
  - --keep <substring>...: do not redact strings containing these (e.g. an already-correct
    company email);
  - verifies afterwards that no detected needle survives in the extracted text.

CLI:
  python3 -m bidkit.pdf_redact <resume.pdf> --firstname <name> --cfg <opportunity.json>
        [--out FILE] [--keep-contact] [--keep STR ...] [--dry-run]
  (domain comes from config redact.domain; --domain overrides)
"""
import argparse, os, re, sys
import fitz
from . import config

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}\b")
URL_RE = re.compile(r"(?:https?://|www\.)[^\s|,;)]+", re.I)
PROFILE_RE = re.compile(r"\b(?:[a-z0-9-]+\.)?(?:linkedin\.com|github\.com|gitlab\.com|twitter\.com|x\.com|"
                        r"medium\.com|behance\.net|dribbble\.com|stackoverflow\.com)/[^\s|,;)]+", re.I)


def detect(text):
    """Return a set of contact strings found in text (emails, phones, urls, profiles)."""
    hits = set()
    hits.update(EMAIL_RE.findall(text))
    hits.update(m.group(0).strip() for m in PHONE_RE.finditer(text))
    hits.update(URL_RE.findall(text))
    hits.update(PROFILE_RE.findall(text))
    # strip trailing punctuation that regexes may swallow
    return {h.rstrip(".,;:)|") for h in hits if len(h.rstrip(".,;:)|")) >= 7}


def scrub(src, out, replacement_email, keep=(), keep_contact=False, dry_run=False):
    """Returns dict(removed=[...], kept=[...], replacement_at=(page, rect) or None, survivors=[...])."""
    doc = fitz.open(src)
    full = "".join(p.get_text() for p in doc)
    needles = detect(full)
    kept = sorted(n for n in needles if any(k and k in n for k in keep) or n == replacement_email)
    targets = sorted(n for n in needles if n not in kept)
    result = {"removed": [], "kept": kept, "replacement_at": None, "survivors": []}
    if keep_contact or not targets:
        if not dry_run and out != src:
            doc.save(out)
        doc.close()
        result["kept"] = sorted(needles)
        return result
    # locate first email for replacement position
    first_email = None
    for pno, page in enumerate(doc):
        for n in targets:
            if EMAIL_RE.fullmatch(n):
                rects = page.search_for(n)
                if rects:
                    first_email = (pno, rects[0]); break
        if first_email: break
    for pno, page in enumerate(doc):
        for n in targets:
            for r in page.search_for(n):
                page.add_redact_annot(r, fill=(1, 1, 1))
                result["removed"].append((pno + 1, n))
    if dry_run:
        doc.close(); return result
    for page in doc:
        page.apply_redactions()
    if first_email:
        pno, r = first_email
        fs = max(8.0, min(11.0, r.height * 0.9))
        doc[pno].insert_text((r.x0, r.y1 - 2), replacement_email, fontsize=fs, fontname="helv",
                             color=(0, 0, 0.55))
        result["replacement_at"] = (pno + 1, tuple(round(v, 1) for v in r))
    doc.save(out); doc.close()
    # verify
    after = "".join(p.get_text() for p in fitz.open(out))
    result["survivors"] = sorted(n for n in targets if n in after)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf"); ap.add_argument("--firstname", required=True)
    ap.add_argument("--cfg"); ap.add_argument("--domain")
    ap.add_argument("--out"); ap.add_argument("--keep-contact", action="store_true")
    ap.add_argument("--keep", nargs="*", default=[]); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    domain = a.domain or (config.load(a.cfg)["redact"]["domain"] if a.cfg else None)
    if not domain:
        print("need --domain or --cfg with redact.domain"); return 2
    repl = f"{a.firstname.lower()}@{domain}"
    out = a.out or re.sub(r"\.pdf$", "", a.pdf) + " (scrubbed).pdf"
    res = scrub(a.pdf, out, repl, keep=a.keep, keep_contact=a.keep_contact, dry_run=a.dry_run)
    print(f"{os.path.basename(a.pdf)} -> {out if not a.dry_run else '(dry run)'}")
    for p, n in res["removed"]: print(f"   removed p{p}: {n}")
    for n in res["kept"]: print(f"   kept:        {n}")
    if res["replacement_at"]: print(f"   overlay {repl} at p{res['replacement_at'][0]}")
    if res["survivors"]:
        print(f"   FAIL survivors still extractable: {res['survivors']}"); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
