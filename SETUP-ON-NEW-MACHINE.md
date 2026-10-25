# Setting up this repo on a new machine

You unzipped a **transfer** build of `bid-writing/`. It has all the code, the gated evaluation
harness, every opportunity, and the company assets in `company/` — but **no secrets**. The
`secrets/` directory was intentionally left out of the zip (it holds live Google tokens, portal
passwords, and session cookies that must never travel loosely). So this machine re-mints every
credential fresh with its own interactive sign-ins. Nothing is copied from the source machine.

Work top to bottom. Everything runs from the repo root unless a step says `cd bidkit`.

---

## 0. Prerequisites
- Python ≥ 3.9 (`python3 --version`).
- A browser on this machine for the one-time Google / portal sign-ins.
- The Google Cloud **OAuth Desktop-app client** JSON for your project (see step 2) — the one file
  you cannot regenerate purely from a command here; download it from the Google Cloud console.

## 1. Install dependencies + scaffold (one command)
```
bin/setup.sh --all
```
This installs the bidkit core, Gmail libraries, Playwright + Chromium, creates `secrets/`
(chmod 700), checks for Arial, and runs the test suite. **Expected: the self-test passes**
(≈310 passed, 1 skipped). If it does, the code is good on this machine; the rest is credentials.

## 2. Gmail — sign in to Google (read + send)
The harness reads the bid mailbox and sends the daily digest. Two scopes = two one-time consents.
```
cp inbox/inbox.example.json inbox/inbox.json          # edit: set source.type to "gmail_api"
# place your OAuth Desktop-app client JSON here:
#   secrets/gmail-oauth-client.json
cd bidkit
python3 -m bidkit.mail_gmail auth      --cfg ../inbox/inbox.json   # browser → sign in → read token
python3 -m bidkit.mail_gmail send-auth --cfg ../inbox/inbox.json   # browser → sign in → send token
python3 -m bidkit.mail_gmail test      --cfg ../inbox/inbox.json   # lists recent messages = working
cd ..
```
Writes `secrets/gmail-token.json` (readonly) and `secrets/gmail-send-token.json` (send). Both
self-refresh after this; you won't sign in again unless you revoke access.

## 3. Portals — log in once each (WEBS, Public Purchase)
```
cp inbox/portals.example.json inbox/portals.json
cd bidkit
python3 -m bidkit.portal login des.wa.gov        --portals ../inbox/portals.json   # headed; log in
python3 -m bidkit.portal login publicpurchase.com --portals ../inbox/portals.json  # if you use it
cd ..
```
Each opens a real browser; log in, press Enter. The session is saved to
`secrets/browser-profiles/<portal>/storage_state.json`. WEBS/FGA also self-re-login from the
password in step 5 when a session expires (~20 min idle).

## 4. FGA sourcing token
```
cd bidkit && python3 -m bidkit.fga --portals ../inbox/portals.json login --from-browser && cd ..
```
(Run step 3's `portal login federalgovadvisors.com` first if the browser profile isn't set up.)
Writes `secrets/fga-tokens.json` (JWT + refresh, self-refreshing ~1 year).

## 5. Passwords for unattended re-login (WEBS / FGA)
```
printf 'export WEBS_PASSWORD=...\nexport FGA_PASSWORD=...\n' > secrets/env
chmod 600 secrets/env
```
These let the scheduled runs re-login after a session expires without a human. (On macOS you may
instead store them in the keychain as `bidkit-webs` / `bidkit-fga`; `env` is the portable fallback.)

## 6. The daily evaluation harness + digest
```
cp inbox/harness.example.json inbox/harness.json      # set digest.to, digest.org_name
                                                      # autonomy stays "a" (notify-only) — the safe default
bin/bid-harness.sh --dry-run                          # composes the digest and prints it — does NOT send
```
When the dry-run looks right, drop `--dry-run` to send for real, or schedule it (step 7).

## 7. Schedule (optional, when you're ready to run it daily)
- **macOS (launchd):** `inbox/launchd/com.example.bid-harness.plist.example`
  (also `com.example.bid-inbox` for the mail poll and `com.example.bid-source` for FGA sourcing).
- **Linux (systemd):** `inbox/systemd/bid-harness.{service,timer}` (+ the inbox/source pairs).
- Order per weekday morning: inbox poll (07:00) → sourcing (07:15) → harness + digest (07:40).

## 8. Fonts (only if `setup.sh` warned about Arial)
Bid PDFs must be **real Arial by name**. macOS has it at
`/System/Library/Fonts/Supplemental/Arial.ttf` (the opportunity configs already point there). On
Linux: `sudo apt install ttf-mscorefonts-installer`, then update the `fonts` block in
`opportunities/_template/opportunity.json`.

---

## Verify you're done
```
cd bidkit && python3 -m pytest -q && cd ..          # all green
python3 -m bidkit.mail_gmail test --cfg ../inbox/inbox.json   # (from bidkit/) lists messages
bin/bid-harness.sh --dry-run                        # composes the digest with real data
```
If the dry-run digest reads correctly and lists your opportunities, the machine is fully set up.

## Notes
- **`inbox/fga-seen.json` DID travel in the zip**, so the first sourcing run reports only genuinely
  new postings, not the whole backlog.
- Full reference: `README.md` → "Moving to another machine"; per-file credential table:
  `secrets/README.md`.
- Keep this unzipped copy as sensitive as the original — it still contains real bid data, the W-9,
  signatures, resumes, and filed `.eml` emails.
