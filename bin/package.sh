#!/usr/bin/env bash
# package.sh — build a distributable zip of this repo for another machine.
#
# Usage:  bin/package.sh [--share] [--check] [--out DIR]
#   default   TRANSFER build (to your own other machine): everything needed to operate, INCLUDING the
#             company assets in company/ (signature PNGs, W-9, resumes) and filed .eml emails.
#   --share   SHARE build (for a partner/bidwriter): additionally strips the company-sensitive assets
#             (W-9 and any W-9 copies, signature images, signed forms/proposals, unscrubbed raw resumes,
#             the principal's personal job-application material, executed contracts, captured mail pages)
#             and raw .eml files.
#   --check   list what would be included/excluded and the projected size; write nothing.
#   --out DIR where to write (default dist/, gitignored).
#
# ALWAYS excluded, both modes (per-machine secrets/state and noise):
#   inbox/inbox.json inbox/portals.json inbox/state.json inbox/queue.jsonl inbox/logs/ inbox/.poll.lock
#   inbox/secrets/  **/storage_state.json  **/browser-profiles/  *credentials*.json  *token*.json
#   portal-captures/ WEBS/  (portal page captures may carry account names / view-state)
#   (inbox/fga-seen.json — the sourcing seen-state — IS carried, so the other machine does not re-report everything as new)
#   .git/  __pycache__/  .pytest_cache/  *.pyc  .DS_Store  *.tmp  dist/
# The zip root is bid-writing/ and contains PACKAGE-MANIFEST.txt (build info, file list, sha256 of
# every file) so the receiving machine can verify integrity and know which mode it is.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MODE="transfer"; CHECK=0; OUT="$ROOT/dist"
while [[ $# -gt 0 ]]; do case "$1" in
  --share) MODE="share";; --check) CHECK=1;; --out) OUT="$2"; shift;;
  *) echo "unknown arg $1" >&2; exit 2;; esac; shift; done

STAMP="$(date +%Y%m%d-%H%M)"
NAME="bid-writing-${MODE}-${STAMP}.zip"

# ---- exclusion lists ------------------------------------------------------------------------
ALWAYS_EXCLUDE=(
  ".git/*" "*/__pycache__/*" "__pycache__/*" "*.pyc" "*/.pytest_cache/*" ".pytest_cache/*" "*.DS_Store" "*.tmp"
  "dist/*" "inbox/inbox.json" "inbox/portals.json" "inbox/state.json" "inbox/queue.jsonl" "inbox/logs/*" "inbox/.poll.lock"
  "inbox/secrets/*" "*/storage_state.json" "*/browser-profiles/*" "*credentials*.json" "*token*.json"
  "portal-captures/*" "WEBS/*"
  "secrets/*"
  "inbox/harness.json"
)
SHARE_EXCLUDE=(
  "company/fw9.pdf" "company/*signature*.png" "company/raw-resumes/*"
  "*.eml"
  # copies of the W-9 and any signed form/proposal elsewhere in the tree (they carry the signature image + EIN)
  "*W-9*" "*w-9*" "*W9*" "*w9*" "*-signed.pdf" "*SIGNED*.pdf" "signed.pdf"
  # the principal's personal job-search material (transcripts, references, cover letters, employer-targeted resumes)
  "application-materials/"
  # executed agreements (counterparty PII) and captured mail pages
  "company/contracts/executed/*" "email-summaries/*"
)
EXCL=("${ALWAYS_EXCLUDE[@]}"); [[ "$MODE" == "share" ]] && EXCL+=("${SHARE_EXCLUDE[@]}")

BASE="$(basename "$ROOT")"

# ---- stage a filtered copy (one code path for --check and build) ---------------------------
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
STAGE="$TMP/$BASE"; mkdir -p "$STAGE"
RS=(); for e in "${EXCL[@]}"; do RS+=("--exclude=$e"); done
rsync -a "${RS[@]}" --exclude="/dist" --exclude="/.git" --exclude="/WEBS" --exclude="/portal-captures" "$ROOT/" "$STAGE/"

sensitive_scan() {   # prints any staged path that must never ship; empty output = clean
  ( cd "$STAGE" && find . -type f | sed 's|^\./||' \
    | grep -E "^secrets/|^inbox/secrets/|^inbox/inbox\.json$|^inbox/portals\.json$|^inbox/state\.json$|^inbox/queue\.jsonl$|storage_state\.json$|browser-profiles/|credentials.*\.json$|token.*\.json$|^\.git/|__pycache__|\.DS_Store$|^inbox/logs/" || true )
  if [[ "$MODE" == "share" ]]; then
    ( cd "$STAGE" && find . -type f | sed 's|^\./||' | grep -iE "^company/fw9\.pdf$|signature.*\.png$|\.eml$|w-?9[^/]*\.pdf$|signed[^/]*\.pdf$|application-materials/|^company/contracts/executed/|^email-summaries/" || true )
  fi
}

# ---- check mode -----------------------------------------------------------------------------
if [[ $CHECK -eq 1 ]]; then
  echo "mode: $MODE   ->  $OUT/$NAME"
  echo "== excluded patterns =="; printf '   %s\n' "${EXCL[@]}"
  echo "== included, by top-level dir =="
  ( cd "$STAGE" && find . -type f | sed 's|^\./||' | awk -F/ '{d=(NF>1?$1:"(root)"); n[d]++} END{for(d in n) printf "   %-28s %5d files\n", d, n[d]}' | sort )
  ( cd "$STAGE" && for d in */; do printf "   %-28s %s\n" "$d" "$(du -sh "$d" | cut -f1)"; done )
  echo "   total: $(du -sh "$STAGE" | cut -f1) uncompressed, $(cd "$STAGE" && find . -type f | wc -l | tr -d ' ') files"
  echo "== sensitive scan (must be empty) =="; S="$(sensitive_scan)"; [[ -z "$S" ]] && echo "   clean" || { echo "$S"; exit 1; }
  exit 0
fi

# ---- build -----------------------------------------------------------------------------------
S="$(sensitive_scan)"; if [[ -n "$S" ]]; then echo "REFUSING to build — sensitive files staged:"; echo "$S"; exit 1; fi
mkdir -p "$OUT"

# manifest with sha256 of every file
{
  echo "bid-writing package manifest"
  echo "built:      $(date -Iseconds) on $(hostname -s 2>/dev/null || hostname)"
  echo "mode:       $MODE  ($( [[ $MODE == share ]] && echo 'company-sensitive assets and .eml STRIPPED' || echo 'full transfer incl. company assets and .eml' ))"
  echo "excluded:   ${EXCL[*]}"
  echo "unpack:     unzip $NAME && cd $BASE && bin/setup.sh --all   (then see README.md 'Moving to another machine')"
  echo "note:       inbox/inbox.json, inbox/portals.json, OAuth tokens and browser profiles are per-machine and NOT included."
  echo
  echo "files ($(cd "$STAGE" && find . -type f | wc -l | tr -d ' ')) — sha256:"
  ( cd "$STAGE" && find . -type f ! -name PACKAGE-MANIFEST.txt -print0 | sort -z | xargs -0 shasum -a 256 | sed 's|  \./|  |' )
} > "$STAGE/PACKAGE-MANIFEST.txt"

( cd "$TMP" && zip -r -q -X "$OUT/$NAME" "$BASE" )
SIZE=$(du -h "$OUT/$NAME" | cut -f1)
echo "built $OUT/$NAME ($SIZE, mode=$MODE, $(unzip -l "$OUT/$NAME" | tail -1 | awk '{print $2}') files)"
echo "sha256: $(shasum -a 256 "$OUT/$NAME" | cut -d' ' -f1)"
