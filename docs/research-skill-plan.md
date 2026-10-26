# Plan: research and test before building the research skill

The research step answers two things for an RFP already in hand: **what is this contract worth**, and **who held it before**. This page is the plan for proving that can be done before any skill gets written. It covers SAM.gov federal RFPs only — see "Scope" at the end.

Read `docs/context.md` for background and `docs/reviews/engineering.md` for the agent architecture this fits into.

## What the skill outputs

The research skill emits facts. It never decides whether Doug should bid — that is the qualifier's job, and a research step that editorialises makes the qualifier's call harder to audit.

| Field | Rule |
| --- | --- |
| **Price** | The prior awarded value for this same work, with its award ID. If none is found, a band from the estimation subagent, carrying its method and confidence. Never a bare number. |
| **Components** | What is being bought, read out of the attachment text: period of performance, line items, deliverables, and blocking requirements (clearance, FedRAMP, CMMC, brand-name, sole-source). |
| **Prior awardee** | Company, award ID, amount, dates, and how the match was made. |
| **Open questions** | Required whenever any field is unknown. |

`unknown` is a first-class answer. A blank question list beside an unknown field is a schema violation that code rejects. The qualifier can act on "unknown, and here is why"; it cannot act on an invented number.

## Phase 1: build a ground-truth set, for free

You cannot measure research without known answers. They do not need to be collected by hand.

SAM.gov's `relatedopportunities` endpoint returns `totalAwardAmt` and `recipientCount`. So for a solicitation that has already been awarded, the true answer is already published. Hide it, run research on the solicitation alone, and compare.

- Pull closed solicitations in the profile's NAICS and PSC families.
- Keep the ones that have a recorded award amount and at least one readable attachment.
- Spread them across build (`D*`) and buy (`7A*`) PSCs, across agencies, and across size.
- Target 40. **Hold 20 back** as a test set the skill is never written from, matching decision 13 in `docs/context.md`.
- Write the inputs and the answers to separate files, so a blind run is the default and revealing the answer takes a deliberate step.

Filter the junk first. SAM returns notices flagged `is_active=true` whose response deadline has already passed — one in the current pull was two months stale. The set needs a real date check before anything else.

## Phase 2: measure the data ceiling before writing a prompt

There is no point asking an agent to find what is not published. On the 20 training cases, measure mechanically:

- what share have readable attachment text. The API's `description` field came back empty on all six RFPs checked by hand, so scope lives only in the attachments, and some of those are image-only and need OCR
- what share state a dollar value anywhere in their documents
- what share have a findable prior award, broken down by which method found it

If prior awards turn out to be findable only a third of the time, the skill is mainly an estimator and the subagent is the main event rather than the fallback. That number decides where the effort goes, and it is cheap to get.

## Phase 3: race the matching methods against ground truth

Title word-overlap produces confident nonsense. Tested by hand, it matched a student enrollment platform to a $195M Palantir data platform, and matched the vendor "Soteri" to Soterix Medical, a medical device company. So candidate matchers get scored, not assumed.

| Method | Note |
| --- | --- |
| Title keyword | Baseline. Known bad; include it to quantify how bad. |
| Agency + PSC band | Gives scale, not identity. |
| Agency + PSC + contracting-office prefix | The office code sits in the solicitation number, e.g. `283213...`. |
| Predecessor reference in award descriptions | Found 9 of 15 on live SSA data. Strongest so far. |
| SAM `parentNoticeId` and related notices | Present in the search payload, unused today. |

Score **precision ahead of recall**. A wrong incumbent is worse than no incumbent, because the qualifier will act on it. Require a contract-number format guard: the predecessor regex once returned `ACCESSDATA`, a product name, where a contract number belonged.

## Phase 4: specify and test the estimation subagent

When no prior award is found, a subagent researches further and estimates. It returns a band, a method, and a confidence — never a point value. Methods in priority order, each step down lowering confidence:

1. a value stated in the solicitation documents
2. same contracting office, same PSC, historical distribution
3. same PSC across agencies, normalised by scope size (seats, users, sites)
4. unit build-up from the components (hours by role, or per-seat times count)
5. refuse, and return questions

Test it on ground-truth cases where the true value is known but withheld, and measure two things together:

- **containment**: does the band contain the true value
- **band width**: a $10,000 to $10,000,000 band contains everything and tells the qualifier nothing

Both, or neither. Containment on its own is a metric you can win by being useless.

## Phase 5: adversarial tests, before anything ships

- **Fabrication.** Include cases with genuinely no findable answer. The skill must return unknown plus questions. One invented number or citation fails the release, the bar `docs/reviews/engineering.md` already sets.
- **The Soteri trap**, as a named permanent test case. Pass means it does not report Soterix Medical.
- **Citation check by code.** Every award ID reported must exist, and its amount must match what USASpending returns.

## Phase 6: write the skill

Draft it around whatever won Phase 3, then run the held-back 20 and record that as the baseline. Nothing ships afterwards that worsens the fabrication rate.

## Open decisions

| # | Decision | Why it matters |
| --- | --- | --- |
| 1 | What containment rate passes | Sets the bar for Phase 4 |
| 2 | Can the qualifier act on a band, or does it need one number | If one number, estimation is a much harder problem and we should know now |
| 3 | How wide a band is still useful | A band nobody can use is the same as no answer |
| 4 | May the subagent use paid data when free sources fail | Changes the cost model and the build |

## Scope

This plan holds for SAM.gov federal RFPs, where award data is good enough to trace a predecessor contract by ID. The Washington city and county RFPs Doug also sells into have no equivalent record, and need the comparables approach instead. One method does not cover both, and pretending otherwise is how the research step starts inventing numbers.
