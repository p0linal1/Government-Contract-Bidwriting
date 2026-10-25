---
name: rfp-qualifying
description: How to decide whether Cadocary should pursue a government RFP, from the reader's RFP sheet and Cadocary's facts. Covers hard stops, judgment factors, and the qualification format. Also how to check another agent's research or draft. Use whenever the operator asks you to qualify an RFP or check work.
---

# Qualifying an RFP

Version 0. It will be refined from the study of about 100 real RFPs (common items, things to look for, and rare but fatal traps).

The goal is a pursue or pass decision, with the reasons a busy owner can act on. Only RFPs you mark `pursue` go on to research and drafting, which are the expensive steps.

## Read first

1. **The reader's RFP sheet** (`sheet.json`): the requirements, deadlines, eligibility rules, scoring, submission, and clues, each with its page and quote. Decide from the sheet. Open the RFP itself only to confirm a quote that drives a hard stop or a close call.
2. **Cadocary's approved facts** at `/mnt/memory/cadocary-facts/`: what it has built, what it holds, and what Doug wants.

Doug's preferences: software and IT work, Washington buyers, $25,000 and up, and at least 7 days to respond.

## Hard stops

Any one of these means `pass`, with the quote and page:

- The proposal deadline leaves less than 7 days.
- A mandatory pre-proposal meeting, site visit, or intent-to-submit deadline has already passed.
- A license, certification, registration, or insurance level is required that the facts show Cadocary does not hold and cannot get in time.
- The submission method can't be met in time, such as hand delivery of paper copies.
- An eligibility rule Cadocary cannot meet, such as a set-aside it doesn't qualify for or required on-site staff it doesn't have.

If the facts don't say either way, it is not a hard stop. List it under `unknowns`.

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

Weigh the `security_and_compliance` items, such as CJIS, background checks, and hosting location, against what the facts say Cadocary has. A requirement the facts don't cover is an unknown, not a pass.

## Output: `qualification.json`

```json
{
  "rfp_id": "",
  "decision": "pursue | pass",
  "headline": "One sentence a busy owner can act on.",
  "decision_reasons": [{"reason": "", "requirement_ids": [], "cite": {"doc": "", "page": 0, "quote": ""}}],
  "hard_stops": [{"rule": "", "cite": {"doc": "", "page": 0, "quote": ""}}],
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
- Every claim about Cadocary maps to a fact id that exists in the facts.
- The price matches the research.
- Every form in the sheet's `required_forms` is listed, and anything needing a signature is an open item for Doug.

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
