#!/usr/bin/env bash
# bid-source.sh — cron/launchd entry point for SOURCING: search the FGA portal for open opportunities
# matching company/sourcing.json (NAICS / PSC codes widened to the last digit), write the report with
# what is NEW since the last run, and notify when there is something new.
#
# Deterministic only: it does not decide what to pursue. Read the report, then file the keepers:
#   cd bidkit && python3 -m bidkit.fga --portals ../inbox/portals.json file <opportunity-id> --brief
#
# Usage:  bin/bid-source.sh [--since-days N] [--all]
#
# Auth: bidkit.fga keeps FGA tokens in secrets/fga-tokens.json (0600) and refreshes them itself.
# Bootstrap once per machine, either from a headed browser login
#   cd bidkit && python3 -m bidkit.portal login federalgovadvisors.com --portals ../inbox/portals.json
#            && python3 -m bidkit.fga --portals ../inbox/portals.json login --from-browser
# or with stored credentials (portals.json username + password_env / keychain):  python3 -m bidkit.fga login --auto
#
# Schedule (crontab -e), weekdays at 7:15:
#   15 7 * * 1-5  /Users/<you>/bid-writing/bin/bid-source.sh >> /Users/<you>/bid-writing/inbox/logs/source-cron.log 2>&1
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
[[ -f "$ROOT/secrets/env" ]] && . "$ROOT/secrets/env" || { [[ -f "$HOME/.config/bidkit/env" ]] && . "$HOME/.config/bidkit/env"; }
CRITERIA="${BID_SOURCING_CRITERIA:-$ROOT/company/sourcing.json}"
PORTALS="$ROOT/inbox/portals.json"
OUT="$ROOT/opportunities/sourcing/fga"
STATE="$ROOT/inbox/fga-seen.json"
LOGDIR="$ROOT/inbox/logs"; mkdir -p "$LOGDIR"
LOG="$LOGDIR/source-$(date +%Y-%m).log"
if [[ ! -f "$CRITERIA" ]]; then echo "$(date -Iseconds) ERROR no criteria file $CRITERIA" | tee -a "$LOG" >&2; exit 2; fi
LOCK="$ROOT/inbox/.source.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  if [[ -n "$(find "$LOCK" -maxdepth 0 -mmin +30 2>/dev/null)" ]]; then rmdir "$LOCK"; mkdir "$LOCK" || exit 0; else exit 0; fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT
{
  echo "== $(date -Iseconds) sourcing start"
  cd "$ROOT/bidkit" && python3 -m bidkit.fga --portals "$PORTALS" search --criteria "$CRITERIA" --out "$OUT" --state "$STATE" "$@"
  rc=$?
  echo "== $(date -Iseconds) sourcing end rc=$rc"
  # Triage the fresh matches into inbox/sourcing-queue.{csv,md}: score each on value + eligibility,
  # auto-reject the obvious no-matches (too-large / out-of-scope / closed) so only worthwhile RFPs
  # surface. Non-fatal — a triage failure must not fail the sourcing run.
  if [[ $rc -eq 0 ]]; then
    echo "== $(date -Iseconds) triage start"
    python3 -m bidkit.triage --rows "$OUT/latest.json" --criteria "$CRITERIA" --out "$ROOT/inbox" \
      && echo "== $(date -Iseconds) triage end" || echo "== $(date -Iseconds) triage FAILED (non-fatal)"
  fi
} >> "$LOG" 2>&1
# notify when something is new (desktop notification on macOS; harmless elsewhere)
NEW=$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1])).get("new_ids",[])))' "$OUT/latest.json" 2>/dev/null || echo 0)
if [[ "${NEW:-0}" -gt 0 ]]; then
  REPORT="$(ls -t "$OUT"/report-*.md 2>/dev/null | head -1)"
  echo "$(date -Iseconds) $NEW new sourcing match(es): $REPORT" >> "$LOG"
  if command -v osascript >/dev/null 2>&1; then
    osascript -e "display notification \"$NEW new match(es) — see $(basename "$REPORT")\" with title \"Bid sourcing (FGA)\"" 2>/dev/null || true
  fi
fi
exit ${rc:-0}
