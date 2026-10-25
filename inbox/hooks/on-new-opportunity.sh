#!/usr/bin/env bash
# on-new-opportunity.sh — called by bin/bid-inbox.sh after a poll that filed >= 1 new/follow-up
# message. Arg 1 = count filed this run.
#
# Default behaviour (safe, no AI involved):
#   1. macOS notification with the count.
#   2. Open the newest intake brief(s) in Kiro (the IDE binary; reuses the open window) so the
#      human can read the brief and say "run intake on opportunities/<ID>".
#
# Headless agent handoff: the `kiro` binary on this machine is the IDE launcher (verified with
# `kiro --help`: open/diff/merge only) — it cannot run a prompt non-interactively. If/when a
# headless CLI is installed, add the invocation in the HANDOFF block below. Keep it opt-in: an
# unattended agent writing files from cron is a bigger blast radius than filing email.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COUNT="${1:-0}"
QUEUE="$ROOT/inbox/queue.jsonl"

# newest N filed entries -> their brief paths
BRIEFS=$(tail -n "$COUNT" "$QUEUE" 2>/dev/null | python3 -c '
import json,sys,os
root=sys.argv[1]
for l in sys.stdin:
    try: r=json.loads(l)
    except Exception: continue
    if r.get("action") in ("new","followup") and r.get("brief"):
        print(os.path.join(root, r["brief"]))' "$ROOT")

if command -v osascript >/dev/null 2>&1; then
  osascript -e "display notification \"$COUNT new bid email(s) filed — open Kiro and run intake\" with title \"bid-inbox\"" 2>/dev/null || true
fi

if command -v kiro >/dev/null 2>&1 && [[ -n "$BRIEFS" ]]; then
  # open the intake brief AND the facts sheet (written by bidkit.brief) for each filed opportunity
  echo "$BRIEFS" | while IFS= read -r b; do
    [[ -f "$b" ]] && kiro --reuse-window "$b" >/dev/null 2>&1 || true
    f="$(dirname "$b")/opportunity-facts.md"; [[ -f "$f" ]] && kiro --reuse-window "$f" >/dev/null 2>&1 || true
  done
fi

# ---- HANDOFF (opt-in; empty by default) -----------------------------------------------------
# Example shape once a headless agent CLI exists (DO NOT enable without reviewing its permissions):
#   for b in $BRIEFS; do
#     opp=$(dirname "$b")
#     <headless-agent> --cwd "$ROOT" --prompt "run intake on ${opp#$ROOT/}" --no-interactive
#   done
exit 0
