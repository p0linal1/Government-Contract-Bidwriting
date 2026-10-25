---
name: rfp-qualifying
description: How to qualify a government RFP for Cadocary. Covers hard stops, judgment factors, every requirement and deadline, and the qualification format. Also how to check another agent's research or draft. Use whenever the operator asks you to qualify an RFP or check work.
---

# Qualifying an RFP

Version 0. It will be refined from the study of about 100 real RFPs (common items, things to look for, and rare but fatal traps).

The goal is two things: a pursue or pass decision with its reasons, and the full list of requirements that everything later is checked against.

## Read first

1. The whole RFP, every page, including attachments and addenda. Scope often hides in an attachment, and addenda change dates and page limits.
2. Cadocary's approved facts at `/mnt/memory/cadocary-facts/`: what it has built, what it holds, and what Doug wants.

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

| Factor | Ratings | What to look at |
| --- | --- | --- |
| knockouts | clear, at_risk, fails, unknown | Every mandatory requirement against the facts |
| incumbent | none, weak, strong, unknown | A current vendor named, "replace our existing system", integration with a named product |
| past_performance | strong, partial, none, unknown | Cadocary's products and projects in the facts that match the scope |
| evaluation_fit | favors_us, neutral, against_us, unknown | The scoring criteria and weights, and how they play to Cadocary's strengths |
| price_competitiveness | likely, unclear, unlikely | Lowest price wins, or best value, or qualifications only |
| competition_density | low, medium, high, unknown | How common the product category is and how many vendors serve it |

## Justice-sector requirements to look for

These are common in jail, court, and public defense software:

- CJIS security (the FBI's rules for criminal justice data), including policies, audits, and staff fingerprinting
- background checks for anyone with data access
- where data is hosted (in the US, in the state, or in a government cloud) and who owns it
- cyber and professional liability insurance above the usual limits
- integration with an existing jail, court, or records system named in the RFP
- public records and data retention rules
- accessibility standards

## Deadlines

Capture every one as written, with its page:

- buyer question deadline
- intent-to-submit
- pre-proposal meeting, and whether it is mandatory
- proposal deadline
- anything else

Copy the time zone exactly as written. If the RFP says "PST" on a date that falls in daylight time, say so in `note`.

## Output: `qualification.json`

```json
{
  "rfp_id": "",
  "decision": "pursue | pass",
  "decision_reasons": [{"reason": "", "cite": {"doc": "", "page": 0, "quote": ""}}],
  "hard_stops": [{"rule": "", "cite": {"doc": "", "page": 0, "quote": ""}}],
  "requirements": [
    {"id": "R1", "text": "", "kind": "mandatory | scored | format | form | submission", "cite": {"doc": "", "page": 0, "quote": ""}}
  ],
  "evaluation": {
    "method": "lowest_price | best_value | qualifications_only | unknown",
    "criteria": [{"name": "", "weight": "", "cite": {"doc": "", "page": 0, "quote": ""}}]
  },
  "deadlines": [{"kind": "questions | intent_to_submit | pre_proposal_meeting | proposal | other", "as_written": "", "mandatory": true, "note": "", "cite": {"doc": "", "page": 0, "quote": ""}}],
  "submission": {"method": "email | portal | paper | mixed", "copies": "", "separate_cost_volume": false, "signatures_required": false, "details": "", "cite": {"doc": "", "page": 0, "quote": ""}},
  "page_limit": {"pages": null, "what_counts": "", "cite": {"doc": "", "page": 0, "quote": ""}},
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

Every `quote` is the exact words from that page. Never paraphrase inside `quote`.

## Checking another agent's work

When the operator asks you to check work, start fresh. Don't lean on your earlier opinion of the RFP, and look for what is wrong, not what is right.

**Research** (`research.json`):

- Every number has a citation, or it appears under `educated_guesses`.
- Open at least five citations, including every one behind the value estimate, and confirm the quoted words are on that page.
- Every research category was searched or has a `not_found` entry.
- Comparables are like for like: the same kind of system, a similar buyer size, and the term and what was included are recorded.
- The confidence matches the evidence, using the definitions in the research skill.

**Draft** (`draft.json` and the proposal files):

- Every requirement in your `requirements` list appears in the compliance matrix with a section and page.
- The page count is within the limit, using the RFP's rules for what counts.
- Every claim about Cadocary maps to a fact id that exists in the facts.
- The price matches the research.
- Required forms are listed, and anything needing a signature is an open item for Doug.

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
