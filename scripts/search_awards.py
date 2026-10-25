#!/usr/bin/env python3
"""Pull the federal award evidence an RFP's value estimate is built from.

The research agent has no bash and no POST: USAspending's award search is a POST with a JSON
body, so an agent with only web_fetch cannot issue it. This script does every fetch, and the
agent only reads the result and makes the judgment call.

Public endpoints, no API key:

  notice     https://sam.gov/api/prod/opps/v2/opportunities/<notice_id>
  attachments https://sam.gov/api/prod/opps/v3/opportunities/<notice_id>/resources
  related    https://sam.gov/api/prod/opps/v2/opportunities/<notice_id>/relatedopportunities
  awards     https://api.usaspending.gov/api/v2/search/spending_by_award/   (POST)

SAM requires `Accept: application/hal+json` or it answers 406. Its description text lives in
`description[].body`, and a related award notice's awardee under `data2.award.awardee`.

Subcommands:
  notice    the solicitation's own facts: PSC, NAICS, place of performance, deadline, and the
            description text (which is where the scope lives when there are no attachments)
  related   what SAM recorded as the award against a solicitation — the answer, for a closed one
  history   one contracting office's obligations by fiscal year, filtered to a purpose. This is
            line 1 (affordability) for a federal buyer: what this office actually spends.
  search    structural award search: agency + PSC, optionally narrowed to one office, with
            awards on or after --cutoff excluded so an award made against the solicitation
            under study can never enter the pool used to estimate it
  chain     walk the predecessor references federal award descriptions carry ("PRIOR AWARD X",
            "RENEWAL OF PREVIOUS CONTRACT X") to get a price history and the escalation rate

Usage:
  python3 scripts/search_awards.py notice  <notice_id>
  python3 scripts/search_awards.py related <notice_id>
  python3 scripts/search_awards.py history --agency "Department of Defense" --office W50S9E \
      --purpose RECRUIT,ADVERTIS,MARKET
  python3 scripts/search_awards.py search  --agency "Social Security Administration" --psc 7A21 \
      --cutoff 2026-08-18
  python3 scripts/search_awards.py chain   --agency "Social Security Administration" --psc 7A21
  # add --json to any subcommand for machine-readable output
"""

import argparse
import collections
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SAM_NOTICE = "https://sam.gov/api/prod/opps/v2/opportunities/{notice_id}"
SAM_RESOURCES = "https://sam.gov/api/prod/opps/v3/opportunities/{notice_id}/resources"
SAM_RELATED = "https://sam.gov/api/prod/opps/v2/opportunities/{notice_id}/relatedopportunities"
SAM_FILE = "https://sam.gov/api/prod/opps/v3/opportunities/resources/files/{resource_id}/download"
AWARDS = "https://api.usaspending.gov/api/v2/search/spending_by_award/"

SAM_HEADERS = {
    "Accept": "application/hal+json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

AWARD_FIELDS = [
    "Award ID", "Recipient Name", "Award Amount", "Description",
    "Start Date", "End Date", "Awarding Agency", "Awarding Sub Agency",
]

# A federal PIID: long, upper-case alphanumeric, several digits. The length and digit floor are
# what stop a product name being read as a contract number — an early version of this regex
# returned "ACCESSDATA" from "RENEWAL OF ACCESSDATA ENTERPRISE".
PIID = re.compile(r"^[A-Z0-9]{13,20}$")
PREDECESSOR = re.compile(
    r"(?:PRIOR AWARD|PREVIOUS\s+(?:ORDER|CONTRACT)|RENEWAL OF\s+(?:EXPIRING\s+)?(?:ORDER|CONTRACT)?"
    r"|EXPIRING(?:\s+TO)?)\s*#?\s*([A-Z0-9]{10,24})",
    re.I,
)

# SAM writes a department's name in caps; USAspending wants its own top-tier name.
AGENCY_NAMES = {
    "AGRICULTURE, DEPARTMENT OF": "Department of Agriculture",
    "COMMERCE, DEPARTMENT OF": "Department of Commerce",
    "DEPT OF DEFENSE": "Department of Defense",
    "ENERGY, DEPARTMENT OF": "Department of Energy",
    "GENERAL SERVICES ADMINISTRATION": "General Services Administration",
    "HEALTH AND HUMAN SERVICES, DEPARTMENT OF": "Department of Health and Human Services",
    "HOMELAND SECURITY, DEPARTMENT OF": "Department of Homeland Security",
    "INTERIOR, DEPARTMENT OF THE": "Department of the Interior",
    "JUSTICE, DEPARTMENT OF": "Department of Justice",
    "LABOR, DEPARTMENT OF": "Department of Labor",
    "NATIONAL AERONAUTICS AND SPACE ADMINISTRATION": "National Aeronautics and Space Administration",
    "SOCIAL SECURITY ADMINISTRATION": "Social Security Administration",
    "STATE, DEPARTMENT OF": "Department of State",
    "TRANSPORTATION, DEPARTMENT OF": "Department of Transportation",
    "TREASURY, DEPARTMENT OF THE": "Department of the Treasury",
    "VETERANS AFFAIRS, DEPARTMENT OF": "Department of Veterans Affairs",
}

# Product Service Code families. NAICS does not separate building software from buying a licence;
# PSC does, and that decides whether Cadocary can compete on labour at all.
PSC_FAMILIES = [
    ("7A", "buy: software licences (COTS)"),
    ("7B", "buy: IT hardware"), ("7C", "buy: IT hardware"), ("7D", "buy: IT equipment"),
    ("7E", "buy: IT equipment"), ("7F", "buy: IT equipment"), ("7G", "buy: network hardware"),
    ("7H", "buy: IT equipment"), ("7J", "buy: IT equipment"), ("7K", "buy: IT equipment"),
    ("D", "build: IT services or application development"),
]


def psc_family(psc):
    if not psc:
        return "unknown (no PSC on the notice)"
    code = psc.upper()
    for prefix, label in PSC_FAMILIES:
        if code.startswith(prefix):
            return label
    return f"other: PSC {code}"


def fiscal_year(date_str):
    """Federal fiscal year: October starts the next one."""
    d = str(date_str or "")[:10]
    if len(d) < 7 or not d[:4].isdigit():
        return None
    return int(d[:4]) + (1 if d[5:7] >= "10" else 0)


def get_json(url, attempts=4):
    last = None
    for attempt in range(attempts):
        req = urllib.request.Request(url, headers=SAM_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500 and exc.code != 429:
                return None
            last = exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
        time.sleep(1.5 * (attempt + 1))
    print(f"  giving up on {url}: {last}", file=sys.stderr)
    return None


def post_json(url, body, attempts=4):
    data = json.dumps(body).encode("utf-8")
    last = None
    for attempt in range(attempts):
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500 and exc.code != 429:
                print(f"  {url}: HTTP {exc.code} {exc.read()[:200].decode('utf-8', 'ignore')}", file=sys.stderr)
                return None
            last = exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
        time.sleep(1.5 * (attempt + 1))
    print(f"  giving up on {url}: {last}", file=sys.stderr)
    return None


def award_search(agency, psc=None, naics=None, keywords=None, start="2015-01-01",
                 end="2030-12-31", limit=100, sort="Start Date"):
    """One page of awards. psc/naics are plain arrays — a dict is rejected by the API."""
    filters = {
        "award_type_codes": ["A", "B", "C", "D"],
        "time_period": [{"start_date": start, "end_date": end}],
    }
    if agency:
        filters["agencies"] = [{"type": "awarding", "tier": "toptier", "name": agency}]
    if psc:
        filters["psc_codes"] = list(psc)
    if naics:
        filters["naics_codes"] = list(naics)
    if keywords:
        filters["keywords"] = list(keywords)
    payload = post_json(AWARDS, {
        "filters": filters, "fields": AWARD_FIELDS,
        "sort": sort, "order": "desc", "limit": limit, "page": 1,
    })
    return (payload or {}).get("results") or []


# --- subcommands -----------------------------------------------------------------

def cmd_notice(args):
    detail = get_json(SAM_NOTICE.format(notice_id=args.notice_id))
    if not detail:
        sys.exit(f"no notice {args.notice_id}")
    data = detail.get("data2") or {}
    # The scope lives in description[].body. An empty `content` field is not an empty description.
    text = []
    for entry in detail.get("description") or []:
        body = (entry or {}).get("body") or ""
        plain = re.sub(r"<[^>]+>", " ", body)
        plain = re.sub(r"&nbsp;", " ", plain)
        plain = re.sub(r"[ \t]+", " ", plain)
        if plain.strip():
            text.append(plain.strip())

    attachments = []
    resources = get_json(SAM_RESOURCES.format(notice_id=args.notice_id)) or {}
    for group in (resources.get("_embedded") or {}).get("opportunityAttachmentList") or []:
        for att in group.get("attachments") or []:
            if att.get("fileExists") != "1":
                continue
            attachments.append({
                "name": att.get("name"),
                "mime_type": att.get("mimeType"),
                "size": att.get("size"),
                "resource_id": att.get("resourceId"),
                "download": SAM_FILE.format(resource_id=att.get("resourceId")),
            })

    psc = data.get("classificationCode")
    pop = data.get("placeOfPerformance") or {}
    out = {
        "notice_id": args.notice_id,
        "solicitation_number": data.get("solicitationNumber"),
        "title": data.get("title"),
        "notice_type": data.get("type"),
        "psc": psc,
        "psc_family": psc_family(psc),
        "naics": ((data.get("naics") or [{}])[0].get("code") or [None])[0],
        "place_of_performance": {
            "city": (pop.get("city") or {}).get("name"),
            "state": (pop.get("state") or {}).get("code"),
        },
        "response_date": ((data.get("solicitation") or {}).get("deadlines") or {}).get("response"),
        "response_tz": ((data.get("solicitation") or {}).get("deadlines") or {}).get("responseTz"),
        "posted_date": detail.get("postedDate"),
        "archived": detail.get("archived"),
        "cancelled": detail.get("cancelled"),
        "office_prefix": (data.get("solicitationNumber") or "")[:6] or None,
        "contacts": [
            {"type": c.get("type"), "name": c.get("fullName"), "email": c.get("email")}
            for c in data.get("pointOfContact") or []
        ],
        "attachments": attachments,
        "description_text": "\n\n".join(text),
    }
    if args.json:
        print(json.dumps(out, indent=2))
        return
    print(f"{out['solicitation_number']}  {out['title']}")
    print(f"  PSC {out['psc']} — {out['psc_family']}")
    print(f"  NAICS {out['naics']} | PoP {out['place_of_performance']['city']}, "
          f"{out['place_of_performance']['state']}")
    print(f"  type {out['notice_type']} | posted {str(out['posted_date'])[:10]} | "
          f"response {out['response_date']} ({out['response_tz']})")
    print(f"  archived {out['archived']} | cancelled {out['cancelled']} | "
          f"office prefix {out['office_prefix']}")
    print(f"  attachments: {len(attachments)}")
    for att in attachments:
        print(f"    {att['name']}  [{att['mime_type']}] {att['size']} bytes")
    if out["description_text"]:
        print(f"\n  description ({len(out['description_text'])} chars):\n")
        print("  " + out["description_text"][:args.chars].replace("\n", "\n  "))
    else:
        print("\n  no description text — the scope is in the attachments")


def cmd_related(args):
    payload = get_json(SAM_RELATED.format(notice_id=args.notice_id))
    if payload is None:
        sys.exit(f"no related notices for {args.notice_id}")
    awardees = []
    for rel in payload.get("relatedOpportunities") or []:
        if not isinstance(rel, dict):
            continue
        # The award sits under data2 on a related award notice; older shapes put it at the top.
        inner = rel.get("data2") or {}
        award = inner.get("award") or rel.get("award") or {}
        who = (award.get("awardee") or {}) if isinstance(award, dict) else {}
        if who.get("name"):
            awardees.append({
                "name": who.get("name"),
                "uei": who.get("ueiSAM"),
                "contract_number": award.get("number"),
                "amount": award.get("amount"),
                "award_date": award.get("date"),
                "award_title": inner.get("title"),
            })
    out = {
        "notice_id": args.notice_id,
        "total_award_amount": payload.get("totalAwardAmt") or 0,
        "recipient_count": payload.get("recipientCount") or 0,
        "related_notice_count": payload.get("count") or 0,
        "awardees": awardees,
    }
    if args.json:
        print(json.dumps(out, indent=2))
        return
    if not out["total_award_amount"] and not awardees:
        print(f"{args.notice_id}: no award recorded against this solicitation")
        return
    print(f"{args.notice_id}: ${out['total_award_amount']:,.0f} "
          f"to {out['recipient_count']} recipient(s)")
    for who in awardees:
        print(f"  {who['name']}  contract {who['contract_number']}  "
              f"${float(who['amount'] or 0):,.0f}  {who['award_date']}")
        if who["award_title"]:
            print(f"    {who['award_title']}")


def cmd_history(args):
    """Line 1 for a federal buyer: what this office actually obligates, by fiscal year."""
    agency = AGENCY_NAMES.get(args.agency.upper(), args.agency)
    rows = award_search(agency, keywords=[args.office], limit=args.limit)
    purpose = [p.strip().upper() for p in (args.purpose or "").split(",") if p.strip()]
    matcher = re.compile("|".join(re.escape(p) for p in purpose), re.I) if purpose else None

    by_year = collections.defaultdict(list)
    for row in rows:
        desc = str(row.get("Description") or "")
        if matcher and not matcher.search(desc):
            continue
        year = fiscal_year(row.get("Start Date"))
        if year:
            by_year[year].append(row)

    out = {
        "agency": agency, "office": args.office, "purpose": purpose,
        "awards_scanned": len(rows),
        "by_fiscal_year": [
            {
                "fiscal_year": year,
                "total": sum(r.get("Award Amount") or 0 for r in by_year[year]),
                "award_count": len(by_year[year]),
                "awards": [
                    {"award_id": r.get("Award ID"), "recipient": r.get("Recipient Name"),
                     "amount": r.get("Award Amount"), "start": str(r.get("Start Date"))[:10],
                     "description": str(r.get("Description") or "")[:120]}
                    for r in sorted(by_year[year], key=lambda r: -(r.get("Award Amount") or 0))
                ],
            }
            for year in sorted(by_year, reverse=True)
        ],
    }
    if args.json:
        print(json.dumps(out, indent=2))
        return
    print(f"{agency} / office {args.office} — {len(rows)} awards scanned"
          f"{', filtered to ' + ','.join(purpose) if purpose else ''}")
    if not out["by_fiscal_year"]:
        print("  nothing matched — line 1 is dead for this office/purpose")
        return
    for year in out["by_fiscal_year"]:
        print(f"  FY{year['fiscal_year']}: ${year['total']:>12,.0f}  ({year['award_count']} awards)")
        for award in year["awards"]:
            print(f"      ${award['amount']:>10,.0f}  {str(award['recipient'])[:28]:30s} "
                  f"{award['description'][:58]}")


def cmd_search(args):
    """Structural search. --cutoff keeps the solicitation's own award out of its own estimate."""
    agency = AGENCY_NAMES.get(args.agency.upper(), args.agency)
    rows = award_search(agency, psc=args.psc.split(",") if args.psc else None,
                        naics=args.naics.split(",") if args.naics else None,
                        limit=args.limit)
    if args.office:
        scoped = [r for r in rows if str(r.get("Award ID") or "").upper().startswith(args.office.upper())]
        pool_label = f"same office {args.office}"
        if not scoped:
            scoped, pool_label = rows, f"agency+PSC (no award found at office {args.office})"
    else:
        scoped, pool_label = rows, "agency+PSC"

    dropped = 0
    if args.cutoff:
        before = len(scoped)
        scoped = [r for r in scoped if str(r.get("Start Date") or "")[:10] < args.cutoff[:10]]
        dropped = before - len(scoped)

    amounts = sorted(r.get("Award Amount") or 0 for r in scoped)
    band = None
    if amounts:
        band = {
            "n": len(amounts), "min": amounts[0],
            "p25": amounts[len(amounts) // 4], "median": amounts[len(amounts) // 2],
            "p75": amounts[3 * len(amounts) // 4], "max": amounts[-1],
        }
    out = {
        "agency": agency, "psc": args.psc, "naics": args.naics, "office": args.office,
        "cutoff": args.cutoff, "pool": pool_label,
        "excluded_on_or_after_cutoff": dropped,
        "band": band,
        "awards": [
            {"award_id": r.get("Award ID"), "recipient": r.get("Recipient Name"),
             "amount": r.get("Award Amount"), "start": str(r.get("Start Date"))[:10],
             "end": str(r.get("End Date"))[:10], "description": str(r.get("Description") or "")[:160]}
            for r in sorted(scoped, key=lambda r: -(r.get("Award Amount") or 0))[:args.show]
        ],
    }
    if args.json:
        print(json.dumps(out, indent=2))
        return
    print(f"{agency} | PSC {args.psc or '-'} | pool: {pool_label}")
    if args.cutoff:
        print(f"  cutoff {args.cutoff}: {dropped} award(s) on or after it excluded")
    if not band:
        print("  no awards found — this line is dead, say so rather than guessing")
        return
    print(f"  n={band['n']}  min ${band['min']:,.0f}  p25 ${band['p25']:,.0f}  "
          f"median ${band['median']:,.0f}  p75 ${band['p75']:,.0f}  max ${band['max']:,.0f}")
    print("  NOTE: a median is not an estimate of this contract. Same office + same PSC can be")
    print("        unrelated work. Confirm scope before using any of these as a comparable.")
    for award in out["awards"]:
        print(f"    ${award['amount']:>12,.0f}  {str(award['recipient'])[:28]:30s} "
              f"{award['start']}→{award['end']}  {award['award_id']}")
        print(f"        {award['description'][:100]}")


def cmd_chain(args):
    """Walk the predecessor references award descriptions carry, for a price history."""
    agency = AGENCY_NAMES.get(args.agency.upper(), args.agency)
    rows = award_search(agency, psc=args.psc.split(",") if args.psc else None, limit=args.limit)
    if args.office:
        rows = [r for r in rows if str(r.get("Award ID") or "").upper().startswith(args.office.upper())] or rows

    by_id = {str(r.get("Award ID")): r for r in rows}
    chains, rejected = [], []
    for row in rows:
        match = PREDECESSOR.search(str(row.get("Description") or ""))
        if not match:
            continue
        prior_id = match.group(1).upper()
        if not PIID.match(prior_id):
            # The format guard: "ACCESSDATA" is a product name, not a contract number.
            rejected.append({"award_id": row.get("Award ID"), "rejected_text": prior_id})
            continue
        prior = by_id.get(prior_id)
        if prior is None:
            found = award_search(agency, keywords=[prior_id], limit=5)
            prior = next((r for r in found if str(r.get("Award ID")) == prior_id), None)
        current_amount = row.get("Award Amount") or 0
        prior_amount = (prior or {}).get("Award Amount") or 0
        chains.append({
            "award_id": row.get("Award ID"),
            "recipient": row.get("Recipient Name"),
            "amount": current_amount,
            "start": str(row.get("Start Date"))[:10],
            "names_prior": prior_id,
            "prior_resolved": prior is not None,
            "prior_amount": prior_amount or None,
            "prior_start": str((prior or {}).get("Start Date"))[:10] if prior else None,
            "change_pct": round((current_amount - prior_amount) / prior_amount * 100, 1)
            if prior_amount else None,
            "description": str(row.get("Description") or "")[:160],
        })

    out = {
        "agency": agency, "psc": args.psc, "office": args.office,
        "awards_scanned": len(rows),
        "predecessor_references": len(chains),
        "rejected_by_format_guard": rejected,
        "chains": sorted(chains, key=lambda c: -(c["amount"] or 0)),
    }
    if args.json:
        print(json.dumps(out, indent=2))
        return
    print(f"{agency} | PSC {args.psc or '-'} | {len(rows)} awards scanned, "
          f"{len(chains)} name a predecessor")
    for chain in out["chains"]:
        print(f"  {chain['award_id']}  ${chain['amount']:>12,.0f}  ({chain['start']})  "
              f"{str(chain['recipient'])[:26]}")
        if chain["prior_resolved"]:
            print(f"    prior {chain['names_prior']}  ${chain['prior_amount']:>12,.0f}  "
                  f"({chain['prior_start']})   change {chain['change_pct']:+.1f}%")
        else:
            print(f"    prior {chain['names_prior']}  (named but not resolvable in this pool)")
    for bad in rejected:
        print(f"  format guard rejected '{bad['rejected_text']}' on {bad['award_id']} "
              f"— not a contract number")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("notice", help="the solicitation's own facts and description text")
    p.add_argument("notice_id")
    p.add_argument("--chars", type=int, default=4000, help="description characters to print")
    p.set_defaults(func=cmd_notice)

    p = sub.add_parser("related", help="what SAM recorded as the award against a solicitation")
    p.add_argument("notice_id")
    p.set_defaults(func=cmd_related)

    p = sub.add_parser("history", help="an office's obligations by fiscal year (line 1)")
    p.add_argument("--agency", required=True)
    p.add_argument("--office", required=True, help="contracting office prefix, e.g. W50S9E")
    p.add_argument("--purpose", default="", help="comma-separated description keywords to keep")
    p.add_argument("--limit", type=int, default=100)
    p.set_defaults(func=cmd_history)

    p = sub.add_parser("search", help="structural award search with a response-date cutoff")
    p.add_argument("--agency", required=True)
    p.add_argument("--psc", default="", help="comma-separated PSC codes")
    p.add_argument("--naics", default="", help="comma-separated NAICS codes")
    p.add_argument("--office", default="", help="narrow to this contracting office prefix")
    p.add_argument("--cutoff", default="", help="exclude awards starting on/after this date")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--show", type=int, default=15)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("chain", help="walk predecessor contract references for a price history")
    p.add_argument("--agency", required=True)
    p.add_argument("--psc", default="")
    p.add_argument("--office", default="")
    p.add_argument("--limit", type=int, default=100)
    p.set_defaults(func=cmd_chain)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
