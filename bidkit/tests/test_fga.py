"""bidkit.fga — sourcing harness tests against a FAKE of the portal's JSON API. The fake reproduces the
contract read from the real app bundle and verified live (Sept 2026): lookup q = contains, repeated
*_code_id = OR within a kind and AND across kinds, page_size ≤ 100 with `next` links, Bearer JWT with
refresh, pre-signed document URLs (which 403 when the portal's signing is broken)."""
import base64, json, os, time, urllib.parse
import pytest
from bidkit import fga

TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "opportunities", "_template")
API = fga.DEFAULT_API


def jwt(exp_offset_s):
    payload = base64.urlsafe_b64encode(json.dumps({"exp": int(time.time()) + exp_offset_s, "token_type": "access"}).encode()).decode().rstrip("=")
    return f"hdr.{payload}.sig"


NAICS = [("54151", "Computer Systems Design and Related Services"), ("541511", "Custom Computer Programming Services"),
         ("541512", "Computer Systems Design Services"), ("541513", "Computer Facilities Management Services"),
         ("541519", "Other Computer Related Services"), ("511210", "Software Publishers"), ("5415", "aggregate")]
PSC = [("D3", "group"), ("AD30", "distractor containing D30"), ("D301", "FACILITY OPERATION"), ("D302", "SYSTEMS DEVELOPMENT"),
       ("D303", "DATA ENTRY"), ("7A20", "APPLICATION DEVELOPMENT SOFTWARE"), ("7A21", "BUSINESS APPLICATION SOFTWARE")]
NID = {c: f"naics-{c}" for c, _ in NAICS}
PID = {c: f"psc-{c}" for c, _ in PSC}


def opp(i, title, naics, psc, due, typ="Solicitation", sa="NONE", src="sam", docs=(), low=None, high=None, agency="Department of Examples"):
    return {"id": f"opp-{i}", "opp_key": f"k{i}", "source_type": src, "source_id": f"SRC-{i}", "opp_cat": "x", "title": title,
            "description_text": f"desc {i}", "ai_summary": f"summary {i}", "posted_date": "2026-09-01", "due_date": due,
            "primary_contact": {"contact_name": "Buyer Contact", "contact_email": "buyer@agency.example", "contact_phone": "(000) 000-0000", "contact_title": "CO"},
            "secondary_contact": None, "naics": naics, "psc": psc, "opp_type_description": typ,
            "documents": [{"id": f"d{i}{k}", "file_name": n, "file_type": ".pdf", "file_size": 10, "download_url": u} for k, (n, u) in enumerate(docs)],
            "set_aside": sa, "nsn": None, "val_est_low": low, "val_est_high": high, "agency_name": agency, "agency_abbreviation": "DOE",
            "pop_country": "USA", "pop_state": "WA", "pop_city": "Spokane", "pop_zip": "99201", "dibbs_status": None, "dibbs_quantity": None,
            "path": f"https://aggregator.example/{i}", "source_path": f"https://source.example/opp/{i}", "document_path": ""}


OPPS = [
    opp(1, "Records Management System Replacement", "541511", "7A20", "2026-10-15", docs=[("RFP.pdf", "https://media.example/ok.pdf"), ("Forms.xlsx", "https://media.example/broken.xlsx")], low=250000, high=1200000),
    opp(2, "Data Entry Services", "561410", "D302", "2026-10-20", src="sled", sa="SBA"),
    opp(3, "Case Management Software and Programming", "541512", "D303", "2026-11-01", low=100000, high=100000),
    opp(4, "Paving", "237310", "Y1AA", "2026-10-30"),
    opp(5, "Sole Source - Brand Name Widget Software", "541519", "7A21", "2026-10-25"),
    opp(6, "Closing Tomorrow Software Support", "541519", "7A21", "2026-09-18"),
    opp(7, "8(a) Set-Aside IT Support", "541512", "7A21", "2026-10-28", sa="8A"),
    opp(8, "Award Notice - Old Contract", "541511", "7A20", "2026-12-01", typ="Award Notice"),
]
FEDERAL_ONLY = {"opp-1", "opp-3", "opp-4", "opp-5", "opp-6", "opp-7", "opp-8"}


class FakeApi:
    """Callable with the http signature (method, url, headers, body) -> (status, headers, bytes)."""
    def __init__(self, page_size_cap=2):
        self.access, self.refresh = jwt(3600), "refresh-good"
        self.valid_access = {self.access}
        self.creds = ("vendor@example.com", "correct horse")
        self.calls = []
        self.cap = page_size_cap
        self.docs_ok = True
        self.patches = []
        self.drop_on_write = None                     # a code the fake "loses" on PATCH, to test the verify step
        self.profile = {"id": "bp-1", "legal_business_name": "Example Vendor LLC", "email": "office@vendor.example",
                        "naics_codes": [{"id": NID["541511"], "naics_code": "541511", "industry_title": "t"}],
                        "psc_codes": [{"id": PID["D302"], "psc_code": "D302", "psc_name": "t"}],
                        "top_naics_codes": [{"id": NID["541511"], "naics_code": "541511"}], "status_business_profile": True}

    def _json(self, status, obj):
        return status, {"content-type": "application/json"}, json.dumps(obj).encode()

    def __call__(self, method, url, headers, body=None):
        self.calls.append((method, url))
        u = urllib.parse.urlparse(url); qs = urllib.parse.parse_qs(u.query); path = u.path
        if url.startswith("https://media.example/"):
            if not self.docs_ok or "broken" in url:
                return 403, {"content-type": "application/xml"}, b"<Error><Code>SignatureDoesNotMatch</Code></Error>"
            return 200, {"content-type": "application/pdf"}, b"%PDF-1.4 fake document"
        if path.endswith("/auth/login/"):
            b = json.loads(body or b"{}")
            if (b.get("email"), b.get("password")) == self.creds:
                self.access = jwt(3600); self.valid_access.add(self.access); self.refresh = "refresh-good"
                return self._json(200, {"user": {"id": "u1", "firstName": "V", "lastName": "C", "email": b["email"], "role": "user"}, "accessToken": self.access, "refreshToken": self.refresh})
            return self._json(401, {"detail": "No active account found with the given credentials"})
        if path.endswith("/auth/refresh/"):
            b = json.loads(body or b"{}")
            if b.get("refresh") == self.refresh and self.refresh != "refresh-dead":
                self.access = jwt(3600); self.valid_access.add(self.access); self.refresh = "refresh-rotated"
                return self._json(200, {"accessToken": self.access, "refreshToken": self.refresh})
            return self._json(401, {"detail": "Token is invalid or expired"})
        # everything else needs a valid bearer
        tok = (headers.get("Authorization") or "").replace("Bearer ", "")
        if tok not in self.valid_access:
            return self._json(401, {"detail": "Given token not valid for any token type"})
        if path.endswith("/business-profile/naics-codes/"):
            q = (qs.get("q") or [""])[0]
            return self._json(200, {"count": 0, "next": None, "previous": None, "results": [{"id": NID[c], "naics_code": c, "industry_title": t} for c, t in NAICS if q in c]})
        if path.endswith("/business-profile/psc-codes/"):
            q = (qs.get("q") or [""])[0]
            return self._json(200, {"count": 0, "next": None, "previous": None, "results": [{"id": PID[c], "psc_code": c, "psc_name": t} for c, t in PSC if q in c]})
        if path.endswith("/business-profile/"):
            if method == "PATCH":
                ctype = headers.get("Content-Type", "")
                assert ctype.startswith("multipart/form-data; boundary="), ctype
                boundary = ctype.split("boundary=")[1]
                fields = {}
                for part in body.decode().split("--" + boundary)[1:-1]:
                    head, _, val = part.partition("\r\n\r\n")
                    name = head.split('name="')[1].split('"')[0]
                    fields[name] = val.rstrip("\r\n")
                self.patches.append(fields)
                for f, code_f, table in (("naics_codes", "naics_code", NID), ("psc_codes", "psc_code", PID)):
                    ids = json.loads(fields[f]); inv = {v: k for k, v in table.items()}
                    self.profile[f] = [{"id": i, code_f: inv[i], "industry_title" if f == "naics_codes" else "psc_name": "t"} for i in ids if i in inv and not (self.drop_on_write and inv[i] == self.drop_on_write)]
                self.profile["top_naics_codes"] = json.loads(fields.get("top_naics_codes", "[]"))
                return self._json(200, self.profile)
            return self._json(200, self.profile)
        if path.endswith("/fetch-documents/"):
            oid = path.split("/")[-3]
            return self._json(200, next(o["documents"] for o in OPPS if o["id"] == oid))
        m = [o for o in OPPS if path.endswith(f"/opportunities/{o['id']}/")]
        if m:
            return self._json(200, m[0])
        if path.endswith("/opportunities/"):
            rows = OPPS
            nids = qs.get("naics_code_id"); pids = qs.get("psc_code_id")
            if nids: rows = [o for o in rows if NID.get(o["naics"]) in nids]
            if pids: rows = [o for o in rows if PID.get(o["psc"]) in pids]
            if qs.get("only_federal"): rows = [o for o in rows if o["id"] in FEDERAL_ONLY]
            if qs.get("only_state_and_local"): rows = [o for o in rows if o["id"] not in FEDERAL_ONLY]
            if qs.get("q"): rows = [o for o in rows if qs["q"][0].lower() in o["title"].lower()]
            page = int((qs.get("page") or ["1"])[0]); size = min(int((qs.get("page_size") or ["100"])[0]), self.cap)
            chunk = rows[(page - 1) * size: page * size]
            nxt = None
            if page * size < len(rows):
                q2 = dict(qs); q2["page"] = [str(page + 1)]
                nxt = f"{u.scheme}://{u.netloc}{u.path}?" + urllib.parse.urlencode(q2, doseq=True)
            return self._json(200, {"count": len(rows), "next": nxt, "previous": None, "results": chunk})
        return 404, {}, b"not found"


@pytest.fixture
def api(tmp_path):
    a = FakeApi()
    return a


def client_for(api, tmp_path, access=None, refresh="refresh-good", creds=None):
    tf = tmp_path / "tokens.json"
    tf.write_text(json.dumps({"accessToken": access if access is not None else api.access, "refreshToken": refresh}))
    return fga.FgaClient({}, token_file=str(tf), http=api, credentials=(lambda: creds) if creds is not None else (lambda: None))


def test_expand_codes_varies_only_the_last_digit_against_the_portal_lookup(api, tmp_path):
    c = client_for(api, tmp_path)
    naics = c.expand_codes("naics", ["541511", "541519"], 1)
    assert [x["code"] for x in naics] == ["541511", "541512", "541513", "541519"]      # 54151 / 5415 aggregates dropped, no dupes
    assert naics[0]["id"] == "naics-541511" and naics[0]["seed"] == "541511" and "Programming" in naics[0]["title"]
    assert [x["code"] for x in c.expand_codes("naics", ["511210"], 1)] == ["511210"]     # a prefix with a single real code
    psc = c.expand_codes("psc", ["D302"], 1)
    assert [x["code"] for x in psc] == ["D301", "D302", "D303"]                          # AD30 (contains D30) and D3 (group) excluded
    assert [x["code"] for x in c.expand_codes("psc", ["7a20"], 0)] == ["7A20"]           # vary 0 = the seed itself, case-normalised
    assert c.expand_codes("psc", ["", None], 1) == []


def test_run_search_unions_kinds_and_paginates(api, tmp_path):
    c = client_for(api, tmp_path)
    crit = {"naics": ["541511"], "psc": ["D302"], "vary_last_digits": 1, "active_only": True, "scope": "all"}
    matched, flt = fga.run_search(c, crit)
    ids = {m["record"]["id"]: m["matched_by"] for m in matched}
    # NAICS 54151x → opps 1,3,5,6,7,8 ; PSC D30x → opps 2,3 ; opp 3 matched by both
    assert set(ids) == {"opp-1", "opp-2", "opp-3", "opp-5", "opp-6", "opp-7", "opp-8"}
    assert sorted(ids["opp-3"]) == ["naics:541512", "psc:D303"] and ids["opp-2"] == ["psc:D302"]
    assert [x["code"] for x in flt["naics"]] == ["541511", "541512", "541513", "541519"]
    # paginated: the fake caps pages at 2 rows, so the NAICS search took several requests following `next`
    opp_calls = [u for m, u in api.calls if "/opportunities/?" in u and "naics_code_id" in u]
    assert len(opp_calls) >= 3 and all("page_size=100" in u for u in opp_calls)
    assert all("active_only=true" in u for u in opp_calls) and all("ordering=due_date" in u for u in opp_calls)
    # scope → server-side flags
    assert fga.base_params({"scope": "federal"})["only_federal"] == "true"
    assert fga.base_params({"scope": "state_and_local", "keywords": "records"}) ["only_state_and_local"] == "true"
    assert fga.base_params({"keywords": "records"}, since="2026-09-01") == {"source_type_filter": "opportunities", "active_only": "true", "q": "records", "posted_date_after": "2026-09-01", "ordering": "due_date"}


def test_resale_screen_drops_cots_but_protects_real_work():
    """The resale screen drops branded COTS license/renewal noise UNLESS a keep pattern (dev/support
    signal) also matches. Both pattern lists come from the criteria; empty lists = screen off."""
    def row(title, naics="541519", psc="7A21"):
        return {"title": title, "opp_type": "Solicitation", "set_aside": "NONE", "naics": naics, "psc": psc, "due": "2026-12-01"}
    crit = {
        "resale_title_patterns": [r"\brenewals?\b", r"\bsubscriptions?\b", r"\blicen[sc]e[sd]?\b",
                                  r"\blicen[sc]ing\b", r"\bperpetual\b", r"\bupgrades?\b"],
        "keep_title_patterns": [r"\bdevelop\w*\b", r"\bimplement\w*\b", r"\bmoderniz\w*\b",
                                r"\breplacement\b", r"\bprofessional services\b", r"\bapplication maintenance\b"],
    }
    rows = [
        row("Mimecast Renewal FY26-27"),                                   # drop: renewal
        row("Five-Year Verkada License Renewal"),                          # drop: license + renewal
        row("Autodesk Vault Professional 2027 Upgrade"),                   # drop: upgrade
        row("Adobe Software Subscriptions"),                               # drop: subscription
        row("CAD System Replacement for 9-1-1"),                           # keep: replacement (no resale word)
        row("LIMS Software and Implementation"),                           # keep: implement
        row("Website Modernization Platform, Professional Services"),      # keep: modernization/professional services
        row("Development of a Remote Easy Access License System"),         # keep: 'License' present BUT protected by 'Development'
        row("NJKiDS Application Maintenance and Support"),                 # keep: application maintenance (no resale word)
        row("Records Management System Replacement"),                      # keep: no resale word at all
    ]
    kept, dropped = fga.apply_screens(rows, crit)
    kept_titles = {r["title"] for r in kept}
    assert dropped.get("resale/COTS renewal") == 4
    assert "Mimecast Renewal FY26-27" not in kept_titles
    assert "Development of a Remote Easy Access License System" in kept_titles     # protected false-positive guard
    assert "NJKiDS Application Maintenance and Support" in kept_titles
    assert "CAD System Replacement for 9-1-1" in kept_titles
    assert len(kept) == 6
    # empty pattern lists = screen disabled: nothing dropped for resale
    _, none_dropped = fga.apply_screens(rows, {})
    assert "resale/COTS renewal" not in none_dropped


def test_normalize_screens_and_report_with_seen_state(api, tmp_path):
    import datetime as dt
    c = client_for(api, tmp_path)
    crit = {"naics": ["541511"], "psc": ["D302"], "vary_last_digits": 1, "min_days_to_due": 3,
            "exclude_opportunity_types": ["Award Notice"], "exclude_set_asides": ["8A"], "exclude_title_patterns": [r"\bsole[- ]source\b"]}
    today = dt.date(2026, 9, 16); when = dt.datetime(2026, 9, 16, 8, 0)
    out = tmp_path / "out"; state = tmp_path / "state" / "seen.json"
    rp, rows, new_ids, flt = fga.source(c, crit, str(out), str(state), today=today, when=when)
    got = {r["id"] for r in rows}
    assert got == {"opp-1", "opp-2", "opp-3"}                 # 5 sole source, 6 closes in 2 days, 7 8(a), 8 award notice screened out
    assert new_ids == got
    r1 = next(r for r in rows if r["id"] == "opp-1")
    assert r1["url"] == f"{fga.DEFAULT_PORTAL}/opportunities/view/opp-1?tab=opportunities" and r1["source_url"] == "https://source.example/opp/1"
    assert r1["value_low"] == 250000.0 and r1["value_high"] == 1200000.0 and r1["documents"] == 2 and r1["matched_by"] == ["naics:541511"]
    assert r1["contact"]["email"] == "buyer@agency.example" and r1["pop"] == "Spokane, WA"
    md = open(rp).read()
    assert rp.endswith("report-2026-09-16.md") and "## New since last run (3)" in md and "## All open matches (3)" in md
    assert "screened out: closes in < 3 days (1); set-aside: 8A (1); title pattern (1); type: Award Notice (1)" in md
    assert "$250,000–$1,200,000" in md and "| 2026-10-15 | [Records Management System Replacement](" in md and "541511, 541512, 541513, 541519" in md
    csv_text = (out / "latest.csv").read_text()
    assert csv_text.splitlines()[0].startswith("due,title,agency") and "Records Management System Replacement" in csv_text and ",yes" in csv_text
    latest = json.load(open(out / "latest.json")); assert len(latest["rows"]) == 3 and set(latest["new_ids"]) == got
    # second run: nothing new; state remembers first_seen
    rp2, rows2, new2, _ = fga.source(c, crit, str(out), str(state), today=today, when=when + dt.timedelta(days=1))
    assert new2 == set() and "## New since last run (0)" in open(rp2).read() and "_none_" in open(rp2).read()
    st = json.load(open(state)); assert st["seen"]["opp-1"]["first_seen"].startswith("2026-09-16T08:00") and st["seen"]["opp-1"]["last_seen"].startswith("2026-09-17")
    # --all reports everything as new again without touching first_seen
    _, _, new3, _ = fga.source(c, crit, str(out), str(state), ignore_state=True, today=today, when=when)
    assert new3 == got and json.load(open(state))["seen"]["opp-1"]["first_seen"].startswith("2026-09-16T08:00")


def test_auth_refresh_login_and_failure_paths(api, tmp_path):
    # 1. expired access token, live refresh token → refreshed transparently, rotated refresh saved 0600
    c = client_for(api, tmp_path, access=jwt(-10))
    codes = c.lookup_codes("naics", "541511")
    assert codes[0]["code"] == "541511" and c.tokens["refreshToken"] == "refresh-rotated"
    assert oct(os.stat(c.token_file).st_mode & 0o777) == "0o600"
    assert any(u.endswith("/auth/refresh/") for _, u in api.calls) and not any(u.endswith("/auth/login/") for _, u in api.calls)
    # 2. server rejects a token that looks valid → 401 → refresh → retry once
    api.calls.clear(); api.valid_access.clear()
    c2 = client_for(api, tmp_path, access=jwt(3600), refresh="refresh-rotated")
    assert c2.lookup_codes("psc", "D302")[0]["code"] == "D302"
    kinds = ["auth" if "/auth/" in u else "lookup" for _, u in api.calls]
    assert kinds[:3] == ["lookup", "auth", "lookup"]                    # 401 → refresh → retry, once
    # 3. dead refresh token + stored credentials → API login
    api.refresh = "refresh-dead"
    c3 = client_for(api, tmp_path, access=jwt(-10), refresh="refresh-dead", creds=("vendor@example.com", "correct horse"))
    assert c3.lookup_codes("naics", "5112")[0]["code"] == "511210" and c3.tokens["user"]["email"] == "vendor@example.com"
    # 4. dead refresh token, no credentials → honest remedy
    api.refresh = "refresh-dead"
    c4 = client_for(api, tmp_path, access=jwt(-10), refresh="refresh-dead")
    with pytest.raises(fga.FgaAuthError) as e:
        c4.lookup_codes("naics", "5112")
    assert "login --from-browser" in str(e.value) and "--auto" in str(e.value)
    # 5. wrong password
    c5 = client_for(api, tmp_path, access=jwt(-10), refresh="refresh-dead", creds=("vendor@example.com", "nope"))
    with pytest.raises(fga.FgaAuthError) as e:
        c5.lookup_codes("naics", "5112")
    assert "login failed" in str(e.value)
    # 6. bootstrap from the browser profile's storage_state.json (what bidkit.portal login leaves behind)
    prof = tmp_path / "prof"; prof.mkdir()
    (prof / "storage_state.json").write_text(json.dumps({"cookies": [{"name": "accessToken", "value": jwt(3600), "domain": "portal.example"},
                                                                     {"name": "refreshToken", "value": "refresh-good", "domain": "portal.example"}]}))
    api.refresh = "refresh-good"
    c6 = fga.FgaClient({}, token_file=str(tmp_path / "t6.json"), http=api, credentials=lambda: None)
    c6.import_browser_tokens(str(prof))
    assert c6.tokens["refreshToken"] == "refresh-good" and c6.lookup_codes("naics", "541511")
    with pytest.raises(fga.FgaAuthError):
        c6.import_browser_tokens(str(tmp_path / "nowhere"))


def test_file_opportunity_creates_folder_record_docs_and_brief_reads_it(api, tmp_path):
    from bidkit import brief
    c = client_for(api, tmp_path)
    folder, pr, downloaded = fga.file_opportunity(c, "opp-1", str(tmp_path / "opps"), template_dir=TEMPLATE)
    assert os.path.basename(folder) == "SRC-1-Records-Management-System-Replacement"
    oj = json.load(open(os.path.join(folder, "opportunity.json")))
    assert oj["id"] == "SRC-1-Records-Management-System-Replacement" and oj["agency"] == "Department of Examples" and oj["agency_source"] == "bidkit.fga (portal record)"
    assert oj["title"] == "Records Management System Replacement" and oj["solicitation_number"] == "SRC-1" and oj["source"]["type"] == "fga"
    assert oj["due"] == {"date": "2026-10-15", "time": "", "timezone": "America/Los_Angeles", "confirmed": False, "source": "bidkit.fga (portal record — DETECTED)"}
    assert oj["sourcing"]["id"] == "opp-1" and "{{" not in json.dumps(oj)
    rec = json.load(open(os.path.join(folder, "rfp", "portal-record.json")))[0]
    assert rec["portal"] == "fga" and rec["reference"] == "SRC-1" and rec["closed"] == "2026-10-15" and rec["estimated_value"] == 1200000.0
    assert rec["estimated_value_text"] == "$250,000–$1,200,000 (FGA estimate)" and "aggregator" in rec["estimated_value_label"]
    assert [d["name"] for d in rec["documents"]] == ["RFP.pdf", "Forms.xlsx"] and rec["naics"] == "541511" and rec["psc"] == "7A20"
    # one document downloaded, one 403 at the aggregator's storage → recorded, with the source system as the fallback
    assert downloaded[0] == "RFP.pdf" and downloaded[1].startswith("ERROR Forms.xlsx: HTTP 403")
    assert open(os.path.join(folder, "rfp", "RFP.pdf"), "rb").read().startswith(b"%PDF")
    fetch_md = open(os.path.join(folder, "rfp", "portal-fetch.md")).read()
    assert "**ERROR** Forms.xlsx" in fetch_md and "get them from the source system instead: https://source.example/opp/1" in fetch_md
    assert "- https://source.example/opp/1" in open(os.path.join(folder, "initial-email", "links.md")).read()
    note = open(os.path.join(folder, "sourcing", "fga-record.md")).read()
    assert "## FGA AI summary" in note and "summary 1" in note and "**due 2026-10-15**" in note
    # brief folds the record in: due from the portal, FGA's value with its own label, agency kept
    facts, changed, nq = brief.run(folder)
    assert facts["schedule"]["due"]["date"] == "2026-10-15" and "portal-record.json (federalgovadvisors.com)" in facts["schedule"]["due"]["source"]
    assert facts["money_value_signals"][0]["amount"] == 1200000.0 and "aggregator's model" in facts["money_value_signals"][0]["snippet"]
    oj2 = json.load(open(os.path.join(folder, "opportunity.json")))
    assert oj2["portal_record"]["reference"] == "SRC-1" and oj2["agency"] == "Department of Examples"
    # refuses to clobber an existing folder
    with pytest.raises(fga.FgaError):
        fga.file_opportunity(c, "opp-1", str(tmp_path / "opps"), template_dir=TEMPLATE)
    # without a template: a minimal opportunity.json
    folder2, _, _ = fga.file_opportunity(c, "opp-3", str(tmp_path / "opps"), template_dir=None, docs=False)
    oj3 = json.load(open(os.path.join(folder2, "opportunity.json")))
    assert oj3["solicitation_number"] == "SRC-3" and oj3["due"]["date"] == "2026-11-01" and not os.path.exists(os.path.join(folder2, "rfp", "portal-fetch.md"))


def test_cli_codes_search_and_file(api, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fga, "_urllib_http", api)
    tf = tmp_path / "tokens.json"; tf.write_text(json.dumps({"accessToken": api.access, "refreshToken": "refresh-good"}))
    crit = tmp_path / "criteria.json"
    crit.write_text(json.dumps({"naics": ["541511"], "psc": ["D302"], "vary_last_digits": 1, "min_days_to_due": 0}))
    assert fga.main(["--token-file", str(tf), "codes", "--criteria", str(crit)]) == 0
    out = capsys.readouterr().out
    assert "NAICS (4 codes" in out and "541513" in out and "PSC (3 codes" in out and "naics-541511" in out
    assert fga.main(["--token-file", str(tf), "search", "--criteria", str(crit), "--out", str(tmp_path / "rep"), "--state", str(tmp_path / "seen.json")]) == 0
    out = capsys.readouterr().out
    assert "open match(es)" in out and "NEW" in out and (tmp_path / "rep" / "latest.csv").exists()
    assert fga.main(["--token-file", str(tf), "file", "opp-2", "--out", str(tmp_path / "opps"), "--template", TEMPLATE, "--no-docs"]) == 0
    assert "filed" in capsys.readouterr().out and (tmp_path / "opps" / "SRC-2-Data-Entry" / "opportunity.json").exists()
    # login status line and the auth failure exit code
    assert fga.main(["--token-file", str(tf), "login"]) == 0 and "token ok until" in capsys.readouterr().out
    tf.write_text(json.dumps({"accessToken": jwt(-5), "refreshToken": "refresh-dead"})); api.refresh = "refresh-dead"
    assert fga.main(["--token-file", str(tf), "codes", "--criteria", str(crit)]) == 3
    assert "FGA AUTH" in capsys.readouterr().out


def test_profile_sync_is_additive_backed_up_and_verified(api, tmp_path, capsys):
    c = client_for(api, tmp_path)
    crit = {"naics": ["541511"], "psc": ["D302"], "vary_last_digits": 1}
    # dry run: a plan, no PATCH, no backup
    plan, backup, after = fga.sync_business_profile(c, crit, apply=False)
    assert plan["naics"] == {"current": ["541511"], "add": ["541512", "541513", "541519"], "remove": [], "codes": ["541511", "541512", "541513", "541519"],
                             "ids": [NID["541511"], NID["541512"], NID["541513"], NID["541519"]]}
    assert plan["psc"]["add"] == ["D301", "D303"] and plan["psc"]["remove"] == [] and backup is None and after is None and api.patches == []
    # apply: multipart PATCH with JSON id lists, top_naics_codes passed through, backup written 0600, verified by re-read
    plan, backup, after = fga.sync_business_profile(c, crit, apply=True, backup_dir=str(tmp_path / "bk"))
    assert len(api.patches) == 1
    sent = api.patches[0]
    assert json.loads(sent["naics_codes"]) == plan["naics"]["ids"] and json.loads(sent["psc_codes"]) == [PID["D301"], PID["D302"], PID["D303"]]
    assert json.loads(sent["top_naics_codes"]) == [NID["541511"]]
    assert sorted(x["naics_code"] for x in after["naics_codes"]) == ["541511", "541512", "541513", "541519"]
    assert os.path.dirname(backup) == str(tmp_path / "bk") and oct(os.stat(backup).st_mode & 0o777) == "0o600"
    assert json.load(open(backup))["naics_codes"][0]["naics_code"] == "541511" and len(json.load(open(backup))["naics_codes"]) == 1   # the PRE-change profile
    # idempotent: a second apply adds nothing
    plan2, _, _ = fga.sync_business_profile(c, crit, apply=True, backup_dir=str(tmp_path / "bk"))
    assert plan2["naics"]["add"] == [] and plan2["psc"]["add"] == []
    # replace mode removes codes outside the criteria (only when asked)
    api.profile["psc_codes"].append({"id": PID["7A20"], "psc_code": "7A20", "psc_name": "t"})
    plan3, _, _ = fga.sync_business_profile(c, crit, apply=False)
    assert plan3["psc"]["remove"] == [] and "7A20" in plan3["psc"]["codes"]
    plan4, _, _ = fga.sync_business_profile(c, crit, apply=False, replace=True)
    assert plan4["psc"]["remove"] == ["7A20"] and plan4["psc"]["codes"] == ["D301", "D302", "D303"]
    # the verify step catches a write the server silently dropped
    api.drop_on_write = "D303"
    with pytest.raises(fga.FgaError) as e:
        fga.sync_business_profile(c, crit, apply=True, backup_dir=str(tmp_path / "bk"))
    assert "INCOMPLETE" in str(e.value) and "D303" in str(e.value) and "backup:" in str(e.value)
    api.drop_on_write = None
    # CLI
    import bidkit.fga as mod
    tf = tmp_path / "tokens.json"; tf.write_text(json.dumps({"accessToken": api.access, "refreshToken": "refresh-good"}))
    critp = tmp_path / "crit.json"; critp.write_text(json.dumps(crit))
    orig = mod._urllib_http; mod._urllib_http = api
    try:
        assert mod.main(["--token-file", str(tf), "profile", "--criteria", str(critp)]) == 0
        out = capsys.readouterr().out
        assert "dry run" in out and "would add: nothing" in out            # already synced above
        assert mod.main(["--token-file", str(tf), "profile", "--criteria", str(critp), "--apply", "--backup-dir", str(tmp_path / "bk")]) == 0
        assert "profile updated and re-read" in capsys.readouterr().out
    finally:
        mod._urllib_http = orig
