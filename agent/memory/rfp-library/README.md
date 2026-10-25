# RFP library

Every RFP the pipeline has found, kept so later runs can refer back to it. Our code writes here, and the agents only read.

## Layout

- `/index.md`: one line per RFP, in the form `rfp-id | buyer | title | proposal deadline | status`.
- `/rfps/<rfp-id>/record.json`:
  - where the RFP was found, with its links
  - the buyer and title
  - the deadlines as parsed by code
  - the status
  - the file ids of its documents
- `/rfps/<rfp-id>/findings/`: results from earlier runs (qualification, research, checks, and the packet).

Full RFP documents, the PDFs and their extracted text, are too large to store here. They live in the Files API, and a run gets them under `/mnt/session/uploads/<rfp-id>/`.

## Status words

`new`, `qualifying`, `passed`, `researching`, `drafting`, `ready_for_doug`, `sent`, `won`, `lost`.

The library is empty so far.
