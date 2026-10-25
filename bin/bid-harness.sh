#!/usr/bin/env bash
# bid-harness.sh — daily evaluation-harness entry point: evaluate the whole portfolio through the
# gated pipeline and email the principal the X/Y/Z digest with drafts attached.
#
# This is the SUPERSET daily entry point. It runs AFTER the deterministic ingest (bin/bid-inbox.sh
# files new solicitations; bin/bid-source.sh sources FGA). It then:
#   1. runs each opportunity through the gated evaluation pipeline (bidkit.harness), under the
#      AUTONOMY MODE in inbox/harness.json (default: a = notify-only — no agent writing);
#   2. composes and sends the daily digest (bidkit.digest) via the configured mail backend.
#
# The AI "writer" is only invoked in autonomy mode b/c AND when agent_cli is configured; otherwise
# the harness degrades to notify-only and says so in the digest. There is no headless agent runner
# on this box yet, so today this runs in mode a: it reports + emails, the human runs intake/build
# in the IDE.
#
# Usage:  bin/bid-harness.sh [--dry-run]        # --dry-run composes but does NOT send
#
# Config: inbox/harness.json (copy inbox/harness.example.json). The digest recipient and the Gmail
# SEND token live in config / secrets, never in code. The Gmail send scope needs its own one-time
# consent: cd bidkit && python3 -m bidkit.mail_gmail send-auth --cfg ../inbox/inbox.json
#
# Schedule (launchd recommended on macOS): inbox/launchd/com.example.bid-harness.plist.example
# cron (weekdays 07:40, after the inbox poll and sourcing run):
#   40 7 * * 1-5  /Users/<you>/bid-writing/bin/bid-harness.sh >> /Users/<you>/bid-writing/inbox/logs/cron.log 2>&1
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
[[ -f "$ROOT/secrets/env" ]] && . "$ROOT/secrets/env" || { [[ -f "$HOME/.config/bidkit/env" ]] && . "$HOME/.config/bidkit/env"; }

CFG="$ROOT/inbox/harness.json"
LOGDIR="$ROOT/inbox/logs"; mkdir -p "$LOGDIR"
LOG="$LOGDIR/$(date +%Y-%m).log"
if [[ ! -f "$CFG" ]]; then
  echo "$(date -Iseconds) ERROR no $CFG — copy inbox/harness.example.json and edit" | tee -a "$LOG" >&2; exit 2
fi

# single-instance lock so overlapping runs don't double-send
LOCK="$ROOT/inbox/.harness.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  if [[ -n "$(find "$LOCK" -maxdepth 0 -mmin +30 2>/dev/null)" ]]; then rmdir "$LOCK"; mkdir "$LOCK" || exit 0; else exit 0; fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

{
  echo "== $(date -Iseconds) harness start"
  cd "$ROOT/bidkit" && python3 -m bidkit.digest run --cfg "$CFG" "$@"
  rc=$?
  echo "== $(date -Iseconds) harness end rc=$rc"
} >> "$LOG" 2>&1
exit ${rc:-0}
