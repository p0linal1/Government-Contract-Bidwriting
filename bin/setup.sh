#!/usr/bin/env bash
# setup.sh — prepare a machine (macOS or Linux) to run this repo.
#
# Usage:  bin/setup.sh [--gmail] [--portal] [--all]
#   core            bidkit runtime + tests (PyMuPDF, openpyxl, python-docx, pytest)
#   --gmail         Gmail REST API backend (google-api-python-client, oauthlib)
#   --portal        Playwright + Chromium for portal fetching (persisted-cookie sessions)
#   --all           both extras
# Idempotent; safe to re-run. Nothing here touches secrets — it only creates the in-tree secrets/
# directory and tells you which files to put there. Everything the tools need lives under the repo
# root, so a zip of the whole tree moves the system (creds included) to another machine.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GMAIL=0; PORTAL=0
for a in "$@"; do case "$a" in --gmail) GMAIL=1;; --portal) PORTAL=1;; --all) GMAIL=1; PORTAL=1;; *) echo "unknown flag $a" >&2; exit 2;; esac; done
OS="$(uname -s)"
say() { printf '\n== %s\n' "$*"; }
warn() { printf '   WARNING: %s\n' "$*"; }

say "python"
command -v python3 >/dev/null || { echo "python3 not found" >&2; exit 1; }
python3 -c 'import sys; assert sys.version_info >= (3, 9), sys.version' || { echo "need Python >= 3.9" >&2; exit 1; }
python3 --version

say "core requirements"
python3 -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
python3 -m pip install --quiet -r "$ROOT/bidkit/requirements.txt"
echo "   ok"

if [[ $GMAIL -eq 1 ]]; then
  say "gmail extra"
  python3 -m pip install --quiet -r "$ROOT/bidkit/requirements-gmail.txt"
  echo "   ok — next: put your OAuth Desktop-app client JSON at secrets/gmail-oauth-client.json,"
  echo "        set source.type=gmail_api in inbox/inbox.json (credentials_file/token_file point at ../secrets/),"
  echo "        then: (cd bidkit && python3 -m bidkit.mail_gmail auth --cfg ../inbox/inbox.json)"
fi

if [[ $PORTAL -eq 1 ]]; then
  say "portal extra (playwright + chromium)"
  python3 -m pip install --quiet -r "$ROOT/bidkit/requirements-portal.txt"
  if [[ "$OS" == "Linux" ]]; then
    echo "   installing chromium system deps (may prompt for sudo)…"
    python3 -m playwright install-deps chromium || warn "install-deps failed — install libnss3/libatk/libgbm etc. manually"
  fi
  python3 -m playwright install chromium
  echo "   ok — next: cp inbox/portals.example.json inbox/portals.json; then per portal, on a machine WITH a display:"
  echo "        (cd bidkit && python3 -m bidkit.portal login publicpurchase.com --portals ../inbox/portals.json)"
  echo "        Profiles + storage_state.json live in secrets/browser-profiles/ (in-tree, chmod 700)."
  echo "        Sourcing (FGA): after  portal login federalgovadvisors.com  run"
  echo "        (cd bidkit && python3 -m bidkit.fga --portals ../inbox/portals.json login --from-browser)  then  bin/bid-source.sh"
fi

say "secrets directory (in-tree, portable)"
mkdir -p "$ROOT/secrets/browser-profiles"; chmod 700 "$ROOT/secrets" "$ROOT/secrets/browser-profiles"
echo "   $ROOT/secrets  (env passwords, OAuth client + token, FGA tokens, browser profiles — all INSIDE the repo tree)"
echo "   a zip of the whole repo moves the system to another machine; keychain items are an optional local convenience only"
[[ -f "$ROOT/inbox/inbox.json" ]] || echo "   TODO: cp inbox/inbox.example.json inbox/inbox.json  and edit"

say "fonts (bid PDFs must be REAL Arial by name — metric-compatible substitutes fail the family check)"
ARIAL_MAC="/System/Library/Fonts/Supplemental/Arial.ttf"
if [[ -f "$ARIAL_MAC" ]]; then
  echo "   macOS Arial found: $ARIAL_MAC (opportunity.json defaults already point here)"
else
  FOUND="$(fc-list 2>/dev/null | grep -i 'arial\.ttf\|Arial\.ttf' | head -1 | cut -d: -f1 || true)"
  if [[ -n "$FOUND" ]]; then
    echo "   Arial found via fontconfig: $FOUND"
    echo "   -> set fonts.regular/bold/italic/bold_italic in each opportunity.json (and opportunities/_template/opportunity.json) to the Arial*.ttf files in $(dirname "$FOUND")"
  else
    warn "no Arial TTF on this machine. PyMuPDF rendering needs the real files:"
    echo "     Debian/Ubuntu: sudo apt install ttf-mscorefonts-installer   (accept the EULA)  -> /usr/share/fonts/truetype/msttcorefonts/Arial*.ttf"
    echo "     or copy Arial.ttf / Arial Bold.ttf / Arial Italic.ttf / Arial Bold Italic.ttf from a licensed machine to ~/.fonts/"
    echo "     then update the fonts block in opportunities/_template/opportunity.json."
  fi
fi

say "scheduling"
if [[ "$OS" == "Darwin" ]]; then
  echo "   launchd (recommended): see inbox/launchd/com.example.bid-inbox.plist.example"
else
  echo "   systemd user timer: see inbox/systemd/README.md   (or cron: */30 7-19 * * 1-5 $ROOT/bin/bid-inbox.sh)"
fi

say "self-test"
( cd "$ROOT/bidkit" && python3 -m pytest -q 2>&1 | tail -1 )
echo
echo "done."
