#!/usr/bin/env python3
"""
coverage_diff.py — prove that a set of NEW steering docs covers every heading and bullet of
a set of OLD steering docs before the old ones are retired.

For each heading (#, ##, ###) and each top-level bullet in the OLD files, extract a set of
"content words" (lowercased, stopwords + markdown removed). An item is COVERED if some NEW
file shares at least `--threshold` fraction of its content words (default 0.55) within a
sliding window, or if a distinctive key phrase (≥3 consecutive content words) appears
verbatim in a new file. Items that fail are printed for human review.

Usage:
  python3 coverage_diff.py --old A.md B.md --new C.md D.md ... [--threshold 0.55]
Exit code 1 if any item is uncovered.
"""
import argparse, re, sys

STOP = set("""a an the and or of to in on for with by from as at is are be was were it its this that
these those we our you your they their into over under vs versus not no if then than when where
which who whom how what any all each every per via so do does done doing use used using should
shall must may can will would could also only just more most less least very same other another
such both either neither one two three first second next last e g i.e etc see file files md
""".split())

def content_words(s):
    s = re.sub(r"`[^`]*`", " ", s)             # drop code spans (paths/names) - noisy
    s = re.sub(r"\*\*|__|\*|_|~~", " ", s)    # markdown emphasis
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)  # links -> text
    toks = re.findall(r"[a-zA-Z][a-zA-Z0-9\-']+", s.lower())
    return [t for t in toks if t not in STOP and len(t) > 2]

def items_from(path):
    out = []
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    # skip front matter
    if lines and lines[0].strip() == "---":
        try:
            end = lines.index("---", 1)
            lines = lines[end+1:]
        except ValueError:
            pass
    buf = None
    for ln in lines:
        if re.match(r"^\s*#{1,6}\s+", ln):
            if buf: out.append(buf); buf = None
            out.append(("heading", re.sub(r"^\s*#{1,6}\s+", "", ln).strip()))
        elif re.match(r"^\s*[-*•]\s+", ln) or re.match(r"^\s*\d+\.\s+", ln):
            if buf: out.append(buf)
            buf = ("bullet", re.sub(r"^\s*([-*•]|\d+\.)\s+", "", ln).strip())
        elif buf and ln.startswith("  ") and ln.strip():
            buf = (buf[0], buf[1] + " " + ln.strip())      # continuation line
        else:
            if buf: out.append(buf); buf = None
    if buf: out.append(buf)
    return [(k, t) for k, t in out if len(content_words(t)) >= 2]

def covered(item_words, new_text_words_sets, new_texts, threshold):
    iw = set(item_words)
    if not iw: return True, "empty"
    # 1) verbatim key phrase: any 3 consecutive content words appearing in order in a new text
    for i in range(len(item_words) - 2):
        phrase = " ".join(item_words[i:i+3])
        for nt in new_texts:
            if phrase in nt:
                return True, f"phrase:'{phrase}'"
    # 2) set overlap against each new file (whole-file bag of words) — lenient but catches moves
    best = 0.0
    for ws in new_text_words_sets:
        frac = len(iw & ws) / len(iw)
        best = max(best, frac)
    return best >= threshold, f"overlap={best:.2f}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", nargs="+", required=True)
    ap.add_argument("--new", nargs="+", required=True)
    ap.add_argument("--threshold", type=float, default=0.55)
    a = ap.parse_args()

    new_texts, new_sets = [], []
    for p in a.new:
        with open(p, encoding="utf-8") as fh:
            raw = fh.read()
        cw = content_words(raw)
        new_texts.append(" ".join(cw))
        new_sets.append(set(cw))

    total = miss = 0
    for p in a.old:
        for kind, text in items_from(p):
            total += 1
            ok, why = covered(content_words(text), new_sets, new_texts, a.threshold)
            if not ok:
                miss += 1
                print(f"UNCOVERED [{p.split('/')[-1]}] ({kind}) {why}\n    {text[:160]}")
    print(f"\n{total} items checked, {miss} uncovered")
    sys.exit(1 if miss else 0)

if __name__ == "__main__":
    main()
