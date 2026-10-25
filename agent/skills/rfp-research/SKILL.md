---
name: rfp-research
description: How to research a government RFP for Cadocary. Covers what the contract is worth, comparable past awards, the incumbent and competitors, and a recommended price, with a source for every number. Use whenever the operator asks for research on an RFP.
---

# Researching an RFP

Version 1. It will be refined from the study of real RFPs and from checking estimates against awards whose prices are public.

The questions, in order of importance:

1. What did buyers pay for comparable work? (comparable past awards)
2. What is this contract worth?
3. Who holds the work now, and when does their contract end?
4. Who else is likely to bid?
5. What should Cadocary charge?

Doug's mentor warned: "Claude will do deep research and lie to you, especially if it can't find anything." City and county award records are scattered, so "not found" will often be the honest answer. That answer is expected and accepted. An invented award, source, or quote is the worst possible outcome.

## Rules

- Every number carries a source: a URL plus the exact words from that page, or an RFP page plus the exact words.
- **A search result is a lead, not a source.** Open the page with web fetch and copy the quote from what the fetch returned. A snippet from the search results never goes in `quote`.
- **The quote is copied, never retyped.** Keep it short (one or two sentences) and make sure it contains the number or name it supports. If the page would not load, needed a login, or was a scanned PDF with no text, it is not a source. Log it in `not_found`.
- **Nothing from memory.** You may know or think you know that a vendor serves a buyer, or what a system costs. Use that only to decide where to search. It goes in the output only once a fetched page says it.
- A number you cannot source goes under `educated_guesses`, with your reasoning. Nothing else is allowed.
- Record every search you run in `searches_run`, including the ones that found nothing.
- Compare like with like. For each comparable, record the term (years), what was included (licenses, setup, hosting, support, services), and the buyer's size.
- Pull data from an API or a downloadable list when one exists, rather than reading pages by hand.
- Never contact anyone. If a records request or a question to the buyer would help, list it under `follow_ups` for Doug.

## Step 1: read the RFP before searching

Read every RFP file the operator names, and the qualification if there is one. Write down these anchors first, because every search builds on them:

- **The buyer:** exact legal name, type (city, county, court, jail, public defense office, state agency), and state. Watch for buyers with the same name in other states, such as Clark County, Washington and Clark County, Nevada.
- **The system:** what kind it is, in the RFP's own words and in two or three common synonyms. For example, "case management system" also appears as "CMS", "defender case management", and "indigent defense software". "Jail management system" also appears as "JMS" and "offender management".
- **The size:** users or seats, caseload, beds, sites, the buyer's population, and anything else the price will scale with.
- **The shape:** term and renewals, hosted or on premises, data migration, training, and support.
- **Clues:** any budget, estimate, grant, current system, or current vendor the RFP names. The RFP is often the best source you will get.

## Step 2: where to look

Cover every category. For each one that turns up nothing, add a `not_found` entry saying where you looked.

1. **The RFP itself:** budget, estimated value, number of users or seats, term and renewals, and any mention of the current system or contract. Check addenda and the questions-and-answers document too. Buyers often reveal the incumbent or a budget there.
2. **The buyer's own records:** this is where most city and county prices are.
   - Council or board agendas, minutes, and staff reports. A purchase over a few thousand dollars usually needs a vote, and the staff report states the vendor, the amount, and the term. Many Washington cities and counties post these on Legistar (`<buyer>.legistar.com`), Granicus, CivicClerk, or a CivicPlus "Agenda Center". Search phrases like `"<buyer>" council "<system type>" contract`, `"authorize" "<vendor>" agreement`, and `"<system type>" "staff report"`.
   - Claims or voucher approval lists in council packets. They show payments to each vendor, which reveals the incumbent and what it is paid each year.
   - Adopted budgets and capital plans: lines for software, maintenance, or the replacement project.
   - Bid tabulations from earlier rounds of this purchase.
   - The current contract and its amendments, if they are posted. Amendments often carry the running total.
3. **Washington sources:**
   - WEBS, the state's bid site (`pr-webs-vendor.des.wa.gov`), for earlier solicitations and awards from this buyer. Some pages need a vendor login. If so, log it in `not_found`.
   - Statewide master contracts from the Department of Enterprise Services (`apps.des.wa.gov/DESContracts`), including NASPO ValuePoint software contracts. Cities and counties may buy from these, and their price sheets give real rates.
   - State agency payments to vendors (`fiscal.wa.gov`), when the buyer or a comparable is a state agency.
   - Population from the Office of Financial Management's April 1 estimates (`ofm.wa.gov`), for sizing buyers.
4. **Federal awards:** for federal buyers or federally funded projects, search usaspending.gov. It has an open API (`api.usaspending.gov/api/v2/search/spending_by_award/`); use it rather than reading pages.
5. **Comparable buyers:** counties or cities of similar size that bought the same kind of system in the last five years. Look in their council records (as in category 2), award notices, and local news. Buyers in Oregon, Idaho, and similar states count when Washington has too few.
6. **Incumbent and competitors:**
   - who holds the current contract, and when it ends
   - which vendors bid on comparables (bid tabulations and staff reports often list every bidder)
   - vendor case studies or press releases naming this buyer. Treat a vendor's own figures as the vendor's claim, and say so in `why_comparable`.
   - Vendors to search for in justice software include Tyler Technologies, Journal Technologies, Motorola Solutions, CentralSquare, Karpel, and LegalServer. These are search terms, not facts. Name one as incumbent or competitor only with a fetched page.

Plan on roughly 25 to 60 searches. Stop when every category has a finding or a `not_found` entry and new searches stop turning up anything new.

## Step 3: make comparables comparable

Raw contract amounts mislead. A three-year license with setup is not one year of support. For each comparable:

- Record what the amount is in `amount_kind`. **awarded** means the contract amount. **not_to_exceed** means a ceiling, which is often far above what was paid. **paid** means payments actually made. **budgeted** means money set aside, not spent. **amended_total** means the running total after amendments.
- Split one-time costs (setup, migration, training) from recurring costs (licenses, hosting, support) when the source allows it.
- Work out `annual_amount`: the recurring cost per year, plus one-time costs spread over the term. Show the arithmetic in `how_computed`. If the source doesn't allow a split, say so and divide the total by the term.
- Record the buyer's population (or seats, beds, or caseload, whichever the price scales with) in `size`, with its own citation.

## Value estimate

- Use the buyer's stated value or budget if there is one. That is `stated_in_rfp` or `budget_document`.
- Otherwise build it from comparables. Scale each comparable's `annual_amount` by size, multiply by this RFP's term, and take the middle as `likely` and the spread as `low` to `high`. Show every step in `how_built`.
- With fewer than two usable comparables, the basis is `educated_guess`, the range must be wide, and the confidence is low.

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

## Traps

- **Not-to-exceed amounts** read like prices. They are ceilings.
- **Cumulative amendments.** "Amendment 3, increasing the total to $X" is the total, not the amendment.
- **Hardware and other vendors' work** bundled in (servers, scanners, interfaces). Note it in `included`.
- **Grant-funded purchases** may be sized to the grant, not to the need.
- **Old awards.** Note the year. Prices more than five years old are weak evidence.
- **Two buyers, one name.** Confirm the state on every page.
- **The vendor's own page** may round up or count a whole region. Prefer the buyer's records.

## Before you write the file

Check your own work. The qualifier will check it again, opening at least five citations.

- Every number in the file is either next to a `cite` or listed in `educated_guesses`.
- Every `quote` came from a page you fetched in this run, and contains the number or name it supports.
- Every category in Step 2 appears in `searches_run`, and those with no result appear in `not_found`.
- The line items add up to the total, and each `annual_amount` matches its `how_computed`.
- The confidence follows the definitions above, not your feeling.

## Output: `research.json`

```json
{
  "rfp_id": "",
  "anchors": {
    "buyer": "", "buyer_type": "", "state": "",
    "system": "", "synonyms": [""],
    "size": "", "term_years": 0, "shape": "",
    "clues": [{"clue": "", "cite": {"file": "", "page": 0, "quote": ""}}]
  },
  "value_estimate": {
    "low": 0, "likely": 0, "high": 0,
    "basis": "stated_in_rfp | budget_document | award_records | comparables | educated_guess",
    "confidence": "high | medium | low",
    "how_built": ""
  },
  "comparables": [
    {"buyer": "", "title": "", "awarded_on": "", "awardee": "", "amount": 0,
     "amount_kind": "awarded | not_to_exceed | paid | budgeted | amended_total",
     "term_years": 0, "included": "", "annual_amount": 0, "how_computed": "",
     "size": {"measure": "population | seats | beds | caseload", "value": 0, "cite": {"url": "", "quote": "", "retrieved_at": ""}},
     "scope_match": "strong | partial | weak", "why_comparable": "",
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
  "educated_guesses": [{"claim": "", "reasoning": ""}],
  "follow_ups": [{"action": "records_request | question_for_buyer", "to": "", "what": "", "why": ""}]
}
```

For RFP citations, `cite` is `{"file": "", "page": 0, "quote": ""}` instead of a URL.
