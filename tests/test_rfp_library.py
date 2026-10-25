"""Offline tests for what the app's server shows from the RFP Library. Nothing here calls an API."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

import live  # noqa: E402
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


def test_a_step_shows_what_it_was_given_and_what_came_back_but_never_the_draft():
    read_sheet = {"type": "agent.tool_use", "id": "a", "name": "read", "input": {"file_path": "/out/sheet.json", "offset": 200, "limit": 201}, "processed_at": "t"}
    read_draft = {"type": "agent.tool_use", "id": "b", "name": "read", "input": {"file_path": "/out/proposal.md"}, "processed_at": "t"}
    results = {"a": "x" * 2000, "b": "Doug's draft"}
    sheet = live.describe("Qualifier", read_sheet, results)
    assert sheet["text"] == "Qualifier read sheet.json lines 200-400"
    assert sheet["detail"]["input"] == "/out/sheet.json lines 200-400"
    assert len(sheet["detail"]["result"]) <= live.DETAIL_LENGTH + 2
    assert live.describe("Operator", read_draft, results)["detail"]["result"] == live.WITHHELD


def test_repeated_steps_merge_into_one_with_a_count():
    step = {"agent": "Qualifier", "text": "Qualifier read Cadocary's facts", "at": "t", "count": 1, "detail": None}
    other = {**step, "text": "Qualifier read sheet.json"}
    rows = live.merged([step, step, step, other])
    assert [(row["text"], row["count"]) for row in rows] == [("Qualifier read Cadocary's facts", 3), ("Qualifier read sheet.json", 1)]


def test_the_shown_draft_loses_notes_to_doug_and_his_address():
    draft = (
        "# Response\n\n[DOUG: delete this note before sending. Confirm with Pat ([removed], [removed]).]\n\n"
        "| Address | 12 Elm Street, Richland WA 99352 |\n\nBody text [NEEDED FROM DOUG: date sent]."
    )
    shown = rfp_library.without_notes_to_doug(draft)
    assert "delete this note" not in shown
    assert "[NEEDED FROM DOUG: date sent]" in shown
    scrubbed = rfp_library.TOWN_AFTER_STREET.sub(rfp_library.REMOVED, rfp_library.scrubbed(shown))
    assert "Elm" not in scrubbed and "99352" not in scrubbed
