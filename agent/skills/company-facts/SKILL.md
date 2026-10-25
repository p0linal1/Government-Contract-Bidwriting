---
name: company-facts
description: How to use Cadocary's facts for one particular bid. Covers which facts hold for every bid, how to choose past work, references, staff, approach, and pricing basis from the RFP sheet, how to cite fact ids, what to do with unapproved facts, and how to ask Doug for a missing fact. Use whenever you qualify an RFP or draft a proposal.
---

# Using Cadocary's facts for one bid

Version 0.

The facts are in `/mnt/memory/cadocary-facts/README.md`. Nothing about Cadocary may be claimed unless a fact there says it.

Doug's rule: no standard set of facts fits every RFP. Which past projects, references, staff, and claims to use depends on the bid. Read every fact once, then choose for this RFP.

## Two kinds of facts

**Stable:** the same in every bid. Use them wherever the RFP asks.

- identity: `company.*`, such as the legal name, location, website, and email
- registrations: the UEI, CAGE code, NAICS, and PSC codes
- products: `product.*`, what each one does, how it runs, and its listed price

**Chosen per RFP:** pick these for this bid only.

- past performance: `work.*` and `product.*`
- references
- staff
- approach: `service.*` and the `approach` and `built` facts of the closest projects
- pricing basis

## Choosing for this RFP

Work from the reader's sheet (`sheet.json`).

1. **List what the buyer scores and what it is buying.** Take `evaluation.criteria` with their weights, every `scored` requirement, and the `scope` items.
2. **Match facts to each one.** For each criterion and scope item, find the facts that answer it most directly. A closer match beats a bigger one. Judge closeness by:
   - the same kind of buyer and users. A Washington public defense office is closest to DocketBot.
   - the same kind of job, such as document automation, a booking platform, or an assistant grounded in source data
   - the same rules or data, such as Washington court systems, JIS, CPSR audits, or Medicare plan data
   - the same delivery: hosted, desktop, or mobile
3. **Use the two or three closest projects,** not all of them. Put the strongest one where the most points are. A loose example on a heavily weighted criterion loses points; say less instead.
4. **Meet the RFP's own rules.** If it asks for a number of projects or references, a minimum value, a time window, or government clients, use only facts that meet the rule. If none do, that is a missing fact (below). For the qualifier, it is also a knockout at risk.
5. **Watch for facts that cut against the bid.** DocketBot and ClientCheck are Windows desktop apps, not cloud services. If the RFP requires a hosted system, never present them as one. Say what they are, and note the gap.
6. **Record the choice.** The qualifier names the chosen fact ids and why in `factors.past_performance`. The drafter adds a `calls_for_doug` entry (topic `references` or `staffing`) when it chose between close alternatives.

For each kind:

- **Past performance.** SpendLogic, Hotels4Truckers, and PURLPal are client projects that Cadocary designed and built. Never call them Cadocary products, and never say Cadocary sold them to anyone. DocketBot, ClientCheck, and Highlighter are Cadocary's own products.
- **References.** Use only a reference whose fact records the person's permission and the date they gave it. There are none yet.
- **Staff.** Use only people the facts name, with only the roles and experience the facts give. There are none yet.
- **Approach.** Build it from the `service.*` facts and the approach of the closest project, told in the RFP's terms. Describe how Cadocary works only the way the facts do.
- **Pricing basis.** Rates and prices come only from Doug's price list in the facts. There is none yet. The $30/month DocketBot and ClientCheck licenses are retail prices for one user. Never use them as a bid price, and never multiply them out for a buyer's seat count.

## Staying inside the fact

- **A client's result stays the client's.** Write "SpendLogic reports that its customers achieve a 20:1 ROI", never "Cadocary delivers a 20:1 ROI".
- **A client's credential is not Cadocary's.** The FedRAMP version and the "50 years of GovCon experience" belong to SpendLogic's platform. The facts show no FedRAMP authorization, certification, or years of experience for Cadocary.
- **Numbers exactly as written.** No rounding up, and no totals, user counts, or dates the facts don't give.
- **No stretching.** "Designed and implemented for one client" never becomes "deployed for agencies". Desktop apps never become a platform.
- **Words from the site** are marketing copy. Use them as facts about what Cadocary built and offers, and leave out superlatives such as "better and cheaper at once" unless the RFP asks for a value statement.

## Citing fact ids

- Every claim about Cadocary carries the id of each fact it rests on, copied exactly from the facts file. Never make up an id.
- **Qualifier:** list ids in `factors.past_performance.fact_ids`, and name the id in a `decision_reasons` entry when a fact drives the reason.
- **Drafter:** one `cadocary_claims` entry per fact behind each claim: `text` is the claim as it reads in the proposal, and `fact_id` is one id. A sentence resting on two facts gets two entries with the same text.
- The checker compares each claim to its fact. A claim that says more than its fact fails the check.

## Unapproved facts

No fact is approved yet. Each row says `approved: no` until Doug reads it.

- **Qualifying** may rely on unapproved facts.
- **A draft** may use them, but each one must be listed for Doug's confirmation before he sends. Add one `open_items` line: "Confirm these facts before sending: " followed by every unapproved fact id the draft relies on.

## When the bid needs a fact that isn't there

The RFP asks for something, such as an insurance limit, a certification, a reference, a resume, a past government contract, or a rate, and no fact covers it.

- Never fill it in, estimate it, or write vague words that imply it.
- In the proposal, leave a marked blank: `[NEEDED FROM DOUG: professional liability limit]`.
- Add a question for Doug to `open_items` (drafter) or `unknowns` (qualifier). Start it with "Question for Doug:", word it so he can answer in one line, and end with the requirement id it serves.
  - Good: "Question for Doug: Do you carry professional liability insurance of at least $2,000,000 per claim, and with which carrier? (R14)"
  - Good: "Question for Doug: Name one government client who will act as a reference for DocketBot, with their title, phone, and email. (R22)"
  - Bad: "Question for Doug: Tell us about your insurance."
- Ask for exactly what the RFP needs: the number, the yes or no, or the name. One question per missing fact.
- For the qualifier, a missing fact is an unknown, not a hard stop.
