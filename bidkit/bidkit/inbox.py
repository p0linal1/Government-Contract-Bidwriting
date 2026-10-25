#!/usr/bin/env python3
"""
inbox.py — turn bid-invitation emails into opportunity folders. Designed to run from cron.

Why: solicitations arrive by email (portal notifications, partner forwards, agency blasts).
Left in a mailbox they get missed, and filing them by hand means the intake phase starts with
copy-paste. This module polls an IMAP mailbox, recognises solicitation emails, and files each
one into the standard opportunity layout — raw .eml, readable email.md, attachments, extracted
links, a best-effort due date, a filled opportunity.json, and an intake-brief.md that tells the
human (or a Kiro session) exactly what to do next. It is idempotent (dedupes on Message-ID),
read-only against the mailbox by default, and never invents facts: guesses are labelled guesses.

Routing: if the solicitation number in the subject matches an EXISTING opportunity folder, the
message is filed as a FOLLOW-UP (addendum / Q&A / reminder) under that opportunity instead of
creating a duplicate. Everything processed is appended to a queue (JSON lines) for pickup.

Deterministic only. The AI intake step (reading the RFP, building the timeline, reconciling a
partner checklist) is a separate, human-initiated step: open Kiro and say
"run intake on opportunities/<ID>" — the bid-intake steering takes it from there.

Config: inbox/inbox.json (see inbox/inbox.example.json). source.type selects the mail backend:
  imap       — imaplib (mail_imap.py); password from env var / macOS keychain, never in the file
  gmail_api  — Gmail REST API with OAuth (mail_gmail.py); token file outside the repo
Both implement the same MailFetcher protocol, so everything below is backend-agnostic.

CLI (run from the bidkit/ directory or with PYTHONPATH=bidkit):
  python3 -m bidkit.inbox poll   --cfg inbox/inbox.json [--dry-run] [--since-days N]
  python3 -m bidkit.inbox ingest --cfg inbox/inbox.json <message.eml>... [--dry-run]
  python3 -m bidkit.inbox queue  --cfg inbox/inbox.json [--all]
  python3 -m bidkit.inbox status --cfg inbox/inbox.json
"""
import argparse, datetime as dt, email.utils, html, json, os, re, shutil, sys

# ----------------------------------------------------------------------------- defaults
DEFAULT_SUBJECT_KEYWORDS = ["RFP", "RFQ", "RFI", "ITB", "Request for Proposal", "Request for Quote",
                            "Request for Qualifications", "Request for Information", "Invitation to Bid",
                            "Solicitation", "Sources Sought", "Bid Opportunity", "Bidding Opportunity",
                            "Bid Notice", "Notice of Funding"]
DEFAULT_ATTACHMENT_TYPES = [".pdf", ".xlsx", ".xls", ".xlsm", ".docx", ".doc", ".zip", ".csv", ".txt", ".rtf"]
STOPWORDS = set("a an the and or of to for in on at by with from re fw fwd request proposal proposals "
                "quote quotes qualifications information invitation bid bids rfp rfq rfi itb solicitation "
                "notice opportunity due reminder new posted issued released amendment addendum".split())
DATE_CUE = re.compile(r"(due|deadline|clos(?:e|es|ing)|submit(?:ted|tal|ssion)s?|no later than|by)\b", re.I)
DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})\b"), "mdy"),
    (re.compile(r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
                r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", re.I), "mon"),
]
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
SOL_NUMBER_PATTERNS = [
    re.compile(r"\b(?:RFP|RFQ|RFI|ITB|Bid|Solicitation)\s*(?:No\.?|Number|#)?\s*:?\s*([A-Z]{0,4}-?\d{2,4}-\d{2,4}(?:-[A-Z0-9]+)?)\b", re.I),
    re.compile(r"#\s*([A-Z]{0,4}-?\d{2,4}-\d{2,4}(?:-[A-Z0-9]+)?)\b"),
    re.compile(r"\b(\d{4}-\d{3,4}(?:-[A-Z0-9]+)?)\b"),
    re.compile(r"\b(\d{2}-\d{3}(?:-[A-Z0-9]+)?)\b"),
]
# Body-level extraction for portal/notification emails whose SUBJECT is generic ("WEBS Bidding
# Opportunity", "Important Bid Notice") but whose BODY carries the real reference number and title on
# labelled lines. Label-based and source-agnostic — any procurement email using these labels benefits.
# Each pattern captures a raw reference string; normalize_ref_number() cleans it. All require the
# capture to contain at least one digit (rejects "(RFP Release)" and other prose).
BODY_NUMBER_PATTERNS = [
    # WEBS: whole value after the label to end-of-line — "R2701", "2026_01", "RFP # 10266", "DRSRFP 26-06"
    re.compile(r"Customer\s+Reference\s+Number\s*:?\s*([^\r\n]{1,40})", re.I),
    # Parenthetical full number, e.g. DemandStar "(RFP-26-084-CCC-0-2026/DFW)"
    re.compile(r"\(\s*((?:RFP|RFQ|RFI|ITB|Bid|Solicitation)[- ]?[A-Z0-9][A-Z0-9./-]{3,40})\s*\)", re.I),
    # Generic "RFP No. / Solicitation #: <num>" appearing in the body
    re.compile(r"\b(?:RFP|RFQ|RFI|ITB|Solicitation)\s*(?:No\.?|Number|#)\s*:?\s*([A-Z]{0,5}-?\d{2,4}-[A-Z0-9-]{2,20})\b", re.I),
]
# WEBS/other "Title: <text>" line — a clean human title for the slug.
BODY_TITLE_PATTERN = re.compile(r"^\s*Title\s*:?\s*(.+?)\s*$", re.I | re.M)
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.I)


class InboxError(Exception):
    pass


from .mail_imap import MailError, parse_message, resolve_password  # noqa: E402  (protocol + helpers live there)


# ----------------------------------------------------------------------------- config / state
def load_config(path):
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    cfg = {k: v for k, v in raw.items() if not k.startswith("_")}
    root = os.path.abspath(cfg.get("root") or os.path.join(os.path.dirname(os.path.abspath(path)), ".."))
    cfg["_root"] = root
    cfg.setdefault("folder", "INBOX")
    cfg.setdefault("since_days", 14)
    cfg.setdefault("opportunities_dir", "opportunities")
    cfg.setdefault("template_dir", "opportunities/_template")
    cfg.setdefault("state_file", "inbox/state.json")
    cfg.setdefault("queue_file", "inbox/queue.jsonl")
    cfg.setdefault("max_attachment_mb", 25)
    cfg.setdefault("mark_seen", False)
    cfg.setdefault("attachment_types", DEFAULT_ATTACHMENT_TYPES)
    m = cfg.setdefault("match", {})
    m.setdefault("subject_any", DEFAULT_SUBJECT_KEYWORDS)
    m.setdefault("body_any", [])
    m.setdefault("from_allow", [])
    # from_trust = solicitation SOURCE senders (procurement portals / bid-notification services) whose
    # notification subjects lack RFP/RFQ words; filed regardless of subject. The actual addresses are
    # COMPANY config and live in inbox.json (see inbox.example.json), never here — the no-hardcoding
    # gate enforces that.
    m.setdefault("from_trust", [])
    m.setdefault("from_deny", [])
    for k in ("opportunities_dir", "template_dir", "state_file", "queue_file"):
        cfg[k] = cfg[k] if os.path.isabs(cfg[k]) else os.path.join(root, cfg[k])
    return cfg


def load_state(cfg):
    p = cfg["state_file"]
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    return {"processed": {}, "last_poll": None}


def save_state(cfg, state):
    os.makedirs(os.path.dirname(cfg["state_file"]), exist_ok=True)
    tmp = cfg["state_file"] + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    os.replace(tmp, cfg["state_file"])


def resolve_password(imap_cfg):
    env = imap_cfg.get("password_env")
    if env and os.environ.get(env):
        return os.environ[env]
    svc = imap_cfg.get("password_keychain_service")
    if svc and sys.platform == "darwin":
        try:
            out = subprocess.run(["security", "find-generic-password", "-s", svc, "-a", imap_cfg["user"], "-w"],
                                 capture_output=True, text=True, check=True)
            pw = out.stdout.strip()
            if pw:
                return pw
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    raise InboxError(f"no mailbox password: set ${env or 'password_env'} or store it in the keychain "
                     f"(security add-generic-password -s {svc or '<service>'} -a {imap_cfg.get('user')} -w)")


# ----------------------------------------------------------------------------- message parsing
def parse_message(raw_bytes):
    return email.message_from_bytes(raw_bytes, policy=email.policy.default)


def _html_to_text(s):
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", s)).strip()


def body_text(msg):
    """Best text body: text/plain preferred, else text/html converted. Also returns raw html for links."""
    plain, htmlb = None, None
    try:
        b = msg.get_body(preferencelist=("plain",))
        if b is not None: plain = b.get_content()
    except Exception:
        plain = None
    try:
        b = msg.get_body(preferencelist=("html",))
        if b is not None: htmlb = b.get_content()
    except Exception:
        htmlb = None
    text = plain if plain and plain.strip() else (_html_to_text(htmlb) if htmlb else "")
    return text.strip(), (htmlb or "")


def header(msg, name, default=""):
    v = msg.get(name)
    return str(v) if v is not None else default


def from_address(msg):
    name, addr = email.utils.parseaddr(header(msg, "From"))
    return name, addr.lower()


def received_at(msg):
    try:
        d = email.utils.parsedate_to_datetime(header(msg, "Date"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d
    except Exception:
        return dt.datetime.now(dt.timezone.utc)


def message_id(msg):
    mid = header(msg, "Message-ID").strip()
    if not mid:
        # synthesize a stable id from headers so dedupe still works
        mid = "<synth-" + re.sub(r"[^A-Za-z0-9]", "", header(msg, "Date") + header(msg, "Subject"))[:60] + ">"
    return mid


# ----------------------------------------------------------------------------- matching
def matches(msg, cfg):
    """Return (bool, reason)."""
    m = cfg["match"]
    subj = header(msg, "Subject")
    _, addr = from_address(msg)
    if m["from_deny"] and any(d.lower() in addr for d in m["from_deny"]):
        return False, f"from denied ({addr})"
    if m["from_allow"] and not any(a.lower() in addr for a in m["from_allow"]):
        return False, f"from not in allow list ({addr})"
    # Trusted solicitation-source senders (procurement portals / bid-notification services, configured
    # in inbox.json → match.from_trust) are filed regardless of subject keywords — their notification
    # subjects (e.g. "…Bidding Opportunity", "New Opportunity Found…", "Breakdown for Opportunity…")
    # don't carry RFP/RFQ words. from_deny still wins (checked above); from_allow, when set, still gates.
    if m.get("from_trust") and any(t.lower() in addr for t in m["from_trust"]):
        return True, f"trusted sender ({addr})"
    for kw in m["subject_any"]:
        if re.search(r"(?<![A-Za-z])" + re.escape(kw) + r"(?![A-Za-z])", subj, re.I):
            return True, f"subject keyword {kw!r}"
    if m["body_any"]:
        text, _ = body_text(msg)
        for kw in m["body_any"]:
            if re.search(r"(?<![A-Za-z])" + re.escape(kw) + r"(?![A-Za-z])", text, re.I):
                return True, f"body keyword {kw!r}"
    return False, "no keyword match"


# ----------------------------------------------------------------------------- derivations
def solicitation_number(subject):
    s = re.sub(r"^\s*((re|fw|fwd)\s*:\s*)+", "", subject, flags=re.I)
    for pat in SOL_NUMBER_PATTERNS:
        m = pat.search(s)
        if m:
            return normalize_ref_number(m.group(1)) or m.group(1).upper().strip("-")
    return None


def normalize_ref_number(raw, strip_label=False):
    """Clean a raw reference string into a filesystem-safe, traceable id, or None if it has no digit.
    Path-safe always (slash/space -> hyphen). With strip_label=True (body extractions), a LABEL prefix
    followed by a space or a No./#/: marker is dropped ('RFP # 10266' -> '10266'; 'RFP-26-084-CCC/DFW'
    -> '26-084-CCC-DFW'), but a label hyphenated INTO the id ('ITB-24-0087') is preserved.
    '(RFP Release)' -> None (no digit)."""
    if not raw:
        return None
    s = raw.strip().rstrip(".").strip()
    if strip_label:
        # label + explicit marker (No./Number/#/:) -> drop:  "RFP # 10266", "Solicitation No. X"
        s2 = re.sub(r"^(?:RFP|RFQ|RFI|ITB|Bid|Solicitation)\b\s*(?:No\.?|Number|#|:)\s*", "", s, flags=re.I)
        if s2 == s:
            # label + space + digit (no marker) -> drop the bare label:  "RFP 10266", "RFP-26-084" (from a paren)
            s2 = re.sub(r"^(?:RFP|RFQ|RFI|ITB|Bid|Solicitation)[\s-]+(?=\d)", "", s, flags=re.I)
        s = s2
    if not re.search(r"\d", s):        # must contain a digit to be a real number
        return None
    s = s.replace("\\", "-").replace("/", "-")     # path-unsafe separators -> hyphen
    s = re.sub(r"\s+", "-", s.strip())              # internal spaces -> hyphen
    s = re.sub(r"[^A-Za-z0-9._-]", "", s)           # keep a safe charset
    s = re.sub(r"-{2,}", "-", s).strip("-_.")
    return s.upper()[:40] or None


def solicitation_number_from_body(text):
    """Reference number from a portal/notification body (labelled lines). None if absent."""
    if not text:
        return None
    for pat in BODY_NUMBER_PATTERNS:
        m = pat.search(text)
        if m:
            num = normalize_ref_number(m.group(1), strip_label=True)
            if num:
                return num
    return None


def title_from_body(text):
    """The human title from a 'Title: …' line (WEBS-style), trimmed. None if absent."""
    if not text:
        return None
    m = BODY_TITLE_PATTERN.search(text)
    if not m:
        return None
    title = m.group(1).strip()
    # guard against a runaway match (e.g. a paragraph): titles are short
    return title if 0 < len(title) <= 120 else None


# a generic notification subject carries no opportunity identity — prefer the body for the slug
GENERIC_SUBJECTS = re.compile(r"^\s*(?:(?:re|fw|fwd)\s*:\s*)*"
                              r"(?:webs\s+)?bidding\s+opportunity|important\s+bid\s+notice|"
                              r"(?:new\s+)?opportunity(?:\s+(?:found|recommendations))?|bid\s+notice"
                              r"\b", re.I)


def _slugify(s, max_words=4, max_len=40):
    """Shared slug builder: drop a leading number token, keep meaningful words, TitleCase."""
    s = re.sub(r"^\s*((re|fw|fwd)\s*:\s*)+", "", s, flags=re.I)
    s = re.sub(r"#?\b[A-Z]{0,4}-?\d{2,4}[-_]\d{2,4}(?:-[A-Z0-9]+)?\b", " ", s)   # drop the number
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9]+", s) if w.lower() not in STOPWORDS]
    out = []
    for w in words:
        if len(out) >= max_words: break
        out.append(w if w.isupper() else w.capitalize())
    slug = "-".join(out) or "Solicitation"
    return slug[:max_len].rstrip("-")


def slug_from_subject(subject, max_words=4, max_len=40):
    return _slugify(subject, max_words, max_len)


def derive_id(msg, text=None):
    """Folder id + solicitation number. Prefers the SUBJECT, but for portal/notification emails whose
    subject is generic ("WEBS Bidding Opportunity", "Important Bid Notice") it reads the reference
    number and title out of the BODY, so folders are named by the real solicitation, not the notice."""
    subj = header(msg, "Subject")
    if text is None:
        text, _ = body_text(msg)
    num = solicitation_number(subj)
    subject_is_generic = bool(GENERIC_SUBJECTS.match(subj))
    # For generic notification subjects, or when the subject has no number, mine the body.
    if not num or subject_is_generic:
        body_num = solicitation_number_from_body(text)
        if body_num:
            num = body_num
    # Slug: a body 'Title:' wins for generic subjects; otherwise use the subject.
    slug = None
    if subject_is_generic:
        bt = title_from_body(text)
        if bt:
            slug = _slugify(bt)
    if not slug:
        slug = slug_from_subject(subj)
    if num:
        return f"{num}-{slug}", num
    d = received_at(msg).strftime("%Y%m%d")
    return f"{d}-{slug}", None


def find_existing_opportunity(opps_dir, number):
    """An existing folder whose name starts with the solicitation number (case-insensitive)."""
    if not number or not os.path.isdir(opps_dir):
        return None
    for name in sorted(os.listdir(opps_dir)):
        if name.startswith("_"): continue
        if name.upper().startswith(number.upper() + "-") or name.upper() == number.upper():
            return os.path.join(opps_dir, name)
    return None


# ----------------------------------------------------------------------------- thread dedup
def _ref_message_ids(msg):
    """Every Message-ID this message threads onto, from In-Reply-To + References (RFC-822)."""
    ids = []
    for hname in ("In-Reply-To", "References"):
        for m in re.finditer(r"<[^>]+>", header(msg, hname)):
            ids.append(m.group(0).strip())
    return ids


def normalized_subject(subj):
    """A subject stripped of threading noise so two messages on the same thread collapse to one key:
    drop leading Re:/Fwd:/[Priority!]/[External]-style prefixes (repeatable), collapse whitespace,
    lowercase. 'Re: [Priority!] Re: New Opportunity …' -> 'new opportunity …'."""
    s = subj or ""
    # strip repeated leading prefixes: Re:, Fwd:, Fw:, and any [bracketed tag] like [Priority!]/[External]
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"^\s*(?:(?:re|fw|fwd)\s*:\s*|\[[^\]]*\]\s*)", "", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip().lower()


def find_existing_by_thread(msg, state, opps_dir):
    """Find the opportunity this message is a FOLLOWUP to, when there is no solicitation number to
    match on (the sourcing-digest 'New Opportunity Found' thread problem: follow-ups with no number
    each minted a new folder). Two signals, in priority order:
      1. RFC-822 threading — In-Reply-To / References names a Message-ID we already filed; the state
         maps that id to its opportunity.
      2. Normalized-subject match — the subject, stripped of Re:/[Priority!]/… prefixes, equals the
         normalized subject of an already-processed message AND the sender domain matches (so two
         genuinely different RFPs with a generic subject don't collapse).
    Returns an absolute opportunity dir, or None. Only matches opportunities that still exist on disk."""
    processed = (state or {}).get("processed") or {}

    def _opp_path(opp_rel):
        if not opp_rel:
            return None
        p = opp_rel if os.path.isabs(opp_rel) else os.path.join(opps_dir, os.path.basename(opp_rel.rstrip("/")))
        return p if os.path.isdir(p) else None

    # 1) explicit RFC-822 threading
    for rid in _ref_message_ids(msg):
        rec = processed.get(rid)
        if rec:
            p = _opp_path(rec.get("opportunity"))
            if p:
                return p

    # 2) normalized-subject + sender-domain match against processed messages
    nsub = normalized_subject(header(msg, "Subject"))
    if not nsub:
        return None
    sender_dom = from_address(msg)[1].split("@")[-1].lower()
    for rec in processed.values():
        if normalized_subject(rec.get("subject", "")) != nsub:
            continue
        rec_dom = (rec.get("from", "") or "").split("@")[-1].lower()
        if rec_dom and sender_dom and rec_dom != sender_dom:
            continue
        p = _opp_path(rec.get("opportunity"))
        if p:
            return p
    return None


def guess_due_date(text):
    """Best-effort: a date within ~90 chars after a due/deadline cue. Returns (iso, snippet) or (None, None)."""
    best = None
    for cue in DATE_CUE.finditer(text):
        window = text[cue.start(): cue.start() + 110]
        for pat, kind in DATE_PATTERNS:
            m = pat.search(window)
            if not m: continue
            try:
                if kind == "ymd": y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                elif kind == "mdy":
                    mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    if y < 100: y += 2000
                else:
                    mo = MONTHS[m.group(1)[:3].lower()]; d = int(m.group(2)); y = int(m.group(3))
                iso = dt.date(y, mo, d).isoformat()
            except (ValueError, KeyError):
                continue
            snippet = re.sub(r"\s+", " ", window[: m.end() + 20]).strip()
            if best is None or iso < best[0]:
                best = (iso, snippet)
            break
    return best if best else (None, None)


def extract_links(text, htmlb):
    links = []
    for src in (htmlb, text):
        for u in URL_RE.findall(src or ""):
            u = u.rstrip(".,;:")
            if u not in links:
                links.append(u)
    return links


def safe_filename(name, fallback="attachment"):
    name = (name or fallback).strip().replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^\w.\- ()\[\]]+", "_", name).strip(" .")
    return name or fallback


# ----------------------------------------------------------------------------- filing
def _write(path, data, mode="w"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode, encoding=None if "b" in mode else "utf-8") as fh:
        fh.write(data)


def save_attachments(msg, dest_dir, cfg):
    saved, skipped = [], []
    allowed = {e.lower() for e in cfg["attachment_types"]}
    limit = float(cfg["max_attachment_mb"]) * 1024 * 1024
    for part in msg.iter_attachments():
        fname = safe_filename(part.get_filename(), "attachment.bin")
        ext = os.path.splitext(fname)[1].lower()
        try:
            payload = part.get_payload(decode=True) or b""
        except Exception:
            payload = b""
        if allowed and ext not in allowed:
            skipped.append((fname, "type not allowed")); continue
        if len(payload) > limit:
            skipped.append((fname, f"{len(payload)/1048576:.1f} MB > limit")); continue
        if not payload:
            skipped.append((fname, "empty")); continue
        target = os.path.join(dest_dir, fname)
        n = 1
        while os.path.exists(target):
            stem, e = os.path.splitext(fname); target = os.path.join(dest_dir, f"{stem} ({n}){e}"); n += 1
        _write(target, payload, "wb")
        saved.append(os.path.basename(target))
    return saved, skipped


def email_markdown(msg, text, links, attachments, skipped):
    name, addr = from_address(msg)
    lines = [f"# {header(msg, 'Subject')}", "",
             f"- **From:** {name} <{addr}>" if name else f"- **From:** {addr}",
             f"- **To:** {header(msg, 'To')}",
             f"- **Date:** {header(msg, 'Date')}",
             f"- **Message-ID:** `{message_id(msg)}`", ""]
    if attachments:
        lines += ["## Attachments (saved to attachments/)"] + [f"- {a}" for a in attachments] + [""]
    if skipped:
        lines += ["## Attachments skipped"] + [f"- {a} — {why}" for a, why in skipped] + [""]
    if links:
        lines += ["## Links (portal links usually require login — fetch manually into rfp/)"] + [f"- {u}" for u in links] + [""]
    lines += ["## Body", "", text or "_(no text body)_", ""]
    return "\n".join(lines)


def fill_template_json(template_path, dest_path, values):
    txt = open(template_path, encoding="utf-8").read()
    for k, v in values.items():
        txt = txt.replace("{{" + k + "}}", json.dumps(v)[1:-1])   # JSON-escape the value
    txt = re.sub(r"\{\{[A-Z_]+\}\}", "", txt)                       # any leftover placeholder -> ""
    json.loads(txt)
    _write(dest_path, txt)


def intake_brief(oid, msg, text, due, links, attachments, opp_rel, kind, existing_rel=None):
    name, addr = from_address(msg)
    due_iso, due_snip = due
    lines = [f"# Intake brief — {oid}", "",
             f"_Generated by bidkit.inbox from an email received {received_at(msg).isoformat()}. "
             f"Everything below is extracted or guessed from the email only; nothing has been verified against a solicitation document._", "",
             f"- **Kind:** {'NEW opportunity' if kind == 'new' else 'FOLLOW-UP to existing opportunity ' + (existing_rel or '')}",
             f"- **Subject:** {header(msg, 'Subject')}",
             f"- **From:** {name} <{addr}>",
             f"- **Due date (GUESS from email text — confirm in the RFP):** {due_iso or 'not found'}"
             + (f"  — _\"{due_snip}\"_" if due_snip else ""),
             f"- **Attachments saved:** {len(attachments)}" + (f" — {', '.join(attachments)}" if attachments else ""),
             f"- **Links found:** {len(links)}" + ("  (see initial-email/links.md; portal links usually need a login)" if links else ""),
             "", "## Next step", "",
             f"Open Kiro in this repo and say: **\"run intake on {opp_rel}\"** — the `bid-intake` steering will "
             "read the solicitation and all addenda, build the timeline, identify format and evaluation rules, "
             "and produce the intake return package. Before that:", "",
             "1. Download the solicitation and every attachment/addendum from the portal into `rfp/` (links above).",
             "2. If a bid-development partner forwarded this, put their checklist in `initial-email/attachments/`.",
             "3. Confirm the due date and time zone from the RFP itself, then set `due` in `opportunity.json`.",
             "", "## Email body (first 60 lines)", "", "```",
             *text.splitlines()[:60], "```", ""]
    return "\n".join(lines)


def process_message(msg, cfg, state, dry_run=False, now=None):
    """File one message. Returns a result dict (also appended to the queue unless dry_run)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    mid = message_id(msg)
    res = {"message_id": mid, "subject": header(msg, "Subject"), "from": from_address(msg)[1],
           "received": received_at(msg).isoformat(), "processed_at": now.isoformat()}
    if mid in state["processed"]:
        res.update(action="skip", reason="already processed", opportunity=state["processed"][mid].get("opportunity"))
        return res
    ok, why = matches(msg, cfg)
    if not ok:
        res.update(action="ignore", reason=why)
        return res
    text, htmlb = body_text(msg)
    oid, number = derive_id(msg, text)
    links = extract_links(text, htmlb)
    due = guess_due_date(text)
    opps = cfg["opportunities_dir"]
    existing = find_existing_opportunity(opps, number)
    # When there's no solicitation number to match on, fall back to THREAD dedup (RFC-822
    # In-Reply-To/References, or a normalized-subject + sender-domain match) so a follow-up on an
    # existing opportunity attaches as a followup instead of minting a duplicate folder.
    if not existing and cfg.get("thread_dedup", True):
        existing = find_existing_by_thread(msg, state, opps)
    root = cfg["_root"]

    if existing:
        kind = "followup"
        opp_dir = existing
        stamp = received_at(msg).strftime("%Y%m%d-%H%M")
        short = re.sub(r"[^A-Za-z0-9]", "", mid)[-8:]
        sub_dir = os.path.join(opp_dir, "initial-email", "followups", f"{stamp}-{short}")
        att_dir = os.path.join(sub_dir, "attachments")
    else:
        kind = "new"
        opp_dir = os.path.join(opps, oid)
        sub_dir = os.path.join(opp_dir, "initial-email")
        att_dir = os.path.join(sub_dir, "attachments")

    opp_rel = os.path.relpath(opp_dir, root)
    res.update(action=kind, reason=why, opportunity=opp_rel, solicitation_number=number,
               due_guess=due[0], links=len(links))
    if dry_run:
        res["would_write"] = os.path.relpath(sub_dir, root)
        res["attachments"] = [safe_filename(p.get_filename(), "attachment.bin") for p in msg.iter_attachments()]
        return res

    if kind == "new":
        if os.path.isdir(cfg["template_dir"]):
            shutil.copytree(cfg["template_dir"], opp_dir, dirs_exist_ok=True)
            tmpl_json = os.path.join(cfg["template_dir"], "opportunity.json")
            if os.path.exists(tmpl_json):
                name, addr = from_address(msg)
                # Values we GUESS are tagged with a bidkit.* source so bidkit.brief may refresh them once the
                # RFP is read; a human editing them (or setting confirmed: true) removes them from our control.
                fill_template_json(tmpl_json, os.path.join(opp_dir, "opportunity.json"), {
                    "ID": oid, "AGENCY": name or addr.split("@")[-1], "AGENCY_SOURCE": "bidkit.inbox (sender name — GUESS)",
                    "TITLE": header(msg, "Subject"), "NUMBER": number or "",
                    "SOURCE_TYPE": "email", "RECEIVED": received_at(msg).isoformat(), "FROM": addr,
                    "MESSAGE_ID": mid, "DUE_DATE": due[0] or "", "DUE_SOURCE": "bidkit.inbox (email text — GUESS)" if due[0] else ""})
        else:
            os.makedirs(opp_dir, exist_ok=True)
    os.makedirs(att_dir, exist_ok=True)
    saved, skipped = save_attachments(msg, att_dir, cfg)
    _write(os.path.join(sub_dir, "email.eml"), msg.as_bytes(), "wb")
    _write(os.path.join(sub_dir, "email.md"), email_markdown(msg, text, links, saved, skipped))
    if links:
        _write(os.path.join(sub_dir, "links.md"), "# Links from the email\n\n" + "\n".join(f"- {u}" for u in links) + "\n")
    brief_name = "intake-brief.md" if kind == "new" else f"followup-brief-{os.path.basename(sub_dir)}.md"
    _write(os.path.join(opp_dir, brief_name),
           intake_brief(oid if kind == "new" else os.path.basename(opp_dir), msg, text, due, links, saved, opp_rel,
                        kind, existing_rel=opp_rel))
    res.update(attachments=saved, attachments_skipped=[f"{a} ({w})" for a, w in skipped],
               written=os.path.relpath(sub_dir, root), brief=os.path.join(opp_rel, brief_name))
    # record subject + sender so thread dedup (find_existing_by_thread) can match a later follow-up
    # that carries no solicitation number by its normalized subject + sender domain.
    state["processed"][mid] = {"opportunity": opp_rel, "kind": kind, "when": now.isoformat(),
                               "subject": header(msg, "Subject"), "from": from_address(msg)[1]}
    os.makedirs(os.path.dirname(cfg["queue_file"]), exist_ok=True)
    with open(cfg["queue_file"], "a", encoding="utf-8") as fh:
        fh.write(json.dumps(res) + "\n")
    return res


# ----------------------------------------------------------------------------- fetchers
def make_fetcher(cfg):
    """Build the MailFetcher named by cfg["source"]["type"]: "imap" (default; needs cfg["imap"])
    or "gmail_api" (Gmail REST + OAuth; needs cfg["gmail_api"]). Protocol: mail_imap.py docstring."""
    kind = (cfg.get("source") or {}).get("type") or ("gmail_api" if "gmail_api" in cfg and "imap" not in cfg else "imap")
    if kind == "imap":
        from .mail_imap import ImapFetcher
        if "imap" not in cfg:
            raise InboxError("source.type is imap but no 'imap' block in config")
        return ImapFetcher(cfg["imap"], cfg.get("folder", "INBOX"))
    if kind == "gmail_api":
        from .mail_gmail import GmailFetcher
        if "gmail_api" not in cfg:
            raise InboxError("source.type is gmail_api but no 'gmail_api' block in config")
        return GmailFetcher(cfg["gmail_api"])
    raise InboxError(f"unknown source.type {kind!r} (expected imap or gmail_api)")


def poll(cfg, dry_run=False, since_days=None, fetcher_factory=None):
    """Poll the mailbox and process every new message. fetcher_factory(cfg) -> context manager
    with uids_since()/fetch()/mark_seen() — injectable for tests."""
    state = load_state(cfg)
    factory = fetcher_factory or make_fetcher
    results = []
    with factory(cfg) as f:
        uids = f.uids_since(since_days if since_days is not None else cfg["since_days"])
        for uid in uids:
            msg = f.fetch(uid)
            if msg is None: continue
            r = process_message(msg, cfg, state, dry_run=dry_run)
            r["uid"] = uid
            results.append(r)
            if not dry_run and cfg.get("mark_seen") and r["action"] in ("new", "followup"):
                try: f.mark_seen(uid)
                except Exception as e: r["mark_seen_error"] = str(e)
    if not dry_run:
        state["last_poll"] = dt.datetime.now(dt.timezone.utc).isoformat()
        save_state(cfg, state)
    return results


def ingest_files(cfg, paths, dry_run=False):
    state = load_state(cfg)
    results = []
    for p in paths:
        with open(p, "rb") as fh:
            msg = parse_message(fh.read())
        r = process_message(msg, cfg, state, dry_run=dry_run); r["file"] = p
        results.append(r)
    if not dry_run:
        save_state(cfg, state)
    return results


def print_results(results):
    counts = {}
    for r in results:
        counts[r["action"]] = counts.get(r["action"], 0) + 1
        tag = {"new": "NEW     ", "followup": "FOLLOWUP", "skip": "skip    ", "ignore": "ignore  "}[r["action"]]
        extra = ""
        if r["action"] in ("new", "followup"):
            extra = f" -> {r.get('opportunity')}" + (f"  due≈{r['due_guess']}" if r.get("due_guess") else "") \
                    + (f"  att={len(r.get('attachments', []))}" if "attachments" in r else "") \
                    + ("  [DRY RUN]" if "would_write" in r else "")
        elif r["action"] == "skip":
            extra = f" ({r.get('opportunity')})"
        print(f"{tag} {r['subject'][:70]!r}{extra}")
    print("summary:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "no messages")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("poll", help="poll the IMAP mailbox"); p.add_argument("--cfg", required=True)
    p.add_argument("--dry-run", action="store_true"); p.add_argument("--since-days", type=int)
    p = sub.add_parser("ingest", help="process local .eml files"); p.add_argument("--cfg", required=True)
    p.add_argument("files", nargs="+"); p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("queue", help="show the processed queue"); p.add_argument("--cfg", required=True)
    p.add_argument("--all", action="store_true", help="include skips/ignores")
    p = sub.add_parser("status", help="state summary"); p.add_argument("--cfg", required=True)
    a = ap.parse_args(argv)
    cfg = load_config(a.cfg)
    try:
        if a.cmd == "poll":
            print_results(poll(cfg, dry_run=a.dry_run, since_days=a.since_days)); return 0
        if a.cmd == "ingest":
            print_results(ingest_files(cfg, a.files, dry_run=a.dry_run)); return 0
        if a.cmd == "queue":
            if not os.path.exists(cfg["queue_file"]):
                print("queue empty"); return 0
            with open(cfg["queue_file"], encoding="utf-8") as fh:
                rows = [json.loads(l) for l in fh if l.strip()]
            for r in rows:
                if a.all or r["action"] in ("new", "followup"):
                    print(f"{r['processed_at'][:16]}  {r['action']:8s} {r.get('opportunity','')}  {r['subject'][:60]!r}")
            return 0
        if a.cmd == "status":
            st = load_state(cfg)
            kind = (cfg.get("source") or {}).get("type", "imap")
            who = cfg.get("imap", {}).get("user") if kind == "imap" else cfg.get("gmail_api", {}).get("user", "me")
            print(f"root: {cfg['_root']}\nsource: {kind}  mailbox: {who or '(not set)'} / {cfg['folder']}")
            print(f"last poll: {st.get('last_poll')}\nprocessed messages: {len(st['processed'])}")
            return 0
    except (InboxError, MailError) as e:
        print(f"INBOX ERROR: {e}"); return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
