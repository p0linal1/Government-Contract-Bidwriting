#!/usr/bin/env bash
# deploy.sh — create or update the SAM.gov research tool on AWS Lambda behind a Function URL.
# Safe to re-run: the first run creates everything, later runs just ship new code.
#
# Creates (names overridable with the env vars below):
#   Secrets Manager secret  sam-research-tool/tokens   {"caller name": "bearer token"}
#   IAM role                sam-research-tool-role     logs + read that one secret
#   Lambda function         sam-research-tool          python3.12, 512 MB, 5 min timeout
#   Function URL            public HTTPS endpoint; the function itself rejects calls without a token
#
# Usage:  cloud/deploy.sh
# Env:    AWS_REGION (default us-east-1), FUNCTION_NAME, SECRET_NAME, AWS_PROFILE
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export AWS_REGION="${AWS_REGION:-us-east-1}" AWS_PAGER=""
FN="${FUNCTION_NAME:-sam-research-tool}"
SECRET="${SECRET_NAME:-$FN/tokens}"
ROLE="$FN-role"

say() { printf '\n== %s\n' "$*"; }

say "checking AWS login"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text) || {
  echo "Not logged in. Run 'aws configure' or 'aws sso login' first." >&2; exit 1; }
echo "account $ACCOUNT, region $AWS_REGION"

say "building"
ZIP=$("$ROOT/cloud/build.sh")

say "token secret"
NEW_TOKEN=""
if aws secretsmanager describe-secret --secret-id "$SECRET" >/dev/null 2>&1; then
  echo "exists: $SECRET"
else
  NEW_TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
  aws secretsmanager create-secret --name "$SECRET" \
    --description "Bearer tokens for the $FN MCP server" \
    --secret-string "{\"owner\": \"$NEW_TOKEN\"}" >/dev/null
  echo "created: $SECRET (first token is named 'owner')"
fi
SECRET_ARN=$(aws secretsmanager describe-secret --secret-id "$SECRET" --query ARN --output text)

say "execution role"
if aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  echo "exists: $ROLE"
else
  aws iam create-role --role-name "$ROLE" --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]
  }' >/dev/null
  aws iam attach-role-policy --role-name "$ROLE" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  echo "created: $ROLE (waiting for IAM to propagate)"
  sleep 12
fi
aws iam put-role-policy --role-name "$ROLE" --policy-name read-token-secret --policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [{\"Effect\": \"Allow\", \"Action\": \"secretsmanager:GetSecretValue\", \"Resource\": \"$SECRET_ARN\"}]
}"
ROLE_ARN=$(aws iam get-role --role-name "$ROLE" --query Role.Arn --output text)

say "function"
ENV="{\"Variables\": {\"SAM_TOOL_TOKENS_SECRET\": \"$SECRET_ARN\"}}"
if aws lambda get-function --function-name "$FN" >/dev/null 2>&1; then
  aws lambda update-function-code --function-name "$FN" --zip-file "fileb://$ZIP" >/dev/null
  aws lambda wait function-updated --function-name "$FN"
  aws lambda update-function-configuration --function-name "$FN" --environment "$ENV" \
    --timeout 300 --memory-size 512 >/dev/null
  aws lambda wait function-updated --function-name "$FN"
  echo "updated: $FN"
else
  for attempt in 1 2 3; do
    # A brand-new role can take a few more seconds before Lambda may assume it.
    aws lambda create-function --function-name "$FN" --runtime python3.12 --architectures arm64 \
      --handler handler.lambda_handler --role "$ROLE_ARN" --zip-file "fileb://$ZIP" \
      --timeout 300 --memory-size 512 --environment "$ENV" >/dev/null && break
    [[ $attempt == 3 ]] && exit 1
    sleep 10
  done
  aws lambda wait function-active --function-name "$FN"
  echo "created: $FN"
fi

say "function URL"
if ! aws lambda get-function-url-config --function-name "$FN" >/dev/null 2>&1; then
  aws lambda create-function-url-config --function-name "$FN" --auth-type NONE >/dev/null
  aws lambda add-permission --function-name "$FN" --statement-id public-function-url \
    --action lambda:InvokeFunctionUrl --principal "*" --function-url-auth-type NONE >/dev/null
  # Newer accounts also require InvokeFunction for URL calls; older CLIs lack the flag, which is fine.
  aws lambda add-permission --function-name "$FN" --statement-id public-function-url-invoke \
    --action lambda:InvokeFunction --principal "*" --invoked-via-function-url >/dev/null 2>&1 || true
fi
URL=$(aws lambda get-function-url-config --function-name "$FN" --query FunctionUrl --output text)

# Cap concurrent runs so a leaked token can't run up a bill. Fails harmlessly on accounts whose
# total concurrency limit is too low to reserve from.
aws lambda put-function-concurrency --function-name "$FN" --reserved-concurrent-executions 5 >/dev/null 2>&1 \
  || echo "(could not reserve concurrency; account limit too low — fine for now)"

say "done"
echo "URL: $URL"
TOKEN_DIR="$HOME/.config/$FN"
mkdir -p "$TOKEN_DIR" && chmod 700 "$TOKEN_DIR"
echo "$URL" > "$TOKEN_DIR/url"
if [[ -n "$NEW_TOKEN" ]]; then
  # Saved to a private file rather than printed, so it doesn't land in terminal logs or scrollback.
  (umask 077 && echo "$NEW_TOKEN" > "$TOKEN_DIR/token-owner")
  cat <<MSG

Your token is saved (readable only by you) at:
  $TOKEN_DIR/token-owner

Test it:
  cloud/smoke.sh $URL @$TOKEN_DIR/token-owner

Add it to Claude Code:
  claude mcp add --transport http sam-research $URL --header "Authorization: Bearer \$(cat $TOKEN_DIR/token-owner)"
MSG
else
  echo "Tokens unchanged. Manage them with cloud/tokens.sh."
fi
