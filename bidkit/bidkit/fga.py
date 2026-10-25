#!/usr/bin/env python3
"""
fga.py — SOURCING harness for the Federal Government Advisors portal (portal.federalgovadvisors.com).

Different job from bidkit.portal: not "fetch the documents of one known solicitation" but "which open
opportunities match our NAICS / PSC codes, which of them are new since the last run, and file the ones
worth pursuing". Different UI too — an Angular single-page app — so this harness does NOT drive the
"Add Filters" panel with a browser. The panel is a thin form over a JSON API, and the app's own
service class (buildOpportunitiesParams, read from the shipped bundle) documents the contract exactly,
so the harness sends the same request the Apply button would, with every code in the criteria file:

  GET  {api}/opportunities/?page=&page_size=100&source_type_filter=opportunities
         &naics_code_id=<uuid>&naics_code_id=…        (repeated = OR within a kind)
         &psc_code_id=<uuid>…                         (NAICS and PSC are ANDed by the server →
                                                       the harness runs one search per kind and unions)
         [&active_only=true] [&only_federal=true | &only_state_and_local=true] [&q=keywords]
         [&posted_date_after=YYYY-MM-DD] [&due_date_after=…] [&set_aside_id=…] [&opp_type_id=…] [&ordering=…]
  GET  {api}/business-profile/naics-codes/?q=54151   → {results:[{id, naics_code, industry_title}]}  (q = contains)
  GET  {api}/business-profile/psc-codes/?q=D30       → {results:[{id, psc_code, psc_name}]}
  GET  {api}/opportunities/<id>/                      full record; documents[] carry pre-signed download_url
  GET  {api}/opportunities/<id>/fetch-documents/      refreshed document list
  POST {api}/auth/login/ {email,password} → {user, accessToken, refreshToken};  POST {api}/auth/refresh/ {refresh}
  Bearer JWT access token (~15 h) + refresh token (~1 year) — the browser keeps them as cookies
  accessToken / refreshToken on portal.federalgovadvisors.com; the harness keeps them in a 0600 token
  file outside the repo and refreshes them itself. Deep link for humans:
  {portal}/opportunities/view/<id>?tab=opportunities

Company data (the codes) lives in a CRITERIA FILE passed with --criteria — never in this module:
  {"naics": [...], "psc": [...], "vary_last_digits": 1, "active_only": true, "scope": "all|federal|state_and_local",
   "exclude_opportunity_types": [...], "min_days_to_due": 3, "keywords": ""}
vary_last_digits=1 widens every seed code to all codes the portal knows that share every digit but the
last (54151x, D30x); the expansion is resolved against the portal's own lookup, so only real codes are sent.

CLI:
  python3 -m bidkit.fga login  --portals inbox/portals.json [--from-browser | --auto]
        --from-browser: import the tokens from the Playwright profile bootstrapped by
                        `python3 -m bidkit.portal login federalgovadvisors.com` (headed, human types the password)
        --auto:         API login with stored credentials (portals.json username + password_env / keychain)
  python3 -m bidkit.fga codes  --criteria <file> --portals …            # the expanded code set and the portal's ids (the "filter", as data)
  python3 -m bidkit.fga search --criteria <file> --portals … --out opportunities/sourcing/fga [--state inbox/fga-seen.json] [--all]
        → <out>/report-<date>.md (NEW since last run first), <out>/latest.json, <out>/latest.csv; seen-state updated
  python3 -m bidkit.fga profile --criteria <file> --portals … [--apply] [--replace]
        → widen the portal's BUSINESS PROFILE code lists (what its recommendations / alert emails key on) to the
          expanded criteria: dry run prints the additions; --apply PATCHes (multipart, JSON-encoded id lists — the
          profile editor's own encoding) after backing up the profile JSON outside the repo, then re-reads to verify
  python3 -m bidkit.fga file   <opportunity-id> --portals … [--out opportunities] [--no-docs] [--brief]
        → opportunities/<number>-<slug>/ with opportunity.json, rfp/portal-record.json (same shape bidkit.brief reads
          for WEBS), rfp/<documents>, sourcing/fga-record.md; --brief runs bidkit.brief + calendar afterwards
Nothing here is confirmed: dates, values and set-asides are the portal's data (DETECTED); the human confirms
from the solicitation itself.
"""
import argparse, csv, datetime as dt, json, os, re, shutil, sys, time, urllib.error, urllib.parse, urllib.request

DEFAULT_API = "https://services.federalgovadvisors.com/api/"
DEFAULT_PORTAL = "https://portal.federalgovadvisors.com"
DEFAULT_TOKEN_FILE = "~/.config/bidkit/fga-tokens.json"
PORTAL_KEY = "federalgovadvisors.com"
PAGE_SIZE = 100                                   # the server caps page_size at 100 (verified)
CODE_KINDS = {                                    # kind → (lookup path, code field, title field, full code length)
    "naics": ("business-profile/naics-codes/", "naics_code", "industry_title", 6),
    "psc": ("business-profile/psc-codes/", "psc_code", "psc_name", 4),
}


class FgaError(Exception):
    pass


class FgaAuthError(FgaError):
    pass


# ----------------------------------------------------------------------------- HTTP (stdlib; injectable for tests)
def _urllib_http(method, url, headers, body=None, timeout=60):
    """(status, headers_dict, bytes). Never raises on HTTP errors — the caller decides."""
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read() if e.fp else b""
    except urllib.error.URLError as e:
        raise FgaError(f"network error for {url}: {e.reason}")


class FgaClient:
    """Authenticated JSON client. Tokens live in token_file (0600, outside the repo). On 401 the client
    refreshes once; if the refresh token is dead it logs in with stored credentials when they exist,
    otherwise raises FgaAuthError with the remedy."""

    def __init__(self, spec=None, token_file=None, http=None, credentials=None):
        self.spec = spec or {}
        self.api = (self.spec.get("api_url") or DEFAULT_API).rstrip("/") + "/"
        self.portal = (self.spec.get("portal_url") or DEFAULT_PORTAL).rstrip("/")
        self.token_file = os.path.expanduser(token_file or self.spec.get("token_file") or DEFAULT_TOKEN_FILE)
        self.http = http or _urllib_http
        self._credentials = credentials              # callable → (user, pw) | None ; default reads portals.json + secret store
        self.tokens = self._load_tokens()

    # ---- tokens
    def _load_tokens(self):
        try:
            with open(self.token_file, encoding="utf-8") as fh:
                t = json.load(fh)
            return t if isinstance(t, dict) else {}
        except Exception:
            return {}

    def save_tokens(self, access=None, refresh=None, user=None):
        t = dict(self.tokens)
        if access: t["accessToken"] = access
        if refresh: t["refreshToken"] = refresh
        if user is not None: t["user"] = {k: user.get(k) for k in ("id", "firstName", "lastName", "email") if isinstance(user, dict)}
        t["saved_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        os.makedirs(os.path.dirname(self.token_file), exist_ok=True)
        with open(self.token_file, "w", encoding="utf-8") as fh:
            json.dump(t, fh, indent=2)
        os.chmod(self.token_file, 0o600)
        self.tokens = t
        return t

    @staticmethod
    def jwt_expiry(token):
        """UTC datetime the JWT expires, or None."""
        try:
            import base64
            payload = token.split(".")[1]
            data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            return dt.datetime.fromtimestamp(int(data["exp"]), dt.timezone.utc)
        except Exception:
            return None

    def import_browser_tokens(self, profile_dir):
        """Bootstrap from the Playwright profile's storage_state.json (written by bidkit.portal on close):
        the portal keeps accessToken / refreshToken as cookies. No password involved."""
        p = os.path.join(os.path.expanduser(profile_dir), "storage_state.json")
        if not os.path.exists(p):
            raise FgaAuthError(f"no browser state at {p} — run: python3 -m bidkit.portal login {PORTAL_KEY}  (headed) first")
        with open(p, encoding="utf-8") as fh:
            cookies = {c["name"]: c["value"] for c in json.load(fh).get("cookies", [])}
        if not cookies.get("refreshToken"):
            raise FgaAuthError(f"browser state at {p} has no refreshToken cookie — log in again in the headed window")
        return self.save_tokens(access=cookies.get("accessToken"), refresh=cookies["refreshToken"])

    def login(self, email, password):
        status, data = self._json("POST", "auth/login/", body={"email": email, "password": password}, auth=False)
        if status != 200 or not isinstance(data, dict) or not data.get("accessToken"):
            raise FgaAuthError(f"login failed (HTTP {status}): {self._err(data)}")
        self.save_tokens(access=data["accessToken"], refresh=data.get("refreshToken"), user=data.get("user"))
        return data.get("user") or {}

    def refresh(self):
        rt = self.tokens.get("refreshToken")
        if not rt:
            return False
        status, data = self._json("POST", "auth/refresh/", body={"refresh": rt}, auth=False)
        if status != 200 or not isinstance(data, dict) or not data.get("accessToken"):
            return False
        self.save_tokens(access=data["accessToken"], refresh=data.get("refreshToken") or rt)
        return True

    def _credentials_or_none(self):
        if self._credentials is not None:
            return self._credentials()
        try:
            from .portal import resolve_credentials
            user, pw = resolve_credentials(self.spec)
            return (user, pw) if user and pw else None
        except Exception:
            return None

    def ensure_auth(self):
        """Make sure we hold a usable access token; refresh / re-login as needed."""
        exp = self.jwt_expiry(self.tokens.get("accessToken", ""))
        if exp and exp > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2):
            return
        if self.refresh():
            return
        creds = self._credentials_or_none()
        if creds:
            self.login(*creds); return
        raise FgaAuthError("not logged in to FGA (no valid token, refresh failed) — run: python3 -m bidkit.fga login --from-browser "
                           "(after a headed `python3 -m bidkit.portal login federalgovadvisors.com`) or --auto with stored credentials")

    # ---- requests
    @staticmethod
    def _err(data):
        if isinstance(data, dict):
            return data.get("detail") or data.get("message") or json.dumps(data)[:200]
        return str(data)[:200]

    def _json(self, method, path, params=None, body=None, auth=True):
        url = path if path.startswith("http") else self.api + path.lstrip("/")
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
        headers = {"Accept": "application/json", "User-Agent": "bidkit-fga/1.0"}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8"); headers["Content-Type"] = "application/json"
        if auth:
            headers["Authorization"] = f"Bearer {self.tokens.get('accessToken', '')}"
        status, _, raw = self.http(method, url, headers, data)
        try:
            parsed = json.loads(raw.decode("utf-8")) if raw else None
        except Exception:
            parsed = raw.decode("utf-8", "replace")[:500]
        return status, parsed

    def get(self, path, params=None, _retry=True):
        self.ensure_auth()
        status, data = self._json("GET", path, params=params)
        if status == 401 and _retry:
            if not self.refresh():
                creds = self._credentials_or_none()
                if not creds:
                    raise FgaAuthError("FGA rejected the token and the refresh failed — run: python3 -m bidkit.fga login --from-browser")
                self.login(*creds)
            return self.get(path, params=params, _retry=False)
        if status != 200:
            raise FgaError(f"HTTP {status} for {path}: {self._err(data)}")
        return data

    def paginate(self, path, params, limit=None):
        """Every result across pages (follows `next`)."""
        out, page = [], 1
        params = dict(params or {}); params.setdefault("page_size", PAGE_SIZE)
        url = path
        while url:
            data = self.get(url, params=params if page == 1 else None)
            out += data.get("results") or []
            url = data.get("next"); page += 1
            if limit and len(out) >= limit:
                break
        return out

    # ---- domain calls
    def lookup_codes(self, kind, q):
        path, code_f, title_f, _ = CODE_KINDS[kind]
        data = self.get(path, params={"q": q})
        return [{"code": r.get(code_f), "id": r.get("id"), "title": r.get(title_f) or ""} for r in (data.get("results") or [])]

    def expand_codes(self, kind, codes, vary_last_digits=1):
        """Every full-length code the portal knows that shares all but the last `vary_last_digits`
        digits with a seed code (vary_last_digits=0 → the seed codes themselves). Returns
        [{code, id, title, seed}] sorted by code, each code once."""
        _, _, _, full = CODE_KINDS[kind]
        found = {}
        for seed in codes:
            seed = str(seed).strip().upper()
            if not seed:
                continue
            prefix = seed[:max(1, len(seed) - int(vary_last_digits))] if vary_last_digits else seed
            for r in self.lookup_codes(kind, prefix):
                code = (r["code"] or "").upper()
                if len(code) == full and code.startswith(prefix) and r["id"] and code not in found:
                    found[code] = dict(r, code=code, seed=seed)
        return [found[c] for c in sorted(found)]

    def search(self, params, limit=None):
        p = {"source_type_filter": "opportunities", "page_size": PAGE_SIZE}
        p.update(params or {})
        return self.paginate("opportunities/", p, limit=limit)

    def opportunity(self, opp_id):
        return self.get(f"opportunities/{opp_id}/")

    def documents(self, opp_id):
        data = self.get(f"opportunities/{opp_id}/fetch-documents/")
        return data if isinstance(data, list) else (data or {}).get("results") or []

    def download(self, url):
        """Documents come from pre-signed object-storage URLs: plain GET, no bearer token."""
        status, headers, raw = self.http("GET", url, {"User-Agent": "bidkit-fga/1.0"}, None)
        if status != 200:
            raise FgaError(f"HTTP {status} downloading {url[:80]}…")
        return raw, headers.get("content-type", "")

    def business_profile(self):
        return self.get("business-profile/")

    def patch_multipart(self, path, fields, _retry=True):
        """PATCH with multipart/form-data — the encoding the portal's own profile editor uses
        (its FormData carries JSON-encoded lists in text fields). fields: {name: str}."""
        self.ensure_auth()
        boundary = "----bidkit" + hex(int(time.time() * 1000))[2:]
        parts = []
        for name, value in fields.items():
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n")
        body = ("".join(parts) + f"--{boundary}--\r\n").encode("utf-8")
        url = self.api + path.lstrip("/")
        headers = {"Accept": "application/json", "User-Agent": "bidkit-fga/1.0", "Content-Type": f"multipart/form-data; boundary={boundary}",
                   "Authorization": f"Bearer {self.tokens.get('accessToken', '')}"}
        status, _, raw = self.http("PATCH", url, headers, body)
        try:
            data = json.loads(raw.decode("utf-8")) if raw else None
        except Exception:
            data = raw.decode("utf-8", "replace")[:500]
        if status == 401 and _retry and self.refresh():
            return self.patch_multipart(path, fields, _retry=False)
        if status not in (200, 202):
            raise FgaError(f"HTTP {status} for PATCH {path}: {self._err(data)}")
        return data


def profile_code_plan(profile, flt, replace=False):
    """What the business profile's NAICS / PSC lists would become: the union of what is there and the
    expanded criteria (replace=True → the expanded criteria only). Returns
    {kind: {"current": [codes], "add": [codes], "remove": [codes], "ids": [ids to send]}}."""
    plan = {}
    for kind, (field, code_f) in {"naics": ("naics_codes", "naics_code"), "psc": ("psc_codes", "psc_code")}.items():
        current = {(x.get(code_f) or "").upper(): x.get("id") for x in (profile.get(field) or []) if x.get("id")}
        wanted = {c["code"]: c["id"] for c in (flt.get(kind) or [])}
        final = dict(wanted) if replace else {**current, **wanted}
        plan[kind] = {"current": sorted(current), "add": sorted(set(final) - set(current)), "remove": sorted(set(current) - set(final)),
                      "ids": [final[c] for c in sorted(final)], "codes": sorted(final)}
    return plan


def sync_business_profile(client, criteria, apply=False, replace=False, backup_dir=None, when=None):
    """Widen the portal's business profile (what its recommendations / alerts key on) to the criteria's
    expanded code set. Dry run unless apply=True. Backs up the current profile JSON first (outside the
    repo — it holds contact details). Returns (plan, backup_path, result_profile_or_None)."""
    when = when or dt.datetime.now(dt.timezone.utc)
    profile = client.business_profile()
    flt = resolve_filter(client, criteria)
    plan = profile_code_plan(profile, flt, replace=replace)
    backup = None
    if apply:
        bdir = os.path.expanduser(backup_dir or os.path.dirname(client.token_file))
        os.makedirs(bdir, exist_ok=True)
        backup = os.path.join(bdir, f"fga-business-profile-backup-{when.strftime('%Y%m%d-%H%M%S')}.json")
        with open(backup, "w", encoding="utf-8") as fh:
            json.dump(profile, fh, indent=1, ensure_ascii=False)
        os.chmod(backup, 0o600)
        top = [x.get("id") if isinstance(x, dict) else x for x in (profile.get("top_naics_codes") or []) if x]
        fields = {"naics_codes": json.dumps(plan["naics"]["ids"]), "psc_codes": json.dumps(plan["psc"]["ids"]),
                  "top_naics_codes": json.dumps(top)}                 # sent unchanged, as the editor does
        result = client.patch_multipart("business-profile/", fields)
        after = client.business_profile()                          # verify from a fresh read, not the PATCH echo
        got = {"naics": sorted((x.get("naics_code") or "").upper() for x in after.get("naics_codes") or []),
               "psc": sorted((x.get("psc_code") or "").upper() for x in after.get("psc_codes") or [])}
        for kind in ("naics", "psc"):
            missing = sorted(set(plan[kind]["codes"]) - set(got[kind]))
            if missing:
                raise FgaError(f"profile update verified INCOMPLETE — {kind.upper()} codes not present after PATCH: {missing} (backup: {backup})")
        return plan, backup, after
    return plan, backup, None


# ----------------------------------------------------------------------------- criteria → query
def load_criteria(path):
    with open(path, encoding="utf-8") as fh:
        c = json.load(fh)
    return {k: v for k, v in c.items() if not k.startswith("_")}


def resolve_filter(client, criteria):
    """The 'Add Filters' panel as data: expanded NAICS and PSC code sets with the portal's ids."""
    vary = int(criteria.get("vary_last_digits", 1))
    return {kind: client.expand_codes(kind, criteria.get(kind) or [], vary) for kind in CODE_KINDS if criteria.get(kind)}


def base_params(criteria, since=None):
    p = {"source_type_filter": criteria.get("source_type_filter") or "opportunities"}
    if criteria.get("active_only", True):
        p["active_only"] = "true"
    scope = (criteria.get("scope") or "all").lower()
    if scope in ("federal", "only_federal"):
        p["only_federal"] = "true"
    elif scope in ("state_and_local", "sled", "only_state_and_local"):
        p["only_state_and_local"] = "true"
    if criteria.get("keywords"):
        p["q"] = criteria["keywords"]
    if since:
        p["posted_date_after"] = since if isinstance(since, str) else since.isoformat()
    p["ordering"] = criteria.get("ordering") or "due_date"
    return p


def run_search(client, criteria, since=None, limit=None):
    """One search per code kind (the server ANDs kinds), unioned by opportunity id with the codes that
    matched each record. Returns (records, filter_used)."""
    flt = resolve_filter(client, criteria)
    by_id = {}
    for kind, codes in flt.items():
        if not codes:
            continue
        params = base_params(criteria, since)
        params[f"{kind}_code_id"] = [c["id"] for c in codes]
        for rec in client.search(params, limit=limit):
            e = by_id.setdefault(rec["id"], {"record": rec, "matched_by": []})
            code = (rec.get(kind) or "").upper()
            e["matched_by"].append(f"{kind}:{code}" if code else kind)
    return list(by_id.values()), flt


def normalize(rec, portal_url=DEFAULT_PORTAL, matched_by=None):
    """Flat, report-ready view of a portal record. Money is FGA's estimate, not the agency's."""
    def money(v):
        try:
            return float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None
    c = rec.get("primary_contact") or {}
    low, high = money(rec.get("val_est_low")), money(rec.get("val_est_high"))
    return {
        "id": rec.get("id"), "source_id": rec.get("source_id"), "source_type": rec.get("source_type"),
        "title": (rec.get("title") or "").strip(), "agency": rec.get("agency_name") or "", "agency_abbr": rec.get("agency_abbreviation") or "",
        "opp_type": rec.get("opp_type_description") or "", "set_aside": rec.get("set_aside") or "",
        "naics": rec.get("naics") or "", "psc": rec.get("psc") or "",
        "posted": rec.get("posted_date"), "due": rec.get("due_date"),
        "value_low": low, "value_high": high,
        "pop": ", ".join(x for x in (rec.get("pop_city"), rec.get("pop_state")) if x),
        "url": f"{portal_url}/opportunities/view/{rec.get('id')}?tab=opportunities",
        "source_url": rec.get("source_path") or "", "aggregator_url": rec.get("path") or "",
        "documents": len(rec.get("documents") or []),
        "contact": {"name": c.get("contact_name"), "email": c.get("contact_email"), "phone": c.get("contact_phone"), "title": c.get("contact_title")},
        "matched_by": sorted(set(matched_by or [])),
        "summary": (rec.get("ai_summary") or rec.get("description_text") or "")[:600].strip(),
    }


def apply_screens(rows, criteria, today=None):
    """Post-filters the portal can't do, all driven by the criteria file: drop excluded opportunity
    types, set-aside categories the company cannot bid, titles matching exclusion patterns (sole-source
    notices…), and anything closing sooner than min_days_to_due. Each dropped row is counted by reason
    in the returned stats so the report can say what was screened out."""
    today = today or dt.date.today()
    excl_types = {t.strip().lower() for t in (criteria.get("exclude_opportunity_types") or [])}
    excl_sa = {t.strip().upper() for t in (criteria.get("exclude_set_asides") or [])}
    pats = [re.compile(p, re.I) for p in (criteria.get("exclude_title_patterns") or [])]
    # Resale screen: drop a title matching ANY resale_title_patterns UNLESS it also matches a
    # keep_title_pattern (dev/custom/implementation/support signal). Both come from the criteria file
    # and default to empty (opt-in; nothing resale-specific is baked into the library).
    resale_pats = [re.compile(p, re.I) for p in (criteria.get("resale_title_patterns") or [])]
    keep_pats = [re.compile(p, re.I) for p in (criteria.get("keep_title_patterns") or [])]
    min_days = int(criteria.get("min_days_to_due", 0) or 0)
    out, dropped = [], {}
    def drop(reason):
        dropped[reason] = dropped.get(reason, 0) + 1
    for r in rows:
        if r["opp_type"].strip().lower() in excl_types:
            drop(f"type: {r['opp_type']}"); continue
        if r["set_aside"].strip().upper() in excl_sa:
            drop(f"set-aside: {r['set_aside']}"); continue
        if any(p.search(r["title"]) for p in pats):
            drop("title pattern"); continue
        if resale_pats and any(p.search(r["title"]) for p in resale_pats) \
                and not any(p.search(r["title"]) for p in keep_pats):
            drop("resale/COTS renewal"); continue
        if min_days and r.get("due"):
            try:
                if (dt.date.fromisoformat(r["due"]) - today).days < min_days:
                    drop(f"closes in < {min_days} days"); continue
            except ValueError:
                pass
        out.append(r)
    return out, dropped


# ----------------------------------------------------------------------------- state + report
def load_state(path):
    try:
        with open(path, encoding="utf-8") as fh:
            s = json.load(fh)
        return s if isinstance(s, dict) else {"seen": {}}
    except Exception:
        return {"seen": {}}


def save_state(path, state):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1)


def fmt_money(low, high):
    if low is None and high is None:
        return ""
    if low is not None and high is not None and low != high:
        return f"${low:,.0f}–${high:,.0f}"
    return f"${(high if high is not None else low):,.0f}"


def _row(r):
    title = r["title"].replace("|", "/")[:90]
    return (f"| {r['due'] or ''} | [{title}]({r['url']}) | {r['agency'][:40]} | {r['opp_type']} | {r['set_aside']} | "
            f"{r['naics']} | {r['psc']} | {fmt_money(r['value_low'], r['value_high'])} | {', '.join(m.split(':')[1] for m in r['matched_by'] if ':' in m)} |")


HEADER = "| Due | Title | Agency | Type | Set-aside | NAICS | PSC | FGA est. value | Matched |\n|---|---|---|---|---|---|---|---|---|"


def write_report(out_dir, rows, new_ids, flt, criteria, state_path, when=None, dropped=None):
    when = when or dt.datetime.now()
    os.makedirs(out_dir, exist_ok=True)
    stamp = when.strftime("%Y-%m-%d")
    rows = sorted(rows, key=lambda r: (r["due"] or "9999", r["title"]))
    new = [r for r in rows if r["id"] in new_ids]
    L = [f"# FGA sourcing — {stamp}", "",
         f"_{len(rows)} open match(es) for the criteria; **{len(new)} new** since the last run (state: `{state_path}`). "
         f"Everything here is the portal's data (DETECTED): confirm dates, set-asides and scope in the solicitation. "
         f"Value = FGA's estimate, not the agency's. Deep links open the FGA portal (login)._", "",
         "## Filter applied (codes resolved against the portal)", ""]
    for kind, codes in flt.items():
        seeds = sorted({c['seed'] for c in codes})
        L.append(f"- **{kind.upper()}** from seeds {', '.join(seeds)} → " + ", ".join(f"{c['code']}" for c in codes))
    L += ["", f"- scope: {criteria.get('scope', 'all')}; active only: {criteria.get('active_only', True)}; min days to due: {criteria.get('min_days_to_due', 0)}",
          f"- excluded types: {', '.join(criteria.get('exclude_opportunity_types') or []) or 'none'}",
          f"- excluded set-asides: {', '.join(criteria.get('exclude_set_asides') or []) or 'none'}; title patterns: {', '.join(criteria.get('exclude_title_patterns') or []) or 'none'}"]
    if criteria.get("resale_title_patterns"):
        L.append(f"- resale screen: drop titles matching {', '.join(criteria['resale_title_patterns'])} "
                 f"UNLESS they also match a keep pattern ({', '.join(criteria.get('keep_title_patterns') or []) or 'none'})")
    if dropped:
        L.append("- screened out: " + "; ".join(f"{k} ({v})" for k, v in sorted(dropped.items())))
    L.append("")
    L += [f"## New since last run ({len(new)})", ""]
    L += [HEADER] + [_row(r) for r in new] if new else ["_none_"]
    L += ["", f"## All open matches ({len(rows)})", "", HEADER] + [_row(r) for r in rows]
    by_kind = {}
    for r in rows:
        for m in r["matched_by"]:
            by_kind[m] = by_kind.get(m, 0) + 1
    L += ["", "## Matches by code", ""] + [f"- {k}: {v}" for k, v in sorted(by_kind.items())]
    L += ["", "## Next", "- Pick the ones worth a look: `python3 -m bidkit.fga file <id> --brief` files an opportunity folder "
          "(portal record + documents) and runs the facts sheet, research plan and calendar.", ""]
    rp = os.path.join(out_dir, f"report-{stamp}.md")
    with open(rp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    with open(os.path.join(out_dir, "latest.json"), "w", encoding="utf-8") as fh:
        json.dump({"generated": when.isoformat(), "filter": flt, "criteria": criteria, "new_ids": sorted(new_ids), "rows": rows}, fh, indent=1, ensure_ascii=False)
    with open(os.path.join(out_dir, "latest.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        cols = ["due", "title", "agency", "opp_type", "set_aside", "naics", "psc", "value_low", "value_high", "posted", "pop", "source_id", "url", "source_url", "matched_by", "new"]
        w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c) if c not in ("matched_by", "new") else (";".join(r["matched_by"]) if c == "matched_by" else ("yes" if r["id"] in new_ids else "")) for c in cols])
    return rp


def source(client, criteria, out_dir, state_path, since=None, ignore_state=False, limit=None, today=None, when=None):
    """search → screens → new-vs-seen → report. Returns (report_path, rows, new_ids, filter)."""
    when = when or dt.datetime.now()
    matched, flt = run_search(client, criteria, since=since, limit=limit)
    rows, dropped = apply_screens([normalize(m["record"], client.portal, m["matched_by"]) for m in matched], criteria, today=today)
    state = load_state(state_path)
    seen = state.setdefault("seen", {})
    new_ids = {r["id"] for r in rows if ignore_state or r["id"] not in seen}
    now = when.isoformat(timespec="seconds")
    for r in rows:
        e = seen.setdefault(r["id"], {"first_seen": now, "title": r["title"][:80], "due": r["due"]})
        e["last_seen"] = now; e["due"] = r["due"]
    state["last_run"] = now
    save_state(state_path, state)
    return write_report(out_dir, rows, new_ids, flt, criteria, state_path, when=when, dropped=dropped), rows, new_ids, flt


# ----------------------------------------------------------------------------- file one opportunity
def portal_record(rec, portal_url=DEFAULT_PORTAL):
    """The shape bidkit.brief already reads (rfp/portal-record.json, as for WEBS) + FGA extras."""
    n = normalize(rec, portal_url)
    low, high = n["value_low"], n["value_high"]
    return {"portal": "fga", "portal_key": PORTAL_KEY, "url": n["url"], "system_id": n["id"], "reference": n["source_id"],
            "organization": n["agency"], "title": n["title"], "description": (rec.get("description_text") or "")[:3000],
            "posted": n["posted"], "closed": n["due"],
            "estimated_value_text": (fmt_money(low, high) + " (FGA estimate)") if (low or high) else None,
            "estimated_value": high if high is not None else low,
            "estimated_value_label": "FGA's estimated value range for this opportunity (the aggregator's model, not the agency's figure)",
            "contact": n["contact"],
            "documents": [{"name": d.get("file_name") or d.get("name") or f"document-{i+1}", "url": d.get("download_url") or ""} for i, d in enumerate(rec.get("documents") or [])],
            "amendments": [],
            "naics": n["naics"], "psc": n["psc"], "set_aside": n["set_aside"], "opp_type": n["opp_type"], "source_type": n["source_type"],
            "source_url": n["source_url"], "aggregator_url": n["aggregator_url"], "place_of_performance": n["pop"], "ai_summary": rec.get("ai_summary") or ""}


def _slug(title, max_words=4, max_len=40):
    stop = set("a an the and or of to for in on at by with from request proposal proposals rfp rfq rfi services service".split())
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9]+", title or "") if w.lower() not in stop]
    out = []
    for w in words:
        if len(out) >= max_words: break
        out.append(w if w.isupper() else w.capitalize())
    return ("-".join(out) or "Opportunity")[:max_len].rstrip("-")


def file_opportunity(client, opp_id, out_root, template_dir=None, docs=True, when=None):
    """Create opportunities/<number>-<slug>/ from the portal record: opportunity.json, rfp/portal-record.json
    (+ .md), rfp/<documents>, sourcing/fga-record.md. Returns (folder, record, downloaded)."""
    when = when or dt.datetime.now(dt.timezone.utc)
    rec = client.opportunity(opp_id)
    pr = portal_record(rec, client.portal)
    number = re.sub(r"[^\w.-]+", "-", (pr["reference"] or pr["system_id"][:8])).strip("-")
    folder = os.path.join(out_root, f"{number}-{_slug(pr['title'])}")
    if os.path.exists(folder):
        raise FgaError(f"{folder} already exists — refusing to overwrite; delete it or file elsewhere with --out")
    if template_dir and os.path.isdir(template_dir):
        shutil.copytree(template_dir, folder)
    os.makedirs(os.path.join(folder, "rfp"), exist_ok=True); os.makedirs(os.path.join(folder, "sourcing"), exist_ok=True)
    # opportunity.json: from the template's placeholders when present, else a minimal one
    oj_path = os.path.join(folder, "opportunity.json")
    values = {"ID": os.path.basename(folder), "AGENCY": pr["organization"], "AGENCY_SOURCE": "bidkit.fga (portal record)",
              "TITLE": pr["title"], "NUMBER": pr["reference"] or "", "SOURCE_TYPE": "fga", "RECEIVED": when.isoformat(),
              "FROM": pr["url"], "MESSAGE_ID": pr["system_id"], "DUE_DATE": pr["closed"] or "",
              "DUE_SOURCE": "bidkit.fga (portal record — DETECTED)" if pr["closed"] else ""}
    if os.path.exists(oj_path):
        txt = open(oj_path, encoding="utf-8").read()
        for k, v in values.items():
            txt = txt.replace("{{" + k + "}}", json.dumps(v)[1:-1])
        txt = re.sub(r"\{\{[A-Z_]+\}\}", "", txt)
        oj = json.loads(txt)
    else:
        oj = {"id": values["ID"], "agency": values["AGENCY"], "agency_source": values["AGENCY_SOURCE"], "title": values["TITLE"],
              "solicitation_number": values["NUMBER"], "source": {"type": "fga", "received": values["RECEIVED"], "from": values["FROM"], "message_id": values["MESSAGE_ID"]},
              "due": {"date": values["DUE_DATE"], "time": "", "timezone": "America/Los_Angeles", "confirmed": False, "source": values["DUE_SOURCE"]}}
    oj["sourcing"] = {"portal": PORTAL_KEY, "id": pr["system_id"], "url": pr["url"], "source_url": pr["source_url"], "filed": when.isoformat()}
    with open(oj_path, "w", encoding="utf-8") as fh:
        json.dump(oj, fh, indent=2, ensure_ascii=False)
    # portal record (brief reads it) + human note
    rec_json = os.path.join(folder, "rfp", "portal-record.json")
    with open(rec_json, "w", encoding="utf-8") as fh:
        json.dump([dict(pr, captured_at=when.isoformat())], fh, indent=2, ensure_ascii=False)
    note = [f"# {pr['title']}", "", f"- FGA: {pr['url']}", f"- source: {pr['source_url'] or '—'}  ({pr['source_type']}, {pr['opp_type']})",
            f"- agency: {pr['organization']}; reference # **{pr['reference'] or '—'}**", f"- posted {pr['posted'] or '—'}; **due {pr['closed'] or '—'}** (DETECTED — confirm in the solicitation)",
            f"- NAICS {pr['naics'] or '—'}; PSC {pr['psc'] or '—'}; set-aside {pr['set_aside'] or '—'}; place of performance {pr['place_of_performance'] or '—'}",
            f"- FGA estimated value: {pr['estimated_value_text'] or '—'}",
            f"- contact: {pr['contact'].get('name') or '—'} {pr['contact'].get('email') or ''} {pr['contact'].get('phone') or ''}".rstrip(), ""]
    if pr["ai_summary"]:
        note += ["## FGA AI summary (the aggregator's text — not the solicitation)", "", pr["ai_summary"], ""]
    if pr["description"]:
        note += ["## Description (as posted)", "", pr["description"], ""]
    with open(os.path.join(folder, "sourcing", "fga-record.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(note))
    downloaded = []
    if docs:
        try:
            doc_list = client.documents(pr["system_id"]) or rec.get("documents") or []
        except FgaError as e:
            doc_list = rec.get("documents") or []; downloaded.append(f"ERROR fetch-documents: {e}")
        for d in doc_list:
            url = d.get("download_url")
            if not url:
                continue
            name = re.sub(r"[^\w.\- ()\[\]&,]+", "_", d.get("file_name") or f"document-{len(downloaded)+1}").strip(" ._") or "document"
            try:
                data, _ = client.download(url)
                with open(os.path.join(folder, "rfp", name), "wb") as fh:
                    fh.write(data)
                downloaded.append(name)
            except FgaError as e:
                downloaded.append(f"ERROR {name}: {e}")
        errors = [x for x in downloaded if x.startswith("ERROR")]
        with open(os.path.join(folder, "rfp", "portal-fetch.md"), "a", encoding="utf-8") as fh:
            fh.write(f"# Portal fetch — {when.isoformat()}\n\n## {pr['url']}\n- portal: `{PORTAL_KEY}` (bidkit.fga)\n"
                     + "".join(f"- {'**ERROR** ' if x.startswith('ERROR') else 'new       `'}{x.replace('ERROR ', '') if x.startswith('ERROR') else x + '`'}\n" for x in downloaded)
                     + ("- no documents attached on the portal\n" if not downloaded else "")
                     + (f"- documents failed at the aggregator's storage (a 403 there means ITS signed links are broken — its own UI fails the same way); "
                        f"get them from the source system instead: {pr['source_url'] or pr['aggregator_url'] or 'no source link'}\n" if errors else "") + "\n")
    # the source system's page is where the real documents live: leave it where bidkit.portal fetch looks
    links = [u for u in (pr["source_url"], pr["aggregator_url"]) if u]
    if links:
        os.makedirs(os.path.join(folder, "initial-email"), exist_ok=True)
        with open(os.path.join(folder, "initial-email", "links.md"), "w", encoding="utf-8") as fh:
            fh.write("# Links (from the sourcing portal record — no email for this opportunity)\n\n" + "\n".join(f"- {u}" for u in links) + "\n")
    return folder, pr, downloaded


# ----------------------------------------------------------------------------- CLI
def _spec(portals_path):
    from .portal import load_portals
    portals = load_portals(os.path.normpath(portals_path)) if portals_path else {}
    return portals.get(PORTAL_KEY) or {}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--portals", default=None, help="inbox/portals.json (entry federalgovadvisors.com: token_file, profile_dir, username, password_env…)")
    ap.add_argument("--token-file", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("login", help="obtain tokens: --from-browser (Playwright profile) or --auto (stored credentials)")
    g = l.add_mutually_exclusive_group(); g.add_argument("--from-browser", action="store_true"); g.add_argument("--auto", action="store_true")
    c = sub.add_parser("codes", help="show the expanded NAICS/PSC filter with the portal's ids"); c.add_argument("--criteria", required=True)
    s = sub.add_parser("search", help="run the sourcing search and write the report")
    s.add_argument("--criteria", required=True); s.add_argument("--out", default="opportunities/sourcing/fga")
    s.add_argument("--state", default="inbox/fga-seen.json"); s.add_argument("--all", action="store_true", help="report everything as new (ignore seen-state)")
    s.add_argument("--since-days", type=int, default=None, help="only opportunities posted in the last N days"); s.add_argument("--limit", type=int, default=None)
    pr = sub.add_parser("profile", help="show / widen the portal's business-profile NAICS+PSC lists to the criteria (dry run unless --apply)")
    pr.add_argument("--criteria", required=True); pr.add_argument("--apply", action="store_true", help="PATCH the profile (backs it up first)")
    pr.add_argument("--replace", action="store_true", help="set the lists to the criteria exactly instead of adding to them")
    pr.add_argument("--backup-dir", default=None, help="where to keep the pre-change profile JSON (default: next to the token file)")
    f = sub.add_parser("file", help="file one opportunity as an opportunity folder"); f.add_argument("opportunity_id")
    f.add_argument("--out", default="opportunities"); f.add_argument("--template", default="opportunities/_template")
    f.add_argument("--no-docs", action="store_true"); f.add_argument("--brief", action="store_true", help="run bidkit.brief + calendar afterwards")
    a = ap.parse_args(argv)
    spec = _spec(a.portals)
    client = FgaClient(spec, token_file=a.token_file)
    try:
        if a.cmd == "login":
            if a.from_browser:
                from .portal import profile_dir_for
                client.import_browser_tokens(profile_dir_for(PORTAL_KEY, spec))
                client.ensure_auth()
                print(f"tokens imported from the browser profile → {client.token_file} (access token valid until {client.jwt_expiry(client.tokens['accessToken'])})")
            elif a.auto:
                from .portal import resolve_credentials
                user, pw = resolve_credentials(spec)
                if not (user and pw):
                    print("no stored credentials: set portals.json → federalgovadvisors.com username + password_env / password_keychain_service"); return 2
                u = client.login(user, pw); print(f"logged in as {u.get('email') or user} → {client.token_file}")
            else:
                client.ensure_auth(); print(f"token ok until {client.jwt_expiry(client.tokens['accessToken'])} ({client.token_file})")
            return 0
        if a.cmd == "codes":
            crit = load_criteria(a.criteria); flt = resolve_filter(client, crit)
            for kind, codes in flt.items():
                print(f"{kind.upper()} ({len(codes)} codes from seeds {sorted({c['seed'] for c in codes})}):")
                for cd in codes: print(f"   {cd['code']:8s} {cd['title'][:70]:70s} {cd['id']}")
            return 0
        if a.cmd == "search":
            crit = load_criteria(a.criteria)
            since = (dt.date.today() - dt.timedelta(days=a.since_days)).isoformat() if a.since_days else None
            rp, rows, new_ids, flt = source(client, crit, a.out, a.state, since=since, ignore_state=a.all, limit=a.limit)
            print(f"{len(rows)} open match(es), {len(new_ids)} new → {rp}")
            for r in sorted(rows, key=lambda r: (r['due'] or '9999'))[:15]:
                if r["id"] in new_ids: print(f"   NEW {r['due']} {r['title'][:60]:60s} {r['agency'][:28]:28s} {r['naics']}/{r['psc']} {fmt_money(r['value_low'], r['value_high'])}")
            return 0
        if a.cmd == "profile":
            crit = load_criteria(a.criteria)
            plan, backup, after = sync_business_profile(client, crit, apply=a.apply, replace=a.replace, backup_dir=a.backup_dir)
            for kind in ("naics", "psc"):
                pk = plan[kind]
                print(f"{kind.upper()}: on the profile now {pk['current'] or '[]'}")
                print(f"   {'ADDED' if a.apply else 'would add'}: {pk['add'] or 'nothing'}" + (f"   {'REMOVED' if a.apply else 'would remove'}: {pk['remove']}" if pk["remove"] else ""))
            if a.apply:
                print(f"profile updated and re-read: NAICS {sorted(x.get('naics_code') for x in after.get('naics_codes') or [])}; "
                      f"PSC {sorted(x.get('psc_code') for x in after.get('psc_codes') or [])}\n   backup of the previous profile: {backup}")
            else:
                print("dry run — nothing changed; add --apply to update the profile (a backup is written first)")
            return 0
        if a.cmd == "file":
            folder, pr, downloaded = file_opportunity(client, a.opportunity_id, a.out, template_dir=a.template, docs=not a.no_docs)
            print(f"filed {folder}\n   {pr['title']} — {pr['organization']}; due {pr['closed']}; {len([d for d in downloaded if not d.startswith('ERROR')])} document(s)"
                  + (f"; errors: {[d for d in downloaded if d.startswith('ERROR')]}" if any(d.startswith('ERROR') for d in downloaded) else ""))
            if a.brief:
                from . import brief, calendar
                brief.run(folder)
                try:
                    calendar.main(["ics", folder])
                except SystemExit:
                    pass
                print(f"   brief + calendar written in {folder}")
            return 0
    except FgaAuthError as e:
        print(f"FGA AUTH: {e}"); return 3
    except FgaError as e:
        print(f"FGA ERROR: {e}"); return 1


if __name__ == "__main__":
    sys.exit(main())
