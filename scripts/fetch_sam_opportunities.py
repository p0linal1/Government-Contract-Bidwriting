#!/usr/bin/env python3
"""Pull open SAM.gov contract opportunities matching a vendor profile's NAICS/PSC codes.

Uses the same public endpoints sam.gov's own search UI calls, so no API key is needed:

  search   https://sam.gov/api/prod/sgs/v1/search/?index=opp&naics=<codes>&notice_type=<types>
  detail   https://sam.gov/api/prod/opps/v2/opportunities/<notice_id>
  related  https://sam.gov/api/prod/opps/v2/opportunities/<notice_id>/relatedopportunities

All require `Accept: application/hal+json` or they answer 406.

By default the search itself is restricted to notice types a vendor can respond to and to response
deadlines still ahead, so award notices and expired solicitations are never downloaded or enriched.
Each surviving notice is then checked against its related notices, which is where SAM records an
award made against a solicitation that is still listed as active.

Usage:
  python3 scripts/fetch_sam_opportunities.py                      # reads profile.json
  python3 scripts/fetch_sam_opportunities.py --profile acme.json --no-enrich
  python3 scripts/fetch_sam_opportunities.py --all-notices --include-inactive   # past-performance research
"""

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

SEARCH_URL = "https://sam.gov/api/prod/sgs/v1/search/"
DETAIL_URL = "https://sam.gov/api/prod/opps/v2/opportunities/{notice_id}"
RELATED_URL = "https://sam.gov/api/prod/opps/v2/opportunities/{notice_id}/relatedopportunities"
UI_URL = "https://sam.gov/opp/{notice_id}/view"
# The search API accepts up to 1,000 per page, so a filtered pull is usually a single request.
PAGE_SIZE = 1000
HEADERS = {
    "Accept": "application/hal+json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

# SAM's notice-type codes. Only RFPs are requested by default — a Solicitation or a Combined
# Synopsis/Solicitation is the government asking for a bid. The wider set adds the notice types
# that ask for something other than a bid: Sources Sought is market research, a Presolicitation is
# advance warning, and a Special Notice is usually an industry day with nothing to respond to.
NOTICE_TYPES = {
    "o": "Solicitation",
    "k": "Combined Synopsis/Solicitation",
    "p": "Presolicitation",
    "r": "Sources Sought",
    "s": "Special Notice",
    "i": "Intent to Bundle Requirements (DoD- Funded)",
    "a": "Award Notice",
    "u": "Justification",
    "g": "Sale of Surplus Property",
}
RFP_TYPES = "o,k"
RESPONSIVE_TYPES = "o,k,p,r,i"

DEFAULT_PROFILE = "profile.json"


def load_profile(path):
    path = Path(path)
    if not path.exists():
        sys.exit(f"no profile at {path} — copy profile.example.json to profile.json and set your NAICS codes")
    return json.loads(path.read_text())


def get_json(url, params=None, attempts=4):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    last = None
    for attempt in range(attempts):
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # A 4xx other than rate limiting will not get better on retry.
            if 400 <= exc.code < 500 and exc.code != 429:
                raise RuntimeError(f"{url}: HTTP {exc.code}") from exc
            last = exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"giving up on {url}: {last}")


def search(field, codes, notice_types=RFP_TYPES, response_from=None, include_inactive=False):
    """Every notice carrying any of `codes` (one NAICS or PSC field), as search-result dicts.

    SAM ORs a comma-separated code list, so all of a profile's NAICS codes cost one query.
    """
    found, page = [], 0
    while True:
        params = {
            "index": "opp",
            "mode": "search",
            "sort": "-modifiedDate",
            "mfe": "true",
            "page": page,
            "size": PAGE_SIZE,
            field: ",".join(codes),
            "is_active": "true",
        }
        if notice_types:
            params["notice_type"] = notice_types
        if response_from:
            params["response_date.from"] = response_from
        if include_inactive:
            params["is_inactive"] = "true"
        payload = get_json(SEARCH_URL, params)
        results = payload.get("_embedded", {}).get("results", [])
        found.extend(results)
        meta = payload.get("page", {})
        if page == 0 and meta.get("totalElements", 0) > meta.get("maxAllowedRecords", float("inf")):
            print(
                f"  warning: {field} matched {meta['totalElements']} notices but SAM only pages through "
                f"{meta['maxAllowedRecords']}; narrow the codes or drop --all-notices",
                file=sys.stderr,
            )
        page += 1
        if not results or page >= meta.get("totalPages", 0):
            break
    return found


def org_names(hierarchy):
    """Flatten SAM's org hierarchy into department / sub-tier / office."""
    levels = {entry.get("type"): entry.get("name") for entry in hierarchy or []}
    return (
        levels.get("DEPARTMENT") or "",
        levels.get("AGENCY") or levels.get("SUB-TIER") or "",
        levels.get("OFFICE") or "",
    )


def flatten(record, matched_by):
    descriptions = record.get("descriptions") or [{}]
    department, sub_tier, office = org_names(record.get("organizationHierarchy"))
    return {
        "notice_id": record.get("_id"),
        "title": record.get("title"),
        "solicitation_number": record.get("solicitationNumber"),
        "notice_type": (record.get("type") or {}).get("value"),
        "department": department,
        "sub_tier": sub_tier,
        "office": office,
        "publish_date": record.get("publishDate"),
        "modified_date": record.get("modifiedDate"),
        "response_date": record.get("responseDate"),
        "response_timezone": record.get("responseTimeZone"),
        "is_canceled": record.get("isCanceled"),
        "matched_by": sorted(matched_by),
        "description_excerpt": (descriptions[0].get("content") or "")[:1000],
        "url": UI_URL.format(notice_id=record.get("_id")),
    }


def award_of(data2):
    """The award block of a notice's data2, or None if it records no award."""
    award = (data2 or {}).get("award") or {}
    awardee = award.get("awardee") or {}
    if not (awardee.get("name") or award.get("amount") or award.get("number")):
        return None
    return {
        "awardee": (awardee.get("name") or "").strip(),
        "awardee_uei": awardee.get("ueiSAM"),
        "amount": award.get("amount"),
        "date": award.get("date"),
        "contract_number": award.get("number"),
    }


def related_award(notice_id):
    """An award SAM has linked to this notice through its related notices, or None."""
    related = get_json(RELATED_URL.format(notice_id=notice_id))
    for entry in related.get("relatedOpportunities") or []:
        found = award_of(entry.get("data2"))
        if found:
            data2 = entry.get("data2") or {}
            found["award_notice_id"] = data2.get("opportunityId") or data2.get("id")
            return found
    return None


def enrich(row):
    """Add what only the detail endpoints carry: full NAICS/PSC, set-aside, POC, and any award."""
    try:
        detail = get_json(DETAIL_URL.format(notice_id=row["notice_id"]))
    except RuntimeError as exc:
        row["enrich_error"] = str(exc)
        return row
    data = detail.get("data2") or {}
    naics = []
    for entry in data.get("naics") or []:
        codes = entry.get("code")
        naics.extend(codes if isinstance(codes, list) else [codes])
    solicitation = data.get("solicitation") or {}
    place = data.get("placeOfPerformance") or {}
    contacts = data.get("pointOfContact") or []
    primary = next((c for c in contacts if c.get("type") == "primary"), contacts[0] if contacts else {})
    row.update(
        {
            "naics_codes": [c for c in naics if c],
            "psc_code": data.get("classificationCode"),
            "set_aside": solicitation.get("setAside"),
            "archive_date": (data.get("archive") or {}).get("date"),
            "place_of_performance": " ".join(
                part
                for part in (
                    place.get("city", {}).get("name") if isinstance(place.get("city"), dict) else place.get("city"),
                    (place.get("state") or {}).get("code"),
                    place.get("zip"),
                )
                if part
            ),
            "contact_name": primary.get("fullName"),
            "contact_email": primary.get("email"),
            "contact_phone": primary.get("phone"),
        }
    )
    try:
        row["award"] = award_of(data) or related_award(row["notice_id"])
    except RuntimeError as exc:
        row["award"] = None
        row["enrich_error"] = f"related-notice check failed: {exc}"
    return row


CSV_COLUMNS = [
    "notice_id",
    "title",
    "solicitation_number",
    "notice_type",
    "set_aside",
    "department",
    "sub_tier",
    "office",
    "naics_codes",
    "psc_code",
    "matched_by",
    "publish_date",
    "modified_date",
    "response_date",
    "archive_date",
    "place_of_performance",
    "contact_name",
    "contact_email",
    "contact_phone",
    "url",
]


def write_csv(path, rows, columns):
    with Path(path).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            flat = dict(row)
            for key in ("matched_by", "naics_codes"):
                if isinstance(flat.get(key), list):
                    flat[key] = "; ".join(str(v) for v in flat[key])
            if isinstance(flat.get("award"), dict):
                flat["award"] = flat["award"].get("awardee") or "yes"
            writer.writerow(flat)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="vendor profile JSON (default: profile.json)")
    parser.add_argument("--out-dir", default="data", help="where to write opportunities.json/.csv")
    parser.add_argument("--no-enrich", action="store_true", help="skip the per-notice detail and award checks")
    parser.add_argument(
        "--include-no-deadline",
        action="store_true",
        help="also pull notices with no response date (one extra, larger search per code field)",
    )
    parser.add_argument(
        "--include-market-research",
        action="store_true",
        help="also pull Sources Sought, Presolicitations and Special Notices, which ask for something other than a bid",
    )
    parser.add_argument(
        "--all-notices",
        action="store_true",
        help="drop the server-side type/deadline filters, award notices included (research mode; slow)",
    )
    parser.add_argument("--include-inactive", action="store_true", help="also return archived notices")
    parser.add_argument("--workers", type=int, default=6, help="concurrent detail requests")
    args = parser.parse_args()

    profile = load_profile(args.profile)
    fields = [(f, [str(c) for c in profile.get(f) or []]) for f in ("naics", "psc")]
    fields = [(f, codes) for f, codes in fields if codes]
    if not fields:
        sys.exit(f"{args.profile} lists no naics or psc codes")

    now = datetime.now(timezone.utc)
    wanted_types = RESPONSIVE_TYPES if args.include_market_research else RFP_TYPES
    if args.all_notices:
        queries = [{"notice_types": None, "response_from": None}]
    else:
        queries = [{"notice_types": wanted_types, "response_from": now.strftime("%Y-%m-%dT%H:%M:%S+00:00")}]
        if args.include_no_deadline:
            queries.append({"notice_types": wanted_types, "response_from": None, "no_deadline_only": True})

    by_notice, matches = {}, {}
    for field, codes in fields:
        for query in queries:
            results = search(field, codes, query["notice_types"], query["response_from"], args.include_inactive)
            if query.get("no_deadline_only"):
                results = [r for r in results if not r.get("responseDate")]
            print(f"  {field}={','.join(codes)}: {len(results)}", file=sys.stderr)
            for record in results:
                notice_id = record.get("_id")
                if not notice_id:
                    continue
                by_notice[notice_id] = record
                code_set = set(codes)
                # Search results don't say which code hit; the detail call fills naics_codes later.
                matches.setdefault(notice_id, set()).add(f"{field.upper()} {'/'.join(sorted(code_set))}")

    rows = [flatten(record, matches[nid]) for nid, record in by_notice.items()]
    print(f"{len(rows)} unique notices", file=sys.stderr)

    if not args.no_enrich and rows:
        print(f"fetching detail and award status for {len(rows)} notices...", file=sys.stderr)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            rows = list(pool.map(enrich, rows))
        failed = sum(1 for r in rows if r.get("enrich_error"))
        if failed:
            print(f"  {failed} detail lookups failed", file=sys.stderr)
        awarded = sum(1 for r in rows if r.get("award"))
        if awarded:
            print(f"  {awarded} already have an award recorded against them", file=sys.stderr)
        # Narrow matched_by to the codes that actually appear on the notice.
        wanted = {f: set(codes) for f, codes in fields}
        for row in rows:
            hits = [f"NAICS {c}" for c in row.get("naics_codes") or [] if c in wanted.get("naics", ())]
            if row.get("psc_code") in wanted.get("psc", ()):
                hits.append(f"PSC {row['psc_code']}")
            if hits:
                row["matched_by"] = sorted(hits)

    rows.sort(key=lambda r: r.get("response_date") or "9999")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": now.isoformat(),
        "profile": {
            k: profile.get(k)
            for k in ("legal_business_name", "uei", "cage_code", "naics", "psc", "set_aside_eligibility")
        },
        "filters": {
            "server_side": not args.all_notices,
            "notice_types": None if args.all_notices else wanted_types,
            "include_no_deadline": args.include_no_deadline,
            "include_inactive": args.include_inactive,
            "enriched": not args.no_enrich,
        },
        "count": len(rows),
        "opportunities": rows,
    }
    (out_dir / "opportunities.json").write_text(json.dumps(payload, indent=2))
    write_csv(out_dir / "opportunities.csv", rows, CSV_COLUMNS)
    print(f"wrote {out_dir/'opportunities.json'} and {out_dir/'opportunities.csv'}", file=sys.stderr)


if __name__ == "__main__":
    main()
