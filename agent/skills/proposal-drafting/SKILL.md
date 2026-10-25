---
name: proposal-drafting
description: How to draft a complete, compliant government proposal for Cadocary from the qualification, the research, and the approved facts. Covers structure, claims, price, page limits, and the draft format. Use whenever the operator asks for a proposal draft.
---

# Drafting a proposal

Version 0. The nuances will be filled in from the study of real RFPs and winning proposals.

The goal is a proposal Doug can send after one read. It answers every requirement in the buyer's own order, fits the page limit, and builds on the reasons Cadocary is competitive. Once sent, it is legally binding.

## Read first

1. `qualification.json`:
   - the requirements list
   - the evaluation criteria and weights
   - the page limit and what counts toward it
   - the submission format and required forms
2. `research.json`: why Cadocary is competitive, and the price.
3. `/mnt/memory/cadocary-facts/`: everything you may say about Cadocary.
4. The RFP's instructions to proposers. They decide the structure.

## Rules

- **Claims about Cadocary.** Past projects, clients, references, staff, certifications, insurance, and numbers come only from the facts. Record the fact id for each in `cadocary_claims`. If a fact isn't there, don't write it. Add it to `open_items`.
- **References.** List a reference only if the facts record their permission to be named.
- **Price.** Use only `price_recommendation` from the research. If it is `null`, leave a clearly marked blank and add it to `open_items`.
- **Structure.** Follow the RFP's section order, headings, and numbering. Evaluators score against their own outline.
- **Mandatory requirements.** Answer each one explicitly, using the buyer's words.
- **Space.** Divide it by the scoring weights: more pages where more points are.
- **Contract terms.** Flag terms Doug might object to under `calls_for_doug`, such as liability caps, indemnity, data ownership, or insurance above current limits. Don't accept or reject them yourself.
- **Signatures and sworn statements.** Never sign, certify, or attest for Doug. Signatures, notarized forms, and certifications go in `open_items`.
- **Language.** Plain and specific: numbers, names, and dates from the facts. No filler words such as "cutting-edge", "seamless", or "robust".

## Format rules to check every time

- **Separate cost volume:** when one is required, the price never appears in the technical proposal.
- **Page limit:** check what counts. Cover letters, resumes, references, and appendices are often excluded, but not always.
- **Addenda:** acknowledge each one by number where the RFP asks.
- **Layout:** follow the RFP's font, size, margins, file type, and file naming rules.

## Files

Write to the output folder the operator names:

- `proposal.md`: the technical proposal
- `cost.md`: only when a separate cost volume is required
- `draft.json`: the format below

## Output: `draft.json`

```json
{
  "rfp_id": "",
  "files": {"proposal": "proposal.md", "cost": null, "forms": []},
  "compliance_matrix": [
    {"requirement_id": "R1", "section": "", "page": 0, "status": "met | partial | not_met | not_applicable", "note": ""}
  ],
  "page_count": {"estimated": 0, "method": "about 500 words per page until a renderer exists", "limit": null},
  "cadocary_claims": [{"text": "", "fact_id": ""}],
  "calls_for_doug": [{"topic": "price | references | exceptions | questions | assumptions | staffing", "choice_made": "", "alternatives": "", "why": ""}],
  "open_items": [""]
}
```

There must be one compliance row for every requirement in the qualification.
