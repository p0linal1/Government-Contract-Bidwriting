# Task: Doug's facts sheet

Build one structured record of everything true about Cadocary, which Doug approves once. The agent may only claim what is on it. All three plan reviews put this first, for three reasons:

- A sent bid is legally binding, so a made-up reference, certification, or price is the most expensive mistake the agent can make.
- It is how the agent stays on track when nobody is watching. Doug answers each question once, ever, instead of once per bid.
- The drafter has nothing true to say without it.

Read `docs/context.md` first for the background.

## What done looks like

1. Doug has answered every section below, or marked it "unknown", in about a 30 to 60 minute interview.
2. The real facts live in a gitignored file, following this repo's `profile.json` pattern. A `facts.example.json` with the same shape and made-up values is committed.
3. Doug has read the finished sheet and approved each section.
4. The three past awards for the research test (section 12) are collected.

## Shape of each fact

Every fact needs the same five parts, so code can check claims against the sheet:

- `id`: a stable key, such as `insurance.general_liability`
- `value`: the fact itself
- `source`: where it came from, such as "Doug, interview, Oct 25" or a document name
- `approved`: true only after Doug has read it
- `expires`: the expiry date for anything that runs out, such as insurance, registrations, and certifications

`profile.json` already holds the legal name, NAICS codes, set-aside eligibility, capabilities, and exclusions. Agree with Alyssa and Polina whether the facts sheet extends that file or sits beside it. Don't keep the same fact in two places.

**Built:** the sheet sits beside the profile, in a gitignored `facts.json`. Fact ids use the same names as the agent's Cadocary Facts memory store (`agent/memory/cadocary-facts/README.md`): `company.*`, `product.*`, `prefs.*`, plus one prefix per remaining section below, such as `insurance.*` and `references.*`. The company facts `profile.json` already holds (legal name, UEI, CAGE, website, location, NAICS, PSC, capabilities) are not repeated. Start from `facts.example.json`, which has every section below with made-up or unknown values. `python3 scripts/check_facts.py` rejects a malformed sheet: a missing part, an empty value instead of "unknown", insurance or a certification with no expiry, a reference with no `permission_date`, or a fact the profile already holds. It also lists what is still unknown or unapproved, which is the agenda for the next talk with Doug. `--usable` prints only the approved, known, unexpired facts. That output, and nothing else, is what the agent gets. The section 12 awards go in the same file under `research_test` and never reach the agent. (Proposed by the facts lane; Alyssa and Polina to confirm.)

## Sections to fill

1. **Company identity**
   - legal name and address
   - Washington business license (UBI) number
   - SAM.gov registration status and expiry
   - WEBS and Public Purchase vendor registration
   - years in business, size, and small business status
   - NAICS codes
   - who can sign bids
2. **Certifications**
   - small business, minority- or woman-owned (state OMWBE), veteran, and any others
   - anything Doug has applied for but doesn't hold yet
3. **Insurance:** for each type, the limit, the carrier, and the expiry. Ask whether a buyer can be added as an additional insured.
   - general liability
   - professional (errors and omissions)
   - cyber
   - auto
   - workers' comp
4. **Security and compliance**
   - CJIS readiness: written policies, and whether staff can pass fingerprint background checks
   - SOC 2 or similar
   - where data is hosted (including government cloud)
   - how long data is kept
   - accessibility standards met
5. **Products:** for each of the five products:
   - what it does
   - who uses it today, with live customers if any
   - how it is hosted and what it is built with
   - which kinds of RFP requirements it covers
6. **Past performance:** for each project or contract:
   - client, dates, dollar value, and scope
   - the result, in numbers if possible
   - whether we may name the client
7. **References:** name, title, organization, contact details, which projects they speak to, and the date they agreed to be named. A reference without recorded permission is never used.
8. **Team:** each person's role, experience, resume, background checks or clearances, and how many hours they have available.
9. **Pricing (private):**
   - hourly rate by role
   - license, setup, and hosting prices
   - the lowest price Doug will accept
   - usual payment terms
   - discounts he offers

   This never goes in a shared or public file.
10. **Preferences**
    - bids he wants: currently software and IT, Washington, $25,000 and up, at least 7 days to respond
    - work he never bids on
    - the farthest he will travel for on-site work
    - contract terms he won't accept (liability, data ownership, insurance demands)
11. **Approved text:** a company overview paragraph, standard approach statements, and answers he reuses. These are text the drafter may copy word for word.
12. **For the research test:** three past Washington awards Doug knows the price of. For each, get the buyer, what was bought, roughly what was paid, and a link to the RFP if he has one. The research step gets only the RFP, and his answer is the key.
13. **Paperwork on file:** W-9, certificate of insurance, signed standard forms, and capability sheets. Note where each file lives.

## What we already know

| Fact | Status |
| --- | --- |
| The five products and what they do (see `docs/context.md`) | From Doug. Confirm the details and live customers |
| Website: cadocary.com | From Doug |
| Bids he wants: software and IT, Washington, $25,000 and up, at least 7 days | From Doug |
| Currently bidding on jail software | From Doug |
| Has a bid inbox, an FGA subscription, and logins for WEBS and Public Purchase | From Doug (inside bidkit) |
| Insurance at $1,000,000 general liability and $1,000,000 cyber | Made up for the prototype. Do not use until Doug confirms |
| Rate of $175 an hour, blended | Made up for the prototype. Do not use until Doug confirms |
| No small business certification and no CJIS documentation on file | Made up for the prototype. Ask |

## Also ask Doug

Answered Oct 25:

- [x] What is FGA, and can we see one sample breakdown? **Forget FGA. It uses SAM.gov, which this repo already covers.**
- [x] How many RFPs a month fit him, how many does he submit, and how many hours does each take? **Not relevant. We are building only the research skill.**
- [x] Does he have past bids, won or lost, with the winning price? **Yes, two.** Collect them into `facts.json` under `research_test` (gitignored; prices stay private).
- [x] Has he tried GovDash, Sweetspot, or Cleatus? If he quit one, why? **No.**
- [x] Is one early message OK when a buyer-question deadline or mandatory meeting would otherwise be missed? **No.** The agent sends nothing early.
- [x] Can bidkit's code go in this repo? **Yes.** Still keep its saved portal logins out.

## Rules while doing this

- Record "unknown" rather than guessing. An empty field is safe; an invented one is not.
- Keep real values out of git. Commit only the example file.
- Write down the source for every fact as you collect it. Filling sources in later doesn't happen.
- Later, the approved sheet is loaded read-only into a Managed Agents memory store, and only our code ever writes to it (see `docs/managed-agents.md`, section 11).
