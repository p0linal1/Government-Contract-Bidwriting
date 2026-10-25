#!/usr/bin/env python3
"""
triage.py — score sourced FGA candidates on VALUE and ELIGIBILITY (each with a source + a
confidence), auto-reject obvious no-matches, and emit a triage queue so only worthwhile RFPs
graduate to the human evaluation queue.

Why: `bidkit.fga search` returns hundreds of open matches. Most are noise — mega-contracts a
small firm cannot perform as prime, out-of-scope buys that slipped through the code net,
sub-threshold nibbles not worth a formal bid. This does a SHALLOW first-pass score using ONLY
the data the sourcing record already carries (title, NAICS/PSC, FGA's value estimate, opp type,
short summary) so a human can skim a ranked list instead of 600 rows. It is NOT the deep
go/no-go: a "keep" here means "worth the deep four-line value triangulation" (bid-intake step
4b), so its confidence is honestly capped at MEDIUM.

Every score carries its SOURCE and a CONFIDENCE (LOW / MEDIUM / HIGH), matching the vocabulary in
bid-intake. Nothing company-specific is hard-coded: value thresholds come from the criteria file's
`triage` block, eligibility codes from the criteria's own NAICS/PSC seeds (a test enforces this).

Inputs : the sourcing rows (opportunities/sourcing/fga/latest.json) + the criteria file
CLI    : python3 -m bidkit.triage --rows <latest.json> --criteria <sourcing.json> --out <dir>
"""
import argparse, csv, datetime as dt, json, os, re, sys

# --- default VALUE thresholds (dollars); overridable via criteria["triage"] ---
DEFAULT_TRIAGE = {
    "min_worthwhile": 50_000,       # below this a formal bid isn't worth it → value score low
    "sweet_low": 50_000,            # sweet spot band (high value score)
    "sweet_high": 5_000_000,
    "teaming_high": 20_000_000,     # sweet_high..teaming_high = large, needs teaming (borderline)
    "too_large": 20_000_000,        # at/above this → auto-reject (cannot perform as small prime)
    # STRONG signals = clear custom software work (development/build/implementation/migration).
    "strong_title_patterns": [
        r"\bdevelop\w*", r"\bcustom\b", r"\bapplication development\b", r"\bsoftware development\b",
        r"\bmodern\w*", r"\bimplement\w*", r"\bintegrat\w*", r"\bmigrat\w*",
        r"\bapplication (?:maintenance|support)\b", r"\bsoftware (?:maintenance|support)\b",
        r"\bsystem (?:replacement|modernization|configuration)\b", r"\bdata (?:conversion|migration)\b",
        r"\bweb (?:app|application|portal|site) development\b", r"\bapi\b",
    ],
    # WEAK signals = software-adjacent but generic (a COTS renewal can carry these). Not enough for KEEP.
    "weak_title_patterns": [
        r"\bsaas\b", r"\bcloud\b", r"\bplatform\b", r"\bsoftware\b", r"\bsystem\b",
        r"\bweb (?:app|application|portal|site)\b", r"\bhelp ?desk\b", r"\bmanagement system\b",
    ],
    "negative_title_patterns": [
        r"\bhardware\b", r"\bequipment\b", r"\bappliance\b", r"\bfurniture\b", r"\bvehicle\b",
        r"\blandscap\w*", r"\bjanitorial\b", r"\bconstruction\b", r"\broofing\b", r"\bhvac\b",
        r"\bfood\b", r"\buniform\b", r"\bfuel\b", r"\bmowing\b", r"\btree\b", r"\bhedge\b",
        r"\bbackup services\b", r"\bLAN\b", r"\bnetwork\b", r"\bstorage\b", r"\bsupport\b renewal",
    ],
    "reject_opp_types": ["Award Notice", "Sale of Surplus Property", "Justification"],
}


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def get_rows(rows_obj):
    return rows_obj["rows"] if isinstance(rows_obj, dict) and "rows" in rows_obj else rows_obj


def seed_naics(criteria):
    """The on-target NAICS set = the criteria's own seeds (widened by last digit like the search)."""
    seeds = set()
    for code in criteria.get("naics", []):
        seeds.add(code)
        if criteria.get("vary_last_digits"):
            seeds.add(code[:-1] + "x")   # prefix marker; membership test below handles it
    return {c for c in seeds}


def naics_on_seed(naics, criteria):
    """True if this NAICS matches a seed, or shares all-but-last-digit with a seed (the search's own
    widening rule). Uses ONLY the criteria's codes — nothing hard-coded."""
    if not naics:
        return False
    for code in criteria.get("naics", []):
        if naics == code:
            return True
        if criteria.get("vary_last_digits") and len(naics) == len(code) and naics[:-1] == code[:-1]:
            return True
    return False


def fmt_money(low, high):
    def m(v):
        if v is None:
            return None
        return f"${v/1e6:.1f}M" if v >= 1e6 else f"${v/1e3:.0f}k"
    lo, hi = m(low), m(high)
    if lo and hi and lo != hi:
        return f"{lo}–{hi}"
    return hi or lo or "no estimate"


def score_value(row, tri):
    """(score 1-5, source, confidence, note). Source is FGA's estimate — never the agency's figure."""
    high = row.get("value_high")
    low = row.get("value_low")
    if high is None and low is None:
        return 3, "no FGA estimate", "LOW", "no value published by FGA — size unknown"
    v = high or low
    src = "FGA estimate (not the agency's figure)"
    if v >= tri["too_large"]:
        return 1, src, "MEDIUM", f"{fmt_money(low, high)} — too large to perform as a small prime"
    if v >= tri["teaming_high"]:
        return 2, src, "LOW", f"{fmt_money(low, high)} — large; would require teaming"
    if v < tri["min_worthwhile"]:
        return 2, src, "MEDIUM", f"{fmt_money(low, high)} — below the worthwhile-bid threshold"
    if tri["sweet_low"] <= v <= tri["sweet_high"]:
        return 5, src, "MEDIUM", f"{fmt_money(low, high)} — in the sweet spot"
    return 4, src, "MEDIUM", fmt_money(low, high)


def score_eligibility(row, criteria, tri):
    """(score 1-5, source, confidence, note) — can the firm actually perform this?
    Signals: NAICS on-seed (core software), positive/negative title patterns. Summary is a weak
    bonus only (FGA summaries are thin). Confidence capped at MEDIUM (title-level, pre-RFP)."""
    # Match on the TITLE ONLY. FGA summaries are thin and noisy — letting them trigger a KEEP
    # produced false positives (a "Server Backup" summary contains "implement"), so the summary is
    # not used for scoring (calibration finding).
    title = (row.get("title") or "").lower()
    on_seed = naics_on_seed(row.get("naics"), criteria)
    strong = [p for p in tri["strong_title_patterns"] if re.search(p, title, re.I)]
    weak = [p for p in tri["weak_title_patterns"] if re.search(p, title, re.I)]
    neg = [p for p in tri["negative_title_patterns"] if re.search(p, title, re.I)]
    srcs = []
    if row.get("naics"):
        srcs.append(f"NAICS {row['naics']}{' (on-seed)' if on_seed else ' (off-seed)'}")
    if row.get("psc"):
        srcs.append(f"PSC {row['psc']}")
    if strong:
        srcs.append("title: custom-software signal")
    elif weak:
        srcs.append("title: generic software signal")
    if neg:
        srcs.append("title: non-software signal")
    source = "; ".join(srcs) or "codes only"

    # A non-software signal in the title CAPS eligibility even if a software word is also present
    # (e.g. "Server Backup Services", "Hyperflex LAN Renewal") — these are infra/hardware buys.
    if neg:
        return (2, source, "LOW", "non-software signal in title (infra/hardware) — likely out of scope") \
            if strong else (1, source, "MEDIUM", "non-software scope (hardware/infra/landscaping/etc.)")
    # KEEP-worthy (5) only with a clear custom-software signal on a core NAICS
    if on_seed and strong:
        return 5, source, "MEDIUM", "core software NAICS + custom-software scope in title"
    if strong:
        return 4, source, "MEDIUM", "custom-software signal (off-seed NAICS — confirm scope)"
    # generic software word only: plausible but not clearly custom work → borderline territory
    if on_seed or weak:
        return 3, source, "LOW", "generic software signal — read the RFP to confirm it's custom work"
    return 2, source, "LOW", "off-seed NAICS, no software signal in title"


def verdict(vs, es, row, tri, today=None):
    """keep | borderline | reject, with a one-line reason. Auto-rejects the obvious no-matches."""
    today = today or dt.date.today()
    # closed?
    due = row.get("due")
    if due:
        try:
            if dt.date.fromisoformat(due) < today:
                return "reject", "closed (due date passed)"
        except ValueError:
            pass
    if (row.get("opp_type") or "") in tri["reject_opp_types"]:
        return "reject", f"opportunity type: {row['opp_type']}"
    if es <= 1:
        return "reject", "out of scope — the firm cannot perform this work"
    if vs <= 1:
        return "reject", "too large to perform as a small prime"
    # keep = both axes clearly positive; borderline otherwise
    if vs >= 4 and es >= 4:
        return "keep", "worthwhile value + eligible — evaluate deeply"
    if vs >= 3 and es >= 3:
        return "borderline", "plausible but mixed signals — skim before evaluating"
    return "borderline", "weak on value or eligibility — low priority"


def triage_rows(rows, criteria, today=None):
    tri = dict(DEFAULT_TRIAGE, **(criteria.get("triage") or {}))
    out = []
    for r in rows:
        vs, vsrc, vconf, vnote = score_value(r, tri)
        es, esrc, econf, enote = score_eligibility(r, criteria, tri)
        vd, reason = verdict(vs, es, r, tri, today=today)
        out.append({
            "row": r, "value_score": vs, "value_source": vsrc, "value_conf": vconf, "value_note": vnote,
            "elig_score": es, "elig_source": esrc, "elig_conf": econf, "elig_note": enote,
            "verdict": vd, "reason": reason,
        })
    # rank: keep first, then borderline, then reject; within a tier by (value+elig) desc, due asc
    tier = {"keep": 0, "borderline": 1, "reject": 2}
    out.sort(key=lambda x: (tier[x["verdict"]], -(x["value_score"] + x["elig_score"]),
                            x["row"].get("due") or "9999"))
    return out, tri


# ----------------------------------------------------------------------------- writers
CSV_COLS = ["priority", "verdict", "fga_id", "title", "agency", "source", "solicitation_number",
            "due_date", "value_est", "value_score", "value_source", "value_confidence",
            "eligibility_score", "eligibility_source", "eligibility_confidence", "reason",
            "url", "notes"]


def write_csv(scored, path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_COLS)
        for i, s in enumerate(scored, 1):
            r = s["row"]
            w.writerow([
                i, s["verdict"], r.get("source_id") or r.get("id"), r.get("title", ""),
                r.get("agency", ""), "FGA", r.get("source_id", ""), r.get("due") or "",
                fmt_money(r.get("value_low"), r.get("value_high")), s["value_score"],
                s["value_source"], s["value_conf"], s["elig_score"], s["elig_source"],
                s["elig_conf"], s["reason"], r.get("url", ""),
                f"value: {s['value_note']} | eligibility: {s['elig_note']}",
            ])


def write_md(scored, tri, path, when=None):
    when = (when or dt.datetime.now()).strftime("%Y-%m-%d")
    keep = [s for s in scored if s["verdict"] == "keep"]
    bord = [s for s in scored if s["verdict"] == "borderline"]
    rej = [s for s in scored if s["verdict"] == "reject"]
    L = [f"# Sourcing triage — {when}", "",
         f"_First-pass score of {len(scored)} FGA sourcing candidates on **value** and **eligibility**, "
         f"each with a source and a confidence (LOW/MEDIUM/HIGH). This is a SHALLOW screen on FGA's own "
         f"data — a **keep** means 'worth the deep four-line value triangulation' (bid-intake step 4b), "
         f"not a go/no-go. Value = FGA's estimate, never the agency's figure. Promote a keeper with "
         f"`bin/bid-file.sh <fga_id>`, which files it for full intake and it then appears in "
         f"`evaluation-queue.csv`. Machine-readable: `inbox/sourcing-queue.csv`._", "",
         f"**{len(keep)} keep · {len(bord)} borderline · {len(rej)} reject** "
         f"(auto-reject: value ≥ ${tri['too_large']/1e6:.0f}M, out-of-scope, closed, or non-competition type).", ""]

    def rowline(s):
        r = s["row"]
        t = (r.get("title") or "")[:70].replace("|", "/")
        return (f"| [{t}]({r.get('url','')}) | {(r.get('agency') or '')[:28]} | {r.get('due') or ''} | "
                f"{fmt_money(r.get('value_low'), r.get('value_high'))} | {s['value_score']}/{s['value_conf']} | "
                f"{s['elig_score']}/{s['elig_conf']} | {s['reason']} |")

    hdr = ["| Title | Agency | Due | FGA value | Value (score/conf) | Elig (score/conf) | Reason |",
           "|---|---|---|---|---|---|---|"]
    L += [f"## KEEP — evaluate deeply ({len(keep)})", ""] + hdr + [rowline(s) for s in keep] + [""]
    L += [f"## BORDERLINE — skim first ({len(bord)})", ""] + hdr + [rowline(s) for s in bord] + [""]
    L += [f"## REJECT — auto-screened ({len(rej)})", "",
          "_Grouped reasons; full rows in the CSV._", ""]
    from collections import Counter
    rc = Counter(s["reason"] for s in rej)
    L += [f"- {reason}: {n}" for reason, n in rc.most_common()]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Score FGA sourcing candidates for triage.")
    ap.add_argument("--rows", required=True, help="sourcing rows JSON (fga latest.json)")
    ap.add_argument("--criteria", required=True, help="sourcing.json (thresholds + NAICS/PSC seeds)")
    ap.add_argument("--out", default="inbox", help="dir for sourcing-queue.csv/.md")
    ap.add_argument("--keep-only", action="store_true", help="CSV only keeps non-reject rows")
    a = ap.parse_args(argv)
    rows = get_rows(load_json(a.rows))
    criteria = load_json(a.criteria)
    scored, tri = triage_rows(rows, criteria)
    os.makedirs(a.out, exist_ok=True)
    csv_rows = [s for s in scored if not (a.keep_only and s["verdict"] == "reject")]
    write_csv(csv_rows, os.path.join(a.out, "sourcing-queue.csv"))
    write_md(scored, tri, os.path.join(a.out, "sourcing-queue.md"))
    from collections import Counter
    c = Counter(s["verdict"] for s in scored)
    print(f"triaged {len(scored)} → keep {c['keep']}, borderline {c['borderline']}, reject {c['reject']}")
    print(f"wrote {os.path.join(a.out, 'sourcing-queue.csv')} and .md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
