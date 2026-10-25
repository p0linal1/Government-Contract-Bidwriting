#!/usr/bin/env python3
"""
evaluation.py — the gated RFP-evaluation pipeline engine.

Why: an RFP evaluation is only as trustworthy as the process behind each number. This engine
models an evaluation as an ORDERED, EXTENSIBLE pipeline of stages, each with a GATE — a
deterministic checklist that must pass before the next stage may start. The governing
principle (spec Requirement 2): a gate verifies that the work was ACTUALLY PERFORMED and
sourced — the research was run, each number cites a source or an explicit UNKNOWN-with-reason —
not merely that an output field is populated. "Performed and found nothing" must be
distinguishable from "not performed"; if it isn't, the gate fails. A confident number that was
invented is worse than an honest UNKNOWN.

Stage types (spec Requirement 1a) drive how a gate is built:
  research       — find facts that exist in the world; gate checks coverage + provenance.
  synthesis      — construct a choice among genuine alternatives; gate checks alternatives were
                   generated and a reasoned selection made, judgments surfaced not resolved.
  reconciliation — deterministic arithmetic + internal consistency; gate checks numbers tie out
                   and canonical/derived docs agree (delegates to opportunity_lint).
A hybrid stage lists a primary + secondary type and runs each discipline for the part it covers.

This module is the ENGINE and the shared GATE TOOLKIT. Individual stage gates live in
gate_<stage>.py and register themselves in STAGES. Nothing company- or bid-specific lives here;
every value is read from the opportunity folder (gate: tests/test_no_hardcoding.py).

CLI:
  python3 -m bidkit.evaluation stages                         # list the registered pipeline
  python3 -m bidkit.evaluation run   <opp-dir> [--upto STAGE] [--json]
  python3 -m bidkit.evaluation gate  <opp-dir> <stage>  [--json]   # run one gate
"""
import argparse, json, os, re, sys
from dataclasses import dataclass, field, asdict
from typing import Callable, Optional

# ----------------------------------------------------------------------------- types
RESEARCH = "research"
SYNTHESIS = "synthesis"
RECONCILIATION = "reconciliation"

FAIL = "fail"
WARN = "warn"


class EvaluationError(Exception):
    pass


@dataclass
class GateFinding:
    """One checklist item's result.

    performed: did the step actually run? False ⇒ "step not run" (a hard signal, distinct from
    a step that ran and found nothing). ok: did the (performed) step satisfy the check?
    """
    check: str
    ok: bool
    severity: str = FAIL          # FAIL (blocking) or WARN (advisory)
    performed: bool = True
    message: str = ""
    evidence: str = ""

    @property
    def blocking_failure(self) -> bool:
        return (not self.ok) and self.severity == FAIL


# confidence levels — the pipeline's currency (replaces pass/fail as the thing that matters).
HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"


@dataclass
class GateResult:
    """A GRADER's output for one stage. It SCORES confidence; it never blocks the pipeline.

    `confidence` is derived from the findings unless a grader sets it explicitly (via
    `set_confidence`): a grader that knows its own confidence — e.g. value-research reading the
    anchor strength — should set it; otherwise it is inferred (all findings ok ⇒ HIGH; only
    advisory/warn issues ⇒ MEDIUM; any hard finding failed or a step not performed ⇒ LOW).

    `passed`/`status` are retained for the write-back linter and backward compatibility, but the
    ENGINE no longer uses them to halt — every stage always runs (spec Requirement 1)."""
    stage: str
    findings: list = field(default_factory=list)
    _confidence: Optional[str] = None

    @property
    def passed(self) -> bool:
        return not any(f.blocking_failure for f in self.findings)

    @property
    def status(self) -> str:
        return "pass" if self.passed else "fail"

    @property
    def confidence(self) -> str:
        if self._confidence is not None:
            return self._confidence
        # LOW only on a BLOCKING (FAIL-severity) problem — a hard check failed or a required step
        # was not performed. An advisory (WARN) issue, even "not performed," caps at MEDIUM: an
        # optional-but-absent item (e.g. no buyer contact recorded) must not tank a stage to LOW.
        if any(f.blocking_failure for f in self.findings):
            return LOW
        if any((not f.ok) for f in self.findings):   # only advisory (WARN) issues remain
            return MEDIUM
        return HIGH

    def set_confidence(self, level):
        """A grader that computes its own confidence (e.g. from anchor strength) sets it here;
        otherwise confidence is inferred from the findings."""
        assert level in (HIGH, MEDIUM, LOW)
        self._confidence = level
        return self

    def add(self, finding: GateFinding):
        self.findings.append(finding)
        return finding

    def to_dict(self):
        return {"stage": self.stage, "status": self.status, "confidence": self.confidence,
                "findings": [asdict(f) for f in self.findings]}


# ----------------------------------------------------------------------------- context
class EvalContext:
    """Lazy loader for one opportunity folder. Gates read artifacts through this so a missing
    artifact is distinguishable from a present-but-incomplete one."""

    def __init__(self, opp_dir):
        self.dir = os.path.abspath(opp_dir)
        if not os.path.isdir(self.dir):
            raise EvaluationError(f"opportunity folder not found: {self.dir}")
        self._cache = {}

    @property
    def id(self):
        return os.path.basename(self.dir.rstrip("/"))

    def path(self, *parts):
        return os.path.join(self.dir, *parts)

    def exists(self, *parts):
        return os.path.exists(self.path(*parts))

    def json(self, *parts):
        key = ("json",) + parts
        if key not in self._cache:
            p = self.path(*parts)
            if not os.path.exists(p):
                self._cache[key] = None
            else:
                with open(p, encoding="utf-8") as fh:
                    try:
                        self._cache[key] = json.load(fh)
                    except json.JSONDecodeError as e:
                        raise EvaluationError(f"invalid JSON in {p}: {e}")
        return self._cache[key]

    def text(self, *parts):
        key = ("text",) + parts
        if key not in self._cache:
            p = self.path(*parts)
            self._cache[key] = open(p, encoding="utf-8").read() if os.path.exists(p) else None
        return self._cache[key]

    def opportunity(self):
        """The opportunity.json, NORMALIZED into the shape the readers parse (P0): an agent may
        write a dict 'recommendation' or a prose 'anchor' that would otherwise crash downstream
        re.search/int calls. Normalization is defensive and idempotent; the raw file on disk is
        untouched here (a separate prep/repair step persists the fix). Cached per context."""
        key = ("opp-normalized",)
        if key not in self._cache:
            raw = self.json("opportunity.json")
            if not isinstance(raw, dict):
                self._cache[key] = raw
            else:
                from . import opportunity_lint  # deferred: avoid import cycle at module load
                norm, _repairs = opportunity_lint.normalize_opportunity(raw)
                self._cache[key] = norm
        return self._cache[key]

    def rfp_files(self):
        d = self.path("rfp")
        return sorted(os.listdir(d)) if os.path.isdir(d) else []


# ----------------------------------------------------------------------------- gate toolkit
# Shared helpers grouped by stage type. Each returns a GateFinding; a gate assembles the
# findings relevant to the part(s) of the stage it covers. The helpers encode the
# "process-performed, not output-present" discipline so no individual gate has to re-derive it.

# ---- provenance primitives (used across types) ----
_UNKNOWN_RE = re.compile(r"\bUNKNOWN\b", re.I)
_URL_RE = re.compile(r"https?://\S+", re.I)
# an RFP-page / document citation like "(RFP p.5)" or "Section 2.4" or "source: <file>.pdf p.1"
_DOC_CITE_RE = re.compile(r"\b(p\.?\s?\d+|page\s+\d+|section\s+[\d.]+|\.pdf|\.docx|\.xlsx)\b", re.I)


def _has_source(blob: str) -> bool:
    return bool(blob) and (bool(_URL_RE.search(blob)) or bool(_DOC_CITE_RE.search(blob)))


def _has_unknown_with_reason(blob: str) -> bool:
    """UNKNOWN is only acceptable with a reason — i.e. more than the bare word on the line."""
    if not blob or not _UNKNOWN_RE.search(blob):
        return False
    # strip the token and surrounding punctuation; something explanatory must remain
    residue = _UNKNOWN_RE.sub("", blob).strip(" :.-—\t")
    return len(residue) >= 8


# ---- research helpers ----
def require_sourced(check: str, label: str, blob: Optional[str], severity=FAIL) -> GateFinding:
    """A produced value must cite a source (URL / RFP page / document) OR be an explicit
    UNKNOWN-with-reason. A bare number/claim with neither FAILS."""
    if blob is None:
        return GateFinding(check, ok=False, severity=severity, performed=False,
                           message=f"{label}: not recorded", evidence="")
    if _has_source(blob):
        return GateFinding(check, ok=True, severity=severity, message=f"{label}: sourced",
                           evidence=blob.strip()[:160])
    if _has_unknown_with_reason(blob):
        return GateFinding(check, ok=True, severity=severity, message=f"{label}: UNKNOWN with reason",
                           evidence=blob.strip()[:160])
    return GateFinding(check, ok=False, severity=severity, performed=True,
                       message=f"{label}: value present but neither sourced nor UNKNOWN-with-reason",
                       evidence=blob.strip()[:160])


def require_attempted(check: str, label: str, blob: Optional[str], severity=FAIL) -> GateFinding:
    """A research step must show it RAN with a recorded outcome. Absence ⇒ not performed ⇒ FAIL."""
    if blob is None or not blob.strip():
        return GateFinding(check, ok=False, severity=severity, performed=False,
                           message=f"{label}: no record the step was attempted", evidence="")
    return GateFinding(check, ok=True, severity=severity, message=f"{label}: attempted",
                       evidence=blob.strip()[:160])


def distinct_notrun_vs_empty(check: str, label: str, blob: Optional[str],
                             found_cues=("found", "no public record", "none found", "not found",
                                         "searched", "no record", "unavailable"),
                             severity=FAIL) -> GateFinding:
    """The strongest research gate: a negative result is only trustworthy if the step VISIBLY ran.
    A blank/absent field is treated as not-performed and FAILS; a recorded outcome (whether it
    found something or explicitly found nothing) PASSES. This is what stops a skipped search from
    masquerading as 'no incumbent found'."""
    if blob is None or not blob.strip():
        return GateFinding(check, ok=False, severity=severity, performed=False,
                           message=f"{label}: blank — cannot tell 'searched, nothing found' from 'not searched'",
                           evidence="")
    low = blob.lower()
    if _has_source(blob) or any(c in low for c in found_cues) or _has_unknown_with_reason(blob):
        return GateFinding(check, ok=True, severity=severity,
                           message=f"{label}: outcome recorded", evidence=blob.strip()[:160])
    return GateFinding(check, ok=False, severity=severity, performed=True,
                       message=f"{label}: content present but no evidence the step actually ran",
                       evidence=blob.strip()[:160])


# ---- synthesis helpers ----
def require_alternatives_considered(check: str, label: str, alternatives, min_n=2,
                                    severity=FAIL) -> GateFinding:
    """A synthesis stage must weigh genuine alternatives, not assume one. `alternatives` is a
    list the gate extracted from the artifact."""
    n = len(alternatives or [])
    if n >= min_n:
        return GateFinding(check, ok=True, severity=severity,
                           message=f"{label}: {n} alternatives considered",
                           evidence="; ".join(str(a)[:40] for a in alternatives[:4]))
    return GateFinding(check, ok=False, severity=severity, performed=(n > 0),
                       message=f"{label}: only {n} option(s) recorded; need >= {min_n} (a single assumed option is not synthesis)",
                       evidence="")


def require_reasoned_selection(check: str, label: str, selection: Optional[str],
                               reasoning: Optional[str], severity=FAIL) -> GateFinding:
    """A selected option must cite WHY it was chosen. A choice with no reasoning FAILS."""
    if not selection or not selection.strip():
        return GateFinding(check, ok=False, severity=severity, performed=False,
                           message=f"{label}: no selection recorded")
    if reasoning and len(reasoning.strip()) >= 20:
        return GateFinding(check, ok=True, severity=severity,
                           message=f"{label}: selection with reasoning", evidence=selection.strip()[:120])
    return GateFinding(check, ok=False, severity=severity, performed=True,
                       message=f"{label}: selection '{selection.strip()[:60]}' has no stated reasoning")


def require_no_default_assumed(check: str, label: str, record: Optional[str],
                               severity=FAIL) -> GateFinding:
    """Guards against a stage that jumped to a conclusion without the synthesis. The caller
    passes the artifact text; the gate requires evidence the alternatives/reasoning exist (this
    is a coarse structural check — the per-stage gate pairs it with the two helpers above)."""
    if not record or not record.strip():
        return GateFinding(check, ok=False, severity=severity, performed=False,
                           message=f"{label}: no synthesis record present")
    return GateFinding(check, ok=True, severity=severity, message=f"{label}: synthesis record present")


def require_cites_upstream(check: str, label: str, reasoning: Optional[str], cues,
                           severity=FAIL) -> GateFinding:
    """A verdict/synthesis that claims to build on upstream stages must reference them. `cues` is
    a list of substrings (e.g. 'value', 'price', 'fit') at least one group of which must appear."""
    if not reasoning or not reasoning.strip():
        return GateFinding(check, ok=False, severity=severity, performed=False,
                           message=f"{label}: no reasoning recorded")
    low = reasoning.lower()
    missing = [grp for grp in cues if not any(term in low for term in grp)]
    if not missing:
        return GateFinding(check, ok=True, severity=severity, message=f"{label}: cites all upstream artifacts")
    return GateFinding(check, ok=False, severity=severity, performed=True,
                       message=f"{label}: reasoning does not cite upstream {missing}")


def require_surfaced_not_resolved(check: str, label: str, surfaced: bool, conflict_present: bool,
                                  severity=FAIL) -> GateFinding:
    """A human-decision/conflict must be surfaced as OPEN, never silently resolved."""
    if conflict_present and not surfaced:
        return GateFinding(check, ok=False, severity=severity, performed=True,
                           message=f"{label}: a human-decision/conflict appears resolved without being surfaced")
    return GateFinding(check, ok=True, severity=severity,
                       message=f"{label}: {'surfaced' if conflict_present else 'none present'}")


# ----------------------------------------------------------------------------- stage registry
@dataclass
class Stage:
    id: str
    order: int
    type: object                 # a StageType string, or a tuple (primary, secondary) for hybrids
    gate: Callable               # Callable[[EvalContext], GateResult]
    tasklist_template: str = ""
    depends_on: list = field(default_factory=list)


STAGES: "list[Stage]" = []


def register(stage: Stage):
    """Register a stage in the pipeline. Gate modules call this at import time. Extensibility
    (spec Requirement 9) = a new register() call + a gate module; the engine never changes."""
    if any(s.id == stage.id for s in STAGES):
        STAGES[:] = [s for s in STAGES if s.id != stage.id]
    STAGES.append(stage)
    STAGES.sort(key=lambda s: s.order)
    return stage


def ordered_stages():
    return list(STAGES)


def get_stage(stage_id):
    for s in STAGES:
        if s.id == stage_id:
            return s
    raise EvaluationError(f"no such stage: {stage_id} (known: {[s.id for s in STAGES]})")


# Import the gate modules so they self-register. Done lazily to avoid import cycles and to keep
# the engine importable even if a gate module is mid-development.
def _load_gates():
    for mod in ("gate_intake", "gate_value", "gate_pricing", "gate_fit", "gate_gonogo"):
        try:
            __import__(f"bidkit.{mod}")
        except ImportError:
            pass


# ----------------------------------------------------------------------------- engine
class EvaluationEngine:
    def __init__(self, opp_dir):
        _load_gates()
        self.ctx = EvalContext(opp_dir)

    def run(self, upto=None):
        """Walk EVERY stage in order, grading each (spec Requirement 1: generate → grade → always
        continue). A weak stage yields a LOW-confidence result, never a halt. `upto` stops after a
        named stage for partial runs. Returns the list of GateResults (each carrying a confidence)."""
        results = []
        for stage in ordered_stages():
            results.append(stage.gate(self.ctx))
            if upto and stage.id == upto:
                break
        return results

    def gate(self, stage_id):
        return get_stage(stage_id).gate(self.ctx)


# ----------------------------------------------------------------------------- CLI
def _print_result(res: GateResult):
    print(f"[{res.confidence}] {res.stage}")
    for f in res.findings:
        mark = "ok " if f.ok else ("!! " if f.blocking_failure else "~  ")
        run = "" if f.performed else " (NOT PERFORMED)"
        print(f"  {mark}{f.check}: {f.message}{run}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stages", help="list the registered pipeline")
    r = sub.add_parser("run", help="run the pipeline for one opportunity")
    r.add_argument("opp"); r.add_argument("--upto"); r.add_argument("--json", action="store_true")
    g = sub.add_parser("gate", help="run one stage's gate")
    g.add_argument("opp"); g.add_argument("stage"); g.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    # When invoked as `python3 -m bidkit.evaluation`, this module runs as __main__ while the gate
    # modules import `bidkit.evaluation` as a SEPARATE module object and register into ITS registry.
    # Resolve the canonical package module so the CLI sees those registrations (not __main__'s).
    import importlib
    mod = importlib.import_module("bidkit.evaluation")
    mod._load_gates()
    if a.cmd == "stages":
        for s in mod.ordered_stages():
            print(f"{s.order:>3}  {s.id:<20} type={s.type}")
        return 0

    try:
        eng = mod.EvaluationEngine(a.opp)
        if a.cmd == "gate":
            results = [eng.gate(a.stage)]
        else:
            results = eng.run(upto=a.upto)
    except mod.EvaluationError as e:
        print(f"EVALUATION ERROR: {e}"); return 2

    if a.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        for res in results:
            _print_result(res)
    # The pipeline always completes; exit 0. A non-zero code would wrongly imply a halt. Low
    # confidence is reported per-stage, not an error — scripts read --json for the levels.
    return 0


if __name__ == "__main__":
    sys.exit(main())
