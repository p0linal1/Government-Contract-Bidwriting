#!/usr/bin/env python3
"""
mail_imap.py — IMAP implementation of the MailFetcher protocol used by bidkit.inbox.

MailFetcher protocol (any object usable as `with make_fetcher(cfg) as f:`):
    f.uids_since(days) -> list[str]        ids of candidate messages (newest window)
    f.fetch(uid)       -> EmailMessage|None parsed with email.policy.default
    f.mark_seen(uid)                       optional; only called when inbox.mark_seen is true
Sibling implementation: mail_gmail.GmailFetcher (Gmail REST API + OAuth). Tests inject fakes.

Read-only by default: messages are fetched with BODY.PEEK so polling never flips \\Seen.
Password: env var named by imap.password_env, else macOS keychain item
(service imap.password_keychain_service, account imap.user). Never stored in config.

CLI:  python3 -m bidkit.mail_imap test --cfg inbox/inbox.json     # login + count recent messages
"""
import argparse, datetime as dt, email, email.policy, imaplib, os, subprocess, sys


class MailError(Exception):
    pass


def resolve_password(imap_cfg):
    env = imap_cfg.get("password_env")
    if env and os.environ.get(env):
        return os.environ[env]
    svc = imap_cfg.get("password_keychain_service")
    if svc and sys.platform == "darwin":
        try:
            out = subprocess.run(["security", "find-generic-password", "-s", svc, "-a", imap_cfg["user"], "-w"],
                                 capture_output=True, text=True, check=True)
            if out.stdout.strip():
                return out.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    raise MailError(f"no mailbox password: set ${env or 'password_env'} or store it in the keychain "
                    f"(security add-generic-password -s {svc or '<service>'} -a {imap_cfg.get('user')} -w)")


def parse_message(raw_bytes):
    return email.message_from_bytes(raw_bytes, policy=email.policy.default)


class ImapFetcher:
    def __init__(self, imap_cfg, folder="INBOX"):
        self.cfg = imap_cfg; self.folder = folder; self.conn = None

    def __enter__(self):
        host = self.cfg["host"]; port = int(self.cfg.get("port", 993))
        self.conn = imaplib.IMAP4_SSL(host, port) if self.cfg.get("ssl", True) else imaplib.IMAP4(host, port)
        self.conn.login(self.cfg["user"], resolve_password(self.cfg))
        typ, _ = self.conn.select(self.folder, readonly=True)
        if typ != "OK":
            raise MailError(f"cannot select folder {self.folder!r}")
        return self

    def __exit__(self, *exc):
        try:
            self.conn.close(); self.conn.logout()
        except Exception:
            pass

    def uids_since(self, days):
        since = (dt.date.today() - dt.timedelta(days=int(days))).strftime("%d-%b-%Y")
        typ, data = self.conn.uid("search", None, f"(SINCE {since})")
        if typ != "OK":
            raise MailError("IMAP search failed")
        return [u.decode() for u in data[0].split()] if data and data[0] else []

    def fetch(self, uid):
        typ, data = self.conn.uid("fetch", uid, "(BODY.PEEK[])")
        if typ != "OK" or not data or data[0] is None:
            return None
        for part in data:
            if isinstance(part, tuple) and len(part) >= 2:
                return parse_message(part[1])
        return None

    def mark_seen(self, uid):
        self.conn.select(self.folder, readonly=False)
        self.conn.uid("store", uid, "+FLAGS", "(\\Seen)")
        self.conn.select(self.folder, readonly=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("test", help="log in and count messages in the recent window")
    t.add_argument("--cfg", required=True); t.add_argument("--since-days", type=int, default=7)
    a = ap.parse_args(argv)
    from .inbox import load_config
    cfg = load_config(a.cfg)
    try:
        with ImapFetcher(cfg["imap"], cfg.get("folder", "INBOX")) as f:
            uids = f.uids_since(a.since_days)
            print(f"IMAP OK: {cfg['imap']['user']} / {cfg.get('folder','INBOX')} — {len(uids)} message(s) in the last {a.since_days} day(s)")
            if uids:
                m = f.fetch(uids[-1])
                print(f"  newest: {m['Subject']!r} from {m['From']}")
        return 0
    except (MailError, imaplib.IMAP4.error, OSError) as e:
        print(f"IMAP ERROR: {e}"); return 1


if __name__ == "__main__":
    sys.exit(main())
