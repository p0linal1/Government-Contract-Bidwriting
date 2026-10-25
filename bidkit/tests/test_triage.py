from bidkit import triage

CRIT = {"naics": ["541511", "541519", "518210"], "vary_last_digits": 1}


def row(title, naics="541511", psc="7A20", low=None, high=None, due="2027-01-01", opp_type="Solicitation", summary=""):
    return {"id": "x", "source_id": "SRC", "title": title, "agency": "Agency", "naics": naics, "psc": psc,
            "value_low": low, "value_high": high, "due": due, "opp_type": opp_type, "summary": summary,
            "url": "http://x"}


def verdict_of(r):
    scored, _ = triage.triage_rows([r], CRIT, today=None)
    return scored[0]


def test_value_scoring_and_sources():
    # sweet spot
    s = triage.score_value(row("x", high=1_000_000), triage.DEFAULT_TRIAGE)
    assert s[0] == 5 and "FGA estimate" in s[1] and s[2] == "MEDIUM"
    # too large → low score, and the note says why
    s = triage.score_value(row("x", high=200_000_000), triage.DEFAULT_TRIAGE)
    assert s[0] == 1 and "too large" in s[3]
    # no estimate → medium score, LOW confidence, source says so
    s = triage.score_value(row("x"), triage.DEFAULT_TRIAGE)
    assert s[0] == 3 and s[2] == "LOW" and "no FGA estimate" in s[1]
    # sub-threshold
    assert triage.score_value(row("x", high=10_000), triage.DEFAULT_TRIAGE)[0] == 2


def test_eligibility_strong_vs_generic_vs_negative():
    # strong custom-software signal on a core NAICS → 5
    assert triage.score_eligibility(row("Custom Application Development"), CRIT, triage.DEFAULT_TRIAGE)[0] == 5
    # generic software word only → 3 (borderline)
    assert triage.score_eligibility(row("Records Management System"), CRIT, triage.DEFAULT_TRIAGE)[0] == 3
    # non-software title → capped low even on a software NAICS
    assert triage.score_eligibility(row("Server Backup Services"), CRIT, triage.DEFAULT_TRIAGE)[0] <= 2
    assert triage.score_eligibility(row("Hedge Trimming and Landscaping"), CRIT, triage.DEFAULT_TRIAGE)[0] == 1
    # summary must NOT trigger a keep (thin/noisy) — title is generic, summary has "implement"
    e = triage.score_eligibility(row("Server Backup Services", summary="vendor will implement backups"), CRIT, triage.DEFAULT_TRIAGE)
    assert e[0] <= 2


def test_verdicts_auto_reject_and_keep():
    assert verdict_of(row("Custom Software Development Platform", high=1_000_000))["verdict"] == "keep"
    assert verdict_of(row("Enterprise System Modernization", high=2_000_000))["verdict"] == "keep"
    # mega-contract → reject regardless of great fit
    assert verdict_of(row("Custom Software Development", high=200_000_000))["verdict"] == "reject"
    # out of scope → reject
    assert verdict_of(row("Tree Removal and Hedge Trimming", naics="561730", high=100_000))["verdict"] == "reject"
    # closed → reject
    assert verdict_of(row("Custom Development", high=500_000, due="2020-01-01"))["verdict"] == "reject"
    # award notice type → reject
    assert verdict_of(row("Custom Development", high=500_000, opp_type="Award Notice"))["verdict"] == "reject"
    # generic + value present → borderline (not auto-anything)
    assert verdict_of(row("Records Management System", high=500_000))["verdict"] == "borderline"


def test_confidence_capped_at_medium():
    # a shallow title-level screen must never claim HIGH confidence
    scored, _ = triage.triage_rows([row("Custom Application Development", high=1_000_000)], CRIT)
    s = scored[0]
    assert s["value_conf"] in ("LOW", "MEDIUM") and s["elig_conf"] in ("LOW", "MEDIUM")


def test_naics_on_seed_uses_only_criteria_codes():
    # 541512 shares all-but-last-digit with seed 541511 → on-seed via widening
    assert triage.naics_on_seed("541512", CRIT) is True
    assert triage.naics_on_seed("541511", CRIT) is True
    # 561730 (landscaping) is nowhere near a seed
    assert triage.naics_on_seed("561730", CRIT) is False
