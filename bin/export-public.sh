#!/usr/bin/env bash
# export-public.sh — build the public, company-neutral edition of this repo.
#
# Usage:  bin/export-public.sh [--check] [--git] [--author "Name <email>"] [--out DIR] [--no-test]
#   default out: dist/public/bid-workshop  (dist/ is gitignored)
#   --check   list what would be exported (source -> public path); write nothing
#   --git     git init the output with FRESH history (nothing from this repo's history)
#   --author  make the initial commit as this identity (otherwise staged, not committed)
#   --zip     also write dist/public/bid-workshop-<stamp>.zip (files only: no .git/, no marker)
#
# Fails closed: a denylist hit, an unknown e-mail address, or a failing test exits non-zero.
# What is exported, rewritten and denied: company/public-export/config.json (private; never exported).
# Mark private passages in any exported file with a whole-line comment pair, private:begin / private:end
# (#, <!--, or // leader) — see bidkit/tools/public_export.py.
# Nothing is pushed. Review the output, then create the remote and push it yourself.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${BIDKIT_PYTHON:-}"
if [[ -z "$PY" ]]; then
  for c in python3 /usr/bin/python3; do
    if "$c" -c "import fitz, openpyxl, docx, pytest" 2>/dev/null; then PY="$c"; break; fi
  done
fi
[[ -n "$PY" ]] || { echo "no python with bidkit deps (pip3 install -r bidkit/requirements.txt), or set BIDKIT_PYTHON" >&2; exit 2; }
OUT="$ROOT/dist/public/bid-workshop"; ARGS=(); ZIP=0
while [[ $# -gt 0 ]]; do case "$1" in
  --out) OUT="$2"; shift;;
  --author) ARGS+=(--author "$2"); shift;;
  --zip) ZIP=1;;
  --check|--git|--no-test) ARGS+=("$1");;
  *) echo "unknown arg $1" >&2; exit 2;; esac; shift; done
"$PY" "$ROOT/bidkit/tools/public_export.py" --root "$ROOT" \
  --config "$ROOT/company/public-export/config.json" --out "$OUT" ${ARGS[@]+"${ARGS[@]}"}
# --zip: package the scanned, tested export (only reached when the export succeeded; set -e).
# The zip carries the files only — no .git/ and no export marker — so the recipient starts clean.
if [[ $ZIP -eq 1 ]]; then
  NAME="$(basename "$OUT")"; Z="$(dirname "$OUT")/${NAME}-$(date +%Y%m%d-%H%M).zip"
  rm -f "$Z"
  ( cd "$(dirname "$OUT")" && zip -r -q -X "$Z" "$NAME" -x "$NAME/.git/*" "$NAME/.public-export" "*.DS_Store" )
  echo "zip: $Z ($(du -h "$Z" | cut -f1), $(unzip -Z1 "$Z" | grep -cv '/$') files)"
  echo "sha256: $(shasum -a 256 "$Z" | cut -d' ' -f1)"
fi
