# Context tracker

What the bid agent needs to know to work like Doug in the real world, and how close we are on each piece. We update this page after every round of the loop.

Each piece has a checklist, and its percentage is the share of items checked. Items are not weighted, so a piece can look half done while the item that decides most bids is still missing. The "Biggest gap" column names that item.

## Where we are

As of October 28, 2026, after round 1.

| # | Piece | Done | Biggest gap | Who can close it |
| --- | --- | --- | --- | --- |
| 1 | Doug's facts | 41% | Insurance, references, and prices | Doug's files and inbox, then Doug confirms |
| 2 | Doug's judgment | 17% | Bid or pass, and why, on real RFPs | Only Doug, in conversation |
| 3 | Every open RFP in his lane | 38% | Registration on WEBS and Public Purchase | Doug registers, then the agent reads the alerts |
| 4 | The buyer's history | 40% | The big counties beyond King and Snohomish | Us, from public records |
| 5 | The competition | 33% | Who else bid, and how they scored | Us, by records request that Doug signs |
| 6 | What the buyer cares about | 50% | Staff reports for each target buyer | Us, from public records |
| 7 | What's coming | 50% | Which offices still run JustWare | Us, from public records |
| 8 | Doug's winning content | 50% | His past proposals | Doug's files |

Overall: 40%, the average of the eight.

## Checklists

### 1. Doug's facts

The truth about Cadocary that a bid claims. Detail is in `agent/memory/cadocary-facts/README.md`; the questions are in `docs/questions-for-doug.md`.

- [x] Name, federal ID numbers, and industry codes
- [x] Washington business license number
- [x] Founding date: October 10, 2024
- [x] Who signs: Doug, the only governor on the state record
- [x] SAM.gov registration active
- [x] Set-asides: small business only, no SBA certifications
- [x] Public contract history checked: none found
- [ ] SAM.gov expiry date
- [ ] WEBS and Public Purchase registration
- [ ] Washington women- and minority-owned certification (the state directory needs a person to pass a robot check)
- [ ] Insurance
- [ ] Security readiness for criminal justice data (CJIS), and where hosted work would run
- [ ] Past work: years, values, and permission to name each client
- [ ] How many offices use DocketBot and ClientCheck
- [ ] References who agreed to be named
- [ ] Staff and resumes
- [ ] Rates, price list, and lowest acceptable total

7 of 17.

### 2. Doug's judgment

How Doug decides. This is what lets the agent steer like him.

- [x] His stated rules: $1M to $5M, no military, software only, Washington first, at least 7 days, offshore staff allowed
- [ ] What the rules mean at the edges: total or per year, IT for a defense office, Veterans Affairs
- [ ] Bid or pass, and why, on 5 to 10 real RFPs
- [ ] His past bids and how they turned out
- [ ] Partners, competitors, and buyers who know him
- [ ] His corrections on one full run of the agent

1 of 6.

### 3. Every open RFP in his lane

Washington courts, prosecutors, public defense, jails, and probation, including every change to a posting.

- [x] Federal notices from SAM.gov, through Polina's tool
- [x] A map of where each big Washington buyer posts, in `docs/wa-bid-portals.md`
- [x] The courts office and Office of Public Defense pages, both readable without an account
- [ ] County websites with public lists, read on a schedule: Clark, Thurston, Kitsap, Yakima, Whatcom, and Benton
- [ ] WEBS registration
- [ ] Public Purchase registration
- [ ] Other portal accounts: OpenGov (Seattle, Pierce County), ProcureWare (Snohomish County, City of Spokane), King County, and Bonfire (Vancouver)
- [ ] An inbox the agent can read for bid alerts

3 of 8.

### 4. The buyer's history

What each buyer runs today, what it paid, and when the contract ends.

- [x] 12 comparable Washington contracts with prices, in `docs/wa-market-findings.md`
- [x] The public sources that work: council records, county and state contract lists, and the Office of Public Defense
- [ ] The same for the other big counties: Pierce, Spokane, Clark, Thurston, Kitsap, Yakima, and Benton
- [ ] Current system, vendor, and contract end date for each target buyer
- [ ] Connected to the agent as a research tool

2 of 5.

### 5. The competition

- [x] Who wins in Washington: Tyler, Journal Technologies, Karpel, Pine Technologies, Concourse Tech, GxP Partners, LegalServer, and Tribridge
- [x] Prices for 11 of those 12 contracts
- [ ] Who else bid on each
- [ ] How each bid was scored
- [ ] The winning proposals
- [ ] A records request sent. One is drafted for Snohomish County's court system award, not sent.

2 of 6.

### 6. What the buyer cares about

- [x] The agent reads each RFP's scoring
- [x] One buyer's reasons on record: King County picked its jail system on 10-year cost and fit to more than 900 requirements, not the lowest upfront price
- [ ] Staff reports for each target buyer
- [ ] Connected to the researcher

2 of 4.

### 7. What's coming

- [x] JustWare hosting ends in 2027, so every office on it has to move
- [x] Washington's public defender caseload limits started in January 2026
- [x] State public defense grants can pay for case management systems
- [x] District and city courts are moving to one statewide Tyler system, with all of them planned to be live in 2027. Those courts will not buy their own case systems, and DocketBot and ClientCheck read the old court sites the new system replaces.
- [ ] Which Washington offices still run JustWare
- [ ] Contract end dates at target buyers
- [ ] Council agendas and budget votes watched for new projects
- [ ] Connected to the agent

4 of 8.

### 8. Doug's winning content

- [x] Three case studies from the website
- [x] A proposal template, from Atharva
- [x] Product demo videos
- [ ] Doug's past proposals
- [ ] Results with numbers from Cadocary's own work. Today the only numbers are ones the clients reported.
- [ ] Product screenshots approved for proposals. Frames from the demo videos would do. We can't run DocketBot or ClientCheck ourselves: they are Windows apps that need a Washington court login.

3 of 6.

## Who can close what

- **Us, from public records:** pieces 4, 6, and 7, and most of 5 once a records request is sent.
- **Doug's accounts:** much of 1, the past-bids part of 2, the alerts for 3, and all of 8 sit in his email and files. A one-time link that lets the agent read them would close these without a long interview. That needs Doug's yes.
- **Only Doug, in conversation:** the rest of 2, his judgment. About an hour: walk through 5 to 10 RFPs, "bid or pass, and why".

## Loop log

### Round 1, October 28, 2026

- Checked the Washington Secretary of State, the SBA small business list (which mirrors SAM.gov), USAspending, data.wa.gov, and seven councils' records. Piece 1 went from 1 of 17 to 7 of 17.
- Found that no government contracts appear in public records. The qualifier should not claim past government performance.
- Found that SAM.gov lists codes such as janitorial and landscaping, beyond what the capability statement says. Added a question for Doug.
- Found the statewide court system move, which narrows Doug's market to prosecutors, public defense, jails, and probation, and may affect his products. Added to piece 7.
- Could not check the state's women- and minority-owned directory: it needs a person to pass a robot check.
- Mapped where 15 big Washington counties and cities, the courts office, and the Office of Public Defense post bids (`docs/wa-bid-portals.md`). Piece 3 went from 1 of 7 to 3 of 8.
- Found one open opportunity in Doug's lane: the courts office's information request for a statewide juvenile referral and detention system, due January 4, 2027. Also found three recent RFPs in his lane: Bothell (prosecutor case system), Kennewick (police and jail records), and the King County Prosecutor. These are good cases to walk Doug through for piece 2.
- Learned that DocketBot and ClientCheck can't be run here: they are Windows apps that need a Washington court login.
