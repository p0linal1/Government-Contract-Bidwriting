# Plan: Cadocary bid agent

Built at the Seattle AI Week Claude Impact Lab hackathon, October 25, 2026. Demos are at 7:30 PM today. A team of about four, plus the business owner.

## The business and the owner

Cadocary LLC is a small Washington software company owned by Doug. It sells legal and justice software, including tools for public defenders, and bids on government contracts. One current bid is for jail software. Products: DocketBot (public defense tools), ClientCheck (court records), SpendLogic (procurement documents from templates), PURLPal (answers from large document sets), Hotels4Truckers (web and mobile booking).

## The problem, in Doug's words

- Finding RFPs, researching them, and writing bids are three jobs he is in the loop on today. He wants out.
- A paid service already sends him FGA bid breakdowns. "What this has created is a chore." He wants the bid written, not another breakdown.
- "I want artificial intelligence, not artificial asking if I'm right."
- The one message he wants: "You are a competitive applicant, here is your application, and this is how much money I expect it to be worth. Permission to send?"
- "If it's done twenty minutes of work and now it's asking me a question, that's not going to be good for me. But if it's done eight hours, getting all the way to the end, and then it's just the final 'am I completely full of shit here', then it's worth it for me to read all of that."
- "There's no downside to failure. There's incredible upside to success. The limiting factor is how much time you're asking of the user."
- Token cost does not worry him. A sent bid is legally binding, so he does read the final bid before sending.
- He already built "bidkit", his own Python pipeline: a mail inbox poller, an FGA search, triage scoring, portal downloads (Playwright with saved logins for WEBS and Public Purchase), a facts extractor with source snippets, calendar files, five pass/fail gates (intake, value, pricing, fit, go/no-go), and PDF assembly. He says: "I think the scripts I wrote are trying to be skills."

## What we are building

One operator agent on Anthropic Managed Agents, running in Anthropic's cloud on a daily schedule. It delegates to four subagents. Doug sees a clean web app that shows what the agent is doing on each RFP, live, and he acts only once per bid, at the end.

Pipeline, as the team agreed:

1. Sourcing, deterministic. Saved searches on SAM.gov run on a schedule (cron) and store complete RFPs only. Software filters, completeness, and time zones belong here. The operator gets new RFPs through a tool or endpoint. Teammates are building this part. FGA may be out of scope for this round, and SAM.gov was named instead, but that is not settled.
2. Qualifying, agentic. It reads each RFP and decides whether Cadocary is qualified, competitive, and a match for Doug's preferences (software, Washington, $25,000 and up, at least 7 days to respond). Deterministic rules feed the agent's judgment but are not a hard pass or fail. Factors: knockout must-haves, incumbent strength, past performance relevance, evaluation method, price competitiveness, and competition density.
3. Research, agentic. It works out what the contract is worth in dollars and, most importantly, finds prior awarded bids for comparable work. Pull data with code wherever possible (scripts as tools), and use deep research only where code can't reach. It must report confidence, say when data is missing, and label educated guesses. Doug's mentor warned that "Claude will do deep research and lie to you, especially if it can't find anything."
4. Qualifying again, as the checker. The same qualifying agent checks the research (did it get lazy?), eligibility and competitiveness, and later that the draft is complete against the RFP's requirements. An adversarial second opinion (another Claude session, or Codex) validates the research. Everything flows back through the operator as a feedback loop.
5. Drafting, agentic. It writes the whole proposal from a template, built on the reasons Cadocary is competitive, inside the page limit.
6. Doug reviews the finished bid: why it is competitive, expected worth with sources, confidence, the draft page by page, and every call the agent made, such as references, questions to the buyer, and price. Then he gives permission to send, or passes.

Agent outputs use fixed formats so code can check them, and the templates must be extensible. Skills (Markdown instructions) carry the nuance, are hidden from Doug, and are the hardest part: how to delegate, how to qualify, what to research (with pricing), and how to draft. Doug's bidkit scripts become tools, possibly as an MCP server Cadocary hosts so logins stay on its server. Data access comes through connectors.

## How we plan to get the skills right

Collect about 100 real RFPs (a collection effort is running now). Run one Claude per RFP to fill the same sheet: scope, knockout must-haves, scoring method and weights, budget and price clues, incumbent, certifications, insurance, references, format, page limits, deadlines, submission method, and "what makes this one different", each with a page cite. Then one Claude combines the sheets into three groups: common (a checklist), variable (things to look for), and rare but fatal (warnings). Turn that into first drafts of the skills, each backed by real examples. Reuse the same 100 RFPs as an evaluation set with a baseline, so changes don't make the agent worse.

## Managed Agents facts the plan relies on

- Scheduled deployments use cron. Vaults hold credentials and inject them at request time. Skills attach to agents. The multiagent block lets one coordinator delegate to predefined subagents that share the sandbox. Memory stores persist between sessions. The session event stream exposes every tool call and result, so the app can show the work live. Outcomes grade a deliverable against a rubric, with a separate grader.
- Known gaps: no documented Gmail or Google Drive connector, no saved browser logins, no way for a new email to start a run, and grading loops that do not pause for a person.

## What exists now

- A clickable front-end prototype (React) that simulates the whole flow with live agent event streams, a real RFP (City of Lakewood, WA), source chips on every claim, the morning brief, the proposal page-by-page review, and a "How it works" page. It is shared as an artifact.
- A team repo with the Claude Code setup (instructions, commands, hooks), a FastAPI backend, a React frontend, CI, and a Cloud Run plan. No agent code yet. No Anthropic API key yet.

## Open questions

- SAM.gov only, or FGA, WEBS, and the bid inbox too, for the demo?
- How to pull prior awarded bids reliably (USAspending for federal awards; state and city award data such as watransparency.com; bid tabulations; council records).
- How the agent is steered when nobody is in the loop.
- How to measure "competitive" before any bid has been won or lost.
- What to show at the 7:30 PM demo.
