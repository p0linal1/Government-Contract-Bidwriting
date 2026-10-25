"""Offline tests for the Lambda MCP handler (cloud/handler.py). SAM.gov is never called."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cloud"))
import handler  # noqa: E402


@pytest.fixture(autouse=True)
def tokens(monkeypatch):
    monkeypatch.setenv("SAM_TOOL_TOKENS", json.dumps({"alice": "tok-a", "bob": "tok-b"}))
    monkeypatch.delenv("SAM_TOOL_TOKENS_SECRET", raising=False)
    handler._tokens.update(loaded=0.0, by_token={})


def call(body, token="tok-a", method="POST"):
    event = {
        "requestContext": {"http": {"method": method}},
        "headers": {"Authorization": f"Bearer {token}"} if token else {},
        "body": json.dumps(body),
    }
    return handler.lambda_handler(event, None)


def result(response):
    return json.loads(response["body"])["result"]


def test_rejects_missing_and_wrong_tokens():
    assert call({"jsonrpc": "2.0", "id": 1, "method": "ping"}, token=None)["statusCode"] == 401
    assert call({"jsonrpc": "2.0", "id": 1, "method": "ping"}, token="tok-z")["statusCode"] == 401


def test_get_is_not_allowed_on_stateless_server():
    assert call({}, method="GET")["statusCode"] == 405


def test_initialize_and_list_tools():
    init = result(call({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}}))
    assert init["protocolVersion"] == "2025-03-26"
    assert "tools" in init["capabilities"]
    tools = result(call({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))["tools"]
    assert {t["name"] for t in tools} == {"search_opportunities", "get_notice"}


def test_notification_gets_202_and_batch_is_supported():
    assert call({"jsonrpc": "2.0", "method": "notifications/initialized"})["statusCode"] == 202
    batch = call([{"jsonrpc": "2.0", "method": "notifications/initialized"}, {"jsonrpc": "2.0", "id": 7, "method": "ping"}])
    assert json.loads(batch["body"]) == [{"jsonrpc": "2.0", "id": 7, "result": {}}]


def test_bad_codes_are_a_tool_error_not_a_crash():
    res = result(call({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                       "params": {"name": "search_opportunities", "arguments": {"naics": ["54; DROP"]}}}))
    assert res["isError"] and "invalid naics" in res["content"][0]["text"]


def test_search_filters_and_compacts(monkeypatch):
    now = datetime.now(timezone.utc)
    rows = [
        {"notice_id": "a" * 32, "title": "Open", "notice_type": "Solicitation", "set_aside": "SBA",
         "response_date": (now + timedelta(days=5)).isoformat(), "description_excerpt": "<p>Build &amp; host</p>",
         "department": "DOD", "url": "u"},
        {"notice_id": "b" * 32, "title": "Awarded", "notice_type": "Solicitation", "award": {"awardee": "X"},
         "response_date": (now + timedelta(days=5)).isoformat()},
        {"notice_id": "c" * 32, "title": "8a only", "notice_type": "Solicitation", "set_aside": "8A",
         "response_date": (now + timedelta(days=5)).isoformat()},
    ]
    seen = {}

    def fake_collect(profile, **kwargs):
        seen.update(profile)
        return rows, now

    monkeypatch.setattr(handler.fetch, "collect", fake_collect)
    res = result(call({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
        "name": "search_opportunities",
        "arguments": {"naics": ["541511"], "set_aside_eligibility": ["SBA"]}}}))
    data = json.loads(res["content"][0]["text"])
    assert seen["naics"] == ["541511"]
    assert [n["title"] for n in data["notices"]] == ["Open"]
    assert data["notices"][0]["description"] == "Build & host"
    assert data["dropped"] == {"already awarded": 1, "set-aside not eligible (8A)": 1}
    assert data["total"] == 1 and data["has_more"] is False


def test_search_pages_in_stable_order(monkeypatch):
    now = datetime.now(timezone.utc)
    rows = [{"notice_id": f"{i:032x}", "title": f"n{i}", "notice_type": "Solicitation",
             "response_date": (now + timedelta(days=i % 3 + 1)).isoformat()} for i in range(7)]
    monkeypatch.setattr(handler.fetch, "collect", lambda profile, **kw: ([dict(r) for r in reversed(rows)], now))

    def page(offset):
        res = result(call({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {
            "name": "search_opportunities", "arguments": {"naics": ["541511"], "limit": 3, "offset": offset}}}))
        return json.loads(res["content"][0]["text"])

    first, second, third = page(0), page(3), page(6)
    assert first["has_more"] and first["next_offset"] == 3
    assert third["has_more"] is False and third["next_offset"] is None
    ids = [n["notice_id"] for p in (first, second, third) for n in p["notices"]]
    assert len(ids) == len(set(ids)) == 7


def test_get_notice_rejects_bad_ids():
    res = result(call({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                       "params": {"name": "get_notice", "arguments": {"notice_id": "../etc"}}}))
    assert res["isError"]
