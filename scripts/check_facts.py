#!/usr/bin/env python3
"""Check Doug's facts sheet, and print the facts the agent is allowed to claim.

The agent may only state what is on this sheet (docs/fact-sheet.md). This script is the gate: it
refuses a sheet with a malformed fact, and `--usable` prints only the facts that are approved, known,
and not expired. That output is what gets loaded, read-only, into the agent's memory store.

Every fact has exactly five parts:
    {"id": "insurance.general_liability", "value": ..., "source": "Doug, interview, Oct 25",
     "approved": false, "expires": "2027-06-30" or null}

Record "unknown" as the value rather than guessing. Ids follow the Cadocary Facts memory store
(agent/memory/cadocary-facts/README.md): company.*, product.*, prefs.*, and so on. Company facts
already in profile.json (legal name, UEI, CAGE, website, location, NAICS, PSC, capabilities) stay
there and are not repeated here.

Inputs:
  facts.json                 the real sheet, gitignored; start from facts.example.json

Usage:
  python3 scripts/check_facts.py                      # check facts.json, print what's still open
  python3 scripts/check_facts.py facts.example.json
  python3 scripts/check_facts.py --usable             # JSON of the facts the agent may claim
"""

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

FACTS_FILE = Path("facts.json")
UNKNOWN = "unknown"
FIELDS = ("id", "value", "source", "approved", "expires")

# Sections from docs/fact-sheet.md, as the first part of each id, named as in the Cadocary Facts
# memory store. The research-test awards (section 12) are their own list, not facts, because the
# agent must never see them.
SECTIONS = (
    "company",
    "certifications",
    "insurance",
    "security",
    "product",
    "past_performance",
    "references",
    "team",
    "pricing",
    "prefs",
    "approved_text",
    "paperwork",
)
# Things that run out. A known value in these sections needs an expiry date.
EXPIRING = ("certifications", "insurance")
# Memory store ids whose values come from profile.json. Don't keep the same fact twice.
PROFILE_FACTS = (
    "company.legal_name",
    "company.uei",
    "company.cage_code",
    "company.website",
    "company.location",
    "company.naics",
    "company.psc",
    "company.capabilities",
)
ID_PATTERN = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
AWARD_FIELDS = ("id", "buyer", "bought", "paid", "rfp_url", "source")
EXPIRY_WARNING = timedelta(days=60)


def is_unknown(value):
    return isinstance(value, str) and value.strip().lower() == UNKNOWN


def parse_date(text):
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def validate(sheet):
    """Return a list of problems with `sheet`; empty means the sheet is well formed."""
    problems = []
    facts = sheet.get("facts")
    if not isinstance(facts, list):
        return ["sheet has no \"facts\" list"]
    seen = set()
    for n, fact in enumerate(facts):
        label = fact.get("id") if isinstance(fact, dict) and fact.get("id") else f"fact #{n + 1}"
        if not isinstance(fact, dict):
            problems.append(f"{label}: not an object")
            continue
        missing = [f for f in FIELDS if f not in fact]
        extra = sorted(fact.keys() - set(FIELDS))
        if missing:
            problems.append(f"{label}: missing {', '.join(missing)}")
        if extra:
            problems.append(f"{label}: unexpected {', '.join(extra)}")
        if missing:
            continue
        fact_id, value = fact["id"], fact["value"]
        if not isinstance(fact_id, str) or not ID_PATTERN.match(fact_id):
            problems.append(f"{label}: id must look like section.name, lowercase")
            continue
        if fact_id in seen:
            problems.append(f"{fact_id}: duplicate id")
        seen.add(fact_id)
        section = fact_id.split(".", 1)[0]
        if section not in SECTIONS:
            problems.append(f"{fact_id}: unknown section {section!r}")
        if fact_id in PROFILE_FACTS:
            problems.append(f"{fact_id}: comes from profile.json, not here")
        if value is None or value == "" or value == [] or value == {}:
            problems.append(f"{fact_id}: empty value; write \"unknown\" instead")
        if not isinstance(fact["source"], str) or not fact["source"].strip():
            problems.append(f"{fact_id}: no source")
        if not isinstance(fact["approved"], bool):
            problems.append(f"{fact_id}: approved must be true or false")
        if fact["approved"] is True and is_unknown(value):
            problems.append(f"{fact_id}: approved but the value is unknown")
        expires = fact["expires"]
        if expires is not None and parse_date(expires) is None:
            problems.append(f"{fact_id}: expires must be YYYY-MM-DD or null")
        if section in EXPIRING and expires is None and not is_unknown(value):
            problems.append(f"{fact_id}: {section} facts need an expiry date")
        if section == "references" and not is_unknown(value):
            if not isinstance(value, dict) or not parse_date(value.get("permission_date")):
                problems.append(f"{fact_id}: a reference needs the permission_date they agreed to be named")
    problems.extend(validate_awards(sheet.get("research_test", [])))
    return problems


def validate_awards(awards):
    """The three past awards Doug knows the price of: the answer key for the research test."""
    if not isinstance(awards, list):
        return ["research_test must be a list"]
    problems = []
    for n, award in enumerate(awards):
        label = f"research_test #{n + 1}"
        if not isinstance(award, dict):
            problems.append(f"{label}: not an object")
            continue
        missing = [f for f in AWARD_FIELDS if f not in award]
        if missing:
            problems.append(f"{label}: missing {', '.join(missing)}")
    return problems


def usable(sheet, today=None):
    """The facts the agent may claim: approved, known, and not expired, as {id: value}."""
    today = today or date.today()
    out = {}
    for fact in sheet["facts"]:
        if fact["approved"] is not True or is_unknown(fact["value"]):
            continue
        expires = parse_date(fact["expires"])
        if expires and expires < today:
            continue
        out[fact["id"]] = fact["value"]
    return out


def status(sheet, today=None):
    """What's still open on the sheet, for the next session with Doug."""
    today = today or date.today()
    unknown, unapproved, expired, expiring = [], [], [], []
    for fact in sheet["facts"]:
        if is_unknown(fact["value"]):
            unknown.append(fact["id"])
        elif fact["approved"] is not True:
            unapproved.append(fact["id"])
        expires = parse_date(fact["expires"])
        if expires and expires < today:
            expired.append(f"{fact['id']} ({fact['expires']})")
        elif expires and expires - today <= EXPIRY_WARNING:
            expiring.append(f"{fact['id']} ({fact['expires']})")
    return {"unknown": unknown, "unapproved": unapproved, "expired": expired, "expiring": expiring}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", nargs="?", type=Path, default=FACTS_FILE)
    parser.add_argument("--usable", action="store_true", help="print the claimable facts as JSON")
    args = parser.parse_args()

    if not args.path.exists():
        sys.exit(f"{args.path} not found. Copy facts.example.json to facts.json and fill it in.")
    try:
        sheet = json.loads(args.path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"{args.path} is not valid JSON: {exc}")

    problems = validate(sheet)
    if problems:
        print(f"{args.path}: {len(problems)} problem(s)", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        sys.exit(1)

    if args.usable:
        print(json.dumps(usable(sheet), indent=2, sort_keys=True))
        return

    facts = sheet["facts"]
    claimable = usable(sheet)
    print(f"{args.path}: {len(facts)} facts, {len(claimable)} the agent may claim")
    for heading, ids in status(sheet).items():
        if ids:
            print(f"\n{heading} ({len(ids)}):")
            for fact_id in ids:
                print(f"  {fact_id}")
    awards = sheet.get("research_test", [])
    print(f"\nresearch test awards: {len(awards)} of 3")


if __name__ == "__main__":
    main()
