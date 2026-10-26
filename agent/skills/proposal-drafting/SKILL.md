---
name: proposal-drafting
description: How to draft a complete, compliant government proposal for Cadocary from the qualification, the research, and the approved facts. Covers structure, claims, price, page limits, and the draft format. Use whenever the operator asks for a proposal draft.
---

# Drafting a proposal

Version 1. It now drafts from `templates/proposal.md`, modeled on the structure and style of Doug's past proposals. The nuances will be filled in from the study of real RFPs and winning proposals.

The goal is a proposal Doug can send after one read. It answers every requirement in the buyer's own order, fits the page limit, and builds on the reasons Cadocary is competitive. Once sent, it is legally binding.

## Read first

1. `sheet.json` (the reader's RFP sheet):
   - the requirements list
   - the evaluation criteria and weights
   - the page limit and what counts toward it
   - the submission method, format rules, and required forms
   - amendments to acknowledge, and contract terms to flag
2. `qualification.json`: why Cadocary should pursue it, and the judgment factors.
3. `research.json`: why Cadocary is competitive, and the price.
4. `/mnt/memory/cadocary-facts/`: everything you may say about Cadocary.
5. The RFP's instructions to proposers. They decide the structure.
6. `templates/proposal.md` in this skill: the starting point for every proposal.

## The template

Copy `templates/proposal.md` to `proposal.md` in the output folder and fill it in. The template's comment at the top explains its markers.

- **The RFP's outline wins.** If the RFP prescribes sections, rename, reorder, and renumber the template's sections to match it exactly, keeping their content and style. Add any section the RFP requires that the template lacks. Drop template sections the RFP doesn't want and that earn no points.
- **`{{fact:...}}`** comes only from the facts. If a fact is missing or "unknown", write `[MISSING: <fact id>]` in place and add it to `open_items`. Never fill a blank with something plausible.
- **`{{rfp:...}}`** comes from `sheet.json` or the RFP, in the buyer's own words.
- **`{{price:...}}`** comes only from `price_recommendation`. Line items with hourly or one-time units go in the one-time table, per-year items in the recurring table. Recompute every total and confirm it matches the research. If they differ, use the research and flag the mismatch in `open_items`.
- **`WRITE` comments** are instructions for prose. Follow them, then delete them.
- **`IF` comments** mark optional blocks. Keep a block only when its condition holds.
- **`[SIGNATURE: Doug signs]`** stays as written. Signing is Doug's.
- When you are done, no `{{`, `}}`, or `<!--` is left in `proposal.md`. Only `[MISSING: ...]` and `[SIGNATURE: ...]` markers remain, and each is in `open_items`.

## House style

From Doug's past proposals. Keep it.

- **Bold lead-ins.** Most paragraphs in the approach, security, and involvement sections start with a short bold label: "**Data Conversion.** ..."
- **Understand the buyer first.** The approach opens with the buyer's current system, how they operate, and their two to four real priorities, using the RFP's own numbers.
- **Cite the buyer's documents.** Refer to clarifications by addendum and question number ("Addendum 3 confirms ..."). Say plainly which items an addendum removed and that they are not included.
- **Point to the workbooks.** End technical subsections by naming the buyer's attachment that holds the line-by-line answers.
- **Honest framing.** Present adjacent products and projects as relevant experience, and say what they are not: "presented as relevant interoperability experience rather than as prior RMS implementation experience." Never imply a deployment, certification, or authorization the facts don't record.
- **Show the arithmetic.** Each price line is hours times the rate. Assumptions are listed. Exceptions are written as requests subject to negotiation.
- **Close each part cleanly.** Where a part ends partway down a page, add *"The remainder of this page has been intentionally left blank."*

## Rules

- **Claims about Cadocary.** Past projects, clients, references, staff, certifications, insurance, and numbers come only from the facts. Record the fact id for each in `cadocary_claims`. If a fact isn't there, don't write it. Add it to `open_items`. The company-facts skill says which facts fit this RFP and how to word the question for Doug.
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

- `proposal.md`: the technical proposal, filled from the template
- `cost.md`: only when a separate cost volume is required. It holds the template's Part V, and `proposal.md` then has no prices at all.
- `draft.json`: the format below. The operator builds Doug's review from it, so `commitments` and `submission_checklist` must be complete.

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
  "commitments": [{"kind": "price | validity | schedule | personnel | certification | reference | exception", "text": "", "section": "", "page": 0}],
  "calls_for_doug": [{"topic": "price | references | exceptions | questions | assumptions | staffing", "choice_made": "", "alternatives": "", "why": ""}],
  "submission_checklist": [{"item": "", "file_name": "", "needs_signature": false, "note": ""}],
  "open_items": [""]
}
```

There must be one compliance row for every requirement in the sheet. `commitments` lists everything that binds Cadocary once sent: the price, how long it is valid, the schedule, each person committed, each certification or compliance claim, each reference named, and each contract exception requested. `submission_checklist` lists every file, form, and copy the buyer wants, with the buyer's file naming rule.
