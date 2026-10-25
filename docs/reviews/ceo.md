# CEO Review: Cadocary bid agent

Reviewed October 25, 2026, using the GStack "plan CEO review" method, applied as a read-only review. Nothing was run or installed. The team could not be asked questions, so every choice the method would put to the team is listed under "Decisions for the team" with a recommendation.

Inputs read: `docs/reviews/plan.md`, the GStack review method, and the team repo (`CLAUDE.md`, `docs/architecture.md`, `docs/brief.md`, the `/submit` skill). The method's separate 11-section deep-review file was not included, so this review applies its stated rules directly: no silent failures, trace what happens when things go wrong, measure outcomes, and draw the flow.

## The short version

The vision is right, and Doug told you exactly what he wants. The plan spends most of its effort on the parts that are easy for Claude (writing) and on machinery (schedules, four subagents, two clouds). It spends too little on the two words in Doug's message that are hard: **"competitive"** and **"how much money."** It also sources from SAM.gov, which is federal, while Doug's buyers are mostly Washington cities and counties. Tonight, show one real Washington RFP going all the way through a real agent, with every number linked to a real source. Build the rest after.

Two timing facts change the plan:

- **The real build deadline is 5:30 PM, not 7:30 PM.** The repo's `/submit` skill says a repo link and a demo recording are due at 5:30 PM. Building effectively stops around 4:45 PM. That is about four hours from now.
- **There is no API key and no agent code yet.** Getting a key is the first task, before anything else.

## Review mode chosen

- **For the demo tonight: Scope reduction.** The plan touches well over 15 files across two systems (the Anthropic-hosted agent and the team's own app), with no agent code at midday and four hours of build time left. The method says to cut to the smallest version that proves the idea.
- **For the real product: Selective expansion.** The plan's direction is sound. Keep it, harden it, and add a small number of high-value pieces (below). Each addition is a proposal for the team to accept or reject, not a done deal.

## 1. Premise check: is this the right problem?

**Mostly yes.** Doug's pain is his time. He is doing three jobs (finding, researching, writing) and the paid service he uses made one of them a chore instead of removing it. He named the exact output he wants: "You are a competitive applicant, here is your application, and this is how much money I expect it to be worth. Permission to send?" The plan aims straight at that, not at a stand-in for it. That is the right target.

**The cost of doing nothing:** Doug keeps reading bid breakdowns, bids on fewer contracts than he could, and his own pipeline (bidkit) stays a set of scripts only he can run.

**Four premises in the plan are wrong or untested:**

1. **"No downside to failure" is true before sending and false at sending.** A government bid is legally binding. A wrong price, a certification Cadocary does not hold, an insurance level it does not carry, or a reference who never agreed to be named can get the bid thrown out, embarrass Cadocary with a small group of Washington buyers who talk to each other, or create legal exposure for a false statement. So the system can be loose and exploratory early, and must be strict and checkable at the end.

2. **The hard part is not writing.** Claude writes proposals well. The hard parts are deciding "competitive" and estimating "how much money," because both depend on data the plan has not found yet (prior awards and winning prices for local justice software). Doug's mentor already named the danger: research that invents answers when it finds nothing. The plan should put most of its care there and treat drafting as the easy step.

3. **SAM.gov probably misses Doug's market.** Jails, public defenders, and courts are mostly run by counties and cities. Those buyers post on WEBS (Washington's state bid site), Public Purchase, and similar sites, which is exactly why Doug's bidkit logs into them. The demo RFP itself is from the City of Lakewood, a city bid that would not appear on SAM.gov. The plan's sourcing choice contradicts its own demo story.

4. **Volume is unknown.** How many RFPs a month actually fit Doug (software, Washington, $25,000 and up, 7 or more days left)? If the answer is three, then the daily schedule and the sourcing machinery are overbuilt, and nearly all the value is in qualify, research, and draft. Count last quarter's matches from Doug's FGA emails before building more sourcing.

**One more mismatch:** the plan centers on a web app that shows the agent working live. Doug said he wants to act once per bid, at the end. He will not watch a live feed. The live view is great for the demo audience and for building trust in the first weeks. Doug's daily screen should be a short "ready for you" list, and his alert should be one message.

## 2. What already exists that the plan should reuse

Doug already built most of the plumbing. He said it himself: "the scripts I wrote are trying to be skills."

| Pipeline step | Already in bidkit | What is actually new |
|---|---|---|
| Sourcing | Inbox poller, FGA search, logged-in downloads from WEBS and Public Purchase, calendar files | Removing duplicates across sources, catching addenda (official changes to an RFP after it is posted) |
| Qualifying | Triage scoring, intake, value, fit, and go/no-go gates | Judgment on incumbent strength, competition, and evaluation method |
| Research | Value and pricing gates (rules only) | Finding comparable past awards and winning prices, with sources |
| Checking | Facts extractor with source snippets | Using those snippets to confirm every claim; a "must" checklist for the draft |
| Drafting and assembly | PDF assembly | The written proposal itself |

**Recommendation:** wrap bidkit's scripts as tools the agent can call. Do not rebuild sourcing from scratch on SAM.gov. The plan's own "known gaps" for the hosted agent (no saved browser logins, no email trigger, no Gmail connector) are exactly the things bidkit already handles on Doug's own machine. Running bidkit's tools on a Cadocary-hosted server, so logins never leave Doug's control, should be the plan, not "possibly."

## 3. The 10x version (for the real product)

What Doug's Monday could feel like in six months:

> Two bids are ready. Lakewood jail software: competitive, likely worth $180,000 to $240,000 over three years, based on four similar awards (links). Spokane County defender case tools: ready, about $60,000. Your reading time: about 25 minutes. Also: a county jail contract with another vendor ends in March and their budget includes a replacement. I drafted an introduction letter. Last month you sent six bids and won one. Our price estimates were within 15% of the winning price on the three that have been decided.

The pieces that get there, each for the team to accept or reject:

1. **Learn from every result (biggest value, medium effort).** After each deadline, pull the award notice and the bid tab (the public list of who bid what price). Feed winners, losers, and winning prices back into qualifying and pricing. This is the only real way to measure "competitive," and after six months Cadocary would hold pricing data for Washington justice software that competitors do not have.
2. **A Company Facts sheet Doug approves once (small effort, removes the most risk).** Certifications, insurance limits, references who have agreed to be named, past contracts, staff, and a rate card. The agent may only claim what is on this sheet. Doug answers each question once, ever, instead of once per bid. This is also the answer to "how is the agent steered when nobody is in the loop."
3. **Review sorted by risk (small to medium effort).** Doug's review opens with the binding commitments: price, dates, certifications claimed, references named, and any exceptions to the buyer's contract terms. Text already approved in an earlier bid is marked "same as last time." His reading shrinks to what is new.
4. **Get winning proposals through public records (medium effort, slow but compounding).** Washington's Public Records Act lets anyone request past proposals after an award. The agent can file those requests automatically and build a library of real winning bids. This is the reliable route to "prior awarded bids" for city and county work, which the plan lists as an open question.
5. **Check paid data before building scrapers (small effort to evaluate).** Services such as GovSpend and Deltek GovWin sell state and local award and purchase data. Check whether one covers Washington justice software. Buying the data may be cheaper than researching it per bid.
6. **See RFPs before they post (large effort, later).** Watch contract end dates, council agendas, and budgets. Draft questions for the buyer's question window early. This is how established government vendors win.

Doug's call, not the team's: getting Cadocary onto cooperative contracts that agencies can buy from without running a new RFP. That would change the business more than any bid agent, and it is outside this plan.

## 4. What to cut

### For the demo tonight

| Cut tonight | Do this instead | Bring back for the product? |
|---|---|---|
| Daily schedule (cron) | A "Run" button | Yes |
| SAM.gov sourcing | Load two or three real Washington RFPs by hand, including Lakewood | Yes, after WEBS, Public Purchase, and the FGA inbox |
| Four subagents | One main agent, plus at most one separate checker | Split further only when one agent runs out of room or a step needs different tools |
| Codex or another model as second opinion | Code checks (below) plus one checker with a fresh start | Maybe |
| Running all 100 RFPs | Use about 10 to shape the first skills | Yes, as the test set |
| Memory stores, the rubric grader, extensible templates | One template, no memory | Some, later |
| The bidkit server (MCP) | Call one or two bidkit scripts directly if they run, otherwise skip | Yes |
| Actually sending a bid | "Permission to send" produces the finished package. Nothing is submitted. | Only after weeks of Doug sending by hand |
| Live feed as the main screen | Keep it as a demo view. The main screen is the "ready for you" message. | Yes, as a secondary view |

### For the real product

Keep the vision. Cut "the same qualifying agent checks its own work" (see section 5), and cut soft-only rules where a hard stop is correct (see Decision D5).

## 5. Missing steps and failure modes in the agent loop

The flow with the missing steps added (new steps marked NEW):

```
 SOURCES: WEBS, Public Purchase, FGA email, SAM.gov later
    |
    v
 1 SOURCE    full RFP, all attachments, NEW: addenda, NEW: remove duplicates
    |        deadlines in Pacific time, NEW: question deadline and mandatory meetings
    v
 2 QUALIFY   NEW: hard stops checked by code first, then the agent's judgment
    |        no-go: one line in a weekly note, reason saved
    v
 3 RESEARCH  value range, comparable awards, incumbent
    |        every number carries a link and the exact quote it came from
    v
 4 CHECK     code: is each quote really in its source?
    |        separate checker with a fresh start, NEW: try at most twice
    |        still failing: "no-go, could not verify," and stop
    v
 5 DRAFT     template + NEW: Company Facts only + NEW: Doug's rate card
    |
    v
 4 CHECK     NEW: every "must" in the RFP mapped to a page in the draft
    |        page limit, required forms, each addendum acknowledged
    v
 6 DOUG      "Competitive, worth $X to $Y. Permission to send?"
    |        Send / NEW: Fix this / Pass (with a one-line reason)
    v
 7 SEND      NEW: re-check for late addenda, submit hours early, save the receipt
    |
    v
 8 OUTCOME   NEW: award notice, bid tab, winning price, fed back into 2 and 3
```

### Sourcing

- **Addenda are missing from the plan entirely.** Buyers change RFPs after posting: new deadlines, new page limits, answers to vendor questions. A bid written against the original can be thrown out. Many RFPs also require the bidder to acknowledge each addendum in writing. Check for addenda at the start and again right before sending.
- **Duplicates.** The same RFP can arrive from WEBS, Public Purchase, FGA, and SAM.gov. Without matching them up, the agent writes the same bid twice.
- **"At least 7 days" is the wrong clock.** The question deadline and any mandatory pre-bid meeting usually come well before the due date. Missing a mandatory meeting disqualifies the bid.
- **Silent sourcing failures.** Saved logins expire and sites change. "No new RFPs today" and "sourcing broke today" must look different to Doug. Otherwise he misses bids and never knows.
- **Registration.** Some buyers require vendor registration before a bid counts. Track it per buyer.

### Qualifying

- **Some rules must be hard stops.** Doug's bidkit uses pass/fail gates for a reason. Deadline passed, mandatory meeting missed, a required license or certification not held, or a submission method Cadocary cannot meet should stop the bid outright. Everything else can be judgment.
- **Domain knockouts for this market.** Jail and court software often requires CJIS compliance (the FBI's security rules for criminal justice data), staff background checks, and specific insurance levels. The qualifying skill needs these written in.
- **Product fit.** Five product lines, including Hotels4Truckers. The agent needs to know which products fit which kinds of RFP, or it will chase the wrong work.

### Research

- **Invented numbers are the biggest risk.** Make it impossible by rule: every number needs a link and the exact quote. Code fetches the source and confirms the quote is really there. Anything that fails is labeled "guess" automatically. A second AI agreeing with the first is not proof; matching the quote in the source is.
- **Comparing unlike things.** A three-year license plus setup is not the same as one year of service. Research should record the term and what was included for each comparable.
- **Federal data does not cover local buyers.** USAspending is federal only. City and county awards live in council minutes, bid tabs, and public records requests.

### Checking

- **The checker is the same agent that did the qualifying.** It will tend to agree with itself. Use a separate checker that starts fresh, with different instructions, and lean on code checks wherever possible.
- **"Did it get lazy?" is not a check.** Replace it with concrete tests: every quote found in its source, every "must" in the RFP mapped to a page, page limit met, every required form present.
- **No stopping rule.** The plan's feedback loop has no limit. Cap it at two retries, then stop with a clear "no-go, here is why" rather than looping until the deadline.

### Drafting

- **Claims must come from the Company Facts sheet.** References are real people and must agree to be named. Past contracts and certifications must be true. Nothing is invented.
- **Price must come from Doug's rate card**, adjusted with the research, never made up by the agent. It is the most expensive mistake a bid can contain.
- **Contract terms.** Many RFPs treat silence as acceptance of the buyer's contract terms (liability, insurance, data ownership). The draft must flag every term Doug might object to.
- **Format traps.** Price sheets in the buyer's spreadsheet format, separate technical and price files, signatures, notarized forms, and sometimes paper copies. Some bids cannot be submitted online at all.

### Doug's review

- **Only two buttons.** The plan offers "send" or "pass." Doug will often want "fix this and bring it back." His fixes and his reasons for passing are the best steering signal the system will ever get. Save every one and use them to improve the skills.
- **When Doug is busy.** The message must show time left before the deadline, with one reminder. If he does not answer, the bid expires cleanly and he is told.
- **When the agent needs a fact only Doug has.** Do not stop mid-run (Doug was clear). Finish the bid, mark the gap, and list it at the top of the review: "I assumed your insurance is $2 million; confirm."

### Sending

- **The plan does not describe sending at all.** Each portal is different, and some require e-signatures, addendum acknowledgments, or uploads in a fixed order.
- **Keep the send button out of the agent's hands.** RFP documents are text from strangers. A planted instruction in a PDF should never be able to trigger a submission. Sending should be done by plain code, only after Doug's click.
- **Submit early.** Portals slow down at deadlines. Aim for hours ahead, and save the confirmation receipt.

### What happens when each step fails

| Step | What goes wrong | How it is caught | What Doug sees |
|---|---|---|---|
| Source | Login expired, site changed | Daily "sources checked" status per site | "WEBS check failed today" in his note |
| Source | Addendum posted after drafting | Re-check before sending | Bid held, with "the RFP changed, re-checking" |
| Qualify | Hard stop missed | Code checks before the agent's judgment | Nothing, the bid never reaches him |
| Research | Number has no real source | Code quote check | Number labeled "guess" with low confidence |
| Check | Fails twice | Retry limit | "No-go: could not verify. Here is why." |
| Draft | Claim not on the facts sheet | Code compares claims to the sheet | Flagged at the top of the review |
| Doug | No answer before deadline | Deadline timer | One reminder, then "expired" |
| Send | Portal error | Receipt required | "Not sent. Here is the error." Never silence. |

## 6. How success is measured

### For the demo tonight

- One real Washington RFP goes from PDF to finished draft through the real agent, not the simulation.
- Every number in the draft opens to a real source containing that number.
- The code checks pass: quotes found, every "must" covered, page limit met.
- The agent turns down at least one real RFP for a correct reason. This shows judgment, not just enthusiasm.
- Doug reads the real draft, and the team records how long it took and whether he would send it, and what he would change.

### For the real product

| Measure | Why it matters | Target to start |
|---|---|---|
| Doug's minutes per bid | The thing he said limits everything | Under 30 |
| Bids sent per month | The point of the tool | More than before, by Doug's count |
| Share sent without edits | Shows the drafts are trusted | Rising each month |
| Share Doug passes on | Each pass wasted his reading time | Falling each month |
| Unverified claims sent | Legal and reputation risk | Zero |
| Bids rejected for format or deadline | Preventable losses | Zero |
| Price estimate vs. winning price | The "how much money" promise | Within about 20%, measured on decided bids |
| Win rate and dollars won | The real result | Tracked from month three |

**Measuring "competitive" before any bid is decided:** use the 100-RFP set. For past RFPs where the winner and price are public, hide the answer, run the agent, and compare its verdict and price estimate to what really happened. Doug can also grade 10 past RFPs from memory ("I would have bid this one, not that one") as a second answer key.

## 7. The riskiest assumption and how to test it cheaply

**Riskiest assumption:** that the research step can find real, sourced prior awards and prices for Washington city and county justice software, well enough to say "competitive" and "worth $X" honestly.

If this fails, Doug's message becomes "here is your application and a guess," which is close to the breakdowns he already finds a chore.

**Cheap test, under an hour, before 2 PM today:**

1. Ask Doug for three past Washington awards he already knows (buyer, product type, roughly what was paid). Doug is the answer key.
2. Give the research step only the RFP for each, not the answer.
3. Count: how many numbers came with a source that really contains them, and how close the estimate was to what Doug knows.

**What to do with the result:** if it does well on two of three, keep "worth $X" in the demo. If not, change the message to "worth $X to $Y, based on N awards, low confidence," show the sources, and say plainly that the outcome loop is how it gets better. Being honest about confidence is a stronger demo than a confident number someone in the audience can challenge.

**Second-riskiest, ten-minute test:** search SAM.gov for jail, court, and public defense software in Washington over the last 90 days and compare with WEBS. If SAM.gov shows little, Decision D2 is settled.

**Third, during the afternoon:** hand Doug the real Lakewood draft and time his review. That number is the product.

## 8. Plan for the next four hours

| Time | Work |
|---|---|
| Now to 1:15 | Get the API key. Spend 30 minutes with Doug on the Company Facts sheet, his rate card, and three past awards he knows. Pick the demo RFPs: Lakewood plus one that should be turned down. Copy the plan into `docs/brief.md`, which is still empty and which the repo treats as the source of truth. |
| 1:15 to 1:45 | Prove the hosted agent works at all: one session, one skill, one tool. If not working by 1:45, switch to the simpler agent loop inside the team's own backend (Decision D3). |
| 1:45 to 3:15 | One real run on Lakewood: qualify, research, draft. In parallel, teammates build the code checks (quote check, "must" checklist, page count). These are clear, testable jobs for the sourcing teammates if sourcing is cut. |
| 3:15 to 4:00 | Connect the real run's events to the prototype screens. Doug reviews the real draft; time him. |
| 4:00 to 4:45 | Record the two-minute demo video. Run `/submit`. |
| 5:30 | Submission due: repo link and recording. |
| 5:30 to 7:30 | Rehearse. Optionally start a second live run so the demo can show one in progress. |

What the builders will run into: scanned PDFs that need text recognition, price sheets in spreadsheets, RFPs too long to read in one pass (bidkit's facts extractor helps here), and slow or blocked websites during research.

**Two repo cautions.** The repo will be made public tonight. Doug's rate card, Company Facts, prior bids, and bidkit's saved logins must stay out of it. Ask Doug before putting his bidkit scripts in a public repo. Also, the clickable prototype is described as a shared artifact; make sure the screens you demo are actually in the repo you submit.

## 9. Decisions for the team

| # | Decision | Recommendation | Why |
|---|---|---|---|
| D1 | What the demo proves | **One real Washington RFP, start to finish, through the real agent**, plus one correct rejection | It answers the only question judges and Doug care about: does it actually work on a real bid? A simulated full pipeline proves less. |
| D2 | Where RFPs come from | **Tonight: hand-load real Washington RFPs. Product: WEBS, Public Purchase, and the FGA inbox through bidkit first; SAM.gov second** | Doug's buyers are cities and counties. The demo RFP itself is a city bid. bidkit already reaches these sites. |
| D3 | Where the agent runs tonight | **Try the hosted Managed Agents setup until 1:45 PM; if a basic session does not work by then, run the agent loop inside the team's own backend** | The hosted setup fits the product, but there is no key or agent code yet and only four build hours. Both can send the same step-by-step events to the screen. |
| D4 | Live run or recorded run at the demo | **Record a real run this afternoon and replay it; optionally show a second run in progress** | Doug said a full run may take hours. Nobody can show that live in two minutes, and the recording is due at 5:30 PM anyway. |
| D5 | Hard rules or judgment only | **A short list of hard stops in code (deadline passed, mandatory meeting missed, required license or certification not held, submission impossible); judgment for the rest** | Doug's own bidkit uses pass/fail gates. Letting the agent "judge" its way past a missing certification wastes Doug's review or worse. |
| D6 | Who checks the work | **Code checks first, then one separate checker that starts fresh. Drop Codex for tonight** | An agent checking itself tends to agree with itself. Code checks cannot be talked out of a result. |
| D7 | Company Facts sheet | **Yes. Build it with Doug today, in 30 minutes. The agent may only claim what is on it** | Removes the largest legal risk, shortens Doug's review, and answers "how is it steered with nobody in the loop." Doug answers once, ever. |
| D8 | Where the price comes from | **Doug's rate card, adjusted by research, with the reasoning shown** | Price is binding and the costliest error. Doug's pricing rules belong to Doug. |
| D9 | The 100-RFP collection | **Use about 10 tonight to shape the skills; keep all 100 as the test set for later** | Processing 100 RFPs and merging them is a day of work on its own. Ten real examples are enough for first drafts of the skills. |
| D10 | Sending | **Never submit tonight. For the first weeks of real use, the agent prepares the package and Doug submits it himself** | A bid is binding. Trust gets earned on real bids before the send button is automated. |
| D11 | bidkit | **Wrap it as tools, hosted on Cadocary's own server. Do not rebuild sourcing** | It already does sourcing, logins, fact extraction with sources, and PDF assembly. Logins stay with Doug. |
| D12 | Doug's main screen | **A "ready for you" message with the four parts Doug asked for. The live view sits one click behind it** | Doug wants to act once. The live view is for trust and for the audience. |
| D13 | Doug's review buttons | **Send, Fix this, Pass (with a one-line reason)** | His fixes and reasons are the best signal for improving the agent. Two buttons throw that away. |
| D14 | Product addition: learn from results | **Accept for the product, not tonight** | It is the only way to measure "competitive" and make prices better over time. |
| D15 | Product addition: public records requests for winning proposals | **Accept for the product** | It is the reliable path to prior awarded bids for city and county work. |
| D16 | Product addition: paid award data | **Spend one hour checking before building scrapers** | Buying it may be cheaper than researching it bid by bid. |

## Review report

| Area | Status | Main finding |
|---|---|---|
| Premise | Finding | Right problem; "no downside" is false at send; SAM.gov misfits Doug's market |
| Reuse | Finding | bidkit already covers sourcing, logins, cited facts, and assembly |
| Scope tonight | Finding | Too large for four build hours; cut to one real RFP end to end |
| Agent loop | Finding | Missing addenda, hard stops, a stopping rule, an independent checker, sending details, and outcome tracking |
| Measurement | Finding | No success measures in the plan; proposed above |
| Riskiest assumption | Finding | Research may not find real local award prices; test with Doug's three known awards before 2 PM |
| Deadline | Finding | The repo says the recording is due at 5:30 PM, not 7:30 PM |

**Verdict:** Proceed, with the scope cut for tonight and decisions D1 to D13 made before 1:15 PM.

**Unresolved decisions:** D1 through D16 above, all awaiting the team.
