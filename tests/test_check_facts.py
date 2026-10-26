"""Offline tests for the facts sheet checker."""

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_facts  # noqa: E402

TODAY = date(2026, 10, 25)


def fact(fact_id, value="x", **over):
    row = {"id": fact_id, "value": value, "source": "Doug, interview, Oct 25", "approved": True, "expires": None}
    row.update(over)
    return row


def sheet(*facts, awards=()):
    return {"facts": list(facts), "research_test": list(awards)}


def test_example_sheet_is_valid_and_claims_nothing():
    example = json.loads((ROOT / "facts.example.json").read_text(encoding="utf-8"))
    assert check_facts.validate(example) == []
    assert check_facts.usable(example) == {}


def test_example_products_and_client_work_exist_in_the_memory_store():
    readme = (ROOT / "agent" / "memory" / "cadocary-facts" / "README.md").read_text(encoding="utf-8")
    store_ids = re.findall(r"^\| ([a-z0-9_]+(?:\.[a-z0-9_]+)+) \|", readme, re.MULTILINE)
    store_items = {store_id.rsplit(".", 1)[0] for store_id in store_ids}
    example = json.loads((ROOT / "facts.example.json").read_text(encoding="utf-8"))
    for row in example["facts"]:
        section, _, rest = row["id"].partition(".")
        if section in ("product", "work"):
            item = f"{section}.{rest.split('.', 1)[0]}"
            assert "." in rest and item in store_items, row["id"]


def test_well_formed_sheet_has_no_problems():
    s = sheet(
        fact("company.wa_ubi", "123"),
        fact("insurance.cyber", {"limit_usd": 1000000}, expires="2027-01-01"),
        fact("references.jane", {"name": "Jane", "permission_date": "2026-10-25"}),
    )
    assert check_facts.validate(s) == []


def test_missing_and_extra_fields():
    row = fact("company.wa_ubi")
    del row["source"]
    row["note"] = "hi"
    problems = check_facts.validate(sheet(row))
    assert any("missing source" in p for p in problems)
    assert any("unexpected note" in p for p in problems)


def test_bad_id_unknown_section_and_duplicates():
    problems = check_facts.validate(sheet(fact("Insurance"), fact("rumors.x"), fact("team.a"), fact("team.a")))
    assert any("section.name" in p for p in problems)
    assert any("unknown section 'rumors'" in p for p in problems)
    assert any("team.a: duplicate id" in p for p in problems)


def test_profile_facts_are_not_repeated():
    problems = check_facts.validate(sheet(fact("company.naics", ["541511"])))
    assert problems == ["company.naics: comes from profile.json, not here"]


def test_empty_value_must_be_written_as_unknown():
    problems = check_facts.validate(sheet(fact("company.wa_ubi", "", approved=False)))
    assert any("write \"unknown\"" in p for p in problems)


def test_unknown_cannot_be_approved():
    problems = check_facts.validate(sheet(fact("company.wa_ubi", "unknown", approved=True)))
    assert problems == ["company.wa_ubi: approved but the value is unknown"]


def test_insurance_needs_expiry_unless_unknown():
    problems = check_facts.validate(sheet(fact("insurance.auto", {"limit_usd": 1})))
    assert problems == ["insurance.auto: insurance facts need an expiry date"]
    assert check_facts.validate(sheet(fact("insurance.auto", "unknown", approved=False))) == []


def test_bad_expiry_date():
    problems = check_facts.validate(sheet(fact("insurance.auto", expires="June 2027")))
    assert any("YYYY-MM-DD" in p for p in problems)


def test_reference_without_permission_is_refused():
    problems = check_facts.validate(sheet(fact("references.bob", {"name": "Bob"})))
    assert problems == ["references.bob: a reference needs the permission_date they agreed to be named"]


def test_research_test_awards_need_every_field():
    problems = check_facts.validate(sheet(awards=[{"id": "a", "buyer": "City"}]))
    assert problems == ["research_test #1: missing bought, paid, rfp_url, source"]


def test_usable_drops_unapproved_unknown_and_expired():
    s = sheet(
        fact("company.wa_ubi", "123"),
        fact("company.employees", "4", approved=False),
        fact("company.small_business", "unknown", approved=False),
        fact("insurance.cyber", "1M", expires="2026-10-24"),
        fact("insurance.auto", "500k", expires="2026-10-25"),
    )
    assert check_facts.usable(s, today=TODAY) == {"company.wa_ubi": "123", "insurance.auto": "500k"}


def test_status_lists_what_to_ask_doug():
    s = sheet(
        fact("company.employees", "4", approved=False),
        fact("company.small_business", "unknown", approved=False),
        fact("insurance.cyber", "1M", expires="2026-10-01"),
        fact("insurance.auto", "500k", expires="2026-11-30"),
    )
    assert check_facts.status(s, today=TODAY) == {
        "unknown": ["company.small_business"],
        "unapproved": ["company.employees"],
        "expired": ["insurance.cyber (2026-10-01)"],
        "expiring": ["insurance.auto (2026-11-30)"],
    }


def test_cli_refuses_a_bad_sheet(tmp_path):
    path = tmp_path / "facts.json"
    path.write_text(json.dumps(sheet(fact("references.bob", {"name": "Bob"}))))
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_facts.py"), str(path), "--usable"],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "permission_date" in result.stderr
    assert result.stdout == ""
