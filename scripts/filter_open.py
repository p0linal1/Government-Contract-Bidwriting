#!/usr/bin/env python3
"""Cut a fetched SAM.gov pull down to the notices a vendor can still respond to.

SAM's `is_active=true` is not the same as biddable: most active notices are Award Notices for
contracts already given out, and many others are past their response deadline but not yet
archived. This keeps the solicitation-shaped notice types whose deadline is still ahead.

Usage:
  python3 scripts/filter_open.py
  python3 scripts/filter_open.py --include-no-deadline --days 45
"""

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_sam_opportunities import CSV_COLUMNS  # noqa: E402

# Notice types you can actually act on. Award Notices, Justifications and Special Notices are
# information only — no response is being solicited.
BIDDABLE_TYPES = {
    "Solicitation",
    "Combined Synopsis/Solicitation",
    "Presolicitation",
    "Sources Sought",
    "Request for Information",
    "Intent to Bundle Requirements (DoD- Funded)",
}


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--in-file", default="data/opportunities.json")
    parser.add_argument("--out-dir", default="data")
    parser.add_argument("--days", type=int, default=None, help="only deadlines within N days")
    parser.add_argument(
        "--include-no-deadline",
        action="store_true",
        help="keep notices with no response date (often presolicitations)",
    )
    args = parser.parse_args()

    payload = json.loads(Path(args.in_file).read_text())
    now = datetime.now(timezone.utc)
    kept = []
    for row in payload["opportunities"]:
        if row.get("is_canceled"):
            continue
        if row.get("notice_type") not in BIDDABLE_TYPES:
            continue
        deadline = parse_date(row.get("response_date"))
        if deadline is None:
            if not args.include_no_deadline:
                continue
            row["days_left"] = None
        else:
            days_left = (deadline - now).days
            if days_left < 0:
                continue
            if args.days is not None and days_left > args.days:
                continue
            row["days_left"] = days_left
        kept.append(row)

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
                "opportunities": kept,
            },
            indent=2,
        )
    )

    columns = ["days_left"] + CSV_COLUMNS
    with (out_dir / "open_opportunities.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in kept:
            flat = dict(row)
            for key in ("matched_by", "naics_codes"):
                if isinstance(flat.get(key), list):
                    flat[key] = "; ".join(str(v) for v in flat[key])
            writer.writerow(flat)

    print(f"{len(kept)} of {payload['count']} notices are still open for response")
    print(f"wrote {out_dir/'open_opportunities.json'} and {out_dir/'open_opportunities.csv'}")


if __name__ == "__main__":
    main()
