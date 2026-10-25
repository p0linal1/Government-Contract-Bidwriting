#!/usr/bin/env python3
"""
digest.py — compose and send the daily bid-sourcing digest email (the north-star deliverable).

Why: the whole harness exists to produce one trustworthy daily email to the principal —
"Here is the summary of <org>'s Bid Sourcing activity: X opportunities added, Y updated,
Z passed go/no-go, and drafts for each of them are attached." (The org name is config, not code.)

The pipeline never halts: every stage of every opportunity produces a best-effort output carrying a
HIGH/MEDIUM/LOW confidence (bidkit/evaluation.py). So this digest is an INFORMATION report, not a
blocked-work report. It turns a RunReport + the portfolio view into that message: the X/Y/Z lead
line (each count substantiated by the portfolio, never asserted); an Added / Updated listing that
always carries each opp's estimated value, confidence and overall confidence (never a blank cell);
a "Passed go/no-go" table (verdict + confidence + rationale + value + draft); a "Needs your
decision" section (the OPEN human-decision items surfaced in the summary); and a "Review / override"
section — every stage output currently below HIGH confidence, shown as the current best estimate
plus how to raise its confidence. It is a review list, never a "stuck / blocked" list: the hard rule
is that an estimate is always presented with its confidence, never as a settled fact.
The go/no-go passers' drafts are attached (or linked when over the size cap).

It builds a standard RFC-822 message and hands the bytes to the EXISTING send path
(mail_gmail.send_raw) — it adds no new credential surface. The recipient and backend come from
config, never code (gate: tests/test_no_hardcoding.py). If the backend is unavailable the composed
digest is written to the log dir and a non-zero exit is returned, so the summary is never lost.

CLI:
  python3 -m bidkit.digest run --cfg inbox/harness.json [--opps <dir>] [--dry-run] [--out FILE]
    --dry-run / --out: compose and print/save, do NOT send.
"""
import argparse, json, os, re, sys, datetime as dt
from email.message import EmailMessage

from . import portfolio, harness


def _fmt_money(v):
    try:
        return f"${int(v):,}" if v else ""
    except (TypeError, ValueError):
        return ""


def _passer_rows(rows, passed_ids):
    by_id = {r["opportunity"]: r for r in rows}
    return [by_id[i] for i in passed_ids if i in by_id]


def _rationale(opps_dir, opp_id):
    """One-line go/no-go rationale: the clause after 'DECISION:' / 'Recommendation:' in go-no-go.md
    (or the summary). Returns '' if none found."""
    for rel in (("research", "go-no-go.md"), ("opportunity-summary.md",)):
        p = os.path.join(opps_dir, opp_id, *rel)
        if not os.path.exists(p):
            continue
        text = open(p, encoding="utf-8").read()
        m = re.search(r"(?im)\b(?:decision|recommendation)\b\s*:?\s*\*{0,2}[A-Za-z /-]+\*{0,2}\s*[—:-]\s*(.+)", text)
        if m:
            s = re.sub(r"\*\*(.+?)\*\*", r"\1", m.group(1)).replace("**", "").strip()
            s = re.sub(r"\s+", " ", s)
            if s:
                return s[:200]
    return ""


def _value(opp_json):
    """Return (display, source_url, basis, confidence) for an opportunity's value estimate. display
    leads with the anchor when present, else the likely figure. confidence is the value-research
    stage's own confidence token (HIGH/MEDIUM/LOW) when recorded, so the digest can badge the figure
    rather than presenting it as a settled fact. An opp with no figure yet still returns a
    confidence (LOW) so the reader sees the stage ran but has nothing firm."""
    ve = (opp_json or {}).get("value_estimate") or {}
    anchor = ve.get("anchor")
    likely = ve.get("likely")
    conf = (ve.get("confidence") or "").upper()
    if anchor:
        disp = f"{_fmt_money(anchor)} (anchor)"
        return disp, ve.get("anchor_source") or ve.get("source") or "", ve.get("anchor_basis") or ve.get("basis") or "", conf
    if likely:
        disp = f"{_fmt_money(likely)} (likely)"
        return disp, ve.get("source") or "", ve.get("basis") or "", conf
    return "", "", "", conf


def _find_draft(opp_dir):
    """Return the path to a submittable draft for a passer, if one exists (final/ then SUBMIT)."""
    for rel in ("deliverables/bid/final", "SUBMIT", "proposed"):
        d = os.path.join(opp_dir, rel)
        if os.path.isdir(d):
            for name in sorted(os.listdir(d)):
                if name.startswith("."):
                    continue
                p = os.path.join(d, name)
                if os.path.isfile(p) and name.lower().endswith((".pdf", ".docx", ".xlsx")):
                    return p
    return None


def _esc(s):
    """Minimal HTML escaping for cell text."""
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# inline styles only — Gmail strips <style> blocks and class attributes
_TD = 'style="border:1px solid #ddd;padding:6px 10px;vertical-align:top;font-size:13px;"'
_TH = 'style="border:1px solid #ddd;padding:6px 10px;text-align:left;background:#f3f4f6;font-size:12px;color:#374151;"'
_TABLE = 'style="border-collapse:collapse;width:100%;max-width:720px;margin:4px 0 18px;font-family:Arial,Helvetica,sans-serif;"'
_H2 = 'style="font-family:Arial,Helvetica,sans-serif;font-size:15px;margin:18px 0 4px;color:#111;"'


def _html_table(headers, rows_html):
    if not rows_html:
        return '<p style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#6b7280;margin:2px 0 14px;">(none)</p>'
    head = "".join(f"<th {_TH}>{_esc(h)}</th>" for h in headers)
    return (f'<table {_TABLE}><thead><tr>{head}</tr></thead><tbody>'
            + "".join(rows_html) + "</tbody></table>")


# confidence badge — colour-coded so the reader sees at a glance how firm each figure is
_CONF_COLOR = {"HIGH": "#047857", "MEDIUM": "#b45309", "LOW": "#b91c1c"}


def _conf_badge(level):
    if not level:
        return ""
    c = _CONF_COLOR.get(level, "#6b7280")
    return (f'<span style="display:inline-block;padding:1px 6px;border-radius:3px;'
            f'font-size:11px;font-weight:bold;color:#fff;background:{c};">{_esc(level)}</span>')


def _render_html(lead, when, mode_note, added, updated, passers, decisions, review, research_queue, errs):
    def cell(x):
        return f"<td {_TD}>{x}</td>"   # x already escaped/marked up by caller

    def _val_cell(d):
        val = _esc(d["value"]) or '<span style="color:#9ca3af;">no figure yet</span>'
        if d.get("value_src"):
            val += f' <a href="{_esc(d["value_src"])}" style="color:#2563eb;">[source]</a>'
        if d.get("value_conf"):
            val += " " + _conf_badge(d["value_conf"])
        return val

    parts = [
        '<div style="font-family:Arial,Helvetica,sans-serif;color:#111;">',
        f'<p style="font-size:15px;font-weight:bold;margin:0 0 2px;">{_esc(lead)}</p>',
        f'<p style="font-size:12px;color:#6b7280;margin:0 0 14px;">Run: {_esc(when)} &nbsp;({_esc(mode_note)})</p>',
        '<p style="font-size:12px;color:#6b7280;margin:0 0 14px;">Every figure below is a best-effort '
        'estimate carrying its own confidence (HIGH / MEDIUM / LOW), not a settled fact. '
        '"Review / override" lists the judgment calls for you; the "Auto-research queue" lists gaps '
        'the harness will chase itself on the next run.</p>',
    ]

    # Passed go/no-go — split LIVE vs EXPIRED (P4a): a bid whose confirmed deadline has passed is
    # not actionable; keep it out of the live list so it doesn't read as pursuable.
    live_passers = [d for d in passers if not d.get("expired")]
    expired_passers = [d for d in passers if d.get("expired")]

    def _passer_row(d):
        verdict = f'<b>{_esc(d["verdict"].upper())}</b>'
        if d.get("verdict_conf"):
            verdict += " " + _conf_badge(d["verdict_conf"])
        rat = _esc(d["rationale"])
        draft = "✓" if d["draft"] else "—"
        return ("<tr>" + cell(f'<b>{_esc(d["opp"])}</b>')
                + cell(verdict + (f'<br><span style="color:#4b5563;">{rat}</span>' if rat else ""))
                + cell(_val_cell(d)) + cell(_esc(d["due"])) + cell(draft) + "</tr>")

    parts.append(f'<h2 {_H2}>Passed go/no-go — live ({len(live_passers)})</h2>')
    parts.append(_html_table(["Opportunity", "Verdict & confidence", "Est. value (source · confidence)", "Due", "Draft"],
                             [_passer_row(d) for d in live_passers]))
    if expired_passers:
        parts.append(f'<h2 {_H2}>Passed go/no-go — EXPIRED, deadline passed ({len(expired_passers)})</h2>')
        parts.append(_html_table(["Opportunity", "Verdict & confidence", "Est. value (source · confidence)", "Due", "Draft"],
                                 [_passer_row(d) for d in expired_passers]))

    # Needs your decision
    parts.append(f'<h2 {_H2}>Needs your decision ({len(decisions)})</h2>')
    drows = ["<tr>" + cell(f'<b>{_esc(d["opp"])}</b>') + cell(_esc(d["ask"])) + "</tr>" for d in decisions]
    parts.append(_html_table(["Opportunity", "Decision ask"], drows))

    # Review / override — HUMAN-DECISION gaps: a judgment only the operator can settle.
    parts.append(f'<h2 {_H2}>Review / override — your judgment ({len(review)})</h2>')
    rrows = ["<tr>" + cell(f'<b>{_esc(a["opp"])}</b>') + cell(_esc(a["stage"])) + cell(_conf_badge(a["confidence"]))
             + cell(_esc(a["reason"])) + cell(f'<span style="color:#047857;">{_esc(a["remedy"])}</span>') + "</tr>"
             for a in review]
    parts.append(_html_table(["Opportunity", "Stage", "Confidence", "Current best estimate rests on", "How to raise confidence"], rrows))

    # Auto-research queue — NEEDS-RESEARCH gaps the HARNESS resolves on the next run (not your task).
    parts.append(f'<h2 {_H2}>Auto-research queue — the harness will chase these ({len(research_queue)})</h2>')
    qrows = ["<tr>" + cell(f'<b>{_esc(a["opp"])}</b>') + cell(_esc(a["stage"])) + cell(_conf_badge(a["confidence"]))
             + cell(_esc(a["reason"])) + cell(f'<span style="color:#6b7280;">{_esc(a["remedy"])}</span>') + "</tr>"
             for a in research_queue]
    parts.append(_html_table(["Opportunity", "Stage", "Confidence", "Gap", "Auto-resolve action"], qrows))

    # Added / Updated — always carry value(+conf) and overall confidence (never a blank row)
    for title, data in (("Added", added), ("Updated", updated)):
        parts.append(f'<h2 {_H2}>{title} ({len(data)})</h2>')
        rws = ["<tr>" + cell(f'<b>{_esc(d["opp"])}</b>') + cell(_esc(d["rec"])) + cell(_val_cell(d))
               + cell(_esc(d["due"])) + cell(_conf_badge(d.get("overall_conf"))) + "</tr>" for d in data]
        parts.append(_html_table(["Opportunity", "Rec", "Est. value (source · confidence)", "Due", "Overall confidence"], rws))

    if errs:
        parts.append(f'<h2 {_H2}>Errors ({len(errs)})</h2>')
        erows = ["<tr>" + cell(f'<b>{_esc(e["opp"])}</b>') + cell(_esc(e["error"])) + "</tr>" for e in errs]
        parts.append(_html_table(["Opportunity", "Error"], erows))

    parts.append("</div>")
    return "\n".join(parts)


def _val_text(d):
    """value (source · confidence) rendered for plaintext."""
    v = d.get("value") or "no figure yet"
    if d.get("value_src"):
        v += f" [source: {d['value_src']}]"
    if d.get("value_conf"):
        v += f" ({d['value_conf']})"
    return v


def _render_text(lead, when, mode_note, added, updated, passers, decisions, review, research_queue, errs):
    """Plaintext fallback — same information, pipe-delimited so it stays readable without HTML.
    Every figure carries its confidence; nothing is presented as a settled fact."""
    L = [lead, "",
         f"Run: {when}  ({mode_note})",
         "Every figure is a best-effort estimate with its own confidence (HIGH/MEDIUM/LOW), "
         "not a settled fact. 'Review / override' lists the judgment calls for you; the "
         "'Auto-research queue' lists gaps the harness will chase itself on the next run.", ""]
    live_passers = [d for d in passers if not d.get("expired")]
    expired_passers = [d for d in passers if d.get("expired")]

    def _passer_lines(d):
        vc = f" [{d['verdict_conf']}]" if d.get("verdict_conf") else ""
        out = [f"  - {d['opp']} — {d['verdict'].upper()}{vc}"
               + (f": {d['rationale']}" if d["rationale"] else "")]
        out.append(f"      value: {_val_text(d)}  |  due: {d['due'] or '?'}  |  draft: {'yes' if d['draft'] else 'no'}")
        return out

    L.append(f"## Passed go/no-go — live ({len(live_passers)})")
    if not live_passers:
        L.append("  (none)")
    for d in live_passers:
        L.extend(_passer_lines(d))
    L.append("")
    if expired_passers:
        L.append(f"## Passed go/no-go — EXPIRED, deadline passed ({len(expired_passers)})")
        for d in expired_passers:
            L.extend(_passer_lines(d))
        L.append("")
    L.append(f"## Needs your decision ({len(decisions)})")
    if not decisions:
        L.append("  (none)")
    for d in decisions:
        L.append(f"  - [{d['opp']}] {d['ask']}")
    L.append("")
    L.append(f"## Review / override — your judgment ({len(review)})")
    if not review:
        L.append("  (none)")
    for a in review:
        L.append(f"  - {a['opp']}: {a['stage']} [{a['confidence']}] — {a['reason']}")
        if a["remedy"]:
            L.append(f"      to raise confidence: {a['remedy']}")
    L.append("")
    L.append(f"## Auto-research queue — the harness will chase these ({len(research_queue)})")
    if not research_queue:
        L.append("  (none)")
    for a in research_queue:
        L.append(f"  - {a['opp']}: {a['stage']} [{a['confidence']}] — {a['reason']}")
        if a["remedy"]:
            L.append(f"      auto-resolve: {a['remedy']}")
    L.append("")
    for title, data in (("Added", added), ("Updated", updated)):
        L.append(f"## {title} ({len(data)})")
        if not data:
            L.append("  (none)")
        for d in data:
            oc = f" [overall {d['overall_conf']}]" if d.get("overall_conf") else ""
            extra = " | ".join(x for x in (d["rec"], _val_text(d), f"due {d['due']}" if d["due"] else "") if x)
            L.append(f"  - {d['opp']}{oc}" + (f" — {extra}" if extra else ""))
        L.append("")
    if errs:
        L.append(f"## Errors ({len(errs)})")
        for e in errs:
            L.append(f"  - {e['opp']}: {e['error']}")
        L.append("")
    return "\n".join(L)


def compose(report, rows, cfg, opps_dir, when=None):
    """Build the digest EmailMessage from a RunReport + portfolio rows. Pure: no network."""
    dcfg = cfg.get("digest", {}) or {}
    when = when or dt.date.today().isoformat()
    c = report.counts or {}
    added, updated, passed = c.get("added", []), c.get("updated", []), c.get("passed", [])

    # The company name / lead wording is CONFIG, never baked into the library.
    org = dcfg.get("org_name", "")
    possessive = f"{org}'s " if org else ""
    lead = (f"Here is the summary of {possessive}Bid Sourcing activity: "
            f"{len(added)} opportunities added, {len(updated)} updated, "
            f"{len(passed)} passed go/no-go.")

    by_id = {r["opportunity"]: r for r in rows}

    def _opp_json(opp_id):
        p = os.path.join(opps_dir, opp_id, "opportunity.json")
        if os.path.exists(p):
            try:
                raw = json.load(open(p, encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
            # normalize defensively (P0): an agent-written dict recommendation / prose anchor must
            # not reach the renderers as-is.
            from . import opportunity_lint
            norm, _ = opportunity_lint.normalize_opportunity(raw)
            return norm
        return {}

    # per-opportunity confidence from the RunReport (the harness graded every stage this run)
    res_by_id = {res.opportunity: res for res in report.results}

    def _overall_conf(opp_id):
        res = res_by_id.get(opp_id)
        return (res.overall_confidence if res else "") or ""

    def _verdict_conf(opp_id):
        res = res_by_id.get(opp_id)
        return (res.stage_confidence.get("go-no-go", "") if res else "") or ""

    def _expired(opp_id):
        """True when a CONFIRMED due date is in the past (P4a). An unconfirmed/DETECTED due is not
        trusted enough to call expired."""
        r = by_id.get(opp_id, {})
        dr = r.get("days_remaining")
        return bool(r.get("due_confirmed")) and isinstance(dr, int) and dr < 0

    # ---- assemble the per-section row data once (shared by text + HTML renderers) ----
    def _passer_data():
        data = []
        for i in passed:
            r = by_id.get(i, {})
            disp, src, _basis, vconf = _value(_opp_json(i))
            data.append({"opp": i, "verdict": r.get("recommendation", ""),
                         "verdict_conf": _verdict_conf(i),
                         "rationale": _rationale(opps_dir, i), "value": disp, "value_src": src,
                         "value_conf": vconf, "expired": _expired(i),
                         "due": r.get("due") or "", "draft": bool(_find_draft(os.path.join(opps_dir, i)))})
        return data

    def _simple_data(ids):
        data = []
        for i in ids:
            r = by_id.get(i, {})
            disp, src, _b, vconf = _value(_opp_json(i))
            data.append({"opp": i, "rec": r.get("recommendation", ""), "value": disp,
                         "value_src": src, "value_conf": vconf,
                         "overall_conf": _overall_conf(i), "due": r.get("due") or ""})
        return data

    passer_data = _passer_data()
    added_data = _simple_data(added)
    updated_data = _simple_data(updated)
    decisions = [{"opp": res.opportunity, "ask": it}
                 for res in report.results for it in res.open_items]
    # Below-HIGH stage outputs, split by KIND (P2b): a 'needs-research' gap is something the harness
    # resolves on the next run (an Auto-research queue) — NOT a task for the human; a 'human-decision'
    # gap is a genuine judgment the operator must settle (Review / override).
    all_items = [{"opp": res.opportunity, "stage": it.get("stage", ""),
                  "confidence": it.get("confidence", ""), "reason": it.get("reason", ""),
                  "remedy": it.get("remedy", ""), "kind": it.get("kind", "human-decision")}
                 for res in report.results for it in (res.review_items or [])]
    research_queue = [it for it in all_items if it["kind"] == "needs-research"]
    review = [it for it in all_items if it["kind"] != "needs-research"]
    errs = [{"opp": res.opportunity, "error": res.error} for res in report.results if res.error]

    # ---- plaintext body (fallback) ----
    text = _render_text(lead, when, report.mode_note, added_data, updated_data, passer_data,
                        decisions, review, research_queue, errs)
    # ---- HTML body (tables, Gmail-friendly inline styles) ----
    html = _render_html(lead, when, report.mode_note, added_data, updated_data, passer_data,
                        decisions, review, research_queue, errs)

    msg = EmailMessage()
    default_subject = (f"{org} " if org else "") + "Bid Sourcing — daily digest"
    subject = dcfg.get("subject") or default_subject   # tolerate an explicit null in config
    msg["Subject"] = f"{subject} ({when})"
    if dcfg.get("to"):
        msg["To"] = dcfg["to"]
    if dcfg.get("from"):
        msg["From"] = dcfg["from"]
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    body = text   # kept for the oversize-draft fallback below

    # attach the passers' drafts (or note a link if over the size cap)
    cap_mb = dcfg.get("max_attachment_mb", 20)
    for pid in passed:
        opp_dir = os.path.join(opps_dir, pid)
        draft = _find_draft(opp_dir)
        if not draft:
            continue
        size_mb = os.path.getsize(draft) / 1_000_000
        if size_mb > cap_mb:
            # too big to attach — the Passed table already lists the passer and its draft flag;
            # skip the attachment (don't mutate the multipart body / HTML alternative).
            continue
        with open(draft, "rb") as fh:
            data = fh.read()
        ext = os.path.splitext(draft)[1].lstrip(".") or "bin"
        maintype = "application"
        subtype = {"pdf": "pdf",
                   "docx": "vnd.openxmlformats-officedocument.wordprocessingml.document",
                   "xlsx": "vnd.openxmlformats-officedocument.spreadsheetml.sheet"}.get(ext, "octet-stream")
        msg.add_attachment(data, maintype=maintype, subtype=subtype,
                           filename=f"{pid}-{os.path.basename(draft)}")
    return msg


def send(msg, cfg):
    """Send via the existing Gmail send path. Returns the sent message id. Raises on backend error
    (the caller writes the digest to the log dir and exits non-zero)."""
    from . import mail_gmail
    gcfg = (cfg.get("digest", {}) or {}).get("gmail_api") or cfg.get("gmail_api") or {}
    return mail_gmail.send_raw(gcfg, msg.as_bytes())


def run(cfg, opps_dir=None, dry_run=False, out=None, sender=None):
    """Compose from a fresh orchestration pass, then send (unless dry-run). `sender` lets tests
    inject a fake; defaults to the real Gmail path. Returns (exit_code, message)."""
    opps_dir = opps_dir or cfg["opportunities_dir"]
    report = harness.orchestrate(cfg, opps_dir=opps_dir, dry_run=dry_run)
    rows = portfolio.build_portfolio(opps_dir, run_gates=False)
    msg = compose(report, rows, cfg, opps_dir)

    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(msg.as_string())
    if dry_run:
        return 0, msg

    send_on_empty = (cfg.get("digest", {}) or {}).get("send_on_empty", False)
    c = report.counts or {}
    if not send_on_empty and not (c.get("added") or c.get("updated")):
        return 0, msg  # quiet run: nothing new, suppressed

    try:
        (sender or send)(msg, cfg)
        return 0, msg
    except Exception as e:  # noqa: BLE001 — never lose the digest if the backend is down
        logdir = cfg.get("log_dir", "../inbox/logs")
        os.makedirs(logdir, exist_ok=True)
        fname = os.path.join(logdir, f"digest-{dt.date.today().isoformat()}.eml")
        with open(fname, "w", encoding="utf-8") as fh:
            fh.write(msg.as_string())
        return 1, f"send failed ({e}); digest written to {fname}"


# --------------------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="compose and send the daily digest")
    r.add_argument("--cfg", default=None)
    r.add_argument("--opps", default=None)
    r.add_argument("--dry-run", action="store_true", help="compose only; do not send")
    r.add_argument("--out", default=None, help="write the composed .eml here")
    a = ap.parse_args(argv)

    try:
        cfg = harness.load_config(a.cfg)
    except harness.HarnessError as e:
        print(f"HARNESS ERROR: {e}"); return 2

    code, result = run(cfg, opps_dir=a.opps, dry_run=a.dry_run, out=a.out)
    if a.dry_run:
        print(result.as_string() if hasattr(result, "as_string") else result)
    else:
        print(result if isinstance(result, str) else "sent")
    return code


if __name__ == "__main__":
    sys.exit(main())
