#!/usr/bin/env python3
"""
mail_gmail.py — Gmail REST API (OAuth 2.0) implementation of the MailFetcher protocol.

SCAFFOLD for the machine that has Google API access. Same three-method protocol as
mail_imap.ImapFetcher (uids_since / fetch / mark_seen), so bidkit.inbox is backend-agnostic:
set  "source": {"type": "gmail_api"}  and a "gmail_api" block in inbox/inbox.json.

Dependencies are OPTIONAL and imported lazily — this module loads (and its tests run) without
them. Install on the target machine:  pip3 install -r bidkit/requirements-gmail.txt

Setup (one time, on a machine with a browser):
  1. Google Cloud console → APIs & Services → enable "Gmail API" → Credentials →
     "OAuth client ID" of type Desktop app → download the JSON.
  2. Save it OUTSIDE the repo, e.g. ~/.config/bidkit/gmail-credentials.json (config key
     gmail_api.credentials_file).
  3. python3 -m bidkit.mail_gmail auth --cfg inbox/inbox.json
     → opens a browser for consent, writes gmail_api.token_file (refresh token). On a headless
       box, run `auth` on a machine with a browser and copy the token file over (chmod 600).
  Scopes: gmail.readonly by default; gmail.modify is requested only when inbox.mark_seen is true
  (changing scopes later requires deleting the token file and re-running `auth`).

Config block:
  "gmail_api": {"credentials_file": "~/.config/bidkit/gmail-credentials.json",
                "token_file": "~/.config/bidkit/gmail-token.json",
                "user": "me", "query": "in:inbox", "label_ids": [],
                "raw_cache_dir": "../secrets/gmail-raw-cache"}
  raw_cache_dir (optional): a directory to cache raw messages as <id>.eml. Set it and each message
  is fetched from the API at most once, ever; subsequent polls/parses read from disk. This is what
  keeps repeated runs under Gmail's per-minute query-cost quota. Omit to disable caching. API calls
  also use exponential backoff on 429/5xx, so the FIRST (cache-populating) run survives the quota.
  Treat the cache as private mail content — keep it outside the repo (gitignored) like the token.

CLI:
  python3 -m bidkit.mail_gmail auth --cfg inbox/inbox.json         # run/refresh the OAuth flow
  python3 -m bidkit.mail_gmail test --cfg inbox/inbox.json [--since-days 7]
"""
import argparse, base64, datetime as dt, os, random, sys, time
from .mail_imap import MailError, parse_message

SCOPE_READ = "https://www.googleapis.com/auth/gmail.readonly"
SCOPE_MODIFY = "https://www.googleapis.com/auth/gmail.modify"
SCOPE_SEND = "https://www.googleapis.com/auth/gmail.send"
INSTALL_HINT = "pip3 install -r bidkit/requirements-gmail.txt  (google-api-python-client, google-auth-oauthlib)"


def _expand(p):
    return os.path.expanduser(p) if p else p


def _scopes(mark_seen):
    return [SCOPE_MODIFY] if mark_seen else [SCOPE_READ]


def load_credentials(gcfg, mark_seen=False, interactive=False):
    """Return google.oauth2 Credentials, refreshing or (if interactive) running the consent flow.
    Raises MailError with actionable text when libraries or files are missing."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError:
        raise MailError(f"Gmail API libraries not installed: {INSTALL_HINT}")
    token_file = _expand(gcfg.get("token_file", "~/.config/bidkit/gmail-token.json"))
    cred_file = _expand(gcfg.get("credentials_file", "~/.config/bidkit/gmail-credentials.json"))
    scopes = _scopes(mark_seen)
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, scopes)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not interactive:
            raise MailError(f"no valid Gmail token at {token_file}; run: python3 -m bidkit.mail_gmail auth --cfg <inbox.json>")
        if not os.path.exists(cred_file):
            raise MailError(f"OAuth client file not found: {cred_file} (download a Desktop-app OAuth client JSON from Google Cloud)")
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError:
            raise MailError(f"google-auth-oauthlib not installed: {INSTALL_HINT}")
        flow = InstalledAppFlow.from_client_secrets_file(cred_file, scopes)
        creds = flow.run_local_server(port=0, open_browser=True)
    os.makedirs(os.path.dirname(token_file), exist_ok=True)
    with open(token_file, "w", encoding="utf-8") as fh:
        fh.write(creds.to_json())
    try:
        os.chmod(token_file, 0o600)
    except OSError:
        pass
    return creds


def build_service(creds):
    try:
        from googleapiclient.discovery import build
    except ImportError:
        raise MailError(f"google-api-python-client not installed: {INSTALL_HINT}")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def gmail_query(base_query, days, now=None):
    """Gmail search string for the recent window. `after:` takes epoch seconds."""
    now = now or dt.datetime.now(dt.timezone.utc)
    after = int((now - dt.timedelta(days=int(days))).timestamp())
    q = (base_query or "").strip()
    return f"{q} after:{after}".strip()


def decode_raw(raw_b64url):
    """Gmail returns the RFC 822 message base64url-encoded (no padding)."""
    pad = "=" * (-len(raw_b64url) % 4)
    return base64.urlsafe_b64decode(raw_b64url + pad)


def _encode_raw(raw_bytes):
    """Inverse of decode_raw: RFC 822 bytes -> base64url without padding (Gmail's wire form)."""
    return base64.urlsafe_b64encode(raw_bytes).decode("ascii").rstrip("=")


# ---------------------------------------------------------------- sending (gmail.send scope)
# Sending is a SEPARATE capability from fetching: it needs the gmail.send scope, which requires
# its own consent and its own token file (default gmail_api.send_token_file) so it never disturbs
# the read-only fetch token. Gmail sends AS the authenticated account; you cannot spoof From to an
# address the account can't send as.
def load_send_credentials(gcfg, interactive=False):
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError:
        raise MailError(f"Gmail API libraries not installed: {INSTALL_HINT}")
    token_file = _expand(gcfg.get("send_token_file", "../secrets/gmail-send-token.json"))
    cred_file = _expand(gcfg.get("credentials_file", "~/.config/bidkit/gmail-credentials.json"))
    scopes = [SCOPE_SEND]
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, scopes)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not interactive:
            raise MailError(f"no valid Gmail SEND token at {token_file}; run: python3 -m bidkit.mail_gmail send-auth --cfg <inbox.json>")
        if not os.path.exists(cred_file):
            raise MailError(f"OAuth client file not found: {cred_file}")
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError:
            raise MailError(f"google-auth-oauthlib not installed: {INSTALL_HINT}")
        flow = InstalledAppFlow.from_client_secrets_file(cred_file, scopes)
        creds = flow.run_local_server(port=0, open_browser=True)
    os.makedirs(os.path.dirname(token_file), exist_ok=True)
    with open(token_file, "w", encoding="utf-8") as fh:
        fh.write(creds.to_json())
    try:
        os.chmod(token_file, 0o600)
    except OSError:
        pass
    return creds


def send_raw(gcfg, raw_bytes, service=None):
    """Send an RFC-822 message (bytes) via the Gmail API. Returns the sent message id.
    Sends as the authenticated account (userId='me')."""
    if service is None:
        service = build_service(load_send_credentials(gcfg))
    body = {"raw": _encode_raw(raw_bytes)}
    resp = _execute_with_backoff(service.users().messages().send(userId="me", body=body))
    return resp.get("id")


# Gmail's per-user "Total Query Cost" quota is per-MINUTE: a burst of raw fetches (one poll can be
# ~100 messages) trips 429/403 rateLimitExceeded. The API has no client-side pacing, so we add
# exponential backoff with jitter and honour Retry-After when present. Only rate/5xx errors retry;
# everything else (404, auth) is re-raised immediately.
MAX_RETRIES = 6
BASE_DELAY_S = 2.0
_RETRY_REASONS = {"rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded", "backendError", "internalError"}


def _is_retryable(exc):
    """True for a googleapiclient HttpError that represents a transient rate/5xx condition."""
    status = getattr(getattr(exc, "resp", None), "status", None)
    try:
        status = int(status)
    except (TypeError, ValueError):
        status = None
    if status in (429, 500, 502, 503):
        return True
    if status == 403:                                   # 403 is overloaded; only retry the rate-limit reasons
        blob = ""
        try:
            blob = exc.content.decode("utf-8", "replace") if isinstance(exc.content, bytes) else str(exc.content or "")
        except Exception:
            blob = str(exc)
        return any(r in blob for r in _RETRY_REASONS)
    return False


def _execute_with_backoff(request, _sleep=time.sleep):
    """Call request.execute() with exponential backoff on transient rate-limit / 5xx errors.
    `request` is a googleapiclient request object (has .execute()). Non-retryable errors propagate."""
    try:
        from googleapiclient.errors import HttpError
    except ImportError:                                 # tests inject fakes whose .execute() never raises HttpError
        return request.execute()
    for attempt in range(MAX_RETRIES + 1):
        try:
            return request.execute()
        except HttpError as e:
            if attempt >= MAX_RETRIES or not _is_retryable(e):
                raise
            delay = BASE_DELAY_S * (2 ** attempt) + random.uniform(0, 1.0)
            _sleep(delay)


class GmailFetcher:
    """MailFetcher over the Gmail API. `service` is injectable (tests pass a fake)."""
    def __init__(self, gcfg, mark_seen=False, service=None):
        self.cfg = gcfg; self.mark_seen_scope = mark_seen; self.service = service
        self.user = gcfg.get("user", "me")
        # Optional on-disk cache of raw messages, keyed by Gmail message id. When set, each message
        # is fetched from the API at most once — ever; later polls/parses read the .eml from disk.
        # This is what keeps repeated runs off the per-minute quota. Off unless raw_cache_dir is set.
        self.cache_dir = _expand(gcfg.get("raw_cache_dir"))
        if self.cache_dir:
            os.makedirs(self.cache_dir, exist_ok=True)

    def __enter__(self):
        if self.service is None:
            self.service = build_service(load_credentials(self.cfg, mark_seen=self.mark_seen_scope))
        return self

    def __exit__(self, *exc):
        try:
            self.service.close()
        except Exception:
            pass

    def uids_since(self, days):
        q = gmail_query(self.cfg.get("query", "in:inbox"), days)
        ids, token = [], None
        while True:
            kwargs = {"userId": self.user, "q": q, "maxResults": 100}
            if self.cfg.get("label_ids"):
                kwargs["labelIds"] = self.cfg["label_ids"]
            if token:
                kwargs["pageToken"] = token
            resp = _execute_with_backoff(self.service.users().messages().list(**kwargs))
            ids += [m["id"] for m in resp.get("messages", [])]
            token = resp.get("nextPageToken")
            if not token:
                break
        return list(reversed(ids))          # oldest first, like the IMAP UID order

    def _cache_path(self, uid):
        return os.path.join(self.cache_dir, f"{uid}.eml") if self.cache_dir else None

    def fetch(self, uid):
        # 1. Cache hit — parse the local .eml, no API call.
        cpath = self._cache_path(uid)
        if cpath and os.path.exists(cpath):
            with open(cpath, "rb") as fh:
                return parse_message(fh.read())
        # 2. Cache miss (or caching off) — hit the API once, then persist the raw bytes.
        msg = _execute_with_backoff(
            self.service.users().messages().get(userId=self.user, id=uid, format="raw"))
        raw = msg.get("raw")
        if not raw:
            return None
        raw_bytes = decode_raw(raw)
        if cpath:
            tmp = cpath + ".tmp"
            with open(tmp, "wb") as fh:
                fh.write(raw_bytes)
            os.replace(tmp, cpath)          # atomic; a partial write never becomes a poisoned cache entry
        return parse_message(raw_bytes)

    def mark_seen(self, uid):
        _execute_with_backoff(self.service.users().messages().modify(
            userId=self.user, id=uid, body={"removeLabelIds": ["UNREAD"]}))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("auth", help="run the OAuth consent flow and store the token"); a1.add_argument("--cfg", required=True)
    t = sub.add_parser("test", help="list recent messages"); t.add_argument("--cfg", required=True)
    t.add_argument("--since-days", type=int, default=7)
    sa = sub.add_parser("send-auth", help="run the OAuth consent flow for the gmail.send scope"); sa.add_argument("--cfg", required=True)
    sd = sub.add_parser("send", help="send an .eml file via the Gmail API")
    sd.add_argument("--cfg", required=True); sd.add_argument("--eml", required=True)
    a = ap.parse_args(argv)
    from .inbox import load_config
    cfg = load_config(a.cfg)
    if "gmail_api" not in cfg:
        print("no 'gmail_api' block in config"); return 2
    try:
        if a.cmd == "auth":
            creds = load_credentials(cfg["gmail_api"], mark_seen=bool(cfg.get("mark_seen")), interactive=True)
            print(f"token stored at {_expand(cfg['gmail_api'].get('token_file', '~/.config/bidkit/gmail-token.json'))}"
                  f" (scopes: {', '.join(_scopes(bool(cfg.get('mark_seen'))))})")
            return 0
        if a.cmd == "send-auth":
            load_send_credentials(cfg["gmail_api"], interactive=True)
            print(f"SEND token stored at {_expand(cfg['gmail_api'].get('send_token_file', '../secrets/gmail-send-token.json'))} (scope: {SCOPE_SEND})")
            return 0
        if a.cmd == "send":
            with open(a.eml, "rb") as fh:
                raw = fh.read()
            mid = send_raw(cfg["gmail_api"], raw)
            print(f"sent: message id {mid}")
            return 0
        with GmailFetcher(cfg["gmail_api"], mark_seen=bool(cfg.get("mark_seen"))) as f:
            ids = f.uids_since(a.since_days)
            print(f"Gmail API OK: {len(ids)} message(s) match {gmail_query(cfg['gmail_api'].get('query','in:inbox'), a.since_days)!r}")
            if ids:
                m = f.fetch(ids[-1]); print(f"  newest: {m['Subject']!r} from {m['From']}")
        return 0
    except MailError as e:
        print(f"GMAIL ERROR: {e}"); return 1


if __name__ == "__main__":
    sys.exit(main())
