"""
Gate: the shared library must contain NOTHING opportunity- or company-specific. Every such
value belongs in an opportunity.json. This test fails the build if a company name, a bid
identifier, a dollar figure, a person's contact detail, or a hand-measured coordinate tuple
appears anywhere in bidkit/bidkit/.

Rationale (design §"Correctness properties" #5): both historical bids hard-coded these and
had to be rewritten for the next bid.
"""
import os, re, glob

PKG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bidkit")

FORBIDDEN = [
    # company / people / bids
    (r"\bYourCo\b", "company name"),
    (r"\bBIPIN\b", "bid id"),
    (r"\b26-013\b", "bid id"),
    (r"\b2026-110\b", "bid id"),
    (r"\bDental\b", "bid id"),
    (r"\bKennewick\b", "agency"),
    (r"\bFGA\b|Federal Government Advisors", "partner"),
    # identifiers / contacts
    (r"\b\d{2}-\d{7}\b", "EIN-shaped number"),
    (r"[A-Za-z0-9._%+-]+@gmail\.", "personal email"),
    # money and form names
    (r"\$\s?[0-9]{1,3}(,[0-9]{3})+", "dollar figure"),
    (r"\bA7\b|\bA11\b|\bA9\b", "specific form id"),
    # hand-measured coordinates: a literal 2-tuple of 2-3 digit numbers used as a position
    (r"insert_(?:text|image)\(\s*\(\s*\d{2,3}\s*,\s*\d{2,3}\s*\)", "literal coordinate"),
    (r"fitz\.Rect\(\s*\d{2,3}\s*,\s*\d{2,3}\s*,\s*\d{2,3}\s*,\s*\d{2,3}\s*\)", "literal rect"),
]


def _sources():
    return sorted(glob.glob(os.path.join(PKG, "*.py")))


# A portal adapter may name ITS OWN portal (like "WEBS" or "Public Purchase"): that is portal data, not
# company data. The partner pattern is therefore not applied to the file whose sole job is that portal —
# the codes it searches with still have to come from the criteria file, which the rest of the gate enforces.
PORTAL_NAME_EXEMPT = {"fga.py": {"partner"}, "triage.py": {"partner"}}


def test_library_has_no_hardcoded_opportunity_values():
    hits = []
    for path in _sources():
        text = open(path, encoding="utf-8").read()
        exempt = PORTAL_NAME_EXEMPT.get(os.path.basename(path), set())
        # strip docstrings/comments? NO — docstrings that name a bid are also a smell; but allow
        # the module docstring's motivating "why" to mention the historical bid generically.
        # We therefore only exempt lines that are pure comments starting with '# hist:'.
        for lineno, line in enumerate(text.splitlines(), start=1):
            if line.strip().startswith("# hist:"):
                continue
            for pat, label in FORBIDDEN:
                if label in exempt:
                    continue
                if re.search(pat, line):
                    hits.append(f"{os.path.basename(path)}:{lineno} [{label}] {line.strip()[:90]}")
    assert not hits, "hard-coded opportunity/company values in bidkit:\n  " + "\n  ".join(hits)


def test_sourcing_harness_carries_no_codes():
    """The sourcing harness must not know any NAICS / PSC code: they are company data in the criteria file."""
    text = open(os.path.join(PKG, "fga.py"), encoding="utf-8").read()
    body = "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))
    # 6-digit NAICS or 4-char PSC literals as quoted strings (docstring examples like 54151x are fine)
    codes = re.findall(r"[\"'](\d{6}|[A-Z]\d{3}|\d[A-Z]\d{2}|[A-Z]{2}\d{2})[\"']", body)
    assert not codes, f"fga.py hard-codes classification codes: {codes}"


def test_every_module_is_config_or_argument_driven():
    """Each CLI module must accept its opportunity-specific inputs via argv/config, i.e. define
    main(argv=None) — not read fixed paths at import time."""
    for path in _sources():
        name = os.path.basename(path)
        if name.startswith("_") or name == "__init__.py":
            continue
        text = open(path, encoding="utf-8").read()
        assert "def main(argv=None)" in text, f"{name} lacks main(argv=None)"
        # no absolute /Users/... paths baked in (macOS system font paths are allowed)
        for m in re.finditer(r"/Users/[^\s\"']+", text):
            raise AssertionError(f"{name} hard-codes a user path: {m.group(0)}")
