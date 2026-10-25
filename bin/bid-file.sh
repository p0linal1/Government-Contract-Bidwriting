#!/usr/bin/env bash
# bid-file.sh — file ONE sourced FGA opportunity as an intake-ready opportunity folder.
#
# The FGA-first intake path: bin/bid-source.sh writes the sourcing report; you read it and pick the
# keepers; this script turns a chosen opportunity into opportunities/<number>-<slug>/ (opportunity.json,
# rfp/portal-record.json + .md, any documents, sourcing/fga-record.md, initial-email/links.md) and runs
# bidkit.brief + calendar so it is ready for the Kiro intake step. It does NOT decide to pursue — that
# is your call after reading the report.
#
# Usage:
#   bin/bid-file.sh <fga-opportunity-id> [--no-docs]
#   e.g. bin/bid-file.sh 31b1e9f2-84be-420b-a8e0-9d868e4de60e
#     (the id is the UUID in the portal deep link in the report:
#      https://portal.federalgovadvisors.com/opportunities/view/<id>?tab=opportunities)
#
# Auth: same as bin/bid-source.sh — tokens in secrets/fga-tokens.json, self-refreshing. If the token
# has expired, re-auth once: cd bidkit && python3 -m bidkit.fga --portals ../inbox/portals.json login --auto
#
# After this runs, in Kiro say:  "run intake on opportunities/<the folder it printed>"
# FGA rarely attaches the documents itself (its links 403); initial-email/links.md carries the
# SOURCE-system URL — fetch the RFP + attachments into rfp/ from there before/at intake.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
[[ -f "$ROOT/secrets/env" ]] && . "$ROOT/secrets/env" || { [[ -f "$HOME/.config/bidkit/env" ]] && . "$HOME/.config/bidkit/env"; }

OPP_ID="${1:-}"
if [[ -z "$OPP_ID" ]]; then echo "usage: $0 <fga-opportunity-id> [--no-docs]" >&2; exit 2; fi
shift || true
PORTALS="$ROOT/inbox/portals.json"

cd "$ROOT/bidkit" && python3 -m bidkit.fga --portals "$PORTALS" file "$OPP_ID" --out "$ROOT/opportunities" --brief "$@"
