# Context tracker

What the bid agent needs to know to work like Doug in the real world, and how close we are on each piece. We update this page after every round of the loop.

Each piece has a checklist, and its percentage is the share of items checked. Items are not weighted, so a piece can look half done while the item that decides most bids is still missing. The "Biggest gap" column names that item.

## Where we are

As of October 28, 2026, after round 2.

| # | Piece | Done | Biggest gap | Who can close it |
| --- | --- | --- | --- | --- |
| 1 | Doug's facts | 41% | Insurance, references, and prices | Doug's files and inbox, then Doug confirms |
| 2 | Doug's judgment | 17% | Bid or pass, and why, on real RFPs | Only Doug, in conversation |
| 3 | Every open RFP in his lane | 38% | bidkit's code, which already reads his bid alerts and logs into WEBS and Public Purchase | Doug shares bidkit |
| 4 | The buyer's history | 50% | Prices and contract end dates for half the offices | Us, by records request |
| 5 | The competition | 57% | Scores and winning proposals | Us, by records request |
| 6 | What the buyer cares about | 60% | Staff reports for each target buyer | Us, from public records |
| 7 | What's coming | 75% | Watching council agendas for new projects | Us, once it's connected to the agent |
| 8 | Doug's winning content | 50% | His past proposals | Doug's files |

Overall: 49%, the average of the eight.

## When the loop is done

The agent is ready when it passes a backtest. It gets past Washington RFPs whose results are public, with the results hidden: Kitsap 2022-114, Whatcom 22-09, Lewis County 2021, Snohomish County's 2026 court system, and King County's 2018 jail system. For each, it predicts who won and roughly at what price, and says whether Cadocary could have competed. We score it against what really happened. Research rounds stop when the score stops improving.

Doug still decides what is true about Cadocary and how much risk he takes. Market judgment is the agent's job, and it can know more there than any one person tracks.

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
- [ ] bidkit's code. Doug's own pipeline already reads his bid-alert inbox and logs into WEBS and Public Purchase, so he is probably registered on both already.

3 of 8.

### 4. The buyer's history

What each buyer runs today, what it paid, and when the contract ends.

- [x] 12 comparable Washington contracts with prices, in `docs/wa-market-findings.md`
- [x] The public sources that work: council records, county and state contract lists, and the Office of Public Defense
- [x] Current system and vendor for most justice offices in the ten biggest counties and the Tri-Cities, in `docs/wa-buyers.md`
- [ ] Price and contract end date for each. About half are found.
- [ ] Pierce and Spokane counties in detail. Their sites block automated reads.
- [ ] Connected to the agent as a research tool

3 of 6.

### 5. The competition

- [x] Who wins in Washington: Karpel takes prosecutor systems, with Journal Technologies second. Also Tyler, Pine Technologies, Concourse Tech, GxP Partners, LegalServer, EIS, and Tribridge
- [x] Prices for about 25 contracts, in `docs/wa-market-findings.md` and `docs/wa-buyers.md`
- [x] Who bid on the recent prosecutor systems: Kitsap and Whatcom drew Karpel and Journal, Pend Oreille drew nobody
- [x] One full score sheet: Kitsap, Karpel 4.29 to Journal 3.81
- [ ] Scores for the rest
- [ ] The winning proposals
- [ ] Records requests sent. One is drafted for Snohomish County; Kitsap, Whatcom, Lewis, and the Clark County Prosecutor are next. Waiting on whose name they go under.

4 of 7.

### 6. What the buyer cares about

- [x] The agent reads each RFP's scoring
- [x] One buyer's reasons on record: King County picked its jail system on 10-year cost and fit to more than 900 requirements, not the lowest upfront price
- [x] Scoring weights for four more: Kitsap (cost 25 of 100), King County's KC001265 (demos 30 and price 22 of 130), Bothell, and the state courts office's juvenile request, which asks for off-the-shelf fit and similar customers
- [ ] Staff reports for each target buyer
- [ ] Connected to the researcher

3 of 5.

### 7. What's coming

- [x] JustWare: the vendor ended support in June 2021. "Hosting ends in 2027" comes only from Snohomish County's papers. Prosecutors leaving it mostly go to Pine Technologies
- [x] Washington's public defender caseload limits started in January 2026
- [x] State public defense grants can pay for defender-only case systems. Kitsap used its 2024 money on case management tools, and six more counties planned technology spending for 2025
- [x] District and city courts are moving to one statewide Tyler system, with all of them planned to be live in 2027. Those courts will not buy their own case systems, and DocketBot and ClientCheck read the old court sites the new system replaces.
- [x] Which Washington offices still run JustWare: Snohomish County until July 2027, and probably Yakima County's prosecutor and assigned counsel
- [x] Contract end dates for the next openings: Kitsap's jail (November 30, 2026), Benton's juvenile center (December 31, 2026), Benton's public defense (January 31, 2027), Benton's prosecutor (April 30, 2027), and Kitsap's public defense (April 2027)
- [ ] Council agendas and budget votes watched for new projects
- [ ] Connected to the agent

6 of 8.

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

### Round 2, October 28, 2026

- Four research helpers covered who runs what in the ten biggest counties and the Tri-Cities, who won the recent prosecutor RFPs, and where JustWare is still used. The results are in `docs/wa-buyers.md`.
- The biggest finding: most of Doug's lane is under his $1 million floor. Prosecutor and defender systems in mid-size counties cost $80,000 to $500,000. Only jail systems and the biggest counties pass $1 million. His answer to question C1 decides how much of the market is open.
- Best openings: Kitsap County's jail system (contract ends November 30, 2026), Clark County's 1990s prosecutor system, Yakima County's offices still on JustWare, and Benton County's prosecutor and juvenile center.
- Corrected the JustWare dates in piece 7.
- Learned that Doug's own bid pipeline, bidkit, already reads his bid alerts and logs into WEBS and Public Purchase. Asked for its code (question B7 on his answer page).
- Set the finish line: a backtest on five past Washington RFPs with known results.
- Overall went from 40% to 49%.
