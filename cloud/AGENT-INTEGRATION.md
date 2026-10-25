# Integrating the SAM.gov research tool

A remote MCP server that finds federal contract opportunities a business can still respond to. Give it
NAICS codes; it returns open SAM.gov notices with everything already awarded, expired, cancelled, or
set aside for someone else removed. Your agent decides which ones fit.

You need two things from the owner: the **endpoint URL** and a **bearer token**. Each caller gets its
own token; treat it like a password.

## Connect

**Claude Code**

```bash
claude mcp add --transport http sam-research <URL> --header "Authorization: Bearer <TOKEN>"
```

**Claude Agent SDK (Python)**

```python
options = ClaudeAgentOptions(
    mcp_servers={
        "sam-research": {
            "type": "http",
            "url": os.environ["SAM_TOOL_URL"],
            "headers": {"Authorization": f"Bearer {os.environ['SAM_TOOL_TOKEN']}"},
        }
    },
    allowed_tools=["mcp__sam-research__*"],
)
```

**Claude API (MCP connector)**: Anthropic connects to the server for you.

```python
client.beta.messages.create(
    model="claude-opus-5-5",
    max_tokens=16000,
    betas=["mcp-client-2025-11-20"],
    mcp_servers=[{
        "type": "url",
        "url": os.environ["SAM_TOOL_URL"],
        "name": "sam-research",
        "authorization_token": os.environ["SAM_TOOL_TOKEN"],
    }],
    tools=[{"type": "mcp_toolset", "mcp_server_name": "sam-research"}],
    messages=[...],
)
```

Any other MCP client works too: the transport is Streamable HTTP, stateless. Every request is a
`POST` of JSON-RPC, and every reply is `application/json`. There is no SSE stream, and `GET` returns
`405`.

## Tools

### `search_opportunities`

| Argument | Type | Notes |
|---|---|---|
| `naics` | string[] | e.g. `["541511", "541512"]`. Up to 25. This or `psc` is required. |
| `psc` | string[] | Optional Product Service Codes, e.g. `["DA01"]` |
| `set_aside_eligibility` | string[] | Set-asides the business qualifies for: `SBA`, `SBP`, `8A`, `8AN`, `HZC`, `HZS`, `SDVOSBC`, `SDVOSBS`, `WOSB`, `WOSBSS`, `EDWOSB`, `EDWOSBSS`, `VSA`, `VSS`, `ISBEE`, `IEE`. Omit it to keep every set-aside. Unrestricted notices are always kept. |
| `days` | int | Only deadlines within this many days |
| `include_no_deadline` | bool | Also keep notices with no response date |
| `limit`, `offset` | int | Paging. Default 40 per page, max 60. |

Returns:

```json
{
  "total": 104, "offset": 0, "returned": 40, "has_more": true, "next_offset": 40,
  "dropped": {"set-aside not eligible (8A)": 2, "deadline beyond 30 days": 5},
  "notices": [{
    "notice_id": "f28de4a9e5b949fdb8142557bd2f2527",
    "title": "U.S. Senate Wellbeing Application",
    "notice_type": "Solicitation",
    "response_kind": "bid",
    "days_left": 28,
    "response_date": "2026-11-23T19:00:00+00:00",
    "agency": "SENATE, THE / ...",
    "set_aside": null,
    "naics_codes": ["541519"], "psc_code": "DA10",
    "place_of_performance": "DC 20002",
    "solicitation_number": "2027-R-007",
    "contact_email": "...",
    "description": "first ~300 characters, plain text",
    "url": "https://sam.gov/opp/.../view"
  }]
}
```

- `response_kind` is `bid` for a solicitation, `pre-bid` for a presolicitation, or `market research` for sources sought and RFI-style special notices.
- Notices are ordered by nearest deadline. That order is stable, so paging with `next_offset` neither skips nor repeats a notice. Each page re-runs the search, which takes about 1–4 seconds.

### `get_notice`

`{"notice_id": "<32-char id>"}`. Returns:

- the full description (plain text);
- every point of contact;
- the set-aside and place of performance;
- any award recorded against the notice;
- `attachments[]`, each with `name`, `size_bytes` and a `url` that downloads the RFP document directly with no authentication.

## Suggested agent behavior

The server returns candidates and doesn't judge fit; that's the agent's job. A loop that works:

1. Call `search_opportunities` with the business's codes and set-aside eligibility. Page until `has_more` is false.
2. Score each notice 0–100 against what the business actually does, and assign a verdict:
   - **pursue:** fit 70 or higher and nothing disqualifying;
   - **consider:** the description is too thin to judge, or the notice is only partly in scope;
   - **skip:** everything else.
3. Skip hardware, parts or brand-name license purchases for a services business, and notices of intent to sole-source to a named vendor.
4. Score Sources Sought and RFIs on fit too. Answering them is how a small business gets a later solicitation set aside for it.
5. Call `get_notice` only for `pursue` and `consider` notices, and read the attachments before recommending a bid.

`.claude/agents/sam-researcher.md` in this repo has the full rubric the local version uses.

## Limits and behavior

| | |
|---|---|
| Latency | `search_opportunities` takes about 1–4 seconds for a 4–9 code profile. `get_notice` takes under 1 second. |
| Timeout | 5 minutes per call (Lambda) |
| Page size | About 32,000 characters per 40-notice page, under Claude Code's 50,000-character MCP result limit |
| State | None. The server doesn't remember what a caller has already seen; track that on your side by `notice_id`. |
| Errors | Bad input comes back as a tool result with `isError: true` and a message. A bad or missing token gets HTTP `401`. |
| Freshness | Live. Every call queries SAM.gov. |

**Caveat:** the server uses the public JSON endpoints behind sam.gov's own search page. SAM.gov
doesn't document them, so they can change without notice. If searches start failing, check the
function's logs first.

## Operating it (owner)

```bash
cloud/tokens.sh add <name>       # new caller; token saved to ~/.config/sam-research-tool/token-<name>
cloud/tokens.sh revoke <name>    # takes effect within 5 minutes
cloud/tokens.sh list
cloud/deploy.sh                  # ship code changes; tokens untouched
cloud/smoke.sh <URL> @~/.config/sam-research-tool/token-owner
aws logs tail /aws/lambda/sam-research-tool --follow   # one line per call: caller, tool, ok, seconds
```

New tokens work within about 30 seconds.
