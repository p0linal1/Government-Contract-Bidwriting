"""The RFP Library and each RFP's findings, read only, for the app's sidebar, Today, and RFP pages.

agent/library.py writes the library; this only reads it. The app polls, so answers are cached for
a little while, and a memory is read again only when its content has changed.

The app has no login, so an answer carries only the fields its pages show, never a draft or
notes, and contact details are scrubbed out: drafts are built from Doug's private facts, and
any finding can quote them.
"""

import json
import re
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import live

MEMORY_BETA = "agent-memory-2026-07-22"
STORE_ID = json.loads(live.IDS_FILE.read_text())["memory_stores"]["rfp-library"]["id"]
RECORD_PATH = re.compile(r"/rfps/([^/]+)/record\.json")
FINDING_FILES = {"packet": "packet.json", "qualification": "qualification.json", "summary": "summary.md", "research": "research.json"}
DRAFT_FILES = ("proposal.md", "draft.json")

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?:\+?1[\s.-]?)?\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")
STREET = re.compile(
    r"\b\d{1,6}\s+(?:[NSEW]\.?\s+)?(?:[A-Z0-9][\w'.-]*\s+){1,4}"
    r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct|Place|Pl|Parkway|Pkwy|Highway|Hwy|Circle|Cir|Terrace|Loop|Trail)\b\.?"
    r"(?:,?\s*(?:Suite|Ste|Apt|Unit|#)\s*[\w-]+)?"
    r"|\bP\.?\s?O\.?\s+Box\s+\d+",
)
REMOVED = "[removed]"
RUNNING = ("running", "rescheduling")

LIBRARY_CACHE_SECONDS = 45
RFP_CACHE_SECONDS = 8
SESSION_COUNT = 50
RECENT_RUNS = 5
READERS = 8
DAY_SECONDS = 24 * 60 * 60

cache_lock = threading.Lock()
# By cache key: (monotonic time, answer).
cached = {}
# By memory path: (content_sha256, content).
contents = {}


def scrubbed(answer):
    """The answer with every email address, phone number, and street address taken out."""
    text = json.dumps(answer)
    for pattern in (EMAIL, PHONE, STREET):
        text = pattern.sub(REMOVED, text)
    return json.loads(text)


def memory_call(path):
    return live.anthropic(f"memory_stores/{STORE_ID}/{path}", beta=MEMORY_BETA)


def memories():
    """Every memory in the store by path, without its content."""
    found, page = {}, None
    while True:
        query = {"limit": 100, **({"page": page} if page else {})}
        listing = memory_call(f"memories?{urllib.parse.urlencode(query)}")
        found.update((item["path"], item) for item in listing["data"] if item["type"] == "memory")
        page = listing.get("next_page")
        if not page:
            return found


def read(memory):
    known = contents.get(memory["path"])
    if known and known[0] == memory["content_sha256"]:
        return known[1]
    content = memory_call(f"memories/{memory['id']}")["content"]
    contents[memory["path"]] = (memory["content_sha256"], content)
    return content


def findings(stored, rfp_id):
    """Whichever of the packet, qualification, summary, and research a run has saved for this RFP."""
    found = {}
    for key, name in FINDING_FILES.items():
        memory = stored.get(f"/rfps/{rfp_id}/findings/{name}")
        if not memory:
            continue
        text = read(memory)
        if name.endswith(".md"):
            found[key] = text
            continue
        try:
            found[key] = json.loads(text)
        except json.JSONDecodeError:
            # A run can save a broken file. The page shows the other findings rather than failing.
            continue
    return found


def days_left(deadline, now):
    if not deadline:
        return None
    try:
        when = datetime.fromisoformat(deadline)
    except ValueError:
        return None
    when = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
    return int((when - now).total_seconds() // DAY_SECONDS)


def buyer(agency):
    """The office that is buying: the last part of SAM.gov's department / agency / office path."""
    if not agency:
        return "Unknown buyer"
    office = agency.split("/")[-1].strip()
    if not office.isupper():
        return office
    # SAM.gov shouts. Short words and ones with digits are mostly codes and acronyms, so they stay.
    return " ".join(word.capitalize() if word.rstrip(".,").isalpha() and len(word) > 2 else word for word in office.split())


def rfp_runs():
    """The Operator's recent sessions that each worked one RFP, newest first."""
    query = urllib.parse.urlencode({"limit": SESSION_COUNT, "agent_id": live.OPERATOR_ID})
    return [session for session in live.anthropic(f"sessions?{query}")["data"] if (session.get("metadata") or {}).get("rfp_id")]


def run_summary(session, step_count):
    """A session as live.py describes it, plus its RFP and its last steps. Only a running one is read step by step."""
    threads = live.session_threads(session)
    steps = live.latest_steps(session["id"], threads)[:step_count] if step_count else []
    planned = session["metadata"].get("steps", "")
    return {**live.summary(session, threads), "rfp_id": session["metadata"]["rfp_id"], "planned": planned.split(",") if planned else [], "steps": steps}


def newest_by_rfp(sessions):
    newest = {}
    for session in sessions:
        newest.setdefault(session["metadata"]["rfp_id"], session)
    return newest


def library_row(record, packet, run, now):
    return {
        "id": record["rfp_id"],
        "title": record["title"],
        "buyer": buyer(record.get("agency")),
        "agency": record.get("agency"),
        "solicitation_number": record.get("solicitation_number"),
        "response_kind": record.get("response_kind"),
        "deadline": record.get("deadline"),
        "days_left": days_left(record.get("deadline"), now),
        "status": record["status"],
        "sam_url": record.get("sam_url"),
        "headline": packet.get("headline") if packet else None,
        "recommendation": packet.get("recommendation") if packet else None,
        "run": run,
    }


def cached_answer(key, seconds, build):
    with cache_lock:
        hit = cached.get(key)
        if hit and time.monotonic() - hit[0] < seconds:
            return hit[1]
        answer = build()
        cached[key] = (time.monotonic(), answer)
        return answer


def build_library():
    stored = memories()
    record_memories = [memory for path, memory in stored.items() if RECORD_PATH.fullmatch(path)]
    with ThreadPoolExecutor(max_workers=READERS) as pool:
        records = [json.loads(text) for text in pool.map(read, record_memories)]
    sessions = rfp_runs()
    runs = {
        rfp_id: run_summary(session, 1 if session["status"] in RUNNING else 0)
        for rfp_id, session in newest_by_rfp(sessions).items()
    }
    now = datetime.now(timezone.utc)
    rows = []
    for record in records:
        packet_memory = stored.get(f"/rfps/{record['rfp_id']}/findings/packet.json")
        packet = findings(stored, record["rfp_id"]).get("packet") if packet_memory else None
        rows.append(library_row(record, packet, runs.get(record["rfp_id"]), now))
    titles = {row["id"]: row["title"] for row in rows}
    recent = [{**run_summary(session, 0), "rfp_title": titles.get(session["metadata"]["rfp_id"])} for session in sessions[:RECENT_RUNS]]
    return scrubbed({"as_of": now.isoformat(timespec="seconds"), "rfps": rows, "runs": recent})


def library():
    """Every RFP in the library, with the newest run on each, and the latest runs."""
    return cached_answer("library", LIBRARY_CACHE_SECONDS, build_library)


def pick(source, keys):
    return {key: source[key] for key in keys if key in source}


def shown_findings(found):
    """Only what the RFP page shows from each finding."""
    packet, qualification, research = found.get("packet"), found.get("qualification"), found.get("research")
    return {
        "packet": packet and {
            **pick(packet, ("headline", "recommendation", "open_items")),
            "expected_worth": pick(packet.get("expected_worth") or {}, ("low", "likely", "high", "confidence", "basis")),
            "deadlines": [pick(date, ("kind", "as_written", "page")) for date in packet.get("deadlines", [])],
            "calls_for_doug": [pick(call, ("topic", "choice_made", "why")) for call in packet.get("calls_for_doug", [])],
            "risks": [pick(risk, ("risk", "source")) for risk in packet.get("risks", [])],
        },
        "qualification": qualification and {
            **pick(qualification, ("decision", "headline")),
            "decision_reasons": [
                {"reason": reason.get("reason"), "cite": pick(reason.get("cite") or {}, ("doc", "page", "quote"))}
                for reason in qualification.get("decision_reasons", [])
            ],
        },
        "research": research and {
            "value_estimate": pick(research.get("value_estimate") or {}, ("low", "likely", "high", "confidence", "basis")),
            "comparables": [
                pick(comparable, ("buyer", "title", "awarded_on", "awardee", "amount", "amount_kind", "annual_amount", "term_years"))
                for comparable in research.get("comparables", [])
            ],
        },
        "summary": found.get("summary"),
    }


def build_rfp(rfp_id):
    stored = memories()
    memory = stored.get(f"/rfps/{rfp_id}/record.json")
    if not memory:
        return None
    record = json.loads(read(memory))
    found = findings(stored, rfp_id)
    newest = newest_by_rfp(rfp_runs()).get(rfp_id)
    run = run_summary(newest, live.STEP_COUNT) if newest else None
    now = datetime.now(timezone.utc)
    saved = {finding["name"] for finding in record.get("findings", [])}
    return scrubbed({
        **library_row(record, found.get("packet"), run, now),
        **pick(record, ("notice_type", "set_aside", "place_of_performance")),
        "draft_ready": any(name in saved for name in DRAFT_FILES),
        "findings": shown_findings(found),
    })


def rfp(rfp_id):
    """One RFP's record, whatever findings runs have saved, and its newest run. None if it is not in the library."""
    return cached_answer(f"rfp:{rfp_id}", RFP_CACHE_SECONDS, lambda: build_rfp(rfp_id))
