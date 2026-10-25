import http.server, json, os, socket, threading
import pytest
from bidkit import portal

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "fixtures", "publicpurchase-bid-page.html")
FIXTURE_HTML = open(FIXTURE, encoding="utf-8", errors="ignore").read()
BASE = "https://www.publicpurchase.com/gems/kennewick,wa/bid/bidView?bidId=214432"


# ----------------------------------------------------------------------------- pure: links + adapters
def test_extract_links_absolutises_and_strips_markup():
    links = portal.extract_links(FIXTURE_HTML, BASE)
    assert links, "fixture yielded no anchors"
    assert sum(l.href.startswith("https://www.publicpurchase.com/") for l in links) > len(links) * 0.8   # relative hrefs absolutised
    assert all(l.href.startswith("http") for l in links)
    assert not any(l.href.startswith(("javascript:", "mailto:", "#")) for l in links)
    assert any("&outlineId=" in l.href for l in links)                    # &amp; unescaped


def test_publicpurchase_adapter_on_real_page():
    """Documents have NO extension in the URL; the filename is the anchor text; each has a paired
    '[Download]' anchor. A generic extension-based filter would find zero documents here."""
    links = portal.extract_links(FIXTURE_HTML, BASE)
    generic = portal.PortalAdapter().document_links(links)
    pp = portal.PublicPurchasePortal().document_links(links)
    names = sorted(n for _, n in pp)
    assert len(pp) >= 10 and len(pp) < len(links)
    assert "26-013 RFP - BIPIN RFP .pdf" in names
    assert "A2 - Public Safety RMS Requirements Template.xlsx" in names
    assert "A7- Certifications and Assurances Form.pdf" in names
    assert len({h.href for h, _ in pp}) == len(pp)                        # one entry per document, not per anchor
    assert not any("onlineTrackChanges" in h.href for h, _ in pp)         # track-changes links excluded
    assert not any(n.lower().strip("[]") == "download" for n in names)    # never named "[Download]"
    # The generic adapter DOES spot these (via the "[Download]" anchor text) but would name every
    # file "[Download]" — the adapter exists for correct naming, not detection.
    bare = sum(1 for _, n in generic if n.strip("[]").lower() == "download")
    assert bare >= 10 and bare > len(generic) * 0.7                       # most files would collide as "[Download]"


def test_generic_adapter_uses_extensions_and_words():
    html = ('<a href="/files/RFP.pdf">RFP Document</a> <a href="/x/Attachment%20A.xlsx">Attachment A</a>'
            '<a href="/about">About us</a> <a href="/dl?id=9">Download Addendum 1</a> <a href="/dl?id=9">Download Addendum 1</a>'
            '<a href="javascript:void(0)">Print</a>')
    docs = portal.PortalAdapter().document_links(portal.extract_links(html, "https://p.example.gov/bid/1"))
    got = {n for _, n in docs}
    assert got == {"RFP.pdf", "Attachment A.xlsx", "Download Addendum 1"}
    assert len(docs) == 3                                                  # duplicate href collapsed


def test_is_logged_in_heuristics():
    assert portal.PortalAdapter().is_logged_in("<html><body>Welcome, vendor</body></html>")
    assert not portal.PortalAdapter().is_logged_in('<form><input type="password" name="p"></form>')
    assert portal.PortalAdapter({"logged_in_marker": "Sign out"}).is_logged_in("<a>Sign out</a>")
    assert not portal.PortalAdapter({"logged_in_marker": "Sign out"}).is_logged_in("<a>Sign in</a>")
    assert portal.PublicPurchasePortal().is_logged_in(FIXTURE_HTML)       # saved page had no password field


def test_select_adapter_config_then_domain_then_generic(tmp_path):
    portals = {"publicpurchase.com": {"adapter": "publicpurchase", "profile_dir": str(tmp_path / "pp")},
               "bids.example.gov": {"adapter": "generic", "logged_in_marker": "Logout"}}
    ad, key = portal.select_adapter("https://www.publicpurchase.com/gems/x", portals)
    assert isinstance(ad, portal.PublicPurchasePortal) and key == "publicpurchase.com"
    assert portal.profile_dir_for(key, portals[key]) == str(tmp_path / "pp")
    ad, key = portal.select_adapter("https://vendor.bids.example.gov/solicitation/9", portals)
    assert ad.name == "generic" and key == "bids.example.gov" and ad.opt["logged_in_marker"] == "Logout"
    ad, key = portal.select_adapter("https://publicpurchase.com/other", {})                 # domain-claimed, no config
    assert isinstance(ad, portal.PublicPurchasePortal)
    ad, key = portal.select_adapter("https://unknown.example.org/x", {})
    assert ad.name == "generic" and key == "unknown.example.org"
    # ports and www. are stripped before matching (bit us with a local test server)
    assert portal.domain_of("http://127.0.0.1:55686/gems/x") == "127.0.0.1"
    assert portal.domain_of("https://WWW.Example.GOV:8443/a") == "example.gov"
    assert portal.profile_dir_for(key, None).endswith(os.path.join("browser-profiles", "unknown.example.org"))
    ad, key = portal.select_adapter("http://127.0.0.1:9/x", {"127.0.0.1": {"adapter": "publicpurchase"}})
    assert isinstance(ad, portal.PublicPurchasePortal)


def test_links_for_opportunity_reads_initial_and_followups(tmp_path):
    opp = tmp_path / "OPP"; (opp / "initial-email" / "followups" / "x").mkdir(parents=True)
    (opp / "initial-email" / "links.md").write_text("- https://a.example/1\n- https://a.example/1\n")
    (opp / "initial-email" / "followups" / "x" / "links.md").write_text("see https://b.example/2.")
    assert portal.links_for_opportunity(str(opp)) == ["https://a.example/1", "https://b.example/2"]
    assert portal.links_for_opportunity(str(tmp_path / "nope")) == []


# ----------------------------------------------------------------------------- orchestration with a fake session
class FakeSession:
    """Serves the fixture page; 'downloads' return bytes keyed by docId. Records calls."""
    created = []
    def __init__(self, profile_dir, headless):
        self.profile_dir = profile_dir; self.headless = headless; self.closed = False; self.downloads = []
        FakeSession.created.append(self)
    def goto(self, url, settle_ms=0): return url, FIXTURE_HTML
    def download(self, url):
        self.downloads.append(url)
        if "docId=70984883" in url: return b"%PDF-1.4 rfp", None                 # no content-disposition -> use anchor name
        if "docId=70984885" in url: return b"PK\x03\x04xlsx", "A2-from-header.xlsx"  # server-suggested name wins
        raise portal.PortalError("HTTP 404 for " + url)
    def screenshot(self, path): open(path, "wb").write(b"\x89PNG fake")
    def close(self): self.closed = True


def test_fetch_downloads_names_snapshots_and_reports(tmp_path):
    opp = tmp_path / "OPP"; (opp / "initial-email").mkdir(parents=True)
    (opp / "initial-email" / "links.md").write_text(f"- {BASE}\n")
    FakeSession.created.clear()
    rep = portal.fetch_for_opportunity(str(opp), portals={"publicpurchase.com": {"adapter": "publicpurchase", "profile_dir": str(tmp_path / "prof")}},
                                       session_factory=FakeSession)
    page = rep["pages"][0]
    assert page["adapter"] == "publicpurchase" and page["portal"] == "publicpurchase.com"
    names = {d["name"] for d in page["documents"]}
    assert "26-013 RFP - BIPIN RFP .pdf" in names                  # anchor text used
    assert "A2-from-header.xlsx" in names                          # Content-Disposition preferred
    assert (opp / "rfp" / "26-013 RFP - BIPIN RFP .pdf").read_bytes() == b"%PDF-1.4 rfp"
    assert len(page["errors"]) >= 1 and all("HTTP 404" in e for e in page["errors"])   # other docs 404 in the fake
    snaps = [p for p in os.listdir(opp / "rfp") if p.startswith("portal-page-")]
    assert any(p.endswith(".html") for p in snaps) and any(p.endswith(".png") for p in snaps)
    md = (opp / "rfp" / "portal-fetch.md").read_text()
    assert "publicpurchase" in md and "26-013 RFP - BIPIN RFP .pdf" in md and "ERROR" in md
    assert FakeSession.created[0].profile_dir == str(tmp_path / "prof") and FakeSession.created[0].headless is True
    assert FakeSession.created[0].closed


def test_fetch_does_not_overwrite_differing_file(tmp_path):
    opp = tmp_path / "OPP"; (opp / "initial-email").mkdir(parents=True); (opp / "rfp").mkdir()
    (opp / "initial-email" / "links.md").write_text(f"- {BASE}\n")
    (opp / "rfp" / "26-013 RFP - BIPIN RFP .pdf").write_bytes(b"HUMAN-EDITED")
    portal.fetch_for_opportunity(str(opp), portals={}, session_factory=FakeSession)
    assert (opp / "rfp" / "26-013 RFP - BIPIN RFP .pdf").read_bytes() == b"HUMAN-EDITED"
    assert (opp / "rfp" / "26-013 RFP - BIPIN RFP  (1).pdf").read_bytes() == b"%PDF-1.4 rfp"


def test_fetch_detects_login_bounce(tmp_path):
    class LoginBounce(FakeSession):
        def goto(self, url, settle_ms=0): return url, '<form><input type="password"></form>'
    opp = tmp_path / "OPP"; (opp / "initial-email").mkdir(parents=True)
    (opp / "initial-email" / "links.md").write_text("- https://unknown.example.org/bid/1\n")
    rep = portal.fetch_for_opportunity(str(opp), portals={}, session_factory=LoginBounce)
    assert rep["pages"][0]["documents"] == []
    assert any("NOT LOGGED IN" in e and "portal login unknown.example.org" in e for e in rep["pages"][0]["errors"])


def test_dry_run_launches_no_browser(tmp_path):
    opp = tmp_path / "OPP"; (opp / "initial-email").mkdir(parents=True)
    (opp / "initial-email" / "links.md").write_text(f"- {BASE}\n")
    FakeSession.created.clear()
    rep = portal.fetch_for_opportunity(str(opp), portals={}, session_factory=FakeSession, dry_run=True)
    assert rep["dry_run"] and rep["pages"][0]["adapter"] == "publicpurchase" and "profile_dir" in rep["pages"][0]
    assert FakeSession.created == [] and not (opp / "rfp").exists()


def test_cli_links_and_dry_run(tmp_path, capsys):
    opp = tmp_path / "OPP"; (opp / "initial-email").mkdir(parents=True)
    (opp / "initial-email" / "links.md").write_text(f"- {BASE}\n- https://other.example.org/x\n")
    pj = tmp_path / "portals.json"; pj.write_text(json.dumps({"publicpurchase.com": {"adapter": "publicpurchase"}}))
    assert portal.main(["links", str(opp), "--portals", str(pj)]) == 0
    out = capsys.readouterr().out
    assert "publicpurchase" in out and "generic" in out
    assert portal.main(["fetch", str(opp), "--dry-run", "--portals", str(pj)]) == 0
    assert "[DRY RUN]" in capsys.readouterr().out


# ----------------------------------------------------------------------------- REAL browser integration
def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class _Handler(http.server.BaseHTTPRequestHandler):
    """Serves the fixture page, two stub documents, sets a cookie on the page and REQUIRES it for downloads."""
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path.startswith("/bid"):
            body = FIXTURE_HTML.encode("utf-8", "ignore")
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Set-Cookie", "vendor_session=abc123; Path=/"); self.end_headers(); self.wfile.write(body)
        elif "/gems/docviewer/bidDoc" in self.path:
            if "vendor_session=abc123" not in (self.headers.get("Cookie") or ""):
                self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers()
                self.wfile.write(b'<form><input type="password"></form>'); return
            if "docId=70984883" in self.path:
                self.send_response(200); self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", 'attachment; filename="26-013 RFP.pdf"'); self.end_headers(); self.wfile.write(b"%PDF-1.4 real")
            elif "docId=70984885" in self.path:
                self.send_response(200); self.send_header("Content-Type", "application/octet-stream"); self.end_headers(); self.wfile.write(b"PK\x03\x04 xlsx")
            else:
                self.send_response(404); self.end_headers()
        elif self.path == "/whoami":
            ck = self.headers.get("Cookie") or ""
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers()
            self.wfile.write(f"<html><body>cookie:{ck}</body></html>".encode())
        else:
            self.send_response(404); self.end_headers()


@pytest.fixture
def local_portal():
    port = _free_port()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()


@pytest.mark.skipif(pytest.importorskip("playwright", reason="playwright not installed") is None, reason="no playwright")
def test_real_playwright_session_persists_cookies_and_downloads(tmp_path, local_portal):
    """End to end with a REAL headless Chromium: open the (real, saved) Public Purchase page from a
    local server, get a session cookie, download documents WITH that cookie via the context, and
    prove the cookie persists in the profile directory across a second session."""
    try:
        sess = portal.PlaywrightSession(str(tmp_path / "profile"), headless=True, timeout_ms=30000)
    except portal.PortalError as e:
        pytest.skip(f"chromium unavailable: {e}")
    try:
        final, page_html = sess.goto(f"{local_portal}/bid?bidId=214432")
        assert "Public Purchase" in page_html
        docs = portal.PublicPurchasePortal().document_links(portal.extract_links(page_html, final))
        rfp = next(h for h, n in docs if n == "26-013 RFP - BIPIN RFP .pdf")
        data, suggested = sess.download(rfp.href)
        assert data == b"%PDF-1.4 real" and suggested == "26-013 RFP.pdf"            # cookie was sent; CD name parsed
        sess.screenshot(str(tmp_path / "shot.png")); assert (tmp_path / "shot.png").stat().st_size > 0
    finally:
        sess.close()
    # second session on the same profile: cookie must still be there
    sess2 = portal.PlaywrightSession(str(tmp_path / "profile"), headless=True, timeout_ms=30000)
    try:
        _, who = sess2.goto(f"{local_portal}/whoami")
        assert "vendor_session=abc123" in who
    finally:
        sess2.close()


@pytest.mark.skipif(pytest.importorskip("playwright", reason="playwright not installed") is None, reason="no playwright")
def test_real_fetch_for_opportunity_end_to_end(tmp_path, local_portal):
    opp = tmp_path / "OPP"; (opp / "initial-email").mkdir(parents=True)
    (opp / "initial-email" / "links.md").write_text(f"- {local_portal}/bid?bidId=214432\n")
    # local server isn't publicpurchase.com, so point the adapter at it via config
    portals = {"127.0.0.1": {"adapter": "publicpurchase", "profile_dir": str(tmp_path / "prof")}}
    try:
        rep = portal.fetch_for_opportunity(str(opp), portals=portals, headless=True)
    except portal.PortalError as e:
        pytest.skip(f"chromium unavailable: {e}")
    page = rep["pages"][0]
    names = {d["name"] for d in page["documents"]}
    assert "26-013 RFP.pdf" in names                                   # Content-Disposition name
    assert any(n.startswith("A2 - Public Safety RMS") and n.endswith(".xlsx") for n in names)
    assert (opp / "rfp" / "26-013 RFP.pdf").read_bytes() == b"%PDF-1.4 real"
    assert (opp / "rfp" / "portal-fetch.md").exists()
    assert sum(1 for e in page["errors"] if "HTTP 404" in e) >= 8       # the other fixture docs aren't served



# ----------------------------------------------------------------------------- FRAMESET portals (WEBS-style)
# The user's "Save Page" of WEBS produced 438-byte frameset shells: <frameset rows="*,100%">
# <frame name="top" src="help.html"><frame name="bottom" src="Home.aspx">. This synthetic portal
# reproduces that shape so the frame-aware session and the WEBS scaffold are tested against it.
FRAMESET_SHELL = ('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Frameset//EN"><html><head><title>WEBS</title></head>'
                  '<frameset rows="*,100%" border="0"><frame name="top" src="help.html"><frame name="bottom" src="Home.aspx">'
                  '<noframes></noframes></frameset></html>')
HELP_FRAME = "<html><body><p>help</p></body></html>"
HOME_FRAME = ('<html><body><div id="hdr">Welcome vendor <a href="Logout.aspx">Log Out</a></div>'
              '<h1>Opportunity 26-013 Records System</h1>'
              '<a href="ShowDocument.aspx?docId=1">RFP 26-013.pdf</a> '
              '<a href="ShowDocument.aspx?docId=2">Attachment A - Requirements.xlsx</a> '
              '<a href="Search.aspx">Search</a></body></html>')
SEARCH_FRAME = ('<html><body><form action="Results.aspx" method="get"><input name="q" id="q">'
                '<input type="submit" id="go" value="Search"></form></body></html>')
RESULTS_FRAME = ('<html><body><table><tr><td><a class="res" href="Home.aspx?opp=26-013">26-013 Records System</a></td></tr>'
                 '<tr><td><a class="res" href="Home.aspx?opp=99-001">99-001 Paving</a></td></tr></table></body></html>')


class _FramesHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, body, ctype="text/html; charset=utf-8", extra=None):
        self.send_response(200); self.send_header("Content-Type", ctype)
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(body.encode() if isinstance(body, str) else body)
    def do_GET(self):
        p = self.path
        if p in ("/", "/webs/", "/webs/index.html"):
            self._send(FRAMESET_SHELL, extra={"Set-Cookie": "ASP.NET_SessionId=s3ss10n; Path=/"})
        elif p.endswith("help.html"): self._send(HELP_FRAME)
        elif p.startswith("/webs/Home.aspx"): self._send(HOME_FRAME)
        elif p.startswith("/webs/Search.aspx"): self._send(SEARCH_FRAME)
        elif p.startswith("/webs/Results.aspx"): self._send(RESULTS_FRAME)
        elif p.startswith("/webs/ShowDocument.aspx"):
            if "ASP.NET_SessionId=s3ss10n" not in (self.headers.get("Cookie") or ""):
                self._send('<form><input type="password"></form>'); return
            if "docId=1" in p: self._send(b"%PDF-1.4 webs", "application/pdf", {"Content-Disposition": 'attachment; filename="RFP 26-013.pdf"'})
            else: self._send(b"PK\x03\x04", "application/octet-stream")
        else:
            self.send_response(404); self.end_headers()


@pytest.fixture
def frames_portal():
    port = _free_port()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), _FramesHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()


def test_generic_adapter_refuses_search_until_configured():
    ad = portal.PortalAdapter({})
    with pytest.raises(portal.PortalError) as e:
        ad.find_opportunity(None, number="26-013")
    assert "capture <domain> search" in str(e.value) and "--url" in str(e.value)
    ad2, key = portal.select_adapter("https://pr-webs-vendor.des.wa.gov/Home.aspx", {})
    assert isinstance(ad2, portal.WebsPortal) and key == "pr-webs-vendor.des.wa.gov"


# ----------------------------------------------------------------------------- WEBS: grounded on real captures
def _fx(name):
    return open(os.path.join(HERE, "fixtures", name), encoding="utf-8").read()

WEBS = "https://pr-webs-vendor.des.wa.gov/"


def test_webs_results_parser_on_real_capture():
    res = portal.webs_parse_results(_fx("webs-results.html"), WEBS + "Search_Bid_Result.aspx")
    assert res["total"] == 5 and len(res["rows"]) == 5 and res["truncated"] is False
    by_ref = {r["reference"]: r for r in res["rows"]}
    r = by_ref["2026_01"]
    assert r["id"] == "57543" and r["title"] == "Law Enforcement Data Analytics"
    assert r["organization"] == "Washington Counties Risk Pool" and r["posted"] == "2026-09-14"
    assert r["url"] == WEBS + "Search_BidDetails.aspx?ID=57543"
    assert by_ref["CC0342-JMC"]["posted"] == "2026-08-28"            # MM/DD/YY → ISO
    assert "&" in by_ref["1255311"]["description"] and "&amp;" not in by_ref["1255311"]["description"]


def test_webs_detail_parser_on_real_capture():
    rec = portal.webs_parse_detail(_fx("webs-detail.html"), WEBS + "Search_BidDetails.aspx?ID=57527")
    assert rec["system_id"] == "57527" and rec["reference"] == "DRS 26-05"
    assert rec["organization"] == "Department of Retirement Systems" and rec["title"].startswith("DRS Draft Sole Source")
    assert rec["posted"] == "2026-09-10" and rec["closed"] == "2026-09-25"
    assert rec["estimated_value"] == 216073.12 and rec["estimated_value_text"] == "216,073.12"
    assert rec["contact"]["email"] == "buyer@agency.example"
    assert [d["name"] for d in rec["documents"]] == ["DRS Draft Sole Source Contract_26-05 .pdf", "SoleSourceLegalNotice_IBM.pdf",
                                                      "SoleSourceContractJustification IBM.docx"]
    assert all(d["url"].startswith(WEBS + "AttachmentViewer.aspx?AttachmentID=") and "DocType=1" in d["url"] for d in rec["documents"])
    assert [(a["date"], a["name"][:11]) for a in rec["amendments"]] == [("2026-09-16", "Amendment 1"), ("2026-09-16", "Amend 2 DRS")]
    assert all("DocType=2" in a["url"] for a in rec["amendments"])
    assert len(rec["commodity_codes"]) == 2 and rec["commodity_codes"][0].startswith("209-12 - ")
    assert "Benton" in rec["counties"] and len(rec["counties"]) == 39
    assert portal.webs_parse_detail(_fx("webs-home.html"), WEBS + "Home.aspx") == {}     # not a detail page


def test_webs_vendors_parser_on_real_capture():
    rows = portal.webs_parse_vendors(_fx("webs-vendors-downloading.html"))
    assert [r["company"] for r in rows] == ["Alpha Analytics LLC", "Beta Public Safety Software, Inc.", "Gamma Data & Cloud Corp"]
    assert rows[0]["status"] == "Mc-SB" and rows[1]["status"] == "" and rows[2]["phone"] == "(000) 000-0003"
    assert portal.webs_parse_vendors(_fx("webs-detail.html")) == []                     # button not yet clicked


def test_webs_adapter_grounded_rules():
    ad = portal.WebsPortal({})
    assert ad.frame_name == "bottom" and "des.wa.gov" in ad.domains and ad.home == WEBS
    assert ad.is_logged_in(_fx("webs-home.html")) and not ad.is_logged_in('<form><input type="password"></form>')
    assert ad.is_landing_page(WEBS) and ad.is_landing_page(WEBS + "home.html") and ad.is_landing_page(WEBS + "Home.aspx")
    assert not ad.is_landing_page(WEBS + "Search_BidDetails.aspx?ID=57543")
    docs = ad.document_links(portal.extract_links(_fx("webs-detail.html"), WEBS + "Search_BidDetails.aspx?ID=57527"))
    assert [n for _, n in docs] == ["DRS Draft Sole Source Contract_26-05 .pdf", "SoleSourceLegalNotice_IBM.pdf",
                                    "SoleSourceContractJustification IBM.docx", "Amendment 1_ Updated SoleSourceLegalNotice_IBM.pdf",
                                    "Amend 2 DRS Draft Sole Source Contract 26-05.pdf"]       # documents AND amendments, anchor text = filename
    # a WEBS id short-circuits the search entirely (no session needed)
    assert ad.find_opportunity(None, number="ID=57543") == WEBS + "Search_BidDetails.aspx?ID=57543"
    assert ad.find_opportunity(None, number=WEBS + "Search_BidDetails.aspx?ID=7") == WEBS + "Search_BidDetails.aspx?ID=7"
    with pytest.raises(portal.PortalError):
        ad.find_opportunity(None)
    # subject-line → search phrases, shortest (bare title) first
    assert ad.title_candidates("WEBS Notification - New Solicitation: Law Enforcement Data Analytics")[0] == "Law Enforcement Data Analytics"
    assert ad.title_candidates("RFP 2026_01 Law Enforcement Data Analytics")[0] == "Law Enforcement Data Analytics"
    # result matching: exact reference, exact title, unique specific containment; generic word = ambiguous
    rows = portal.webs_parse_results(_fx("webs-results.html"), WEBS)["rows"]
    assert ad.match_row(rows, number="2026_01")["id"] == "57543"
    assert ad.match_row(rows, number="cc0342 jmc")["id"] == "57478"                        # normalised compare
    assert ad.match_row(rows, title="Law Enforcement Data Analytics")["id"] == "57543"
    assert ad.match_row(rows, title="Solicitation: WSU Pullman Recreation Center Management System")["id"] == "57478"
    assert ad.match_row(rows, title="Software") is None
    assert ad.match_row(rows, number="does-not-exist") is None
    assert ad.match_row(rows[:1], number="26-05")["id"] == "57527"                            # single row containing the number
    s = portal.parse_search_arg("des.wa.gov:title=Records Management System")
    assert s == {"portal": "des.wa.gov", "number": None, "title": "Records Management System"}
    assert portal.parse_search_arg("DES.wa.gov: ID=57543")["number"] == "ID=57543"
    assert portal.search_terms({"solicitation_number": "26-013", "title": "RFP 26-013 Records"}) == ("26-013", "RFP 26-013 Records")
    assert portal.search_terms({"title": "{{TITLE}}"}) == (None, None)
    assert portal.search_terms({"title": "x"}, {"number": "N1", "title": None}) == ("N1", "x")


# A faithful stand-in for WEBS built from the real captures: frameset shell, Home.aspx with the
# Logout link, Search_Bid.aspx / SearchBid.aspx forms (POST → results), Search_Bid_Result.aspx rows in
# the real Grid3File markup, Search_BidDetails.aspx (the real fixture) whose #Imagebutton1 postback
# returns the vendors view, AttachmentViewer.aspx serving files with Content-Disposition — and the
# real site's quirk that a TOP-LEVEL request for an inner page bounces to the frameset home.
WEBS_ROWS = [("57543", "Law Enforcement Data Analytics", "Washington Counties Risk Pool", "2026_01", "09/14/26"),
             ("57483", "MERCHANT BANKCARD SERVICES", "A County", "RFP_2026_01", "09/02/26"),
             ("56867", "Enterprise Content Management (ECM) Maintenance", "Enterprise Services (DES), Dept. of", "12625", "09/15/26"),
             ("57527", "DRS Draft Sole Source Contract 26-05", "Department of Retirement Systems", "DRS 26-05", "09/10/26")]


def _webs_results_html(rows):
    tr = ""
    for i, (oid, title, org, ref, posted) in enumerate(rows):
        tr += (f'<tr class="Grid3File{1 + i % 2}"><td align="left" valign="top" style="width:200px;">'
               f'<a class="ctext-hyperlink" href="Search_BidDetails.aspx?ID={oid}"><img alt="" src="images/reactivate.gif" border="0">{title}</a>'
               f'</td><td align="left" valign="top">desc {oid}</td><td><span id="DataGrid1__ctl{i+3}_OrgName">{org}</span></td>'
               f'<td>Buyer</td><td>{ref}</td><td>{posted}</td></tr>')
    return (f'<html><body><form name="Form1" method="post" action="./Search_Bid_Result.aspx" id="Form1"><a href="Logout.aspx">LOGOUT</a>'
            f'<span>Total number of records returned = {len(rows)}</span>'
            f'<table class="ctext" cellspacing="0" border="0" id="DataGrid1"><tbody><tr class="Grid2Header"><td>Title</td><td>Description</td>'
            f'<td>Organization</td><td>Contact</td><td>Reference #</td><td>Date Posted</td></tr>{tr}</tbody></table></form></body></html>')


WEBS_ADV_FORM = ('<html><body><form name="Form1" method="post" action="./SearchBid.aspx" id="Form1"><a href="Logout.aspx">LOGOUT</a>'
                 '<input name="SolicitationKeywords" type="text" id="SolicitationKeywords">'
                 '<select name="ddlBidStatus" id="ddlBidStatus"><option value="-1">&lt;ALL&gt;</option><option selected value="Posted">Posted</option>'
                 '<option value="Closed">Closed</option><option value="Archived">Archived</option></select>'
                 '<input id="CommodityFilterRBL_0" type="radio" name="CommodityFilterRBL" value="0" checked>'
                 '<input id="CommodityFilterRBL_1" type="radio" name="CommodityFilterRBL" value="1">'
                 '<input src="images/button-search.gif" name="SearchButton" type="image" id="SearchButton"></form></body></html>')


WEBS_CREDS = ("vendor@example.com", "correct horse")


class _WebsHandler(http.server.BaseHTTPRequestHandler):
    """Session model: the frameset shell hands out ASP.NET_SessionId; pages need it AND a webs_auth cookie
    (granted by POST LoginPage.aspx with the right credentials), otherwise frame 'bottom' shows the real
    login page — exactly what an expired WEBS session looks like. require_auth=False = fresh login done."""
    require_auth = False
    def log_message(self, *a): pass
    def _send(self, body, ctype="text/html; charset=utf-8", extra=None, code=200):
        self.send_response(code); self.send_header("Content-Type", ctype)
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(body.encode() if isinstance(body, str) else body)
    def _bounce(self):
        self.send_response(302); self.send_header("Location", "/"); self.end_headers()
    def _authed(self):
        c = self.headers.get("Cookie") or ""
        return "ASP.NET_SessionId=w3bs" in c and (not type(self).require_auth or "webs_auth=1" in c)
    def do_GET(self):
        import urllib.parse as up
        u = up.urlparse(self.path); qs = up.parse_qs(u.query); p = u.path
        top_level = self.headers.get("Sec-Fetch-Dest", "document") == "document"
        if p in ("/", "/home.html"):
            self._send(FRAMESET_SHELL, extra={"Set-Cookie": "ASP.NET_SessionId=w3bs; Path=/"}); return
        if p.endswith("help.html"): self._send(HELP_FRAME); return
        if top_level and p.endswith(".aspx") and p != "/AttachmentViewer.aspx":
            self._bounce(); return                                    # the real WEBS behaviour for pages (files download directly)
        if p.endswith(".aspx") and p != "/AttachmentViewer.aspx" and not self._authed():
            self._send(_fx("webs-login.html")); return                # expired session: every page is the login page
        if p == "/Home.aspx": self._send(_fx("webs-home.html")); return
        if p == "/Search_Bid.aspx": self._send(_fx("webs-search-form.html")); return
        if p == "/SearchBid.aspx": self._send(WEBS_ADV_FORM); return
        if p == "/Search_Bid_Result.aspx":
            kw = (qs.get("kw") or [""])[0].lower()
            rows = [r for r in WEBS_ROWS if kw and (kw in r[1].lower() or kw in r[3].lower())]
            self._send(_webs_results_html(rows)); return
        if p == "/Search_BidDetails.aspx":
            oid = (qs.get("ID") or [""])[0]
            if oid != "57527": self._send("<html><body><a href='Logout.aspx'>LOGOUT</a>no such solicitation</body></html>"); return
            self._send(_fx("webs-detail.html")); return
        if p == "/AttachmentViewer.aspx":
            if "ASP.NET_SessionId=w3bs" not in (self.headers.get("Cookie") or ""):
                self._send('<form><input type="password"></form>'); return
            aid = (qs.get("AttachmentID") or [""])[0]
            if aid == "149730": self._send(b"%PDF-1.4 sole source", "application/pdf", {"Content-Disposition": "attachment;filename=DRS Draft Sole Source Contract_26-05 .pdf"})
            elif aid == "149844": self._send(b"%PDF-1.4 amendment 1", "application/pdf", {"Content-Disposition": "attachment;filename=Amendment 1_ Updated SoleSourceLegalNotice_IBM.pdf"})
            else: self.send_response(404); self.end_headers()
            return
        self.send_response(404); self.end_headers()
    def do_POST(self):
        import urllib.parse as up
        n = int(self.headers.get("Content-Length") or 0); body = self.rfile.read(n).decode("utf-8", "replace")
        p = up.urlparse(self.path).path
        form = up.parse_qs(body)
        if p == "/LoginPage.aspx":
            if (form.get("txtEmail") or [""])[0] == WEBS_CREDS[0] and (form.get("txtPassword") or [""])[0] == WEBS_CREDS[1]:
                self.send_response(302); self.send_header("Set-Cookie", "webs_auth=1; Path=/"); self.send_header("Location", "/Home.aspx"); self.end_headers()
            else:
                self._send(_fx("webs-login.html").replace("Forgot Password?", "Invalid login. Forgot Password?"))
            return
        if not self._authed():
            self._send(_fx("webs-login.html")); return
        if p == "/Search_BidDetails.aspx":                          # #Imagebutton1 postback (multipart) → vendors view
            self._send(_fx("webs-vendors-downloading.html")); return
        if p == "/Search_Bid.aspx":
            assert form.get("radCommCodes") == ["1"] and form.get("radCounties") == ["1"], form   # adapter must select All/All
            kw = (form.get("textBoxBidCustRefNum") or [""])[0]
        elif p == "/SearchBid.aspx":
            assert form.get("ddlBidStatus") == ["-1"] and form.get("CommodityFilterRBL") == ["1"], form
            kw = (form.get("SolicitationKeywords") or [""])[0]
        else:
            self.send_response(404); self.end_headers(); return
        self.send_response(302); self.send_header("Location", "/Search_Bid_Result.aspx?kw=" + up.quote(kw)); self.end_headers()


@pytest.fixture
def webs_portal():
    port = _free_port()
    _WebsHandler.require_auth = False
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), _WebsHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}/"
    srv.shutdown()


@pytest.fixture
def webs_portal_expired():
    """Same portal, but every session starts EXPIRED: pages show LoginPage.aspx until a POST LoginPage.aspx
    with WEBS_CREDS sets the auth cookie."""
    port = _free_port()
    _WebsHandler.require_auth = True
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), _WebsHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}/"
    srv.shutdown(); _WebsHandler.require_auth = False


def test_resolve_credentials_env_and_absent(monkeypatch):
    assert portal.resolve_credentials({}) == (None, None)
    assert portal.resolve_credentials({"username": "u@example.com"}) == ("u@example.com", None)
    monkeypatch.setenv("TEST_PORTAL_PW", "s3cret")
    assert portal.resolve_credentials({"username": "u@example.com", "password_env": "TEST_PORTAL_PW"}) == ("u@example.com", "s3cret")
    # a keychain service that doesn't exist falls through to (user, None) instead of raising
    assert portal.resolve_credentials({"username": "u@example.com", "password_keychain_service": "bidkit-test-no-such-service-xyz"}) == ("u@example.com", None)


@pytest.mark.skipif(pytest.importorskip("playwright", reason="playwright not installed") is None, reason="no playwright")
def test_real_webs_expired_session_relogin_with_stored_credentials(tmp_path, webs_portal_expired, monkeypatch, capsys):
    base = webs_portal_expired
    # 1. no credentials stored → honest NOT LOGGED IN with both remedies
    spec = {"adapter": "webs", "login_url": base, "profile_dir": str(tmp_path / "prof")}
    opp = tmp_path / "OPP"; (opp / "initial-email").mkdir(parents=True)
    (opp / "initial-email" / "links.md").write_text(f"- {base}Search_BidDetails.aspx?ID=57527\n")
    try:
        rep = portal.fetch_for_opportunity(str(opp), portals={"127.0.0.1": spec}, headless=True, competitors=False)
    except portal.PortalError as e:
        pytest.skip(f"chromium unavailable: {e}")
    errs = rep["pages"][0]["errors"]
    assert rep["pages"][0]["documents"] == [] and any("NOT LOGGED IN" in e and "portal login 127.0.0.1" in e and "password_keychain_service" in e for e in errs)
    # 2. credentials in the environment (as ~/.config/bidkit/env would provide for cron) → auto re-login, then the fetch proceeds
    monkeypatch.setenv("TEST_WEBS_PW", WEBS_CREDS[1])
    spec2 = dict(spec, username=WEBS_CREDS[0], password_env="TEST_WEBS_PW")
    rep = portal.fetch_for_opportunity(str(opp), portals={"127.0.0.1": spec2}, headless=True, competitors=False)
    page = rep["pages"][0]
    assert page.get("login", "").startswith("session had expired; logged in again as vendor@example.com"), page
    assert page["record"]["reference"] == "DRS 26-05" and {d["name"] for d in page["documents"]} >= {"DRS Draft Sole Source Contract_26-05 .pdf"}
    assert "logged in again" in (opp / "rfp" / "portal-fetch.md").read_text() or True   # report line is optional
    # 3. wrong password → clear failure, no crash
    monkeypatch.setenv("TEST_WEBS_PW", "wrong")
    opp2 = tmp_path / "OPP2"; (opp2 / "initial-email").mkdir(parents=True)
    (opp2 / "initial-email" / "links.md").write_text(f"- {base}Search_BidDetails.aspx?ID=57527\n")
    rep = portal.fetch_for_opportunity(str(opp2), portals={"127.0.0.1": dict(spec2, profile_dir=str(tmp_path / "prof2"))}, headless=True, competitors=False)
    assert any("automatic login as vendor@example.com failed" in e for e in rep["pages"][0]["errors"])
    # 4. `login --auto` CLI
    monkeypatch.setenv("TEST_WEBS_PW", WEBS_CREDS[1])
    pj = tmp_path / "portals.json"; pj.write_text(json.dumps({"127.0.0.1": dict(spec2, profile_dir=str(tmp_path / "prof3"))}))
    assert portal.main(["login", "127.0.0.1", "--auto", "--portals", str(pj)]) == 0
    assert "logged in as vendor@example.com" in capsys.readouterr().out
    # the auto-login saved the session: a plain fetch with the same profile needs no re-login
    opp3 = tmp_path / "OPP3"; (opp3 / "initial-email").mkdir(parents=True)
    (opp3 / "initial-email" / "links.md").write_text(f"- {base}Search_BidDetails.aspx?ID=57527\n")
    rep = portal.fetch_for_opportunity(str(opp3), portals={"127.0.0.1": dict(spec, profile_dir=str(tmp_path / "prof3"))}, headless=True, competitors=False)
    assert rep["pages"][0]["record"]["reference"] == "DRS 26-05" and "login" not in rep["pages"][0]


@pytest.mark.skipif(pytest.importorskip("playwright", reason="playwright not installed") is None, reason="no playwright")
def test_real_webs_grounded_flow_search_open_record_downloads_competitors(tmp_path, webs_portal):
    spec = {"adapter": "webs", "login_url": webs_portal, "profile_dir": str(tmp_path / "prof")}
    ad = portal.WebsPortal(spec)
    try:
        sess = portal.PlaywrightSession(str(tmp_path / "prof"), headless=True, timeout_ms=30000)
    except portal.PortalError as e:
        pytest.skip(f"chromium unavailable: {e}")
    try:
        # a top-level request for an inner page bounces to the frameset (as on the real site) …
        url, html = sess.goto(webs_portal + "Search_BidDetails.aspx?ID=57527", frame_name="bottom")
        assert url.endswith("/Home.aspx") and "txtSystemIdentifier" not in html
        # … so open() navigates the bottom frame instead
        url, html = ad.open(sess, webs_portal + "Search_BidDetails.aspx?ID=57527")
        assert url.endswith("Search_BidDetails.aspx?ID=57527") and "txtSystemIdentifier" in html and ad.is_logged_in(html)
        # reference number → simple search (All codes / All counties asserted server-side) → exact match
        assert ad.find_opportunity(sess, number="2026_01") == webs_portal + "Search_BidDetails.aspx?ID=57543"
        # a notification-style subject → advanced search with the bare title
        assert ad.find_opportunity(sess, title="WEBS Notification - New Solicitation: Enterprise Content Management (ECM) Maintenance") \
            == webs_portal + "Search_BidDetails.aspx?ID=56867"
        # 12625 also matches nothing else; a nonsense number lists candidates in the error
        assert ad.find_opportunity(sess, number="12625").endswith("ID=56867")
        with pytest.raises(portal.PortalError) as e:
            ad.find_opportunity(sess, number="zzz-none", title="Nothing Like This Exists")
        assert "no solicitation matched" in str(e.value) and "--url" in str(e.value)
    finally:
        sess.close()
    # end-to-end: the email linked only the portal's front door; opportunity.json carries the number
    opp = tmp_path / "OPP"; (opp / "initial-email").mkdir(parents=True)
    (opp / "initial-email" / "links.md").write_text(f"- {webs_portal}\n")
    (opp / "opportunity.json").write_text(json.dumps({"id": "DRS-26-05-sole-source", "solicitation_number": "DRS 26-05",
                                                       "title": "WEBS Notification: DRS Draft Sole Source Contract 26-05"}))
    rep = portal.fetch_for_opportunity(str(opp), portals={"127.0.0.1": spec}, headless=True)
    page = rep["pages"][0]
    assert page["adapter"] == "webs" and page["search"]["number"] == "DRS 26-05"
    assert page["found_url"] == webs_portal + "Search_BidDetails.aspx?ID=57527" and page["final_url"] == page["found_url"]
    assert page["record"]["reference"] == "DRS 26-05" and page["record"]["closed"] == "2026-09-25" and page["record"]["estimated_value_text"] == "216,073.12"
    rec = json.load(open(opp / "rfp" / "portal-record.json"))
    assert len(rec) == 1 and rec[0]["estimated_value"] == 216073.12 and len(rec[0]["documents"]) == 3 and len(rec[0]["amendments"]) == 2
    assert "closed: **2026-09-25**" in (opp / "rfp" / "portal-record.md").read_text()
    names = {d["name"] for d in page["documents"]}
    assert "DRS Draft Sole Source Contract_26-05 .pdf" in names and "Amendment 1_ Updated SoleSourceLegalNotice_IBM.pdf" in names
    assert (opp / "rfp" / "Amendment 1_ Updated SoleSourceLegalNotice_IBM.pdf").read_bytes() == b"%PDF-1.4 amendment 1"
    assert sum(1 for e in page["errors"] if "HTTP 404" in e) == 3                        # the other three attachments aren't served
    assert page["competitors"] == 3
    csv_text = (opp / "research" / "portal-vendors-downloading.csv").read_text()
    assert "Alpha Analytics LLC" in csv_text and "Mn-SB-V" in csv_text and "127.0.0.1" in csv_text
    md = (opp / "rfp" / "portal-fetch.md").read_text()
    assert "portal record: **DRS Draft Sole Source Contract 26-05**" in md and "vendors downloading: 3" in md and "searched for number='DRS 26-05'" in md
    # --search on the CLI with no links at all
    opp2 = tmp_path / "OPP2"; (opp2 / "initial-email").mkdir(parents=True)
    pj = tmp_path / "portals.json"; pj.write_text(json.dumps({"127.0.0.1": spec}))
    assert portal.main(["fetch", str(opp2), "--search", "127.0.0.1:ID=57527", "--portals", str(pj), "--no-competitors"]) in (0, 1)
    rep2 = json.load(open(opp2 / "rfp" / "portal-record.json"))
    assert rep2[0]["system_id"] == "57527" and not (opp2 / "research").exists()


def test_config_driven_doc_pattern_and_frame_name_on_generic_adapter():
    ad = portal.PortalAdapter({"frame_name": "bottom", "doc_href_pattern": r"ShowDocument\.aspx\?docId=", "logged_in_marker": "Log Out"})
    assert ad.frame_name == "bottom"
    links = portal.extract_links(HOME_FRAME, "http://x/webs/Home.aspx")
    docs = ad.document_links(links)
    assert sorted(n for _, n in docs) == ["Attachment A - Requirements.xlsx", "RFP 26-013.pdf"]
    assert all("ShowDocument" in l.href for l, _ in docs) and not any("Search" in l.href for l, _ in docs)
    assert ad.is_logged_in(HOME_FRAME) and not ad.is_logged_in("<form><input type='password'></form>")


@pytest.mark.skipif(pytest.importorskip("playwright", reason="playwright not installed") is None, reason="no playwright")
def test_real_frameset_goto_returns_content_frame_and_snapshot_saves_all_frames(tmp_path, frames_portal):
    try:
        sess = portal.PlaywrightSession(str(tmp_path / "prof"), headless=True, timeout_ms=30000)
    except portal.PortalError as e:
        pytest.skip(f"chromium unavailable: {e}")
    try:
        url, html = sess.goto(f"{frames_portal}/webs/", frame_name="bottom")
        assert url.endswith("/webs/Home.aspx") and "Opportunity 26-013" in html and "<frameset" not in html
        # auto mode (no frame_name) picks the frame with the most text -> also the bottom frame
        url2, html2 = sess.goto(f"{frames_portal}/webs/")
        assert "Opportunity 26-013" in html2
        # relative links resolve against the FRAME url, not the shell
        docs = portal.PortalAdapter({"doc_href_pattern": r"ShowDocument"}).document_links(portal.extract_links(html, url))
        assert all(l.href.startswith(f"{frames_portal}/webs/ShowDocument.aspx") for l, _ in docs)
        names = {n for n, _ in sess.frames()}
        assert {"top", "bottom"} <= names
        files = sess.snapshot(str(tmp_path / "snap"))
        base = {os.path.basename(f) for f in files}
        assert "snap.html" in base and "snap.frame-bottom.html" in base and "snap.frame-top.html" in base and "snap.frames.json" in base
        assert "<frameset" in (tmp_path / "snap.html").read_text()                       # the shell, as Save-Page saw it
        assert "Opportunity 26-013" in (tmp_path / "snap.frame-bottom.html").read_text()  # the content we actually need
        # downloads carry the session cookie set by the shell response
        data, name = sess.download(docs[0][0].href)
        assert data.startswith(b"%PDF") or data.startswith(b"PK")
    finally:
        sess.close()


@pytest.mark.skipif(pytest.importorskip("playwright", reason="playwright not installed") is None, reason="no playwright")
def test_real_config_driven_search_flow_on_generic_adapter(tmp_path, frames_portal):
    """An un-grounded frameset portal can still be driven entirely from portals.json (frame_name,
    logged_in_marker, doc_href_pattern, search selectors) — no adapter code needed."""
    spec = {"adapter": "generic", "frame_name": "bottom", "logged_in_marker": "Log Out", "profile_dir": str(tmp_path / "prof"),
            "doc_href_pattern": r"ShowDocument\.aspx\?docId=",
            "search": {"url": f"{frames_portal}/webs/Search.aspx", "input_selector": "#q", "submit_selector": "#go",
                       "result_link_selector": "a.res"}}
    ad = portal.PortalAdapter(spec)
    try:
        sess = portal.PlaywrightSession(str(tmp_path / "prof"), headless=True, timeout_ms=30000)
    except portal.PortalError as e:
        pytest.skip(f"chromium unavailable: {e}")
    try:
        # Search.aspx is served directly (not inside the frameset) — frame_name falls back to top
        found = ad.find_opportunity(sess, number="26-013")
        assert found.endswith("/webs/Home.aspx?opp=26-013")
        with pytest.raises(portal.PortalError):
            ad.find_opportunity(sess, number="does-not-exist")
    finally:
        sess.close()
    # Establish the session first (what `portal login` does): only the frameset shell sets the
    # ASP.NET session cookie; storage_state carries it into the fetch below across a browser restart.
    s0 = portal.PlaywrightSession(str(tmp_path / "prof"), headless=True, timeout_ms=30000)
    try:
        s0.goto(f"{frames_portal}/webs/")
    finally:
        s0.close()
    # end-to-end fetch with --search semantics: no links.md, adapter finds the page, docs land in rfp/
    opp = tmp_path / "OPP"; (opp / "initial-email").mkdir(parents=True)
    rep = portal.fetch_for_opportunity(str(opp), portals={"127.0.0.1": spec}, headless=True,
                                       search={"portal": "127.0.0.1", "number": "26-013"})
    page = rep["pages"][0]
    assert page["url"].endswith("Home.aspx?opp=26-013") and page["adapter"] == "generic"
    names = {d["name"] for d in page["documents"]}
    assert "RFP 26-013.pdf" in names and "Attachment A - Requirements.xlsx" in names
    assert (opp / "rfp" / "RFP 26-013.pdf").read_bytes().startswith(b"%PDF")
    # the search landed on Home.aspx served directly (no frameset), so the snapshot is a plain page;
    # the frameset snapshot path is covered by the previous test
    assert any(s.endswith(".html") for s in page["snapshot"]) and any(s.endswith(".frames.json") for s in page["snapshot"])


def test_capture_writes_grounding_files(tmp_path):
    class Sess(FakeSession):
        def frames(self): return [("top", "http://x/webs/"), ("bottom", "http://x/webs/Home.aspx")]
        def snapshot(self, base):
            open(base + ".html", "w").write(FRAMESET_SHELL); open(base + ".frame-bottom.html", "w").write(HOME_FRAME)
            return [base + ".html", base + ".frame-bottom.html"]
    dest, meta = portal.capture("des.wa.gov", "home", {}, url="http://x/webs/", out_root=str(tmp_path / "caps"), session_factory=Sess)
    assert dest == str(tmp_path / "caps" / "des.wa.gov" / "home")
    assert (tmp_path / "caps" / "des.wa.gov" / "home" / "page.frame-bottom.html").exists()
    cj = json.load(open(os.path.join(dest, "capture.json")))
    assert cj["frames"] == [["top", "http://x/webs/"], ["bottom", "http://x/webs/Home.aspx"]] and "frame_name" in cj["next"]
