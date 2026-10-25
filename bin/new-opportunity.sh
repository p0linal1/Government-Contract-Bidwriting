#!/usr/bin/env bash
# new-opportunity.sh — scaffold a new opportunity folder from opportunities/_template/.
#
# Usage:
#   bin/new-opportunity.sh <ID> ["Agency name"] ["Solicitation title"]
#   e.g. bin/new-opportunity.sh 27-004-COUNTY-JMS "Benton County" "Jail Management System Replacement"
#
# Creates opportunities/<ID>/ with the standard tree and an opportunity.json whose {{ID}},
# {{AGENCY}}, {{TITLE}} placeholders are filled (remaining placeholders are set to "" so the
# file is valid JSON and `python3 -m bidkit.config` passes). Drop the solicitation into rfp/
# and the invitation email into initial-email/, then open Kiro and say:
#   "run intake on opportunities/<ID>"
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ID="${1:-}"; AGENCY="${2:-}"; TITLE="${3:-}"
if [[ -z "$ID" ]]; then echo "usage: $0 <ID> [agency] [title]" >&2; exit 2; fi
if [[ ! "$ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then echo "ID must be a filesystem-safe slug" >&2; exit 2; fi
DEST="$ROOT/opportunities/$ID"
if [[ -e "$DEST" ]]; then echo "already exists: $DEST" >&2; exit 1; fi

cp -R "$ROOT/opportunities/_template" "$DEST"
python3 - "$DEST/opportunity.json" "$ID" "$AGENCY" "$TITLE" <<'PY'
import json, re, sys
path, oid, agency, title = sys.argv[1:5]
txt = open(path, encoding="utf-8").read()
fill = {"{{ID}}": oid, "{{AGENCY}}": agency, "{{TITLE}}": title,
        "{{SOURCE_TYPE}}": "manual", "{{RECEIVED}}": "", "{{FROM}}": "", "{{MESSAGE_ID}}": "", "{{DUE_DATE}}": ""}
for k, v in fill.items():
    txt = txt.replace(k, v.replace('"', '\\"'))
json.loads(txt)  # must be valid
open(path, "w", encoding="utf-8").write(txt)
PY
echo "created $DEST"
find "$DEST" -type d | sed "s|$ROOT/||" | sort
echo
echo "next: put the solicitation in opportunities/$ID/rfp/ and the email in initial-email/,"
echo "      then in Kiro: \"run intake on opportunities/$ID\""
