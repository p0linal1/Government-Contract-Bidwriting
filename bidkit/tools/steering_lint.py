#!/usr/bin/env python3
"""
steering_lint.py — lint a steering series for (a) fact uniqueness and (b) valid front matter.

(a) Fact uniqueness: a list of "canonical facts" (identifiers, emails, phones, product claims)
    must each appear in EXACTLY ONE file — the canonical profile. Pointers by document name are
    fine; repeated VALUES are not. Prints any fact found in a non-canonical file.
(b) Front matter: file must begin with '---' on line 1; must declare `inclusion:` in
    {always, fileMatch, manual, auto}; `auto` requires `name:` and `description:`;
    `fileMatch` requires `fileMatchPattern:`. Also reports the always-on footprint (bytes).

Usage:
  python3 steering_lint.py --dir .kiro/steering --canonical company-profile.md \
      --facts XXXXXXXXXXXX XXXXX XX-XXXXXXX "XXX XXX XXX" ...
Exit 1 on any violation.
"""
import argparse, os, re, sys

def front_matter(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, "no front matter on line 1"
    try:
        end = lines.index("---", 1)
    except ValueError:
        return None, "unterminated front matter"
    fm = {}
    for ln in lines[1:end]:
        m = re.match(r"^\s*([A-Za-z_]+)\s*:\s*(.*)$", ln)
        if m: fm[m.group(1)] = m.group(2).strip()
    return fm, None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--canonical", required=True, help="filename that may contain the facts")
    ap.add_argument("--facts", nargs="*", default=[])
    ap.add_argument("--exclude", nargs="*", default=[], help="filenames to ignore (e.g. retired)")
    a = ap.parse_args()

    files = sorted(f for f in os.listdir(a.dir) if f.endswith(".md") and f not in a.exclude)
    texts = {f: open(os.path.join(a.dir, f), encoding="utf-8").read() for f in files}
    bad = 0

    print("== front matter ==")
    always_bytes = 0
    for f, t in texts.items():
        fm, err = front_matter(t)
        if err:
            print(f"  FAIL {f}: {err}"); bad += 1; continue
        inc = fm.get("inclusion", "always")
        if inc not in {"always", "fileMatch", "manual", "auto"}:
            print(f"  FAIL {f}: inclusion={inc!r}"); bad += 1
        if inc == "auto" and not (fm.get("name") and fm.get("description")):
            print(f"  FAIL {f}: auto requires name + description"); bad += 1
        if inc == "fileMatch" and not fm.get("fileMatchPattern"):
            print(f"  FAIL {f}: fileMatch requires fileMatchPattern"); bad += 1
        if inc == "always": always_bytes += len(t.encode("utf-8"))
        print(f"  ok   {f}: inclusion={inc}" + (f" name={fm.get('name')}" if inc == "auto" else ""))
    print(f"  always-on footprint: {always_bytes:,} bytes across "
          f"{sum(1 for f,t in texts.items() if (front_matter(t)[0] or {}).get('inclusion','always')=='always')} file(s)")

    print("\n== fact uniqueness ==")
    for fact in a.facts:
        where = [f for f, t in texts.items() if fact in t]
        if a.canonical not in where:
            print(f"  FAIL fact {fact!r} missing from canonical {a.canonical}"); bad += 1
        extra = [f for f in where if f != a.canonical]
        if extra:
            print(f"  FAIL fact {fact!r} also in: {extra}"); bad += 1
        else:
            print(f"  ok   {fact!r} only in {a.canonical}")

    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main()
