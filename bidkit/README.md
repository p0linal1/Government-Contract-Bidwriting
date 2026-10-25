# bidkit — shared bid-document tooling

Generalized, config-driven Python tools for producing and verifying government-bid
documents: requirement workbooks (xlsx), proposal PDFs, signed forms, scrubbed resumes, and
DOCX deliverables. Distilled from the 26-013 BIPIN and 2026-110 Dental Tracker bids, where the
same mechanical problems were each solved twice with hard-coded values.

**Nothing opportunity- or company-specific is hard-coded here.** Every bid supplies an
`opportunity.json` (see `examples/opportunity.example.json`); a test (`tests/test_no_hardcoding.py`)
fails the build if a company name, bid id, dollar figure, or pixel coordinate appears in the
library.

The *why* behind each tool — the trap it guards — is documented in
`.kiro/steering/bid-tooling.md`. The build workflow that uses these tools is
`.kiro/steering/bid-build.md`.

## Install
```
pip3 install -r bidkit/requirements.txt
```
Python 3.9+. Fonts: the PDF renderer/verifier use real TTF files named in the config
(macOS: `/System/Library/Fonts/Supplemental/Arial*.ttf`).

## Layout
```
bidkit/
  bidkit/            the library (importable; each module is also a CLI)
  examples/          opportunity.example.json — copy into <opportunity>/opportunity.json
  tests/             pytest suite (fixtures are generated; no bid data)
  tools/             maintenance scripts (steering coverage diff, steering lint)
  requirements.txt
```

## Modules
Run any module as `python3 -m bidkit.<module> --help` from the `bidkit/` directory, or set
`PYTHONPATH=bidkit`.

| Module | Purpose | Guards against |
|---|---|---|
| `config` | load/validate `opportunity.json`, resolve paths | hard-coded paths/values |
| `xlsx_extract` | requirement rows → JSON; **emits `unnumbered.json`** for blank-number rows | unnumbered-but-real requirement silently skipped |
| `xlsx_fill` | surgical XML fill; column-sorted cells; vocabulary check; **refuses merged-away writes**; keeps x14 validations | openpyxl x14 strip; cell-order corruption; merged-cell hiding |
| `xlsx_verify` | 0 out-of-order rows, validations intact, 0 blanks, 0 placeholders, 0 merged-away values; `--repair` | same three, plus leftover template text |
| `pdf_render` | markdown → PDF with real TTFs; numbering from first counted page; excluded sections unnumbered | font/size penalties; numbering exclusions |
| `pdf_verify` | text present, no MuPDF errors, min font, family allowlist, page count, margins | blank/corrupt PDF; font/size; page limit |
| `pdf_sign` | label-anchored signature/date/name overlay on flat PDFs; `--coords` override | hand-measured coordinates per form |
| `pdf_redact` | true redaction of emails/phones/URLs/handles; overlay `<firstname>@<domain>` | white-boxed text still extractable |
| `docx_render` | markdown → DOCX; colored answer runs | hand-edited, non-regenerable checklists |
| `inbox` | poll the bid mailbox (pluggable `mail_imap` / `mail_gmail`), file solicitation emails as opportunities, route follow-ups, dedupe | missed/duplicated invitations |
| `mail_imap` / `mail_gmail` | MailFetcher backends: IMAP (`BODY.PEEK`, keychain/env password) or Gmail REST API (OAuth token outside repo); optional/lazy | secrets in config; backend lock-in |
| `portal` | fetch portal documents into `rfp/` via a Playwright profile with persisted login (`storage_state.json`); frame-aware (WEBS-style framesets); `capture` saves page + every frame to ground adapters; grounded `publicpurchase`, scaffold `webs`, `generic`; optional/lazy | portals behind login; silent logout; frameset shells |
| `brief` | facts sheet from email + `rfp/` docs: DETECTED dates/$/contacts/format rules/attachments ✔✘/eval lines with snippets; research plan + findings template; sets unconfirmed dates in `opportunity.json` | hunting through the RFP; skipping the incumbent research |
| `calendar` | `.ics` per opportunity (deadline, milestones, internal go/no-go → submit, alarms, UNCONFIRMED titles) + merged all-opportunities.ics; Google Calendar upsert scaffold | filed-and-forgotten deadlines |

## Typical flow for a new bid
Run from the `bidkit/` directory (or `PYTHONPATH=bidkit`); `<cfg>` = `<opp>/opportunity.json`.
```
cp examples/opportunity.example.json <opp>/opportunity.json         # edit paths/rules/signer
python3 -m bidkit.config       <cfg>                                 # validate + font check
python3 -m bidkit.xlsx_extract <cfg> A1                              # -> A1-requirements.json + A1-unnumbered.json
#   REVIEW A1-unnumbered.json: any "requirement?" rows need a real answer
#   classify rows -> fill response/comment in A1-requirements.json (script + human)
python3 -m bidkit.xlsx_fill    <cfg> A1 <extract>/A1-requirements.json
python3 -m bidkit.xlsx_verify  <draft>/A1*.xlsx --ref <opp>/rfp/A1*.xlsx --cfg <cfg> --wb A1
python3 -m bidkit.pdf_render   proposal.md proposal.pdf --cfg <cfg> --footer-label "RFP 00-000"
python3 -m bidkit.pdf_verify   proposal.pdf --cfg <cfg>
python3 -m bidkit.pdf_sign     <cfg> A7 --probe                      # inspect lines/labels first
python3 -m bidkit.pdf_sign     <cfg> A7                              # typed sig, date left blank
python3 -m bidkit.pdf_redact   resume.pdf --firstname jane --cfg <cfg>
python3 -m bidkit.docx_render  checklist.md checklist.docx --answer-color green
python3 -m bidkit.pdf_verify   <submit>/*.pdf --cfg <cfg> --skip fonts,minsize,margins   # agency forms
```
Exit codes are non-zero on any FAIL/refusal so these can gate a script.

## Tests
```
cd bidkit && python3 -m pytest -q
```
Two portal tests drive a real headless Chromium against a local server serving a saved Public
Purchase page; they skip cleanly if Playwright/Chromium are absent.

## Optional extras
```
pip3 install -r requirements-gmail.txt     # bidkit.mail_gmail
pip3 install -r requirements-portal.txt && python3 -m playwright install chromium   # bidkit.portal
```

## Migration stance
Historical scripts in `26-013-BIPIN/deliverables/bid/tools/` and
`2026-110-SVC-Dental-Tracker/deliverables/` are left untouched as the record of what shipped.
New bids use `bidkit/`.
