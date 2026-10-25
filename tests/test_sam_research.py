"""Offline tests for the SAM.gov research scripts. No network: SAM calls are never made."""

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import fetch_sam_opportunities as fetch  # noqa: E402
import filter_open  # noqa: E402
import render_report  # noqa: E402
import scores  # noqa: E402


def iso(days):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def notice(notice_id, **over):
    row = {
        "notice_id": notice_id,
        "title": f"Notice {notice_id}",
        "notice_type": "Solicitation",
        "response_date": iso(10),
        "modified_date": "2026-10-01T00:00:00+00:00",
        "is_canceled": False,
        "set_aside": "NONE",
        "award": None,
        "url": f"https://sam.gov/opp/{notice_id}/view",
    }
    row.update(over)
    return row


def run_filter(tmp_path, rows, profile=None, *extra):
    pull = tmp_path / "opportunities.json"
    pull.write_text(
        json.dumps(
            {"fetched_at": "2026-10-25T00:00:00+00:00", "profile": profile or {}, "count": len(rows), "opportunities": rows}
        )
    )
    subprocess.run(
        [sys.executable, str(SCRIPTS / "filter_open.py"), "--in-file", str(pull), "--out-dir", str(tmp_path),
         "--seen-file", str(tmp_path / "seen.json"), *extra],
        check=True, capture_output=True,
    )
    return json.loads((tmp_path / "open_opportunities.json").read_text())


# --------------------------------------------------------------------------- fetch helpers
def test_award_of_reads_awardee():
    data2 = {"award": {"amount": "142640", "number": "N65", "date": "2026-09-21", "awardee": {"name": " ACME LLC "}}}
    assert fetch.award_of(data2)["awardee"] == "ACME LLC"


@pytest.mark.parametrize("data2", [None, {}, {"award": None}, {"award": {"awardee": {}}}])
def test_award_of_none_when_no_award(data2):
    assert fetch.award_of(data2) is None


def test_related_award_found(monkeypatch):
    payload = {"relatedOpportunities": [
        {"data2": {"title": "amendment"}},
        {"data2": {"opportunityId": "abc", "award": {"amount": "5", "awardee": {"name": "X"}}}},
    ]}
    monkeypatch.setattr(fetch, "get_json", lambda url, params=None: payload)
    found = fetch.related_award("n1")
    assert found["awardee"] == "X" and found["award_notice_id"] == "abc"


def test_search_sends_server_side_filters_and_joins_codes(monkeypatch):
    seen = {}

    def fake(url, params=None):
        seen.update(params)
        return {"_embedded": {"results": [{"_id": "a"}]}, "page": {"totalPages": 1, "totalElements": 1}}

    monkeypatch.setattr(fetch, "get_json", fake)
    fetch.search("naics", ["541511", "541519"], fetch.RESPONSIVE_TYPES, "2026-10-25T00:00:00+00:00")
    assert seen["naics"] == "541511,541519"
    assert "a" not in seen["notice_type"].split(",")  # award notices never requested
    assert seen["response_date.from"].startswith("2026-10-25")


# --------------------------------------------------------------------------- filter
def test_filter_drops_awarded_expired_cancelled_and_info_only(tmp_path):
    rows = [
        notice("keep"),
        notice("awarded", award={"awardee": "ACME"}),
        notice("expired", response_date=iso(-1)),
        notice("cancelled", is_canceled=True),
        notice("award-notice", notice_type="Award Notice"),
        notice("justification", notice_type="Justification"),
    ]
    out = run_filter(tmp_path, rows)
    assert [r["notice_id"] for r in out["opportunities"]] == ["keep"]
    assert out["dropped"]["already awarded"] == 1


def test_filter_keeps_rfis_posted_as_special_notices(tmp_path):
    out = run_filter(tmp_path, [notice("rfi", notice_type="Special Notice")])
    assert out["opportunities"][0]["response_kind"] == "market research"


def test_filter_set_aside_eligibility(tmp_path):
    rows = [notice("open", set_aside="NONE"), notice("blank", set_aside=None),
            notice("sb", set_aside="SBA"), notice("8a", set_aside="8A")]
    out = run_filter(tmp_path, rows, {"set_aside_eligibility": ["SBA", "SBP"]})
    assert {r["notice_id"] for r in out["opportunities"]} == {"open", "blank", "sb"}


def test_filter_without_eligibility_keeps_all_set_asides(tmp_path):
    out = run_filter(tmp_path, [notice("8a", set_aside="8A")])
    assert out["count"] == 1


def test_filter_handles_naive_deadline(tmp_path):
    naive = (datetime.now(timezone.utc) + timedelta(days=3)).replace(tzinfo=None).isoformat()
    out = run_filter(tmp_path, [notice("naive", response_date=naive)])
    assert out["count"] == 1


def test_filter_is_new_is_stable_across_reruns_of_one_pull(tmp_path):
    assert run_filter(tmp_path, [notice("a")])["new_count"] == 1
    assert run_filter(tmp_path, [notice("a")])["new_count"] == 1


# --------------------------------------------------------------------------- scores + report
def test_prune_drops_closed_and_amended():
    rows = [notice("same"), notice("amended", modified_date="2026-10-20T00:00:00+00:00"), notice("unstamped")]
    old = {
        "same": {"fit": 1, "modified_date": "2026-10-01T00:00:00+00:00"},
        "amended": {"fit": 1, "modified_date": "2026-10-01T00:00:00+00:00"},
        "unstamped": {"fit": 1},
        "closed": {"fit": 1, "modified_date": "2026-10-01T00:00:00+00:00"},
    }
    assert set(scores.prune(rows, old)) == {"same", "unstamped"}


def test_validate_catches_missing_unknown_and_malformed():
    rows = [notice("a"), notice("b")]
    problems = render_report.validate(rows, {
        "a": {"fit": 120, "verdict": "maybe", "reason": ""},
        "zzz": {"fit": 50, "verdict": "skip", "reason": "x"},
    })
    text = "\n".join(problems)
    assert "missing score for b" in text
    assert "unknown notice zzz" in text
    assert "fit must be" in text and "verdict must be" in text and "reason is empty" in text


def test_validate_accepts_good_scores():
    assert render_report.validate([notice("a")], {"a": {"fit": 80, "verdict": "pursue", "reason": "fits"}}) == []
