#!/usr/bin/env bash
# tokens.sh — manage who can call the tool. One token per caller, so you can revoke one person
# without touching anyone else. Changes reach the running function within 5 minutes.
#
# Usage:  cloud/tokens.sh list
#         cloud/tokens.sh add <name>      # prints the new token once
#         cloud/tokens.sh revoke <name>
set -euo pipefail
export AWS_REGION="${AWS_REGION:-us-east-1}" AWS_PAGER=""
SECRET="${SECRET_NAME:-${FUNCTION_NAME:-sam-research-tool}/tokens}"
cmd="${1:-list}"; name="${2:-}"
current=$(aws secretsmanager get-secret-value --secret-id "$SECRET" --query SecretString --output text)
case "$cmd" in
  list)
    python3 -c 'import json,sys; [print(n) for n in sorted(json.loads(sys.argv[1]))]' "$current" ;;
  add|revoke)
    [[ -n "$name" ]] || { echo "usage: $0 $cmd <name>" >&2; exit 2; }
    out=$(python3 - "$cmd" "$name" "$current" <<'PY'
import json, secrets, sys
cmd, name, tokens = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
if cmd == "add":
    if name in tokens:
        sys.exit(f"{name} already has a token; revoke it first")
    tokens[name] = secrets.token_urlsafe(32)
    print(tokens[name])
else:
    if tokens.pop(name, None) is None:
        sys.exit(f"no token named {name}")
    print("")
print(json.dumps(tokens))
PY
)
    token=$(printf '%s\n' "$out" | head -1); updated=$(printf '%s\n' "$out" | tail -1)
    aws secretsmanager put-secret-value --secret-id "$SECRET" --secret-string "$updated" >/dev/null
    if [[ "$cmd" == add ]]; then
      dir="$HOME/.config/${FUNCTION_NAME:-sam-research-tool}"; mkdir -p "$dir" && chmod 700 "$dir"
      (umask 077 && echo "$token" > "$dir/token-$name")
      echo "token for $name saved to $dir/token-$name — send it to them over a private channel"
    else
      rm -f "$HOME/.config/${FUNCTION_NAME:-sam-research-tool}/token-$name"; echo "revoked $name"
    fi ;;
  *) echo "usage: $0 list | add <name> | revoke <name>" >&2; exit 2 ;;
esac
