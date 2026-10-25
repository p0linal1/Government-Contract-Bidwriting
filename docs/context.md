# Project context

Everything the team learned on October 25, 2026, written down as of 1:00 PM so anyone can pick up the work. It comes from interviews with Doug, a mentor session, a clickable prototype, and three reviews of the plan. When this page and Doug disagree, Doug is right. Update this page when a decision gets made.

## The short version

- **Customer:** Doug, owner of Cadocary LLC, a small Washington software company that sells legal and justice software to government.
- **What he wants:** an agent that finds RFPs, decides whether Cadocary can win, works out what the contract is worth, and writes the whole bid. It then asks him one question at the end: "You are a competitive applicant, here is your application, and this is how much money I expect it to be worth. Permission to send?"
- **Today's deadlines:** the Impact Lab starter kit says the repo link and demo recording are due at 5:30 PM (confirm with the organizers). Demos are at 7:30 PM.
- **What the reviews said:** the idea is right, but the plan is too big for tonight. Build one real Washington bid from start to finish through the real agent. Have code check every source, and keep the send button in Doug's hands.
- **First tasks:** build Doug's facts sheet (`docs/fact-sheet.md`) and test the research step on three past awards Doug already knows the price of. The Anthropic API key is done (see "What exists and where").

## The business

Cadocary LLC is based in Washington and sells to public defenders, courts, jails, counties, and cities. Doug is currently bidding on a jail software contract. The website is cadocary.com.

| Product | What it does (from Doug) |
| --- | --- |
| DocketBot | Back-office tools for Washington public defenders: intake, conflicts, court dates, caseloads |
| ClientCheck | Watches the state court records system for new charges against clients |
| SpendLogic | Builds procurement compliance documents for federal contractors from templates |
| PURLPal | Answers questions over large document sets (Medicare plan documents), kept current by a data pipeline |
| Hotels4Truckers | Web and mobile booking platform for hotels with truck parking |

**Bids Doug wants:** software and IT work in Washington, $1 million to $5 million, with at least 7 days to respond. Custom software contracts suit Cadocary best. $5 million is a hard limit. Never military applications. Cadocary uses offshore developers, so contracts that allow them are better. (Updated Oct 25 afternoon; replaces "$25,000 and up" from the morning interview.)

## What Doug said, in his words

- Finding RFPs, researching them, and writing bids are three jobs he is in the loop on today. He wants out of all three.
- A paid service already sends him "FGA" bid breakdowns. "What this has created is a chore." He wants the bid written, not another breakdown. (Nobody has confirmed what FGA stands for yet. Ask him.)
- "I want artificial intelligence, not artificial asking if I'm right."
- "If it's done twenty minutes of work and now it's asking me a question, that's not going to be good for me. But if it's done eight hours, getting all the way to the end, and then it's just the final 'am I completely full of shit here', then it's worth it for me to read all of that."
- "There's no downside to failure. There's incredible upside to success. The limiting factor is how much time you're asking of the user."
- Token cost does not worry him. A sent bid is legally binding, so he does read the final bid before sending.
- "I think the scripts I wrote are trying to be skills." (About bidkit, below.)

## Doug's decisions

- **Autopilot.** The agent finds, researches, qualifies, and drafts on its own. Doug reviews a finished bid once. He floated a lighter version where he picks which researched bids to draft. The team leaned toward full autopilot.
- **The agent makes the small calls itself.** It doesn't stop to ask about questions for the buyer, references, and similar things. It lists them for him at the end.
- **Research must answer two things.** Is Cadocary a competitive bidder, and why? The "why" feeds the draft. And what is the contract worth? Many RFPs leave the value out.
- **Pricing comes from research on comparable past contracts.**
- **Preload the agent with Cadocary's website, past projects, and everyone's resume.**
- **He wants a clean web app, not email.** Found RFPs go on the left, each showing whether it is being researched or drafted, and a bid surfaces when it is complete. Email can't easily carry approve buttons.
- **He wants a ranked list of the best bids.**
- **Rejected drafts cost nothing,** because he simply won't send them.

## bidkit: Doug's existing pipeline

Doug already wrote a Python pipeline he calls bidkit. It is not in this repo. It does the following:

- polls a mail inbox
- runs an FGA search
- scores and sorts bids
- downloads from portals using Playwright with saved logins for WEBS and Public Purchase
- pulls facts out of each RFP, each with its source snippet
- makes calendar files
- runs five pass/fail gates: intake, value, pricing, fit, and go/no-go
- assembles the PDF

The plan is to turn these scripts into tools the agent can call. They would likely run as a server Cadocary hosts, so the portal logins never leave Cadocary. Ask Doug before putting any of bidkit in this repo.

## The plan the team agreed on

This comes from the whiteboard and the mentor session.

1. **Sourcing.** Plain code with no agent. Saved searches run on a schedule and keep only complete RFPs. Filters, completeness checks, and time zones belong here. This repo is that step for SAM.gov.
2. **Qualifying.** The agent decides whether Cadocary is qualified, competitive, and a match for Doug's preferences. Rules feed its judgment but are not a hard pass or fail. Its factors:
   - knockout must-haves (missing any one kills the bid)
   - how strong the incumbent is
   - how relevant Cadocary's past work is
   - how the buyer scores bids
   - how competitive the price is
   - how many competitors there are
3. **Research.** The agent works out what the contract is worth and, most importantly, finds past awards for comparable work. It pulls data with code wherever possible. It must report its confidence, say when data is missing, and label educated guesses. The mentor's warning: "Claude will do deep research and lie to you, especially if it can't find anything."
4. **Checking.** The plan has the qualifying agent re-check the research, the eligibility, and later the draft, in a loop back through the operator. The reviews changed this; see "What the reviews found".
5. **Drafting.** The agent writes the whole proposal from a template. It builds on the reasons Cadocary is competitive and stays inside the page limit.
6. **Doug reviews.** He sees why the bid is competitive, its expected worth with sources and confidence, the draft page by page, and every call the agent made. Then he gives permission to send, or passes.

How it is built:

- **The agent.** One lead agent ("operator") on Anthropic Managed Agents, running in Anthropic's cloud, delegates to helper agents for qualifying, research, checking, and drafting.
- **Skills.** Markdown instructions carry the know-how: how to delegate, how to qualify, what to research (including pricing), and how to draft. They are the hardest part to get right, and Doug never sees them.
- **Fixed output formats.** Agent outputs use fixed formats so code can check them.
- **About 100 real RFPs, studied first.** One Claude per RFP fills the same sheet: scope, must-haves, scoring, budget clues, incumbent, certifications, insurance, references, format, page limits, deadlines, and how to submit. The results are sorted into three groups:
  - common items, which become a checklist
  - variable items, which are things to look for
  - rare but fatal items, which become warnings

  That becomes the first draft of the skills. The same RFPs then serve as a test set, so changes never make the agent worse.
- **Plan reviews.** The mentor recommended GStack (Garry Tan) or Superpowers. We used GStack's review methods (below).

## How this repo fits

This repo is step 1 (sourcing) for federal work. It pulls SAM.gov, drops what you can't bid on, and has a small agent rank the rest against `profile.json`. Its design already matches what the reviews ask for: scripts do every fetch and file write, the agent only makes the judgment call, and private profiles stay out of git.

One open question: SAM.gov lists federal contracts, while most of Doug's buyers are Washington cities and counties. Those buyers post on WEBS (the state's bid site), Public Purchase, their own websites, and through FGA. Lakewood, the RFP used in the prototype, is a city bid that would not appear on SAM.gov. The reviews recommend hand-loading two or three Washington RFPs for tonight's demo and adding the Washington sources through bidkit next.

## What the reviews found

The team ran three reviews on the plan using GStack's office hours, CEO review, and engineering review methods. GStack itself was not installed. The full reports are in `docs/reviews/`, and the plan they reviewed is `docs/reviews/plan.md`. Sheffield also has a shareable summary page with a diagram of the loop.

**Verdict:** all three say build it, with changes.

- **Office hours:** the need is real and the demand is proven. Doug pays for a service and wrote his own pipeline. Nothing he has writes the bid or estimates what it's worth.
- **CEO:** writing is the easy part. The hard part is backing up "competitive" and "how much money" with real past awards.
- **Engineering:** run one agent session per RFP, with code checking every step, and give no agent any way to send.

**The riskiest assumption:** that research can find real, sourced past awards and prices for Washington city and county justice software. Test it with three awards Doug already knows. If it misses, the demo says "worth $X to $Y, low confidence" instead of one number.

**Steps the plan is missing:**

| Step | What to add |
| --- | --- |
| Find RFPs | Catch changes the buyer posts after the RFP goes up (addenda). Drop duplicates found on two sites. Tell a quiet day apart from a broken site. |
| Qualify | Hard stops checked by code (deadline too close, mandatory meeting missed, required license missing). Catch the earlier dates: buyer question deadlines, mandatory pre-bid meetings, intent-to-submit. Add jail and court rules: CJIS (the FBI's security rules for criminal justice data), background checks, insurance levels. |
| Research | Every number carries a link and the exact quote. "Nothing found" is a normal, accepted answer, and guesses are labeled. |
| Check | Code confirms each quote is really in its source. A separate checker that starts fresh, not the agent that did the work. At most two rounds of fixes, then stop with "no-go, could not verify". |
| Draft | Claims only from Doug's approved facts sheet, prices only from his price list. Required forms included. Code measures the page count. Flag contract terms Doug might object to. |
| Check the draft | Every requirement in the RFP mapped to a page. Page limit met. Every addendum acknowledged. |
| Doug reviews | A text or email telling him a bid is ready. Three buttons: Send, Fix this, or Pass with a one-line reason. A deadline countdown with one reminder. |
| Send (new) | No agent can send. Doug submits from his own email or portal. Re-check for late changes, submit hours early, and save the receipt. |
| Track the result (new) | Record who won and the winning price. Feed it back into qualifying and pricing. This is the only real way to measure "competitive". |

Real examples from our RFP collection:

- Lakewood's questions were due a week before proposals.
- Lakewood says "5:00 PM PST" on a date that was in daylight time, so taken literally the deadline is an hour late.
- Delaware required an intent-to-submit and a mandatory pre-proposal meeting.
- Some RFPs want paper copies with ink signatures, or the price in a separate file.

## Recommended architecture

This is from the engineering review. The agent shell is built and live (`agent/`): an operator with a delegation skill, plus four helpers (reader, qualifier, researcher, drafter) each with its own skill. The flow is: the reader fills an RFP sheet on the cheaper Sonnet model, the qualifier decides from the sheet, and only a pursue goes on to research and drafting. A read-and-qualify test on Oct 25 (the U.S. Senate wellbeing app RFP) worked end to end. The Reader downloaded all 7 files (114 pages) and wrote a sheet with 302 cited requirements and every deadline, including the question deadline. The Qualifier passed on it for sound reasons: an off-the-shelf wellbeing app, three similar references required, outside Doug's focus. It took 10 minutes and cost $2.67, an environment, and two memory stores (RFP Library and Cadocary Facts). It differs from the review in one way: the qualifier also does the checking, as in the team's original plan, instead of a separate checker agent. The operator pulls RFPs itself through Polina's hosted SAM.gov tool, with its access code kept in an Anthropic vault. A test on Oct 25 searched 95 notices, judged each one, and opened the 5 worth a look, for 82 cents. `agent/library.py` stores every open SAM.gov notice in the RFP Library, with its files in the Files API, and `agent/run.py` starts one session per RFP with its files attached. Not built yet: the record tools and the code checks.

- **One Managed Agents session per RFP,** started by our backend after sourcing. A scheduled deployment sends the same starting message every day, so it can't hand the agent "today's RFP". One session per RFP also gives each bid its own spending cap, live feed, and failure.
- **Agents:** an operator plus four helpers (qualifier, researcher, checker, drafter), all on Opus 5.5 with effort set to high. The checker starts fresh each time. On the operator, workflows and inline agents are turned off, so it can use only these four agents.
- **Record tools.** Every step ends by filing a fixed form through a tool we host as an MCP endpoint on our backend. Code checks the form, the step order, the citations, and the math. It answers "accepted" or a numbered list of problems. The forms are spelled out in `docs/reviews/engineering.md` under "Data flow".
- **Code checks:**
  - every RFP quote is on the page cited
  - every web quote is on its page (code re-fetches it)
  - every number has a source or a "guess" label
  - the searches the agent claims match the searches it actually ran
  - the price math adds up
  - the page count is under the limit
  - every claim about Cadocary maps to an approved fact
  - the agent's deadlines match the deadlines code parsed
- **Safety:**
  - Every tool is set to "always allow" explicitly. Anything set to "ask" waits forever when nobody is watching.
  - No agent has any send, email, upload, or portal tool, and bash is off.
  - Memory stores are read-only to agents, and only our code writes them.
  - Each session has a hard spending cap: $40 and 3 hours per RFP to start.
  - A watcher in our backend catches stuck runs.
- **Live view.** The app reads each helper agent's own event feed, not just the operator's, to show research as it happens.
- **Cost estimate:** about $14 for a full bid and about $2 for an RFP the qualifier turns down. Replace these with measured numbers after ten runs.

## Decisions waiting on the team

| # | Decision | Recommendation |
| --- | --- | --- |
| 1 | What the demo proves | One real Washington RFP through the real agent, start to finished bid, plus one it correctly turns down |
| 2 | Which RFP | Doug's real jail software bid if we have the documents, Lakewood if not |
| 3 | Where RFPs come from tonight | Load two or three Washington RFPs by hand. Run SAM.gov too, and say plainly that it covers federal work only |
| 4 | How many agents tonight | One session per RFP. Inside it, one agent plus a separate fresh checker. Split into four helpers next |
| 5 | Who checks the work | Code checks first, then a fresh checker agent. Drop Codex |
| 6 | What the agent may claim | Only what is on Doug's facts sheet, with prices built from his price list |
| 7 | Hard stops | A short list in code, each showing its quote, and Doug can override |
| 8 | One early notice | Allowed only when a buyer-question deadline, mandatory meeting, or intent-to-submit would otherwise be missed. Needs Doug's OK |
| 9 | Who sends | No agent ever sends. The agent prepares the packet and a checklist, and Doug submits |
| 10 | Doug's buttons | Send, Fix this, and Pass with a one-line reason |
| 11 | Doug's main screen | A "ready for you" message first, with the live agent view one click behind |
| 12 | How the demo runs | Start a full real run by 4 PM, record it, replay it at 7:30, and run one short live step on stage |
| 13 | The 100 RFPs | About 10 tonight to shape the skills. Later, set 40 aside as a test the skills are never written from |
| 14 | Spending cap | $40 and 3 hours per RFP |
| 15 | What goes in a public repo | No logins, prices, or Doug's private bids. Ship sample facts and public RFPs |

## Managed Agents in brief

The full reference is `docs/managed-agents.md`. The facts that matter most:

- **Beta.** Every request sends the header `anthropic-beta: managed-agents-2026-04-01`. Memory stores use `agent-memory-2026-07-22` instead.
- **Building blocks:**
  - Agent: model, system prompt, tools, skills, helper agents
  - Environment: the cloud sandbox
  - Session: one run
  - Events: everything the agent does, streamed live
  - Vaults: credentials
  - Memory stores, Skills, and Deployments (cron schedules)
- **Helper agents go one level deep,** with at most 25 at a time per session. They share the session's files, and each has its own event feed.
- **Tools.** The default for MCP tools is "always ask", which hangs an unattended run, so set permissions explicitly.
- **Cost:** $0.08 per hour of session time plus tokens, and web search is $10 per 1,000 searches.
- **Not covered by zero data retention or HIPAA.** Never send DocketBot or ClientCheck client data (defendants, court records) through it.

## What exists and where

| What | Where | Notes |
| --- | --- | --- |
| SAM.gov sourcing | This repo | Built by Alyssa and Polina |
| SAM.gov tool, hosted | AWS Lambda, run by Polina. Code and guide on the `sam-research-agent` branch (`cloud/AGENT-INTEGRATION.md`). Ask Polina for the web address, which is kept out of the repo on purpose | An online connector with two tools: `search_opportunities` (open notices by NAICS or PSC code, paged, nearest deadline first) and `get_notice` (full details, with attachment links that download directly). The bid agent's access code is in Secret Manager as `sam-tool-token` (project `finchat-495622`). A direct test on Oct 25 returned 99 open notices for Cadocary's codes in the next 60 days, and a notice's files downloaded fine. Coverage check the same day: it returns every match for the codes it is given (95 due within 30 days, 112 with any future deadline, 134 counting notices with no deadline). But one of Cadocary's registered codes, 511210, was retired in 2022 and matches nothing. Its replacement 513210, plus 541512 (computer systems design), finds 36 more notices |
| Clickable prototype | `prototype/` in this repo (pull request #2). Double-click `prototype/click-through.html` | Simulates the full autopilot flow on the real Lakewood RFP, with the live agent feed, sources on every claim, a morning brief, and a page-by-page proposal review. React and Vite; see `prototype/README.md` |
| Demo video (46 seconds) | Sheffield's laptop: `cadocary-demo-video/drafts/draft.mp4` | The problem, the solution, and a click-through of the prototype inside a laptop frame, narrated by ElevenLabs (Brian, eleven_v4; key in Secret Manager as `elevenlabs-api-key`). To rebuild after screen or script changes: `python3 capture.py && python3 voice.py --elevenlabs && ./build.sh` in that folder |
| Plan review page | A Claude doc Sheffield can share | Verdict, loop diagram, and the 15 decisions with a column to mark them |
| RFP collection | Sheffield's laptop (`RFP corpus`) | 80 public RFP PDFs, 78 cataloged by type (legal, AI, portals, data, Washington) |
| Impact Lab starter repo | Sheffield's laptop | Claude Code commands and a FastAPI and React shell. Not used for now |
| Bid agent shell | `agent/` in this repo, live in the Claude Console under Managed Agents (Cadocary Operator) | Operator plus qualifier, researcher, and drafter, each with a skill. A test session on Oct 25 confirmed that the operator reads its skill and the memory stores and delegates to a helper. `agent/README.md` explains how to change it |
| Anthropic API key | Google Secret Manager: secret `anthropic-api-key` in project `finchat-495622` | Works, and Managed Agents is turned on for it (checked Oct 25). Ask Sheffield for access (role: Secret Manager Secret Accessor). If the key is replaced, the name stays the same. Never put it in the repo, a log, or the frontend |

## Suggested split of the work

- **Doug and facts:** the facts sheet, the three-award research test, and the questions for Doug. Start here: `docs/fact-sheet.md`.
- **Platform:** the agent shell is done (`agent/`), and the operator pulls RFPs through Polina's tool. The library code and the one-RFP launcher are built (`agent/library.py`, `agent/run.py`). Next: the record tools endpoint, and running both on a schedule.
- **Checks and sourcing:** the code checks, a deadline parser with time zones, and SAM.gov (already underway in this repo).
- **App:** connect the prototype screens (`prototype/`) to the real event feed and the finished packet.

## Never

- Let an agent send, submit, upload, or email anything.
- Commit Doug's real facts, prices, past bids, portal logins, or any key. Keep real files gitignored, the way `profile.json` is.
- Let the agent state anything about Cadocary that isn't on the approved facts sheet.
- Put a number in a bid without a source or a "guess" label.

## Words you'll see

| Word | Meaning |
| --- | --- |
| RFP | Request for proposals: a buyer's document asking vendors to bid |
| Addendum | A change the buyer posts after the RFP goes up. Bidders often must acknowledge each one |
| Bid tab | The public list of who bid and at what price |
| Incumbent | The vendor that holds the current contract |
| WEBS | Washington's state bid site. State agencies must post there, and many cities and counties do too |
| Public Purchase | A bid site many cities and counties use |
| SAM.gov | The federal government's contract site |
| FGA | The paid bid service Doug uses. Exact name unconfirmed |
| CJIS | The FBI's security rules for criminal justice data. Common in jail and court software bids |
| NAICS | Industry codes used to search for federal contracts |
| Set-aside | A contract reserved for a type of small business |
| Managed Agents | Anthropic's hosted service that runs the agent in the cloud |
| Skill | Markdown instructions that teach the agent how to do one job |
