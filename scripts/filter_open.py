#!/usr/bin/env python3
"""Cut a fetched SAM.gov pull down to the notices a vendor can still respond to.

The fetcher already asks SAM for responsive notice types with a future deadline, but this is the
last line of defence and also catches what the search can't:

  - award notices and expired notices, if the pull was made with --all-notices
  - solicitations still listed as active although an award has been posted against them
  - set-asides the business isn't eligible for (profile `set_aside_eligibility`)
  - cancelled notices

It also marks each notice `is_new` if it wasn't in any earlier run (tracked in data/seen.json),
so a daily run only asks a human to look at what changed.

Usage:
  python3 scripts/filter_open.py
  python3 scripts/filter_open.py --include-no-deadline --days 45
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_sam_opportunities import CSV_COLUMNS, write_csv  # noqa: E402

# Notice types you can act on, and what acting on them means. Award Notices, Justifications and
# Sales of Surplus are information only. RFIs are posted as Sources Sought or Special Notices.
RESPONSE_KIND = {
    "Solicitation": "bid",
    "Combined Synopsis/Solicitation": "bid",
    "Presolicitation": "pre-bid",
    "Intent to Bundle Requirements (DoD- Funded)": "pre-bid",
    "Sources Sought": "market research",
    "Special Notice": "market research",
}

# Set-aside values that restrict who may bid. Anything not listed here (blank, "NONE", or a code
# SAM adds later) is treated as open competition.
RESTRICTED_SET_ASIDES = {
    "SBA", "SBP", "8A", "8AN", "HZC", "HZS", "SDVOSBC", "SDVOSBS", "WOSB", "WOSBSS",
    "EDWOSB", "EDWOSBSS", "VSA", "VSS", "ISBEE", "IEE", "BICiv",
}


def parse_date(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # SAM occasionally sends a bare local timestamp; treat it as UTC rather than crash on compare.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def set_aside_blocked(set_aside, eligible):
    """True if the notice is restricted to a set-aside the business can't claim.

    `eligible` is None when the profile doesn't say, in which case nothing is filtered.
    """
    if eligible is None or not set_aside:
        return False
    return set_aside in RESTRICTED_SET_ASIDES and set_aside not in eligible


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--in-file", default="data/opportunities.json")
    parser.add_argument("--out-dir", default="data")
    parser.add_argument("--seen-file", default="data/seen.json", help="notice ids from earlier runs")
    parser.add_argument("--days", type=int, default=None, help="only deadlines within N days")
    parser.add_argument(
        "--include-no-deadline",
        action="store_true",
        help="keep notices with no response date (often presolicitations)",
    )
    parser.add_argument("--keep-awarded", action="store_true", help="keep notices with a recorded award")
    parser.add_argument(
        "--ignore-set-aside", action="store_true", help="keep set-asides the profile isn't eligible for"
    )
    args = parser.parse_args()

    payload = json.loads(Path(args.in_file).read_text())
    eligible = (payload.get("profile") or {}).get("set_aside_eligibility")
    if args.ignore_set_aside:
        eligible = None
    elif eligible is not None:
        eligible = set(eligible)

    now = datetime.now(timezone.utc)
    kept, dropped = [], {}

    def drop(reason):
        dropped[reason] = dropped.get(reason, 0) + 1

    for row in payload["opportunities"]:
        if row.get("is_canceled"):
            drop("cancelled")
            continue
        kind = RESPONSE_KIND.get(row.get("notice_type"))
        if kind is None:
            drop(f"not responsive ({row.get('notice_type')})")
            continue
        if row.get("award") and not args.keep_awarded:
            drop("already awarded")
            continue
        if set_aside_blocked(row.get("set_aside"), eligible):
            drop(f"set-aside not eligible ({row.get('set_aside')})")
            continue
        deadline = parse_date(row.get("response_date"))
        if deadline is None:
            if not args.include_no_deadline:
                drop("no deadline")
                continue
            row["days_left"] = None
        else:
            days_left = (deadline - now).days
            if deadline < now:
                drop("deadline passed")
                continue
            if args.days is not None and days_left > args.days:
                drop(f"deadline beyond {args.days} days")
                continue
            row["days_left"] = days_left
        row["response_kind"] = kind
        kept.append(row)

    seen_path = Path(args.seen_file)
    seen = json.loads(seen_path.read_text()) if seen_path.exists() else {}
    fetched_at = payload.get("fetched_at") or now.isoformat()
    for row in kept:
        # Keyed on the pull time so re-filtering the same pull doesn't flip new rows to old.
        first_seen = seen.setdefault(row["notice_id"], fetched_at)
        row["first_seen"] = first_seen
        row["is_new"] = first_seen == fetched_at
    seen_path.parent.mkdir(parents=True, exist_ok=True)
    seen_path.write_text(json.dumps(seen, indent=2, sort_keys=True))

    kept.sort(key=lambda r: (r.get("days_left") is None, r.get("days_left")))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "open_opportunities.json").write_text(
        json.dumps(
            {
                "fetched_at": payload.get("fetched_at"),
                "filtered_at": now.isoformat(),
                "profile": payload.get("profile"),
                "count": len(kept),
                "new_count": sum(1 for r in kept if r["is_new"]),
                "dropped": dropped,
                "opportunities": kept,
            },
            indent=2,
        )
    )
    write_csv(out_dir / "open_opportunities.csv", kept, ["days_left", "is_new", "response_kind"] + CSV_COLUMNS)

    print(f"{len(kept)} of {payload['count']} notices are open for response ({sum(r['is_new'] for r in kept)} new)")
    for reason, n in sorted(dropped.items(), key=lambda kv: -kv[1]):
        print(f"  dropped {n:4d}  {reason}")
    print(f"wrote {out_dir/'open_opportunities.json'} and {out_dir/'open_opportunities.csv'}")


if __name__ == "__main__":
    main()
