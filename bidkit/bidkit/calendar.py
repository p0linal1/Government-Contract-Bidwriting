#!/usr/bin/env python3
"""
calendar.py — turn an opportunity's dates into calendar events (.ics) so nothing filed by the poller
is forgotten. Optional Google Calendar insert for the machine with Google API access.

Why: once solicitations are filed automatically, the failure mode shifts from "missed the email" to
"filed it and forgot" — a due date only visible inside a folder is not a deadline. Every opportunity
gets an .ics you can import (or subscribe to via the combined file), with alarms, and a set of internal
working milestones counted back from the due date.

Reads <opp>/opportunity.json:
  due.date / due.time / due.timezone|tz_hint / due.confirmed
  milestones.{questions,prebid,addenda,award,start,interviews,issued}.{date,time,confirmed}
Writes <opp>/calendar.ics (events prefixed with the opportunity id; unconfirmed dates are marked
"(UNCONFIRMED)" in the title so a glance tells you what still needs checking against the RFP).
`all` merges every opportunity into opportunities/all-opportunities.ics (import once, or point a
calendar app at the file / a served copy to subscribe).

Internal milestones (all-day, only when a due date exists and lies ahead):
  go/no-go decision   due - 14 d      research + facts sheet reviewed, bid or pass decided
  draft complete      due -  7 d      narrative/workbooks/pricing drafted; compliance pass starts
  final review        due -  2 d      final compliance audit, wet signatures, package assembled
  SUBMIT              due - 1 day (all-day reminder; the timed event is the deadline itself)

Google Calendar (SCAFFOLD, lazy imports, needs requirements-gmail.txt + calendar scope):
  python3 -m bidkit.calendar google <opp> --cfg inbox/inbox.json [--calendar-id primary] [--dry-run]
  Uses the same OAuth client as mail_gmail with the additional scope
  https://www.googleapis.com/auth/calendar.events (re-run `mail_gmail auth` after adding it, or keep a
  separate token via calendar.token_file). Idempotent: events carry an iCalUID = our stable UID, and
  existing ones are updated, not duplicated.

CLI:
  python3 -m bidkit.calendar ics  <opp-dir> [--out FILE] [--tz America/Los_Angeles] [--no-internal]
  python3 -m bidkit.calendar all  <opportunities-dir> [--out FILE]
  python3 -m bidkit.calendar show <opp-dir>                          # print the events, no files
  python3 -m bidkit.calendar google <opp-dir> --cfg <inbox.json> [--calendar-id ID] [--dry-run]
"""
import argparse, datetime as dt, hashlib, json, os, re, sys

DEFAULT_TZ = "America/Los_Angeles"
TZ_HINTS = {"pt": "America/Los_Angeles", "pst": "America/Los_Angeles", "pdt": "America/Los_Angeles", "pacific": "America/Los_Angeles",
            "mt": "America/Denver", "mst": "America/Denver", "mdt": "America/Denver", "mountain": "America/Denver",
            "ct": "America/Chicago", "cst": "America/Chicago", "cdt": "America/Chicago", "central": "America/Chicago",
            "et": "America/New_York", "est": "America/New_York", "edt": "America/New_York", "eastern": "America/New_York"}
KIND_TITLES = {"due": "DUE — proposal deadline", "questions": "Questions deadline", "prebid": "Pre-bid / pre-proposal conference",
               "addenda": "Final addenda posted", "award": "Award / shortlist notice", "start": "Contract start",
               "interviews": "Interviews / demonstrations", "issued": "Solicitation issued"}
# minutes before the event for VALARM triggers, per kind
ALARMS = {"due": [7 * 1440, 2 * 1440, 1440, 180], "questions": [3 * 1440, 1440], "prebid": [1440, 120],
          "addenda": [1440], "award": [1440], "interviews": [2 * 1440, 120], "start": [7 * 1440], "issued": []}
INTERNAL = [(14, "Go / no-go decision", "Facts sheet + research reviewed; decide bid or pass; confirm team and capacity."),
            (7, "Draft complete", "Narrative, workbooks, pricing drafted; start the compliance pass."),
            (2, "Final review", "Final compliance audit; wet signatures + dates; package assembled and verified."),
            (1, "SUBMIT tomorrow", "Send before the deadline (agency time zone); confirm receipt.")]


class CalendarError(Exception):
    pass


# ----------------------------------------------------------------------------- model
def tz_for(oj):
    due = oj.get("due") or {}
    tz = due.get("timezone")
    if tz and "/" in tz: return tz
    hint = (due.get("tz_hint") or "").lower().replace(" time", "").replace(" standard", "").replace(" daylight", "").strip()
    return TZ_HINTS.get(hint, DEFAULT_TZ)


def _zone(tzname):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tzname)
    except Exception:
        return dt.timezone.utc


def stable_uid(oid, kind):
    return hashlib.sha1(f"{oid}|{kind}".encode()).hexdigest()[:24] + "@bidkit"


def build_events(oj, oid, tzname=None, internal=True, today=None):
    """Return a list of event dicts: {uid, kind, summary, description, start, end, all_day, alarms,
    confirmed}. Timed events are tz-aware datetimes; all-day events carry a date."""
    tzname = tzname or tz_for(oj); z = _zone(tzname)
    today = today or dt.date.today()
    title = oj.get("title") or oid
    agency = oj.get("agency") or ""
    events = []

    def add(kind, date_s, time_s, confirmed, label, extra=""):
        if not date_s: return None
        try: d = dt.date.fromisoformat(str(date_s)[:10])
        except ValueError: return None
        conf = "" if confirmed else " (UNCONFIRMED)"
        summary = f"[{oid}] {label}{conf}"
        desc = f"{title}\n{agency}\nKind: {kind}\n{'Confirmed from the RFP.' if confirmed else 'DETECTED from email/RFP text — confirm against the solicitation and set confirmed: true in opportunity.json.'}\n{extra}".strip()
        if time_s and re.match(r"^\d{1,2}:\d{2}$", str(time_s)):
            hh, mm = map(int, str(time_s).split(":"))
            start = dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=z)
            ev = {"uid": stable_uid(oid, kind), "kind": kind, "summary": summary, "description": desc,
                  "start": start, "end": start + dt.timedelta(minutes=30 if kind != "prebid" else 90), "all_day": False}
        else:
            ev = {"uid": stable_uid(oid, kind), "kind": kind, "summary": summary, "description": desc,
                  "start": d, "end": d + dt.timedelta(days=1), "all_day": True}
        ev["alarms"] = ALARMS.get(kind, [1440]); ev["confirmed"] = bool(confirmed); ev["tz"] = tzname
        events.append(ev); return ev

    due = oj.get("due") or {}
    due_ev = add("due", due.get("date"), due.get("time"), due.get("confirmed"), KIND_TITLES["due"],
                 f"Submission: see opportunity-facts.md → Submission. Due time zone: {tzname}.")
    for kind, m in (oj.get("milestones") or {}).items():
        if isinstance(m, dict) and kind in KIND_TITLES and kind != "due":
            add(kind, m.get("date"), m.get("time"), m.get("confirmed"), KIND_TITLES[kind])
    if internal and due_ev:
        due_date = due_ev["start"].date() if not due_ev["all_day"] else due_ev["start"]
        for days_before, label, desc in INTERNAL:
            d = due_date - dt.timedelta(days=days_before)
            if d < today: continue                      # never create milestones in the past
            events.append({"uid": stable_uid(oid, f"internal-{days_before}"), "kind": "internal", "summary": f"[{oid}] {label}",
                           "description": f"{title}\n{desc}\nDue {due_date.isoformat()}{'' if due_ev['confirmed'] else ' (UNCONFIRMED)'}.",
                           "start": d, "end": d + dt.timedelta(days=1), "all_day": True, "alarms": [540], "confirmed": due_ev["confirmed"], "tz": tzname})
    events.sort(key=lambda e: (e["start"].isoformat() if isinstance(e["start"], dt.date) else str(e["start"])))
    return events


# ----------------------------------------------------------------------------- ics
def _esc(s):
    return str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line):
    """RFC 5545 line folding at 75 octets."""
    out, b = [], line.encode("utf-8")
    while len(b) > 75:
        cut = 75
        while cut > 0 and (b[cut] & 0xC0) == 0x80: cut -= 1      # don't split a UTF-8 sequence
        out.append(b[:cut].decode("utf-8")); b = b" " + b[cut:]
    out.append(b.decode("utf-8"))
    return "\r\n".join(out)


def _dt_utc(d):
    return d.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def event_to_ics(ev, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    L = ["BEGIN:VEVENT", f"UID:{ev['uid']}", f"DTSTAMP:{_dt_utc(now)}"]
    if ev["all_day"]:
        L += [f"DTSTART;VALUE=DATE:{ev['start'].strftime('%Y%m%d')}", f"DTEND;VALUE=DATE:{ev['end'].strftime('%Y%m%d')}"]
    else:
        L += [f"DTSTART:{_dt_utc(ev['start'])}", f"DTEND:{_dt_utc(ev['end'])}"]
    L += [_fold(f"SUMMARY:{_esc(ev['summary'])}"), _fold(f"DESCRIPTION:{_esc(ev['description'])}"),
          f"CATEGORIES:bid,{ev['kind']}", f"STATUS:{'CONFIRMED' if ev['confirmed'] else 'TENTATIVE'}", "TRANSP:TRANSPARENT"]
    for mins in ev.get("alarms", []):
        L += ["BEGIN:VALARM", "ACTION:DISPLAY", _fold(f"DESCRIPTION:{_esc(ev['summary'])}"),
              f"TRIGGER:-PT{mins}M" if mins < 1440 or mins % 1440 else f"TRIGGER:-P{mins // 1440}D", "END:VALARM"]
    L.append("END:VEVENT")
    return "\r\n".join(L)


def calendar_ics(events, name="bidkit opportunities", now=None):
    body = "\r\n".join(event_to_ics(e, now) for e in events)
    head = "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//bidkit//calendar//EN", "CALSCALE:GREGORIAN",
                        "METHOD:PUBLISH", _fold(f"X-WR-CALNAME:{_esc(name)}")])
    return head + ("\r\n" + body if body else "") + "\r\nEND:VCALENDAR\r\n"


def parse_ics_events(text):
    """Minimal parser for our own output (tests + `all` merge): [{uid, summary, dtstart}]."""
    text = re.sub(r"\r\n[ \t]", "", text)           # unfold
    out = []
    for block in re.findall(r"BEGIN:VEVENT\r\n(.*?)\r\nEND:VEVENT", text, re.S):
        props = dict(re.match(r"([^:;]+)(?:;[^:]*)?:(.*)", l).groups() for l in block.split("\r\n") if ":" in l and not l.startswith(("BEGIN", "END", "ACTION", "TRIGGER")))
        out.append({"uid": props.get("UID"), "summary": props.get("SUMMARY"), "dtstart": props.get("DTSTART"), "status": props.get("STATUS")})
    return out


# ----------------------------------------------------------------------------- opportunity I/O
def load_opp(opp_dir):
    p = os.path.join(opp_dir, "opportunity.json")
    if not os.path.exists(p):
        raise CalendarError(f"no opportunity.json in {opp_dir}")
    with open(p, encoding="utf-8") as fh:
        return json.load(fh), os.path.basename(os.path.abspath(opp_dir))


def write_ics_for_opportunity(opp_dir, out=None, tzname=None, internal=True):
    oj, oid = load_opp(opp_dir)
    events = build_events(oj, oid, tzname=tzname, internal=internal)
    out = out or os.path.join(opp_dir, "calendar.ics")
    with open(out, "w", encoding="utf-8", newline="") as fh:
        fh.write(calendar_ics(events, name=f"bid {oid}"))
    return out, events


def write_all(opps_dir, out=None):
    out = out or os.path.join(opps_dir, "all-opportunities.ics")
    events = []
    for name in sorted(os.listdir(opps_dir)):
        d = os.path.join(opps_dir, name)
        if name.startswith("_") or not os.path.isdir(d) or not os.path.exists(os.path.join(d, "opportunity.json")):
            continue
        try:
            oj, oid = load_opp(d)
        except (CalendarError, json.JSONDecodeError):
            continue
        if (oj.get("status") or "").lower() in ("submitted", "lost", "won", "passed", "closed", "archived"):
            continue                                    # finished bids don't need reminders
        events += build_events(oj, oid)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        fh.write(calendar_ics(events, name="bidkit — all open opportunities"))
    return out, events


# ----------------------------------------------------------------------------- google calendar scaffold
CAL_SCOPE = "https://www.googleapis.com/auth/calendar.events"


def google_insert(opp_dir, cfg, calendar_id="primary", dry_run=False, service=None):
    """Upsert this opportunity's events into Google Calendar. `service` injectable for tests.
    Idempotent via iCalUID (= our stable UID): existing events are patched, not duplicated."""
    oj, oid = load_opp(opp_dir)
    events = build_events(oj, oid)
    if service is None and not dry_run:
        try:
            from .mail_gmail import load_credentials, build_service  # noqa: F401
            from googleapiclient.discovery import build
        except ImportError:
            raise CalendarError("Google libraries not installed: pip3 install -r bidkit/requirements-gmail.txt")
        gcfg = dict(cfg.get("gmail_api") or {})
        gcfg.update(cfg.get("calendar") or {})              # optional separate token_file for the calendar scope
        creds = _calendar_credentials(gcfg)
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    results = []
    for ev in events:
        body = {"summary": ev["summary"], "description": ev["description"], "iCalUID": ev["uid"], "transparency": "transparent",
                "status": "confirmed" if ev["confirmed"] else "tentative",
                "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": min(m, 40320)} for m in ev["alarms"][:5]]}}
        if ev["all_day"]:
            body["start"] = {"date": ev["start"].isoformat()}; body["end"] = {"date": ev["end"].isoformat()}
        else:
            body["start"] = {"dateTime": ev["start"].isoformat(), "timeZone": ev["tz"]}
            body["end"] = {"dateTime": ev["end"].isoformat(), "timeZone": ev["tz"]}
        if dry_run:
            results.append({"uid": ev["uid"], "action": "would-import", "summary": ev["summary"]}); continue
        # events.import is the documented way to create with a client-chosen iCalUID; a second import
        # with the same iCalUID updates the existing event on most calendars, so this stays idempotent.
        r = service.events().import_(calendarId=calendar_id, body=body).execute()
        results.append({"uid": ev["uid"], "action": "imported", "id": r.get("id"), "summary": ev["summary"]})
    return results


def _calendar_credentials(gcfg):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    token_file = os.path.expanduser(gcfg.get("calendar_token_file") or gcfg.get("token_file", "~/.config/bidkit/gmail-token.json"))
    if not os.path.exists(token_file):
        raise CalendarError(f"no OAuth token at {token_file}; run mail_gmail auth with the calendar scope added "
                            f"(set gmail_api.extra_scopes: [\"{CAL_SCOPE}\"]) or set calendar.calendar_token_file")
    creds = Credentials.from_authorized_user_file(token_file)
    if CAL_SCOPE not in (creds.scopes or []):
        raise CalendarError(f"token at {token_file} lacks {CAL_SCOPE}; delete it and re-run mail_gmail auth with the scope added")
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


# ----------------------------------------------------------------------------- CLI
def _print_events(events):
    for e in events:
        when = e["start"].isoformat() if e["all_day"] else e["start"].strftime("%Y-%m-%d %H:%M %Z")
        print(f"  {when:22s} {e['summary']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("ics", help="write <opp>/calendar.ics"); i.add_argument("opportunity"); i.add_argument("--out"); i.add_argument("--tz"); i.add_argument("--no-internal", action="store_true")
    s = sub.add_parser("show", help="print events"); s.add_argument("opportunity"); s.add_argument("--no-internal", action="store_true")
    al = sub.add_parser("all", help="merge every open opportunity into one .ics"); al.add_argument("opportunities"); al.add_argument("--out")
    g = sub.add_parser("google", help="upsert events into Google Calendar (scaffold)"); g.add_argument("opportunity"); g.add_argument("--cfg", required=True)
    g.add_argument("--calendar-id", default="primary"); g.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "show":
            oj, oid = load_opp(a.opportunity); ev = build_events(oj, oid, internal=not a.no_internal)
            print(f"{oid}: {len(ev)} event(s), tz {tz_for(oj)}"); _print_events(ev); return 0
        if a.cmd == "ics":
            out, ev = write_ics_for_opportunity(a.opportunity, out=a.out, tzname=a.tz, internal=not a.no_internal)
            print(f"wrote {out} ({len(ev)} events)"); _print_events(ev); return 0
        if a.cmd == "all":
            out, ev = write_all(a.opportunities, out=a.out)
            print(f"wrote {out} ({len(ev)} events across open opportunities)"); return 0
        if a.cmd == "google":
            from .inbox import load_config
            res = google_insert(a.opportunity, load_config(a.cfg), calendar_id=a.calendar_id, dry_run=a.dry_run)
            for r in res: print(f"  {r['action']:13s} {r['summary']}")
            return 0
    except CalendarError as e:
        print(f"CALENDAR ERROR: {e}"); return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
