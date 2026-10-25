# Hosting code on AWS: how we did it

This explains how the SAM.gov research tool ended up running on AWS, and how to do the same for
something new. No prior AWS knowledge assumed.

## The short version

1. Get logged in to AWS from your laptop (once).
2. Wrap your Python code in a function AWS knows how to call.
3. Zip it and upload it as a **Lambda function**.
4. Give it a public **Function URL** so other people and agents can reach it.
5. Lock it down with access tokens kept in **Secrets Manager**.

`cloud/deploy.sh` does steps 3–5 in one command. The rest of this page explains what each piece is
and why it's there.

---

## The pieces, in plain terms

| AWS thing | What it is | Ours |
|---|---|---|
| **Account** | Your AWS "space". Everything you create lives in it and bills to it. | a 12-digit number, shown by `aws sts get-caller-identity` |
| **Region** | Which data center everything runs in. Pick one and stay in it. | `us-east-1` (N. Virginia) |
| **IAM user + access keys** | A login for *you* on the command line. The keys are a username/password pair the `aws` command uses. | one IAM user with admin rights |
| **Lambda function** | Your code, hosted. AWS runs it only when a request comes in, then shuts it down. No server to manage. | `sam-research-tool` |
| **IAM role** | A login for *the function*. It says what the code may touch in AWS (here: write logs, read one secret). Separate from your own login. | `sam-research-tool-role` |
| **Function URL** | A public `https://…` address that runs the function when called. | `https://….lambda-url.us-east-1.on.aws/` |
| **Secrets Manager** | Encrypted storage for passwords and tokens, which the function reads at runtime. | `sam-research-tool/tokens` |
| **CloudWatch Logs** | Where anything the function `print()`s ends up. | `/aws/lambda/sam-research-tool` |

**Why Lambda and not a server:** a "real" server (EC2) runs 24/7, so you pay for it, patch it, and
keep it alive. A Lambda runs only when called, scales itself, and at our volume is effectively
free. The tradeoffs:

- 15 minutes max per call.
- Nothing is remembered between calls.
- No GPUs.
- It can't hold a connection open (no WebSockets).

Anything that answers a request in seconds fits. Long jobs, always-on servers, and ML models don't.

---

## Step 1: Log in to AWS from your laptop (once per machine)

```bash
brew install awscli
aws configure            # paste the access key ID + secret; region us-east-1; output json
aws sts get-caller-identity   # prints your account number = it worked
```

To get access keys: AWS Console → **IAM → Users → Create user** → attach a policy → open the user →
**Security credentials → Create access key → Command Line Interface**. For the first setup the
user needs broad permissions (it creates roles), so **AdministratorAccess** is simplest.

If your organization uses single sign-on (you log in at `something.awsapps.com/start`), use
`aws configure sso` and `aws sso login` instead. Same result, temporary credentials.

Access keys work until you delete them. Between deploys you can **deactivate** them (same
Security credentials page) and reactivate when needed.

---

## Step 2: Make your code callable by Lambda

Lambda calls one function in your code, with the HTTP request as a dictionary, and expects a
dictionary back:

```python
import json

def lambda_handler(event, context):
    method = event["requestContext"]["http"]["method"]   # "GET", "POST", ...
    headers = event.get("headers") or {}                  # header names are lowercase
    body = event.get("body") or ""                        # the request body, as text
    # ... do your work ...
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"hello": "world"}),
    }
```

That's the whole contract. `cloud/handler.py` is our real one: it checks the bearer token, reads
the JSON-RPC message the agent sent, runs the SAM.gov search using the same code as
`scripts/`, and returns JSON.

Things to know when adapting code:

- **Only `/tmp` is writable**, and anything written there may be gone on the next call. Save
  anything that must persist to S3 or DynamoDB.
- **Packages:** the standard library and `boto3` (the AWS library) are built in. Anything else you
  `pip install` has to go into the zip, built for Linux. That's why our tool sticks to the standard
  library.
- **`print()` goes to CloudWatch Logs.** That's your debugging output.

---

## Step 3: Deploy

For this project it's one command, and it's safe to re-run:

```bash
cloud/deploy.sh
```

What it does, in order:

1. **Builds** `cloud/dist/sam-research-tool.zip` (`cloud/build.sh` copies `handler.py` plus the
   `scripts/` modules it imports into one flat zip).
2. **Creates the token secret** in Secrets Manager. On the first run only, it generates your first
   token and saves it to `~/.config/sam-research-tool/token-owner`.
3. **Creates the role** the function runs as: allowed to write logs and read that one secret,
   nothing else.
4. **Creates the function**, or on later runs **updates its code**: Python 3.12, ARM processor,
   512 MB memory, 5-minute timeout.
5. **Creates the Function URL**, plus the permission that lets the public internet call it. The
   code itself rejects anyone without a valid token.
6. **Saves the URL** to `~/.config/sam-research-tool/url` and prints next steps.

Every later code change: edit, run the tests, run `cloud/deploy.sh` again. Tokens are left alone.

### Check it works

```bash
cloud/smoke.sh "$(cat ~/.config/sam-research-tool/url)" @$HOME/.config/sam-research-tool/token-owner
```

You should see a `401` for the no-token call, the tool names, and a real search result.

---

## Step 4: Give people access

Each person or agent gets their **own token**, so you can cut one off without breaking anyone else:

```bash
cloud/tokens.sh add sheffield       # saved to ~/.config/sam-research-tool/token-sheffield
cloud/tokens.sh list
cloud/tokens.sh revoke sheffield    # stops working within 5 minutes
```

Send tokens by AirDrop or direct message, never a group chat or a committed file. The file ends
with a line break; strip it (`tr -d '\n' < file`) before pasting it into another secret store.

The URL isn't secret. Without a token it only returns `401`.

---

## Hosting something new from scratch

The minimum to put any Python function on the internet, by hand. Replace `hello` with your name,
and `ACCOUNT_ID` with the number from `aws sts get-caller-identity`:

```bash
# 1. Code
cat > handler.py <<'EOF'
import json
def lambda_handler(event, context):
    return {"statusCode": 200, "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"hello": "world"})}
EOF
zip function.zip handler.py

# 2. A role for the function to run as (allowed to write logs)
aws iam create-role --role-name hello-role --assume-role-policy-document \
  '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam attach-role-policy --role-name hello-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
sleep 10   # new roles take a few seconds to become usable

# 3. The function
aws lambda create-function --function-name hello --runtime python3.12 \
  --handler handler.lambda_handler --zip-file fileb://function.zip \
  --role arn:aws:iam::ACCOUNT_ID:role/hello-role

# 4. A public URL (both permissions are needed)
aws lambda create-function-url-config --function-name hello --auth-type NONE
aws lambda add-permission --function-name hello --statement-id url \
  --action lambda:InvokeFunctionUrl --principal "*" --function-url-auth-type NONE
aws lambda add-permission --function-name hello --statement-id url-invoke \
  --action lambda:InvokeFunction --principal "*" --invoked-via-function-url

# 5. Try it
curl "$(aws lambda get-function-url-config --function-name hello --query FunctionUrl --output text)"
```

To update code later: `zip function.zip handler.py`, then
`aws lambda update-function-code --function-name hello --zip-file fileb://function.zip`.

**Warning:** this URL has no access control. Anyone who finds it can call it, and you pay for
every call. Before it does anything real, add a token check like the one in `cloud/handler.py`
(`caller_for`). Easiest: copy `cloud/deploy.sh` and `cloud/tokens.sh` and change the names.

---

## What it costs

At our usage, close to nothing:

- **Lambda:** billed per call by time × memory. The free tier covers 1 million calls and 400,000
  GB-seconds a month, which is thousands of searches a day.
- **Secrets Manager:** about $0.40 a month per secret.
- **CloudWatch Logs:** cents.

To keep an eye on it, set a **budget alert** (Console → Billing → Budgets, e.g. email me above
$5/month). There is no cap on how many calls can run at once; our account's limit was too low to
reserve one. So if a token leaks, revoke it.

---

## When something breaks

| Symptom | Check |
|---|---|
| `aws: Unable to locate credentials` / `ExpiredToken` | You're not logged in: `aws configure`, or `aws sso login` |
| `AccessDenied` while deploying | Your IAM user lacks permissions; it needs IAM, Lambda and Secrets Manager rights |
| `The role defined for the function cannot be assumed` | The role was just created; wait 10 seconds and re-run (`deploy.sh` retries this) |
| Calls return `401` | Wrong, revoked, or newline-padded token |
| Calls return `500` / time out | Read the logs: `aws logs tail /aws/lambda/sam-research-tool --since 15m` |
| It worked locally but not on AWS | A package missing from the zip, or code writing outside `/tmp` |

---

## Taking it all down

Everything `deploy.sh` created, removed in reverse order:

```bash
aws lambda delete-function-url-config --function-name sam-research-tool
aws lambda delete-function --function-name sam-research-tool
aws iam delete-role-policy --role-name sam-research-tool-role --policy-name read-token-secret
aws iam detach-role-policy --role-name sam-research-tool-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
aws iam delete-role --role-name sam-research-tool-role
aws secretsmanager delete-secret --secret-id sam-research-tool/tokens --recovery-window-in-days 7
aws logs delete-log-group --log-group-name /aws/lambda/sam-research-tool
```

The secret is recoverable for 7 days after deletion; everything else is gone immediately. Running
`cloud/deploy.sh` again rebuilds it all, with new tokens.
