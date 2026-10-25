"""Keep the RFP Library memory store filled from SAM.gov, with each RFP's documents and findings.

Our code writes the library and the agents only read it. Three jobs, run from the repo root:

    python3 agent/library.py sync                                  store every open notice not yet stored
    python3 agent/library.py fetch-documents <rfp-id>              upload a notice's attachments to the Files API
    python3 agent/library.py save-findings <session-id> <rfp-id>   copy a finished run's results into the library

Every job needs ANTHROPIC_API_KEY. sync and fetch-documents also need SAM_TOOL_URL and SAM_TOOL_TOKEN.
agent/README.md has the one-line command that reads them from Secret Manager. An RFP's id is its
SAM.gov notice id.
"""

import argparse
import hashlib
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from setup import AGENTS_BETA, API, IDS_FILE, MEMORY_BETA

# Cadocary's registered codes, from memory/cadocary-facts/README.md. SAM.gov retired 511210 in 2022,
# so its replacement 513210 and the closely related 541512 are added. A coverage check on Oct 25
# found 36 more notices with them.
NAICS = ["511210", "513210", "518210", "541511", "541512", "541519"]
PSC = ["7A20", "DA10", "D302", "D308", "DA01"]
SEARCH_PAGE_SIZE = 60  # the SAM tool's maximum

MEMORY_LIMIT_BYTES = 102_400  # per memory, from the memory store API reference
RECORD_PATH = re.compile(r"/rfps/[^/]+/record\.json")
INDEX_FORMAT = "rfp-id | buyer | title | proposal deadline | status"

# The full get_notice result, stored next to the attachments, because many SAM.gov notices put the
# statement of work in the description rather than in a file.
NOTICE_FILE = "sam-notice.json"

# The agents' results and the proposal. Everything else in a session's outputs is working material:
# copies and text versions of the RFP's documents, and the Reader's scripts.
FINDING_SUFFIXES = (".json", ".md")


def send(method, url, *, headers, body=None, shown_as=None):
    """Send one request and return the reply body, waiting out rate limits and overloads.

    A dropped connection is retried only for GET: a POST may have landed, and sending it again could
    start a second session or upload a file twice.
    """
    attempts = 5
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=300) as reply:
                return reply.read()
        except urllib.error.HTTPError as error:
            if error.code not in (429, 529) or attempt == attempts:
                sys.exit(f"{method} {shown_as or url} failed ({error.code}): {error.read().decode()}")
        except (urllib.error.URLError, TimeoutError) as error:
            if method != "GET" or attempt == attempts:
                sys.exit(f"{method} {shown_as or url} failed: {error}")
        time.sleep(2**attempt)


def anthropic_headers(beta):
    return {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "anthropic-beta": beta}


def anthropic(method, path, body=None, *, beta=AGENTS_BETA):
    headers = anthropic_headers(beta)
    payload = None
    if body is not None:
        payload = json.dumps(body).encode()
        headers["content-type"] = "application/json"
    reply = send(method, f"{API}/{path}", headers=headers, body=payload)
    return json.loads(reply) if reply else {}


def upload(name, content):
    """Store one file in the Files API and return its id."""
    boundary = uuid.uuid4().hex
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    disposition = f'form-data; name="file"; filename="{name.replace(chr(34), chr(39))}"'
    body = (
        f"--{boundary}\r\nContent-Disposition: {disposition}\r\nContent-Type: {content_type}\r\n\r\n".encode()
        + content
        + f"\r\n--{boundary}--\r\n".encode()
    )
    headers = {**anthropic_headers(AGENTS_BETA), "content-type": f"multipart/form-data; boundary={boundary}"}
    return json.loads(send("POST", f"{API}/files", headers=headers, body=body))["id"]


def session_outputs(session_id):
    files, page = [], None
    while True:
        query = {"scope_id": session_id, "limit": 100, **({"page": page} if page else {})}
        listing = anthropic("GET", f"files?{urllib.parse.urlencode(query)}")
        files += listing["data"]
        page = listing.get("next_page")
        if not listing.get("has_more") or not page:
            return files


def sam(tool, arguments):
    """Call one tool on the hosted SAM.gov server and return its result."""
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
    headers = {
        "Authorization": f"Bearer {os.environ['SAM_TOOL_TOKEN']}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    reply = json.loads(send("POST", os.environ["SAM_TOOL_URL"], headers=headers, body=json.dumps(body).encode(), shown_as=f"SAM tool {tool}"))
    if "error" in reply:
        sys.exit(f"SAM tool {tool} failed: {reply['error']}")
    text = reply["result"]["content"][0]["text"]
    if reply["result"].get("isError"):
        sys.exit(f"SAM tool {tool} failed: {text}")
    return json.loads(text)


def download(url):
    """Fetch one RFP attachment. SAM.gov attachment links need no login."""
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Cadocary bid agent)"})
    with urllib.request.urlopen(request, timeout=300) as reply:
        return reply.read()


def fits_in_memory(content):
    return len(content) <= MEMORY_LIMIT_BYTES


class Library:
    """The RFP Library memory store. Lists every memory once, then reads and writes them by path."""

    def __init__(self):
        self.store_id = json.loads(IDS_FILE.read_text())["memory_stores"]["rfp-library"]["id"]
        self.memories = {}
        page = None
        while True:
            query = {"limit": 100, **({"page": page} if page else {})}
            listing = self.call("GET", f"memories?{urllib.parse.urlencode(query)}")
            self.memories.update((item["path"], item) for item in listing["data"] if item["type"] == "memory")
            page = listing.get("next_page")
            if not page:
                return

    def call(self, method, path, body=None):
        return anthropic(method, f"memory_stores/{self.store_id}/{path}", body, beta=MEMORY_BETA)

    def read(self, path):
        return self.call("GET", f"memories/{self.memories[path]['id']}")["content"]

    def write(self, path, text):
        """Create or replace the memory at path. Unchanged content is not sent again."""
        content = text.encode()
        if not fits_in_memory(content):
            sys.exit(f"{path} is {len(content):,} bytes, over the {MEMORY_LIMIT_BYTES:,}-byte memory limit.")
        digest = hashlib.sha256(content).hexdigest()
        existing = self.memories.get(path)
        if existing and existing["content_sha256"] == digest:
            return
        if existing:
            memory = self.call("POST", f"memories/{existing['id']}", {"content": text})
        else:
            memory = self.call("POST", "memories", {"path": path, "content": text})
        self.memories[path] = {"id": memory["id"], "path": path, "content_sha256": digest}

    def delete(self, path):
        self.call("DELETE", f"memories/{self.memories.pop(path)['id']}")

    def record(self, rfp_id):
        path = record_path(rfp_id)
        if path not in self.memories:
            sys.exit(f"RFP {rfp_id} is not in the library. Run `python3 agent/library.py sync` first.")
        return json.loads(self.read(path))

    def save_record(self, record):
        self.write(record_path(record["rfp_id"]), json.dumps(record, indent=2) + "\n")

    def rebuild_index(self):
        """Rewrite the index from every stored record, and return how many RFPs it lists."""
        paths = [path for path in self.memories if RECORD_PATH.fullmatch(path)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            records = [json.loads(text) for text in pool.map(self.read, paths)]
        pages = index_pages(records)
        for path, text in pages.items():
            self.write(path, text)
        for path in [path for path in self.memories if path.startswith("/index/") and path not in pages]:
            self.delete(path)
        return len(records)


def record_path(rfp_id):
    return f"/rfps/{rfp_id}/record.json"


def new_record(notice, found_at):
    return {
        "rfp_id": notice["notice_id"],
        "status": "new",
        "title": notice["title"],
        "agency": notice.get("agency"),
        "notice_type": notice.get("notice_type"),
        "response_kind": notice.get("response_kind"),
        "deadline": notice.get("response_date"),
        "days_left": notice.get("days_left"),
        "days_left_as_of": found_at.date().isoformat(),
        "solicitation_number": notice.get("solicitation_number"),
        "set_aside": notice.get("set_aside"),
        "naics_codes": notice.get("naics_codes"),
        "psc_code": notice.get("psc_code"),
        "place_of_performance": notice.get("place_of_performance"),
        "description_start": notice.get("description"),
        "sam_url": notice["url"],
        "found": {"source": "SAM.gov", "tool": "search_opportunities", "at": found_at.isoformat(timespec="seconds")},
        "documents": [],
        "findings": [],
        "runs": [],
    }


def deadline(record):
    return datetime.fromisoformat(record["deadline"]) if record["deadline"] else None


def deadline_order(record):
    when = deadline(record)
    return (when is None, when.timestamp() if when else 0)


def deadline_month(record):
    when = deadline(record)
    return when.astimezone(timezone.utc).strftime("%Y-%m") if when else "no-deadline"


def index_line(record):
    fields = [record["rfp_id"], record["agency"] or "unknown buyer", record["title"], record["deadline"] or "none", record["status"]]
    return " | ".join(str(field).replace("|", "/").replace("\n", " ") for field in fields) + "\n"


def index_text(heading, records):
    return (
        f"# {heading}\n\n"
        f"One line per RFP, nearest proposal deadline first: `{INDEX_FORMAT}`. "
        "Each RFP's record is at `/rfps/<rfp-id>/record.json`.\n\n" + "".join(index_line(record) for record in records)
    )


def index_pages(records):
    """The index memories to write, by path: one file while it fits in a memory, otherwise one per deadline month."""
    records = sorted(records, key=deadline_order)
    whole = index_text("RFP index", records)
    if fits_in_memory(whole.encode()):
        return {"/index.md": whole}
    months = {}
    for record in records:
        months.setdefault(deadline_month(record), []).append(record)
    pages = {f"/index/{month}.md": index_text(f"RFP index: {month}", group) for month, group in months.items()}
    pages["/index.md"] = (
        "# RFP index\n\nToo long for one memory, so it is split by proposal deadline month. "
        f"Each month's file has one line per RFP: `{INDEX_FORMAT}`.\n\n"
        + "".join(f"- `/index/{month}.md`: {len(group)} RFPs\n" for month, group in months.items())
    )
    return pages


def search_all():
    """Every open notice for Cadocary's codes, paging until the tool says there are no more."""
    notices, offset = {}, 0
    while True:
        page = sam("search_opportunities", {"naics": NAICS, "psc": PSC, "limit": SEARCH_PAGE_SIZE, "offset": offset})
        notices.update((notice["notice_id"], notice) for notice in page["notices"])
        if not page["has_more"]:
            return list(notices.values())
        offset = page["next_offset"]


def sync():
    library = Library()
    notices = search_all()
    new = [notice for notice in notices if record_path(notice["notice_id"]) not in library.memories]
    found_at = datetime.now(timezone.utc)
    for notice in new:
        library.save_record(new_record(notice, found_at))
    listed = library.rebuild_index()
    print(f"SAM.gov search: {len(notices)} open notices for Cadocary's codes.")
    print(f"Wrote {len(new)} new records. {len(notices) - len(new)} were already stored. The index lists {listed} RFPs.")


def unique_name(name, taken):
    """A file name not yet used for this RFP, since all of its documents mount in one folder."""
    name = name.replace("/", "-")
    stem, dot, extension = name.rpartition(".")
    if not dot:
        stem, extension = name, ""
    candidate, number = name, 2
    while candidate in taken:
        candidate = f"{stem} ({number}){dot}{extension}"
        number += 1
    return candidate


def fetch_documents(rfp_id):
    """Upload every attachment of the notice that isn't stored yet, and return the updated record.

    Safe to run again: stored files are skipped, and a download that failed before is tried again.
    """
    library = Library()
    record = library.record(rfp_id)
    notice = sam("get_notice", {"notice_id": rfp_id})
    record["documents"] = [document for document in record["documents"] if document["file_id"]]
    stored = {document["url"] for document in record["documents"]}
    uploaded, failed = 0, []

    def store(name, url, content):
        record["documents"].append({
            "name": name, "url": url, "size_bytes": len(content), "file_id": upload(name, content),
            "uploaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        library.save_record(record)

    if notice["url"] not in stored:
        store(NOTICE_FILE, notice["url"], json.dumps(notice, indent=2).encode())
        uploaded += 1
    for attachment in notice["attachments"]:
        if attachment["url"] in stored:
            continue
        name = unique_name(attachment["name"], {document["name"] for document in record["documents"]})
        try:
            content = download(attachment["url"])
        except (urllib.error.URLError, TimeoutError) as error:
            failed.append({"name": name, "url": attachment["url"], "size_bytes": attachment.get("size_bytes"), "file_id": None, "error": str(error)})
            continue
        store(name, attachment["url"], content)
        uploaded += 1

    # Failed downloads stay on the record, so a run can hand their links to the Reader instead.
    record["documents"] += failed
    library.save_record(record)
    print(f"{rfp_id}: {len(record['documents']) - len(failed)} documents stored ({uploaded} uploaded now), {len(failed)} failed.")
    for document in failed:
        print(f"  could not download {document['name']}: {document['error']}")
    return record


def parsed_json(outputs, name):
    if name not in outputs:
        return None
    try:
        return json.loads(outputs[name])
    except json.JSONDecodeError:
        print(f"  {name} is not valid JSON, so the status ignores it.")
        return None


def status_after_run(outputs, current):
    """The step an RFP has reached, from the files a run wrote. A run that stops early leaves it at the next step."""
    packet = parsed_json(outputs, "packet.json")
    qualification = parsed_json(outputs, "qualification.json")
    if packet:
        return "ready_for_doug" if packet.get("recommendation") == "send" else "passed"
    if qualification and qualification.get("decision") == "pass":
        return "passed"
    if "research.json" in outputs or "draft.json" in outputs:
        return "drafting"
    if qualification:
        return "researching"
    if "sheet.json" in outputs:
        return "qualifying"
    return current


def save_findings(session_id, rfp_id):
    """Copy a session's results into /rfps/<rfp-id>/findings/ and update the RFP's status."""
    library = Library()
    record = library.record(rfp_id)
    originals = {document["name"] for document in record["documents"]}
    copied = {finding["from_file_id"] for finding in record["findings"]}
    outputs = {}
    for output in session_outputs(session_id):
        name = output["filename"]
        if not name.endswith(FINDING_SUFFIXES) or name in originals or output["id"] in copied:
            continue
        content = send("GET", f"{API}/files/{output['id']}/content", headers=anthropic_headers(AGENTS_BETA))
        outputs[name] = content
        finding = {"name": name, "size_bytes": len(content), "session_id": session_id, "from_file_id": output["id"]}
        if fits_in_memory(content):
            finding["memory_path"] = f"/rfps/{rfp_id}/findings/{name}"
            library.write(finding["memory_path"], content.decode())
        else:
            finding["file_id"] = upload(name, content)
        record["findings"].append(finding)
        where = finding.get("memory_path") or f"Files API {finding['file_id']} (too big for a memory)"
        print(f"  saved {name} ({len(content):,} bytes) to {where}")

    previous = record["status"]
    record["status"] = status_after_run(outputs, previous)
    record["runs"].append({"session_id": session_id, "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "status": record["status"]})
    library.save_record(record)
    library.rebuild_index()
    print(f"{rfp_id}: saved {len(outputs)} findings. Status {previous} -> {record['status']}.")
    return record


def require_environment(*names):
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        sys.exit(f"Set {', '.join(missing)} first. See agent/README.md for the one-line command.")


def main():
    parser = argparse.ArgumentParser(description="Keep the RFP Library filled from SAM.gov.")
    jobs = parser.add_subparsers(dest="job", required=True)
    jobs.add_parser("sync", help="store every open notice for Cadocary's codes that isn't stored yet")
    fetch = jobs.add_parser("fetch-documents", help="upload one RFP's attachments to the Files API")
    fetch.add_argument("rfp_id")
    save = jobs.add_parser("save-findings", help="copy a finished session's results into the library")
    save.add_argument("session_id")
    save.add_argument("rfp_id")
    args = parser.parse_args()

    if args.job == "save-findings":
        require_environment("ANTHROPIC_API_KEY")
        save_findings(args.session_id, args.rfp_id)
        return
    require_environment("ANTHROPIC_API_KEY", "SAM_TOOL_URL", "SAM_TOOL_TOKEN")
    if args.job == "sync":
        sync()
    else:
        fetch_documents(args.rfp_id)


if __name__ == "__main__":
    main()
