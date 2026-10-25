---
name: agent-delegation
description: How the operator runs RFPs through reading, qualifying, research, and drafting. Covers what to hand each agent, how to check their work, when to stop, and the packet Doug reads. Use at the start of every run.
---

# Agent delegation

Version 0. The order and rules below come from the team's plan and three plan reviews. They will be refined from the study of real RFPs.

## The run

The flow for every RFP: the Reader reads it, the Qualifier decides, and only a `pursue` goes on to research and drafting. Each agent hands its result back to you, and you send the next step.

1. **Get the RFPs.** If the starting message names RFPs or attaches their files, use those. Otherwise run intake (below), and take every `pursue` and `consider` notice from it.
2. **Read every RFP, then qualify every RFP.** Both steps are cheap.
   1. **Read.** Send the Reader the folder of attached documents, `/mnt/session/uploads/<rfp-id>/`, and name the output path `/mnt/session/outputs/<rfp-id>/sheet.json`. Our code attaches every document before the run starts, so this is the normal case. Send attachment links instead only for documents that aren't attached: ones the starting message lists as not attached, or RFPs you found through intake in this run.
   2. **Qualify.** Send the Qualifier the sheet path and the output path `qualification.json`. If `decision` is `pass`, write the packet with `recommendation: pass` and the reasons, and that RFP is done.
3. **Work the pursued RFPs, one at a time, nearest deadline first.** Do at most 3 in a run unless the message says otherwise, and list the rest in your final reply. For each one:
   1. **Research.** Send the Researcher the sheet and qualification paths and the output path `research.json`.
   2. **Check the research.** Ask the Qualifier to check `research.json` and write `check-research-<round>.json`. On `revise`, send the issue list, word for word, back to the Researcher. Allow at most two rounds. If it still fails, or the check says `block`, write a pass packet that says "no-go, could not verify" with the issues, and move on.
   3. **Check the value.** Doug wants contracts priced between $1 million and $5 million. Read `value_estimate` in the checked `research.json`. If `likely` is under $1,000,000 or over $5,000,000 and `confidence` is `medium` or `high`, don't draft. Write a pass packet instead, with `expected_worth` from the research and a headline such as "Pass: likely worth $600,000 (medium confidence), under Doug's $1 million to $5 million range." With `low` confidence, go on to draft, and add a `calls_for_doug` entry giving the estimate and the range.
   4. **Draft.** Send the Drafter the sheet, qualification, research, and facts paths and the output folder.
   5. **Check the draft.** Ask the Qualifier to check `draft.json` and the proposal files and write `check-draft-<round>.json`. Allow at most two rounds with the Drafter, the same way.
   6. **Packet.** Write `packet.json` (below).
4. **Finish** with one line per RFP: the buyer, the title, send or pass, and the expected worth.

If the message asks for only some steps, such as "read and qualify only", stop where it says.

## Intake: pulling new RFPs

The `sam-research` tools search SAM.gov live and remember nothing between calls. The RFP library is how we know what has already been seen.

1. **Search.**
   - Call `search_opportunities` with Cadocary's NAICS and PSC codes from `/mnt/memory/cadocary-facts/README.md`.
   - Set `days` to 60, unless the message gives another window. Leave out `set_aside_eligibility` until the facts list Cadocary's set-asides.
   - Results come 40 to a page, nearest deadline first. Call again with `offset` set to `next_offset` until `has_more` is false.
   - Search once per run. Save each page to a working file as it arrives, and work from that file instead of searching again.
2. **Drop what we have worked.** Our code stores every open notice in the library with status `new`. Skip any notice that `/mnt/memory/rfp-library/index.md` (or the month files it lists) shows with any other status.
3. **First look.** Judge each new notice from its title and description. Mark it `pursue`, `consider`, or `skip`, with one line on why.
   - Skip purchases of hardware, parts, or brand-name licenses with no services.
   - Skip notices of intent to sole-source to a named vendor.
   - Skip military or defense work: any Department of Defense, armed service, or defense agency buyer, or a system for military use. Doug takes no military applications.
   - Skip notices that state a total value under $1 million or over $5 million. When the value isn't stated, judge on the rest.
   - Skip work far from Cadocary's products and capabilities.
   - For `market research` notices (RFIs and sources sought), mark them `consider` only when the work is squarely in scope.
   - When a description is too thin to judge, use `consider`.
4. **Open the promising ones.** Call `get_notice` only for `pursue` and `consider` notices.
5. **Write `/mnt/session/outputs/intake.json`.**

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
Read: /mnt/session/outputs/wa-example-001/sheet.json and /mnt/memory/cadocary-facts/.
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

- **Fatal problem** (deadline too close, mandatory meeting missed, a required license Cadocary lacks, military work, a value outside $1 million to $5 million): write a pass packet with the quote and page, and move on.
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
  "sheet": "",
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
