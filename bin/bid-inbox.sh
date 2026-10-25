#!/usr/bin/env bash
# bid-inbox.sh — cron/launchd entry point: poll the bid mailbox and file new solicitations.
#
# Deterministic only: fetches mail, files each solicitation into opportunities/<ID>/ (raw .eml,
# email.md, attachments, links, due-date guess, opportunity.json, intake-brief.md) and appends
# to inbox/queue.jsonl. It does NOT run the AI intake step — see the "handoff" section below.
#
# Usage:  bin/bid-inbox.sh [--dry-run] [--since-days N]
#
# Password: resolved by bidkit.inbox from $BID_INBOX_PASSWORD or the macOS keychain item
#   security add-generic-password -s bid-inbox -a <mailbox-user> -w      (one-time; prompts)
# Cron runs with a minimal environment, so this script sources secrets/env if it exists
# (in-tree secrets/ is the portable location; ~/.config/bidkit/env is the legacy fallback)
# (put `export BID_INBOX_PASSWORD=...` there, chmod 600) — or rely on the keychain.
#
# Schedule (crontab -e), every 30 minutes, 7am-7pm, weekdays:
#   */30 7-19 * * 1-5  /Users/<you>/bid-writing/bin/bid-inbox.sh >> /Users/<you>/bid-writing/inbox/logs/cron.log 2>&1
# On macOS, launchd is more reliable than cron for a user session (survives sleep, no TCC prompts
# for the keychain): see inbox/launchd/com.example.bid-inbox.plist.example.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
[[ -f "$ROOT/secrets/env" ]] && . "$ROOT/secrets/env" || { [[ -f "$HOME/.config/bidkit/env" ]] && . "$HOME/.config/bidkit/env"; }

CFG="$ROOT/inbox/inbox.json"
LOGDIR="$ROOT/inbox/logs"; mkdir -p "$LOGDIR"
LOG="$LOGDIR/$(date +%Y-%m).log"
if [[ ! -f "$CFG" ]]; then
  echo "$(date -Iseconds) ERROR no $CFG — copy inbox/inbox.example.json and edit" | tee -a "$LOG" >&2; exit 2
fi

# single-instance lock so overlapping cron runs don't double-file
LOCK="$ROOT/inbox/.poll.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  if [[ -n "$(find "$LOCK" -maxdepth 0 -mmin +30 2>/dev/null)" ]]; then rmdir "$LOCK"; mkdir "$LOCK" || exit 0; else exit 0; fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

{
  echo "== $(date -Iseconds) poll start"
  cd "$ROOT/bidkit" && python3 -m bidkit.inbox poll --cfg "$CFG" "$@"
  rc=$?
  echo "== $(date -Iseconds) poll end rc=$rc"
} >> "$LOG" 2>&1

# ---- optional portal autofetch (opt-in) -----------------------------------------------------
# For each opportunity filed THIS run, open its portal links in the logged-in browser profile and
# download the documents into rfp/. Requires playwright + a bootstrapped profile (see
# inbox/portals.example.json). Enabled by portal_autofetch.enabled in inbox.json or PORTAL_AUTOFETCH=1.
NEWCOUNT=$(tail -n 200 "$LOG" | awk '/poll start/{n=0} /^(NEW|FOLLOWUP)/{n++} END{print n+0}')
AUTOFETCH="${PORTAL_AUTOFETCH:-$(python3 -c 'import json,sys;c=json.load(open(sys.argv[1]));print(1 if (c.get("portal_autofetch") or {}).get("enabled") else 0)' "$CFG" 2>/dev/null || echo 0)}"
if [[ "$NEWCOUNT" -gt 0 && "$AUTOFETCH" == "1" ]]; then
  {
    echo "== $(date -Iseconds) portal autofetch for $NEWCOUNT filed item(s)"
    tail -n "$NEWCOUNT" "$ROOT/inbox/queue.jsonl" | python3 -c '
import json,sys
for l in sys.stdin:
    try: r=json.loads(l)
    except Exception: continue
    if r.get("action")=="new" and r.get("opportunity"): print(r["opportunity"])' | while IFS= read -r opp; do
      ( cd "$ROOT/bidkit" && python3 -m bidkit.portal fetch "$ROOT/$opp" --portals "$ROOT/inbox/portals.json" ) || echo "   portal fetch failed for $opp (see rfp/portal-fetch.md)"
    done
  } >> "$LOG" 2>&1
fi

# ---- facts sheet + research plan + calendar (deterministic; always on) -------------------------
# For every opportunity touched THIS run (new or follow-up): extract the facts sheet from whatever is
# in initial-email/ + rfp/ (re-run later once the RFP is fetched — it refreshes its own detections),
# write the research plan, and (re)generate calendar.ics. Then merge the all-opportunities calendar.
if [[ "$NEWCOUNT" -gt 0 ]]; then
  {
    echo "== $(date -Iseconds) brief + calendar for $NEWCOUNT filed item(s)"
    tail -n "$NEWCOUNT" "$ROOT/inbox/queue.jsonl" | python3 -c '
import json,sys
seen=set()
for l in sys.stdin:
    try: r=json.loads(l)
    except Exception: continue
    o=r.get("opportunity")
    if r.get("action") in ("new","followup") and o and o not in seen:
        seen.add(o); print(o)' | while IFS= read -r opp; do
      ( cd "$ROOT/bidkit" && python3 -m bidkit.brief "$ROOT/$opp" && python3 -m bidkit.calendar ics "$ROOT/$opp" ) \
        || echo "   brief/calendar failed for $opp"
    done
    ( cd "$ROOT/bidkit" && python3 -m bidkit.calendar all "$ROOT/opportunities" ) || true
  } >> "$LOG" 2>&1
fi

# ---- handoff hook ---------------------------------------------------------------------------
# If anything NEW/FOLLOWUP was filed this run, call the hook (if present). The default hook only
# writes a desktop notification; edit inbox/hooks/on-new-opportunity.sh to add e.g. a headless
# agent invocation once one is available on this machine.
if [[ "$NEWCOUNT" -gt 0 && -x "$ROOT/inbox/hooks/on-new-opportunity.sh" ]]; then
  "$ROOT/inbox/hooks/on-new-opportunity.sh" "$NEWCOUNT" >> "$LOG" 2>&1 || true
fi
exit ${rc:-0}
