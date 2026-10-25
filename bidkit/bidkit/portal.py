#!/usr/bin/env python3
"""
portal.py — fetch solicitation documents from procurement portals into <opportunity>/rfp/ using
a browser session with PERSISTED COOKIES (Playwright persistent profile).

SCAFFOLD for the machine that keeps logged-in browser profiles. Portals (Public Purchase,
WEBS, BidNet, Bonfire, PlanetBids, …) put the RFP and attachments behind a vendor login, so
the inbox poller can only save the LINKS from the email. This module opens those links in a
real browser profile where you have already logged in once, finds the document links on the
page, downloads them with the session's cookies, and leaves a record (screenshot, saved HTML,
portal-fetch.md) so the intake step can cite what was fetched and when.

Three layers, each testable alone:
  extract_links(html, base_url)       pure HTML → [Link(href, text)]        (no browser)
  adapters (PortalAdapter subclasses) per-portal rules: which links are documents, how to name
                                      the file, how to tell you're logged in. GenericPortal works
                                      from file extensions + "download/attachment" text;
                                      PublicPurchasePortal is grounded on a REAL saved bid page.
  sessions                            PlaywrightSession (real browser, persistent user_data_dir,
                                      lazy import — module loads without playwright) or any
                                      object with the same 4 methods (tests use a fake/local server)

Playwright is OPTIONAL: pip3 install -r bidkit/requirements-portal.txt && python3 -m playwright install chromium

Persisted cookies: one profile directory per portal (portals.json → profile_dir). Bootstrap once
per portal on a machine with a display:  python3 -m bidkit.portal login publicpurchase.com
→ a headed browser opens; log in; press Enter; cookies persist in the profile for future
headless runs. Profiles live OUTSIDE the repo (~/.config/bidkit/browser-profiles/<portal>/).

CLI:
  python3 -m bidkit.portal fetch   <opportunity-dir> [--url URL ...] [--search des.wa.gov:<number>] [--dry-run] [--headed]
  python3 -m bidkit.portal login   <portal-domain>   [--url URL]           # headed; log in once, cookies persist
  python3 -m bidkit.portal capture <portal-domain> <page-name> [--url URL] [--headed]
                                                    # save page + EVERY FRAME to portal-captures/ for grounding
  python3 -m bidkit.portal links   <opportunity-dir>                       # show links + adapter choice, no browser
  fetch reads links from initial-email/links.md (and followups) unless --url is given; --search asks
  the portal adapter to find the opportunity when the email carried no link; downloads land in rfp/
  (never overwriting a differing existing file); writes rfp/portal-fetch.md.

Frames: legacy portals (WEBS) are <frameset> pages — the top document is an empty shell and a
browser's "Save Page" captures only that shell. goto()/snapshot() are frame-aware: content comes
from the adapter's frame_name (or the largest child frame), and snapshots save every frame;
goto_in_frame() navigates the content frame itself (frameset sites bounce top-level inner URLs).

Grounded adapters (selectors verified on the live site, fixtures in tests/fixtures/):
  publicpurchase  document links + naming (real saved bid page)
  webs            frameset navigation, login page + automatic re-login with stored credentials
                  (sessions expire after ~20 idle minutes), simple + advanced search, result matching by
                  reference number / title, solicitation record (dates, estimated value, contact, files,
                  amendments → rfp/portal-record.json), direct downloads, vendors-downloading list
                  (→ research/portal-vendors-downloading.csv)
Anything else: the `generic` adapter, configurable from portals.json (frame_name, logged_in_marker,
doc_href_pattern, doc_name_from, search{url, input_selector, submit_selector, result_link_selector}).

Credentials for unattended re-login are never in the repo: portals.json names the username and a
password_env variable or a keychain service (resolve_credentials).
"""
import argparse, datetime as dt, html as htmlmod, json, os, re, sys, urllib.parse

DOC_EXT = (".pdf", ".xlsx", ".xls", ".xlsm", ".docx", ".doc", ".zip", ".csv", ".txt", ".rtf", ".pptx")
DOC_WORDS = re.compile(r"(?i)\b(download|attachment|addend|amendment|document|specification|exhibit|solicitation|rfp|rfq|itb)\b")
INSTALL_HINT = "pip3 install -r bidkit/requirements-portal.txt && python3 -m playwright install chromium"
DEFAULT_PROFILE_ROOT = "~/.config/bidkit/browser-profiles"


class PortalError(Exception):
    pass


class NotLoggedIn(PortalError):
    """The portal answered with its login page. fetch() catches this, logs in with stored credentials
    when the adapter knows how (WebsPortal) and retries once; otherwise it reports NOT LOGGED IN."""


def resolve_credentials(spec):
    """(username, password) for a portal from portals.json + a secret store — NEVER from the file itself:
      "username": "you@example.com",
      "password_env": "WEBS_PASSWORD",                 # environment variable (cron: ~/.config/bidkit/env)
      "password_keychain_service": "bidkit-webs"       # macOS: security add-generic-password -s bidkit-webs -a <username> -w
                                                       # Linux: secret-tool store --label=bidkit service bidkit-webs account <username>
    Returns (None, None) when nothing is configured or the store has no entry."""
    import subprocess
    user = (spec or {}).get("username")
    if not user or str(user).upper().startswith("TODO"):     # the example file's placeholder
        return None, None
    env = spec.get("password_env")
    if env and os.environ.get(env):
        return user, os.environ[env]
    svc = spec.get("password_keychain_service")
    if svc:
        for cmd in (["security", "find-generic-password", "-s", svc, "-a", user, "-w"],
                    ["secret-tool", "lookup", "service", svc, "account", user]):
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=20)
                if out.stdout.strip():
                    return user, out.stdout.strip()
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                continue
    return user, None


# ----------------------------------------------------------------------------- links (pure)
class Link:
    __slots__ = ("href", "text")
    def __init__(self, href, text): self.href, self.text = href, text
    def __repr__(self): return f"Link({self.href!r}, {self.text!r})"
    def __eq__(self, o): return isinstance(o, Link) and (self.href, self.text) == (o.href, o.text)
    def __hash__(self): return hash((self.href, self.text))


def extract_links(page_html, base_url):
    """All anchors as absolute URLs with visible text (tags stripped, entities unescaped)."""
    out = []
    for href, inner in re.findall(r'<a\b[^>]*?href\s*=\s*"([^"]+)"[^>]*>(.*?)</a>', page_html, flags=re.I | re.S):
        href = htmlmod.unescape(href.strip())
        if href.startswith(("javascript:", "mailto:", "#")):
            continue
        text = htmlmod.unescape(re.sub(r"<[^>]+>|\s+", " ", inner)).strip()
        out.append(Link(urllib.parse.urljoin(base_url, href), text))
    return out


def domain_of(url):
    """Host without port or leading www. — the key used to match portals.json entries."""
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def safe_filename(name, fallback="document"):
    name = (name or fallback).strip().replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^\w.\- ()\[\]&,]+", "_", name).strip(" ._")
    return name[:180] or fallback


# ----------------------------------------------------------------------------- adapters
class PortalAdapter:
    """Per-portal knowledge. Subclass and register in ADAPTERS; select via portals.json or domain.

    Config-driven grounding (portals.json options) — lets a portal be grounded from a captured
    page WITHOUT code: `frame_name` (content frame of a frameset), `logged_in_marker` (string only
    present when signed in), `doc_href_pattern` (regex: anchors whose href matches are documents),
    `doc_name_from` ("text" | "path" — where the filename comes from), `wait_after_load_ms`."""
    name = "generic"
    domains = ()                       # domains this adapter claims by default
    login_url = None                   # where `login` should open (defaults to the page url)
    wait_after_load_ms = 0             # extra settle time for JS-heavy pages
    frame_name = None                  # content frame for frameset portals (None = auto/top)

    def __init__(self, options=None):
        self.opt = options or {}
        if self.opt.get("frame_name"): self.frame_name = self.opt["frame_name"]
        if self.opt.get("wait_after_load_ms") is not None: self.wait_after_load_ms = int(self.opt["wait_after_load_ms"])
        if self.opt.get("login_url"): self.login_url = self.opt["login_url"]

    def is_logged_in(self, page_html):
        """Heuristic: a password field on the page means we were bounced to a login form."""
        sel = self.opt.get("logged_in_marker")
        if sel:
            return sel in page_html
        return not re.search(r'type\s*=\s*"password"', page_html, re.I)

    def open(self, session, url):
        """Load the opportunity page and return (final_url, html) of its CONTENT document. Frameset
        portals override this to navigate the content frame (see WebsPortal.open)."""
        kwargs = {"settle_ms": self.wait_after_load_ms}
        if self.frame_name:
            kwargs["frame_name"] = self.frame_name
        try:
            return session.goto(url, **kwargs)
        except TypeError:                                   # fake/legacy sessions without frame_name
            return session.goto(url, settle_ms=self.wait_after_load_ms)

    def is_landing_page(self, url):
        """True when url is the portal's home/login page rather than an opportunity — the usual case
        for notification emails that just say "log in to view". fetch then searches instead."""
        return False

    def page_metadata(self, session, page_html, page_url):
        """Structured facts the portal's own record states (dates, reference number, estimated value,
        contact, document list). {} when the adapter has no grounded parser for this page."""
        return {}

    def competitor_list(self, session):
        """[{company, email, phone, status}] of vendors the portal shows as having downloaded the
        solicitation (competitive intelligence), or None when the portal offers no such list."""
        return None

    def login(self, session, username, password):
        """Sign in with stored credentials (see resolve_credentials). Only grounded adapters know the
        form; the fallback is the human, once, in a headed window: python3 -m bidkit.portal login <domain>."""
        raise PortalError(f"adapter {self.name!r} has no automatic login — run: python3 -m bidkit.portal login <domain> (headed)")

    def find_opportunity(self, session, number=None, title=None):
        """Navigate from a portal home/search page to the opportunity's detail page and return its
        URL, for emails that name a solicitation but don't link it.

        Base behaviour is CONFIG-DRIVEN so a portal can be grounded from captured pages without code:
        portals.json → "search": {url, input_selector, submit_selector, result_link_selector,
        result_text_contains}. The adapter fills input_selector with the number (or title), clicks
        submit_selector, then follows the first result_link_selector whose text or href contains
        result_text_contains (default: the query). Grounded subclasses override this."""
        s = self.opt.get("search") or {}
        needed = ("url", "input_selector", "submit_selector", "result_link_selector")
        if not all(s.get(k) for k in needed):
            raise PortalError(f"adapter {self.name!r} cannot search this portal for {number or title!r}: capture its search "
                              f"and results pages (python3 -m bidkit.portal capture <domain> search --headed) and set "
                              f"portals.json → \"search\" {{url, input_selector, submit_selector, result_link_selector}}; "
                              f"or open the opportunity in a browser and pass its URL with --url")
        query = number or title
        if not query:
            raise PortalError(f"need a solicitation number or title to search {self.name}")
        session.goto(s["url"], settle_ms=self.wait_after_load_ms, frame_name=self.frame_name)
        fr = session.frame(self.frame_name)
        fr.fill(s["input_selector"], query)
        fr.click(s["submit_selector"])
        try:
            fr.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        must = (s.get("result_text_contains") or query).lower()
        for a in fr.query_selector_all(s["result_link_selector"]):
            txt = (a.inner_text() or "").strip()
            if must in txt.lower() or must in (a.get_attribute("href") or "").lower():
                return urllib.parse.urljoin(fr.url, a.get_attribute("href") or "")
        raise PortalError(f"{self.name} search for {query!r} returned no matching result link")

    def document_links(self, links):
        """[(Link, filename)] — which anchors are documents and what to call the file."""
        pat = self.opt.get("doc_href_pattern")
        if pat:
            return self._links_by_pattern(links, re.compile(pat, re.I), self.opt.get("doc_name_from", "text"))
        seen, out = set(), []
        for ln in links:
            path = urllib.parse.urlparse(ln.href).path.lower()
            is_doc = path.endswith(DOC_EXT) or (DOC_WORDS.search(ln.text) and DOC_WORDS.search(path + " " + ln.text))
            if not is_doc or ln.href in seen:
                continue
            seen.add(ln.href)
            fname = safe_filename(urllib.parse.unquote(os.path.basename(urllib.parse.urlparse(ln.href).path))) \
                if path.endswith(DOC_EXT) else safe_filename(ln.text)
            out.append((ln, fname))
        return out

    @staticmethod
    def _links_by_pattern(links, href_re, name_from="text"):
        """Documents = anchors whose href matches; one entry per href; filename from the first anchor
        whose text isn't a bare 'download' word (or from the URL path)."""
        by_href = {}
        for ln in links:
            if not href_re.search(ln.href):
                continue
            e = by_href.setdefault(ln.href, {"link": ln, "name": None})
            if name_from == "text" and ln.text and not re.fullmatch(r"\[?\s*(download|view|open)\s*\]?", ln.text, re.I):
                e["name"] = e["name"] or ln.text
        out = []
        for href, e in by_href.items():
            if name_from == "path" or not e["name"]:
                base = urllib.parse.unquote(os.path.basename(urllib.parse.urlparse(href).path))
                e["name"] = e["name"] or base or f"document-{len(out)+1}"
            out.append((e["link"], safe_filename(e["name"])))
        return out


class PublicPurchasePortal(PortalAdapter):
    """Grounded on a real saved Public Purchase bid page (tests/fixtures/publicpurchase-bid-page.html):
    document anchors are /gems/docviewer/bidDoc?...docId=N (NO file extension), the filename is the
    anchor text, and each document has a second anchor "[Download]" to the same href. Track-changes
    links (/gems/.../onlineTrackChanges) are not documents."""
    name = "publicpurchase"
    domains = ("publicpurchase.com",)
    login_url = "https://www.publicpurchase.com/gems/login/login"
    wait_after_load_ms = 500
    DOC_HREF = re.compile(r"/gems/docviewer/bidDoc\?", re.I)

    def document_links(self, links):
        by_href = {}
        for ln in links:
            if not self.DOC_HREF.search(ln.href):
                continue
            entry = by_href.setdefault(ln.href, {"link": ln, "name": None})
            if ln.text and not re.fullmatch(r"\[?\s*download\s*\]?", ln.text, re.I):
                entry["name"] = ln.text                      # the non-"[Download]" anchor carries the filename
        out = []
        for href, e in by_href.items():
            doc_id = re.search(r"docId=(\d+)", href)
            fname = safe_filename(e["name"]) if e["name"] else f"document-{doc_id.group(1) if doc_id else len(out)+1}"
            out.append((e["link"], fname))
        return out

    def is_logged_in(self, page_html):
        return "Sign out" in page_html or "Logout" in page_html or not re.search(r'type\s*=\s*"password"', page_html, re.I)


def _text(fragment):
    """Visible text of an HTML fragment: tags stripped, entities unescaped, whitespace collapsed."""
    return re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))).strip()


def _us_date_iso(s):
    """'9/14/2026' or '09/10/26' -> '2026-09-14' (None if it isn't a US date)."""
    m = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})\s*", s or "")
    if not m:
        return None
    mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    y = y + 2000 if y < 100 else y
    try:
        return dt.date(y, mo, d).isoformat()
    except ValueError:
        return None


def _money_number(s):
    """'1,500,000' / '216,073.12' / '' -> float or None."""
    t = re.sub(r"[^\d.]", "", s or "")
    try:
        return float(t) if t else None
    except ValueError:
        return None


def webs_parse_results(page_html, base_url):
    """Rows of a WEBS search-results page (Search_Bid_Result.aspx, table #DataGrid1).

    Grounded on a live capture: each result is <tr class="Grid3File1|2"> with cells Title (an
    <a class="ctext-hyperlink" href="Search_BidDetails.aspx?ID=N">), Description, Organization,
    Contact, Reference #, Date Posted (MM/DD/YY). 'Total number of records returned = N' precedes
    the grid; 100 rows per page with a pager when there are more. Returns
    {"total": int|None, "rows": [{id, title, description, organization, contact, reference,
    posted, url}], "truncated": bool}."""
    total = re.search(r"Total number of records returned\s*=\s*(\d+)", _text(page_html))
    rows = []
    for m in re.finditer(r'(?is)<tr class="Grid3File[12]">(.*?)</tr>', page_html):
        cells = re.findall(r"(?is)<td[^>]*>(.*?)</td>", m.group(1))
        if len(cells) < 6:
            continue
        href = re.search(r'href="([^"]*Search_BidDetails\.aspx\?ID=(\d+))"', cells[0], re.I)
        if not href:
            continue
        rows.append({"id": href.group(2), "title": _text(cells[0]), "description": _text(cells[1]),
                     "organization": _text(cells[2]), "contact": _text(cells[3]), "reference": _text(cells[4]),
                     "posted": _us_date_iso(_text(cells[5])) or _text(cells[5]),
                     "url": urllib.parse.urljoin(base_url, htmlmod.unescape(href.group(1)))})
    n_total = int(total.group(1)) if total else None
    return {"total": n_total, "rows": rows, "truncated": bool(n_total and n_total > len(rows))}


def webs_parse_detail(page_html, page_url):
    """Structured record from a WEBS solicitation page (Search_BidDetails.aspx?ID=N).

    Grounded on live captures: every field is a <span id="txt…">: txtSystemIdentifier (WEBS ID),
    txtReferenceNumber (the agency's own number), txtOrgName, txtTitle, txtDescription,
    txtActiveDate (Date Posted), txtInactiveDate (Date Closed), txtEstimatedValue ("Estimated Initial
    Contract Value", often blank), txtContactName/txtContactPhone/txtEmail, labelCommCodes,
    labelCounties. Documents are anchors in table #dataGridBidDocuments (DocType=1) and amendments
    in #dataGridBidAmendments (DocType=2, each with a <span id="…labelFileDate">). Anchor text is
    the real filename. Returns {} if the page isn't a detail page."""
    def span(i):
        m = re.search(rf'(?is)<span id="{i}"[^>]*>(.*?)</span>', page_html)
        return _text(m.group(1)) if m else ""
    if not re.search(r'id="txtSystemIdentifier"', page_html):
        return {}
    rec = {"portal": "webs", "url": page_url, "system_id": span("txtSystemIdentifier"),
           "reference": span("txtReferenceNumber"), "organization": span("txtOrgName"), "title": span("txtTitle"),
           "description": span("txtDescription"),
           "posted": _us_date_iso(span("txtActiveDate")) or span("txtActiveDate") or None,
           "closed": _us_date_iso(span("txtInactiveDate")) or span("txtInactiveDate") or None,
           "estimated_value_text": span("txtEstimatedValue") or None,
           "estimated_value": _money_number(span("txtEstimatedValue")),
           "contact": {"name": span("txtContactName") or None, "phone": span("txtContactPhone") or None,
                       "email": span("txtEmail") or None},
           "counties": [c.strip() for c in span("labelCounties").split(",") if c.strip()],
           "documents": [], "amendments": []}
    cc = re.search(r'(?is)<span id="labelCommCodes"[^>]*>(.*?)</span>', page_html)
    rec["commodity_codes"] = [_text(c) for c in re.split(r"<br\s*/?>", cc.group(1)) if _text(c)] if cc else []
    def grid(table_id):
        m = re.search(rf'(?is)<table[^>]*id="{table_id}"[^>]*>(.*?)</table>\s*</span>', page_html)
        return m.group(1) if m else ""
    for a in re.finditer(r'(?is)<a\b[^>]*href="([^"]*AttachmentViewer\.aspx[^"]*)"[^>]*>(.*?)</a>', grid("dataGridBidDocuments")):
        rec["documents"].append({"name": _text(a.group(2)), "url": urllib.parse.urljoin(page_url, htmlmod.unescape(a.group(1)))})
    for row in re.finditer(r'(?is)<span id="dataGridBidAmendments[^"]*labelFileDate"[^>]*>(.*?)</span>.*?<a\b[^>]*href="([^"]*AttachmentViewer\.aspx[^"]*)"[^>]*>(.*?)</a>', grid("dataGridBidAmendments")):
        rec["amendments"].append({"date": _us_date_iso(_text(row.group(1))) or _text(row.group(1)), "name": _text(row.group(3)),
                                  "url": urllib.parse.urljoin(page_url, htmlmod.unescape(row.group(2)))})
    return rec


def webs_parse_vendors(page_html):
    """[{company, email, phone, status}] from the 'Vendors Downloading' view (table #Datagrid1 with
    header cells Company Name / Email / Phone / Status; Status carries OMWBE-style flags such as
    Mc-SB). The page itself says the list covers only vendors who opted in to information sharing."""
    m = re.search(r'(?is)<table[^>]*id="Datagrid1"[^>]*>(.*?)</table>', page_html)
    if not m:
        return []
    header = None; out = []
    for tr in re.finditer(r"(?is)<tr[^>]*>(.*?)</tr>", m.group(1)):
        cells = [_text(c) for c in re.findall(r"(?is)<td[^>]*>(.*?)</td>", tr.group(1))]
        if not cells:
            continue
        if header is None:
            header = [re.sub(r"[^a-z]", "", c.lower()) for c in cells]
            continue
        if len(cells) != len(header):
            continue
        d = dict(zip(header, cells))
        out.append({"company": d.get("companyname", ""), "email": d.get("email", ""), "phone": d.get("phone", ""),
                    "status": d.get("status", "")})
    return out


class WebsPortal(PortalAdapter):
    """Washington's Electronic Business Solution (WEBS, des.wa.gov) — GROUNDED on live, logged-in
    captures of every page in the flow (scrubbed copies in tests/fixtures/webs-*.html).

    Facts this adapter relies on (all observed, none guessed):
    - The site is an ASP.NET FRAMESET: top document = shell (home.html) with frames `top` (help.html)
      and `bottom` (the real page). A top-level request for ANY inner URL bounces back to the frameset
      home, so inner pages are reached by navigating frame `bottom` (goto_in_frame / clicks).
    - Logged in ⇔ the bottom frame has the `Logout.aspx` link (and "Hello User …").
    - Simple search Search_Bid.aspx: radios #radCommCodes_1 / #radCounties_1 = "All" (default is
      "My" codes/counties), keyword box #textBoxBidCustRefNum (maxlength 15 — matches title words AND
      reference-number substrings), submit image #Image1 → Search_Bid_Result.aspx (#DataGrid1, 100
      rows/page). Advanced search SearchBid.aspx: #SolicitationKeywords (no length cap),
      #ddlBidStatus (-1 = ALL incl. Closed/Archived — use it for incumbent/prior-solicitation research),
      #CommodityFilterRBL_1 = no commodity filter, submit #SearchButton → same results page.
    - Detail Search_BidDetails.aspx?ID=<WEBS id>: see webs_parse_detail. Documents download directly:
      GET AttachmentViewer.aspx?AttachmentID=N&DocType=1|2&BidID=N answers with the file and
      Content-Disposition: attachment;filename=… (works through the session's cookie jar).
    - #Imagebutton1 ("Vendors Downloading") posts back and shows #Datagrid1 with Company/Email/Phone/
      Status of vendors who downloaded the solicitation (opt-in list) — competitive intelligence.
    portals.json may override login_url (test servers), logged_in_marker and frame_name."""
    name = "webs"
    domains = ("des.wa.gov",)
    login_url = "https://pr-webs-vendor.des.wa.gov/"
    frame_name = "bottom"
    wait_after_load_ms = 500
    LOGGED_IN_MARKER = "Logout.aspx"
    DOC_HREF = re.compile(r"AttachmentViewer\.aspx\?", re.I)
    DETAIL_RE = re.compile(r"Search_BidDetails\.aspx\?ID=(\d+)", re.I)
    SIMPLE_SEARCH, ADVANCED_SEARCH = "Search_Bid.aspx", "SearchBid.aspx"
    KEYWORD_MAXLEN = 15
    SEL = {"all_codes": "#radCommCodes_1", "all_counties": "#radCounties_1", "keyword": "#textBoxBidCustRefNum",
           "submit": "#Image1", "adv_keywords": "#SolicitationKeywords", "adv_status": "#ddlBidStatus",
           "adv_no_commodity_filter": "#CommodityFilterRBL_1", "adv_submit": "#SearchButton",
           "vendors_button": "#Imagebutton1",
           # LoginPage.aspx (shown in frame 'bottom' when the ~20-minute ASP.NET session has expired)
           "login_email": "#txtEmail", "login_password": "#txtPassword", "login_submit": "#Image1"}
    LANDING_PATHS = ("", "/", "/home.html", "/home.aspx", "/login.aspx", "/loginpage.aspx", "/default.aspx")

    @property
    def home(self):
        return self.login_url or "https://pr-webs-vendor.des.wa.gov/"

    def is_logged_in(self, page_html):
        return (self.opt.get("logged_in_marker") or self.LOGGED_IN_MARKER) in page_html

    def is_landing_page(self, url):
        return urllib.parse.urlparse(url).path.lower() in self.LANDING_PATHS

    def document_links(self, links):
        return self._links_by_pattern(links, self.DOC_HREF, "text")

    def open(self, session, url):
        if hasattr(session, "goto_in_frame"):
            final_url, html = session.goto_in_frame(url, self.frame_name, settle_ms=self.wait_after_load_ms, home_url=self.home)
        else:
            final_url, html = super().open(session, url)
        if not self.is_logged_in(html):
            raise NotLoggedIn("WEBS shows its login page (sessions expire after ~20 idle minutes)")
        return final_url, html

    def login(self, session, username, password):
        """Fill LoginPage.aspx in frame 'bottom' (#txtEmail / #txtPassword / #Image1 'Log In'). Returns True when
        the frame that comes back carries the Logout link. Credentials come from resolve_credentials — never
        from a file in the repo."""
        session.goto(self.home, settle_ms=self.wait_after_load_ms, frame_name=self.frame_name)
        fr = session.frame(self.frame_name)
        if self.is_logged_in(fr.content()):
            return True
        if fr.query_selector(self.SEL["login_password"]) is None:
            raise PortalError("WEBS: expected LoginPage.aspx in frame 'bottom' but found no password field — capture the page and re-ground the login flow")
        fr.fill(self.SEL["login_email"], username)
        fr.fill(self.SEL["login_password"], password)
        fr = session.click_in_frame(fr, self.SEL["login_submit"], settle_ms=self.wait_after_load_ms, frame_name=self.frame_name)
        ok = self.is_logged_in(fr.content())
        if ok and hasattr(session, "save_state"):
            session.save_state()
        return ok

    def page_metadata(self, session, page_html, page_url):
        return webs_parse_detail(page_html, page_url)

    def competitor_list(self, session):
        if not hasattr(session, "frame") or not hasattr(session, "click_in_frame"):
            return None
        fr = session.frame(self.frame_name)
        if fr.query_selector(self.SEL["vendors_button"]) is None:
            return None
        fr = session.click_in_frame(fr, self.SEL["vendors_button"], settle_ms=self.wait_after_load_ms, frame_name=self.frame_name)
        return webs_parse_vendors(fr.content())

    # ---- search
    @staticmethod
    def _norm(s):
        return re.sub(r"[^a-z0-9]+", "", (s or "").lower())

    @staticmethod
    def title_candidates(title):
        """Search phrases to try for an email subject: the whole thing, the part after the last colon
        or dash (notification subjects prefix the title), and the title minus RFP/RFQ-style lead words."""
        out = []
        def add(t):
            t = re.sub(r"\s+", " ", (t or "")).strip(" -–—:")
            if len(t) >= 4 and t not in out:
                out.append(t)
        add(title)
        for sep in (":", " - ", " – ", " — "):
            if title and sep in title:
                add(title.rsplit(sep, 1)[1])
        add(re.sub(r"(?i)^(?:(?:re|fw|fwd)\s*:\s*)?(?:(?:new|posted|notification|solicitation|rfp|rfq|rfqq|rfi|itb|amendment|addendum|no\.?|#|\d[\w-]*)\s+)+", "", title or ""))
        return sorted(out, key=len)                  # the bare title is the likeliest hit; the full subject rarely is

    def match_row(self, rows, number=None, title=None):
        """Pick the result row that IS the solicitation: exact reference-number match first, then exact
        title, then a unique containment either way. Returns the row or None (ambiguity = None)."""
        n, t = self._norm(number), self._norm(title)
        if n:
            exact = [r for r in rows if self._norm(r["reference"]) == n]
            if len(exact) == 1:
                return exact[0]
            if len(exact) > 1 and t:
                by_title = [r for r in exact if self._norm(r["title"]) == t or t in self._norm(r["title"])]
                if len(by_title) == 1:
                    return by_title[0]
        if t:
            exact = [r for r in rows if self._norm(r["title"]) == t]
            if len(exact) == 1:
                return exact[0]
            # containment only for specific titles: a single generic word ("software") would "uniquely"
            # match whichever row happens to contain it
            if len(t) >= 12:
                contains = [r for r in rows if t in self._norm(r["title"]) or (len(self._norm(r["title"])) >= 12 and self._norm(r["title"]) in t)]
                if len(contains) == 1:
                    return contains[0]
        if n and len(rows) == 1 and n in self._norm(rows[0]["reference"] + " " + rows[0]["title"]):
            return rows[0]
        return None

    def _frame(self, session, url):
        _, html = session.goto_in_frame(url, self.frame_name, settle_ms=self.wait_after_load_ms, home_url=self.home)
        if not self.is_logged_in(html):
            raise NotLoggedIn("WEBS shows its login page (sessions expire after ~20 idle minutes)")
        return session.frame(self.frame_name)

    def simple_search(self, session, keyword):
        fr = self._frame(session, urllib.parse.urljoin(self.home, self.SIMPLE_SEARCH))
        fr.check(self.SEL["all_codes"]); fr.check(self.SEL["all_counties"])
        fr.fill(self.SEL["keyword"], keyword[:self.KEYWORD_MAXLEN])
        fr = session.click_in_frame(fr, self.SEL["submit"], settle_ms=self.wait_after_load_ms, frame_name=self.frame_name)
        return webs_parse_results(fr.content(), fr.url)

    def advanced_search(self, session, keywords, status="-1"):
        """status: -1 = all (Posted + Closed + Archived), or 'Posted' / 'Closed' / 'Archived'."""
        fr = self._frame(session, urllib.parse.urljoin(self.home, self.ADVANCED_SEARCH))
        fr.fill(self.SEL["adv_keywords"], keywords)
        fr.select_option(self.SEL["adv_status"], status)
        fr.check(self.SEL["adv_no_commodity_filter"])
        fr = session.click_in_frame(fr, self.SEL["adv_submit"], settle_ms=self.wait_after_load_ms, frame_name=self.frame_name)
        return webs_parse_results(fr.content(), fr.url)

    def find_opportunity(self, session, number=None, title=None):
        q = (number or "").strip()
        m = self.DETAIL_RE.search(q) or re.fullmatch(r"(?i)\s*id\s*[=:]\s*(\d+)\s*", q)
        if m:                                                      # the email (or the human) gave the WEBS id
            return urllib.parse.urljoin(self.home, f"Search_BidDetails.aspx?ID={m.group(1)}")
        if not q and not title:
            raise PortalError("need a solicitation number or title to search WEBS")
        seen, candidates = set(), []
        def consider(res):
            hit = self.match_row(res["rows"], number=q or None, title=title)
            for r in res["rows"]:
                if r["id"] not in seen:
                    seen.add(r["id"]); candidates.append(r)
            return hit
        if q and len(q) <= self.KEYWORD_MAXLEN:                   # reference numbers hit the simple search directly
            hit = consider(self.simple_search(session, q))
            if hit:
                return hit["url"]
        for phrase in self.title_candidates(title) + ([q] if q else []):
            hit = consider(self.advanced_search(session, phrase))
            if hit:
                return hit["url"]
        shown = "; ".join(f"{r['reference']} | {r['title'][:50]} | {r['organization'][:30]} → {r['url']}" for r in candidates[:8])
        raise PortalError(f"WEBS: no solicitation matched number={number!r} title={title!r}. "
                          f"{len(candidates)} candidate(s): {shown or 'none'} — pass the right page with --url")


ADAPTERS = {a.name: a for a in (PortalAdapter, PublicPurchasePortal, WebsPortal)}


def load_portals(path):
    """portals.json: {"<domain>": {"adapter": "publicpurchase", "profile_dir": "...", ...options}}"""
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return {k.lower(): v for k, v in raw.items() if not k.startswith("_")}


def select_adapter(url, portals):
    """(adapter instance, portal_key). Config wins; otherwise an adapter that claims the domain;
    otherwise generic. Matching is by domain suffix so sub-hosts resolve to their portal."""
    dom = domain_of(url)
    for key, spec in portals.items():
        if dom == key or dom.endswith("." + key):
            cls = ADAPTERS.get((spec or {}).get("adapter", "generic"), PortalAdapter)
            return cls(spec), key
    for cls in ADAPTERS.values():
        if any(dom == d or dom.endswith("." + d) for d in cls.domains):
            return cls({}), dom
    return PortalAdapter({}), dom


def profile_dir_for(portal_key, spec):
    p = (spec or {}).get("profile_dir") or os.path.join(DEFAULT_PROFILE_ROOT, re.sub(r"[^\w.-]", "_", portal_key))
    return os.path.expanduser(p)


# ----------------------------------------------------------------------------- sessions
class PlaywrightSession:
    """Real browser with a persistent profile PLUS a storage_state round-trip.

    Why both: a persistent user_data_dir keeps long-lived cookies and localStorage, but Chromium
    drops SESSION cookies (no Expires/Max-Age — which is what most portal logins use) when the
    browser closes. Discovered by test: after a clean close only the analytics cookies survived.
    Playwright's storage_state export DOES capture session cookies, so on close we save
    <profile>/storage_state.json and on open we re-inject its cookies. Result: a login done once
    (headed) survives headless cron runs until the portal itself expires the session.

    Methods: goto(url)->(final_url, html); download(url)->(bytes, suggested_name|None);
    screenshot(path); close(). Lazy-imports playwright so the module loads without it."""
    STATE_FILE = "storage_state.json"

    def __init__(self, profile_dir, headless=True, timeout_ms=60000):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise PortalError(f"playwright not installed: {INSTALL_HINT}")
        os.makedirs(profile_dir, exist_ok=True)
        self.profile_dir = profile_dir
        self._state_path = os.path.join(profile_dir, self.STATE_FILE)
        self._pw = sync_playwright().start()
        try:
            self.ctx = self._pw.chromium.launch_persistent_context(user_data_dir=profile_dir, headless=headless,
                                                                   accept_downloads=True)
        except Exception as e:
            self._pw.stop()
            raise PortalError(f"could not launch chromium with profile {profile_dir}: {str(e)[:200]} — {INSTALL_HINT}")
        self.ctx.set_default_timeout(timeout_ms)
        self._restore_state()
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()

    def _restore_state(self):
        if not os.path.exists(self._state_path):
            return
        try:
            with open(self._state_path, encoding="utf-8") as fh:
                state = json.load(fh)
            cookies = state.get("cookies") or []
            if cookies:
                self.ctx.add_cookies(cookies)
        except Exception:
            pass                                    # a corrupt state file must never block a fetch

    def save_state(self):
        try:
            self.ctx.storage_state(path=self._state_path)
            os.chmod(self._state_path, 0o600)
        except Exception:
            pass

    def goto(self, url, settle_ms=0, frame_name=None):
        """Navigate and return (url, html) of the CONTENT document.

        Frame-aware: legacy portals (e.g. WEBS, an ASP.NET frameset) put the real page inside a
        child frame; page.content() would return only the 438-byte <frameset> shell — which is
        exactly what a browser's "Save Page" captured for us. If `frame_name` is given, that frame's
        content/url is returned; otherwise the child frame with the most text wins; a page with no
        child frames returns the top document. Relative links must be resolved against the
        returned url (the frame's), not the top url."""
        self.page.goto(url, wait_until="domcontentloaded")
        try:
            self.page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        if settle_ms:
            self.page.wait_for_timeout(settle_ms)
        fr = self._content_frame(frame_name)
        try:
            fr.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        return fr.url, fr.content()

    def goto_in_frame(self, url, frame_name, settle_ms=0, home_url=None):
        """Navigate a CHILD FRAME to url and return (frame_url, frame_html).

        Why: frameset portals answer a top-level request for an inner page by bouncing back to the
        frameset home (observed on WEBS: page.goto(Search_BidDetails.aspx?ID=…) lands on Home.aspx
        every time), so the only way to reach an inner page is to navigate the content frame itself.
        If the current page has no frame called frame_name, home_url is loaded first to build the
        frameset; if there still is no such frame the site isn't a frameset and a plain goto is used."""
        def named():
            return next((f for f in self.page.frames if f.name == frame_name and f is not self.page.main_frame), None)
        fr = named()
        if fr is None and home_url:
            self.page.goto(home_url, wait_until="domcontentloaded")
            try:
                self.page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            fr = named()
        if fr is None:
            return self.goto(url, settle_ms=settle_ms, frame_name=frame_name)
        fr.goto(url, wait_until="domcontentloaded")
        try:
            self.page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        if settle_ms:
            self.page.wait_for_timeout(settle_ms)
        fr = self._content_frame(frame_name)
        return fr.url, fr.content()

    def click_in_frame(self, frame, selector, settle_ms=0, frame_name=None):
        """Click something that navigates the frame (a link or an ASP.NET postback button) and wait for
        the new document. Returns the (possibly new) Frame object to keep interacting with."""
        clicked = False
        try:
            with self.page.expect_event("framenavigated", timeout=20000):
                frame.click(selector); clicked = True
        except Exception as e:
            if not clicked:
                raise PortalError(f"click {selector!r} failed: {str(e)[:160]}")
            # clicked fine; the navigation event may simply have been faster than the listener
        try:
            self.page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        if settle_ms:
            self.page.wait_for_timeout(settle_ms)
        return self._content_frame(frame_name or frame.name or None)

    def _content_frame(self, frame_name=None):
        main = self.page.main_frame
        kids = [f for f in self.page.frames if f is not main and f.url and f.url != "about:blank"]
        if not kids:
            return main
        if frame_name:
            for f in kids:
                if f.name == frame_name:
                    return f
        def weight(f):
            try:
                return len(f.evaluate("document.body ? document.body.innerText : ''"))
            except Exception:
                return 0
        return max(kids, key=weight)

    def frames(self):
        """[(name, url)] for every frame on the current page (top first)."""
        return [(f.name or ("top" if f is self.page.main_frame else ""), f.url) for f in self.page.frames]

    def frame(self, frame_name=None):
        """The Playwright Frame to interact with (named child frame, else auto, else top)."""
        return self._content_frame(frame_name)

    def snapshot(self, dest_base):
        """Save top document + EVERY child frame's HTML + a full-page screenshot + frames.json.
        dest_base is a path prefix; writes <base>.html, <base>.frame-<name>.html, <base>.png,
        <base>.frames.json. Returns the list of files written."""
        written = []
        with open(dest_base + ".html", "w", encoding="utf-8") as fh:
            fh.write(self.page.content()); written.append(dest_base + ".html")
        meta = []
        for i, f in enumerate(self.page.frames):
            is_top = f is self.page.main_frame
            meta.append({"index": i, "name": f.name, "url": f.url, "top": is_top})
            if is_top or not f.url or f.url == "about:blank":
                continue
            tag = re.sub(r"[^\w.-]", "_", f.name or f"frame{i}")
            try:
                p = f"{dest_base}.frame-{tag}.html"
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(f.content()); written.append(p)
            except Exception as e:
                meta[-1]["error"] = str(e)[:120]
        with open(dest_base + ".frames.json", "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2); written.append(dest_base + ".frames.json")
        try:
            self.page.screenshot(path=dest_base + ".png", full_page=True); written.append(dest_base + ".png")
        except Exception:
            pass
        return written

    def download(self, url):
        """Fetch with the session's cookies. Returns (bytes, filename from Content-Disposition or None)."""
        resp = self.ctx.request.get(url)
        if not resp.ok:
            raise PortalError(f"HTTP {resp.status} for {url}")
        ctype = (resp.headers.get("content-type") or "").lower()
        if "text/html" in ctype:
            raise PortalError(f"got an HTML page instead of a document for {url} (login expired or viewer page)")
        name = None
        cd = resp.headers.get("content-disposition") or ""
        m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)", cd, re.I)
        if m:
            name = urllib.parse.unquote(m.group(1))
        return resp.body(), name

    def screenshot(self, path):
        self.page.screenshot(path=path, full_page=True)

    def wait_for_enter(self, prompt, wait_file=None, timeout_s=1800):
        """Block until the human is done in the headed window. Interactive: press Enter. Non-interactive
        (cron, an agent's shell, no TTY): pass wait_file — we poll until that file exists (someone runs
        `touch <file>`), then delete it. Gives up after timeout_s so an abandoned window can't hang a job."""
        if wait_file:
            print(f"{prompt}\n   (no TTY: waiting up to {timeout_s}s for signal file {wait_file})", flush=True)
            deadline = dt.datetime.now() + dt.timedelta(seconds=timeout_s)
            while not os.path.exists(wait_file):
                if dt.datetime.now() > deadline:
                    raise PortalError(f"timed out waiting for {wait_file}")
                self.page.wait_for_timeout(1000)          # keeps the browser event loop alive
            try: os.remove(wait_file)
            except OSError: pass
            return
        input(prompt)

    def close(self):
        try:
            self.save_state()                       # capture session cookies BEFORE the browser drops them
            self.ctx.close()
        finally:
            self._pw.stop()


# ----------------------------------------------------------------------------- orchestration
def links_for_opportunity(opp_dir):
    """URLs from initial-email/links.md and any followups/*/links.md."""
    urls = []
    cands = [os.path.join(opp_dir, "initial-email", "links.md")]
    fu = os.path.join(opp_dir, "initial-email", "followups")
    if os.path.isdir(fu):
        for d in sorted(os.listdir(fu)):
            cands.append(os.path.join(fu, d, "links.md"))
    for p in cands:
        if os.path.exists(p):
            for m in re.finditer(r"https?://[^\s<>\"')\]]+", open(p, encoding="utf-8").read()):
                u = m.group(0).rstrip(".,;:")
                if u not in urls:
                    urls.append(u)
    return urls


def _unique_path(dest_dir, fname, data):
    """Return a path to write: same name if new or identical content; suffixed if content differs."""
    target = os.path.join(dest_dir, fname)
    if not os.path.exists(target):
        return target, "new"
    if open(target, "rb").read() == data:
        return target, "identical"
    stem, ext = os.path.splitext(fname); n = 1
    while os.path.exists(os.path.join(dest_dir, f"{stem} ({n}){ext}")):
        n += 1
    return os.path.join(dest_dir, f"{stem} ({n}){ext}"), "renamed"


def _opportunity_json(opp_dir):
    p = os.path.join(opp_dir, "opportunity.json")
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def search_terms(oj, search=None):
    """(number, title) to look a solicitation up with when the email linked only the portal's front
    door. An explicit --search wins; otherwise opportunity.json's solicitation_number / title (the
    poller stores the subject as the title; adapters derive candidate phrases from it)."""
    number = (search or {}).get("number") or oj.get("solicitation_number") or oj.get("number") or None
    title = (search or {}).get("title") or oj.get("title") or None
    if title and re.fullmatch(r"\{\{.*\}\}", str(title)):        # unfilled template placeholder
        title = None
    return (str(number).strip() if number else None), (str(title).strip() if title else None)


def _write_portal_record(opp_dir, key, rec):
    """rfp/portal-record.json (+ .md): what the portal's own solicitation page states. Merged by url so
    re-fetches refresh in place. bidkit.brief reads the JSON (dates, estimated value, contact, files)."""
    rfp_dir = os.path.join(opp_dir, "rfp"); os.makedirs(rfp_dir, exist_ok=True)
    jp = os.path.join(rfp_dir, "portal-record.json")
    try:
        recs = json.load(open(jp, encoding="utf-8")) if os.path.exists(jp) else []
        if not isinstance(recs, list): recs = []
    except Exception:
        recs = []
    rec = dict(rec, portal_key=key, captured_at=dt.datetime.now(dt.timezone.utc).isoformat())
    recs = [r for r in recs if r.get("url") != rec.get("url")] + [rec]
    with open(jp, "w", encoding="utf-8") as fh:
        json.dump(recs, fh, indent=2, ensure_ascii=False)
    L = ["# Portal record(s) — what the portal's own page states (DETECTED; confirm in the RFP)", ""]
    for r in recs:
        L += [f"## {r.get('title') or '(untitled)'}", f"- portal: `{r.get('portal_key')}` — {r.get('url')}",
              f"- organization: {r.get('organization') or '—'}", f"- reference #: **{r.get('reference') or '—'}**  (portal id {r.get('system_id') or '—'})",
              f"- posted: {r.get('posted') or '—'}   closed: **{r.get('closed') or '—'}**",
              f"- estimated initial contract value: **{r.get('estimated_value_text') or '— (blank on the portal)'}**"]
        c = r.get("contact") or {}
        L.append(f"- contact: {c.get('name') or '—'} — {c.get('email') or ''} {c.get('phone') or ''}".rstrip(" —"))
        if r.get("documents"):
            L += ["- documents:"] + [f"  - {d['name']}" for d in r["documents"]]
        if r.get("amendments"):
            L += ["- amendments:"] + [f"  - {a.get('date') or ''} {a['name']}".strip() for a in r["amendments"]]
        if r.get("description"):
            L += ["", f"> {r['description'][:1200]}"]
        L += ["", f"_captured {r.get('captured_at')}_", ""]
    with open(os.path.join(rfp_dir, "portal-record.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    return jp


def _write_competitors(opp_dir, key, rows, page_url):
    """research/portal-vendors-downloading.csv (+ .md): vendors the portal lists as having downloaded
    the solicitation. Competitive intelligence for the research step — who else is looking."""
    import csv
    rd = os.path.join(opp_dir, "research"); os.makedirs(rd, exist_ok=True)
    when = dt.datetime.now(dt.timezone.utc).isoformat()
    cp = os.path.join(rd, "portal-vendors-downloading.csv")
    with open(cp, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["company", "email", "phone", "status", "portal", "source_url", "captured_at"])
        for r in rows:
            w.writerow([r.get("company", ""), r.get("email", ""), r.get("phone", ""), r.get("status", ""), key, page_url, when])
    L = [f"# Vendors downloading — {len(rows)} listed by `{key}` (captured {when})", "",
         "_The portal shows only vendors who opted in to information sharing, so this is a floor, not the field. "
         "Status flags are the portal's certification codes (e.g. minority/women/veteran/small business). "
         "Contact details are in the CSV; use them for teaming outreach, not marketing._", "",
         "| Company | Status |", "|---|---|"] + [f"| {r.get('company','')} | {r.get('status','')} |" for r in rows] + [""]
    with open(os.path.join(rd, "portal-vendors-downloading.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    return cp


def _with_login(adapter, sess, spec, key, entry, step):
    """Run step(); if the portal answered with its login page, sign in with stored credentials (when the
    adapter has a grounded login form and portals.json names a username) and run step() once more."""
    try:
        return step()
    except NotLoggedIn as e:
        user, pw = resolve_credentials(spec)
        if not (user and pw):
            raise NotLoggedIn(f"{e} — run: python3 -m bidkit.portal login {key}   (or store credentials: portals.json username + "
                              f"password_env / password_keychain_service for unattended re-login)")
        if not adapter.login(sess, user, pw):
            raise PortalError(f"automatic login as {user} failed (wrong password or the login page changed) — run: python3 -m bidkit.portal login {key}")
        entry["login"] = f"session had expired; logged in again as {user}"
        return step()


def fetch_for_opportunity(opp_dir, urls=None, portals=None, session_factory=None, headless=True, dry_run=False,
                          search=None, competitors=True):
    """Open each portal URL, download its documents into rfp/, record everything in rfp/portal-fetch.md.
    session_factory(profile_dir, headless) -> session; defaults to PlaywrightSession.
    search: optional {"portal": "<domain>", "number": "...", "title": "..."} used when the email
    named a solicitation but carried no link — the adapter's find_opportunity() locates the page.
    A URL that is only the portal's front door (notification emails usually say "log in to view")
    triggers the same search using opportunity.json's solicitation_number/title.
    Grounded adapters also record the portal's own solicitation record (rfp/portal-record.json) and,
    when competitors=True, the vendors-downloading list (research/portal-vendors-downloading.csv).
    Returns a report dict."""
    portals = portals or {}
    urls = list(urls or links_for_opportunity(opp_dir))
    rfp_dir = os.path.join(opp_dir, "rfp")
    report = {"opportunity": opp_dir, "started": dt.datetime.now(dt.timezone.utc).isoformat(), "pages": [], "dry_run": dry_run}
    factory = session_factory or (lambda prof, hl: PlaywrightSession(prof, headless=hl))
    oj = _opportunity_json(opp_dir)
    if not urls and search and search.get("portal"):
        # no link in the email: ask the portal adapter to find the opportunity page
        key = search["portal"].lower(); spec = portals.get(key, {})
        adapter = ADAPTERS.get(spec.get("adapter", "generic"), PortalAdapter)(spec)
        if adapter.name == "generic":
            for cls in ADAPTERS.values():
                if any(key == d or key.endswith("." + d) for d in cls.domains): adapter = cls(spec)
        entry = {"url": None, "portal": key, "adapter": adapter.name, "documents": [], "errors": [], "search": search}
        report["pages"].append(entry)
        if dry_run:
            entry["profile_dir"] = profile_dir_for(key, spec); return report
        sess = None
        try:
            sess = factory(profile_dir_for(key, spec), headless)
            number, title = search_terms(oj, search)
            entry["search"] = {"number": number, "title": title}
            found = _with_login(adapter, sess, spec, key, entry, lambda: adapter.find_opportunity(sess, number=number, title=title))
            entry["url"] = found; urls = [found]
        except PortalError as e:
            entry["errors"].append(str(e))
        except Exception as e:                              # a browser/automation failure must not kill the run
            entry["errors"].append(f"{type(e).__name__}: {str(e)[:200]}")
        finally:
            if sess is not None:
                try: sess.close()
                except Exception: pass
        if not urls:
            _write_report(rfp_dir, report); return report
        report["pages"].pop()          # the found url is processed by the normal loop below
    if not urls:
        report["note"] = "no links found (initial-email/links.md missing or empty; pass --url or --search)"
        return report
    for url in urls:
        adapter, key = select_adapter(url, portals)
        entry = {"url": url, "portal": key, "adapter": adapter.name, "documents": [], "errors": []}
        report["pages"].append(entry)
        if dry_run:
            entry["profile_dir"] = profile_dir_for(key, portals.get(key)); continue
        sess = None
        spec = portals.get(key) or {}
        try:
            sess = factory(profile_dir_for(key, spec), headless)
            number = title = None
            if adapter.is_landing_page(url):
                # the email linked the portal's front door, not the solicitation: look it up
                number, title = search_terms(oj, search if search and search.get("portal", key) == key else None)
                if not (number or title):
                    entry["errors"].append("link is the portal's front door and opportunity.json has no solicitation_number/title "
                                           "to search for — pass --url <opportunity page> or --search <domain>:<number>")
                    continue
                entry["search"] = {"number": number, "title": title}

            def step():
                target = url
                if entry.get("search"):
                    target = adapter.find_opportunity(sess, number=number, title=title)
                    entry["found_url"] = target
                final_url, page_html = adapter.open(sess, target)
                if not adapter.is_logged_in(page_html):
                    raise NotLoggedIn("portal answered with its login page")
                return final_url, page_html
            final_url, page_html = _with_login(adapter, sess, spec, key, entry, step)
            entry["final_url"] = final_url
            os.makedirs(rfp_dir, exist_ok=True)
            stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            snap_base = os.path.join(rfp_dir, f"portal-page-{stamp}")
            if hasattr(sess, "snapshot"):
                entry["snapshot"] = [os.path.basename(p) for p in sess.snapshot(snap_base)]
            else:
                with open(snap_base + ".html", "w", encoding="utf-8") as fh:
                    fh.write(page_html)
                try:
                    sess.screenshot(snap_base + ".png")
                except Exception as e:
                    entry["errors"].append(f"screenshot: {str(e)[:120]}")
            try:
                rec = adapter.page_metadata(sess, page_html, final_url)
            except Exception as e:
                rec = {}; entry["errors"].append(f"portal record: {str(e)[:120]}")
            if rec:
                entry["record"] = {k: rec.get(k) for k in ("system_id", "reference", "title", "organization", "posted", "closed", "estimated_value_text")}
                entry["record_file"] = os.path.basename(_write_portal_record(opp_dir, key, rec))
            for ln, fname in adapter.document_links(extract_links(page_html, final_url)):
                try:
                    data, suggested = sess.download(ln.href)
                    name = safe_filename(suggested) if suggested else fname
                    if not os.path.splitext(name)[1] and suggested is None:
                        # no extension anywhere: sniff the magic bytes
                        name += ".pdf" if data[:4] == b"%PDF" else ".zip" if data[:2] == b"PK" else ".bin"
                    path, status = _unique_path(rfp_dir, name, data)
                    if status != "identical":
                        with open(path, "wb") as fh:
                            fh.write(data)
                    entry["documents"].append({"name": os.path.basename(path), "bytes": len(data), "status": status, "href": ln.href})
                except PortalError as e:
                    entry["errors"].append(f"{fname}: {e}")
            if competitors:
                try:
                    rows = adapter.competitor_list(sess)      # navigates away from the page: keep it LAST
                except Exception as e:
                    rows = None; entry["errors"].append(f"vendors-downloading list: {str(e)[:120]}")
                if rows:
                    entry["competitors"] = len(rows)
                    entry["competitors_file"] = os.path.relpath(_write_competitors(opp_dir, key, rows, final_url), opp_dir)
        except NotLoggedIn as e:
            entry["errors"].append(f"NOT LOGGED IN — {e}" if "portal login" in str(e) else f"NOT LOGGED IN — run: python3 -m bidkit.portal login {key} ({e})")
        except PortalError as e:
            entry["errors"].append(str(e))
        except Exception as e:                              # a browser/automation failure must not kill the run
            entry["errors"].append(f"{type(e).__name__}: {str(e)[:200]}")
        finally:
            if sess is not None:
                try: sess.close()
                except Exception: pass
    if not dry_run:
        _write_report(rfp_dir, report)
    return report


def _write_report(rfp_dir, report):
    os.makedirs(rfp_dir, exist_ok=True)
    lines = [f"# Portal fetch — {report['started']}", ""]
    for p in report["pages"]:
        lines += [f"## {p['url']}", f"- portal: `{p['portal']}` (adapter `{p['adapter']}`)" + (f"  → final URL `{p.get('final_url')}`" if p.get("final_url") else "")]
        if p.get("login"):
            lines.append(f"- login: {p['login']}")
        if p.get("search"):
            lines.append(f"- searched for number={p['search'].get('number')!r} title={p['search'].get('title')!r}" + (f" → found `{p['found_url']}`" if p.get("found_url") else ""))
        r = p.get("record")
        if r:
            lines.append(f"- portal record: **{r.get('title')}** — {r.get('organization')}; ref # **{r.get('reference')}**; posted {r.get('posted')}, "
                         f"**closes {r.get('closed')}**; estimated value {r.get('estimated_value_text') or '(blank)'} → `{p.get('record_file')}`")
        if p.get("competitors"):
            lines.append(f"- vendors downloading: {p['competitors']} listed → `{p.get('competitors_file')}`")
        for d in p["documents"]:
            lines.append(f"- {d['status']:9s} `{d['name']}` ({d['bytes']:,} bytes)")
        for e in p["errors"]:
            lines.append(f"- **ERROR** {e}")
        if not p["documents"] and not p["errors"]:
            lines.append("- no document links recognised on this page (check the adapter / add one)")
        lines.append("")
    lines += ["_Snapshots: portal-page-*.html / .png in this folder. Verify every file with "
              "`bidkit.pdf_verify` / `bidkit.xlsx_verify` before relying on it._", ""]
    with open(os.path.join(rfp_dir, "portal-fetch.md"), "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


DEFAULT_CAPTURE_ROOT = "portal-captures"


def capture(portal_key, page_name, portals, url=None, headed=False, out_root=None, session_factory=None, wait_file=None):
    """Save a portal page WITH ALL ITS FRAMES for grounding an adapter: <root>/<portal>/<page_name>/
    page.html, page.frame-<name>.html, page.frames.json, page.png, capture.json (url, time, frames).
    --headed: opens visibly, lets you log in / navigate to the exact page, then press Enter.
    Captures may contain your account name and ASP.NET view-state; the folder is gitignored — review
    and scrub before promoting one to bidkit/tests/fixtures/."""
    spec = portals.get(portal_key.lower(), {})
    adapter = ADAPTERS.get(spec.get("adapter", "generic"), PortalAdapter)(spec)
    if adapter.name == "generic":
        for cls in ADAPTERS.values():
            if any(portal_key.lower() == d or portal_key.lower().endswith("." + d) for d in cls.domains):
                adapter = cls(spec)
    target = url or spec.get("login_url") or adapter.login_url or f"https://{portal_key}/"
    root = out_root or DEFAULT_CAPTURE_ROOT
    dest = os.path.join(root, re.sub(r"[^\w.-]", "_", portal_key), re.sub(r"[^\w.-]", "_", page_name))
    os.makedirs(dest, exist_ok=True)
    factory = session_factory or (lambda p, hl: PlaywrightSession(p, headless=hl))
    sess = factory(profile_dir_for(portal_key, spec), not headed)
    try:
        sess.goto(target, settle_ms=adapter.wait_after_load_ms)
        if headed:
            sess.wait_for_enter(f"Navigate to the page you want captured as {page_name!r} (log in if needed), then press Enter… ", wait_file=wait_file)
        files = sess.snapshot(os.path.join(dest, "page"))
        frames = sess.frames() if hasattr(sess, "frames") else []
        meta = {"portal": portal_key, "page_name": page_name, "requested_url": target,
                "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(), "frames": frames,
                "files": [os.path.basename(f) for f in files],
                "next": "inspect page.frame-*.html for the content frame; set frame_name / doc_href_pattern / "
                        "search selectors in inbox/portals.json, or promote a scrubbed copy to bidkit/tests/fixtures/"}
        with open(os.path.join(dest, "capture.json"), "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)
        return dest, meta
    finally:
        sess.close()


def login(portal_key, portals, url=None, session_factory=None, wait_file=None, auto=False):
    """Open a HEADED browser on the portal so the human logs in once; cookies persist in the profile.
    auto=True: headless, using stored credentials (portals.json username + password_env/keychain) through
    the adapter's grounded login form — what cron needs when a portal expires sessions (WEBS: ~20 min)."""
    spec = portals.get(portal_key.lower(), {})
    adapter = ADAPTERS.get(spec.get("adapter", "generic"), PortalAdapter)(spec)
    for cls in ADAPTERS.values():                      # domain-claimed adapter if not configured
        if adapter.name == "generic" and any(portal_key.lower().endswith(d) for d in cls.domains):
            adapter = cls(spec)
    target = url or spec.get("login_url") or adapter.login_url or f"https://{portal_key}/"
    prof = profile_dir_for(portal_key, spec)
    factory = session_factory or (lambda p, hl: PlaywrightSession(p, headless=hl))
    if auto:
        user, pw = resolve_credentials(spec)
        if not (user and pw):
            raise PortalError(f"no stored credentials for {portal_key}: set portals.json → username and password_env or "
                              f"password_keychain_service (macOS: security add-generic-password -s <service> -a <username> -w)")
        sess = factory(prof, True)
        try:
            ok = adapter.login(sess, user, pw)
            return {"portal": portal_key, "profile_dir": prof, "logged_in": ok, "username": user, "mode": "auto"}
        finally:
            sess.close()
    sess = factory(prof, False)
    try:
        sess.goto(target)
        sess.wait_for_enter(f"Log in to {portal_key} in the browser window, then press Enter here to save the session… ", wait_file=wait_file)
        kw = {"frame_name": adapter.frame_name} if adapter.frame_name else {}
        try:
            _, page_html = sess.goto(target, **kw)
        except TypeError:
            _, page_html = sess.goto(target)
        ok = adapter.is_logged_in(page_html)
        return {"portal": portal_key, "profile_dir": prof, "logged_in": ok, "mode": "headed"}
    finally:
        sess.close()


def parse_search_arg(value):
    """'des.wa.gov:2026_01' → number; 'des.wa.gov:ID=12345' → number 'ID=12345' (adapters recognise the
    portal-id form); 'des.wa.gov:title=Records Management System' → title."""
    dom, _, q = value.partition(":")
    q = q.strip()
    search = {"portal": dom.strip().lower(), "number": None, "title": None}
    if re.match(r"(?i)^title\s*=", q):
        search["title"] = q.split("=", 1)[1].strip() or None
    else:
        search["number"] = q or None
    return search


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="download portal documents into <opp>/rfp/")
    f.add_argument("opportunity"); f.add_argument("--url", action="append"); f.add_argument("--dry-run", action="store_true")
    f.add_argument("--headed", action="store_true"); f.add_argument("--portals", default=None)
    f.add_argument("--search", help='"<portal-domain>:<query>" — find the page when the email had no link or linked only the portal home. '
                                    'query = the solicitation/reference number, "ID=<portal id>", or "title=<words>"')
    f.add_argument("--no-competitors", action="store_true", help="skip the portal's vendors-downloading list")
    l = sub.add_parser("login", help="open a headed browser to log in once (cookies persist)")
    l.add_argument("portal"); l.add_argument("--url"); l.add_argument("--portals", default=None)
    l.add_argument("--wait-for-file", help="non-interactive: keep the window open until this file exists (touch it when logged in)")
    l.add_argument("--auto", action="store_true", help="headless login with stored credentials (portals.json username + password_env/keychain)")
    k = sub.add_parser("links", help="show links + adapter choice; no browser"); k.add_argument("opportunity"); k.add_argument("--portals", default=None)
    c = sub.add_parser("capture", help="save a portal page + ALL frames to portal-captures/ for grounding an adapter")
    c.add_argument("portal"); c.add_argument("name"); c.add_argument("--url"); c.add_argument("--headed", action="store_true")
    c.add_argument("--out", default=None); c.add_argument("--portals", default=None)
    c.add_argument("--wait-for-file", help="with --headed and no TTY: proceed when this file exists")
    a = ap.parse_args(argv)
    portals_path = a.portals or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "inbox", "portals.json")
    portals = load_portals(os.path.normpath(portals_path))
    try:
        if a.cmd == "links":
            for u in links_for_opportunity(a.opportunity):
                ad, key = select_adapter(u, portals)
                print(f"{ad.name:14s} {key:28s} {u}")
            return 0
        if a.cmd == "login":
            r = login(a.portal, portals, url=a.url, wait_file=a.wait_for_file, auto=a.auto)
            who = f" as {r['username']}" if r.get("username") else ""
            print(f"profile {r['profile_dir']}: {'logged in' + who if r['logged_in'] else 'still NOT logged in (login page detected)'}")
            return 0 if r["logged_in"] else 1
        if a.cmd == "capture":
            dest, meta = capture(a.portal, a.name, portals, url=a.url, headed=a.headed, out_root=a.out, wait_file=a.wait_for_file)
            print(f"captured -> {dest}/")
            for fr in meta["frames"]: print(f"   frame {fr[0] or '(unnamed)':12s} {fr[1]}")
            print(f"   files: {', '.join(meta['files'])}\n   {meta['next']}")
            return 0
        search = parse_search_arg(a.search) if a.search else None
        rep = fetch_for_opportunity(a.opportunity, urls=a.url, portals=portals, headless=not a.headed, dry_run=a.dry_run, search=search,
                                    competitors=not a.no_competitors)
        if rep.get("note"): print(rep["note"]); return 1
        rc = 0
        for p in rep["pages"]:
            print(f"{p['url']}\n   adapter={p['adapter']} portal={p['portal']}" + (f" profile={p.get('profile_dir')} [DRY RUN]" if a.dry_run else ""))
            if p.get("found_url"): print(f"   found via search: {p['found_url']}")
            if p.get("record"): print(f"   portal record: {p['record'].get('reference')} | {p['record'].get('title')} | closes {p['record'].get('closed')} | est. value {p['record'].get('estimated_value_text') or '(blank)'}")
            if p.get("competitors"): print(f"   vendors downloading: {p['competitors']} -> {p.get('competitors_file')}")
            for d in p["documents"]: print(f"   {d['status']:9s} {d['name']} ({d['bytes']:,} B)")
            for e in p["errors"]: print(f"   ERROR {e}"); rc = 1
        if not a.dry_run: print(f"report: {os.path.join(a.opportunity, 'rfp', 'portal-fetch.md')}")
        return rc
    except PortalError as e:
        print(f"PORTAL ERROR: {e}"); return 1


if __name__ == "__main__":
    sys.exit(main())
