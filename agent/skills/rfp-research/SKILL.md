---
name: rfp-research
description: How to research a government RFP for Cadocary. Covers what the contract is worth, comparable past awards, the incumbent and competitors, whether the price is set by a product nobody has to build, and a recommended price, with a source for every number. Use whenever the operator asks for research on an RFP.
---

# Researching an RFP

Version 2. Refined from running it by hand on real solicitations and from Doug's own pricing and intake notes. It will keep changing as estimates get checked against awards whose prices are public.

The questions, in order of importance:

1. What did buyers pay for comparable work? (comparable past awards)
2. What is this contract worth?
3. Who holds the work now, and when does their contract end?
4. Is the price set by a product that already exists, or by the work of building one?
5. Who else is likely to bid?
6. What should Cadocary charge?

Doug's mentor warned: "Claude will do deep research and lie to you, especially if it can't find anything." An invented award, source, or quote is the worst possible outcome.

But "I found nothing" is not an acceptable answer either. Halting is a failure to be useful. **Always produce an estimate carrying its reasoning, its sources, and an explicit confidence level that a human can override.** A number labelled "MEDIUM confidence, built from these three lines, because the incumbent contract is not public" is a transparent judgment. A number with no basis is a lie. Never confuse the two, and never deliver neither.

## The method: four independent lines

A single number found in one place is not research. **The estimate's credibility comes from methods that do not share inputs converging on the same corridor.** Run all four lines. When one comes up empty, the others still bound the number.

**Line 1 — Can the buyer afford it?**
What this buyer actually spends on this kind of thing.
- *Local/state buyer:* audited financial statements, adopted budget, the relevant expense line (professional and contracted services, technology, IT). For a government or 501(c)(3), check the related-party transactions schedule — "None" means no incumbent lock-in, a named affiliate means the opposite.
- *Federal buyer:* the buying office's own obligation history, by fiscal year, from USASpending. Filter its awards to the matching purpose and total them per year. This is often stronger than a budget document because it is the actual spend on the actual line.
- Ask Doug's question: is this contract **material to this buyer, or a rounding error?** A rounding error means affordability sets no useful ceiling — say so and move on.

**Line 2 — The buyer's own procurement thresholds.**
The buyer's rules bracket the number before any comparable does.
- *Local/state:* purchasing policy, board-approval triggers, quote-versus-formal-solicitation cutoffs, and which federal-funds thresholds the RFP embeds. A formal, board-approved, multiyear RFP is self-evidently above those floors.
- *Federal:* which procedures the solicitation itself used. Being synopsised at all puts it above the micro-purchase threshold. A combined synopsis/solicitation with email quotes and award without discussions is the simplified-acquisition pattern and sits below the simplified acquisition threshold. A full source selection — multiple volumes, a page-limited technical volume, Section M evaluation factors, past-performance questionnaires — is apparatus the buyer would not build for a small purchase.
- Confirm current thresholds rather than reciting remembered ones; they move, and a legislative branch buyer (Senate, House) runs its own regulations, not the FAR.

**Line 3 — Comparable public awards, plus a unit-rate proxy.**
Real award values for the same kind of work, at buyers of similar size, in the last few years. Plus a per-unit rate where one exists — per seat, per student, per bed, per capita, per employee. **Label every proxy a proxy, never a match.**

**Line 4 — Bottom-up cost-to-deliver.**
What it costs Cadocary to staff and run this scope, at the blended rate from the facts sheet, with AI acceleration expressed as **fewer hours, never a discounted rate**. See `bid-pricing.md` thinking: raw scope hours, then a stated compression factor.

### Expect lines to die, and say which

Two or three live lines is the normal case, not a failure. Which line dies is predictable from the buy:

- A **product-access buy** (the bidder must already own a platform, a database, a media network) kills Line 4. There is no labour scope to estimate. Do not substitute a guess at the likely winner's cost structure — that is Line 3 wearing a different hat, and it fakes convergence.
- A **large-agency buyer** kills Line 1. An appropriation of hundreds of millions cannot bound a six-figure contract.
- A **first-time buy** kills the incumbent hunt, which caps confidence at MEDIUM however good the other lines are.

Record each dead line with the reason. A line reported as empty must be distinguishable from a line never attempted.

## Lead with the anchor, not the band

Report the **tightest-anchored figure first** — an appropriation or budget line for this specific purchase, or a real incumbent contract amount. The Low/Likely/High envelope is the outer boundary, not the headline. Leading with a wide band buries the one number that was actually sourced.

When no true anchor exists, say that plainly in the first line and lead with the strongest comparable instead.

## Price basis — decide this explicitly

This changes whether Cadocary can compete at all, and it is cheap to establish: do the comparable awards name repeat product vendors at stable prices?

- **COTS subscription.** Several vendors already hold a working product. The price is set by their marginal cost — seats, hosting, support — so it can sit below what a build costs. A builder cannot reach it. Record `cots_subscription`.
- **Custom build.** No existing product fits the requirement. Price is set by labour hours and Cadocary is competitive. Record `custom_build`.
- **Hybrid.** Configure and extend an existing platform. This is where the AI-compression advantage actually bites. Record `hybrid`.

A low-looking estimate on a COTS buy is not an error in the estimate. It is the market price of something nobody has to build. Say so, because the number alone misleads.

## Rules

- Every number carries a source: a URL plus the exact words from that page, or an RFP page plus the exact words.
- A number you cannot source goes under `educated_guesses`, with your reasoning. Nothing else is allowed.
- Record every search you run in `searches_run`, including the ones that found nothing.
- Compare like with like. For each comparable, record the term in years, what was included (licences, setup, hosting, support, services), and the buyer's size. **Annualise before comparing** — a $105,000 award over 24 months is $52,500 a year and belongs beside other annual figures.
- **Record what you excluded and why**, in `exclusions`. A comparable set is defined as much by what is thrown out. Dropping the wrong thing inflates an estimate by orders of magnitude.
- **Never compose an HTTP request.** Where a tool exists, call it; the fetches are scripted so the field names and the leakage cutoff are right every time. Web search and web fetch are for reading pages a tool does not cover — council packets, budget documents, vendor price lists, news.
- Never present a judgment as a settled fact, and never halt instead of estimating.

## Where to look

Cover every category. For each one that turns up nothing, add a `not_found` entry saying where you looked.

1. **The RFP itself:** budget, estimated value, number of users or seats, term and renewals, period of performance, line items, and any mention of the current system or contract. The scope often lives only in the attachments — fetch and read them, and treat an empty description field as "not yet read", not "nothing stated".
2. **The buyer's own records:**
   - council or board agendas, minutes, and staff reports that approved earlier purchases. The motion wording is near-standard: `"...award of a contract to <vendor>, in the amount of $<amount>, for <scope>"`. Packets also carry bid tabulations and the buyer's own pre-bid estimate.
   - adopted budgets, CIP lines, grant awards
   - bid tabulations from earlier rounds of this purchase
   - the current contract, if it is posted
3. **Washington sources:** WEBS award notices and its *Estimated Initial Contract Value* field, the list of vendors who downloaded the documents (look for the incumbent among them), Department of Enterprise Services master contracts, county and city contract lists.
4. **Federal awards:** the `search_federal_awards` tool, never usaspending.gov by hand. See the federal lane below.
5. **Comparable buyers:** agencies of similar size that bought the same kind of system in the last five years — award notices, staff reports, local news.
6. **Incumbent and competitors:** who holds the current contract and when it ends, which vendors bid on comparables, vendor case studies naming this buyer, and vendor published price lists (GSA schedule, state contract).

Stop when every category has a finding or a `not_found` entry and new searches stop turning up anything new.

## The federal lane: call the tool, don't compose HTTP

For SAM.gov solicitations the award data is good enough to trace a specific predecessor, which local records rarely allow. **Every fetch here is a tool call.** Do not build URLs or request bodies: USAspending's award search is a POST with a JSON body, which `web_fetch` cannot issue, and the field names are not guessable — `description[].body` not `.content`, the awardee under `data2.award.awardee`, `total` not `population`. Each of those was got wrong by hand before being fixed in the tool.

`search_federal_awards` takes one of the operations below. `scripts/search_awards.py` is the implementation, verified against live data.

> **Not wired yet.** The Researcher currently has only read, write, glob, grep, web search and web fetch (`agent/setup.py`), so it cannot run the script or issue a POST. Until `search_federal_awards` is hosted on our MCP endpoint, run the script in our code before the session starts and mount its `--json` output under `/mnt/session/uploads/findings/<rfp-id>/`. Do not work around this by having the agent fetch USAspending directly — it cannot, and what it produces instead will look like an answer.

| Operation | Arguments | Gives you |
| --- | --- | --- |
| `notice` | notice id | PSC and its build/buy family, NAICS, place of performance, response deadline with time zone, archived/cancelled, the attachment list with download links, and the description text |
| `related` | notice id | what SAM recorded as the award against that solicitation: `total_award_amount`, `recipient_count`, and each awardee with contract number and date |
| `history` | agency, office prefix, purpose keywords | that contracting office's obligations by fiscal year, filtered to a purpose — **this is line 1 for a federal buyer** |
| `search` | agency, PSC, office prefix, **cutoff** | the award pool with a percentile band, every award on or after the cutoff excluded |
| `chain` | agency, PSC, office prefix | predecessor references walked into a price history with the year-over-year change |

How to read what comes back:

- **Always pass `cutoff` = the solicitation's own response date.** Without it the award made against the solicitation under study sits in the pool used to predict it. On one test case the uncut median was $9,976,267 — the exact answer. The tool reports how many awards it excluded; if that count is zero on a closed solicitation, check the date.
- **A band is not an estimate.** `search` returns min/p25/median/p75/max because the distribution is informative. The median is not the answer — same office and same PSC covered airport turnstiles and software licences in the same pool. Confirm scope on each award before using it as a comparable.
- **`psc_family` decides whether Cadocary can compete on labour.** `D*` is IT services and application development; `7A*` is software licences; `7B`–`7K` is hardware. NAICS does not discriminate — a search on Cadocary's software NAICS returns medical equipment and health studies. Feed this into `price_basis`.
- **Delivery orders are a knockout.** When the pool is full of task or delivery orders against a vehicle the incumbent already holds, Cadocary cannot win at any price. The award IDs show it and the notice never will.
- **`chain` gives the trend, which beats a single prior value.** Roughly a third of awards name a predecessor. The tool's format guard rejects product names read as contract numbers (`ACCESSDATA`, `MAINTENANCE`) and reports what it rejected — read that list, because a rejection means a real predecessor reference went unresolved.
- **`related` is free ground truth.** On a closed solicitation it returns the actual award, which turns past solicitations into test cases with known answers.
- **Legislative branch buyers do not report to USAspending**, so `history` and `search` come back empty for the Senate or House. That is a structural gap, not a null result: the substitute is the Statement of Disbursements published by the Secretary of the Senate, at payee level. The office prefix is also meaningless for their solicitation numbering (`2027-R-007` is not a contracting office code).

## Traps that have actually fired

Each of these produced a confident, wrong answer in testing.

- **Keyword search on a product name.** Searching "Soteri" returned Soterix Medical and Soteria Solutions — wrong vendor, wrong product, wrong agency, at $1.98M. Match structurally first.
- **Title word-overlap scoring.** Matching a student enrollment platform on the words "management" and "platform" returned a $195M Palantir data platform and a $32M Deloitte construction platform. Overlap is not similarity.
- **The median of an office's awards.** Taking the median of same-office, same-PSC awards priced a solicitation against "Global Entry Airport Modernization". Same office and same product code can mean completely unrelated work.
- **A comparable set that includes the adjacent market.** Searching employee assistance programs returned $13M–$468M clinical service contracts for a solicitation that explicitly excluded clinical services. Two orders of magnitude, from one bad inclusion.
- **Skipping Lines 1 and 2.** Pricing a four-component bundle as "richer than any single comparable, therefore above the top of the range" doubled an estimate, until the buyer's own expense line showed it had never spent that much in a year.
- **Trusting a source's own search.** A portal search for `case management` returned fifteen irrelevant meetings because it OR-matched single words. Quote phrases, or download and match in code.

## Confidence

Use only these words, with these meanings. They are Doug's definitions and they govern.

- **high:** a real incumbent contract amount, or an appropriation or budget line for this specific purchase. Nothing else earns high.
- **medium:** several independent lines agree on a corridor.
- **low:** only one line, or only weak lines. Doug will see it as a guess.

A first-time buy with no public incumbent amount caps at medium, however well the other lines converge.

## Price

- Build the price from Doug's price list in `/mnt/memory/cadocary-facts/`. Never invent a rate.
- Give line items with quantity, unit, rate, and amount, and make sure the totals add up.
- Explain how the total compares to the comparables and where it sits in the corridor. If it falls outside the corridor, explain why.
- When the price basis is `cots_subscription`, state plainly that Cadocary's cost-to-deliver sits above the market price, and by how much. That is the fact the qualifier needs.
- If there is no price list in the facts yet, set `price_recommendation` to `null`, give the range the comparables support, and say a price list is missing.

## Output: `research.json`

```json
{
  "rfp_id": "",
  "anchor": {
    "figure": 0, "what_it_is": "", "why_tightest": "",
    "cite": {"url": "", "quote": "", "retrieved_at": ""}
  },
  "value_estimate": {
    "low": 0, "likely": 0, "high": 0,
    "basis": "stated_in_rfp | budget_document | award_records | comparables | educated_guess",
    "confidence": "high | medium | low",
    "how_built": ""
  },
  "price_basis": {
    "kind": "cots_subscription | custom_build | hybrid",
    "why": "",
    "cadocary_cost_vs_market": ""
  },
  "lines": [
    {"line": "affordability | thresholds | comparables | cost_to_deliver",
     "status": "live | dead",
     "implied_low": 0, "implied_high": 0,
     "reason_if_dead": "",
     "how_built": ""}
  ],
  "convergence": {"low": 0, "high": 0, "lines_agreeing": 0, "disagreements": ""},
  "comparables": [
    {"buyer": "", "title": "", "awarded_on": "", "awardee": "", "amount": 0, "term_years": 0,
     "annualized": 0, "included": "", "scope_match": "strong | partial | weak",
     "is_proxy": false, "why_comparable": "",
     "cite": {"url": "", "quote": "", "retrieved_at": ""}}
  ],
  "exclusions": [{"what": "", "amount": 0, "why_excluded": ""}],
  "incumbent": {
    "name": null, "contract_amount": null, "ends_on": null,
    "hunt_outcome": "found | searched_not_found | not_searchable",
    "where_looked": "",
    "cite": {"url": "", "quote": "", "retrieved_at": ""}
  },
  "predecessor_chain": [
    {"award_id": "", "amount": 0, "start": "", "end": "", "names_prior": "", "change_pct": 0}
  ],
  "likely_competitors": [{"name": "", "why": "", "cite": {"url": "", "quote": "", "retrieved_at": ""}}],
  "price_recommendation": {
    "line_items": [{"item": "", "quantity": 0, "unit": "", "rate": 0, "amount": 0}],
    "total": 0,
    "rationale": ""
  },
  "searches_run": [{"category": "rfp | buyer_records | washington | federal | comparables | incumbent_competitors", "where": "", "query": "", "results_found": 0}],
  "not_found": [{"looked_for": "", "where_looked": ""}],
  "educated_guesses": [{"claim": "", "reasoning": ""}],
  "open_questions": [{"question": "", "why_it_matters": "", "how_to_answer": ""}]
}
```

## Definition of done

- All four lines attempted. Each is `live` with a figure, or `dead` with a reason. None silently skipped.
- The incumbent hunt ran, and `hunt_outcome` distinguishes "searched and found nothing" from "not searchable".
- `anchor` is filled, or its absence is stated in `how_built` and confidence is at most medium.
- `price_basis.kind` is set, with the reasoning.
- Every number has a source, or sits in `educated_guesses` with its reasoning.
- `exclusions` records anything dropped from the comparable set.
- No `high` confidence without a real incumbent amount or a purchase-specific budget line.
- `open_questions` names what would most improve the estimate, and how to get it.
