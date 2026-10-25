# Bid agent

The shell of Cadocary's bid agent on Claude Managed Agents. One operator agent hands the work to three helper agents, and each agent has one skill that holds its know-how. All of it is live in the team's Anthropic workspace. In the Claude Console, open Managed Agents and then Cadocary Operator.

| Agent | Job | Skill | Tools |
| --- | --- | --- | --- |
| Cadocary Operator | Pulls new RFPs, hands out the work, checks each result, and writes the packet Doug reads | `agent-delegation` | read, write, glob, grep, and Polina's SAM.gov tool (`search_opportunities`, `get_notice`) |
| Cadocary Qualifier | Decides pursue or pass, lists every requirement and deadline, and checks the other agents' work | `rfp-qualifying` | read, write, glob, grep |
| Cadocary Researcher | Finds what the contract is worth, comparable past awards, the incumbent, and a price, each with a source | `rfp-research` | read, write, glob, grep, web search, web fetch |
| Cadocary Drafter | Writes the proposal from the qualification, the research, and the approved facts | `proposal-drafting` | read, write, edit, glob, grep |

Settings on every agent:

- **Model:** Opus 5.5, with effort set to high.
- **Permissions:** every tool is set to "always allow", because "ask" would leave an unattended run waiting forever.
- **No bash.** No agent has bash, and none can send, submit, or email anything.
- **Helpers:** the three helpers are attached to the Operator by version. The Operator can't invent other agents or start workflows.

## Storage in the cloud

- **RFP Library** (memory store): every RFP found so far, plus earlier findings. The layout is in `memory/rfp-library/README.md`. It is empty for now.
- **Cadocary Facts** (memory store): everything the agents may say about Cadocary. It currently holds the registration details from the team's sourcing profile, the products, and Doug's preferences, none of them approved yet. Doug's facts sheet fills the rest (`docs/fact-sheet.md`).
- **RFP documents:** these go in the Files API, because they are too big for memory. A run gets them under `/mnt/session/uploads/`.
- **Vault** (`Cadocary bid agent`): holds the access code for Polina's SAM.gov tool. Anthropic adds it to each call, so no agent ever sees it.
- **Environment:** `cadocary-bids`, a cloud sandbox with open networking so the researcher can search. Since no agent has bash, web search, web fetch, and our own tools are the only ways out.

When starting a session, attach both memory stores as read-only and pass the vault's id (in `ids.json`). Only our code writes to the memory stores.

## Change something

Edit a prompt in `prompts/`, a skill in `skills/`, or a memory README in `memory/`, then run:

```bash
secret() { gcloud secrets versions access latest --project finchat-495622 --secret "$1"; }
ANTHROPIC_API_KEY="$(secret anthropic-api-key)" SAM_TOOL_URL="$(secret sam-tool-url)" SAM_TOOL_TOKEN="$(secret sam-tool-token)" python3 agent/setup.py
```

The tool's address and access code come from Secret Manager, which keeps them out of the repo.

The script uploads only what changed, makes a new version of each agent it touched, and repoints the Operator to the new helper versions. It records every id in `ids.json`, so commit that file too. Then everyone updates the same agents instead of creating copies.

If Python fails with `CERTIFICATE_VERIFY_FAILED` on a Mac, put `SSL_CERT_FILE=/etc/ssl/cert.pem` in front of the command.

## Not connected yet

- **Storing what intake finds.** The Operator pulls new RFPs with Polina's tool and writes `intake.json`: every notice, its first-look call (pursue, consider, or skip), and file links for the promising ones. Saving those RFPs and their files into the library is our code's job, and it isn't built yet. So a run that starts from intake stops after intake. To work an RFP end to end now, attach its files to the session and name them in the first message.
- **Tested on Oct 25.** The Operator searched all 95 open SAM.gov notices due within 30 days for Cadocary's codes, judged each one, and opened the 5 worth a look. It took 3 minutes and cost 82 cents.
- **No session launcher yet.** The plan is one session per RFP, started by our backend after sourcing.
- **No code checks or record tools yet.** Agents write their results as JSON in `/mnt/session/outputs/<rfp-id>/`, in the formats their skills give.
- **The Qualifier also checks the research and the draft,** as in the team's plan. The engineering review recommends a separate checker agent. See `docs/context.md`, decisions 4 and 5.
