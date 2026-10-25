"""Tests for the one-time cross-folder dedup pass (bidkit.dedup).

The critical safety property: a cluster that only shares a GENERIC subject but differs on
number/due/anchor must be flagged 'review', never auto-merged (two genuinely different RFPs behind
one portal subject). Offline; no git required (apply_merge falls back to os.rename)."""
import json, os
from bidkit import dedup


def _opp(root, name, title, number="", domain="agency.example.gov", due="", anchor=None,
         research_files=0):
    d = root / name
    (d / "rfp").mkdir(parents=True)
    opp = {"id": name, "title": title, "solicitation_number": number,
           "source": {"from": f"alerts@{domain}", "message_id": f"<{name}@x>"},
           "due": {"date": due, "confirmed": bool(due)}}
    if anchor is not None:
        opp["value_estimate"] = {"anchor": anchor}
    (d / "opportunity.json").write_text(json.dumps(opp), encoding="utf-8")
    if research_files:
        (d / "research").mkdir()
        for i in range(research_files):
            (d / "research" / f"f{i}.md").write_text("x", encoding="utf-8")
    return d


def test_true_thread_duplicates_are_mergeable(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "20260914-FGA", "Re: [Priority!] FGA: New Opp (Due Sep 10)", domain="fga.example", due="2026-09-10")
    _opp(opps, "20260930-FGA", "FGA: New Opp (Due Sep 10)", domain="fga.example", due="2026-09-10", research_files=3)
    clusters = dedup.find_clusters(str(opps))
    assert len(clusters) == 1
    c = clusters[0]
    assert c["action"] == "merge"
    assert c["canonical"] == "20260930-FGA"           # richer folder is canonical
    assert c["duplicates"] == ["20260914-FGA"]


def test_generic_subject_different_numbers_is_review_not_merge(tmp_path):
    # the WEBS trap: same generic subject, genuinely different solicitations
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "101526-Turf", "WEBS Bidding Opportunity", number="101526", domain="des.wa.gov")
    _opp(opps, "2026_01-LE", "WEBS Bidding Opportunity", number="2026_01", domain="des.wa.gov")
    c = dedup.find_clusters(str(opps))[0]
    assert c["action"] == "review" and "different solicitation numbers" in c["reason"]


def test_different_due_dates_is_review(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a-rec", "Opportunity Recommendations - Portal", domain="notify.fga", due="2026-10-06")
    _opp(opps, "b-rec", "Opportunity Recommendations - Portal", domain="notify.fga", due="2026-10-20")
    c = dedup.find_clusters(str(opps))[0]
    assert c["action"] == "review" and "different due dates" in c["reason"]


def test_anchors_far_apart_is_review(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a-dup", "Breakdown for Opportunity: X", domain="fga", anchor=1104525)
    _opp(opps, "b-dup", "Breakdown for Opportunity: X", domain="fga", anchor=3600000)
    c = dedup.find_clusters(str(opps))[0]
    assert c["action"] == "review" and "anchors differ" in c["reason"]


def test_apply_folds_duplicates_into_canonical_followups(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "20260914-FGA", "FGA: New Opp (Due Sep 10)", domain="fga", due="2026-09-10")
    _opp(opps, "20260930-FGA", "FGA: New Opp (Due Sep 10)", domain="fga", due="2026-09-10", research_files=3)
    c = dedup.find_clusters(str(opps))[0]
    moved = dedup.apply_merge(str(opps), c)
    assert moved and not (opps / "20260914-FGA").exists()          # duplicate removed from top level
    assert (opps / "20260930-FGA" / "initial-email" / "followups" / "merged-20260914-FGA").is_dir()


def test_no_clusters_when_all_distinct(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", "Alpha RFP", number="A1")
    _opp(opps, "b", "Beta RFP", number="B2")
    assert dedup.find_clusters(str(opps)) == []
