"""Tests for the headless agent runner (bidkit.harness.CliAgentWorker) and its mode b/c wiring.

Fully OFFLINE: no real agent CLI is invoked. A FAKE runner — a tiny python script written to tmp —
stands in for `kiro-cli`; it writes a known artifact into its cwd and echoes a summary, so the
tests prove the worker shells out with cwd=out_root, parses success/failure, and that the
orchestrator routes mode c to the opp dir and mode b to the quarantine subdir."""
import json, os, stat, sys
import pytest
from bidkit import harness


def _opp(root, name, opportunity):
    d = root / name
    (d / "rfp").mkdir(parents=True)
    (d / "opportunity.json").write_text(json.dumps(opportunity), encoding="utf-8")
    (d / "rfp" / "main.pdf").write_text("x", encoding="utf-8")
    return d


def _cfg(tmp_path, **over):
    cfg = dict(harness.DEFAULTS)
    cfg["opportunities_dir"] = str(tmp_path / "opps")
    cfg["state"] = str(tmp_path / "state.json")
    cfg["queue"] = str(tmp_path / "queue.jsonl")
    cfg["prep"] = {"enabled": False}          # isolate the worker from the deterministic prep pass
    cfg.update(over)
    return cfg


def _fake_runner(tmp_path, body):
    """Write a fake agent-runner script that runs `body` (python) in its cwd, and return a command
    prefix string that invokes it. The harness appends the prompt as a final argv item (ignored)."""
    p = tmp_path / "fake_runner.py"
    p.write_text("import os, sys\n" + body + "\n", encoding="utf-8")
    return f"{sys.executable} {p}"


# --------------------------------------------------------------------------- unit: CliAgentWorker
def test_runner_writes_into_cwd_and_reports_ran(tmp_path):
    opp = _opp(tmp_path / "opps", "a", {"id": "a"})
    cli = _fake_runner(tmp_path, "open('AGENT_WAS_HERE.txt','w').write('ok'); print('verdict: BID')")
    w = harness.CliAgentWorker(cli)
    res = w.run(str(opp), str(opp))
    assert res["ran"] is True
    assert "BID" in res.get("summary", "")
    assert (opp / "AGENT_WAS_HERE.txt").exists()        # proves cwd == out_root


def test_runner_nonzero_exit_degrades(tmp_path):
    opp = _opp(tmp_path / "opps", "a", {"id": "a"})
    cli = _fake_runner(tmp_path, "sys.exit(3)")
    res = harness.CliAgentWorker(cli).run(str(opp), str(opp))
    assert res["ran"] is False and "exited 3" in res["note"]


def test_runner_timeout_degrades(tmp_path):
    opp = _opp(tmp_path / "opps", "a", {"id": "a"})
    cli = _fake_runner(tmp_path, "import time; time.sleep(5)")
    res = harness.CliAgentWorker(cli, timeout_sec=1).run(str(opp), str(opp))
    assert res["ran"] is False and "timed out" in res["note"]


def test_runner_not_found_degrades(tmp_path):
    opp = _opp(tmp_path / "opps", "a", {"id": "a"})
    res = harness.CliAgentWorker("definitely-not-a-real-command-xyz").run(str(opp), str(opp))
    assert res["ran"] is False and "not found" in res["note"]


def test_unavailable_when_no_cli():
    assert harness.CliAgentWorker(None).available() is False
    assert harness.CliAgentWorker("kiro-cli chat").available() is True


def test_out_root_created_if_missing(tmp_path):
    opp = _opp(tmp_path / "opps", "a", {"id": "a"})
    out = str(opp / "proposed")                         # does not exist yet
    cli = _fake_runner(tmp_path, "open('x.txt','w').write('ok')")
    harness.CliAgentWorker(cli).run(str(opp), out)
    assert os.path.isfile(os.path.join(out, "x.txt"))   # run() made out_root


# --------------------------------------------------------------------------- orchestration routing
def test_mode_c_runs_agent_in_opp_dir(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    d = _opp(opps, "a", {"id": "a"})
    cli = _fake_runner(tmp_path, "open('C_ARTIFACT.txt','w').write('ok')")
    cfg = _cfg(tmp_path, autonomy="c", agent_cli=cli)
    report = harness.orchestrate(cfg)
    r = next(r for r in report.results if r.opportunity == "a")
    assert r.worked is True
    assert (d / "C_ARTIFACT.txt").exists()              # mode c → canonical opp dir
    assert "worker=cli" in report.mode_note


def test_mode_b_runs_agent_in_quarantine(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    d = _opp(opps, "a", {"id": "a"})
    cli = _fake_runner(tmp_path, "open('B_ARTIFACT.txt','w').write('ok')")
    cfg = _cfg(tmp_path, autonomy="b", agent_cli=cli, quarantine_dir="proposed")
    harness.orchestrate(cfg)
    assert (d / "proposed" / "B_ARTIFACT.txt").exists()  # mode b → quarantine subdir
    assert not (d / "B_ARTIFACT.txt").exists()           # canonical dir untouched


def test_mode_c_without_runner_degrades_to_a(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a"})
    cfg = _cfg(tmp_path, autonomy="c", agent_cli=None)
    report = harness.orchestrate(cfg)
    assert "DEGRADED to notify-only" in report.mode_note


# --------------------------------------------------------------------------- no re-litigation (P1c)
def test_agent_not_re_run_when_inputs_unchanged(tmp_path):
    # A fake runner that commits a verdict (status/recommendation). After it researches once, a
    # second run with unchanged INPUTS must NOT re-run the agent (no re-litigation).
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a"})
    body = ("import json\n"
            "d=json.load(open('opportunity.json')); d['status']='pass'; d['recommendation']='PASS — out of scope'\n"
            "json.dump(d, open('opportunity.json','w'))\n"
            "print('verdict: PASS')\n")
    cli = _fake_runner(tmp_path, body)
    cfg = _cfg(tmp_path, autonomy="c", agent_cli=cli)
    r1 = harness.orchestrate(cfg).results[0]
    assert r1.worked is True                         # researched on the first pass
    r2 = harness.orchestrate(cfg).results[0]
    assert r2.worked is False                        # NOT re-litigated
    assert r2.skipped_reason == "unchanged since last run"


def test_agent_reruns_when_input_changes(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    d = _opp(opps, "a", {"id": "a"})
    body = ("import json\n"
            "x=json.load(open('opportunity.json')); x['status']='pass'; x['recommendation']='PASS'\n"
            "json.dump(x, open('opportunity.json','w'))\n")
    cfg = _cfg(tmp_path, autonomy="c", agent_cli=_fake_runner(tmp_path, body))
    assert harness.orchestrate(cfg).results[0].worked is True
    # change a real INPUT (add an rfp doc) → the agent should run again
    (d / "rfp" / "addendum1.pdf").write_text("new addendum", encoding="utf-8")
    assert harness.orchestrate(cfg).results[0].worked is True


# --------------------------------------------------------------------------- deepen loop (P2c)
def test_deepen_redispatches_on_retrievable_gap(tmp_path):
    # First agent pass leaves the due date an unconfirmed DETECTED guess (a needs-research LOW gap);
    # the FOCUSED follow-up (the deepen loop) confirms it. We prove a 2nd invocation happened and
    # the gap closed. The fake runner counts its calls via a sidecar file and confirms due on call 2.
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a", "due": {"date": "2026-12-01", "confirmed": False, "source": "guess"},
                     "format": {"page_limit": 20}})
    body = (
        "import json, os\n"
        "n = 0\n"
        "if os.path.exists('.calls'): n = int(open('.calls').read())\n"
        "n += 1; open('.calls','w').write(str(n))\n"
        "d = json.load(open('opportunity.json'))\n"
        "d['status'] = 'pass'; d['recommendation'] = 'PASS'\n"
        "if n >= 2:\n"
        "    d['due'] = {'date': '2026-12-01', 'confirmed': True, 'source': 'RFP cover page p.1'}\n"
        "json.dump(d, open('opportunity.json','w'))\n"
        "print('verdict: PASS')\n")
    cli = _fake_runner(tmp_path, body)
    cfg = _cfg(tmp_path, autonomy="c", agent_cli=cli, deepen_max=1)
    r = harness.orchestrate(cfg).results[0]
    assert r.deepen_passes == 1                                   # one focused re-dispatch happened
    assert int((opps / "a" / ".calls").read_text()) == 2         # agent invoked twice total
    oj = json.load(open(opps / "a" / "opportunity.json"))
    assert oj["due"]["confirmed"] is True                        # the retrievable gap was closed


def test_deepen_disabled_when_cap_zero(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a", "due": {"date": "2026-12-01", "confirmed": False, "source": "guess"}})
    body = ("import json\n"
            "d=json.load(open('opportunity.json')); d['status']='pass'; d['recommendation']='PASS'\n"
            "json.dump(d, open('opportunity.json','w'))\n")
    cfg = _cfg(tmp_path, autonomy="c", agent_cli=_fake_runner(tmp_path, body), deepen_max=0)
    r = harness.orchestrate(cfg).results[0]
    assert r.deepen_passes == 0                                   # deepen off → no re-dispatch


# --------------------------------------------------------------------------- P3a: completeness retry
def test_deepen_fixes_a_thin_fit_stage(tmp_path):
    # P3a: a COMPLETENESS gap (fit written without a concrete selection) is a needs-research LOW
    # stage, so the deepen loop re-dispatches and the focused pass writes a real selection. Proves
    # the retry closes incompleteness, not just missing documents.
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a", "due": {"date": "2026-12-01", "confirmed": True, "source": "RFP p.1"},
                     "format": {"page_limit": 20},
                     "value_estimate": {"anchor": 500000, "anchor_source": "https://x", "confidence": "HIGH"}})
    body = (
        "import json, os\n"
        "n = 0\n"
        "if os.path.exists('.calls'): n = int(open('.calls').read())\n"
        "n += 1; open('.calls','w').write(str(n))\n"
        "os.makedirs('research', exist_ok=True)\n"
        "d = json.load(open('opportunity.json')); d['status']='bid'; d['recommendation']='BID'\n"
        "json.dump(d, open('opportunity.json','w'))\n"
        "open('research/go-no-go.md','w').write('# Go/no-go\\nDECISION: BID — value, pricing, fit all support it.\\n')\n"
        "open('research/pricing.md','w').write('# Pricing\\nlabor hours; staff x schedule capacity; mandated schedule; recurring $90k/yr incl margin + infra; corridor reconciled.\\n')\n"
        "if n < 2:\n"
        "    open('research/fit-synthesis.md','w').write('# Fit\\n## What the RFP wants\\nscoring weights.\\n## Candidate configurations\\n- Option A\\n- Option B\\n## Selection\\nProduce a selected best-fit with reasoning, and a competitiveness read.\\n')\n"
        "else:\n"
        "    open('research/fit-synthesis.md','w').write('# Fit\\n## What the RFP wants\\nscoring weights; winnability.\\n## Candidate configurations\\n- Option A: solo\\n- Option B: teaming\\n## Selection\\nSelected best-fit: Configuration B (prime + teaming) because it closes the reference gap; competitiveness is a credible underdog.\\n')\n"
        "print('verdict: BID')\n")
    cfg = _cfg(tmp_path, autonomy="c", agent_cli=_fake_runner(tmp_path, body), deepen_max=1)
    r = harness.orchestrate(cfg).results[0]
    assert r.deepen_passes == 1
    assert r.stage_confidence.get("fit") != "LOW"      # the thin-fit stage was repaired on retry


# --------------------------------------------------------------------------- past-due skip (P4a)
def test_agent_skipped_on_expired_confirmed_due(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a", "due": {"date": "2020-01-01", "confirmed": True, "source": "RFP p.1"}})
    body = "import json\nd=json.load(open('opportunity.json')); d['status']='bid'; json.dump(d,open('opportunity.json','w'))\n"
    cfg = _cfg(tmp_path, autonomy="c", agent_cli=_fake_runner(tmp_path, body))
    r = harness.orchestrate(cfg).results[0]
    assert r.worked is False and r.expired is True
    assert "deadline passed" in r.skipped_reason


def test_agent_runs_on_expired_when_chasing_reissue(tmp_path):
    opps = tmp_path / "opps"; opps.mkdir()
    _opp(opps, "a", {"id": "a", "chase_reissue": True,
                     "due": {"date": "2020-01-01", "confirmed": True, "source": "RFP p.1"}})
    body = "import json\nd=json.load(open('opportunity.json')); d['status']='bid'; json.dump(d,open('opportunity.json','w'))\n"
    cfg = _cfg(tmp_path, autonomy="c", agent_cli=_fake_runner(tmp_path, body))
    r = harness.orchestrate(cfg).results[0]
    assert r.expired is False and r.worked is True          # chase_reissue overrides the past-due skip
