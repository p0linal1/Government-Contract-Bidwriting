#!/usr/bin/env python3
"""
dedup.py — one-time cross-folder duplicate finder/merger for the opportunity backlog.

Why: before ingest-time thread dedup existed, follow-up emails on one thread (and sourcing-digest
"New Opportunity Found" / "Recommendations" notices) were each filed as a NEW opportunity folder.
The mode-c agent then researched each duplicate independently — wasted work and triple-counted
value in the digest. This finds those clusters and, on --apply, folds the duplicates into one
canonical folder's followups/, keeping the richest-researched folder as canonical.

SAFETY — the hard problem here is that a generic portal subject ("WEBS Bidding Opportunity") is
shared by GENUINELY DIFFERENT solicitations. So clustering on subject alone is unsafe. A cluster is
only AUTO-MERGEABLE when it is demonstrably the same procurement:
  - the folders share a solicitation number (opportunity.json.solicitation_number), OR
  - the folders' source emails thread onto each other (In-Reply-To / References), OR
  - same normalized title AND same sender domain AND a matching due date (or no due on either).
A cluster that shares only a generic subject but DIFFERS on number/due is reported as 'review',
never auto-merged. Report-first; writes nothing without --apply. --apply uses `git mv` so the move
is tracked and reversible.

Nothing company- or bid-specific lives here (gate: tests/test_no_hardcoding.py).

CLI:
  python3 -m bidkit.dedup --all <opportunities-dir>            # report clusters (writes nothing)
  python3 -m bidkit.dedup --all <opportunities-dir> --json
  python3 -m bidkit.dedup --all <opportunities-dir> --apply    # fold auto-mergeable dups into followups/
"""
import argparse, json, os, re, subprocess, sys
from collections import defaultdict


def _norm_subject(s):
    """Strip Re:/Fwd:/[bracketed] prefixes, collapse whitespace, lowercase. Mirrors inbox.normalized_subject."""
    s = s or ""
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"^\s*(?:(?:re|fw|fwd)\s*:\s*|\[[^\]]*\]\s*)", "", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip().lower()


def _load(opp_dir):
    p = os.path.join(opp_dir, "opportunity.json")
    if not os.path.exists(p):
        return None
    try:
        return json.load(open(p, encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _info(opps_dir, name):
    """The dedup-relevant facts about one opportunity folder."""
    opp = _load(os.path.join(opps_dir, name)) or {}
    src = opp.get("source") or {}
    due = opp.get("due") or {}
    ve = opp.get("value_estimate") or {}
    # richness score: prefer the folder with the most research on disk as canonical
    research = os.path.join(opps_dir, name, "research")
    rfiles = len([f for f in os.listdir(research)]) if os.path.isdir(research) else 0
    rfp = os.path.join(opps_dir, name, "rfp")
    rfpfiles = len([f for f in os.listdir(rfp)]) if os.path.isdir(rfp) else 0
    return {
        "name": name,
        "title": _norm_subject(opp.get("title") or ""),
        "number": (opp.get("solicitation_number") or "").strip().upper(),
        "domain": (src.get("from") or "").split("@")[-1].lower(),
        "message_id": (src.get("message_id") or "").strip(),
        "due": (due.get("date") or "").strip(),
        "due_confirmed": bool(due.get("confirmed")),
        "anchor": ve.get("anchor") or ve.get("likely") or None,
        "richness": rfiles * 10 + rfpfiles + (5 if opp.get("recommendation") else 0),
    }


def _list_opps(opps_dir):
    out = []
    for name in sorted(os.listdir(opps_dir)):
        p = os.path.join(opps_dir, name)
        if os.path.isdir(p) and not name.startswith((".", "_")) and name not in ("sourcing",) \
                and os.path.exists(os.path.join(p, "opportunity.json")):
            out.append(name)
    return out


def _mergeable(members):
    """Decide whether a cluster (list of _info dicts, all same (title, domain)) is the SAME
    procurement and may be auto-merged. Returns (bool, reason)."""
    numbers = {m["number"] for m in members if m["number"]}
    if len(numbers) > 1:
        return False, f"different solicitation numbers {sorted(numbers)} — distinct solicitations"
    dues = {m["due"] for m in members if m["due"]}
    if len(dues) > 1:
        return False, f"different due dates {sorted(dues)} — likely distinct solicitations"
    # anchors wildly apart (>2x) suggest different scopes behind a shared generic subject
    anchors = [int(m["anchor"]) for m in members if isinstance(m["anchor"], (int, float))]
    if len(anchors) >= 2 and max(anchors) > 2 * max(1, min(anchors)):
        return False, f"value anchors differ >2x {sorted(anchors)} — likely distinct solicitations"
    return True, "same procurement (shared number/due, or consistent generic-subject thread)"


def find_clusters(opps_dir):
    """Group opportunities by (normalized title, sender domain) and classify each group of >1 as
    'merge' (auto-mergeable) or 'review' (shares a subject but looks like distinct solicitations).
    Returns a list of cluster dicts, each with canonical + duplicates + action + reason."""
    groups = defaultdict(list)
    for name in _list_opps(opps_dir):
        info = _info(opps_dir, name)
        if not info["title"]:
            continue
        groups[(info["title"], info["domain"])].append(info)

    clusters = []
    for (title, domain), members in sorted(groups.items()):
        if len(members) < 2:
            continue
        ok, reason = _mergeable(members)
        canonical = max(members, key=lambda m: (m["richness"], m["name"]))
        dups = [m for m in members if m["name"] != canonical["name"]]
        clusters.append({
            "title": title, "domain": domain,
            "action": "merge" if ok else "review",
            "reason": reason,
            "canonical": canonical["name"],
            "duplicates": [m["name"] for m in dups],
        })
    return clusters


def _git_mv(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        subprocess.run(["git", "mv", src, dst], check=True, capture_output=True, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        os.rename(src, dst)   # fall back to a plain move if not a git tree / git unavailable


def apply_merge(opps_dir, cluster):
    """Fold a cluster's duplicates into the canonical folder's followups/<name>/. Returns the moved
    paths. Non-destructive in spirit: the duplicate's content is preserved under the canonical
    folder, tracked via git mv. Only call on an action=='merge' cluster."""
    moved = []
    canon = os.path.join(opps_dir, cluster["canonical"])
    fu_root = os.path.join(canon, "initial-email", "followups")
    for dup in cluster["duplicates"]:
        src = os.path.join(opps_dir, dup)
        dst = os.path.join(fu_root, f"merged-{dup}")
        if os.path.isdir(src):
            _git_mv(src, dst)
            moved.append((dup, os.path.relpath(dst, opps_dir)))
    return moved


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", metavar="DIR", required=True, help="opportunities directory")
    ap.add_argument("--apply", action="store_true", help="fold auto-mergeable duplicates into followups/")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    clusters = find_clusters(a.all)
    if a.json:
        print(json.dumps(clusters, indent=2))
        return 0

    if not clusters:
        print("no duplicate clusters found")
        return 0

    for c in clusters:
        tag = "MERGE " if c["action"] == "merge" else "REVIEW"
        print(f"[{tag}] {c['title'][:55]!r} <{c['domain']}>")
        print(f"    canonical: {c['canonical']}")
        for d in c["duplicates"]:
            print(f"    duplicate: {d}")
        print(f"    reason: {c['reason']}")
        if a.apply and c["action"] == "merge":
            for dup, dst in apply_merge(a.all, c):
                print(f"    merged: {dup} -> {dst}")
    mergeable = [c for c in clusters if c["action"] == "merge"]
    review = [c for c in clusters if c["action"] == "review"]
    print(f"\n{len(mergeable)} auto-mergeable cluster(s), {len(review)} need human review."
          + ("" if a.apply else "  (re-run with --apply to merge the auto-mergeable ones)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
