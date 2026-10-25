#!/usr/bin/env python3
"""Merge the research agent's fit scores into the open-opportunity list and render the report.

The agent judges fit; this script does everything mechanical, so the output shape never depends on
how the model phrased things. It refuses to render if a score is missing, malformed, or names a
notice that isn't in the open list.

Inputs:
  data/open_opportunities.json   from filter_open.py
  data/scores.json               written by the agent:
      {"scores": {"<notice_id>": {"fit": 0-100, "verdict": "pursue|consider|skip", "reason": "..."}}}

Outputs:
  data/ranked.json   stable machine-readable result (what a dashboard should read)
  data/report.md     the human digest

Usage:
  python3 scripts/render_report.py
  python3 scripts/render_report.py --check      # validate scores.json only, write nothing
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

VERDICTS = ("pursue", "consider", "skip")


def validate(open_rows, scores):
    """Return a list of problems with `scores` against the open notices; empty means usable."""
    problems = []
    ids = {row["notice_id"] for row in open_rows}
    for notice_id in sorted(ids - scores.keys()):
        problems.append(f"missing score for {notice_id}")
    for notice_id in sorted(scores.keys() - ids):
        problems.append(f"score for unknown notice {notice_id}")
    for notice_id, score in scores.items():
        if notice_id not in ids:
            continue
        if not isinstance(score, dict):
            problems.append(f"{notice_id}: score must be an object")
            continue
        fit = score.get("fit")
        if not isinstance(fit, (int, float)) or not 0 <= fit <= 100:
            problems.append(f"{notice_id}: fit must be a number 0-100, got {fit!r}")
        if score.get("verdict") not in VERDICTS:
            problems.append(f"{notice_id}: verdict must be one of {VERDICTS}, got {score.get('verdict')!r}")
        if not str(score.get("reason") or "").strip():
            problems.append(f"{notice_id}: reason is empty")
    return problems


def deadline_label(row):
    if row.get("days_left") is None:
        return "no deadline"
    return f"{row['days_left']}d left ({(row.get('response_date') or '')[:10]})"


def render_markdown(result):
    lines = [
        f"# SAM.gov research — {result['generated_at'][:10]}",
        "",
        f"{result['count']} open notices matched the profile "
        f"({result['new_count']} new since the last run). "
        f"Pursue: {len(result['groups']['pursue'])}, "
        f"consider: {len(result['groups']['consider'])}, "
        f"skip: {len(result['groups']['skip'])}.",
        "",
    ]
    dropped = result.get("dropped") or {}
    if dropped:
        lines.append("Filtered out before scoring: " + ", ".join(f"{n} {why}" for why, n in dropped.items()) + ".")
        lines.append("")
    for verdict, heading in (("pursue", "Pursue"), ("consider", "Consider")):
        rows = result["groups"][verdict]
        lines.append(f"## {heading} ({len(rows)})")
        lines.append("")
        if not rows:
            lines.append("None this run.")
            lines.append("")
        for row in rows:
            new = " **NEW**" if row.get("is_new") else ""
            lines.append(f"### [{row['title']}]({row['url']}){new}")
            lines.append("")
            lines.append(
                f"- **Fit {row['fit']}** — {row['reason']}\n"
                f"- {row.get('response_kind')} · {row.get('notice_type')} · {deadline_label(row)}\n"
                f"- {row.get('department')} / {row.get('office')}\n"
                f"- Set-aside: {row.get('set_aside') or 'none'} · "
                f"{', '.join(row.get('matched_by') or [])} · Sol# {row.get('solicitation_number') or '—'}"
            )
            if row.get("contact_email"):
                lines.append(f"- Contact: {row.get('contact_name') or ''} <{row['contact_email']}>")
            lines.append("")
    skipped = result["groups"]["skip"]
    lines.append(f"## Skipped ({len(skipped)})")
    lines.append("")
    for row in skipped:
        lines.append(f"- [{row['title']}]({row['url']}) — {row['reason']}")
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--open-file", default="data/open_opportunities.json")
    parser.add_argument("--scores-file", default="data/scores.json")
    parser.add_argument("--out-dir", default="data")
    parser.add_argument("--check", action="store_true", help="validate scores only")
    args = parser.parse_args()

    opened = json.loads(Path(args.open_file).read_text())
    scores = json.loads(Path(args.scores_file).read_text()).get("scores") or {}
    problems = validate(opened["opportunities"], scores)
    if problems:
        print(f"{len(problems)} problem(s) in {args.scores_file}:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        sys.exit(1)
    if args.check:
        print(f"{args.scores_file} OK ({len(scores)} scores)")
        return

    groups = {verdict: [] for verdict in VERDICTS}
    for row in opened["opportunities"]:
        merged = dict(row, **{k: scores[row["notice_id"]][k] for k in ("fit", "verdict", "reason")})
        groups[merged["verdict"]].append(merged)
    for rows in groups.values():
        # Best fit first; among equals, the nearest deadline.
        rows.sort(key=lambda r: (-r["fit"], r.get("days_left") is None, r.get("days_left") or 0))

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fetched_at": opened.get("fetched_at"),
        "profile": opened.get("profile"),
        "count": opened.get("count"),
        "new_count": opened.get("new_count"),
        "dropped": opened.get("dropped"),
        "groups": groups,
    }
    out_dir = Path(args.out_dir)
    (out_dir / "ranked.json").write_text(json.dumps(result, indent=2))
    # Stamp each score with the version of the notice it judged, so scores.py can tell an amended
    # notice needs rescoring.
    for row in opened["opportunities"]:
        scores[row["notice_id"]]["modified_date"] = row.get("modified_date")
    Path(args.scores_file).write_text(json.dumps({"scores": scores}, indent=2, sort_keys=True))
    (out_dir / "report.md").write_text(render_markdown(result))
    print(
        f"pursue {len(groups['pursue'])} · consider {len(groups['consider'])} · skip {len(groups['skip'])}\n"
        f"wrote {out_dir/'ranked.json'} and {out_dir/'report.md'}"
    )


if __name__ == "__main__":
    main()
