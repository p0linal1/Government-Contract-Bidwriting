# Office hours review: Cadocary bid agent

Review of `docs/reviews/plan.md` using the GStack office-hours method, October 25, 2026, around midday. Demos are at 7:30 PM.

## How this review was run

- Goal question, answered from the plan: this is a hackathon, which the method maps to "builder mode." But there is a real customer (Doug), real money, and legally binding output, so I ran the harder startup-mode diagnostic (the six forcing questions) instead. Product stage: pre-product for the team; Doug is the one user, and he already runs his own version (bidkit).
- The plan is fully formed, so per the method I skipped live questioning and went straight to the forcing questions (answered from the plan), the competitor search, the premise challenge, and alternatives.
- Not run: preamble, telemetry, config, learnings, artifact sync, the Codex second opinion, and the visual mockups. No commands were run. The method's detailed question file (`sections/phase-2a-startup-diagnostic.md`) was not in the materials provided, so the six questions follow the published GStack structure: demand reality, status quo, desperate specificity, narrowest wedge, observation and surprise, future fit.
- Every place the method would ask the team a question and the plan does not answer it is listed at the end under "Questions for the team."

## Verdict

Doug's pain is real and proven: he already pays for a bid service and wrote his own pipeline to escape this work, so demand from this one customer is settled. The plan aims at the right result (one "Permission to send?" message per bid) but is trying to build the whole factory before 7:30 PM; build one honest, finished bid package for the real jail software RFP first, and make that the demo.

## What I understand about this project

Doug runs Cadocary, a small Washington software company selling legal and justice tools to government buyers. Today he personally finds RFPs, researches them, and writes bids. He wants a system that does all three and only bothers him once, at the end, with a finished bid, a dollar estimate, and a yes-or-no question. The team plans a cloud agent on a daily schedule with four helper agents (qualify, research, check, draft), a web app that shows the work live, and skills built from studying about 100 real RFPs. A clickable prototype exists. No agent code and no API key exist yet.

## Demand reality: does the owner actually want this?

Strong evidence, from one person.

What counts as real evidence here:

1. **He pays for the status quo already.** A paid service sends him bid breakdowns. Paying money is the strongest demand signal there is.
2. **He built his own fix.** bidkit is a working Python pipeline: inbox polling, search, scoring, portal downloads with saved logins, fact extraction with source quotes, five pass/fail gates, and PDF assembly. Founders who write code to solve their own problem are not hypothetical users.
3. **He is specific about what is broken.** "What this has created is a chore." The breakdowns made more work, not less. He knows exactly where the existing tool stops being useful.
4. **He named the one output he wants, word for word.** "You are a competitive applicant, here is your application, and this is how much money I expect it to be worth. Permission to send?"
5. **He is spending his Saturday here.** Time is the thing he says he has least of.

What is missing:

- **No numbers.** We do not know how many RFPs he sees a month, how many he submits, how many hours each takes him, or his win rate. Without these, the demo cannot say "this saves Doug X" or "this lets Doug bid on Y more."
- **One customer.** Nothing in the plan says any other small vendor wants this. That is fine for today, since the brief is one business, but it matters if this is open-sourced as a product.
- **No willingness-to-pay test.** He says token cost does not worry him. That tells us he values the outcome, not what he would pay for it.

## Status quo: what he does today and what it costs him

Today Doug is the glue between three jobs: finding, researching, writing. The paid service handles part of finding. bidkit handles finding, downloading, extracting facts, and pass/fail screening. **Nothing he has writes the bid or estimates its worth from comparable awards.** That gap is exactly what the team should fill.

What it costs him:

- **Hours per bid.** Industry estimates put a government RFP response at roughly 10 to 40+ hours, with 23 to 33 hours often cited as an average ([The Bid Lab](https://thebidlab.com/learning-center/how-long-does-it-take-to-write-a-proposal/)). At $100 an hour that is about $4,000 to $8,000 of time per bid ([Blackridge Research](https://www.blackridgeresearch.com/tools/proposal-cost-calculator)). These are vendor-sourced estimates, not Doug's numbers.
- **Bids he never sends.** This is the bigger cost, and the plan's own quotes point at it: "there's no downside to failure... the limiting factor is how much time you're asking of the user." If his time caps how many bids he submits, every RFP he skips is a lost lottery ticket on a $25,000+ contract.
- **Attention spent on breakdowns.** The paid service hands him reading, not results.

The honest framing for the demo: the status quo is not "Doug does nothing." It is "Doug has already automated the easy half, and the hard half (judgment, research, writing) still lands on him."

## Desperate specificity: who exactly is this for?

Doug. The plan is unusually clear on this, which is good. He wants zero check-ins mid-run ("If it's done twenty minutes of work and now it's asking me a question, that's not going to be good for me"), one decision at the end, and he will read the full bid because it is legally binding. Design every screen for a busy owner who opens the app once per bid and wants to say yes or no in under 30 minutes.

## Narrowest wedge: the smallest thing worth building first

**One real RFP in, one finished bid package out, judged by Doug.**

Use the jail software RFP Doug is actually pursuing (or the City of Lakewood RFP already in the prototype, if the jail documents are not on hand). The package contains:

1. A requirements checklist pulled from the RFP, each item with a page cite, marked met, not met, or unknown.
2. A go or no-go call with the three to five reasons that drove it.
3. An estimated contract worth, with every number linked to a source, and "not found" or "educated guess" labels where that is the truth.
4. The full draft proposal, inside the page limit, using only facts about Cadocary that Doug has approved.
5. A short list at the top: "Calls I made that you should check" (price, references, any claim about past work, questions for the buyer).

Skip for the wedge: the daily schedule, SAM.gov sourcing, four separate agents, the MCP server, the 100-RFP study, and the adversarial second model. All of those are good later. None of them changes whether Doug would send the bid.

The test of the wedge is one sentence from Doug: "I would send this, after these edits." Time how long his review takes. That number is the pitch.

## Observation and surprise: what stands out

- **Doug already told you the architecture.** "I think the scripts I wrote are trying to be skills." He has done the hard thinking about the steps and the gates. The team's job is to add judgment and writing, not to rebuild his pipeline.
- **The product is defined by what it does not do: ask questions.** "I want artificial intelligence, not artificial asking if I'm right." Every tool in this market (below) is a copilot that asks for input at each step. Doug wants the opposite.
- **The live activity feed is not what Doug asked for.** He wants to act once, at the end. A live stream of agent work is great for the judges and for building trust in week one, but it is not his daily screen. Lead the demo with the one-decision screen and put the live feed behind a "how it got here" tab.
- **The most valuable thing the agent might say about the jail bid is "don't."** Jail management software is a crowded field with established vendors. Recent county awards drew bids from Tyler Technologies, CentralSquare, EIS, Global Jail Tracker, and others ([Santa Fe County award notice](https://www.santafecountynm.gov/documents/solicitations/Contract_Award_Notification_Jail_Management_System.pdf)), and Clark County, WA went with EIS ([Clark County staff report](https://clark.wa.gov/sites/default/files/dept/files/council-meetings/2015/SR056-15.pdf)). An agent that honestly says "the incumbent is strong, here is why this is a long shot, and here is what it would take" earns more trust than one that always says "you're competitive." The demo story should allow for that answer.

## Future fit: does this get better as AI gets better?

Yes. Drafting and research improve with every model release, so the writing gets cheaper and better over time. What stays valuable and hard to copy is Doug's own material: his approved facts, his past bids, his gates, his preferences, and an evaluation set built from real RFPs and real outcomes. The plan's instinct to build that evaluation set is right. The risk is that funded competitors improve just as fast, so the edge has to be the one-touch workflow and the honesty, not the drafting.

## Competitors and what makes this different

| Tool | What it does | Who it serves | Notes |
|---|---|---|---|
| GovDash | Finds opportunities, builds compliance matrices and outlines, writes proposals from past performance, pricing and contract modules | Federal contractors | Founded 2023, $10M Series A; custom pricing that reviewers say can be costly for small firms ([GovDash](https://www.govdash.com/features/govdash-platform), [LinkedIn](https://linkedin.com/company/govdash), [aibucket](https://aibucket.io/tools/govdash-ai)) |
| Sweetspot | Searches federal sources plus a claimed 1,000+ state and local portals; upload an RFP and get a compliance matrix, outline, and draft "in hours"; bid/no-bid helper | Federal and some state/local | Claims mostly from its own site and a competitor's comparison ([Sweetspot](https://sweetspot.so/), [comparison](https://www.sweetspot.so/sweetspot-versus-other-govcon-software/), [AutogenAI](https://autogenai.com/?p=8134)) |
| Cleatus | Federal, state, and local opportunity database, competitor award analysis, proposal writing | Includes state and local | $4M seed ([Technical.ly](https://technical.ly/entrepreneurship/cleatus-aims-to-be-the-ai-operating-system-for-govcon.md)) |
| Loopio | Answer library for repeated RFP and security questionnaires | Mid-size and enterprise sales teams | Entry tier reported around $20,000 a year ([AutoRFP.ai, a competitor](https://autorfp.ai/blog/loopio-pricing)) |
| AutoRFP.ai | AI answers to RFP questions from your content | Sales teams | Listed at $499 to $899 a month depending on source ([G2](https://g2.com/compare/autorfp-ai-vs-loopio), [AutoRFP.ai](https://autorfp.ai/alternatives/loopio)) |
| GovSpend | State and local purchase order and contract data, including what agencies paid which vendors | Vendors selling to state and local government | Not a competitor; a likely data source for "prior awarded bids." Roughly $7,300 to $24,500 a year per a competitor's blog ([GovSpend](https://govspend.com/sled-agencies/), [Fed-Spend](https://fed-spend.com/blog/govwin-govspend-govtribe-bloomberg-pricing-compared-2026)) |

I could not identify what "FGA" stands for from public sources; the team should confirm which service Doug pays for, since it may already be one of the above.

**What everyone already knows (layer 1):** read the RFP, build a requirements checklist, draft from a library of your past content, and make a careful bid or no-bid call. This is now table stakes. Sweetspot and GovDash both claim it.

**What the market is saying (layer 2):** the space is crowded and funded, mostly aimed at federal work, and every product is a copilot built for proposal teams who want control at each step.

**Where the conventional approach is wrong for Doug (layer 3):** everyone builds copilots because they assume the user wants to steer each step and that the cost of an AI mistake is high. Doug says the opposite: his attention is the scarce thing, and a lost bid costs him almost nothing. That suggests a different product: an autonomous bid shop that does eight hours of work and asks one question, with honesty about confidence doing the job that step-by-step approvals do in other tools.

**What makes this different, honestly:**

1. One decision per bid, at the end, instead of a copilot.
2. A dollar estimate of what the bid is worth, with sources and confidence labels. None of the tools above lead with this.
3. Built on Doug's own pipeline, gates, and logins, so it fits how he already works.
4. Aimed at Washington state and local justice software, a niche the federal-focused platforms underserve.

What is not different: requirements checklists and AI drafting. Do not pitch those as the innovation.

## Premise challenge

The plan rests on these premises. My position on each:

1. **The problem is Doug's time, not bid quality.** Agree. His quotes are consistent on this.
2. **"There's no downside to failure."** Partly disagree. A sent bid is legally binding. A wrong price binds Cadocary. A made-up reference or overstated past project is a misrepresentation to a government buyer. And Washington's justice buyers are a small, repeat pool, so a sloppy bid can follow him. The real rule is: losing is free, lying is not. Design the checks around that.
3. **SAM.gov is the right place to source RFPs.** Disagree. SAM.gov lists federal work. Doug's preferences are Washington, $25,000+, software, and his products serve county and city justice systems. Washington state agencies must post on WEBS; cities and counties may use WEBS or their own sites ([WA DES](https://des.wa.gov/bids), [WEBS fact sheet](https://www.ezview.wa.gov/Portals/_1729/Documents/Presentations/WEBS%20Vendors%20Fact%20Sheet_v1%20.pdf)). bidkit already pulls from WEBS and Public Purchase. SAM.gov risks a demo with zero good matches.
4. **Prior awarded bids can be found reliably.** Partly disagree. Federal awards are in USAspending. State and local awards are scattered across council minutes, bid tabulations, and public records requests, or sold by GovSpend. For most Washington county bids, "no comparable found" will be the common answer, which is exactly when the mentor warned Claude will make things up. Design for "not found" as the normal case, not the exception.
5. **A second AI checking the first catches bad research.** Partly disagree. Two AIs agreeing is one opinion, not two. The checker must verify that each number actually appears at its cited source, and code should do that check wherever it can.
6. **An operator plus four helper agents on a scheduled cloud platform is needed now.** Disagree for today. One agent running three skills in order produces the same package with fewer things to break. There is no agent code and no API key yet, and the plan's own list of platform gaps (no saved browser logins, no email trigger) breaks both of bidkit's input methods if they move to the cloud.
7. **Studying 100 RFPs is the way to get the skills right.** Agree for the long run, disagree for today. Ten to twenty RFPs will show the checklist's shape. The full 100 belongs in the evaluation set next week.
8. **The live view of the agent's work is what Doug wants.** Disagree. It is what the audience wants. Doug wants the end screen.

## Alternatives

**Approach A: One RFP, one package (minimal)**
- Summary: a single Claude run on one real RFP plus a Cadocary facts file, producing the five-part package above, shown in the existing prototype's review screen.
- Effort: small. Risk: low.
- Pros: real output for a real bid by 7:30; directly tests Doug's one sentence; reuses the prototype screens.
- Cons: no schedule or sourcing; looks less like "an agent that runs every day."
- Reuses: the prototype review screen, bidkit's fact extractor output, the backend.

**Approach B: The plan as written (ideal long-term)**
- Summary: scheduled operator on Managed Agents, four helper agents, bidkit as tools on a Cadocary-hosted server, 100-RFP evaluation set, adversarial checker, live web app.
- Effort: extra large. Risk: high for today.
- Pros: the right end state; logins stay on Cadocary's server; the evaluation set protects quality over time.
- Cons: many unproven pieces and no key at midday; the demo likely falls back to the simulated prototype, which judges will notice.
- Reuses: bidkit, the prototype, the repo setup.

**Approach C: Give bidkit a brain (lateral)**
- Summary: keep Doug's pipeline in charge of finding, downloading, and screening, on his own machine with his own logins. Add Claude only at the steps bidkit lacks: research and drafting. Deliver one email per bid: "Permission to send?" with the package attached.
- Effort: medium. Risk: medium.
- Pros: works around the platform's login and email gaps; nothing Doug already trusts gets rebuilt; email is where he already lives.
- Cons: depends on bidkit's code and Doug's machine; less of a web app to show.
- Reuses: all of bidkit.

**Recommendation:** Build A today on the jail software RFP, shaped so it becomes the core of C next week. Keep B as the roadmap slide. This maps to Doug's stated goal: a finished bid he can say yes or no to.

## Biggest risks

1. **Made-up facts in a binding document.** Invented past projects, references, or prices. Fix: the drafter may only state facts about Cadocary that come from a Doug-approved facts file or the RFP itself, and the checker flags any sentence without a source.
2. **Wrong price.** Price is listed as an agent "call," but nothing says where pricing rules come from. Fix: Doug supplies a rate card and a floor; the agent proposes within it and shows the comparables it used.
3. **Sourcing aimed at the wrong market.** SAM.gov versus Washington local buyers (premise 3).
4. **Too much scope for the time left.** About seven hours, no agent code, no key. The likely failure is demoing the simulation instead of real output.
5. **Platform gaps hit the exact things bidkit relies on.** No saved browser logins and no email trigger on Managed Agents. The plan's idea of a Cadocary-hosted tool server is the right answer, but it is not a today task.
6. **Secrets and private data in an open-source repo.** Doug's portal logins, pricing, and bid documents must not land in the public repo. Ship the open-source version with a public RFP and a sample facts file.
7. **No way yet to know if "competitive" means anything.** Without past wins and losses, the score cannot be checked against reality.
8. **The honest answer may be "no-go" on the bid Doug cares about.** That is a feature, but the demo story has to allow for it.

## Missing steps in the loop

The plan's loop is: find, qualify, research, check, draft, Doug reviews, send. These steps are missing or unclear:

1. **What "send" means.** After Doug says yes, who submits? Portal uploads, required forms, signatures by an authorized officer, sometimes notarized affidavits or bid bonds. Nothing in the pipeline does this. For now, the agent should produce a submission-ready packet and a checklist, and Doug (or bidkit's browser automation) submits.
2. **Required attachments.** Insurance certificates, W-9, non-collusion forms, buyer pricing sheets, reference contact permissions. The draft is only part of a complete bid.
3. **The buyer question window and addenda.** Questions to the buyer usually have a deadline well before the due date, and RFPs get amended. An agent that only acts at the end will miss the question deadline and may draft against an outdated RFP. It needs to check for addenda before the final package and either send questions early or note that the window closed.
4. **Mandatory pre-bid meetings.** Some RFPs disqualify bidders who skip them. This is a "rare but fatal" item that must be caught at qualifying time, not at the end.
5. **A source of truth about Cadocary.** Past performance, references, staff, certifications, insurance. bidkit extracts facts from the RFP, not about Cadocary. The drafter needs an approved facts file.
6. **Pricing inputs.** See risk 2.
7. **How Doug finds out a bid is ready.** Email or text. The plan notes there is no Gmail connector.
8. **What happens after submission.** Track the award, the winning bidder, and the winning price (public record), and request a debrief when lost. This is the only way to answer the open question "how do we measure competitive," and it feeds the evaluation set.
9. **Capturing why Doug passes.** When he says no, one line of why should update his preferences for next time.
10. **Rules for when the agent is stuck and nobody is watching.** Proposed: a fatal problem (missing certification, missed mandatory meeting) stops the run and sends Doug one line; an uncertain call takes the safer option, labels it, and lists it in "calls I made"; missing data is reported as missing, never filled in.

## What I noticed (founder signals)

Doug shows nearly every signal the method looks for: a real problem he has today, a specific user (himself), deep knowledge of the space (he sells to these buyers), taste (the exact one-line message he wants), and agency (he already built bidkit and pays for a service). The one unknown is whether other vendors need this too. Pushback against a second opinion could not be observed, since no questions were asked.

## The assignment

Before 3 PM, produce one real, complete bid package for the jail software RFP, hand it to Doug, and ask one question: "Would you send this, and after what edits?" Time his review. His answer and that time are the demo.

## Questions for the team

1. **Which RFP is the demo?**
   Recommended: the jail software bid Doug is actually pursuing. Why: "would you send this?" on a live bid beats any simulation. Fall back to Lakewood if the jail documents are not available.
2. **SAM.gov, or the sources bidkit already uses?**
   Recommended: neither live for the demo; load the RFP directly. Next, use bidkit's WEBS and Public Purchase output. Why: Doug's buyers are Washington local governments, not federal agencies.
3. **How many RFPs does Doug see and submit each month, and how long does each take him?**
   Recommended: ask Doug now, in two minutes. Why: those two numbers turn the demo from "cool" into "this lets Doug bid on four times as many contracts."
4. **Does Doug have past bids, won or lost, with award results?**
   Recommended: yes, collect them today. Why: won bids are the best drafting template, and outcomes are the only real test of "competitive."
5. **Who sets the price?**
   Recommended: Doug gives a rate card and a price floor; the agent stays inside it and shows its comparables. Why: price is legally binding, and the agent should never invent it.
6. **What happens after "Permission to send"?**
   Recommended: the agent hands over a submission-ready packet and a checklist; a person submits this round. Why: signatures and portal uploads are where a mistake is not free.
7. **Has Doug tried Sweetspot, GovDash, or Cleatus?**
   Recommended: ask. Why: if he tried them and quit, his reason is the pitch line; if he has not, the team should know what they already do before building the same thing.
8. **What is "FGA," and what does it already deliver?**
   Recommended: get the name and a sample breakdown. Why: if it already supplies scope and scoring details, the agent can start from it instead of re-extracting.
9. **Where do Cadocary's facts live: past projects, references, insurance, certifications?**
   Recommended: one facts file Doug approves once, and the drafter may only cite from it. Why: this is the main guard against made-up claims.
10. **One agent or an operator plus four helper agents, today?**
    Recommended: one agent running the skills in order. Why: same output, fewer failure points, and the time is short. Split it later when the evaluation set shows a reason.
11. **Is the 100-RFP study worth running today?**
    Recommended: cap it at 10 to 20 for first-draft skills; finish 100 later for the evaluation set. Why: the checklist shape shows up early, and the team needs the hours for the real package.
12. **Is the live activity feed for Doug or for the judges?**
    Recommended: the judges. Lead with the one-decision screen and keep the feed one click away. Why: Doug said he wants to act once.
13. **What goes into the open-source repo?**
    Recommended: no logins, no pricing, no real bid documents beyond public ones; ship a sample facts file. Why: the repo is public at the end of the day.
14. **How is "competitive" measured before any award?**
    Recommended: a written scorecard of observable factors (knockouts met, how the scoring weights favor Cadocary's strengths, incumbent strength, price against comparables), checked later against Doug's past outcomes and public award notices. Why: it makes the judgment explainable now and testable later.
15. **How is the agent steered with nobody in the loop?**
    Recommended: the three rules in "Missing steps" item 10 (stop on fatal, label and continue on uncertain, report missing as missing). Why: it matches Doug's "don't ask me mid-run" while keeping the one thing that must never happen, a confident lie, off the table.

## Status

DONE_WITH_CONCERNS. The review is complete; the concerns are the open questions above, most of which Doug can answer in a few minutes.
