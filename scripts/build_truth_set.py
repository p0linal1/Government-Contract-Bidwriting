#!/usr/bin/env python3
"""Build a ground-truth set for testing the research skill, from already-awarded solicitations.

The research skill has to answer "what is this contract worth" and "who held it before" from a
solicitation alone. Those answers are already published for any solicitation that has since been
awarded, so the test set costs nothing to label: take the solicitation as the input, and take the
award SAM recorded against it as the answer.

Uses the same public endpoints sam.gov's own search UI calls, so no API key is needed:

  search     https://sam.gov/api/prod/sgs/v1/search/?index=opp&naics=<codes>&is_inactive=true
  detail     https://sam.gov/api/prod/opps/v2/opportunities/<notice_id>
  related    https://sam.gov/api/prod/opps/v2/opportunities/<notice_id>/relatedopportunities
  resources  https://sam.gov/api/prod/opps/v3/opportunities/<notice_id>/resources

All require `Accept: application/hal+json` or they answer 406.

Answers are written to a separate file from inputs, so a blind run is the default and revealing
the answer takes a deliberate step. The train/holdout split is a hash of the notice id, so it is
the same every run and a case never drifts between halves.

Usage:
  python3 scripts/build_truth_set.py                       # reads profile.json
  python3 scripts/build_truth_set.py --target 40 --holdout 20
  python3 scripts/build_truth_set.py --profile acme.json --out-dir data
"""

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SEARCH_URL = "https://sam.gov/api/prod/sgs/v1/search/"
DETAIL_URL = "https://sam.gov/api/prod/opps/v2/opportunities/{notice_id}"
RELATED_URL = "https://sam.gov/api/prod/opps/v2/opportunities/{notice_id}/relatedopportunities"
RESOURCES_URL = "https://sam.gov/api/prod/opps/v3/opportunities/{notice_id}/resources"
UI_URL = "https://sam.gov/opp/{notice_id}/view"

HEADERS = {
    "Accept": "application/hal+json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

# Only the notice types that asked for a bid. An award notice is the answer, not the question.
RFP_TYPES = "o,k"
PAGE_SIZE = 1000

# Text-bearing attachments. Anything else (images, spreadsheets) can't be read for scope yet.
READABLE = {".pdf", ".docx", ".doc", ".txt", ".rtf"}


def load_profile(path):
    path = Path(path)
    if not path.exists():
        sys.exit(f"no profile at {path} — copy profile.example.json to profile.json")
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
            if 400 <= exc.code < 500 and exc.code != 429:
                return None
            last = exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
        time.sleep(1.5 * (attempt + 1))
    print(f"  giving up on {url}: {last}", file=sys.stderr)
    return None


def search_closed(naics):
    """Every inactive solicitation carrying any of these NAICS codes."""
    found, page = [], 0
    while True:
        params = {
            "index": "opp",
            "mode": "search",
            "sort": "-modifiedDate",
            "mfe": "true",
            "page": page,
            "size": PAGE_SIZE,
            "naics": ",".join(naics),
            "notice_type": RFP_TYPES,
            "is_inactive": "true",
        }
        payload = get_json(SEARCH_URL, params)
        if not payload:
            break
        results = payload.get("_embedded", {}).get("results", [])
        found.extend(results)
        total = (payload.get("page") or {}).get("totalPages") or 1
        page += 1
        if page >= total or not results:
            break
    return found


def award_answer(notice_id):
    """What SAM recorded as the award against this solicitation, or None."""
    payload = get_json(RELATED_URL.format(notice_id=notice_id))
    if not payload:
        return None
    amount = payload.get("totalAwardAmt") or 0
    related = payload.get("relatedOpportunities") or []
    if not amount and not related:
        return None
    awardees = []
    for rel in related:
        if not isinstance(rel, dict):
            continue
        # The award sits under data2 on a related award notice; older shapes put it at the top.
        inner = rel.get("data2") or {}
        award = inner.get("award") or rel.get("award") or {}
        awardee = (award.get("awardee") or {}) if isinstance(award, dict) else {}
        name = awardee.get("name")
        if name:
            awardees.append(
                {
                    "name": name,
                    "uei": awardee.get("ueiSAM"),
                    "contract_number": award.get("number"),
                    "amount": award.get("amount"),
                    "award_date": award.get("date"),
                    "award_title": inner.get("title"),
                    "award_notice_id": inner.get("opportunityId") or rel.get("opportunityId"),
                }
            )
    return {
        "total_award_amount": amount,
        "recipient_count": payload.get("recipientCount") or 0,
        "related_notice_count": payload.get("count") or len(related),
        "awardees": awardees,
    }


def readable_attachments(notice_id):
    payload = get_json(RESOURCES_URL.format(notice_id=notice_id))
    if not payload:
        return 0, []
    names = []
    for group in payload.get("_embedded", {}).get("opportunityAttachmentList", []) or []:
        for att in group.get("attachments") or []:
            if att.get("fileExists") != "1":
                continue
            if (att.get("mimeType") or "").lower() not in READABLE:
                continue
            names.append({"name": att.get("name"), "resource_id": att.get("resourceId")})
    return len(names), names


def psc_family(psc):
    """Build (services and development) or buy (licenses and hardware), from the PSC code."""
    if not psc:
        return "unknown"
    code = psc.upper()
    if code.startswith("7A"):
        return "buy: software licenses"
    if code.startswith(("7B", "7C", "7D", "7E", "7F", "7G", "7H", "7J", "7K")):
        return "buy: IT hardware"
    if code.startswith("D"):
        return "build: IT services or development"
    return f"other: {code}"


def half(notice_id, holdout_share):
    """Deterministic split, so a case never moves between train and holdout."""
    digest = hashlib.sha256(notice_id.encode()).hexdigest()
    return "holdout" if int(digest[:8], 16) % 100 < holdout_share else "train"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", default="profile.json")
    ap.add_argument("--out-dir", default="data")
    ap.add_argument("--target", type=int, default=40, help="how many labelled cases to keep")
    ap.add_argument("--holdout", type=int, default=50, help="percent of cases reserved as holdout")
    args = ap.parse_args()

    profile = load_profile(args.profile)
    naics = profile.get("naics") or []
    if not naics:
        sys.exit("profile has no NAICS codes")

    now = datetime.now(timezone.utc)
    print(f"searching closed solicitations for NAICS {', '.join(naics)}", file=sys.stderr)
    candidates = search_closed(naics)
    print(f"  {len(candidates)} closed solicitations", file=sys.stderr)

    inputs, answers = [], []
    skipped = {"no_award": 0, "no_readable_attachment": 0, "no_detail": 0}

    for notice in candidates:
        if len(inputs) >= args.target:
            break
        notice_id = notice.get("_id")
        if not notice_id:
            continue

        answer = award_answer(notice_id)
        if not answer or not answer["total_award_amount"]:
            skipped["no_award"] += 1
            continue

        att_count, att_names = readable_attachments(notice_id)
        if not att_count:
            skipped["no_readable_attachment"] += 1
            continue

        detail = get_json(DETAIL_URL.format(notice_id=notice_id))
        data = (detail or {}).get("data2") or {}
        if not data:
            skipped["no_detail"] += 1
            continue

        psc = data.get("classificationCode")
        org = notice.get("organizationHierarchy") or []
        case = {
            "notice_id": notice_id,
            "split": half(notice_id, args.holdout),
            "solicitation_number": data.get("solicitationNumber"),
            "title": data.get("title"),
            "department": (org[0].get("name") if org else None),
            "office": (org[-1].get("name") if org else None),
            "psc": psc,
            "psc_family": psc_family(psc),
            "naics": ((data.get("naics") or [{}])[0].get("code") or [None])[0],
            "place_of_performance": ((data.get("placeOfPerformance") or {}).get("state") or {}).get("code"),
            "response_date": ((data.get("solicitation") or {}).get("deadlines") or {}).get("response"),
            "posted_date": (detail or {}).get("postedDate"),
            "attachments": att_names,
            "url": UI_URL.format(notice_id=notice_id),
        }
        inputs.append(case)
        answers.append(
            {
                "notice_id": notice_id,
                "solicitation_number": case["solicitation_number"],
                "split": case["split"],
                "total_award_amount": answer["total_award_amount"],
                "recipient_count": answer["recipient_count"],
                "awardees": answer["awardees"],
            }
        )
        print(
            f"  kept {case['solicitation_number']} "
            f"${answer['total_award_amount']:,.0f} "
            f"({case['psc_family']}, {case['split']})",
            file=sys.stderr,
        )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "built_at": now.isoformat(),
        "profile_naics": naics,
        "candidates_seen": len(candidates),
        "kept": len(inputs),
        "skipped": skipped,
        "holdout_percent": args.holdout,
    }
    (out_dir / "truth_set_inputs.json").write_text(
        json.dumps({**meta, "cases": inputs}, indent=2)
    )
    (out_dir / "truth_set_answers.json").write_text(
        json.dumps(
            {
                **meta,
                "_warning": "Answers. Do not load these into a research run — a blind run is the point.",
                "answers": answers,
            },
            indent=2,
        )
    )

    by_family, by_split = {}, {}
    for case in inputs:
        by_family[case["psc_family"]] = by_family.get(case["psc_family"], 0) + 1
        by_split[case["split"]] = by_split.get(case["split"], 0) + 1
    print(f"\nkept {len(inputs)} of {len(candidates)} candidates", file=sys.stderr)
    print(f"  skipped: {skipped}", file=sys.stderr)
    print(f"  by split: {by_split}", file=sys.stderr)
    for family, count in sorted(by_family.items(), key=lambda kv: -kv[1]):
        print(f"  {count:>3}  {family}", file=sys.stderr)
    print(
        f"wrote {out_dir/'truth_set_inputs.json'} and {out_dir/'truth_set_answers.json'}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
