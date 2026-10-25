---
name: rfp-research
description: How to research a government RFP for Cadocary. Covers what the contract is worth, comparable past awards, the incumbent and competitors, and a recommended price, with a source for every number. Use whenever the operator asks for research on an RFP.
---

# Researching an RFP

Version 0. It will be refined from the study of real RFPs and from checking estimates against awards whose prices are public.

The questions, in order of importance:

1. What did buyers pay for comparable work? (comparable past awards)
2. What is this contract worth?
3. Who holds the work now, and when does their contract end?
4. Who else is likely to bid?
5. What should Cadocary charge?

Doug's mentor warned: "Claude will do deep research and lie to you, especially if it can't find anything." City and county award records are scattered, so "not found" will often be the honest answer. That answer is expected and accepted. An invented award, source, or quote is the worst possible outcome.

## Rules

- Every number carries a source: a URL plus the exact words from that page, or an RFP page plus the exact words.
- A number you cannot source goes under `educated_guesses`, with your reasoning. Nothing else is allowed.
- Record every search you run in `searches_run`, including the ones that found nothing.
- Compare like with like. For each comparable, record the term (years), what was included (licenses, setup, hosting, support, services), and the buyer's size.
- Pull data from an API or a downloadable list when one exists, rather than reading pages by hand.

## Where to look

Cover every category. For each one that turns up nothing, add a `not_found` entry saying where you looked.

1. **The RFP itself:** budget, estimated value, number of users or seats, term and renewals, and any mention of the current system or contract.
2. **The buyer's own records:**
   - council or board agendas, minutes, and staff reports that approved earlier purchases
   - adopted budgets
   - bid tabulations from earlier rounds of this purchase
   - the current contract, if it is posted
3. **Washington sources:**
   - award notices on WEBS
   - state master contracts (Department of Enterprise Services)
   - county and city contract lists
4. **Federal awards:** usaspending.gov, for federal buyers or federally funded projects.
5. **Comparable buyers:** counties or cities of similar size that bought the same kind of system in the last five years. Look at award notices, staff reports, and local news.
6. **Incumbent and competitors:**
   - who holds the current contract, and when it ends
   - which vendors bid on comparables
   - vendor case studies naming this buyer

Stop when every category has a finding or a `not_found` entry and new searches stop turning up anything new.

## Confidence

Use only these words, with these meanings:

- **high:** the buyer states the value, or two or more independent award records agree within 25 percent.
- **medium:** one award record, or comparables that match on scope and buyer size.
- **low:** anything else. Doug will see it as a guess.

## Price

- Build the price from Doug's price list in `/mnt/memory/cadocary-facts/`. Never invent a rate.
- Give line items with quantity, unit, rate, and amount, and make sure the totals add up.
- Explain how the total compares to the comparables.
- If there is no price list in the facts yet, set `price_recommendation` to `null`, give the range the comparables support, and say a price list is missing.

## Output: `research.json`

```json
{
  "rfp_id": "",
  "value_estimate": {
    "low": 0, "likely": 0, "high": 0,
    "basis": "stated_in_rfp | budget_document | award_records | comparables | educated_guess",
    "confidence": "high | medium | low",
    "how_built": ""
  },
  "comparables": [
    {"buyer": "", "title": "", "awarded_on": "", "awardee": "", "amount": 0, "term_years": 0,
     "included": "", "scope_match": "strong | partial | weak", "why_comparable": "",
     "cite": {"url": "", "quote": "", "retrieved_at": ""}}
  ],
  "incumbent": {"name": null, "contract_amount": null, "ends_on": null, "cite": {"url": "", "quote": "", "retrieved_at": ""}},
  "likely_competitors": [{"name": "", "why": "", "cite": {"url": "", "quote": "", "retrieved_at": ""}}],
  "price_recommendation": {
    "line_items": [{"item": "", "quantity": 0, "unit": "", "rate": 0, "amount": 0}],
    "total": 0,
    "rationale": ""
  },
  "searches_run": [{"category": "rfp | buyer_records | washington | federal | comparables | incumbent_competitors", "where": "", "query": "", "results_found": 0}],
  "not_found": [{"looked_for": "", "where_looked": ""}],
  "educated_guesses": [{"claim": "", "reasoning": ""}]
}
```
