# Government-Contract-Bidwriting

Tools for a small business to find federal contract opportunities it can actually win, and
draft a response to them.

## Step 1: pull matching opportunities from SAM.gov

`scripts/fetch_sam_opportunities.py` reads a vendor profile (NAICS + PSC codes) and pulls every
active SAM.gov opportunity carrying one of those codes.

```bash
python3 scripts/fetch_sam_opportunities.py --profile profiles/example.json
```

Stdlib only — no pip install, no API key. It calls the same public endpoints sam.gov's own
search UI uses:

| | |
|---|---|
| search | `https://sam.gov/api/prod/sgs/v1/search/?index=opp&naics=<code>&is_active=true` |
| detail | `https://sam.gov/api/prod/opps/v2/opportunities/<notice_id>` |

Both require `Accept: application/hal+json` or they answer `406 Not Acceptable`. The search
response is thin (title, dates, org, description excerpt), so each notice gets a second detail
call for the fields that matter when triaging a bid: full NAICS list, PSC, set-aside, archive
date, place of performance, and the contracting officer's name and email.

Options:

- `--no-enrich` — skip the per-notice detail calls (seconds instead of minutes, but no
  set-aside or contact info)
- `--include-inactive` — also return closed notices, for past-performance research
- `--workers N` — concurrent detail requests (default 6)

### Output

Writes `data/opportunities.json` (full records, with description excerpts) and
`data/opportunities.csv` (one row per notice, sorted by response deadline), both keyed on
SAM's `notice_id` and carrying a `matched_by` field naming which of the profile's codes
surfaced it.

`data/` is gitignored — solicitations turn over constantly, so regenerate the pull rather than
reading a stale one out of the repo.

## Step 2: cut it down to what's actually biddable

SAM's `is_active=true` does not mean "open for bids" — most active notices are Award Notices for
contracts already given out, and many more are past their response deadline but not yet archived.
On the Cadocary profile, 2,513 active notices contained only **74** a vendor could still respond to.

```bash
python3 scripts/filter_open.py --days 30
```

Keeps the solicitation-shaped notice types (Solicitation, Combined Synopsis/Solicitation,
Presolicitation, Sources Sought, RFI), drops cancelled notices and past deadlines, adds a
`days_left` column, and writes `data/open_opportunities.json` / `.csv` sorted by urgency.

- `--days N` — only deadlines within N days
- `--include-no-deadline` — keep notices with no response date

## Step 3 (not built yet): rank and draft

The open list still carries noise, because a broad code like NAICS 541519 ("Other Computer
Related Services") surfaces hardware and parts solicitations alongside software work. Ranking
each notice against the profile's capability list, then drafting a response, is the next step.

### Vendor profiles

A profile holds the NAICS codes, PSC codes and capability list from a company's SAM.gov
registration or capability statement. Copy `profiles/example.json` and fill in your own:

```bash
cp profiles/example.json profiles/mycompany.json
python3 scripts/fetch_sam_opportunities.py --profile profiles/mycompany.json
```

Real profiles are gitignored (`profiles/*.json`, with `example.json` the committed template) so
a company's registration details stay out of the repo.
