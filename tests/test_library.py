"""Offline tests for the RFP Library code and the session launcher. Nothing here calls an API."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))

import library  # noqa: E402
import run  # noqa: E402

FOUND_AT = datetime(2026, 10, 25, tzinfo=timezone.utc)


def record(rfp_id, deadline, **over):
    notice = {
        "notice_id": rfp_id, "title": f"Title {rfp_id}", "agency": "CITY OF EXAMPLE", "response_date": deadline,
        "url": f"https://sam.gov/opp/{rfp_id}/view",
    }
    return {**library.new_record(notice, FOUND_AT), **over}


def test_index_is_one_file_while_it_fits_and_sorts_nearest_deadline_first():
    records = [record("later", "2026-12-01T00:00:00+00:00"), record("none", None), record("soon", "2026-11-01T00:00:00+00:00")]
    pages = library.index_pages(records)
    assert list(pages) == ["/index.md"]
    lines = [line for line in pages["/index.md"].splitlines() if " | " in line and not line.startswith("One line")]
    assert [line.split(" | ")[0] for line in lines] == ["soon", "later", "none"]
    assert lines[0] == "soon | CITY OF EXAMPLE | Title soon | 2026-11-01T00:00:00+00:00 | new"


def test_index_splits_by_month_when_over_the_memory_limit(monkeypatch):
    monkeypatch.setattr(library, "MEMORY_LIMIT_BYTES", 300)
    records = [record(f"nov{n}", "2026-11-02T00:00:00+00:00") for n in range(3)]
    records += [record("dec", "2026-12-02T00:00:00+00:00"), record("open", None)]
    pages = library.index_pages(records)
    assert set(pages) == {"/index.md", "/index/2026-11.md", "/index/2026-12.md", "/index/no-deadline.md"}
    assert "- `/index/2026-11.md`: 3 RFPs" in pages["/index.md"]
    assert "nov0 |" in pages["/index/2026-11.md"] and "dec |" not in pages["/index/2026-11.md"]


def test_index_line_keeps_the_column_separator_out_of_fields():
    line = library.index_line(record("a", None, title="Phase 1 | Phase 2"))
    assert line == "a | CITY OF EXAMPLE | Phase 1 / Phase 2 | none | new\n"


def test_status_after_run_follows_the_furthest_step_reached():
    status = library.status_after_run
    assert status({}, "new") == "new"
    assert status({"sheet.json": b"{}"}, "new") == "qualifying"
    assert status({"qualification.json": b'{"decision": "pursue"}'}, "new") == "researching"
    assert status({"qualification.json": b'{"decision": "pass"}'}, "new") == "passed"
    assert status({"research.json": b"{}", "qualification.json": b'{"decision": "pursue"}'}, "new") == "drafting"
    assert status({"packet.json": b'{"recommendation": "send"}'}, "drafting") == "ready_for_doug"
    assert status({"packet.json": b'{"recommendation": "pass"}'}, "drafting") == "passed"


def test_status_after_run_ignores_a_broken_file():
    assert library.status_after_run({"qualification.json": b"{not json"}, "qualifying") == "qualifying"


def test_unique_name_keeps_every_document_in_its_own_file():
    taken = {"SF1449.pdf", "SF1449 (2).pdf", "README"}
    assert library.unique_name("SF1449.pdf", taken) == "SF1449 (3).pdf"
    assert library.unique_name("README", taken) == "README (2)"
    assert library.unique_name("a/b.pdf", taken) == "a-b.pdf"


def test_parse_steps_keeps_pipeline_order():
    assert run.parse_steps("qualify,read") == ["read", "qualify"]
    assert run.parse_steps("all") == run.STEPS


def test_starting_message_lists_attached_files_and_links_for_the_rest():
    stored = record("abc", "2026-11-01T00:00:00+00:00")
    stored["documents"] = [
        {"name": "rfp.pdf", "url": "https://sam.gov/a", "file_id": "file_1"},
        {"name": "map.pdf", "url": "https://sam.gov/b", "file_id": None, "error": "HTTP 404"},
    ]
    message = run.starting_message(stored, ["read", "qualify"])
    assert "/mnt/session/uploads/abc/" in message
    assert "- rfp.pdf" in message
    assert "- map.pdf: https://sam.gov/b" in message
    assert "Run only these steps: read, qualify." in message


def test_status_after_run_never_changes_dougs_outcomes_or_moves_back_on_a_reread():
    status = library.status_after_run
    assert status({"packet.json": b'{"recommendation": "pass"}'}, "sent") == "sent"
    assert status({"sheet.json": b"{}"}, "ready_for_doug") == "ready_for_doug"
    assert status({"qualification.json": b'{"decision": "pass"}'}, "ready_for_doug") == "passed"


def test_deadline_reads_a_trailing_z_and_treats_bad_dates_as_missing():
    assert library.deadline(record("z", "2026-11-01T17:00:00Z")).hour == 17
    assert library.deadline(record("naive", "2026-11-01T17:00:00")).tzinfo == timezone.utc
    assert library.deadline(record("bad", "next Tuesday")) is None
    assert library.deadline_month(record("bad", "next Tuesday")) == "no-deadline"


def test_large_earlier_findings_are_mounted_apart_from_the_documents(monkeypatch):
    stored = record("abc", None)
    stored["documents"] = [{"name": "rfp.pdf", "url": "https://sam.gov/a", "file_id": "file_doc"}]
    stored["findings"] = [
        {"name": "qualification.json", "memory_path": "/rfps/abc/findings/qualification.json"},
        {"name": "sheet.json", "file_id": "file_old"},
        {"name": "sheet.json", "file_id": "file_new"},
    ]
    ids = {
        "agents": {"operator": {"id": "agent_1", "version": 7}},
        "environment": {"id": "env_1"},
        "vault": {"id": "vlt_1"},
        "memory_stores": {"rfp-library": {"id": "mem_1"}},
    }
    sent = {}
    monkeypatch.setattr(run, "anthropic", lambda method, path, body: sent.update(body) or {"id": "sesn_1"})
    run.create_session(ids, stored, ["qualify"], 5)
    mounts = {resource["file_id"]: resource["mount_path"] for resource in sent["resources"] if resource["type"] == "file"}
    assert mounts == {"file_doc": "/abc/rfp.pdf", "file_new": "/findings/abc/sheet.json"}
    assert sent["budget"]["max_list_cost"]["amount"] == "500"
    message = sent["initial_events"][0]["content"][0]["text"]
    assert "/mnt/session/uploads/findings/abc/: sheet.json." in message
