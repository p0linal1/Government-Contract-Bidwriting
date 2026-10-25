#!/usr/bin/env bash
# build.sh — package the Lambda: cloud/handler.py plus the pipeline modules it imports, flat in one
# zip. Stdlib only (boto3 comes with the Lambda runtime), so there is nothing to pip install.
#
# Usage:  cloud/build.sh        → cloud/dist/sam-research-tool.zip
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$ROOT/cloud/dist"
STAGE="$DIST/stage"
rm -rf "$STAGE" && mkdir -p "$STAGE"
cp "$ROOT/cloud/handler.py" "$ROOT/scripts/fetch_sam_opportunities.py" "$ROOT/scripts/filter_open.py" \
   "$ROOT/scripts/scores.py" "$STAGE/"
rm -f "$DIST/sam-research-tool.zip"
(cd "$STAGE" && zip -q -r "$DIST/sam-research-tool.zip" .)
rm -rf "$STAGE"
echo "$DIST/sam-research-tool.zip"
