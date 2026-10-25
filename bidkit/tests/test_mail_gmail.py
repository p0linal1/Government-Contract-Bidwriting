import base64, datetime as dt, email.utils, json
from email.message import EmailMessage
import pytest
from bidkit import inbox, mail_gmail
from bidkit.mail_imap import MailError


# ----------------------------------------------------------------------------- fake Gmail service
class _Call:
    def __init__(self, result): self._r = result
    def execute(self): return self._r


class FakeMessages:
    def __init__(self, store, pages):
        self.store = store; self.pages = pages; self.list_calls = []; self.modified = []
    def list(self, **kw):
        self.list_calls.append(kw)
        page = self.pages[len(self.list_calls) - 1]
        return _Call(page)
    def get(self, userId, id, format):
        assert format == "raw"
        raw = base64.urlsafe_b64encode(self.store[id].as_bytes()).decode().rstrip("=")   # Gmail strips padding
        return _Call({"id": id, "raw": raw})
    def modify(self, userId, id, body):
        self.modified.append((id, body)); return _Call({"id": id})


class FakeService:
    def __init__(self, store, pages): self._m = FakeMessages(store, pages); self.closed = False
    def users(self): return self
    def messages(self): return self._m
    def close(self): self.closed = True


def _msg(subject, mid):
    m = EmailMessage(); m["Subject"] = subject; m["From"] = "a@b.example"; m["To"] = "bids@example.com"
    m["Date"] = email.utils.format_datetime(dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)); m["Message-ID"] = mid
    m.set_content("Proposals due October 1, 2026.")
    return m


# ----------------------------------------------------------------------------- unit
def test_gmail_query_uses_epoch_after():
    now = dt.datetime(2026, 9, 16, 12, 0, tzinfo=dt.timezone.utc)
    q = mail_gmail.gmail_query("in:inbox", 7, now=now)
    assert q.startswith("in:inbox after:")
    assert int(q.split("after:")[1]) == int((now - dt.timedelta(days=7)).timestamp())
    assert mail_gmail.gmail_query("", 1, now=now).startswith("after:")


def test_decode_raw_handles_missing_padding():
    raw = b"Subject: x\r\n\r\nbody"
    enc = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    assert mail_gmail.decode_raw(enc) == raw


def test_fetcher_lists_paginates_fetches_and_marks_seen():
    store = {"m1": _msg("RFP 1-100 A", "<1@x>"), "m2": _msg("RFP 1-200 B", "<2@x>"), "m3": _msg("Lunch", "<3@x>")}
    pages = [{"messages": [{"id": "m3"}, {"id": "m2"}], "nextPageToken": "p2"}, {"messages": [{"id": "m1"}]}]
    svc = FakeService(store, pages)
    with mail_gmail.GmailFetcher({"query": "in:inbox", "label_ids": ["INBOX"]}, service=svc) as f:
        ids = f.uids_since(7)
        assert ids == ["m1", "m2", "m3"]                          # reversed -> oldest first
        assert svc._m.list_calls[0]["labelIds"] == ["INBOX"] and "pageToken" not in svc._m.list_calls[0]
        assert svc._m.list_calls[1]["pageToken"] == "p2"
        m = f.fetch("m2")
        assert m["Subject"] == "RFP 1-200 B" and m["Message-ID"] == "<2@x>"
        f.mark_seen("m2")
        assert svc._m.modified == [("m2", {"removeLabelIds": ["UNREAD"]})]
    assert svc.closed


def test_poll_end_to_end_through_gmail_fetcher(tmp_path):
    """The generic inbox pipeline runs unchanged on top of the Gmail backend."""
    root = tmp_path / "repo"; (root / "inbox").mkdir(parents=True)
    tmpl = root / "opportunities" / "_template"; (tmpl / "initial-email").mkdir(parents=True)
    (tmpl / "opportunity.json").write_text(json.dumps({"id": "{{ID}}", "format": {"font_family_allow": [], "min_font_pt": 10,
        "margin_in": 1, "page_size": "letter", "page_limit": None}, "fonts": {"regular": "r", "bold": "b", "italic": "i", "bold_italic": "bi"},
        "folders": {"extract": "e", "draft": "d", "final": "f", "submit": "SUBMIT"}}))
    cfgp = root / "inbox" / "inbox.json"
    cfgp.write_text(json.dumps({"source": {"type": "gmail_api"}, "gmail_api": {"query": "in:inbox"}}))
    cfg = inbox.load_config(str(cfgp))
    store = {"g1": _msg("RFP 26-013 BIPIN", "<g1@x>"), "g2": _msg("Lunch", "<g2@x>")}
    svc = FakeService(store, [{"messages": [{"id": "g2"}, {"id": "g1"}]}])
    results = inbox.poll(cfg, fetcher_factory=lambda c: mail_gmail.GmailFetcher(c["gmail_api"], service=svc))
    assert [r["action"] for r in results] == ["new", "ignore"]
    assert (root / "opportunities" / "26-013-BIPIN" / "initial-email" / "email.md").exists()


def test_make_fetcher_dispatch(tmp_path):
    cfgp = tmp_path / "inbox.json"
    cfgp.write_text(json.dumps({"source": {"type": "gmail_api"}, "gmail_api": {"query": "in:inbox"}}))
    f = inbox.make_fetcher(inbox.load_config(str(cfgp)))
    assert isinstance(f, mail_gmail.GmailFetcher)
    cfgp.write_text(json.dumps({"imap": {"host": "h", "user": "u", "password_env": "X"}}))
    from bidkit.mail_imap import ImapFetcher
    assert isinstance(inbox.make_fetcher(inbox.load_config(str(cfgp))), ImapFetcher)      # default = imap
    cfgp.write_text(json.dumps({"source": {"type": "carrier-pigeon"}}))
    with pytest.raises(inbox.InboxError):
        inbox.make_fetcher(inbox.load_config(str(cfgp)))
    cfgp.write_text(json.dumps({"source": {"type": "gmail_api"}}))                        # block missing
    with pytest.raises(inbox.InboxError):
        inbox.make_fetcher(inbox.load_config(str(cfgp)))


def test_missing_google_libs_is_a_clear_error(tmp_path):
    """On this machine the Google libraries are not installed: entering the real fetcher must fail
    with an install hint, not an ImportError traceback."""
    pytest.importorskip  # noqa (documenting intent; we WANT the libs absent here)
    try:
        import googleapiclient  # noqa: F401
        pytest.skip("google libs installed here; skip the absence test")
    except ImportError:
        pass
    with pytest.raises(MailError) as e:
        with mail_gmail.GmailFetcher({"token_file": str(tmp_path / "t.json")}):
            pass
    assert "requirements-gmail.txt" in str(e.value)


# ----------------------------------------------------------------------------- raw cache + backoff
def test_raw_cache_fetches_once_then_reads_disk(tmp_path):
    """With raw_cache_dir set, the first fetch hits the API and writes <id>.eml; the second reads
    the .eml from disk and makes no further API call."""
    store = {"m1": _msg("RFP 9-001 Cache", "<c1@x>")}
    svc = FakeService(store, [{"messages": [{"id": "m1"}]}])
    cache = tmp_path / "raw-cache"
    with mail_gmail.GmailFetcher({"query": "in:inbox", "raw_cache_dir": str(cache)}, service=svc) as f:
        m1 = f.fetch("m1")
        assert m1["Subject"] == "RFP 9-001 Cache"
        assert (cache / "m1.eml").exists()
        # Corrupt the service so any further API get() would blow up — proves the 2nd read is cached.
        svc._m.get = lambda **kw: (_ for _ in ()).throw(AssertionError("API get() should not be called on a cache hit"))
        m2 = f.fetch("m1")
        assert m2["Subject"] == "RFP 9-001 Cache" and m2["Message-ID"] == "<c1@x>"


def test_execute_with_backoff_retries_then_succeeds(monkeypatch):
    """A retryable HttpError (429) is retried after sleeping; a later success returns normally."""
    httperr = pytest.importorskip("googleapiclient.errors", reason="google libs absent").HttpError

    class Resp:  # minimal httplib2-style response
        def __init__(self, status): self.status = status; self.reason = "rate"
    calls = {"n": 0}
    slept = []

    class Req:
        def execute(self):
            calls["n"] += 1
            if calls["n"] < 3:
                raise httperr(Resp(429), b'{"error":{"errors":[{"reason":"rateLimitExceeded"}]}}')
            return {"ok": True}

    out = mail_gmail._execute_with_backoff(Req(), _sleep=lambda d: slept.append(d))
    assert out == {"ok": True}
    assert calls["n"] == 3 and len(slept) == 2          # failed twice, slept twice, succeeded on the 3rd


def test_execute_with_backoff_reraises_non_retryable(monkeypatch):
    """A 404 is not a rate-limit condition and must propagate immediately (no retry loop)."""
    httperr = pytest.importorskip("googleapiclient.errors", reason="google libs absent").HttpError

    class Resp:
        def __init__(self, status): self.status = status; self.reason = "nf"
    calls = {"n": 0}

    class Req:
        def execute(self):
            calls["n"] += 1
            raise httperr(Resp(404), b'{"error":{"message":"Not Found"}}')

    with pytest.raises(httperr):
        mail_gmail._execute_with_backoff(Req(), _sleep=lambda d: None)
    assert calls["n"] == 1
