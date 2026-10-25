# Government-Contract-Bidwriting

An agent that finds the federal contract opportunities a small business can actually respond to.
Each day it pulls SAM.gov for your NAICS codes, throws out everything already awarded, expired, or
set aside for someone else, and ranks what's left against what your business does.

## Quick start

You need Python 3.9+ (standard library only) and [Claude Code](https://claude.com/claude-code).

```bash
cp profile.example.json profile.json     # then set your NAICS codes — the only file you edit
bin/sam-research.sh                      # or, inside Claude Code: /sam-research
open data/report.md
```

`profile.json` holds your NAICS codes, optional PSC codes, the set-asides you qualify for, and a
plain-language list of capabilities the agent scores against. It is gitignored, so your codes never
land in the shared repo.

No Claude Code? `bin/sam-research.sh --no-agent` does the pull and filtering and leaves an unranked
`data/open_opportunities.csv`.

## What gets filtered out, and where

Most of what SAM.gov calls "active" is not something you can bid on. On a four-code software
profile, 2,298 active notices held 112 open for response. The rest were award notices, expired
solicitations, and justifications.

| Removed | How |
|---|---|
| Award notices, justifications, surplus sales | Never requested: the search asks only for responsive notice types |
| Deadlines already passed | Never requested: the search asks for `response_date` from now |
| Solicitations still listed as active after an award was posted | Each notice's related notices are checked for an award |
| Set-asides you aren't eligible for | `set_aside_eligibility` in `profile.json` |
| Cancelled notices | Filter |
| Notices you already reviewed | Shown, but only new or amended notices are re-scored and marked **NEW** |

Because the filtering happens in the search, a run fetches detail for ~100 notices, not ~2,500, and
finishes in about ten seconds before scoring.

RFIs have no notice type of their own on SAM.gov. Agencies post them as Sources Sought or Special
Notices, so both are kept and labelled "market research". Answering one is how a small business
gets a later solicitation set aside for it.

## How it runs

```
profile.json
   │
   ▼
scripts/fetch_sam_opportunities.py   SAM search (server-side filtered) + detail + award check
   │  data/opportunities.json
   ▼
scripts/filter_open.py               awarded / set-aside / cancelled / deadline; marks NEW
   │  data/open_opportunities.json
   ▼
scripts/scores.py pending            only notices not yet scored, or amended since
   │
   ▼
sam-researcher agent                 judges fit against capabilities → data/new_scores.json
   │  scripts/scores.py merge
   ▼
scripts/render_report.py             validates scores, writes data/ranked.json + data/report.md
```

The agent (`.claude/agents/sam-researcher.md`) only makes the judgment call. Every SAM.gov request
and every output file comes from a script, so the result doesn't depend on how the model phrased
things. `render_report.py` refuses to publish if any open notice is unscored or a score is
malformed. `.claude/settings.json` limits the agent to running those four scripts and writing its
scores file.

The SAM.gov endpoints are the public ones sam.gov's own search page uses, so there's no API key. They
answer `406` unless the request sends `Accept: application/hal+json`.

### Schedule it

```
# crontab -e — weekdays at 7:00
0 7 * * 1-5  /path/to/repo/bin/sam-research.sh >> /path/to/repo/data/logs/cron.log 2>&1
```

Runs headless with `--permission-mode dontAsk`, so a disallowed action fails instead of hanging.
`SAM_RESEARCH_BUDGET_USD` caps model spend per run (default $2). On macOS you get a notification
when there's something new.

### Outputs

| File | For |
|---|---|
| `data/report.md` | You: pursue / consider / skip, best fit first, with deadline, agency, set-aside, contact |
| `data/ranked.json` | Anything you build on top: the same result, as `groups.{pursue,consider,skip}[]` |
| `data/open_opportunities.csv` | A spreadsheet of every open notice, unranked |

`data/` is gitignored. Solicitations turn over daily, so regenerate the data instead of committing
it.

### Script options

- `fetch_sam_opportunities.py --include-no-deadline` also pulls notices with no response date
- `fetch_sam_opportunities.py --all-notices --include-inactive` turns off the server-side filters,
  for past-award and competitor research (slow)
- `filter_open.py --days 30` limits to deadlines in the next 30 days
- `filter_open.py --keep-awarded` / `--ignore-set-aside` turn off those two filters

## Tests

The pipeline itself is stdlib-only, so the tests are the only thing that needs an install. One
virtualenv keeps it off your system Python:

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q tests/
```

Offline; nothing calls SAM.gov. 18 tests, under a second.
