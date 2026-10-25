#!/usr/bin/env python3
"""Keep the agent's fit scores across runs so it only judges what's new or changed.

  pending   prune data/scores.json to notices that are still open and unamended since scoring,
            then print the open notices that still need a score, compactly, for the agent to read
  merge     fold a file of new scores into data/scores.json

A score is stamped with the notice's modified_date when render_report.py publishes it; if SAM later
shows a different modified_date (an amendment), the score is dropped and the notice comes back as
pending.

Usage:
  python3 scripts/scores.py pending
  python3 scripts/scores.py merge data/new_scores.json
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path

OPEN_FILE = Path("data/open_opportunities.json")
SCORES_FILE = Path("data/scores.json")


def load_scores(path=SCORES_FILE):
    return json.loads(path.read_text()).get("scores", {}) if path.exists() else {}


def save_scores(scores, path=SCORES_FILE):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"scores": scores}, indent=2, sort_keys=True))


def prune(rows, scores):
    """Scores still valid for `rows`: notice still open, and not amended since it was scored."""
    by_id = {row["notice_id"]: row for row in rows}
    kept = {}
    for notice_id, score in scores.items():
        row = by_id.get(notice_id)
        if row is None:
            continue
        stamped = score.get("modified_date")
        if stamped and stamped != row.get("modified_date"):
            continue
        kept[notice_id] = score
    return kept


def plain(text):
    """SAM descriptions are HTML; the agent only needs the words."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text or "")).split())


def describe(row):
    return "\n".join(
        [
            f"## {row['notice_id']}",
            f"title: {row.get('title')}",
            f"type: {row.get('notice_type')} ({row.get('response_kind')}) · "
            + (f"{row['days_left']} days left" if row.get("days_left") is not None else "no deadline"),
            f"agency: {row.get('department')} / {row.get('sub_tier')} / {row.get('office')}",
            f"naics: {', '.join(row.get('naics_codes') or []) or '?'} · psc: {row.get('psc_code') or '?'} · "
            f"set-aside: {row.get('set_aside') or 'none'}",
            f"place: {row.get('place_of_performance') or '?'}",
            f"description: {plain(row.get('description_excerpt'))[:700]}",
            "",
        ]
    )


def cmd_pending(args):
    rows = json.loads(Path(args.open_file).read_text())["opportunities"]
    scores = prune(rows, load_scores())
    save_scores(scores)
    pending = [row for row in rows if row["notice_id"] not in scores]
    print(f"{len(rows)} open · {len(scores)} already scored · {len(pending)} need a score\n")
    for row in pending:
        print(describe(row))


def cmd_merge(args):
    incoming = json.loads(Path(args.file).read_text())
    incoming = incoming.get("scores", incoming)
    if not isinstance(incoming, dict):
        sys.exit(f"{args.file} must be an object of notice_id -> score")
    scores = load_scores()
    for notice_id, score in incoming.items():
        # A rescore replaces the old one, including its modified_date stamp.
        scores[notice_id] = {k: v for k, v in score.items() if k != "modified_date"}
    save_scores(scores)
    print(f"merged {len(incoming)} scores into {SCORES_FILE} ({len(scores)} total)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    pending = sub.add_parser("pending", help="list open notices that need a score")
    pending.add_argument("--open-file", default=str(OPEN_FILE))
    pending.set_defaults(func=cmd_pending)
    merge = sub.add_parser("merge", help="merge new scores into data/scores.json")
    merge.add_argument("file")
    merge.set_defaults(func=cmd_merge)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
