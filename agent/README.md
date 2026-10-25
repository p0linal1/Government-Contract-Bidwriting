# Bid agent

The shell of Cadocary's bid agent on Claude Managed Agents. One operator agent hands the work to four helper agents, and each agent has skills that hold its know-how. All of it is live in the team's Anthropic workspace. In the Claude Console, open Managed Agents and then Cadocary Operator.

| Agent | Job | Skills | Tools |
| --- | --- | --- | --- |
| Cadocary Operator | Pulls new RFPs, hands out the work, checks each result, and writes the packet Doug reads | `agent-delegation` | read, write, glob, grep, and Polina's SAM.gov tool (`search_opportunities`, `get_notice`) |
| Cadocary Reader | Reads an RFP's attached documents, converts them to text, and fills the RFP sheet every later step works from. Runs on Sonnet 5.5 | `rfp-reading` | read, write, glob, grep, bash, web fetch |
| Cadocary Qualifier | Decides pursue or pass from the sheet and Cadocary's facts, and checks the other agents' work | `rfp-qualifying`, `company-facts` | read, write, glob, grep |
| Cadocary Researcher | Finds what the contract is worth, comparable past awards, the incumbent, and a price, each with a source | `rfp-research` | read, write, glob, grep, web search, web fetch |
| Cadocary Drafter | Writes the proposal from the qualification, the research, and the approved facts | `proposal-drafting`, `company-facts` | read, write, edit, glob, grep |

Settings on every agent:

- **Model:** Opus 5.5, with effort set to high.
- **Permissions:** every tool is set to "always allow", because "ask" would leave an unattended run waiting forever.
- **Bash only for the Reader.** It needs bash to convert RFP files to text, and to download any file our code couldn't attach, because web fetch refuses links handed over by another agent. No other agent has bash, and none can send, submit, or email anything.
- **Helpers:** the four helpers are attached to the Operator by version. The Operator can't invent other agents or start workflows.

## Storage in the cloud

- **RFP Library** (memory store): every RFP found so far, plus earlier findings. `library.py` fills it (below). The layout is in `memory/rfp-library/README.md`.
- **Cadocary Facts** (memory store): everything the agents may say about Cadocary. It holds the registration details, what cadocary.com and Doug's capability statement say (each fact with its page), and Doug's preferences, none of them approved yet. Contact details and the street address live in a gitignored `memory/cadocary-facts/private.md`, which `setup.py` loads as `/private.md` only on a machine that has it. The `company-facts` skill teaches the Qualifier and Drafter to choose the facts that fit each bid. Doug's answers to `docs/questions-for-doug.md` fill the rest.
- **RFP documents:** these go in the Files API, because they are too big for memory. A run gets them under `/mnt/session/uploads/<rfp-id>/`.
- **Vault** (`Cadocary bid agent`): holds the access code for Polina's SAM.gov tool. Anthropic adds it to each call, so no agent ever sees it.
- **Environment:** `cadocary-bids`, a cloud sandbox with open networking so the researcher can search. Since no agent has bash, web search, web fetch, and our own tools are the only ways out.

When starting a session, attach both memory stores as read-only and pass the vault's id (in `ids.json`). Only our code writes to the memory stores. `run.py` does all of this.

## Fill the library and run one RFP

Both scripts use the same keys as `setup.py`, so put the same `secret` line and environment in front of them (see "Change something").

```bash
python3 agent/library.py sync                                   # store every open notice not stored yet
python3 agent/run.py <rfp-id> --steps read,qualify --budget-usd 5   # or --steps all, the default, capped at $40
```

- **`library.py sync`** searches Polina's tool with Cadocary's codes, pages through every result, writes `/rfps/<rfp-id>/record.json` for each notice not stored yet with status `new`, and rebuilds `/index.md`. An RFP's id is its SAM.gov notice id. It is safe to run again.
- **`run.py`** first runs `library.py fetch-documents`: it downloads every attachment, uploads it to the Files API, and keeps the file ids in the record, skipping files already stored. Then it starts one session on the Operator version pinned in `ids.json`, with the vault, both memory stores read-only, every document mounted under `/mnt/session/uploads/<rfp-id>/`, and the dollar cap. Earlier findings too big for a memory are mounted under `/mnt/session/uploads/findings/<rfp-id>/`. It prints the session id, waits for the session to finish, prints the Operator's final message, the cost, and the minutes, and runs `library.py save-findings`. It won't start while an earlier session on the same RFP is still unsaved, so a second launch can't double the spend.
- **`library.py save-findings <session-id> <rfp-id>`** copies the run's `.json` and `.md` outputs into `/rfps/<rfp-id>/findings/`, and updates the status from what the run decided. A file too big for a memory, such as the sheet of a long RFP, is copied to the Files API instead. That copy can be attached to later runs but not downloaded, because the Files API only lets you download files a session made. The session's own copy (`from_file_id` in the record) stays downloadable until the session is deleted. Run it by hand if `run.py` was stopped while the session kept going.
- **Tested on Oct 25** on the U.S. Senate Wellbeing Application: sync stored 148 notices. A read-and-qualify run read all 8 attached files (113 pages) without downloading anything, wrote a sheet with 160 requirements, and passed on it, for $2.62 in 11 minutes. save-findings stored the packet and qualification as memories and the 123 kB sheet in the Files API, and set the status to `passed`.

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

- **Intake's first-look calls aren't saved.** The Operator can still pull RFPs itself and write `intake.json` with a pursue, consider, or skip call for each new notice. No code reads that file yet, so the calls don't reach the library. Tested on Oct 25: it judged all 95 open notices due within 30 days in 3 minutes, for 82 cents.
- **No schedule yet.** Nothing runs `sync` or `run.py` on its own. The plan is one session per RFP, started by our backend after sourcing.
- **No code checks or record tools yet.** Agents write their results as JSON in `/mnt/session/outputs/<rfp-id>/`, in the formats their skills give.
- **The Qualifier also checks the research and the draft,** as in the team's plan. The engineering review recommends a separate checker agent. See `docs/context.md`, decisions 4 and 5.
