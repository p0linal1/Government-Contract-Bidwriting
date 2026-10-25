<!--
Doug's review: the one document he reads before deciding. The operator fills it from packet.json,
sheet.json, qualification.json, research.json, and draft.json after both checks. How to fill it is in SKILL.md,
under "Doug's review". Every number keeps its source. No {{ }} or comments are left when done.
For a pass, keep only the headline, "Why pass", and "Checks"; see "Pass version" at the end.
-->

# {{packet:headline}}

**{{rfp:buyer}} · {{rfp:title}} · {{rfp:solicitation_number}}**
Proposal due **{{deadline:proposal.as_written}}**: {{deadline:days_left}} days from today.
Your reading time: about {{review:reading_minutes}} minutes.

**Your choice:** Send · Fix this (say what) · Pass (one line on why)

## What you would be committing to

Read this first. Once sent, these bind Cadocary.

| Commitment | What the draft says | Where |
| --- | --- | --- |
| Price | {{price:total}}, made of {{price:summary}} | Pricing, p. <n> |
| Price valid for | {{rfp:validity_days}} days | Cover letter |
| Schedule | {{rfp:performance_period}} | Schedule, p. <n> |
| People committed | <!-- names and roles from draft.json commitments --> | Team, p. <n> |
| Certifications and compliance claimed | <!-- each, with its fact id --> | Security, p. <n> |
| References named | <!-- each, with the date they agreed --> | References, p. <n> |
| Contract exceptions requested | <!-- each, or "none" --> | Exceptions, p. <n> |

## Why Cadocary is competitive

<!-- From packet.why_competitive. One line each, with its source in parentheses. At most five. -->

- {{packet:why_competitive[].reason}} ({{packet:why_competitive[].source}})

## What it is worth

**{{research:value_estimate.likely}}** expected, range {{research:value_estimate.low}} to {{research:value_estimate.high}}, **{{research:value_estimate.confidence}} confidence**.
Basis: {{research:value_estimate.basis}}. <!-- one sentence from how_built -->

| Comparable | Buyer | Year | Amount | Per year | Source |
| --- | --- | --- | --- | --- | --- |
| {{research:comparables[].title}} | {{research:comparables[].buyer}} | {{research:comparables[].awarded_on}} | {{research:comparables[].amount}} ({{research:comparables[].amount_kind}}) | {{research:comparables[].annual_amount}} | [link]({{research:comparables[].cite.url}}) |

<!-- If there are no comparables, say so in one line, and say the value is a guess. -->
Incumbent: {{research:incumbent.name}}, contract ends {{research:incumbent.ends_on}}.
Our price vs. the comparables: <!-- one sentence from price_recommendation.rationale -->

## Risks

<!-- From packet.risks, worst first, with source. -->

- {{packet:risks[].risk}} ({{packet:risks[].source}})

## Calls I made for you

Change any of these with "Fix this".

| Topic | What I chose | Other options | Why |
| --- | --- | --- | --- |
| {{packet:calls_for_doug[].topic}} | {{packet:calls_for_doug[].choice_made}} | <!-- alternatives --> | {{packet:calls_for_doug[].why}} |

## Before you can send

Only you can do these. Each one blocks sending until it is done.

- [ ] <!-- every open item: signatures, notarized forms, [MISSING: ...] facts, price list gaps -->

## Dates

| What | As written in the RFP | Page |
| --- | --- | --- |
| {{deadline[].kind}} | {{deadline[].as_written}} | {{deadline[].page}} |

<!-- Flag any time zone note from sheet.json deadlines, for example "PST" on a daylight-time date. -->

## How to submit

From sheet.json submission, required_forms, and format_rules. You submit, never the agent.

- Method: {{rfp:submission.method}}. {{rfp:submission.details}}
- Files and copies: <!-- each file to send, with the buyer's naming rule, and whether the price goes separately -->
- Forms: <!-- each required form, and whether it needs a signature -->
- Submit a few hours early, then re-check the buyer's page for late addenda, and save the receipt.

## Checks

- Research check: **{{packet:checks.research}}** ({{review:research_rounds}} round(s))
- Draft check: **{{packet:checks.draft}}** ({{review:draft_rounds}} round(s))
- Requirements covered: {{review:requirements_met}} of {{review:requirements_total}} (compliance matrix in draft.json)
- Page count: {{draft:page_count.estimated}} of {{draft:page_count.limit}} allowed

## Files

- Proposal: `{{packet:files.proposal}}`
- Cost volume: `<!-- if separate -->`
- Qualification: `{{packet:files.qualification}}` · Research: `{{packet:files.research}}`

<!-- Pass version:

# Pass: <reason in a few words>

**<buyer> · <title> · <solicitation number>**

## Why pass

<one line per reason, each with its quote and page, or "no-go, could not verify" with the check issues>

## Checks

<the check results that led here, if any>
-->
