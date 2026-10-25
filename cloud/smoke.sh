#!/usr/bin/env bash
# smoke.sh — check a deployed tool end to end: auth, MCP handshake, and one real SAM.gov search.
#
# Usage:  cloud/smoke.sh <function-url> <token | @token-file> [naics]
set -euo pipefail
URL="${1:?usage: $0 <function-url> <token | @token-file> [naics]}"; TOKEN="${2:?token}"; NAICS="${3:-541511}"
[[ "$TOKEN" == @* ]] && TOKEN="$(cat "${TOKEN#@}")"
post() { curl -sS -X POST "$URL" -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' -d "$1"; }

echo -n "no token → "; curl -s -o /dev/null -w '%{http_code} (want 401)\n' -X POST "$URL" -d '{}'
echo -n "initialize → "; post '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["serverInfo"])'
echo -n "tools/list → "; post '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | python3 -c 'import json,sys; print([t["name"] for t in json.load(sys.stdin)["result"]["tools"]])'
echo "search NAICS $NAICS (10-60s) →"
time post "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"search_opportunities\",\"arguments\":{\"naics\":[\"$NAICS\"],\"days\":30}}}" \
  | python3 -c '
import json, sys
r = json.load(sys.stdin)["result"]
text = r["content"][0]["text"]
if r["isError"]:
    sys.exit("  FAILED: " + text)
d = json.loads(text)
print("  %s open notices (%s on this page, %s chars); dropped %s" % (d["total"], d["returned"], len(text), d["dropped"]))
for n in d["notices"][:3]:
    print("  - %s (%sd)" % (n["title"][:70], n["days_left"]))'
