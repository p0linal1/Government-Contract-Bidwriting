#!/usr/bin/env bash
# sam-research.sh — unattended entry point for SAM.gov research: runs the sam-researcher agent
# (.claude/agents/sam-researcher.md) headlessly against profile.json and leaves the ranked result in
# data/report.md and data/ranked.json.
#
# Usage:  bin/sam-research.sh              # full run: pull, filter, agent scores fit, render
#         bin/sam-research.sh --no-agent   # pull + filter only (no Claude needed); data/open_opportunities.csv
#
# Needs Claude Code (`claude`) signed in, except with --no-agent. The agent may only run the four
# scripts and write data/new_scores.json (.claude/settings.json); --permission-mode dontAsk denies
# anything else instead of waiting for a human.
#
# Optional env: SAM_RESEARCH_BUDGET_USD caps model spend per run (default 2).
#
# Schedule (crontab -e), weekdays at 7:00:
#   0 7 * * 1-5  /path/to/repo/bin/sam-research.sh >> /path/to/repo/data/logs/cron.log 2>&1
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="/usr/local/bin:/opt/homebrew/bin:$HOME/.local/bin:/usr/bin:/bin:$PATH"
cd "$ROOT"

if [[ ! -f profile.json ]]; then
  echo "no profile.json — copy profile.example.json to profile.json and set your NAICS codes" >&2; exit 2
fi
LOGDIR="$ROOT/data/logs"; mkdir -p "$LOGDIR"
LOG="$LOGDIR/sam-research-$(date +%Y-%m).log"
LOCK="$ROOT/data/.sam-research.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  if [[ -n "$(find "$LOCK" -maxdepth 0 -mmin +60 2>/dev/null)" ]]; then rmdir "$LOCK"; mkdir "$LOCK" || exit 0; else exit 0; fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

{
  echo "== $(date -Iseconds) sam-research start"
  if [[ "${1:-}" == "--no-agent" ]]; then
    python3 scripts/fetch_sam_opportunities.py && python3 scripts/filter_open.py
    rc=$?
  else
    if ! command -v claude >/dev/null 2>&1; then
      echo "claude not found on PATH; install Claude Code or use --no-agent"; exit 2
    fi
    claude -p --agent sam-researcher --permission-mode dontAsk \
      --max-budget-usd "${SAM_RESEARCH_BUDGET_USD:-2}" "Run the SAM.gov research."
    rc=$?
  fi
  echo "== $(date -Iseconds) sam-research end rc=$rc"
} 2>&1 | tee -a "$LOG"
rc=${PIPESTATUS[0]}

NEW=$(python3 -c 'import json;print(json.load(open("data/open_opportunities.json")).get("new_count",0))' 2>/dev/null || echo 0)
if [[ "${NEW:-0}" -gt 0 ]] && command -v osascript >/dev/null 2>&1; then
  osascript -e "display notification \"$NEW new open notice(s) — see data/report.md\" with title \"SAM.gov research\"" 2>/dev/null || true
fi
exit "$rc"
