#!/usr/bin/env python3
"""
opportunity_lint.py — enforce that an opportunity's canonical doc agrees with its derived
research artifacts (the write-back-consistency gate).

Why: research derives a better fact, but if `opportunity.json` is never updated and nothing
enforces agreement, a future session reads a stale fact and acts on it. That is exactly what
happened in the 2026-10-06 value-drift postmortem: `research/value-analysis.md` held the
correct ~$1.12M appropriation anchor while `opportunity.json` still led with a loose $2.6M
envelope. This linter FAILS when canonical and derived artifacts disagree, so an unattended run
surfaces drift instead of acting on it. It is the reconciliation-type gate in the evaluation
pipeline (spec Requirement 7) and is also usable standalone over the whole portfolio.

What it checks (each a registered check; a missing input ⇒ SKIP, not FAIL):
  value-consistency        opportunity.json value_estimate headline vs. research/value-analysis.md
  value-anchor-provenance  a value_estimate.anchor must carry an anchor_source
  due-provenance           due.confirmed==true must carry a due.source
  recommendation-consistency  opportunity-summary.md vs. research/go-no-go.md
  status-consistency       opportunity.json.status vs. the recommendation verb
  portal-record-consistency   opportunity.json.portal_record counts vs. rfp/portal-record.json vs. rfp/ files
  summary-cites-sources    (WARN) summary value/schedule lines should cite facts or a URL

Nothing company- or bid-specific lives here; all values are read from the opportunity folder
(gate: tests/test_no_hardcoding.py).

CLI:
  python3 -m bidkit.opportunity_lint <opp-dir> ...            # lint specific opportunities
  python3 -m bidkit.opportunity_lint --all <opportunities-dir>
  python3 -m bidkit.opportunity_lint ... [--json] [--warnings-as-errors]
Exit code: non-zero if any hard (FAIL) check failed.
"""
import argparse, json, os, re, sys

from .evaluation import EvalContext, GateResult, GateFinding, FAIL, WARN

SKIP = "skip"

# --------------------------------------------------------------------------- money normalizer
_MULT = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}
_MONEY_RE = re.compile(
    r"\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*([kmb])?\b", re.I)


def parse_money(text):
    """Return the first dollar amount in `text` as an int, or None. Handles $1.6M, 1,600,000,
    ~$1.12M, 1119683, $500k. Shared with the value-research gate. Accepts a number directly (an
    agent may write an int anchor) and coerces non-str/number inputs to str defensively so a
    malformed field never raises (P0 — the digest must not crash on an unexpected shape)."""
    if text is None:
        return None
    if isinstance(text, bool):
        return None
    if isinstance(text, (int, float)):
        return int(round(text)) if text >= 1000 else None
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return None
    m = _MONEY_RE.search(text)
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    suffix = (m.group(2) or "").lower()
    if suffix:
        num *= _MULT[suffix]
    elif num < 1000:
        # a bare small number with no suffix is almost never a contract value (e.g. "4 lines")
        return None
    return int(round(num))


def all_money(text):
    out = []
    if not text:
        return out
    for m in _MONEY_RE.finditer(text):
        num = float(m.group(1).replace(",", ""))
        suffix = (m.group(2) or "").lower()
        if suffix:
            num *= _MULT[suffix]
        elif num < 1000:
            continue
        out.append(int(round(num)))
    return out


# --------------------------------------------------------------------------- normalizer (P0)
# Canonical status verbs the deterministic tooling understands.
_STATUS_VERBS = ("bid", "conditional", "pass", "foothold", "partner")


def normalize_opportunity(opp):
    """Repair an opportunity dict into the shape the deterministic tooling parses, returning
    (normalized_opp, repairs). Pure: operates on a shallow copy, no I/O.

    The mode-c agent sometimes writes richer-but-wrong shapes — a DICT "recommendation", a prose
    "status", a sentence in the numeric "value_estimate.anchor". Those break re.search/int() in the
    readers. This coerces them WITHOUT losing information (prose is preserved into *_basis fields):
      - recommendation DICT  -> a short string (its verdict/summary), prose kept under
                                recommendation_detail
      - status not a canonical verb -> derived from the recommendation/verdict
      - value_estimate.anchor/low/likely/high as a string/sentence -> int via parse_money, the
                                original prose moved into anchor_basis/basis if that is empty
    Idempotent: a well-formed opportunity passes through unchanged with no repairs."""
    if not isinstance(opp, dict):
        return opp, []
    opp = dict(opp)
    repairs = []

    # --- recommendation: must be a short string -------------------------------------------------
    rec = opp.get("recommendation")
    if isinstance(rec, dict):
        opp["recommendation_detail"] = rec   # keep the full object for the record
        verb = None
        for k in ("verdict", "recommendation", "lean", "frame", "summary", "headline"):
            v = rec.get(k)
            if isinstance(v, str) and v.strip():
                verb = v.strip()
                break
        opp["recommendation"] = (verb or "")[:200]
        repairs.append("recommendation: coerced dict -> string (detail kept in recommendation_detail)")
    elif rec is not None and not isinstance(rec, str):
        opp["recommendation"] = str(rec)
        repairs.append("recommendation: coerced non-string -> string")

    # --- status: coerce only a NON-STRING or a prose SENTENCE; leave a short word (incl. transient
    #     statuses like 'intake'/'evaluated') alone — those are legitimate, not malformed.
    status = opp.get("status")
    is_prose = isinstance(status, str) and (len(status) > 24 or len(status.split()) > 3)
    if status is not None and (not isinstance(status, str) or is_prose):
        rec_str = opp.get("recommendation") if isinstance(opp.get("recommendation"), str) else None
        derived = (_canon_from(rec_str) if rec_str else None) \
            or parse_recommendation(opp.get("recommendation")) \
            or parse_recommendation(opp.get("recommendation_detail")) \
            or (_canon_from(status) if isinstance(status, str) else None)
        if derived:
            opp["status_detail"] = status if isinstance(status, str) else str(status)
            opp["status"] = derived
            repairs.append(f"status: '{opp['status_detail'][:40]}' -> canonical '{derived}'")

    # --- value_estimate numeric fields: must be ints -------------------------------------------
    ve = opp.get("value_estimate")
    if isinstance(ve, dict):
        ve = dict(ve)
        for field in ("anchor", "low", "likely", "high", "corridor_low", "corridor_high"):
            v = ve.get(field)
            if isinstance(v, str) and v.strip():
                n = parse_money(v)
                if n is not None:
                    # preserve the prose: anchor prose -> anchor_basis, else -> basis (if empty)
                    basis_key = "anchor_basis" if field == "anchor" else "basis"
                    if not ve.get(basis_key):
                        ve[basis_key] = v
                    ve[field] = n
                    repairs.append(f"value_estimate.{field}: prose '{v[:30]}' -> {n}")
                else:
                    ve[field] = None
                    repairs.append(f"value_estimate.{field}: unparseable prose -> null")
        opp["value_estimate"] = ve

    return opp, repairs


# --------------------------------------------------------------------------- parsers
# Ordered longest-first so "conditional bid" / "no-bid" win over the bare "bid" substring.
_REC_PATTERNS = [
    (r"no[-\s]?bid", "pass"),
    (r"qualified\s+bid", "conditional"),
    (r"conditional[-\s]?bid", "conditional"),
    (r"foothold", "foothold"),
    (r"partner", "partner"),
    (r"decline", "pass"),
    (r"pass", "pass"),
    (r"bid", "bid"),
]


def _canon_from(span):
    """Return the canonical verb from a short span of text (the recommendation line/paragraph).

    Picks the verb that appears EARLIEST in the span (closest to the 'Recommendation'/'Decision'
    cue), not the highest-priority pattern — because a recommendation block often mentions the
    rejected alternative later ('BID ... reversed the earlier PASS'), and the leading verb is the
    actual decision. Ties at the same position are broken by longest-match priority so
    'conditional bid' / 'no-bid' beat a bare 'bid'/'pass' starting at the same spot."""
    low = span.lower()
    best = None  # (position, -pattern_specificity, canon)
    for rank, (pat, canon) in enumerate(_REC_PATTERNS):
        m = re.search(r"\b" + pat + r"\b", low)
        if m:
            key = (m.start(), rank)   # earliest position wins; _REC_PATTERNS is ordered longest-first
            if best is None or key < best[0]:
                best = (key, canon)
    return best[1] if best else None


def parse_recommendation(text):
    """Extract a canonical recommendation verb (bid / pass / partner / conditional / foothold).

    Reads the RECOMMENDATION SECTION only — the text right after a 'Recommendation' header or an
    inline 'Recommendation:' / 'DECISION:' label — never a greedy whole-document scan (which would
    grab a stray 'pass'/'bid' from unrelated prose). Returns None if no recommendation section is
    found, so the linter SKIPs rather than guessing.

    Defensive (P0): accepts a non-string too. An agent sometimes writes opportunity.json
    "recommendation" as a DICT ({verdict, summary, ...}); rather than crash on re.finditer, pull the
    most verb-bearing string out of it (verdict/recommendation/summary/headline) and parse that."""
    if text is None:
        return None
    if isinstance(text, dict):
        for k in ("verdict", "recommendation", "lean", "frame", "summary", "headline", "reasoning"):
            v = text.get(k)
            if isinstance(v, str):
                canon = _canon_from(v) or parse_recommendation(v)
                if canon:
                    return canon
        return None
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return None
    # 1) a markdown header whose title contains Recommendation/Decision; scan the TITLE's own tail
    #    (after the cue word) first, then the following lines. The title tail is the strongest
    #    signal ('## Recommendation — BID'); the body only decides if the title carries no verb.
    for m in re.finditer(r"(?im)^\s*#{1,6}[^\n]*\b(?:recommendation|decision)\b([^\n]*)\n+((?:[^\n]+\n?){0,3})", text):
        canon = _canon_from(m.group(1)) or _canon_from(m.group(2))
        if canon:
            return canon
    # 2) an inline 'Recommendation: X' / 'DECISION: X' label (also matches '**Recommendation: PASS**'
    #    and 'Recommendation: **PASS** (decline)')
    for m in re.finditer(r"(?i)\b(?:recommendation|decision)\b\s*:?\s*\*{0,2}\s*([^\n]{0,80})", text):
        canon = _canon_from(m.group(1))
        if canon:
            return canon
    return None


def _tol(a, b, frac=0.15):
    """True if two dollar amounts agree within a tolerance (default 15%)."""
    if a is None or b is None:
        return True
    hi = max(abs(a), abs(b))
    return hi == 0 or abs(a - b) <= frac * hi


# --------------------------------------------------------------------------- checks
# Each check returns a GateFinding, or None to SKIP (inputs absent).

def check_value_consistency(ctx):
    opp = ctx.opportunity()
    va = ctx.text("research", "value-analysis.md")
    if not opp or "value_estimate" not in opp or not va:
        return None
    ve = opp["value_estimate"]
    cfg_headline = ve.get("anchor") or ve.get("likely")
    # the analysis headline: prefer an explicit anchor mention, else the "Likely $X" line
    anchor_m = re.search(r"anchor[^\n]*?(\$?\s*[0-9][0-9,.]*\s*[kmb]?)", va, re.I)
    likely_m = re.search(r"likely[^\n]*?(\$?\s*[0-9][0-9,.]*\s*[kmb]?)", va, re.I)
    doc_val = parse_money(anchor_m.group(1)) if anchor_m else None
    if doc_val is None and likely_m:
        doc_val = parse_money(likely_m.group(1))
    # Both sides agree there is NO headline figure (an honest UNKNOWN value estimate — e.g. a
    # document-only generated estimate on an opp with no dollar figure on file). That is CONSISTENT,
    # not drift: there is nothing to disagree about. Do not flag it.
    if cfg_headline is None and doc_val is None:
        return GateFinding("value-consistency", ok=True,
                           message="no headline figure on either side (consistent UNKNOWN)")
    # Exactly one side carries a figure the other lacks ⇒ a real extraction/write-back mismatch.
    if cfg_headline is None or doc_val is None:
        return GateFinding("value-consistency", ok=False, severity=FAIL,
                           message="could not extract a comparable headline from both config and value-analysis")
    if _tol(int(cfg_headline), doc_val):
        return GateFinding("value-consistency", ok=True,
                           message=f"config {int(cfg_headline):,} ~= analysis {doc_val:,}")
    return GateFinding("value-consistency", ok=False, severity=FAIL,
                       message=f"DRIFT: opportunity.json {int(cfg_headline):,} vs value-analysis {doc_val:,}",
                       evidence=f"anchor_source={ve.get('anchor_source','')[:80]}")


def check_value_anchor_provenance(ctx):
    opp = ctx.opportunity()
    if not opp or "value_estimate" not in opp:
        return None
    ve = opp["value_estimate"]
    if "anchor" not in ve:
        return None
    if ve.get("anchor_source"):
        return GateFinding("value-anchor-provenance", ok=True, message="anchor has a source")
    return GateFinding("value-anchor-provenance", ok=False, severity=FAIL,
                       message="value_estimate.anchor present without anchor_source")


def check_due_provenance(ctx):
    opp = ctx.opportunity()
    if not opp or "due" not in opp:
        return None
    due = opp["due"]
    if not due.get("confirmed"):
        return GateFinding("due-provenance", ok=True, severity=WARN,
                           message="due not confirmed (ok at intake; must be confirmed before bid)")
    if due.get("source"):
        return GateFinding("due-provenance", ok=True, message="confirmed due date has a source")
    return GateFinding("due-provenance", ok=False, severity=FAIL,
                       message="due.confirmed=true but no due.source")


def check_recommendation_consistency(ctx):
    summ = parse_recommendation(ctx.text("opportunity-summary.md"))
    gng = parse_recommendation(ctx.text("research", "go-no-go.md"))
    if summ is None or gng is None:
        return None
    if summ == gng:
        return GateFinding("recommendation-consistency", ok=True,
                           message=f"summary and go-no-go agree ({summ})")
    return GateFinding("recommendation-consistency", ok=False, severity=FAIL,
                       message=f"summary says {summ} but go-no-go says {gng}")


def check_status_consistency(ctx):
    opp = ctx.opportunity()
    if not opp or not opp.get("status"):
        return None
    status = opp["status"].lower()
    rec = parse_recommendation(ctx.text("opportunity-summary.md")) \
        or parse_recommendation(opp.get("recommendation") or "")
    if rec is None:
        return None
    rec_pass = rec == "pass"
    pass_status = status in ("pass", "no-bid", "dropped", "lost")
    proceed_status = status in ("bid", "won", "submitted")
    # 'intake'/'evaluated'/'ready' etc. are transient — a decision has not been committed to status
    # yet, so they cannot contradict a recommendation. Only a COMMITTED status can.
    if not pass_status and not proceed_status:
        return GateFinding("status-consistency", ok=True, severity=WARN,
                           message=f"status '{status}' is transient; recommendation is '{rec}' (commit status when decided)")
    contradiction = (pass_status and not rec_pass) or (proceed_status and rec_pass)
    if contradiction:
        return GateFinding("status-consistency", ok=False, severity=FAIL,
                           message=f"status '{status}' contradicts recommendation '{rec}'")
    return GateFinding("status-consistency", ok=True,
                       message=f"status '{status}' consistent with recommendation '{rec}'")


def check_portal_record_consistency(ctx):
    opp = ctx.opportunity()
    pr = ctx.json("rfp", "portal-record.json")
    if not opp or "portal_record" not in opp or not pr:
        return None
    rec = pr[0] if isinstance(pr, list) else pr
    cfg = opp["portal_record"]
    docs = rec.get("documents") or []
    amds = rec.get("amendments") or []
    problems = []
    if "documents" in cfg and cfg["documents"] != len(docs):
        problems.append(f"documents: json says {cfg['documents']}, portal-record has {len(docs)}")
    if "amendments" in cfg and cfg["amendments"] != len(amds):
        problems.append(f"amendments: json says {cfg['amendments']}, portal-record has {len(amds)}")
    # cross-check named files actually exist in rfp/
    present = set(ctx.rfp_files())
    named = [d.get("name") for d in list(docs) + list(amds) if d.get("name")]
    missing = [n for n in named if n and n.replace("'", "_") not in present and n not in present]
    if missing:
        problems.append(f"{len(missing)} portal-record file(s) not found in rfp/: {missing[:3]}")
    if problems:
        return GateFinding("portal-record-consistency", ok=False, severity=FAIL,
                           message="; ".join(problems))
    return GateFinding("portal-record-consistency", ok=True,
                       message=f"{len(docs)} docs + {len(amds)} amendments reconcile")


def check_summary_cites_sources(ctx):
    summ = ctx.text("opportunity-summary.md")
    if not summ:
        return None
    offenders = []
    for line in summ.splitlines():
        # a line that asserts a dollar value should cite a source or facts reference
        if all_money(line):
            has_cite = bool(re.search(r"https?://|opportunity-facts|research/|RFP|Section|p\.?\s?\d", line, re.I))
            if not has_cite:
                offenders.append(line.strip()[:70])
    if offenders:
        return GateFinding("summary-cites-sources", ok=False, severity=WARN,
                           message=f"{len(offenders)} value line(s) without a visible source",
                           evidence=offenders[0])
    return GateFinding("summary-cites-sources", ok=True, message="value lines cite sources")


CHECKS = [
    check_value_consistency,
    check_value_anchor_provenance,
    check_due_provenance,
    check_recommendation_consistency,
    check_status_consistency,
    check_portal_record_consistency,
    check_summary_cites_sources,
]


# --------------------------------------------------------------------------- gate entry point
def lint(ctx):
    """Run every check; return a GateResult. Skipped checks (absent inputs) are omitted."""
    res = GateResult("write-back-consistency")
    for fn in CHECKS:
        finding = fn(ctx)
        if finding is not None:
            res.add(finding)
    return res


def gate(ctx):
    """Pipeline entry point (reconciliation gate)."""
    return lint(ctx)


def lint_dir(opp_dir):
    return lint(EvalContext(opp_dir))


def normalize_dir(opp_dir):
    """Read opportunity.json, normalize it, and PERSIST the repair to disk if anything changed.
    Returns the list of repairs (empty if already clean). Used by the prep pass and the one-time
    backlog-repair CLI (P0d). Idempotent."""
    p = os.path.join(opp_dir, "opportunity.json")
    if not os.path.exists(p):
        return []
    try:
        raw = json.load(open(p, encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    norm, repairs = normalize_opportunity(raw)
    if repairs:
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(norm, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
    return repairs


# --------------------------------------------------------------------------- CLI
def _iter_opps(args):
    if args.all:
        root = args.all
        for name in sorted(os.listdir(root)):
            p = os.path.join(root, name)
            if os.path.isdir(p) and not name.startswith(".") and name not in ("_template", "sourcing"):
                if os.path.exists(os.path.join(p, "opportunity.json")):
                    yield p
    for p in args.opps:
        yield p


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("opps", nargs="*", help="opportunity folders")
    ap.add_argument("--all", metavar="DIR", help="lint every opportunity under DIR")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--warnings-as-errors", action="store_true")
    ap.add_argument("--normalize", action="store_true",
                    help="repair opportunity.json shapes (dict recommendation, prose anchor, etc.) in place")
    a = ap.parse_args(argv)
    if not a.opps and not a.all:
        ap.error("pass opportunity folders or --all <dir>")

    if a.normalize:
        total = 0
        for opp in _iter_opps(a):
            reps = normalize_dir(opp)
            if reps:
                total += 1
                print(f"[normalized] {os.path.basename(opp.rstrip('/'))}")
                for r in reps:
                    print(f"   - {r}")
        print(f"normalized {total} opportunity file(s)")
        return 0

    results = {}
    for opp in _iter_opps(a):
        try:
            results[os.path.basename(opp.rstrip("/"))] = lint_dir(opp)
        except Exception as e:  # noqa: BLE001 — one bad folder must not abort the sweep
            r = GateResult(os.path.basename(opp.rstrip("/")))
            r.add(GateFinding("load", ok=False, severity=FAIL, message=f"error: {e}"))
            results[os.path.basename(opp.rstrip("/"))] = r

    any_fail = False
    if a.json:
        print(json.dumps({k: v.to_dict() for k, v in results.items()}, indent=2))
    for name, res in results.items():
        hard = [f for f in res.findings if f.blocking_failure]
        warns = [f for f in res.findings if (not f.ok) and f.severity == WARN]
        if hard or (a.warnings_as_errors and warns):
            any_fail = True
        if not a.json:
            status = "FAIL" if hard else ("WARN" if warns else "ok")
            print(f"[{status}] {name}  ({len(res.findings)} checks)")
            for f in res.findings:
                if not f.ok:
                    mark = "!!" if f.blocking_failure else "~ "
                    print(f"   {mark} {f.check}: {f.message}")
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
