---
name: rfp-qualifying
description: How to decide whether Cadocary should pursue a government RFP, from the reader's RFP sheet and Cadocary's facts. Covers hard stops, judgment factors, and the qualification format. Also how to check another agent's research or draft. Use whenever the operator asks you to qualify an RFP or check work.
---

# Qualifying an RFP

Version 0. It will be refined from the study of about 100 real RFPs (common items, things to look for, and rare but fatal traps).

The goal is a pursue or pass decision, with the reasons a busy owner can act on. Only RFPs you mark `pursue` go on to research and drafting, which are the expensive steps.

## Read first

1. **The reader's summary** (`summary.md`), then the **RFP sheet** (`sheet.json`): the requirements, deadlines, eligibility rules, scoring, submission, and clues, each with its page and quote. Decide from the sheet. Open the RFP itself only to confirm a quote that drives a hard stop or a close call.
2. **Cadocary's facts** at `/mnt/memory/cadocary-facts/`: what it has built, what it holds, and what Doug wants. The company-facts skill says how to choose and cite them for this RFP.

Doug's preferences:

- software and IT work. Custom software contracts suit Cadocary best.
- contracts priced between $1 million and $5 million. $5 million is a hard limit.
- no military applications
- Cadocary uses offshore developers, so contracts that allow them are better
- Washington buyers preferred, and federal buyers allowed
- at least 7 days to respond

## Hard stops

Any one of these means `pass`, with the quote and page:

- The proposal deadline leaves less than 7 days.
- A mandatory pre-proposal meeting, site visit, or intent-to-submit deadline has already passed.
- A license, certification, registration, or insurance level is required that the facts show Cadocary does not hold and cannot get in time.
- The submission method can't be met in time, such as hand delivery of paper copies.
- An eligibility rule Cadocary cannot meet, such as a set-aside it doesn't qualify for or required on-site staff it doesn't have.
- **Military or defense work.** The buyer is the Department of Defense, an armed service (including the Coast Guard and National Guard), or a defense agency, or the system is for military or defense use. Veterans Affairs and other civilian agencies are not military.
- **Value outside Doug's range.** The RFP states a value or budget for the whole contract below $1 million or above $5 million, which is Doug's hard limit. Use the total for the base term and every option. If the RFP gives only a yearly amount, multiply it by the term and show the arithmetic.

A not-to-exceed amount or contract ceiling is a cap, not the value. A ceiling below $1 million is a hard stop, because the contract can't be worth more. A ceiling above $5 million is not; treat the value as not stated.

If the facts don't say either way, it is not a hard stop. List it under `unknowns`. The same goes for work that may or may not be military: list it, and note it under `factors.knockouts`.

**Before you call any hard stop, look for another route the RFP allows:**

- reselling or partnering for a required product
- teaming or subcontracting for a missing qualification
- a later deadline in an amendment

If the RFP allows a route and the facts are silent on whether Cadocary can take it, it is an unknown, not a stop.

### When the value isn't stated

It is not a stop. Set `value_check.status` to `unknown`, and put any clues from `budget_clues` (seats, term, the current contract) in `value_check.note`. The researcher estimates the value next, and the operator passes on the RFP if that estimate falls outside the range.

Never pass, even partly, on your own guess of the value. Only a value the RFP states counts against the range, and only the researcher's sourced estimate counts after that.

### RFPs written for one company

These are don't-bid unless Cadocary is the company named. Quote the words that show it.

- **Sole-source notice:** a notice of intent to award to a named vendor, or a justification for only one source.
- **Renewal of a named product:** a renewal, maintenance, or license purchase of a product another company makes.
- **Brand name only:** a purchase that says "brand name only", or names a product with "or equivalent" while the specifications match only that product.

When the RFP invites other sources to show they can meet the need, say so in `decision_reasons`, and treat it as a normal judgment call instead.

### Drafts, pre-solicitations, and RFIs

- **A draft RFP or pre-solicitation with no proposal due date:**
  - If it otherwise fits, decide `pursue` and set the headline to "Watch for the final RFP".
  - Put the response window for comments or questions in `questions_for_buyer`.
- **An RFI or sources sought notice:**
  - Answering is cheap, and it can shape a later solicitation, so the bar is fit, not winning.
  - Decide `pursue` when the work is squarely in Cadocary's lane. The drafter then writes a short capability response, not a proposal.
  - Otherwise, decide `pass`.

## Judgment factors

Rate each one with the fixed words below, and give evidence for each rating.

| Factor | Ratings | What to look at in the sheet |
| --- | --- | --- |
| knockouts | clear, at_risk, fails, unknown | Every `mandatory` requirement and every `eligibility` rule, against the facts |
| incumbent | none, weak, strong, unknown | `incumbent_clues`: a current vendor named, "replace" language, integration with a named product |
| past_performance | strong, partial, none, unknown | `scope` against Cadocary's products and projects in the facts |
| evaluation_fit | favors_us, neutral, against_us, unknown | `evaluation` criteria and weights, and how they play to Cadocary's strengths |
| price_competitiveness | likely, unclear, unlikely | Lowest price wins, or best value, or qualifications only |
| competition_density | low, medium, high, unknown | How common the product category is and how many vendors serve it |

Weigh the `security_and_compliance` items, such as CJIS, background checks, and hosting location, against what the facts say Cadocary has. A requirement the facts don't cover is an unknown, not a pass. Look for staffing limits too: US persons or citizens only, no offshore or foreign-national access, or work and data access inside the US. Cadocary's team includes offshore developers (`prefs.offshore_staff`). Check whether the facts show a way to meet the clause, such as only named US staff touching production data. If it plainly cannot, it is a hard stop. If it is unclear, rate knockouts `at_risk` and add the clause to `questions_for_buyer`.

## Output: `qualification.json`

```json
{
  "rfp_id": "",
  "decision": "pursue | pass",
  "headline": "One sentence a busy owner can act on.",
  "decision_reasons": [{"reason": "", "requirement_ids": [], "cite": {"doc": "", "page": 0, "quote": ""}}],
  "hard_stops": [{"rule": "", "cite": {"doc": "", "page": 0, "quote": ""}}],
  "value_check": {"status": "in_range | below_range | above_range | unknown", "stated_total": null, "note": "", "cite": {"doc": "", "page": 0, "quote": ""}},
  "factors": {
    "knockouts": {"rating": "", "evidence": "", "note": ""},
    "incumbent": {"rating": "", "name": "", "evidence": "", "note": ""},
    "past_performance": {"rating": "", "fact_ids": [], "note": ""},
    "evaluation_fit": {"rating": "", "note": ""},
    "price_competitiveness": {"rating": "", "note": ""},
    "competition_density": {"rating": "", "note": ""}
  },
  "questions_for_buyer": [{"question": "", "why_it_matters": "", "due_as_written": ""}],
  "unknowns": [""]
}
```

Every `quote` is the exact words from that page, copied from the sheet or the RFP. Never paraphrase inside `quote`.

## Checking another agent's work

When the operator asks you to check work, start fresh. Don't lean on your earlier opinion of the RFP, and look for what is wrong, not what is right.

**Research** (`research.json`):

- Every number has a citation, or it appears under `educated_guesses`.
- Open at least five citations, including every one behind the value estimate, and confirm the quoted words are on that page.
- Every research category was searched or has a `not_found` entry.
- Comparables are like for like: the same kind of system, a similar buyer size, and the term and what was included are recorded.
- The confidence matches the evidence, using the definitions in the research skill.

**Draft** (`draft.json` and the proposal files):

- Every requirement in the sheet's `requirements` list appears in the compliance matrix with a section and page.
- The page count is within the sheet's `page_limit`, using its rule for what counts.
- Every claim about Cadocary maps to a fact id that exists in the facts, and says no more than that fact. A client's reported result must still read as the client's.
- The price matches the research.
- Every form in the sheet's `required_forms` is listed, and anything needing a signature is an open item for Doug.
- No template markers are left in the proposal (`{{`, `}}`, `<!--`), and every `[MISSING: ...]` and `[SIGNATURE: ...]` marker appears in `open_items`.
- `commitments` lists every price, validity period, schedule, person, certification, reference, and contract exception in the proposal.

Write `check-<target>-<round>.json`:

```json
{
  "target": "research | draft",
  "round": 1,
  "verdict": "pass | revise | block",
  "issues": [{"severity": "fatal | major | minor", "field": "", "problem": "", "evidence": "", "fix": ""}],
  "spot_checks": [{"claim": "", "source": "", "confirmed": "yes | no | unreachable"}]
}
```

Use `block` only for something no revision can fix, such as an invented source the agent defends or a fatal requirement Cadocary cannot meet.
