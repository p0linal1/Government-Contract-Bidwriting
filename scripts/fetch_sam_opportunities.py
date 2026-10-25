#!/usr/bin/env python3
"""Pull active SAM.gov contract opportunities matching a vendor profile's NAICS/PSC codes.

Uses the same public endpoints sam.gov's own search UI calls, so no API key is needed:

  search  https://sam.gov/api/prod/sgs/v1/search/?index=opp&naics=<code>&is_active=true
  detail  https://sam.gov/api/prod/opps/v2/opportunities/<notice_id>

Both require `Accept: application/hal+json` or they answer 406.

Usage:
  python3 scripts/fetch_sam_opportunities.py --profile profiles/cadocary.json
  python3 scripts/fetch_sam_opportunities.py --profile profiles/cadocary.json --no-enrich
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
UI_URL = "https://sam.gov/opp/{notice_id}/view"
PAGE_SIZE = 100
HEADERS = {
    "Accept": "application/hal+json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}


def get_json(url, params=None, attempts=4):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    last = None
    for attempt in range(attempts):
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"giving up on {url}: {last}")


def search_code(field, code, include_inactive=False):
    """Every active notice carrying one NAICS or PSC code, as search-result dicts."""
    found, page = [], 0
    while True:
        params = {
            "index": "opp",
            "mode": "search",
            "sort": "-modifiedDate",
            "mfe": "true",
            "page": page,
            "size": PAGE_SIZE,
            field: code,
            "is_active": "true",
        }
        if include_inactive:
            params["is_inactive"] = "true"
        payload = get_json(SEARCH_URL, params)
        results = payload.get("_embedded", {}).get("results", [])
        found.extend(results)
        meta = payload.get("page", {})
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


def enrich(row):
    """Add the fields that only the detail endpoint carries: full NAICS/PSC, set-aside, POC."""
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


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", default="profiles/cadocary.json", help="vendor profile JSON")
    parser.add_argument("--out-dir", default="data", help="where to write opportunities.json/.csv")
    parser.add_argument("--no-enrich", action="store_true", help="skip the per-notice detail calls")
    parser.add_argument("--include-inactive", action="store_true", help="also return closed notices")
    parser.add_argument("--workers", type=int, default=6, help="concurrent detail requests")
    args = parser.parse_args()

    profile = json.loads(Path(args.profile).read_text())
    codes = [("naics", c) for c in profile.get("naics", [])] + [("psc", c) for c in profile.get("psc", [])]
    if not codes:
        sys.exit(f"{args.profile} lists no naics or psc codes")

    by_notice, matches = {}, {}
    for field, code in codes:
        results = search_code(field, code, args.include_inactive)
        print(f"  {field}={code}: {len(results)}", file=sys.stderr)
        for record in results:
            notice_id = record.get("_id")
            if not notice_id:
                continue
            by_notice[notice_id] = record
            matches.setdefault(notice_id, set()).add(f"{field.upper()} {code}")

    rows = [flatten(record, matches[nid]) for nid, record in by_notice.items()]
    print(f"{len(rows)} unique notices from {len(codes)} codes", file=sys.stderr)

    if not args.no_enrich:
        print(f"fetching detail for {len(rows)} notices...", file=sys.stderr)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            rows = list(pool.map(enrich, rows))
        failed = sum(1 for r in rows if r.get("enrich_error"))
        if failed:
            print(f"  {failed} detail lookups failed", file=sys.stderr)

    rows.sort(key=lambda r: r.get("response_date") or "9999", reverse=False)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "profile": {k: profile.get(k) for k in ("legal_business_name", "uei", "cage_code", "naics", "psc")},
        "count": len(rows),
        "opportunities": rows,
    }
    (out_dir / "opportunities.json").write_text(json.dumps(payload, indent=2))

    with (out_dir / "opportunities.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            flat = dict(row)
            for key in ("matched_by", "naics_codes"):
                if isinstance(flat.get(key), list):
                    flat[key] = "; ".join(str(v) for v in flat[key])
            writer.writerow(flat)

    print(f"wrote {out_dir/'opportunities.json'} and {out_dir/'opportunities.csv'}", file=sys.stderr)


if __name__ == "__main__":
    main()
