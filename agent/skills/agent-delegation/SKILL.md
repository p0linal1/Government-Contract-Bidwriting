---
name: agent-delegation
description: How the operator runs RFPs through qualifying, research, and drafting. Covers what to hand each agent, how to check their work, when to stop, and the packet Doug reads. Use at the start of every run.
---

# Agent delegation

Version 0. The order and rules below come from the team's plan and three plan reviews. They will be refined from the study of real RFPs.

## The run

1. **Get the RFPs.** If the starting message names RFPs or attaches their files, use those and go to step 2. Otherwise run intake (below).
2. **Take RFPs one at a time, nearest deadline first.** Work only on RFPs whose documents are attached to the session. Until our code stores intake results for you, a run that started from intake ends after intake. For each RFP:
   1. **Qualify.** Send the Qualifier the RFP's document paths and the output path `/mnt/session/outputs/<rfp-id>/qualification.json`. Wait for the file.
   2. **Pass?** If `decision` is `pass`, write the packet with `recommendation: pass` and the reasons, then go to the next RFP.
   3. **Research.** Send the Researcher the qualification path, the RFP paths, and the output path `research.json`.
   4. **Check the research.** Ask the Qualifier to check `research.json` and write `check-research-<round>.json`. On `revise`, send the issue list, word for word, back to the Researcher. Allow at most two rounds. If it still fails, or the check says `block`, write a pass packet that says "no-go, could not verify" with the issues, and move on.
   5. **Draft.** Send the Drafter the qualification, research, and facts paths and the output folder.
   6. **Check the draft.** Ask the Qualifier to check `draft.json` and the proposal files and write `check-draft-<round>.json`. Allow at most two rounds with the Drafter, the same way.
   7. **Packet.** Write `packet.json` (below).
3. **Finish** with one line per RFP: the buyer, the title, send or pass, and the expected worth.

## Intake: pulling new RFPs

The `sam-research` tools search SAM.gov live and remember nothing between calls. The RFP library is how we know what has already been seen.

1. **Search.**
   - Call `search_opportunities` with Cadocary's NAICS and PSC codes from `/mnt/memory/cadocary-facts/README.md`.
   - Set `days` to 60, unless the message gives another window. Leave out `set_aside_eligibility` until the facts list Cadocary's set-asides.
   - Results come 40 to a page, nearest deadline first. Call again with `offset` set to `next_offset` until `has_more` is false.
   - Search once per run. Save each page to a working file as it arrives, and work from that file instead of searching again.
2. **Drop what we have seen.** Skip any `notice_id` already listed in `/mnt/memory/rfp-library/index.md`.
3. **First look.** Judge each new notice from its title and description. Mark it `pursue`, `consider`, or `skip`, with one line on why.
   - Skip purchases of hardware, parts, or brand-name licenses with no services.
   - Skip notices of intent to sole-source to a named vendor.
   - Skip work far from Cadocary's products and capabilities.
   - For `market research` notices (RFIs and sources sought), mark them `consider` only when the work is squarely in scope.
   - When a description is too thin to judge, use `consider`.
4. **Open the promising ones.** Call `get_notice` only for `pursue` and `consider` notices.
5. **Write `/mnt/session/outputs/intake.json`.** Our code stores new RFPs and their files in the library from this file.

```json
{
  "searched": {"naics": [], "psc": [], "days": 60, "total": 0, "pages": 0, "dropped": {}},
  "already_seen": 0,
  "notices": [
    {"notice_id": "", "title": "", "agency": "", "response_kind": "bid | pre-bid | market research",
     "response_deadline": "", "days_left": 0, "url": "",
     "first_look": "pursue | consider | skip", "reason": "",
     "attachments": [{"name": "", "url": "", "size_bytes": 0}]}
  ]
}
```

List every new notice, including the skips, so their reasons are kept. `attachments` is filled only for notices you opened.

## What to hand an agent

The other agents do not see your conversation. Every message to them stands on its own:

- the RFP id, buyer, and title
- the paths to read. Never paste or summarize the files' contents; they read the originals.
- the exact output path, and which section of their skill gives the format
- for a revision: the numbered issue list, word for word
- for a check: what is being checked, and the round number

Example:

```
RFP wa-example-001, City of Example, "Case management software".
Read: /mnt/session/uploads/wa-example-001/rfp.md and /mnt/memory/cadocary-facts/.
Qualify it and write /mnt/session/outputs/wa-example-001/qualification.json
in the format under "Output" in your skill.
```

## Before moving to the next step

Open the output file and confirm:

- it exists and is valid JSON
- every field in the skill's format is present
- every number has a citation or is listed under `educated_guesses`

If any check fails, send it back once, naming the problem exactly. A step that fails twice ends that RFP with a pass packet that explains why.

## When nobody is there to ask

Doug is not available during a run. Never stop to ask him something.

- **Fatal problem** (deadline too close, mandatory meeting missed, a required license Cadocary lacks): write a pass packet with the quote and page, and move on.
- **Uncertain call:** take the safer option, say why, and list it under `calls_for_doug`.
- **Missing fact or data:** report it as missing. Never fill it in.

## The packet: `/mnt/session/outputs/<rfp-id>/packet.json`

This is the one screen Doug reads.

```json
{
  "rfp_id": "",
  "headline": "You are a competitive applicant for <title>. Expected worth $<likely> (<confidence> confidence). Permission to send?",
  "recommendation": "send | pass",
  "expected_worth": {"low": 0, "likely": 0, "high": 0, "confidence": "high | medium | low", "basis": ""},
  "why_competitive": [{"reason": "", "source": ""}],
  "risks": [{"risk": "", "source": ""}],
  "deadlines": [{"kind": "", "as_written": "", "page": 0}],
  "calls_for_doug": [{"topic": "", "choice_made": "", "why": ""}],
  "open_items": [""],
  "checks": {"research": "pass | revise | block", "draft": "pass | revise | block"},
  "files": {"proposal": "", "qualification": "", "research": ""}
}
```

For a pass, set `recommendation` to `pass`, start the headline with "Pass:" and the reason, and leave out the draft fields.

## Limits

- No more than two revision rounds for any step.
- A session holds at most 25 helper threads, so finish one RFP before starting the next.
- You cannot send, submit, upload, or email anything, and you never ask another agent to.
