# Engineering review: Cadocary bid agent

- **Plan reviewed:** `docs/reviews/plan.md` ("Plan: Cadocary bid agent")
- **Method:** GStack plan-eng-review: Scope Challenge, then Architecture, Code Quality, Tests, Performance, plus failure modes and the required outputs.
- **Platform facts checked against:** `docs/managed-agents.md` (Managed Agents docs, compiled 2026-10-25) and the Managed Agents reference that ships with Claude Code.
- **Ground truth used:** the real RFPs in the team RFP collection (Lakewood, Delaware, Champaign, Lewis, Whatcom) and the collection notes in the collection notes (data-001 to data-010).
- **Review only.** No commands, scripts, setup or telemetry were run. Nothing was changed except this file. Questions the method would ask the team are under "Decisions for the team", each with a recommendation.
- **Status:** DONE_WITH_CONCERNS. The plan fits Managed Agents, but five design changes should happen before anyone writes agent code (the first five points below).

---

## The short version

If you read nothing else, read this.

1. **One agent session per RFP, started by our own backend.** Not one big session per day. A scheduled deployment sends the same starting message and the same attached files every day, so it cannot hand the agent "today's RFP". One session per RFP gives each bid its own spending cap, its own live feed in the app, and its own failure that does not stop the others.
2. **The agent drives, code holds the gates.** The operator agent decides what to do next, but every step ends by filing a fixed form through a tool we write ("record tools"). Our code checks that form, refuses it if it is wrong, and refuses steps out of order (no draft before research has passed its check).
3. **"Not found" is a normal answer, and code checks every source.** The mentor's warning ("Claude will do deep research and lie to you") is answered by code, not by a second AI: code re-opens every cited web page and checks the quoted words are really there, and checks every RFP quote is on the page cited. Any number without a source must be labeled an educated guess.
4. **Nothing in the system can send.** No agent gets an email, upload, submit or portal tool. After Doug says yes, code builds the final packet and a checklist, and Doug sends it himself.
5. **There are deadlines before the deadline.** Lakewood's questions were due a week before proposals. Delaware required an intent-to-submit and a mandatory pre-proposal meeting. "Doug acts once, at the end" misses these. The plan needs one early, rare notice for time-sensitive items (Decision D5).
6. **Deadlines and time zones are code, and the agent's reading must match.** Lakewood says "5:00 PM PST" on October 25, 2024, when Pacific time was on daylight time. Read literally as PST, the deadline lands one hour late. Code parses, the agent reads, and if they disagree the bid is flagged.
7. **The drafter needs a facts library, or it will invent Cadocary's past work.** The proposal is legally binding. Every claim about Cadocary (past contracts, references, certifications, insurance, prices) must come from a library Doug has approved, and code checks each claim maps to an entry.
8. **Unattended runs hang on anything that asks permission.** The platform's default for MCP tools is "ask a person". At 5 AM nobody is there, so the run waits forever. Every tool's permission must be set explicitly, and a watcher in our backend must catch stuck runs.
9. **The live view needs each subagent's own feed.** The main event stream shows the operator's work plus status changes of the subagents, not every research step. The backend must also read each subagent's thread to show research live.
10. **Do not grade the agent on the same RFPs used to write its skills.** Hold out about 40 of the 100 RFPs, and have a person check the answer key for deadlines and fatal requirements on those.
11. **Biggest risk today: there is no Anthropic API key yet**, and Managed Agents and memory stores are beta features that must be enabled on that key. Nothing else can be tested until that is solved.

---

## Step 0: Scope challenge

### What already exists (reuse it, do not rebuild it)

| Piece | Where | How to reuse it |
|---|---|---|
| bidkit inbox poller, FGA search, triage scoring | Doug's Python | Becomes sourcing code later. Not needed for today if SAM.gov is the live source. |
| Portal downloads with saved logins (WEBS, Public Purchase) | Doug's Python (Playwright) | Stays on Cadocary's server. Wrap as an MCP server after the demo. |
| Facts extractor with source snippets | Doug's Python | Its "fact plus snippet" shape is exactly the citation format every agent must use. Copy its format into the schemas. |
| Five pass/fail gates (intake, value, pricing, fit, go/no-go) | Doug's Python | These are the code checks. Intake becomes completeness, value becomes the $25,000 filter, fit and go/no-go become hard stops plus agent judgment. |
| Calendar files | Doug's Python | Reuse to put every deadline (questions, meeting, proposal) on Doug's calendar when a bid starts. |
| PDF assembly | Doug's Python | Reuse as the deterministic renderer that also counts pages (`render_draft` tool). |
| Clickable prototype with live event streams, source chips, morning brief, page-by-page review | React prototype, shared as an artifact | Keep the screens. Replace the simulated events with real ones, which means matching real event types (see Section 2). |
| Team repo: FastAPI, React, CI, Cloud Run plan, Firestore planned, Pydantic for document shapes | `Claude Impact Lab/` | Backend hosts sourcing, the session launcher, the MCP endpoint, webhooks and the event relay. |
| RFP collection | Team RFP collection (on Sheffield's laptop) | Five full RFPs and ten summarized ones already show the rare-but-fatal cases (paper-only, separate cost volume, mandatory meetings). Use them now as the first test cases. |

### Minimum that achieves the goal for the 7:30 PM demo

The demo story Doug wants is one message: "You are a competitive applicant, here is your application, here is what it is worth. Permission to send?" The smallest real version of that:

1. One real RFP, end to end, on Managed Agents: qualify, research with real award data and sources, check, draft, packet.
2. The app showing that run live, then showing the packet and the "permission to send" screen.
3. Code checks visibly catching something (a bad citation, a page overflow, a mismatched deadline).
4. SAM.gov sourcing running for real, even if the demo RFP is preloaded.

Everything else (bidkit as MCP, WEBS and FGA, memory written from Doug's decisions, the full 100-RFP evaluation, the daily schedule running for real) is next sprint.

### Complexity check

The plan as written adds five agents, five skills, two MCP servers, a scheduler, vaults, two memory stores, a webhook receiver, an event relay, sourcing, a 100-RFP evaluation and the app. GStack treats more than two new services as a smell; this is several times past it. It is the right long-term shape, but not a one-afternoon build with no API key yet. **Recommendation: reduce scope for today to the demo path above (Decision D1).**

---

## Platform check: what the plan assumes vs what Managed Agents does

| The plan says | What the platform actually does | What to change |
|---|---|---|
| Scheduled deployments use cron | True. But every run gets the same starting message and the same attached files. Start time can drift up to 9 minutes. On daylight-saving days, times between 1 and 3 AM are skipped or run twice. No one is connected while it runs. | A deployment cannot pass in today's RFP. Use one session per RFP from our backend (D2). If a deployment is used, schedule it at 5 or 6 AM Pacific, never 1 to 3 AM. |
| Vaults inject credentials at request time | True for MCP servers (matched by URL) and for secrets placed in request headers or body. Not substituted inside a web address. Attached only when a session is created. | Use the vault only for the bearer token of our own MCP endpoint. SAM.gov's documented examples put the key in the web address, so keep that key in the backend, where sourcing runs anyway. Portal logins never enter the agent. |
| Skills attach to agents | True. Up to 20 per agent, versions can be pinned, needs the `read` tool. Skills can also load from a mounted GitHub repo's `.claude/skills/` folder. | Do not mount the team repo to load skills. Its `.claude/skills/` holds `deploy`, `kickoff` and `ship`, which would load into the bid agent. Upload the bid skills through the Skills API and pin versions. |
| A coordinator delegates to predefined subagents that share the sandbox | True. One level deep only. At most 25 child threads per session, idle ones included. A subagent sees only the task it is sent and the shared files, not the operator's conversation. On the newer multiagent type, "workflow runs" and "inline agents" (agents the operator invents on the spot) are on by default. | Turn workflows and inline agents off on the operator so it can only use the four agents we defined. Every delegation carries file paths and the expected form, not a summary. One session per RFP keeps us far under 25 threads. |
| Memory stores persist between sessions | True. Attached only at session creation, 8 per session, 100 kB per memory. Default access is read-write, and the docs warn a prompt-injected agent can write into a store that later sessions trust. | Mount memory read-only. Only our code writes to it, from Doug's decisions. |
| The event stream exposes every tool call and result | Partly. The main stream carries the operator's own calls plus each subagent's status changes and the messages between agents. Each subagent's tool calls are on that subagent's thread stream. The stream has no replay. | The backend reads thread streams (or thread event lists) to show research steps live. On every reconnect: open the stream, list the history, skip events already seen. |
| Outcomes grade a deliverable against a rubric with a separate grader | True. Default 3 rounds, max 20. The grader has no web tools and its reasoning is hidden; you get a short explanation. | Good fit later for the draft. For today, a Checker agent with a fixed output form is easier to test and to show Doug. |
| Gap: no Gmail or Drive connector | Correct, and not needed. | The agent should have no email at all. Notifying Doug is plain backend code. |
| Gap: no saved browser logins | Correct for the sandbox. The sandbox does include Playwright and Chromium. | Keep portal logins on Cadocary's server behind bidkit. Do not move logged-in portals into the sandbox: a logged-in portal is one click from "submit". |
| Gap: a new email cannot start a run | Not a platform gap. Webhooks only go from Anthropic to us, but our backend can create a session from anything it receives. bidkit's inbox poller already does the receiving. | Later: inbox poller calls the same launcher as sourcing. |
| Gap: grading loops do not pause for a person | Correct, and that matches what Doug wants. The real risk is the opposite: anything set to "ask" pauses forever. | Set every tool's permission explicitly. No tool set to "ask". A watcher catches anything stuck. |
| Not in the plan: hard spending caps | Each session can have a hard dollar cap. At the cap it pauses (not deleted) and can resume when the cap is raised. A deployment's cap is copied to each run. | Use a cap on every session. This is the answer to cost runaway. |
| Not in the plan: model effort | Opus 5.5's default effort is "medium". | Set effort to "high" explicitly on every agent. |
| Not in the plan: custom tools need our code to answer | A custom tool call waits until our code answers it. In an unattended run that means a webhook handler. MCP tools are answered by the MCP server directly. | Host our tools on an MCP endpoint in the backend, not as custom tools (D3). |
| Not documented: how long a session may run or sit idle | Unknown. | Our own watchdog sets the time limit. |

---

## Section 1: Architecture

### The system on one page

```text
 5:00 AM PT  Cloud Scheduler (or deployment, see D2)                      DOUG, in the browser
       |                                                                        ^
       v                                                                        | queue, live view,
+------------------------------- BACKEND: FastAPI on Cloud Run ----------------+------------------+
|                                                                                                 |
|  SOURCING (code)              LAUNCHER (code)                 APP API (code)                    |
|  SAM.gov saved searches  -->  claim RFP (once only),     -->  event relay: history + live,      |
|  filters, completeness,       upload its documents,           plain-language step labels,       |
|  dedupe, deadlines + tz       start 1 session per RFP         packet, approve / pass            |
|                               with cap + time limit                                             |
|                                                                                                 |
|  MCP ENDPOINT /mcp (code)                    WATCHERS (code)                                    |
|  read: RFP facts, award search, facts       webhooks: idle, terminated, thread events           |
|  lookup, render_draft (page count)          every 10 min: stuck, over time, at cap,             |
|  record_*: check form, order, sources       missing final packet --> RFP status                 |
+------------+-----------------------------------^------------------------------------------------+
             |  starts sessions                  |  tool calls (MCP), events, webhooks
             v                                   |
+-------------------- ANTHROPIC MANAGED AGENTS: one session per RFP -----------------------------+
|                                                                                                 |
|  OPERATOR (coordinator, Opus 5.5, skill: delegate)                                              |
|     |-- QUALIFIER   skill: qualify            --> record_qualification                          |
|     |-- RESEARCHER  skill: research + price   --> record_research   (web search, web fetch)     |
|     |-- CHECKER     skill: check (new thread each time) --> record_check                        |
|     |-- DRAFTER     skill: draft              --> record_draft      (render_draft for pages)    |
|     '-- operator itself                       --> record_packet                                 |
|                                                                                                 |
|  shared sandbox:  /mnt/session/uploads   RFP documents, read-only                               |
|                   /mnt/session/outputs   each step's form as JSON, draft files                  |
|                   /mnt/memory/...        cadocary-facts, doug-preferences (read-only)            |
|  vault:           bearer token for our MCP endpoint (agents never see it)                       |
|  cap:             hard dollar limit per session                                                 |
+-------------------------------------------------------------------------------------------------+

 DATA STORES
   Firestore      rfps, runs, step forms, checks, decisions, approvals (with packet fingerprint)
   Files API      RFP documents in; session outputs out (copy them: they vanish if a session is deleted)
   Memory stores  written only by our code, from Doug's approved facts and decisions
   Cadocary server (after demo): bidkit as an MCP server. Portal logins, FGA, PDF assembly.
                  Logins never leave it.

 SENDING
   No agent has an email, upload, submit or portal tool. When Doug approves, code freezes the
   packet, builds the submission bundle and checklist, and Doug sends it from his own email
   or portal.
```

### How a day runs, step by step

1. **5:00 AM Pacific.** A scheduler calls the backend's daily job.
2. **Sourcing (code).** Runs the saved searches, keeps software, Washington, $25,000 and up (when stated), at least 7 days left. Checks that all attachments downloaded and contain text. Removes duplicates. Parses every deadline with its time zone. Stores each new RFP as `new`.
3. **Launcher (code).** For each `new` RFP: claims it in one database transaction (so it can never start twice), uploads its documents, and starts a session on the operator agent (pinned version) with the documents mounted, both memory stores read-only, the vault, a dollar cap, and the RFP id in metadata. The starting message gives the RFP id, the file paths, and the facts code already worked out (deadlines, hard stops, submission method). Status becomes `running`.
4. **Operator.** Sends the Qualifier first. If the answer is "pass", it files a short pass packet and stops. Otherwise: Researcher, then a fresh Checker on the research (at most two revision rounds), then Drafter, then a fresh Checker on the draft (at most two rounds), then the final packet.
5. **Record tools (code).** Every step ends with a `record_*` call. Code checks the form, the order, the citations and the math. It answers either "accepted" or a numbered list of problems the agent must fix. Accepted forms go to Firestore, so the app updates the moment a step finishes.
6. **Watchers (code).** Webhooks plus a 10-minute sweep keep each RFP's status true: finished, failed at a step, paused at its cap, stuck, or out of time.
7. **App.** Doug sees a queue ordered by deadline and expected worth, the live view of any run, and finished packets.
8. **Doug decides.** "Permission to send" freezes that exact packet (a fingerprint of the files). Code builds the submission bundle and a checklist matched to the submission method. Doug sends. "Pass" asks for a one-line reason, which goes into his preferences.

### The five agents

All on Opus 5.5 with effort set to "high". `bash` is off for every agent: nothing needs it once rendering and data pulls are tools, and it removes the biggest risk surface.

| Agent | Job | Built-in tools | Our MCP tools | Skill |
|---|---|---|---|---|
| Operator | Decide the next step, delegate, assemble the packet | read, glob, grep, write | `get_rfp_status`, `record_packet` | delegate |
| Qualifier | Read the RFP; requirements, scoring, fit, competitiveness | read, glob, grep, write | `get_hard_stops`, `lookup_fact`, `record_qualification` | qualify |
| Researcher | Contract worth, prior awards, incumbent, price | read, write, web_search, web_fetch | `search_federal_awards` (USAspending), `record_research` | research and pricing |
| Checker | Adversarial check of research, then of the draft | read, grep, web_fetch | `verify_citations`, `record_check` | check |
| Drafter | Write the proposal inside the page limit | read, write, edit | `lookup_fact`, `render_draft`, `record_draft` | draft |

Operator settings: subagents on with exactly these four agents pinned by version; inline agents off; workflows off; no advisor.

Permissions: set every tool to `always_allow`, explicitly. Not "ask" (no one is there to answer at 5 AM) and not "auto" (it pauses for a person when unsure, which is the same hang). This is safe only because no dangerous tool exists anywhere in the system.

Networking: the Researcher needs the open web, and the platform's `limited` mode also limits web search and fetch. Use `unrestricted` with `bash` off everywhere, so the only ways out are web search, web fetch (read-only) and our MCP endpoint. Revisit after the demo with a fixed host list if research works within one.

### Why one session per RFP

| | One session per RFP, started by our code (recommended) | One session per day, from a scheduled deployment (plan) |
|---|---|---|
| Hands the agent today's RFPs | Mounted at start, with code-parsed facts | Agent must fetch them through a tool |
| Spending cap | Per RFP | One cap shared by every RFP that day |
| One RFP goes wrong | Only that RFP is affected | Can stall or exhaust the whole day |
| 25-thread limit | About 5 to 7 threads per RFP | 10 RFPs times 5 steps passes 25 |
| Live view in the app | One feed per RFP card | One mixed feed to untangle |
| Retry a failed step | Start a new session at that step with the earlier forms | Rerun the whole day or hand-steer |

---

## Data flow: what each step passes to the next

Agents share files, not memory of each other's conversations. So every hand-off is a file in `/mnt/session/outputs/` plus a `record_*` call that files the same content with code. The operator passes paths, never retyped summaries.

| From | To | What is passed |
|---|---|---|
| Sourcing (code) | Launcher (code) | RFP record: ids, buyer, documents with fingerprints, parsed deadlines with quotes, submission method, hard stops found by code |
| Launcher | Operator | Starting message: RFP id, document paths, the RFP record, paths to the facts library and Doug's preferences |
| Operator | Qualifier | RFP paths, hard stops, facts and preferences paths, "file with `record_qualification`" |
| Qualifier | Operator | Qualification form (below) |
| Operator | Researcher | Qualification form path: requirements, scope, buyer, incumbent hints, evaluation method |
| Researcher | Operator | Research form (below) |
| Operator | Checker | Research form path, RFP paths, the round number |
| Checker | Operator | Check form: pass, revise or block, with a numbered issue list |
| Operator | Drafter | Qualification and accepted research form paths, facts library, template, page limit and what counts toward it |
| Drafter | Operator | Draft form (below) plus draft files |
| Operator | Checker | Draft form path, requirement list, RFP paths |
| Operator | Code, then Doug | Packet form: the one screen Doug reads |

### Shared citation shape

Every claim in every form carries one of these. Code checks each one.

```yaml
cite_rfp:  {doc: "lakewood.pdf", page: 3, quote: "exact words from that page"}
cite_web:  {url: "https://...", quote: "exact words from that page", retrieved_at: "ISO time"}
```

### Qualification form (`record_qualification`)

```yaml
rfp_id: "..."
decision: pursue | pass | needs_doug        # needs_doug only for a question code and agent cannot settle
hard_stops: [{rule, cite_rfp}]              # code fills this first; the agent may add, never remove
requirements:                               # the compliance list everything later is checked against
  - {id: R1, text, kind: mandatory | scored | format | form | submission, cite_rfp}
evaluation:
  method: lowest_price | best_value | qualifications_only | unknown
  criteria: [{name, weight_points_or_percent, cite_rfp}]
deadlines_as_read:                          # compared with code's parse; any mismatch is flagged
  - {kind: questions | intent_to_submit | pre_proposal_meeting | proposal | other,
     as_written, mandatory: true | false, cite_rfp}
submission: {method: email | portal | paper | mixed, copies, separate_cost_volume: true | false,
             signatures_required: true | false, details, cite_rfp}
page_limit: {pages: number | null, what_counts, cite_rfp}
factors:                                    # each rating has a fixed set of words, plus evidence
  knockouts:             {rating: clear | at_risk | fails | unknown, evidence: [cite_rfp], note}
  incumbent:             {rating: none | weak | strong | unknown, name, evidence, note}
  past_performance:      {rating: strong | partial | none | unknown, fact_ids: [], note}
  evaluation_fit:        {rating: favors_us | neutral | against_us | unknown, note}
  price_competitiveness: {rating: likely | unclear | unlikely, note}
  competition_density:   {rating: low | medium | high | unknown, note}
questions_for_buyer: [{question, why_it_matters, due_as_written}]
unknowns: [string]
```

### Research form (`record_research`)

```yaml
value_estimate:
  low: number, likely: number, high: number          # US dollars
  basis: stated_in_rfp | budget_document | award_records | comparables | educated_guess
  confidence: high | medium | low
  # high   = stated by the buyer, or two or more independent award records agree within 25 percent
  # medium = one award record, or comparables that match on scope and buyer size
  # low    = anything else; the app shows it as a guess
  how_built: "two or three sentences"
comparables:
  - {buyer, title, awarded_on, awardee, amount, scope_match: strong | partial | weak,
     why_comparable, cite_web}
incumbent: {name: string | null, contract_amount, ends_on, cite_web}
likely_competitors: [{name, why, cite_web}]
price_recommendation:
  line_items: [{item, quantity, unit, rate, amount}]   # code recomputes every amount and the total
  total: number
  rationale: "how it compares to the comparables"
searches_run:                                           # code compares this to the actual tool calls
  - {category: federal_awards | state_awards | buyer_records | budget_docs | incumbent | competitors,
     where, query, results_found}
not_found: [{looked_for, where_looked}]                 # a first-class, expected answer
educated_guesses: [{claim, reasoning}]
```

Rule code enforces: every number is either backed by a `cite_web` or `cite_rfp`, or appears under `educated_guesses`. Nothing else is accepted.

### Check form (`record_check`)

```yaml
target: research | draft
round: 1 | 2
verdict: pass | revise | block                # block = stop and show Doug, do not keep fixing
issues: [{severity: fatal | major | minor, field, problem, evidence, fix}]
spot_checks: [{claim, source, confirmed: yes | no | unreachable}]
coverage_gaps: [category]                     # research categories not searched
```

### Draft form (`record_draft`)

```yaml
files: {proposal: "outputs/proposal.md", cost: "outputs/cost.md" | null, forms: ["..."]}
compliance_matrix:                            # one row for every requirement in the qualification form
  - {requirement_id: R1, section, page, status: met | partial | not_met | not_applicable, note}
page_count: number                            # from render_draft, never estimated by the agent
page_limit: number | null
cadocary_claims: [{text, fact_id}]            # every claim about Cadocary maps to the facts library
calls_for_doug:                               # "every call the agent made"
  - {topic: price | references | exceptions | questions | assumptions | staffing,
     choice_made, alternatives, why}
open_items: [string]                          # things only Doug can do: signatures, notary, forms
```

### Packet form (`record_packet`): the screen Doug reads

```yaml
headline: "You are a competitive applicant for X. Expected worth $Y (confidence Z). Permission to send?"
recommendation: send | pass
expected_worth: {low, likely, high, confidence, basis}
why_competitive: [three reasons, each with a source]
risks: [three risks, each with a source]
deadlines: [{kind, local_time, time_zone, days_left}]
calls_for_doug: [...]                         # copied from the draft form
checks: {research: pass | revise | block, draft: pass | revise | block, code_checks: [results]}
run_cost_usd: number                          # from the session's usage
```

The templates stay extensible the simple way: optional fields can be added; fixed word lists change only with a version number on the form, and old forms keep validating.

---

## What should be code and what should be agent judgment

| Code decides (no judgment needed) | Agent decides (judgment) | Code checks the agent |
|---|---|---|
| Which RFPs exist, duplicates, amendments | Whether Cadocary fits and can win | Every RFP quote is on the page cited |
| Filters: software, Washington, $25,000, 7 days | Incumbent strength, competition density | Every web quote is on the page cited (code re-fetches) |
| Deadline parsing, time zones, days left | Which past awards are truly comparable | Every number has a source or is labeled a guess |
| Hard stops (short list, D6) | Contract worth from the evidence | Searches claimed match searches actually run |
| Completeness: every attachment downloaded and readable | The price and its reasoning | Price math and totals |
| Price arithmetic from Doug's rate card | Which references and past projects to feature | Research covered the required categories |
| Rendering, page counting, format rules | Questions to ask the buyer | Every requirement appears in the compliance list |
| Step order and revision limits | Writing the proposal | Page count within the limit, with what counts |
| Spending cap, time limit, retries | When research is good enough to stop | Every claim about Cadocary maps to an approved fact |
| Building the submission bundle | | The agent's deadlines match code's deadlines |

On the plan's line "deterministic rules feed the agent's judgment but are not a hard pass or fail": that is right for soft factors, but some facts are knockouts no judgment can overrule. Keep a short hard-stop list in code (D6): proposal deadline already too close to finish, a mandatory meeting already missed, physical delivery that cannot happen in time, or an eligibility rule Cadocary cannot meet (Delaware's "dedicated onsite analyst within driving distance" is a real example). A hard stop always shows its quote, and Doug can override it.

---

## Failure modes

For each: what goes wrong, what the design does, what Doug sees, and how we test it. **CRITICAL** means: today there is no test, no handling, and it would fail silently.

### 1. No data found (CRITICAL as planned)
- **What goes wrong:** many city and county awards are not in any database. An agent under pressure to produce a number invents a comparable award or a source.
- **Design:** `not_found` and `educated_guess` are normal, accepted answers. Code refuses any number without a source unless it is labeled a guess. Code re-fetches every cited page and checks the quote. Confidence uses fixed words with written definitions, not a made-up percentage.
- **Doug sees:** "Worth: $40,000 to $90,000, educated guess, no prior awards found. Searched: federal awards, the buyer's council minutes, state contract lists." Shown in a different style from sourced numbers.
- **Test:** evaluation cases where no award record exists. Pass means zero invented sources. One invented source fails the whole release.

### 2. Lazy research (CRITICAL as planned)
- **What goes wrong:** the researcher runs two searches, finds nothing, and stops; or claims searches it never ran.
- **Design:** the research skill names required categories (federal awards, state awards, the buyer's own records such as council agendas and bid tabulations, budget documents, incumbent, competitors). Code counts the actual web and award-tool calls in the researcher's thread and compares them with `searches_run`. A missing category or a claimed-but-not-run search sends it back. The Checker, in a fresh thread, looks for what was not searched.
- **Doug sees:** a coverage line per bid ("6 of 6 source types searched") and, when short, why.
- **Test:** replay recorded research runs with categories removed; the record tool must return "revise".

### 3. Duplicate RFPs
- **What goes wrong:** the same solicitation appears on SAM.gov and a state portal, an amendment reposts it with new dates, it shows up again the next day, or two launches race (a retried webhook, a double click, the fall-back daylight-saving night running a schedule twice).
- **Design:** sourcing builds a key from buyer plus solicitation number, with a fallback of buyer plus title plus due date, plus a fingerprint of each document. Same key with new documents means "amended", not "new". The launcher claims an RFP inside one database transaction; a second claim fails. Record tools are safe to call twice.
- **Doug sees:** one card per solicitation, with "Amended on ..." when it changed.
- **Test:** unit tests for same number twice, cross-site duplicate, amendment, and two launches at once.

### 4. A subagent errors
- **What goes wrong:** a thread fails (MCP endpoint down, a model error, retries exhausted). The operator may not notice, or may quietly do the work itself.
- **Design:** the platform reports thread status changes and errors on the main stream. Code does not rely on the operator noticing: if a step's `record_*` never arrives and its thread has ended or failed, the watcher marks the RFP "failed at research" with the error. Retry starts a new session at that step with the earlier accepted forms, so finished work is not redone. Record tools only accept a step's form from the right step (no operator filing its own research).
- **Doug sees:** "Research failed: award search unreachable. Retry." Never a card that spins forever.
- **Test:** fake event lists with a terminated thread and no form; the watcher must mark the failure.

### 5. A run that never finishes (CRITICAL as planned)
- **What goes wrong, in order of likelihood:** a tool left at the MCP default of "ask a person" pauses forever; a custom tool waits for code that is not listening; the operator loops on revisions; the session pauses at its spending cap and nobody notices; our backend misses the final webhook (they can be dropped after three tries and arrive out of order), so the app says "running" forever.
- **Design:** no tool set to "ask"; no custom tools (D3); at most two revision rounds, enforced by the record tools; a time limit per RFP (3 hours to start) after which code interrupts the session and marks it "out of time". The 10-minute sweep fetches the real status of every `running` RFP instead of trusting webhooks. "Done" means "packet accepted by code", not "session went quiet".
- **Doug sees:** stuck, out of time, or paused at cap, with a one-click retry or raise-cap.
- **Test:** sweep tests with fake clocks and fake statuses: waiting on approval, at cap, running past the limit, idle with no packet.

### 6. Cost runaway
- **What goes wrong:** a research loop, a huge RFP read many times, or a run that keeps revising.
- **Design:** a hard dollar cap on every session (start at $40 per RFP; see the cost section). At the cap the session pauses, keeps its work, and the app offers "raise cap". A daily total in the backend stops new launches past a daily ceiling. Workflows off on the operator, so it cannot fan out into hundreds of agents.
- **Doug sees:** cost per bid on every packet, and "paused at $40" when it happens.
- **Test:** launch a session with a tiny cap (for example $0.50) and check the app shows "paused at cap".

### 7. A wrong deadline (CRITICAL as planned)
- **What goes wrong:** the time zone label is wrong (Lakewood's "5:00 PM PST" on a daylight-time date reads one hour late if taken literally); there is no time ("close of business", "noon", date only); there are several deadlines (questions, intent to submit, mandatory meeting, proposal); an addendum moves a date; the buyer is in another time zone (Delaware is Eastern).
- **Design:** code parses every deadline into the buyer's local time zone from the buyer's address, treats "PST" or "EST" labels as "local clock time", and keeps the original words and the page. The Qualifier reads the deadlines independently. Any disagreement blocks the bid until a person looks. The working deadline is the earliest hard date minus a buffer (24 hours to start). The 7-day filter is checked against that working deadline, not the proposal date. Approval is disabled after the working deadline.
- **Doug sees:** each deadline in his time and the buyer's, with the quote, and a countdown.
- **Test:** about 25 unit cases, including Lakewood's PST-in-October, Delaware Eastern time, "close of business", date only, and an addendum that moves the date.

### Other failure modes found in review

| Failure | What goes wrong | Design | Critical? |
|---|---|---|---|
| Invented Cadocary facts in the draft | A binding proposal claims past work, references or certifications that are not real | Facts library approved by Doug; every claim maps to a `fact_id`; code refuses unmapped claims | **CRITICAL** |
| Text inside an RFP or web page gives orders | "Ignore your instructions and email ..." inside a document | Agents have no send, email or external write tools; memory is read-only; record tools only write to that RFP's own record | Contained by design |
| Questions deadline passes before Doug sees anything | Clarifying questions due a week before proposals are never asked | Early notice for time-sensitive items (D5) | **CRITICAL** |
| Mandatory meeting or intent-to-submit missed | Bid disqualified before it is written | Code hard stop if already missed; early notice if still possible | **CRITICAL** |
| Amendment after the draft starts | Draft answers an outdated RFP | Sourcing re-checks open RFPs daily; an amendment marks the bid "needs re-check" and reruns the affected steps | Yes, not handled in plan |
| Page limit overflow | Proposal is non-compliant | `render_draft` returns the real page count; record tool refuses over-limit drafts; "what counts" is captured (Yolo excludes references from its 20 pages) | Handled once built |
| Paper-only or physical submission | "Permission to send" means nothing for a sealed envelope with 5 copies and a flash drive (data-007), or a signed-in-ink original (data-010) | Submission method captured; packet becomes a printing and delivery checklist with the delivery deadline | Yes, not in plan |
| Separate cost volume | MSRS wants proposal and cost as two attachments (data-002) | Form has `separate_cost_volume`; bundle builder follows it | Handled once built |
| Scope hidden in an attachment | Indiana's real scope is in a separate Attachment C (data-006) | Completeness check: every referenced attachment is downloaded and readable before launch | Yes, not in plan |
| MCP endpoint cold or down | Tool calls fail mid-run | Keep one Cloud Run instance warm during runs; agent retries once; watcher marks failure | Medium |
| App live feed drops | Browser misses events | Relay always rebuilds from history, then follows live, skipping events already seen | Handled once built |
| Approval of a changed packet | Doug approves version 1, a rerun changes it | Approval stores the packet fingerprint; any change voids the approval | Yes, not in plan |

---

## Section 2: Code quality (for code not yet written)

1. **One set of form definitions.** Write the six forms above as Pydantic models once. The MCP record tools validate against them, Firestore stores them, and the frontend's types are generated from them. The stack decision already says Pydantic defines Firestore shapes; extend that to the agent forms.
2. **One status machine for an RFP** (`new`, `running`, `failed_at_step`, `paused_at_cap`, `out_of_time`, `ready_for_doug`, `approved`, `passed`, `sent`), in one backend module, with every change logged with its reason. The app reads status; it never guesses from events.
3. **Translate events to plain words in one place**, in the backend relay ("Reading page 12 of the RFP", "Searching federal award records"), not scattered across React components.
4. **Agents, environment and skills live as files in the repo** with their ids recorded, and every session pins an agent version. A skill edit during the demo must not change a run already in progress.
5. **Record tools are safe to call twice** (same form, same result), because retries happen.
6. **The prototype's event names must match the real ones** (`agent.tool_use`, `agent.mcp_tool_use`, `session.thread_created`, `agent.thread_message_received`, `session.status_idle` with its stop reason). If the prototype invented its own shapes, budget time to adapt the screens.
7. **Repo rules apply to agent-facing code too:** no catch-all error handling in the record tools (each refusal names the field and the problem, so the agent can fix it), no leftover prints.

---

## Section 3: Tests

### Test diagram: every new code path and its test

```text
SOURCING
  saved search -> notices ................... replay 3 recorded SAM.gov responses
  filters (software, WA, $25k, 7 days) ...... table of 20 notices with expected keep or drop
  completeness (attachments, readable text) . missing attachment; scanned PDF with no text
  dedupe + amendment ........................ same number twice; cross-site copy; amendment v2
  deadline parse + time zone ................ ~25 cases: PST in October, Eastern buyer, "close of
                                              business", noon, date only, addendum moves date
LAUNCHER
  claim once ................................ two claims at once -> exactly one session
  create session (docs, cap, metadata) ...... one live run against the API with a small RFP
MCP RECORD TOOLS
  form validation ........................... valid; missing field; wrong word in a fixed list
  step order ................................ research before qualification -> refused
  revision limit ............................ third revision -> refused with message
  only the right step files its form ........ operator filing research -> refused
CODE CHECKS
  RFP quote on cited page ................... exact quote; paraphrase; wrong page
  web quote on cited page (re-fetch) ........ recorded pages; unreachable -> "unverified"
  numbers have a source or a guess label .... both cases
  claimed searches vs actual tool calls ..... claimed but not run -> revise
  research coverage ......................... missing category -> revise
  price math ................................ wrong line total; wrong grand total
  page count vs limit, what counts .......... rendered fixtures at, under, over the limit
  Cadocary claims map to facts .............. unmapped claim -> refused
  agent deadlines vs code deadlines ......... mismatch -> flagged
WATCHERS AND WEBHOOKS
  webhook signature, duplicates ............. bad signature refused; same event twice ignored
  waiting on approval ....................... flagged as stuck
  running past time limit ................... interrupted, marked out of time (fake clock)
  paused at cap ............................. marked paused, raise-cap works
  missed webhook ............................ sweep finds the real status
EVENT RELAY
  history then live, no duplicates .......... dropped connection mid-run
  subagent thread feeds ..................... research steps appear under the research step
APPROVAL AND SENDING
  approval stores packet fingerprint ........ change after approval voids it
  no agent can send ......................... scan every agent config: no tool whose name or
                                              description involves send, email, upload, submit
AGENT BEHAVIOR (evaluation, not unit tests)
  extraction, honesty, draft compliance ..... the evaluation set below
```

### The 100-RFP evaluation set

The plan uses the same 100 RFPs both to write the skills and to grade them. That grades the agent on its own homework. Split them.

**Split.** About 60 RFPs to build the skills (the "common / variable / rare but fatal" summary). About 40 held back, never shown while writing skills, used only for grading. Keep the five full RFPs already collected in the held-back group if possible, since they are well understood.

**Answer key.** On the 40 held-back RFPs, a person checks the fields where a mistake is fatal: every deadline with time zone, mandatory meetings and intent-to-submit, submission method and copies, page limit and what counts, knockout requirements. AI-filled sheets without a human check are a second opinion, not an answer key.

**Add to the extraction sheet.** The plan's field list is missing several things the collection notes already show matter: question deadline, intent-to-submit, mandatory pre-proposal meeting, separate cost volume, physical copies and signatures, bonds, set-asides and preference points, award method (lowest price vs best value vs interviews and BAFO), and referenced attachments.

**What to measure, with starting bars to tune after the first run:**

| What | How | Starting bar |
|---|---|---|
| Deadlines | Code plus agent vs answer key, including time zone | Zero silent wrong deadlines. A flagged disagreement is acceptable; an unflagged wrong one fails the release |
| Fatal requirements found | Recall of knockouts and mandatory items vs answer key | 95 percent or better; a miss is the worst error |
| Citations real | Share of quotes found on the cited page | 98 percent or better |
| Invented sources | Sources that do not exist or do not say what is claimed | Zero |
| Honest "not found" | On cases with no findable award record, the agent says so | 100 percent |
| Worth estimate | On RFPs already awarded (public result known), hide the result and compare | Track error and whether "high confidence" is usually close; set a bar after the first ten |
| Qualification vs Doug | Doug labels 20 held-back RFPs "would bid / would not" from a one-paragraph summary | 80 percent agreement; track "agent said pursue, Doug would pass" separately, since that is wasted Doug time |
| Draft compliance | Every mandatory requirement in the compliance list, page limit met, every Cadocary claim mapped | 100 percent on all three |
| Cost and time per RFP | From session usage | Track; compare to the cap |
| Doug's minutes per bid | Time Doug spends on a packet, measured in the first real uses | The real goal; aim for under 20 minutes |

**How to measure "competitive" before any bid is won or lost.** Use RFPs that were already awarded. Many cities publish bid tabulations listing every bidder and price. Hide the result, run the pipeline, and compare: the predicted worth against the actual award, predicted competition against the actual number of bidders, and whether the predicted incumbent advantage held. Later, every real bid's result (won, lost, winner, winning price) goes back into the set.

**Baseline and regressions.** Run version 1 of the skills on the held-back set and save every result. Every skill change reruns the set. A change ships only if no "fails the release" bar gets worse.

**Cost of evaluating.** A full pipeline run on all 40 held-back RFPs is roughly $500 at the estimate below. Run extraction and qualification on all 40, and the full pipeline on 10.

**The extraction sheet itself does not need agents.** "One Claude per RFP fills the same sheet" is one plain API call per RFP with the sheet as a fixed output format. A short script is simpler and faster than 100 agent sessions. Code then checks every quote on its page.

---

## Section 4: Performance and cost

**Rough cost per RFP (estimate; replace with measured numbers after ten runs).** Opus 5.5 is $4 per million input tokens, $20 per million output tokens, $0.20 per million for cached input; web searches are $10 per thousand; session running time is $0.08 per hour. Assume a full run reads about 3 million input tokens across the five agents (half cached) and writes about 300,000: about $6 + $0.30 + $6, plus up to $1.50 of searches and a few cents of running time. **About $14 per full bid. About $2 for an RFP the Qualifier passes on.** A $40 cap gives roughly three times headroom.

**Per day.** Ten matching RFPs with three going all the way: about $55. Doug says cost does not worry him; the cap is there to stop loops, not to save pennies.

**Size of the reading.** The largest collected RFP (Delaware) is about 136,000 characters, roughly 34,000 tokens. Each agent can read it in full; the 1-million-token context is not a constraint. Tool outputs over 100,000 characters are saved to a file automatically.

**Time.** Expect 20 to 90 minutes per full bid. That is fine for a 5 AM run. It is not fine for a live demo (D13).

**Limits that matter.** 25 child threads per session (one session per RFP uses 5 to 7). Session creation is limited to 300 per minute (not a concern). Cloud Run requests last at most 60 minutes, so the browser relay must reconnect; and the MCP endpoint should keep one warm instance while runs are active, or the first tool call of the day may time out.

---

## Security

**Credentials.**
- Anthropic API key: backend only, in Cloud Run secrets. Never in the frontend, a prompt, a memory store or the repo.
- SAM.gov key: backend only. Sourcing is code, so the agent never needs it.
- Portal logins (WEBS, Public Purchase): stay on Cadocary's server inside bidkit. The agent asks bidkit for documents; it never holds or sees a login.
- Our MCP endpoint: protected by a bearer token stored in a vault and matched by URL. Agents never see it.
- Webhooks: verify the signature on every delivery and ignore repeats.
- The web app shows confidential prices before submission. It needs a login (Doug and the team only) before real pricing goes in (D12). The plan does not mention this.

**Binding documents.**
- Every factual claim about Cadocary comes from the approved facts library, mapped by id and checked by code.
- Price comes from code using Doug's rate card and the agent's quantities, not from free text.
- References are listed only if the facts library marks them as "permission given".
- Approval is tied to a fingerprint of the exact files Doug read. Any change voids it.
- Signatures, notarization and certifications are open items for Doug, never filled by the agent.

**Never auto-sending.**
- No agent has a send, email, upload, submit or portal tool. This is a property of the configuration, so it is tested by scanning the agent files (Section 3).
- bidkit's portal upload functions are never exposed through MCP.
- The Gmail and Drive gap in the plan is a feature here: keep it that way.
- After approval, code builds the bundle; Doug presses send in his own email or portal. If Doug later wants a "send for me" button, it is code behind his click, never an agent tool.

**Untrusted text.** RFPs and web pages are written by strangers. With no outbound tools, read-only memory, and record tools that only write to the RFP being worked on, a hostile document can at worst spoil its own bid's analysis, which the checks and Doug's review catch.

**Data.** Managed Agents is not covered by zero data retention or a HIPAA agreement. That is fine for public RFPs and Cadocary's own bid content. Never send DocketBot or ClientCheck client data (defendants, court records) through this system.

---

## Missing steps in the loop

1. **Questions to the buyer have their own, earlier deadline.** Lakewood: questions October 18, proposals October 25. The agent drafts the questions early, and Doug gets one short notice to send them (D5).
2. **Mandatory pre-proposal meetings and intent-to-submit notices** (Delaware has both). Hard stop if missed; early notice if still possible.
3. **Registrations.** Federal bids need an active SAM.gov registration; state and city portals need vendor registration. Code checks Cadocary's registration status and expiry before launch.
4. **Amendments and addenda** between start and submission. Sourcing re-checks every open RFP daily and reruns the affected steps.
5. **Required forms and attachments**: the buyer's own forms, insurance certificate, W-9, non-collusion affidavit, bonds. The Qualifier lists them as requirements of kind `form`; the packet lists which are filled and which need Doug.
6. **Submission mechanics**: email, portal, or physical delivery with copies, a flash drive, and an ink signature. The bundle and checklist follow the method.
7. **A facts library to draft from**: past performance write-ups, references with permission, résumés, certifications, insurance, rate card, boilerplate. Without it the drafter has nothing true to say. This is the largest missing input and it needs Doug for about an hour.
8. **Notifying Doug** that a packet is ready (email or text from the backend). The plan has an app but no way to tell him to open it.
9. **After sending**: confirmation of receipt, then the result (won, lost, winner, winning price). Results feed the evaluation set and Doug's preferences.
10. **Learning from "pass"**: Doug's one-line reason goes into his preferences (written by code), so the Qualifier stops proposing what he always declines.
11. **Retry from a failed step**, reusing accepted forms, instead of starting over.

---

## Decisions for the team

Each has a recommendation and the reason. The team decides.

**D1. Scope for today.**
Recommendation: build the demo path only (one real RFP end to end, live in the app, with code checks catching something, plus SAM.gov sourcing running). Why: there is no API key yet and the full plan is several days of work. Alternative: the full plan, which risks having nothing working at 7:30.

**D2. One session per RFP, or one per day.**
Recommendation: one session per RFP, started by the backend after sourcing. Why: a deployment cannot pass in today's RFP, one session per RFP gives each bid its own cap, feed and failure, and it stays far below the 25-thread limit. Alternatives: (B) the plan's single daily session from a scheduled deployment, with the agent fetching RFPs through a tool; (C) a deployment that fires every 30 minutes and claims one RFP per run, which keeps the platform scheduler but adds idle runs. For the demo, the deployment's "run now" button can still be shown.

**D3. How our tools reach the agent.**
Recommendation: an MCP endpoint on our backend, with every tool set to always allow. Why: the MCP server answers tool calls directly, so unattended runs never wait on our code. Alternative: custom tools, which wait until our code answers, so the backend must catch every call through webhooks even at 5 AM.

**D4. Who sends.**
Recommendation: Doug sends, from his own email or portal, using the bundle and checklist code builds. Why: the bid is legally binding, physical submissions exist, and it removes the most dangerous capability entirely. Alternative later: a code-only "send" button behind Doug's click, tied to the packet fingerprint. Never: an agent tool.

**D5. One early touch for time-sensitive items.**
Recommendation: allow one short notice before the final packet, only for questions to the buyer, mandatory meetings and intent-to-submit, and only when a date would otherwise be missed. Why: these deadlines come before the proposal deadline and missing them loses the bid or the chance to ask. Alternative: strictly one touch at the end, which matches Doug's words but loses some bids.

**D6. Hard stops in code.**
Recommendation: a short list of code hard stops (deadline too close to finish, mandatory meeting missed, physical delivery impossible in time, an eligibility rule Cadocary cannot meet), each with its quote and a Doug override. Everything else stays soft. Why: no amount of judgment makes a missed mandatory meeting un-missed, and code is cheaper and more reliable than an agent rediscovering it. Alternative: the plan's all-soft rules.

**D7. Who checks the research and the draft.**
Recommendation: a separate Checker agent, spawned fresh each time with an adversarial skill, plus the code checks. Why: the plan reuses the Qualifier, and a follow-up to the same thread keeps its earlier opinions, so it is not independent; the code checks are the part that cannot share the agent's blind spots. Alternatives: reuse the Qualifier's thread (plan); Codex, which is not on this platform; Outcomes' built-in grader, which is a good later addition for the draft.

**D8. Sourcing for the demo.**
Recommendation: SAM.gov live, plus two or three Washington RFPs preloaded for the end-to-end demo. Why: SAM.gov has a public API and is quick to wire, but it is federal, while Doug's market (Washington cities and counties, jails, public defense) is mostly on WEBS, Public Purchase, FGA and city sites. Say this plainly in the demo. Alternative: WEBS and FGA through bidkit today, which depends on wrapping bidkit as MCP first.

**D9. Memory.**
Recommendation: two memory stores, both read-only to agents; only code writes them, from Doug's approved facts and decisions. Why: a store the agent can write is a store a hostile RFP can write into, and later bids would trust it. Alternative: agent-writable memory, which learns faster and is harder to trust.

**D10. Evaluation split and answer key.**
Recommendation: 60 RFPs to write skills, 40 held back for grading, with a person checking deadlines and fatal requirements on the 40. Why: grading on the same RFPs used to write the skills overstates quality. Alternative: the plan's reuse of all 100.

**D11. Cap and time limit per RFP.**
Recommendation: $40 and 3 hours per RFP to start, plus a daily ceiling, reviewed after ten runs. Why: about three times the estimated cost of a full bid, and long enough for thorough research. Alternative: no cap, which is how loops become surprises.

**D12. App login.**
Recommendation: restrict the app to Doug and the team before real pricing goes in. Why: unsubmitted prices are confidential. Alternative: open URL for the demo with fake prices only.

**D13. The demo itself.**
Recommendation: start a full real run by 4 PM, record its event history, replay it at 7:30, and start one short live run (qualification only) on stage. Why: a full run can take an hour, and the stored event history makes the replay exact, not a mock. Alternative: everything live, which risks waiting on stage.

**D14. Rendering and page count.**
Recommendation: code renders the draft and counts pages (bidkit's PDF assembly, or a backend renderer), exposed as `render_draft`. Why: page limits depend on the real layout, and an agent's estimate is a guess. Alternative: the agent estimates length, which will overflow on long RFPs.

---

## NOT in scope (today)

- Any sending, uploading or portal submission by the system.
- WEBS, Public Purchase, FGA and the bid inbox as live sources (after bidkit is wrapped as MCP).
- Gmail and Drive.
- Codex or any non-Claude second opinion.
- The full 100-RFP evaluation run (start the answer key; run 10 to 40).
- Memory written by agents.
- Win and loss tracking (design the field now, fill it later).
- Multiple users or businesses.

## TODO for today, in order

| # | What | Who (lane) | Depends on |
|---|---|---|---|
| 0 | Get the Anthropic API key and confirm Managed Agents and memory stores are enabled on it | anyone, now | nothing |
| 1 | Freeze the six forms as Pydantic models (30 minutes, together) | all | nothing |
| 2 | Agent, environment and skill files; upload skills v0; pin versions | A | 0, 1 |
| 3 | MCP endpoint with record tools (validation, order, revision limit) and `render_draft` | A | 1 |
| 4 | Launcher for one RFP: upload docs, start session with cap, metadata, vault | A | 2, 3 |
| 5 | Code checks: RFP quote on page, web quote re-fetch, numbers-have-sources, price math, page count | B | 1 |
| 6 | Deadline parser with time zones and its ~25 test cases | B | nothing |
| 7 | SAM.gov saved search, filters, completeness, dedupe, store | B (teammates already on it) | 6 |
| 8 | Event relay (history then live, thread feeds) and plain-language labels | C | 0 |
| 9 | Wire the prototype to the relay and to the packet form | C | 1, 8 |
| 10 | Facts library: one hour with Doug; load into a read-only memory store | D (with Doug) | 0 |
| 11 | Answer key for 10 held-back RFPs (deadlines, fatal requirements) | D | nothing |
| 12 | Full real run on the demo RFP by 4 PM; record it | A | 2 to 5, 10 |
| 13 | Watcher sweep (stuck, out of time, at cap) | A or B | 4 |

## Parallel lanes

- **Lane A, platform:** agents, MCP endpoint, launcher, watcher.
- **Lane B, code checks and sourcing:** checks, deadline parser, SAM.gov.
- **Lane C, app:** relay and screens.
- **Lane D, Doug and evaluation:** facts library, answer key, skills content.

Step 1 (the forms) is the contract between all four lanes; do it first, together. Lanes A and C touch different folders (`backend/` and `frontend/`), so they will not collide. Lane B's checks are called from Lane A's record tools; agree on function names in step 1.

## Outside voice

Skipped. The method's independent second opinion runs an external command, which this review was not allowed to do. The code checks recommended above are the independent check that matters most for this product.

---

## Completion summary

- Step 0, Scope Challenge: scope reduced for today (D1); the full plan stands as the next sprint.
- Architecture review: 9 issues (session shape, deployment cannot pass today's RFP, tools as MCP not custom tools, permission defaults that hang, thread feeds for the live view, operator workflow and inline-agent defaults, skills loading from the team repo, checker independence, unrestricted networking with bash off).
- Code quality review: 7 points (one set of forms, one status machine, one event translator, pinned agent versions, safe-to-repeat tools, real event names in the prototype, specific refusals).
- Test review: diagram produced; 7 gaps (no held-out set, no human answer key, missing extraction fields, no deadline test cases, no honesty cases, no "no send tool" check, no stuck-run tests).
- Performance review: 4 points (cost estimate and cap, run time vs demo, Cloud Run request limit for the relay, warm MCP instance).
- NOT in scope: written.
- What already exists: written.
- TODO items: 14 proposed.
- Failure modes: 7 critical gaps flagged (no data found, lazy research, never-finishing runs, wrong deadline, invented Cadocary facts, questions deadline, mandatory meetings).
- Outside voice: skipped.
- Parallelization: 4 lanes.
- Lake score: 12 of 14 recommendations chose the complete option; D1 and D8 deliberately trade completeness for the 7:30 PM demo.
- Durable learnings: none logged (logging was out of bounds for this review).

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|---|---|---|---|---|---|
| CEO Review | `/plan-ceo-review` | Scope and strategy | 0 | not part of this review | n/a |
| Codex Review | `/codex review` | Independent second opinion | 0 | skipped (no external commands) | n/a |
| Eng Review | `/plan-eng-review` | Architecture and tests (required) | 1 | ISSUES_OPEN | 27 findings, 7 critical gaps, 14 decisions |
| Design Review | `/plan-design-review` | UI and UX gaps | 0 | not run | n/a |

**VERDICT:** Build it, with changes. The plan is sound in spirit and fits Managed Agents, but before agent code is written the team should adopt one session per RFP, record tools checked by code, no send capability anywhere, explicit tool permissions with a stuck-run watcher, and code-owned deadlines. Get the API key first.

**UNRESOLVED DECISIONS:**
- D1 Scope for today (recommend: demo path only)
- D2 One session per RFP or one per day (recommend: one per RFP, started by the backend)
- D3 How tools reach the agent (recommend: MCP endpoint on the backend, always allow)
- D4 Who sends (recommend: Doug sends from his own email or portal)
- D5 One early touch for time-sensitive items (recommend: yes, only when a date would be missed)
- D6 Hard stops in code (recommend: a short list, with quotes and a Doug override)
- D7 Who checks (recommend: fresh Checker agent plus code checks)
- D8 Sourcing for the demo (recommend: SAM.gov live plus preloaded Washington RFPs)
- D9 Memory (recommend: read-only to agents, written by code)
- D10 Evaluation split (recommend: 60 to build, 40 held back with a human answer key)
- D11 Cap and time limit (recommend: $40 and 3 hours per RFP to start)
- D12 App login (recommend: Doug and team only before real pricing)
- D13 The demo (recommend: recorded full run replayed, plus a short live run)
- D14 Rendering and page count (recommend: code renders and counts)
