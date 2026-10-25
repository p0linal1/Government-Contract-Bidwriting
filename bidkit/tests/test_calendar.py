import datetime as dt, json, os
import pytest
from bidkit import calendar as cal


def _opp(tmp_path, due_date="2026-10-30", due_time="14:00", confirmed=False, tz_hint="Pacific Time", milestones=True, status=None, oid="27-004-Example"):
    o = tmp_path / oid; o.mkdir()
    oj = {"id": oid, "title": "Jail Management System Replacement", "agency": "Example County",
          "due": {"date": due_date, "time": due_time, "timezone": "", "tz_hint": tz_hint, "confirmed": confirmed}}
    if milestones:
        oj["milestones"] = {"questions": {"date": "2026-10-09", "time": "17:00", "confirmed": False},
                            "prebid": {"date": "2026-09-24", "time": "10:00", "confirmed": True},
                            "award": {"date": "2026-11-20", "time": None, "confirmed": False}}
    if status: oj["status"] = status
    (o / "opportunity.json").write_text(json.dumps(oj))
    return o


def test_tz_from_hint_and_default(tmp_path):
    o = _opp(tmp_path); oj, oid = cal.load_opp(str(o))
    assert cal.tz_for(oj) == "America/Los_Angeles"
    oj["due"]["tz_hint"] = "ET"; assert cal.tz_for(oj) == "America/New_York"
    oj["due"]["tz_hint"] = ""; assert cal.tz_for(oj) == cal.DEFAULT_TZ
    oj["due"]["timezone"] = "Europe/Paris"; assert cal.tz_for(oj) == "Europe/Paris"


def test_build_events_timed_allday_internal_and_unconfirmed_marking(tmp_path):
    o = _opp(tmp_path); oj, oid = cal.load_opp(str(o))
    ev = cal.build_events(oj, oid, today=dt.date(2026, 9, 16))
    kinds = [e["kind"] for e in ev]
    assert kinds.count("due") == 1 and kinds.count("internal") == 4 and {"questions", "prebid", "award"} <= set(kinds)
    due = next(e for e in ev if e["kind"] == "due")
    assert not due["all_day"] and due["start"].hour == 14 and str(due["start"].tzinfo) == "America/Los_Angeles"
    assert "(UNCONFIRMED)" in due["summary"] and due["alarms"] == [7 * 1440, 2 * 1440, 1440, 180]
    prebid = next(e for e in ev if e["kind"] == "prebid")
    assert "(UNCONFIRMED)" not in prebid["summary"] and (prebid["end"] - prebid["start"]) == dt.timedelta(minutes=90)
    award = next(e for e in ev if e["kind"] == "award")
    assert award["all_day"] and award["start"] == dt.date(2026, 11, 20)
    internal = sorted(e["start"] for e in ev if e["kind"] == "internal")
    assert internal == [dt.date(2026, 10, 16), dt.date(2026, 10, 23), dt.date(2026, 10, 28), dt.date(2026, 10, 29)]
    # uids are stable across runs
    ev2 = cal.build_events(oj, oid, today=dt.date(2026, 9, 16))
    assert [e["uid"] for e in ev] == [e["uid"] for e in ev2]
    # events are sorted chronologically
    starts = [e["start"].isoformat() if isinstance(e["start"], dt.date) and not isinstance(e["start"], dt.datetime) else e["start"].isoformat() for e in ev]
    assert starts == sorted(starts)


def test_internal_milestones_never_in_the_past(tmp_path):
    o = _opp(tmp_path, due_date="2026-09-20"); oj, oid = cal.load_opp(str(o))
    ev = cal.build_events(oj, oid, today=dt.date(2026, 9, 16))
    internal = [e for e in ev if e["kind"] == "internal"]
    assert all(e["start"] >= dt.date(2026, 9, 16) for e in internal) and len(internal) == 2      # -2d and -1d only


def test_ics_is_valid_and_round_trips(tmp_path):
    o = _opp(tmp_path)
    out, ev = cal.write_ics_for_opportunity(str(o))
    text = open(out, encoding="utf-8", newline="").read()
    assert text.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:") and text.endswith("END:VCALENDAR\r\n")
    assert text.count("BEGIN:VEVENT") == len(ev) == text.count("END:VEVENT")
    assert "BEGIN:VALARM" in text and "TRIGGER:-P7D" in text and "TRIGGER:-PT180M" in text
    assert "DTSTART:20261030T210000Z" in text                  # 14:00 PDT == 21:00Z
    assert "DTSTART;VALUE=DATE:20261120" in text
    assert all(len(l.encode()) <= 75 for l in text.split("\r\n"))   # folded
    parsed = cal.parse_ics_events(text)
    assert len(parsed) == len(ev) and all(p["uid"].endswith("@bidkit") for p in parsed)
    assert any(p["status"] == "TENTATIVE" for p in parsed) and any(p["status"] == "CONFIRMED" for p in parsed)
    # escaping of commas/semicolons in text fields
    oj = json.load(open(o / "opportunity.json")); oj["title"] = "A, B; C"; json.dump(oj, open(o / "opportunity.json", "w"))
    out, _ = cal.write_ics_for_opportunity(str(o))
    assert "A\\, B\\; C" in open(out, encoding="utf-8", newline="").read().replace("\r\n ", "")


def test_all_merges_open_opportunities_and_skips_finished(tmp_path):
    opps = tmp_path / "opportunities"; opps.mkdir()
    _opp(opps, oid="A-1"); _opp(opps, oid="B-2", status="submitted"); (opps / "_template").mkdir()
    (opps / "_template" / "opportunity.json").write_text(json.dumps({"id": "{{ID}}", "due": {"date": "{{DUE_DATE}}"}}))
    out, ev = cal.write_all(str(opps))
    assert out.endswith("all-opportunities.ics") and ev and all(e["summary"].startswith("[A-1]") for e in ev)
    assert "[B-2]" not in open(out).read() and "{{ID}}" not in open(out).read()


def test_no_due_date_yields_no_internal_and_cli(tmp_path, capsys):
    o = _opp(tmp_path, due_date="", due_time="", milestones=True)
    rc = cal.main(["show", str(o)]); assert rc == 0
    out = capsys.readouterr().out
    assert "3 event(s)" in out and "Go / no-go" not in out
    assert cal.main(["ics", str(o), "--no-internal"]) == 0 and (o / "calendar.ics").exists()
    assert cal.main(["show", str(tmp_path / "nope")]) == 1


# ----------------------------------------------------------------------------- google scaffold
class _Call:
    def __init__(self, r): self._r = r
    def execute(self): return self._r


class FakeCalService:
    def __init__(self): self.imported = []
    def events(self): return self
    def import_(self, calendarId, body):
        self.imported.append((calendarId, body)); return _Call({"id": "evt" + str(len(self.imported))})


def test_google_insert_uses_import_with_icaluid_and_dry_run(tmp_path):
    o = _opp(tmp_path)
    dry = cal.google_insert(str(o), {}, dry_run=True)
    assert dry and all(r["action"] == "would-import" for r in dry)
    svc = FakeCalService()
    res = cal.google_insert(str(o), {}, calendar_id="work", service=svc)
    assert len(svc.imported) == len(res) and all(cid == "work" for cid, _ in svc.imported)
    bodies = [b for _, b in svc.imported]
    assert all(b["iCalUID"].endswith("@bidkit") for b in bodies)
    due_body = next(b for b in bodies if "DUE" in b["summary"])
    assert due_body["start"]["timeZone"] == "America/Los_Angeles" and due_body["status"] == "tentative"   # unconfirmed
    prebid_body = next(b for b in bodies if "Pre-bid" in b["summary"])
    assert prebid_body["status"] == "confirmed"
    allday = next(b for b in bodies if "date" in b["start"])
    assert allday["end"]["date"] > allday["start"]["date"]
    assert all(m["minutes"] <= 40320 for b in bodies for m in b["reminders"]["overrides"])   # Google's cap
