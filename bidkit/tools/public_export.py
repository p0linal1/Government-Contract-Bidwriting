#!/usr/bin/env python3
"""
public_export.py — build a publishable copy of a private working repo from an ALLOWLIST.

Pipeline (fails closed at every step):
  1. select   — copy only files matching an `include` glob and no `exclude` glob
                (fnmatch semantics on the repo-relative POSIX path: `*` also matches `/`);
  2. strip    — drop every private block: a line that is only a comment containing the begin
                marker, through the matching end-marker line (both removed). Comment leaders
                recognized: `#`, `<!--`, `//`. Unbalanced or nested markers are an error;
  3. rewrite  — apply ordered regex `substitutions` to file CONTENTS and to file PATHS;
  4. overlay  — copy `overlay_dir` files over the result verbatim (generic replacements for
                files that are wholly private, e.g. a company profile);
  5. scan     — every output path and file is checked against the `denylist` (case-insensitive
                regexes) and every e-mail address must be on `allow_email_domains` /
                `allow_emails`. Any hit fails the export;
  6. test     — optional command run inside the output (e.g. the pytest suite), caches removed after;
  7. git      — optional fresh `git init` (NO history from the source repo); commit only when an
                explicit author is given, so the source repo's identity is never used by accident.

The config is private data (it names what must not leak) and is never itself exported.

Usage:
  python3 bidkit/tools/public_export.py --config <cfg.json> --out <dir> [--git] [--author "Name <email>"]
         [--no-test] [--check]
Exit codes: 0 ok, 1 scan/test failure, 2 config/usage error.
"""
import argparse
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

MARK_FILE = ".public-export"
# Built from parts so this file's own source never reads as a marker line.
_KW_BEGIN = "private" + ":begin"
_KW_END = "private" + ":end"
_LEADER = r"^\s*(?:#|<!--|//)\s*"
BEGIN_RE = re.compile(_LEADER + re.escape(_KW_BEGIN) + r"\b")
END_RE = re.compile(_LEADER + re.escape(_KW_END) + r"\b")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
CACHE_DIRS = {"__pycache__", ".pytest_cache"}


class ExportError(Exception):
    pass


# ---------------------------------------------------------------------------------------- config
def load_config(path: Path) -> dict:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    for key in ("include", "denylist"):
        if not cfg.get(key):
            raise ExportError(f"config: '{key}' is required and must be non-empty")
    cfg.setdefault("exclude", [])
    cfg.setdefault("substitutions", [])
    cfg.setdefault("allow_email_domains", [])
    cfg.setdefault("allow_emails", [])
    cfg["_subs"] = [(re.compile(s["pattern"], re.I if "i" in s.get("flags", "") else 0), s["replace"])
                    for s in cfg["substitutions"]]
    cfg["_deny"] = [(re.compile(d["pattern"], re.I), d.get("label", d["pattern"])) for d in cfg["denylist"]]
    return cfg


# ---------------------------------------------------------------------------------------- steps
def select_files(root: Path, include: List[str], exclude: List[str]) -> List[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        dirnames[:] = [d for d in dirnames if d != ".git" and d not in CACHE_DIRS]
        for name in filenames:
            rel = name if rel_dir == "." else f"{rel_dir}/{name}"
            if any(fnmatch.fnmatchcase(rel, g) for g in include) and \
               not any(fnmatch.fnmatchcase(rel, g) for g in exclude):
                out.append(rel)
    return sorted(out)


def strip_private(text: str, rel: str) -> Tuple[str, int]:
    """Remove private blocks. Returns (text, number of lines removed)."""
    kept, removed, start = [], 0, None
    for i, line in enumerate(text.splitlines(keepends=True), 1):
        if BEGIN_RE.search(line):
            if start is not None:
                raise ExportError(f"{rel}:{i}: nested private block (opened at line {start})")
            start = i; removed += 1; continue
        if END_RE.search(line):
            if start is None:
                raise ExportError(f"{rel}:{i}: private block end without begin")
            start = None; removed += 1; continue
        if start is None:
            kept.append(line)
        else:
            removed += 1
    if start is not None:
        raise ExportError(f"{rel}:{start}: private block never closed")
    return "".join(kept), removed


def substitute(s: str, subs) -> str:
    for rx, rep in subs:
        s = rx.sub(rep, s)
    return s


def as_text(data: bytes) -> Optional[str]:
    if b"\0" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def scan(out: Path, cfg: dict) -> List[str]:
    hits = []
    allow_domains = {d.lower() for d in cfg["allow_email_domains"]}
    allow_emails = {e.lower() for e in cfg["allow_emails"]}
    for p in sorted(out.rglob("*")):
        if ".git" in p.relative_to(out).parts or not p.is_file() or p.name == MARK_FILE:
            continue
        rel = p.relative_to(out).as_posix()
        for rx, label in cfg["_deny"]:
            if rx.search(rel):
                hits.append(f"{rel}: [path] [{label}]")
        data = p.read_bytes()
        text = as_text(data)
        if text is None:                       # binary: scan raw bytes for denylisted terms
            blob = data.decode("latin-1")
            for rx, label in cfg["_deny"]:
                if rx.search(blob):
                    hits.append(f"{rel}: [binary] [{label}]")
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for rx, label in cfg["_deny"]:
                if rx.search(line):
                    hits.append(f"{rel}:{n}: [{label}] {line.strip()[:100]}")
            for m in EMAIL_RE.finditer(line):
                addr = m.group(0).lower()
                domain = addr.split("@", 1)[1]
                if addr in allow_emails or any(domain == d or domain.endswith("." + d) for d in allow_domains):
                    continue
                hits.append(f"{rel}:{n}: [email not allowlisted] {m.group(0)}")
    return hits


def clean_caches(out: Path) -> None:
    for d in list(out.rglob("*")):
        if d.is_dir() and d.name in CACHE_DIRS:
            shutil.rmtree(d, ignore_errors=True)


def prepare_out(out: Path, root: Path) -> None:
    out = out.resolve()
    try:
        root.relative_to(out)
        raise ExportError(f"refusing to write to {out}: it contains the source repo")
    except ValueError:
        pass
    if out.exists():
        if not (out / MARK_FILE).exists():
            raise ExportError(f"refusing to overwrite {out}: not a previous export (no {MARK_FILE})")
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / MARK_FILE).write_text("generated by public_export.py; safe to delete and rebuild\n")


# ---------------------------------------------------------------------------------------- main
def export(root: Path, cfg: dict, out: Path) -> Dict[str, int]:
    files = select_files(root, cfg["include"], cfg["exclude"])
    if not files:
        raise ExportError("include globs matched no files")
    stats = {"files": 0, "private_lines_stripped": 0, "rewritten": 0, "overlay": 0}
    for rel in files:
        new_rel = substitute(rel, cfg["_subs"])
        dest = out / new_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = (root / rel).read_bytes()
        text = as_text(data)
        if text is None:
            dest.write_bytes(data)
        else:
            stripped, n = strip_private(text, rel)
            final = substitute(stripped, cfg["_subs"])
            stats["private_lines_stripped"] += n
            stats["rewritten"] += final != text
            dest.write_text(final, encoding="utf-8")
        shutil.copymode(root / rel, dest)
        stats["files"] += 1
    overlay = cfg.get("overlay_dir")
    if overlay:
        src = (root / overlay)
        for p in sorted(src.rglob("*")):
            if p.is_file() and p.name != ".DS_Store":
                dest = out / p.relative_to(src)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)
                stats["overlay"] += 1
    return stats


def run_tests(out: Path, cfg: dict) -> bool:
    t = cfg.get("test")
    if not t:
        return True
    cmd = [sys.executable if c == "{python}" else c for c in t["cmd"]]
    print(f"test: {' '.join(cmd)}  (cwd {t.get('cwd', '.')})")
    r = subprocess.run(cmd, cwd=out / t.get("cwd", "."))
    clean_caches(out)
    return r.returncode == 0


def git_init(out: Path, author: Optional[str]) -> None:
    def g(*a):
        subprocess.run(["git", *a], cwd=out, check=True)
    g("init", "-q", "-b", "main")
    (out / ".git" / "info").mkdir(parents=True, exist_ok=True)
    with open(out / ".git" / "info" / "exclude", "a") as f:
        f.write(f"\n{MARK_FILE}\n")
    g("add", "-A")
    tracked = subprocess.run(["git", "ls-files"], cwd=out, capture_output=True, text=True, check=True).stdout.split()
    on_disk = [p.relative_to(out).as_posix() for p in out.rglob("*")
               if p.is_file() and ".git" not in p.relative_to(out).parts and p.name != MARK_FILE]
    ignored = sorted(set(on_disk) - set(tracked))
    if ignored:
        print(f"note: {len(ignored)} exported file(s) are matched by the exported .gitignore and not staged:")
        for p in ignored[:20]:
            print(f"   {p}")
    if author:
        m = re.match(r"^\s*(.+?)\s*<([^>]+)>\s*$", author)
        if not m:
            raise ExportError("--author must look like 'Name <email>'")
        name, email = m.groups()
        subprocess.run(["git", "-c", f"user.name={name}", "-c", f"user.email={email}",
                        "commit", "-q", "-m", "Initial public release"], cwd=out, check=True)
        print(f"git: committed as {name} <{email}> (fresh history, 1 commit)")
    else:
        print("git: initialized and staged; NOT committed (pass --author 'Name <email>' to commit).")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2],
                    help="source repo root (default: two levels above this file)")
    ap.add_argument("--git", action="store_true", help="git init the output (fresh history)")
    ap.add_argument("--author", help="'Name <email>' to make the initial commit (requires --git)")
    ap.add_argument("--no-test", action="store_true")
    ap.add_argument("--check", action="store_true", help="list selected files; write nothing")
    a = ap.parse_args(argv)
    try:
        root = a.root.resolve()
        cfg = load_config(a.config)
        if a.check:
            files = select_files(root, cfg["include"], cfg["exclude"])
            for f in files:
                print(f"   {f}  ->  {substitute(f, cfg['_subs'])}")
            print(f"{len(files)} files selected")
            return 0
        if a.author and not a.git:
            raise ExportError("--author requires --git")
        prepare_out(a.out, root)
        stats = export(root, cfg, a.out)
        print(f"exported {stats['files']} files (+{stats['overlay']} overlay) to {a.out}; "
              f"{stats['rewritten']} rewritten, {stats['private_lines_stripped']} private lines stripped")
        hits = scan(a.out, cfg)
        if hits:
            print(f"SCAN FAILED — {len(hits)} hit(s); nothing is publishable until these are fixed:")
            for h in hits:
                print(f"   {h}")
            return 1
        print("scan: clean")
        if not a.no_test and not run_tests(a.out, cfg):
            print("TESTS FAILED in the export")
            return 1
        hits = scan(a.out, cfg)                  # tests must not have written anything sensitive
        if hits:
            print("SCAN FAILED after tests:"); [print(f"   {h}") for h in hits]
            return 1
        if a.git:
            git_init(a.out, a.author)
        return 0
    except ExportError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
