#!/usr/bin/env python3
"""
harness.py — the daily evaluation-harness orchestrator.

Why: this is the entry point that turns the repo into an unattended daily run — it drives each
opportunity through the gated evaluation pipeline, under a configurable AUTONOMY MODE, and produces
a RunReport the digest composer turns into the daily email. It reuses the existing deterministic
ingest (inbox / fga / portal / brief / calendar) rather than reimplementing it, and keeps the AI
"writer" behind a protocol so the harness ships working today (notify-only) and the writer slots in
when a headless agent runner exists.

Autonomy modes (spec Requirement 6/8; mode is CONFIG, never code):
  a  notify-only [DEFAULT] — evaluate + report; never run the agent writer, never change canonical docs.
  b  quarantine            — run the agent writer, but its output goes to opportunities/<id>/<quarantine>/;
                             canonical opportunity.json is untouched; a human promotes.
  c  full                  — the agent writer may write canonical docs, gated solely by the gates.

The AgentWorker is a protocol. NullAgentWorker (mode a) does nothing. CliAgentWorker (b/c) shells to
a configured headless agent runner — and if none is configured/available the harness DEGRADES to
mode a and says so, keeping honest with the fact that there is no headless agent CLI on this box yet.

Idempotency: a per-opportunity content hash (rfp/ + opportunity.json) is stored in the state file;
an opportunity whose inputs are unchanged since the last run is not re-worked.

Nothing company- or bid-specific lives here; all values come from the config and the opportunity
folders (gate: tests/test_no_hardcoding.py).

CLI:
  python3 -m bidkit.harness run --cfg inbox/harness.json [--opps <dir>] [--dry-run] [--no-ingest]
"""
import argparse, hashlib, json, os, sys
from dataclasses import dataclass, field, asdict

from .evaluation import EvaluationEngine, EvalContext, ordered_stages, _load_gates, HIGH, MEDIUM, LOW
from . import portfolio


class HarnessError(Exception):
    pass


# --------------------------------------------------------------------------- config
DEFAULTS = {
    # autonomy governs the AGENT RUNNER (the research/synthesis generators), never the deterministic
    # plane. 'a' notify-only [default — safe]; 'b' quarantine (agent writes to <quarantine_dir>/, a
    # human promotes); 'c' full (agent writes canonical docs, gated solely by the confidence
    # graders). Set 'c' + agent_cli in the live config, not here.
    "autonomy": "a",
    # the headless agent runner, as a command PREFIX, e.g. Kiro CLI:
    #   "kiro-cli chat --no-interactive --trust-all-tools"
    # (requires an active mwinit session + `kiro-cli login`). The per-opportunity task prompt is
    # appended as the final argument and the runner is executed with cwd set to the opportunity
    # folder. None ⇒ no runner ⇒ a b/c run degrades to notify-only.
    "agent_cli": None,
    "agent_timeout_sec": 1800,
    # DEEPEN LOOP (P2c): max focused agent re-dispatches to close retrievable LOW-confidence gaps on
    # a single opp before surfacing them. 0 disables; 1 is a safe default (bounded, no runaway loops).
    "deepen_max": 1,
    "quarantine_dir": "proposed",
    "opportunities_dir": "../opportunities",
    "queue": "../inbox/queue.jsonl",
    "state": "../inbox/portfolio-state.json",
    "ingest": {"enabled": False},
    # deterministic PREP pass, run over the WHOLE portfolio before the gates. These steps are
    # read-the-documents-and-record-facts only — never a judgment call — so they are safe to run
    # unattended on every opportunity, not just newly-filed ones. 'portal_fetch' touches live
    # portals (needs a logged-in session) so it is opt-in and off by default.
    # NOTE: 'portal_fetch' is deliberately ABSENT here. Its default is MODE-DEPENDENT (off in
    # notify-only mode a; on in agent modes b/c — see orchestrate's retrieval-first default). An
    # explicit prep.portal_fetch in the operator's config overrides that.
    "prep": {"enabled": True, "normalize": True, "brief": True, "confirm_due": True,
             "value_estimate": True, "pricing": True, "fit": True, "gonogo": True,
             "calendar": True},
    # path to the bidder's capability-superset JSON for the document-only fit generator. Config,
    # never library (keeps bidkit company-agnostic); None ⇒ the fit generator uses generic configs.
    "capability": None,
}


def load_config(path):
    cfg = dict(DEFAULTS)
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        for k, v in raw.items():
            if not k.startswith("_"):
                cfg[k] = v
    if cfg["autonomy"] not in ("a", "b", "c"):
        raise HarnessError(f"autonomy must be a/b/c, got {cfg['autonomy']!r}")
    return cfg


# --------------------------------------------------------------------------- agent writer protocol
class AgentWorker:
    """Protocol: run_intake/run_build receive an opportunity dir and an output root (which is the
    opp dir itself in mode c, or the quarantine subdir in mode b)."""
    name = "base"

    def available(self):
        return True

    def run(self, opp_dir, out_root, extra=None):
        raise NotImplementedError


class NullAgentWorker(AgentWorker):
    """Mode a: do nothing. The human runs the evaluation in the IDE; the harness only notifies."""
    name = "null"

    def available(self):
        return True

    def run(self, opp_dir, out_root, extra=None):
        return {"ran": False, "note": "notify-only (mode a) — no agent writer"}


# The agent-runner TASK CONTRACT. This is the prompt handed to the headless agent for one
# opportunity: it names the stage artifacts to produce and the discipline to follow. It names NO
# company/bid specifics (those come from the opportunity folder + the repo's own steering, which the
# agent reads automatically) so the library stays bid-agnostic (test_no_hardcoding.py). {out_root}
# is where to write (the opp dir in mode c, the quarantine subdir in mode b).
AGENT_TASK_PROMPT = """\
You are running headlessly to evaluate ONE government solicitation (an "opportunity"). The current
working directory IS the opportunity folder. Follow this repository's steering (.kiro/steering/ —
especially the bid guardrails and company profile) as hard rules; they are already in your context.

Goal: upgrade this opportunity's evaluation from the deterministic document-only placeholders already
on file to RESEARCHED, best-effort outputs — using web search where it helps — and write each stage's
artifact back into {out_root}. Produce, for every stage, an output that carries its reasoning, its
sources (a URL / RFP page, or an explicit UNKNOWN-with-reason), and a HIGH/MEDIUM/LOW confidence.

RETRIEVE BEFORE YOU PUNT. If a document you need is named but missing (the RFP PDF, an addendum, a
buyer contact), ATTEMPT to retrieve it first — pull it from the solicitation portal or the web into
rfp/ and read it. Only record "UNKNOWN" or ask the human to "pull the RFP" if retrieval genuinely
fails; an unretrieved-but-retrievable fact is work for you to do, not a decision to hand back.

Stage artifacts to produce (overwrite the document-only placeholders; keep the shape the graders read):
  1. research/value-analysis.md + opportunity.json "value_estimate": the four independent value
     lines (buyer affordability; procurement thresholds; comparable awards + unit-rate proxy;
     bottom-up cost-to-deliver) AND the incumbent prior-contract hunt. If you find a real
     incumbent/appropriation figure, make it the anchor (with its source) and you may grade HIGH;
     otherwise converge the lines to a corridor at MEDIUM/LOW.
  2. research/pricing.md: the three-axis reconciliation (labor hours; staff x schedule capacity;
     mandated schedule), AI acceleration as a COMPRESSION FACTOR (fewer hours, not a discounted
     rate), recurring sized bottom-up (infra + support labor + margin), reconciled to the value
     corridor. Surface reserved-capacity / scope / rate as decisions.
  3. research/fit-synthesis.md: what the RFP wants (evaluator priorities / scoring / risk / locality);
     MORE THAN ONE candidate configuration from the capability superset; a selected best-fit NAMED and
     followed by its reasoning (a "because ..." clause citing why it beats the alternatives — do NOT
     merely restate this instruction); a competitiveness read. Frame any prior performance as
     transferable experience with a reference-gap note — never an overclaimed turnkey match. State any
     staffing/locality/regulated-data conflict and its most-likely resolution; do not silently resolve it.
  4. research/go-no-go.md + the summary: a verdict (BID / CONDITIONAL-BID / PASS / FOOTHOLD) whose
     reasoning cites the value, pricing, and fit outputs, with a confidence capped by how thin the
     upstream research is. State conditions for a conditional/foothold verdict. A well-founded PASS is
     a valid outcome.

opportunity.json FIELD SCHEMA — write these EXACT shapes (the deterministic tooling parses them; a
dict or prose in a typed field breaks the pipeline):
  - "status": a single lowercase verb STRING, one of: "bid" | "conditional" | "pass" | "foothold".
  - "recommendation": a single short STRING (<=120 chars), e.g. "CONDITIONAL-BID — foothold, bid only
     if teaming closes the reference gap". NOT an object. Put the long reasoning/conditions in
     research/go-no-go.md, not here.
  - "value_estimate": an object with NUMERIC dollar fields — "anchor"/"low"/"likely"/"high" are
     INTEGERS (e.g. 1119683, not "$1.1M" and not a sentence); "confidence" is one of
     HIGH|MEDIUM-HIGH|MEDIUM|LOW; "anchor_source" is a URL string; put any prose explanation in
     "anchor_basis"/"basis" (strings). Example:
       "value_estimate": {{"anchor": 1119683, "anchor_source": "https://city.gov/budget.pdf",
         "anchor_basis": "FY26 adopted appropriation for the project", "low": 900000,
         "likely": 1600000, "high": 2600000, "confidence": "MEDIUM-HIGH",
         "basis": "four-line triangulation; incumbent prior contract", "source": "research/value-analysis.md"}}

BEFORE YOU FINISH, reconcile write-back: the value headline in opportunity.json ("anchor"/"likely")
must agree with the figure in research/value-analysis.md, and "status"/"recommendation" must agree
with research/go-no-go.md and the summary. If they disagree, FIX them so they match — do not leave a
drift for the human to catch.

The one hard rule: never present a judgment as a settled fact. Every number carries a source or an
explicit UNKNOWN-with-reason and a confidence. Do not invent a fact to dissolve a contradiction —
state it, give the most-likely resolution, mark it LOW, and flag it. Keep all generated prose honest
per the guardrails (no overclaimed past performance; product-vs-company certification distinction).

When done, print a one-line summary of the verdict and the value headline.
"""


class CliAgentWorker(AgentWorker):
    """Modes b/c: shell to a configured headless agent runner (e.g. Kiro CLI, invoked as
    `kiro-cli chat --no-interactive --trust-all-tools`). `agent_cli` is the command PREFIX; the
    composed per-opportunity task prompt is appended as the final argument and the runner is executed
    with cwd=out_root so it reads/writes the opportunity folder. available() is False when no
    agent_cli is configured, which makes the orchestrator degrade to notify-only and say so.

    The runner inherits this repo's steering (.kiro/steering/) automatically, so the honesty
    guardrails apply without being re-injected here. A timeout or non-zero exit degrades gracefully
    to {"ran": False} — one opportunity's agent failure never aborts the daily run."""
    name = "cli"

    def __init__(self, agent_cli, timeout_sec=1800, prompt=AGENT_TASK_PROMPT):
        self.agent_cli = agent_cli
        self.timeout_sec = timeout_sec
        self.prompt = prompt

    def available(self):
        return bool(self.agent_cli)

    def run(self, opp_dir, out_root, extra=None):
        if not self.available():
            return {"ran": False, "note": "no agent runner configured"}
        import shlex, subprocess
        os.makedirs(out_root, exist_ok=True)
        prompt = self.prompt.format(out_root=out_root)
        if extra:
            # a focused follow-up instruction (the deepen loop, P2c): retrieve X then re-evaluate
            # just that stage. Appended so the agent still has the full task contract in context.
            prompt = prompt + "\n\nFOCUSED FOLLOW-UP FOR THIS RUN:\n" + extra
        # agent_cli may be a string prefix ("kiro-cli chat --no-interactive --trust-all-tools") or a
        # pre-split list; the prompt is the final positional argument.
        base = shlex.split(self.agent_cli) if isinstance(self.agent_cli, str) else list(self.agent_cli)
        argv = base + [prompt]
        try:
            proc = subprocess.run(argv, cwd=out_root, capture_output=True, text=True,
                                  timeout=self.timeout_sec)
        except FileNotFoundError as e:
            return {"ran": False, "note": f"agent runner not found: {e}"}
        except subprocess.TimeoutExpired:
            return {"ran": False, "note": f"agent runner timed out after {self.timeout_sec}s"}
        if proc.returncode != 0:
            return {"ran": False, "note": f"agent runner exited {proc.returncode}",
                    "stderr": (proc.stderr or "")[-500:]}
        return {"ran": True, "note": "agent runner completed",
                "summary": (proc.stdout or "").strip()[-500:]}


def make_worker(cfg):
    if cfg["autonomy"] == "a":
        return NullAgentWorker()
    return CliAgentWorker(cfg.get("agent_cli"), timeout_sec=cfg.get("agent_timeout_sec", 1800))


# --------------------------------------------------------------------------- idempotency
# opportunity.json keys the AGENT writes (its evaluation OUTPUT) — excluded from the idempotency
# hash so that the agent writing a verdict does not churn the hash and cause endless re-litigation.
# The hash tracks INPUT facts only (id/title/due/format/portal_record/contact/… + the rfp/ docs);
# a committed verdict is re-opened only when a real input changes (a new addendum, a confirmed due
# date change, a new followup), never because the agent recorded its own conclusion.
_AGENT_OUTPUT_KEYS = ("value_estimate", "status", "recommendation", "recommendation_detail",
                      "status_detail", "gates", "decided_at", "inputs_digest")


def content_hash(opp_dir):
    """Stable hash of the INPUTS that would change an evaluation: the input fields of
    opportunity.json (agent-written judgment fields excluded) + the rfp/ file list & sizes. This is
    what makes a researched opportunity reach a steady state: once the agent has written its verdict,
    re-running does not re-trigger it unless a genuine input moved."""
    h = hashlib.sha256()
    oj = os.path.join(opp_dir, "opportunity.json")
    if os.path.exists(oj):
        try:
            opp = json.load(open(oj, encoding="utf-8"))
            inputs = {k: v for k, v in opp.items()
                      if k not in _AGENT_OUTPUT_KEYS and not k.startswith("_")}
            h.update(json.dumps(inputs, sort_keys=True, ensure_ascii=False).encode())
        except json.JSONDecodeError:
            h.update(open(oj, "rb").read())   # unparseable: fall back to raw bytes
    rfp = os.path.join(opp_dir, "rfp")
    if os.path.isdir(rfp):
        for name in sorted(os.listdir(rfp)):
            p = os.path.join(rfp, name)
            if os.path.isfile(p):
                h.update(name.encode())
                h.update(str(os.path.getsize(p)).encode())
    return h.hexdigest()


def _load_state(state_path):
    if state_path and os.path.exists(state_path):
        try:
            return json.load(open(state_path, encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_state(state_path, state):
    os.makedirs(os.path.dirname(state_path) or ".", exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)


# --------------------------------------------------------------------------- run report
# Map a failing gate check to a short, human-actionable REMEDY — so the digest tells the reader
# not just that a gate failed but what to do about it. Keyed by check id (the stable gate check
# name); a sensible default covers any check not listed. No company/bid specifics (generic verbs).
GATE_REMEDY = {
    "due-confirmed": "Confirm the deadline from the RFP and set due.confirmed in opportunity.json.",
    "format-confirmed": "Copy the RFP's format rules into opportunity.json 'format'.",
    "attachments-present": "Fetch the posted documents into rfp/ (portal fetch).",
    "value-analysis-present": "Run the value-research step (research/value-analysis.md).",
    "incumbent-search": "Run the incumbent prior-contract hunt and record the outcome.",
    "confidence-stated": "State a convergence + confidence grade in the value analysis.",
    "high-confidence-anchor": "Downgrade confidence or add a real incumbent/appropriation anchor.",
    "value-written-back": "Write value_estimate back into opportunity.json.",
    "three-axis-reconciliation": "State the hours / capacity / schedule reconciliation.",
    "recurring-bottom-up": "Size recurring bottom-up (infra + support labor + margin).",
    "reconciled-to-corridor": "Reconcile the priced number against the value corridor.",
    "rfp-wants-extracted": "Extract the RFP's evaluation priorities / scoring weights.",
    "candidate-configs": "Consider more than one candidate configuration (synthesis, not a default).",
    "selected-config": "State the selected best-fit configuration with reasoning.",
    "competitiveness-assessed": "Assess whether the best-fit configuration would be competitive.",
    "locality-conflict": "Surface the staffing/locality/regulated-data conflict as a human-decision.",
    "pastperf-honest": "Reframe prior performance as transferable experience + a reference-gap note.",
    "verdict-stated": "State a BID / CONDITIONAL-BID / PASS / FOOTHOLD verdict.",
    "cites-upstream": "Make the verdict reasoning cite the value, pricing, and fit artifacts.",
    "upstream-confidence": "Deepen the low-confidence upstream stage(s) to raise verdict confidence.",
    "conditions-stated": "State the conditions the conditional/foothold verdict depends on.",
    "value-consistency": "Sync opportunity.json value_estimate to research/value-analysis.md.",
    "recommendation-consistency": "Make opportunity-summary.md and go-no-go.md agree on the verdict.",
    "status-consistency": "Set opportunity.json status to match the recommendation.",
    "portal-record-consistency": "Reconcile opportunity.json portal_record with rfp/portal-record.json.",
}
_DEFAULT_REMEDY = "Complete this gate's checklist (see the stage's steering definition of done)."


@dataclass
class OppResult:
    opportunity: str
    worked: bool = False
    skipped_reason: str = ""
    stage_reached: str = ""
    gates_failed: int = 0                                # retained: count of LOW-confidence stages
    recommendation: str = ""
    stage_confidence: dict = field(default_factory=dict)  # {stage_id: HIGH|MEDIUM|LOW}
    overall_confidence: str = ""                          # the go/no-go verdict's confidence
    open_items: list = field(default_factory=list)
    review_items: list = field(default_factory=list)      # [{"stage","confidence","reason","remedy"}]
    prep_notes: list = field(default_factory=list)        # what the deterministic prep pass did
    deepen_passes: int = 0                                 # focused agent re-dispatches (P2c)
    expired: bool = False                                  # confirmed due date is in the past (P4a)
    error: str = ""


@dataclass
class RunReport:
    autonomy: str
    mode_note: str = ""
    results: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)

    def to_dict(self):
        return {"autonomy": self.autonomy, "mode_note": self.mode_note,
                "counts": self.counts, "results": [asdict(r) for r in self.results]}


# --------------------------------------------------------------------------- OPEN items
import re

# A human-decision section is identified STRUCTURALLY by its heading, not by keyword-matching
# individual lines (which swept in section headers and restated analysis). These are the headings
# the intake/build steering actually produces: "Open items for the human", "Decision(s) for the
# human", "Critical human decisions", "Open items / decisions for the human", "Human action items".
_OPEN_HEADING = re.compile(
    r"(?im)^#{1,6}\s*(?:\d+\.\s*)?"
    r"(?:open items?|decisions?|critical human decisions?|human (?:decisions?|action items?)|"
    r"needs?\s+(?:your\s+)?decision|open questions?)"
    r"(?:\s*(?:/|&|and)\s*(?:decisions?|open items?))?"
    r"\b[^\n]*$")
# a markdown list item: '-', '*', or 'N.'/'N)'
_LIST_ITEM = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.+)$")
_ANY_HEADING = re.compile(r"^#{1,6}\s")


def _open_items(ctx):
    """Pull human-decision OPEN items from the opportunity summary — DETERMINISTICALLY, by document
    structure: find a heading whose title names an open-items / human-decision section, then collect
    the list items (-, *, or N.) under it until the next heading, joining wrapped continuation lines.
    Non-list lead-in prose under the heading is skipped. No keyword guessing on individual lines."""
    text = ctx.text("opportunity-summary.md") or ""
    lines = text.splitlines()
    items, i, n = [], 0, len(lines)
    while i < n:
        if not _OPEN_HEADING.match(lines[i]):
            i += 1
            continue
        # inside a decision section: walk until the next heading
        i += 1
        cur = None
        while i < n and not _ANY_HEADING.match(lines[i]):
            m = _LIST_ITEM.match(lines[i])
            if m:
                if cur is not None:
                    items.append(cur)
                cur = m.group(1).strip()
            elif cur is not None and lines[i].strip():
                cur += " " + lines[i].strip()          # wrapped continuation of the current item
            elif cur is not None and not lines[i].strip():
                items.append(cur); cur = None            # blank line ends the current item
            # non-list, non-continuation line (lead-in prose) is skipped
            i += 1
        if cur is not None:
            items.append(cur)
    # normalize whitespace and strip markdown emphasis markers (** and *); cap length and count
    cleaned = []
    for it in items:
        it = re.sub(r"\s+", " ", it).strip()
        it = re.sub(r"\*\*(.+?)\*\*", r"\1", it)   # **bold** -> bold
        it = it.replace("**", "").replace("*", "").strip()
        if it:
            cleaned.append(it[:160])
    return cleaned[:12]


def prep_opportunity(opp_dir, prep_cfg, portals_path=None, capability_path=None):
    """Deterministic PREP pass for one opportunity, run BEFORE the gates. These steps only read the
    documents and record facts (never a judgment call), so they are safe to run unattended over the
    whole portfolio — closing the gap where brief/confirm/calendar previously ran only for
    newly-filed opps at poll time. Returns a list of short notes describing what it did.

    Steps (each individually toggleable in prep_cfg):
      portal_fetch   (opt-in, off by default — touches live portals) : pull posted docs into rfp/
      brief                                                          : refresh facts from rfp/
      confirm_due                                                    : auto-confirm a doc-sourced due date
      value_estimate                                                 : document-only value estimate (+ write-back)
      pricing                                                        : document-only pricing skeleton
      fit                                                            : document-only fit synthesis
      gonogo                                                         : document-only provisional verdict (research/go-no-go.md only)
      calendar                                                       : regenerate the .ics

    `capability_path` (config, never library) is handed to the fit generator so it can read the
    bidder's capability superset; None is fine (the fit generator falls back to generic configs).
    """
    from . import brief
    notes = []

    # 0a) NORMALIZE opportunity.json first (P0): heal any agent-written malformed shape (a dict
    #     recommendation, a prose anchor, a sentence status) so every downstream reader sees the
    #     canonical types and nothing crashes. Persisted to disk; idempotent.
    if prep_cfg.get("normalize", True):
        try:
            from . import opportunity_lint
            reps = opportunity_lint.normalize_dir(opp_dir)
            if reps:
                notes.append(f"normalized opportunity.json ({len(reps)} field(s) repaired)")
        except Exception as e:  # noqa: BLE001
            notes.append(f"normalize skipped: {str(e)[:80]}")

    # 0b) optional portal fetch — only when enabled AND the opportunity still lacks posted documents
    if prep_cfg.get("portal_fetch"):
        try:
            from . import portal
            rfp = os.path.join(opp_dir, "rfp")
            has_docs = os.path.isdir(rfp) and any(
                f.lower().endswith((".pdf", ".docx", ".xlsx", ".doc", ".xls")) and not f.startswith("portal-")
                for f in os.listdir(rfp))
            if not has_docs:
                portals = portal.load_portals(portals_path) if portals_path else {}
                portal.fetch_for_opportunity(opp_dir, portals=portals)  # best-effort; adapter handles login
                notes.append("portal fetch attempted (rfp/ had no documents)")
        except Exception as e:  # noqa: BLE001 — a portal/login failure must not abort prep
            notes.append(f"portal fetch skipped: {str(e)[:80]}")

    # 1) refresh the facts sheet + research plan from whatever is in rfp/ now
    facts = None
    if prep_cfg.get("brief", True):
        try:
            facts, changed, _nq = brief.run(opp_dir, research=True)
            notes.append("brief refreshed" + ("" if changed else " (no change)"))
        except Exception as e:  # noqa: BLE001
            notes.append(f"brief skipped: {str(e)[:80]}")

    # 2) auto-confirm the due date when it came from a document (provenance-gated inside brief)
    if prep_cfg.get("confirm_due", True):
        try:
            if facts is None:
                facts, _c, _n = brief.run(opp_dir, research=False)
            ok, note = brief.auto_confirm_due_from_docs(opp_dir, facts)
            if ok:
                notes.append(f"due auto-confirmed ({note})")
        except Exception as e:  # noqa: BLE001
            notes.append(f"confirm-due skipped: {str(e)[:80]}")

    # 3) deterministic DOCUMENT-ONLY value estimate (the generator half of value-research): so every
    #    opportunity carries a best-effort, LOW-confidence value corridor instead of a blank, even
    #    when no agent-runner web-search pass has run. NON-DESTRUCTIVE — gen_value leaves a stronger
    #    (analyst/agent-runner) estimate untouched and only fills a blank or its own prior output.
    if prep_cfg.get("value_estimate", True):
        try:
            from . import gen_value
            notes.append(gen_value.generate(opp_dir))
        except Exception as e:  # noqa: BLE001 — a value-gen failure must not abort prep
            notes.append(f"value-gen skipped: {str(e)[:80]}")

    # 4) deterministic DOCUMENT-ONLY generators for the downstream stages, so pricing / fit / verdict
    #    are never blank either. Each is NON-DESTRUCTIVE (stands aside for analyst work) and writes
    #    only its research/*.md artifact — never a canonical JUDGMENT field. Order matters: pricing
    #    reads the value corridor; the verdict cites all three upstream artifacts. All document-only
    #    outputs grade LOW, which is the honest score until the agent-runner research pass runs.
    if prep_cfg.get("pricing", True):
        try:
            from . import gen_pricing
            notes.append(gen_pricing.generate(opp_dir))
        except Exception as e:  # noqa: BLE001
            notes.append(f"pricing-gen skipped: {str(e)[:80]}")

    if prep_cfg.get("fit", True):
        try:
            from . import gen_fit
            notes.append(gen_fit.generate(opp_dir, capability_path=capability_path))
        except Exception as e:  # noqa: BLE001
            notes.append(f"fit-gen skipped: {str(e)[:80]}")

    if prep_cfg.get("gonogo", True):
        try:
            from . import gen_gonogo
            notes.append(gen_gonogo.generate(opp_dir))
        except Exception as e:  # noqa: BLE001
            notes.append(f"gonogo-gen skipped: {str(e)[:80]}")

    # 5) regenerate the calendar from the (possibly updated) dates
    if prep_cfg.get("calendar", True):
        try:
            from . import calendar as cal
            cal.write_ics_for_opportunity(opp_dir)
            notes.append("calendar regenerated")
        except Exception as e:  # noqa: BLE001
            notes.append(f"calendar skipped: {str(e)[:80]}")

    return notes


def _has_committed_verdict(ctx):
    """True when the AGENT (not the document-only generator) has already produced a researched
    verdict for this opportunity: a value_estimate with a researched anchor, or a status/
    recommendation, or an inputs_digest stamp from a prior agent run. A document-only estimate
    (generator tag set, no anchor) does NOT count — it is a placeholder awaiting research."""
    opp = ctx.opportunity() or {}
    if opp.get("inputs_digest"):
        return True
    if opp.get("status") or opp.get("recommendation"):
        return True
    ve = opp.get("value_estimate") or {}
    if ve.get("anchor") and ve.get("anchor_source") and not ve.get("generator"):
        return True
    return False


def _is_expired(ctx):
    """True when the opportunity's CONFIRMED due date is in the past. A DETECTED/unconfirmed due is
    not trusted enough to call something expired. An opportunity may opt back in by setting
    opportunity.json 'chase_reissue': true (we are pursuing the next cycle, not this closed one)."""
    opp = ctx.opportunity() or {}
    if opp.get("chase_reissue"):
        return False
    due = opp.get("due") or {}
    if not due.get("confirmed") or not due.get("date"):
        return False
    import datetime as _dt
    try:
        d = _dt.date.fromisoformat(str(due["date"])[:10])
    except ValueError:
        return False
    return d < _dt.date.today()


def _should_run_agent(ctx, unchanged):
    """Whether the agent writer should run for this opportunity:
      - PAST its confirmed deadline            -> SKIP ("deadline passed; not researching") [P4a]
      - inputs changed since the last pass     -> run ("inputs changed")
      - never agent-researched yet             -> run ("not yet researched")
      - researched + inputs unchanged          -> SKIP ("already researched; inputs unchanged") [P1c]
    Returns (bool, reason). Deadline wins: no agent budget is spent on a bid that cannot be
    submitted (unless opportunity.json sets chase_reissue=true)."""
    if _is_expired(ctx):
        return False, "deadline passed; not researching"
    if not unchanged:
        return True, "inputs changed"
    if not _has_committed_verdict(ctx):
        return True, "not yet researched"
    return False, "already researched; inputs unchanged"


def _stamp_decision(opp_dir, inputs_digest):
    """Record that the agent committed a verdict for the current INPUTS: an inputs_digest (so a
    later run can tell the verdict still matches the inputs) + a decided_at timestamp. Written to
    opportunity.json; both keys are excluded from content_hash so stamping does not churn it."""
    import datetime as _dt
    p = os.path.join(opp_dir, "opportunity.json")
    if not os.path.exists(p):
        return
    try:
        opp = json.load(open(p, encoding="utf-8"))
    except json.JSONDecodeError:
        return
    opp["inputs_digest"] = inputs_digest
    opp["decided_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(opp, fh, indent=1, ensure_ascii=False)
        fh.write("\n")


def _needs_prep(ctx):
    """True when an 'unchanged' opportunity still has outstanding DETERMINISTIC prep work, so prep
    reaches backlog the idempotency hash would otherwise skip — while still stabilising so an opp in
    a steady state is genuinely skipped next run (never re-prepped forever). Triggers:
      - an unconfirmed due date (prep may confirm it from a document); OR
      - no value_estimate at all (the document-only value generator can fill it); OR
      - a missing downstream research artifact (pricing / fit / verdict) the document-only
        generators can fill.
    Each document-only artifact, once written, is itself steady state (the generators reproduce
    them and are non-destructive), so their mere presence does NOT keep re-triggering prep."""
    opp = ctx.opportunity() or {}
    due = opp.get("due") or {}
    if not due.get("confirmed"):
        return True
    if not (opp.get("value_estimate") or {}):
        return True
    # a downstream research artifact is still missing ⇒ its document-only generator hasn't run
    for rel in (("research", "pricing.md"), ("research", "fit-synthesis.md"),
                ("research", "go-no-go.md")):
        if not ctx.exists(*rel):
            return True
    return False


def _grade_all_stages(ctx):
    """Grade EVERY stage (the pipeline never halts now) and return:
      stage_confidence: {stage_id: HIGH|MEDIUM|LOW}
      review_items:     [{stage, confidence, reason, remedy}] for each LOW/MEDIUM stage, so the
                        digest can show "here is the output and how to raise its confidence" — a
                        review/override list, not a stuck/blocked list.
    Each review item's reason is the most informative not-ok finding on that stage; the remedy is
    the human-actionable next step from GATE_REMEDY."""
    _load_gates()
    stage_confidence, review = {}, []
    for s in ordered_stages():
        res = s.gate(ctx)
        stage_confidence[s.id] = res.confidence
        if res.confidence != HIGH:
            # pick the finding that best explains the lowered confidence: a blocking fail first,
            # else the first advisory issue.
            bad = next((f for f in res.findings if f.blocking_failure), None) \
                or next((f for f in res.findings if not f.ok), None)
            check = bad.check if bad else ""
            review.append({
                "stage": s.id,
                "confidence": res.confidence,
                "reason": bad.message if bad else "confidence below HIGH",
                "remedy": GATE_REMEDY.get(check, _DEFAULT_REMEDY) if bad else _DEFAULT_REMEDY,
                "kind": _review_kind(check),
            })
    return stage_confidence, review


# Review-item classification (P2b): a gap the HARNESS can resolve by retrieving/running something
# (the next run picks it up) vs. a genuine human JUDGMENT the operator must settle. Keyed by the
# stable gate check id. METHOD language only — no company/bid specifics.
_NEEDS_RESEARCH_CHECKS = frozenset({
    "due-confirmed", "format-confirmed", "attachments-present", "portal-record-consistency",
    "value-analysis-present", "incumbent-search", "line:affordability", "line:procurement-thresholds",
    "line:comparable-awards", "line:cost-to-deliver", "confidence-stated", "rfp-wants-extracted",
    "candidate-configs", "selected-config", "competitiveness-assessed", "cites-upstream",
    "value-written-back", "value-consistency", "recommendation-consistency", "status-consistency",
})


def _review_kind(check):
    """'needs-research' when the gap is retrievable/re-runnable (the harness can close it on the next
    pass); 'human-decision' otherwise (scope, teaming, locality/regulated-data, signatures, margin —
    a judgment only the operator can settle)."""
    return "needs-research" if check in _NEEDS_RESEARCH_CHECKS else "human-decision"


def _deepen(worker, opp_dir, out_root, ctx, cfg):
    """DEEPEN LOOP (P2c): while a stage is LOW for a RETRIEVABLE reason, give the agent one focused
    follow-up to retrieve-and-re-evaluate THAT stage, rather than surfacing it to the human. Bounded
    by cfg['deepen_max'] (default 1). Returns the number of deepen passes actually run.

    A pass runs only if there is at least one needs-research LOW stage AND the pass count is under
    the cap; it stops early when a pass clears all needs-research LOW stages or makes no progress."""
    cap = int(cfg.get("deepen_max", 1))
    passes = 0
    while passes < cap:
        _, review = _grade_all_stages(ctx)
        gaps = [it for it in review if it.get("kind") == "needs-research" and it.get("confidence") == LOW]
        if not gaps:
            break
        lines = [f"- stage '{g['stage']}': {g['reason']} → {g['remedy']}" for g in gaps]
        extra = ("Some stages are still LOW confidence because of RETRIEVABLE gaps. Retrieve the "
                 "named documents/facts (portal/web fetch into rfp/) and RE-EVALUATE just these "
                 "stages, then rewrite their artifacts. Do not hand these back as human decisions:\n"
                 + "\n".join(lines))
        wres = worker.run(opp_dir, out_root, extra=extra)
        passes += 1
        if not wres.get("ran"):
            break
        new_ctx = EvalContext(opp_dir)
        _, new_review = _grade_all_stages(new_ctx)
        new_gaps = [it for it in new_review if it.get("kind") == "needs-research" and it.get("confidence") == LOW]
        ctx = new_ctx
        if len(new_gaps) >= len(gaps):   # no progress — stop re-dispatching
            break
    return passes


# --------------------------------------------------------------------------- orchestrate
def orchestrate(cfg, opps_dir=None, dry_run=False, do_ingest=None):
    _load_gates()
    opps_dir = opps_dir or cfg["opportunities_dir"]
    worker = make_worker(cfg)

    mode_note = f"autonomy={cfg['autonomy']} worker={worker.name}"
    # degrade-to-a when a b/c worker has no runner available
    if cfg["autonomy"] in ("b", "c") and not worker.available():
        mode_note = (f"autonomy={cfg['autonomy']} requested but no agent runner available "
                     f"→ DEGRADED to notify-only")
        worker = NullAgentWorker()

    report = RunReport(autonomy=cfg["autonomy"], mode_note=mode_note)
    state = _load_state(cfg["state"])
    hashes = state.get("hashes", {})

    for name in sorted(os.listdir(opps_dir)):
        p = os.path.join(opps_dir, name)
        if not os.path.isdir(p) or name.startswith(".") or name in portfolio.SKIP_DIRS:
            continue
        if not os.path.exists(os.path.join(p, "opportunity.json")):
            continue

        r = OppResult(opportunity=name)
        try:
            ctx = EvalContext(p)
            h = content_hash(p)
            unchanged = hashes.get(name) == h and not dry_run

            # The idempotency hash alone is not enough to skip prep: an opportunity can be "unchanged"
            # yet never have been prepped (the backlog filed before prep existed, or hashed in an
            # earlier run). So prep runs when the inputs changed OR when there is still deterministic
            # work outstanding — right now that means an unconfirmed-but-document-confirmable due date.
            # Prep is idempotent and self-stabilising: once the date is confirmed, needs_prep is false
            # and the opp is genuinely skipped.
            prep_cfg = dict(cfg.get("prep") or {})
            # RETRIEVAL-FIRST (P2a): in an agent mode (b/c) the agent is expected to work from the
            # posted documents, so pull them into rfp/ during prep unless the operator explicitly
            # opted out. In notify-only (mode a) portal_fetch stays off by default (it touches live
            # portals). This only sets a default; an explicit prep.portal_fetch in config always wins.
            if "portal_fetch" not in prep_cfg and cfg.get("autonomy") in ("b", "c"):
                prep_cfg["portal_fetch"] = True
            needs_prep = prep_cfg.get("enabled", True) and (not unchanged or _needs_prep(ctx))
            if needs_prep:
                r.prep_notes = prep_opportunity(p, prep_cfg, portals_path=cfg.get("portals"),
                                                capability_path=cfg.get("capability"))
                ctx = EvalContext(p)   # re-open: prep may have changed opportunity.json

            # Decide whether to run the AGENT writer. A real (available) writer runs when the INPUTS
            # changed since the last agent pass (content_hash now excludes agent-written fields, so a
            # committed verdict does NOT churn the hash) OR when the opp has never been
            # agent-researched. A researched opp with unchanged inputs is NOT re-litigated (P1c).
            # A Null worker (mode a) does no writing, so it never forces a "run".
            run_agent, agent_reason = _should_run_agent(ctx, unchanged)
            r.expired = _is_expired(ctx)
            if run_agent and worker.name != "null":
                out_root = p if cfg["autonomy"] != "b" else os.path.join(p, cfg["quarantine_dir"])
                wres = worker.run(p, out_root)
                r.worked = bool(wres.get("ran"))
                if r.worked:
                    ctx = EvalContext(p)          # re-open: the agent wrote canonical docs
                    # DEEPEN LOOP (P2c): if a stage is still LOW because of a RETRIEVABLE gap, give
                    # the agent one focused follow-up to retrieve-and-re-evaluate that stage rather
                    # than leaving it for the human. Bounded to the configured number of passes.
                    r.deepen_passes = _deepen(worker, p, out_root, ctx, cfg)
                    if r.deepen_passes:
                        ctx = EvalContext(p)
                    _stamp_decision(p, h)         # record decided_at + inputs_digest
            elif r.expired:
                r.skipped_reason = agent_reason   # "deadline passed; not researching" (P4a)
            elif unchanged and not needs_prep:
                r.skipped_reason = "unchanged since last run"

            # always evaluate (the gates are read-only) and record where the pipeline stands
            row = portfolio.build_row(p, run_gates=True)
            r.stage_reached = row.get("pipeline_at", "")
            r.recommendation = row.get("recommendation", "")
            r.open_items = _open_items(ctx)
            # Grade every stage: the pipeline never halts, so each stage has a confidence and the
            # ones below HIGH become review/override items (best estimate + how to raise it).
            r.stage_confidence, r.review_items = _grade_all_stages(ctx)
            r.overall_confidence = r.stage_confidence.get("go-no-go", "")
            r.gates_failed = sum(1 for lvl in r.stage_confidence.values() if lvl == LOW)
            # record the hash AFTER prep (prep may have rewritten opportunity.json), so an opp that
            # prep leaves in a steady state is genuinely skipped next run rather than re-prepped forever
            hashes[name] = content_hash(p)
        except Exception as e:  # noqa: BLE001 — one bad opportunity must not abort the run
            r.error = str(e)
        report.results.append(r)

    # counts for the digest
    rows = portfolio.build_portfolio(opps_dir, run_gates=False)
    report.counts = portfolio.counts(rows, cfg["queue"], cfg["state"])

    if not dry_run:
        state["hashes"] = hashes
        _save_state(cfg["state"], state)
    return report


def reconcile_state(cfg, opps_dir=None):
    """One-time reconcile so an ALREADY-researched backlog is not re-litigated after the content_hash
    definition changed (P1c). For every opportunity that already carries a committed verdict, stamp
    its current INPUT hash into both opportunity.json (inputs_digest, if absent) and the state's
    hashes map. After this, _should_run_agent sees 'researched + inputs unchanged' and skips it; only
    genuinely new/changed opportunities run the agent on the next pass. Returns the count stamped."""
    _load_gates()
    opps_dir = opps_dir or cfg["opportunities_dir"]
    state = _load_state(cfg["state"])
    hashes = state.get("hashes", {})
    stamped = 0
    for name in sorted(os.listdir(opps_dir)):
        p = os.path.join(opps_dir, name)
        if not os.path.isdir(p) or name.startswith(".") or name in portfolio.SKIP_DIRS:
            continue
        if not os.path.exists(os.path.join(p, "opportunity.json")):
            continue
        try:
            ctx = EvalContext(p)
        except Exception:  # noqa: BLE001
            continue
        if not _has_committed_verdict(ctx):
            continue
        h = content_hash(p)
        hashes[name] = h
        opp = ctx.opportunity() or {}
        if not opp.get("inputs_digest"):
            _stamp_decision(p, h)
        stamped += 1
    state["hashes"] = hashes
    _save_state(cfg["state"], state)
    return stamped


# --------------------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the daily evaluation pass")
    r.add_argument("--cfg", default=None)
    r.add_argument("--opps", default=None)
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--json", action="store_true")
    rc = sub.add_parser("reconcile-state",
                        help="one-time: mark already-researched opportunities as done so a rerun "
                             "does not re-litigate them (after the content_hash change)")
    rc.add_argument("--cfg", default=None)
    rc.add_argument("--opps", default=None)
    a = ap.parse_args(argv)

    try:
        cfg = load_config(a.cfg)
    except HarnessError as e:
        print(f"HARNESS ERROR: {e}"); return 2

    if a.cmd == "reconcile-state":
        n = reconcile_state(cfg, opps_dir=a.opps)
        print(f"[harness] reconciled {n} already-researched opportunity(ies) — a rerun will skip them")
        return 0

    report = orchestrate(cfg, opps_dir=a.opps, dry_run=a.dry_run)

    if a.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f"[harness] {report.mode_note}")
        c = report.counts
        print(f"[harness] added={len(c.get('added', []))} updated={len(c.get('updated', []))} "
              f"passed-go-no-go={len(c.get('passed', []))}")
        for res in report.results:
            tag = res.skipped_reason or (f"pipeline@{res.stage_reached}" + (f" ({res.gates_failed}✗)" if res.gates_failed else ""))
            print(f"  {res.opportunity}: {tag}" + (f"  ERROR: {res.error}" if res.error else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
