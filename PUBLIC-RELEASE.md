# About this public release

This repository is the public, company-neutral edition of a working bid workshop: the `bidkit`
tooling, the Kiro steering methodology, the opportunity template, and the scheduling scripts.

It was generated from a private working copy by `bidkit/tools/public_export.py`. That tool copies
an allowlist of files, removes passages marked private, replaces company identifiers with
placeholders, and refuses to finish if any denylisted term remains. No bids, pricing, resumes,
correspondence, or credentials are included, and none of the private repository's git history is.

- Placeholders: **YourCo** (company), **Pat Principal** (principal), **example.com** (domains),
  **Springfield** (a city used in worked examples), and `XX-…` (identifiers).
- Start with `company/README.md`, then `.kiro/steering/company-profile.md`.
- Where the README says the repo is "local-only; never push it", that refers to **your own working
  copy** once it holds real bids and company data. Keep that copy private.
- Some tests use public procurement records (for example, a published RFP page) as fixtures.
  Tests that need private sample bids skip themselves when those bids are absent.
