"""
bidkit — shared, generalized bid-document tooling (company- and bid-agnostic).

Every module is CLI-runnable (`python3 -m bidkit.<module> ...`) and importable. Nothing
opportunity- or company-specific is hard-coded here; all such values come from a
per-opportunity `opportunity.json` (see `config.py` and `examples/opportunity.example.json`).

Modules and the trap each guards (details: .kiro/steering/bid-tooling.md):
  config        load/validate opportunity.json, resolve paths
  xlsx_extract  requirement rows -> JSON; surfaces UNNUMBERED rows for human review
  xlsx_fill     surgical XML fill; column-sorted cells; merge-map guard; x14 validations kept
  xlsx_verify   out-of-order rows / validations / blanks / placeholders / merged-away values
  pdf_render    markdown -> PDF with real TTFs; numbering from first counted page
  html_render   markdown -> PDF via headless Chrome (fixed-width tables); the table-heavy fallback to pdf_render
  pdf_assemble  concatenate ordered part PDFs; continuous page numbers placed per each page's own height; cover(s) unnumbered; compact tail (resumes) gets a number only
  pdf_splice    replace the first N pages of a built PDF with a signed/scanned front; verify length + flag paper-size mismatch
  pdf_verify    text present / no stream errors / min font / family / pages / margins
  pdf_sign      label-anchored signature/date/name overlay on flat PDFs
  pdf_redact    true redaction of contact info on resumes
  docx_render   markdown -> DOCX with colored answer runs
  inbox         poll mailbox -> opportunity folders (dedupe, follow-up routing, intake brief)
  mail_imap     MailFetcher over IMAP (read-only, keychain/env password)
  mail_gmail    MailFetcher over the Gmail REST API + OAuth (optional libs, lazy)
  portal        portal documents -> rfp/ via Playwright persistent login; frame-aware; capture (optional libs, lazy)
  brief         facts sheet (DETECTED dates/$/contacts/format/attachments) + research plan from email + rfp/
  calendar      .ics deadline + milestones per opportunity; merged calendar; Google Calendar scaffold
  fga           SOURCING via the federalgovadvisors.com portal's JSON API: criteria file (NAICS/PSC, widened to the last digit) ->
                open matches, new-since-last-run report, file one as an opportunity folder
"""
__version__ = "0.1.0"
