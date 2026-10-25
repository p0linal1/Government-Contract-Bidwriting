# RFP library

Every RFP the pipeline has found, kept so later runs can refer back to it. Our code writes here (`agent/library.py` in the team repo), and the agents only read. An RFP's id is its SAM.gov notice id.

## Layout

- `/index.md`: one line per RFP, nearest proposal deadline first, in the form `rfp-id | buyer | title | proposal deadline | status`. If it grows past the 100 kB memory limit, it is split into `/index/<YYYY-MM>.md` files by deadline month, and `/index.md` lists them.
- `/rfps/<rfp-id>/record.json`:
  - where the RFP was found, with its SAM.gov link
  - the buyer, title, notice type, response kind, and solicitation number
  - the proposal deadline as SAM.gov gives it, and the days left on the day it was found
  - the status
  - `documents`: each file's name, size, link, and Files API id
  - `findings` and `runs`: what earlier runs saved, and where
- `/rfps/<rfp-id>/findings/`: results from earlier runs, such as `sheet.json`, `qualification.json`, `research.json`, the checks, and `packet.json`. A file too big for a memory, often the sheet of a long RFP, is kept in the Files API instead, and the record's `findings` gives its file id.

Full RFP documents are too large to store here. They live in the Files API, and a run gets them under `/mnt/session/uploads/<rfp-id>/`, with `sam-notice.json` holding the full SAM.gov notice.

## Status words

`new`, `qualifying`, `passed`, `researching`, `drafting`, `ready_for_doug`, `sent`, `won`, `lost`.

The status names the step an RFP has reached. A run that stops early leaves it at the next step: after a read-only run it is `qualifying`, and after a pursue decision it is `researching`.
