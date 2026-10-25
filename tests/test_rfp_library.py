"""Offline tests for what the app's server shows from the RFP Library. Nothing here calls an API."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

import rfp_library  # noqa: E402


def test_contact_details_are_scrubbed_everywhere_in_an_answer():
    answer = {
        "open_items": ["Call (425) 555-0134 or 206.555.0199, or write to doug@example.com."],
        "nested": {"why": "Mail it to 1234 NE 45th Street, Apt 2, Seattle WA, or PO Box 4411."},
    }
    text = str(rfp_library.scrubbed(answer))
    for private in ("555-0134", "555.0199", "doug@example.com", "45th Street", "Box 4411"):
        assert private not in text


def test_scrubbing_leaves_dates_money_and_solicitation_numbers_alone():
    text = "Due 2026-11-16T11:00:00-05:00, $186,364.73 over 5 years, solicitation 693JK327RFI01, 223 Appendix A titles."
    assert rfp_library.scrubbed(text) == text


def test_the_page_never_gets_a_finding_it_does_not_show():
    found = {
        "packet": {"headline": "Pass: no fit.", "recommendation": "pass", "files": {"draft": "/mnt/session/outputs/proposal.md"}},
        "qualification": {"decision": "pass", "decision_reasons": [{"reason": "No fit.", "requirement_ids": ["R1"], "cite": {"doc": "rfp.pdf", "page": 2, "quote": "q", "extra": 1}}]},
    }
    shown = rfp_library.shown_findings(found)
    assert "files" not in shown["packet"]
    assert shown["qualification"]["decision_reasons"] == [{"reason": "No fit.", "cite": {"doc": "rfp.pdf", "page": 2, "quote": "q"}}]
    assert shown["research"] is None


def test_buyer_is_the_office_with_codes_left_as_written():
    assert rfp_library.buyer("TRANSPORTATION, DEPARTMENT OF / PHMSA / 693JK3 ACQUISITION SERVICES DIV.") == "693JK3 Acquisition Services Div."
    assert rfp_library.buyer(None) == "Unknown buyer"
