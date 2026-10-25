"""AWS Lambda entry point: the SAM.gov research pipeline as a remote MCP tool server.

Served from a Lambda Function URL. Speaks MCP's Streamable HTTP transport in its stateless form:
each POST carries one JSON-RPC message (or a batch) and gets a JSON reply; there is no session and
no server-sent-event stream.

Every request needs `Authorization: Bearer <token>`. Tokens live in a Secrets Manager secret as a
JSON object of {"caller name": "token"} (cloud/tokens.sh manages it); the name is what appears in
the logs. For local testing, SAM_TOOL_TOKENS may hold the same JSON instead.

Unlike the local pipeline there is no profile.json and no saved state: each caller passes its own
codes, and the calling agent judges fit itself.
"""

import base64
import hmac
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# In the deployment zip the pipeline modules sit next to this file; in the repo they're in scripts/.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))

import fetch_sam_opportunities as fetch  # noqa: E402
from filter_open import RESTRICTED_SET_ASIDES, filter_rows  # noqa: E402
from scores import plain  # noqa: E402

PROTOCOL_VERSION = "2025-06-18"
TOKEN_CACHE_SECONDS = 300
# An unrecognised token triggers a reload at most this often, so a newly added token works almost
# at once without letting bad tokens hammer Secrets Manager.
TOKEN_MISS_RELOAD_SECONDS = 30
MAX_CODES = 25
# Claude Code and the Agent SDK divert MCP results over 50,000 characters to a file, so a page of
# compact notices stays well under that (~700 characters each).
DEFAULT_LIMIT = 40
MAX_LIMIT = 60
RESOURCES_URL = "https://sam.gov/api/prod/opps/v3/opportunities/{notice_id}/resources"
DOWNLOAD_URL = "https://sam.gov/api/prod/opps/v3/opportunities/resources/files/{resource_id}/download"

TOOLS = [
    {
        "name": "search_opportunities",
        "description": (
            "Search SAM.gov for federal contract opportunities a business can still respond to. Returns "
            "only open solicitations, presolicitations, sources sought and RFI-style special notices for "
            "the given NAICS/PSC codes; award notices, expired, cancelled and already-awarded notices are "
            "removed, and so are set-asides the business isn't eligible for. Takes 10-60 seconds. Each "
            "notice has a short plain-text description; call get_notice for the full text and attachments. Results "
            "are paged nearest-deadline first: if has_more is true, call again with offset=next_offset."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "naics": {
                    "type": "array",
                    "items": {"type": "string", "pattern": "^[0-9]{2,6}$"},
                    "description": "NAICS codes, e.g. [\"541511\", \"541512\"].",
                },
                "psc": {
                    "type": "array",
                    "items": {"type": "string", "pattern": "^[A-Za-z0-9]{1,4}$"},
                    "description": "Optional Product Service Codes, e.g. [\"DA01\"].",
                },
                "set_aside_eligibility": {
                    "type": "array",
                    "items": {"type": "string", "enum": sorted(RESTRICTED_SET_ASIDES)},
                    "description": (
                        "Set-asides the business qualifies for (SBA/SBP small business, 8A/8AN, HZC/HZS "
                        "HUBZone, SDVOSBC/SDVOSBS, WOSB/WOSBSS, EDWOSB/EDWOSBSS, VSA/VSS, ISBEE/IEE). "
                        "Omit to keep every set-aside. Unrestricted notices are always kept."
                    ),
                },
                "days": {"type": "integer", "minimum": 0, "description": "Only deadlines within this many days."},
                "include_no_deadline": {
                    "type": "boolean",
                    "description": "Also return notices with no response date (often presolicitations).",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_LIMIT,
                    "description": f"Notices per page, nearest deadline first (default {DEFAULT_LIMIT}).",
                },
                "offset": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Skip this many notices; pass the previous page's next_offset to continue.",
                },
            },
        },
    },
    {
        "name": "get_notice",
        "description": (
            "Full detail for one SAM.gov notice: complete description, every point of contact, set-aside, "
            "place of performance, any award recorded against it, and download links for its attachments "
            "(the RFP documents)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"notice_id": {"type": "string", "description": "The notice_id from search_opportunities."}},
            "required": ["notice_id"],
        },
    },
]


# --------------------------------------------------------------------------- auth
_tokens = {"loaded": 0.0, "by_token": {}}


def load_tokens(force=False):
    """{token: caller name}, from Secrets Manager (cached) or SAM_TOOL_TOKENS."""
    if not force and time.time() - _tokens["loaded"] < TOKEN_CACHE_SECONDS and _tokens["by_token"]:
        return _tokens["by_token"]
    raw = os.environ.get("SAM_TOOL_TOKENS")
    secret_id = os.environ.get("SAM_TOOL_TOKENS_SECRET")
    if secret_id:
        import boto3  # in the Lambda runtime; not needed locally

        raw = boto3.client("secretsmanager").get_secret_value(SecretId=secret_id)["SecretString"]
    names = json.loads(raw or "{}")
    _tokens["by_token"] = {token: name for name, token in names.items() if token}
    _tokens["loaded"] = time.time()
    return _tokens["by_token"]


def caller_for(headers):
    """The caller name for this request's bearer token, or None."""
    auth = headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    presented = auth[7:].strip()

    def match(tokens):
        for token, name in tokens.items():
            if hmac.compare_digest(presented, token):
                return name
        return None

    name = match(load_tokens())
    if name is None and time.time() - _tokens["loaded"] > TOKEN_MISS_RELOAD_SECONDS:
        name = match(load_tokens(force=True))
    return name


# --------------------------------------------------------------------------- tools
def codes(args, key, pattern):
    values = [str(v).strip().upper() for v in args.get(key) or [] if str(v).strip()]
    bad = [v for v in values if not re.fullmatch(pattern, v)]
    if bad:
        raise ValueError(f"invalid {key} code(s): {', '.join(bad)}")
    if len(values) > MAX_CODES:
        raise ValueError(f"at most {MAX_CODES} {key} codes per search")
    return values


def compact(row):
    return {
        "notice_id": row.get("notice_id"),
        "title": row.get("title"),
        "notice_type": row.get("notice_type"),
        "response_kind": row.get("response_kind"),
        "days_left": row.get("days_left"),
        "response_date": row.get("response_date"),
        "agency": " / ".join(p for p in (row.get("department"), row.get("sub_tier"), row.get("office")) if p) or None,
        "set_aside": row.get("set_aside") or None,
        "naics_codes": row.get("naics_codes"),
        "psc_code": row.get("psc_code"),
        "place_of_performance": row.get("place_of_performance") or None,
        "solicitation_number": row.get("solicitation_number"),
        "contact_email": row.get("contact_email"),
        "description": plain(row.get("description_excerpt"))[:300],
        "url": row.get("url"),
    }


def search_opportunities(args):
    profile = {"naics": codes(args, "naics", r"\d{2,6}"), "psc": codes(args, "psc", r"[A-Z0-9]{1,4}")}
    if not profile["naics"] and not profile["psc"]:
        raise ValueError("pass at least one NAICS or PSC code")
    eligible = args.get("set_aside_eligibility")
    eligible = None if eligible is None else {str(c) for c in eligible}
    days = args.get("days")
    rows, fetched_at = fetch.collect(
        profile,
        include_no_deadline=bool(args.get("include_no_deadline")),
        workers=10,
        log=lambda msg: print(msg),
    )
    kept, dropped = filter_rows(
        rows,
        eligible=eligible,
        now=fetched_at,
        days=int(days) if days is not None else None,
        include_no_deadline=bool(args.get("include_no_deadline")),
    )
    # Stable order so paging across separate calls neither skips nor repeats a notice.
    kept.sort(key=lambda r: (r.get("days_left") is None, r.get("days_left") or 0, r.get("response_date") or "", r["notice_id"]))
    limit = min(max(int(args.get("limit") or DEFAULT_LIMIT), 1), MAX_LIMIT)
    offset = max(int(args.get("offset") or 0), 0)
    page = kept[offset : offset + limit]
    has_more = offset + limit < len(kept)
    return {
        "fetched_at": fetched_at.isoformat(),
        "total": len(kept),
        "offset": offset,
        "returned": len(page),
        "has_more": has_more,
        "next_offset": offset + limit if has_more else None,
        "dropped": dropped,
        "notices": [compact(row) for row in page],
    }


def get_notice(args):
    notice_id = str(args.get("notice_id") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{32}", notice_id):
        raise ValueError("notice_id must be the 32-character id from search_opportunities")
    with ThreadPoolExecutor(max_workers=3) as pool:
        detail_f = pool.submit(fetch.get_json, fetch.DETAIL_URL.format(notice_id=notice_id))
        resources_f = pool.submit(fetch.get_json, RESOURCES_URL.format(notice_id=notice_id))
        award_f = pool.submit(fetch.related_award, notice_id)
        detail = detail_f.result()
        try:
            resources = resources_f.result()
        except RuntimeError:
            resources = {}
        try:
            award = fetch.award_of(detail.get("data2")) or award_f.result()
        except RuntimeError:
            award = None

    data = detail.get("data2") or {}
    descriptions = detail.get("description") or [{}]
    solicitation = data.get("solicitation") or {}
    place = data.get("placeOfPerformance") or {}
    naics = []
    for entry in data.get("naics") or []:
        found = entry.get("code")
        naics.extend(found if isinstance(found, list) else [found])
    attachments = []
    for group in (resources.get("_embedded") or {}).get("opportunityAttachmentList") or []:
        for item in group.get("attachments") or []:
            if item.get("deletedFlag") == "1":
                continue
            attachments.append(
                {
                    "name": item.get("name"),
                    "size_bytes": item.get("size"),
                    "access": item.get("accessLevel"),
                    "url": item.get("uri")
                    or DOWNLOAD_URL.format(resource_id=item.get("resourceId")),
                }
            )
    return {
        "notice_id": notice_id,
        "title": data.get("title"),
        "solicitation_number": data.get("solicitationNumber"),
        "notice_type": fetch.NOTICE_TYPES.get((data.get("type") or "").lower(), data.get("type")),
        "posted_date": detail.get("postedDate"),
        "response_deadline": (solicitation.get("deadlines") or {}).get("response"),
        "archive_date": (data.get("archive") or {}).get("date"),
        "set_aside": solicitation.get("setAside"),
        "naics_codes": [c for c in naics if c],
        "psc_code": data.get("classificationCode"),
        "place_of_performance": place,
        "contacts": [
            {k: c.get(k) for k in ("type", "fullName", "title", "email", "phone")}
            for c in data.get("pointOfContact") or []
        ],
        "award": award,
        "cancelled": detail.get("cancelled"),
        "description": plain(descriptions[0].get("body"))[:20000],
        "attachments": attachments,
        "url": fetch.UI_URL.format(notice_id=notice_id),
    }


HANDLERS = {"search_opportunities": search_opportunities, "get_notice": get_notice}


# --------------------------------------------------------------------------- MCP
def rpc(message, caller):
    """Reply to one JSON-RPC message, or None for a notification."""
    if "id" not in message:
        return None
    method, params = message.get("method"), message.get("params") or {}
    reply = {"jsonrpc": "2.0", "id": message["id"]}
    if method == "initialize":
        reply["result"] = {
            "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "sam-research", "version": "1.0.0"},
            "instructions": (
                "Call search_opportunities with the business's NAICS codes (and set-aside eligibility if "
                "known), judge each notice's fit against what the business does, then call get_notice "
                "for the promising ones."
            ),
        }
    elif method == "ping":
        reply["result"] = {}
    elif method == "tools/list":
        reply["result"] = {"tools": TOOLS}
    elif method == "tools/call":
        name = params.get("name")
        handler = HANDLERS.get(name)
        if handler is None:
            reply["error"] = {"code": -32602, "message": f"unknown tool {name!r}"}
            return reply
        started = time.time()
        try:
            text, is_error = json.dumps(handler(params.get("arguments") or {}), separators=(",", ":")), False
        except (ValueError, RuntimeError) as exc:
            text, is_error = f"Error: {exc}", True
        print(json.dumps({"caller": caller, "tool": name, "ok": not is_error, "seconds": round(time.time() - started, 1)}))
        reply["result"] = {"content": [{"type": "text", "text": text}], "isError": is_error}
    else:
        reply["error"] = {"code": -32601, "message": f"method not found: {method}"}
    return reply


def respond(status, body=None):
    response = {"statusCode": status, "headers": {"Content-Type": "application/json"}}
    if body is not None:
        response["body"] = json.dumps(body)
    return response


def lambda_handler(event, context):
    method = ((event.get("requestContext") or {}).get("http") or {}).get("method", "POST")
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

    caller = caller_for(headers)
    if caller is None:
        response = respond(401, {"error": "missing or invalid bearer token"})
        response["headers"]["WWW-Authenticate"] = "Bearer"
        return response
    if method != "POST":
        # Stateless server: no SSE stream to open (GET) and no session to end (DELETE).
        return respond(405, {"error": "POST JSON-RPC messages to this URL"})

    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    try:
        message = json.loads(body)
    except json.JSONDecodeError:
        return respond(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})

    if isinstance(message, list):
        replies = [r for r in (rpc(m, caller) for m in message if isinstance(m, dict)) if r]
        return respond(200, replies) if replies else respond(202)
    if not isinstance(message, dict):
        return respond(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}})
    reply = rpc(message, caller)
    return respond(200, reply) if reply else respond(202)
