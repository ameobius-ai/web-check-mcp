"""Tests for web-check-mcp — client + MCP server (mocked network)."""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, Tuple
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.client import CHECK_GROUPS, CHECKS, WebCheckClient, truncate_payload
from src.server import TOOL_DEFS, WebCheckMCPServer, _cli


# ── fixtures ──────────────────────────────────────────────────────────────

def _ok_payload(check: str) -> Dict[str, Any]:
    return {"check": check, "ok": True, "sample": True, "value": "x" * 20}


class FakeOpener:
    """Callable opener: returns (status, body) based on URL path."""

    def __init__(self, mapping: Dict[str, Tuple[int, Any]] | None = None, default_status: int = 200):
        self.mapping = mapping or {}
        self.default_status = default_status
        self.calls = []

    def __call__(self, url: str, timeout: int = 25):
        self.calls.append(url)
        for key, (status, body) in self.mapping.items():
            if key in url:
                if not isinstance(body, (str, bytes)):
                    body = json.dumps(body)
                return status, body
        return self.default_status, json.dumps({"ok": True, "url": url})


# ── catalog ───────────────────────────────────────────────────────────────

class TestCatalog:
    def test_check_count(self):
        assert len(CHECKS) == 31

    def test_groups_cover_known_keys(self):
        for group, names in CHECK_GROUPS.items():
            for n in names:
                assert n in CHECKS, f"{n} missing from CHECKS (group={group})"

    def test_quick_subset(self):
        assert "ssl" in CHECK_GROUPS["quick"]
        assert "dns" in CHECK_GROUPS["quick"]

    def test_list_checks_all(self):
        c = WebCheckClient(opener=FakeOpener())
        items = c.list_checks()
        assert len(items) == 31
        assert {i["name"] for i in items} == set(CHECKS)

    def test_list_checks_group(self):
        c = WebCheckClient(opener=FakeOpener())
        items = c.list_checks(group="security")
        assert len(items) == len(CHECK_GROUPS["security"])

    def test_list_checks_bad_group(self):
        c = WebCheckClient(opener=FakeOpener())
        with pytest.raises(ValueError):
            c.list_checks(group="nope")

    def test_resolve_checks_default_quick(self):
        c = WebCheckClient(opener=FakeOpener())
        assert c.resolve_checks() == CHECK_GROUPS["quick"]

    def test_resolve_unknown_check(self):
        c = WebCheckClient(opener=FakeOpener())
        with pytest.raises(ValueError):
            c.resolve_checks(checks=["not-a-check"])


# ── truncate ──────────────────────────────────────────────────────────────

class TestTruncate:
    def test_small_passthrough(self):
        data = {"a": 1}
        assert truncate_payload(data, 1000) == data

    def test_long_string(self):
        data = "x" * 5000
        out = truncate_payload(data, 100)
        assert isinstance(out, str)
        assert out.endswith("[truncated]")
        assert len(out) < 150

    def test_long_list(self):
        data = [{"i": i, "blob": "y" * 200} for i in range(50)]
        out = truncate_payload(data, 500)
        assert out.get("_truncated") is True
        assert out["_items_kept"] < 50


# ── client ────────────────────────────────────────────────────────────────

class TestClient:
    def test_check_one_ok(self):
        opener = FakeOpener({"/ssl": (200, {"subject": "CN=example.com"})})
        c = WebCheckClient(base_url="http://local/api", opener=opener)
        res = c.check_one("ssl", "example.com")
        assert res["ok"] is True
        assert res["status"] == 200
        assert res["data"]["subject"] == "CN=example.com"
        assert "url=https%3A%2F%2Fexample.com" in opener.calls[0] or "example.com" in opener.calls[0]

    def test_check_one_http_error(self):
        opener = FakeOpener({"/dns": (403, {"error": "Forbidden"})})
        c = WebCheckClient(base_url="http://local/api", opener=opener)
        res = c.check_one("dns", "https://example.com")
        # FakeOpener returns status directly without raising; status 403 => not ok
        assert res["status"] == 403
        assert res["ok"] is False

    def test_check_one_unknown(self):
        c = WebCheckClient(opener=FakeOpener())
        res = c.check_one("nope", "example.com")
        assert res["ok"] is False
        assert "Unknown" in res["error"]

    def test_run_parallel(self):
        opener = FakeOpener(
            {
                "/ssl": (200, {"ssl": True}),
                "/dns": (200, {"dns": True}),
                "/headers": (200, {"h": 1}),
            }
        )
        c = WebCheckClient(base_url="http://local/api", opener=opener, max_workers=3)
        out = c.run("example.com", checks=["ssl", "dns", "headers"])
        assert out["ok_count"] == 3
        assert out["fail_count"] == 0
        assert len(out["results"]) == 3
        assert out["url"] == "https://example.com"

    def test_run_group_security(self):
        opener = FakeOpener(default_status=200)
        c = WebCheckClient(base_url="http://local/api", opener=opener)
        out = c.run("https://example.com", group="security")
        assert out["checks_requested"] == CHECK_GROUPS["security"]
        assert out["ok_count"] == len(CHECK_GROUPS["security"])

    def test_health(self):
        opener = FakeOpener({"/get-ip": (200, {"ip": "1.2.3.4"})})
        c = WebCheckClient(base_url="http://local/api", opener=opener)
        h = c.health()
        assert h["reachable"] is True
        assert "hint" in h

    def test_normalize_base_adds_api(self):
        opener = FakeOpener({"/get-ip": (200, {"ip": "9.9.9.9"})})
        c = WebCheckClient(base_url="http://127.0.0.1:3000", opener=opener)
        assert c.base_url.endswith("/api")


# ── MCP server ────────────────────────────────────────────────────────────

class TestMCPServer:
    def test_tool_count(self):
        assert len(TOOL_DEFS) == 8

    def test_tools_have_annotations(self):
        for t in TOOL_DEFS:
            assert "annotations" in t
            assert t["annotations"]["readOnlyHint"] is True
            assert t["annotations"]["openWorldHint"] is True

    def test_tools_have_schema(self):
        for t in TOOL_DEFS:
            assert t["inputSchema"]["type"] == "object"
            assert "name" in t and "description" in t

    def test_manifest(self):
        s = WebCheckMCPServer()
        m = s.manifest()
        assert m["server"]["name"] == "web-check-mcp"
        assert len(m["tools"]) == 8
        assert m["config"]["check_count"] == 31

    def test_list_checks_tool(self):
        s = WebCheckMCPServer()
        raw = s.handle_tool_call("webcheck_list_checks", {"group": "quick"})
        data = json.loads(raw)
        assert data["count"] == len(CHECK_GROUPS["quick"])

    def test_run_tool_mocked(self, monkeypatch):
        s = WebCheckMCPServer()

        def fake_run(self, url, checks=None, group=None, max_workers=None):
            return {"url": url, "ok_count": 1, "fail_count": 0, "results": [{"check": "ssl", "ok": True}]}

        monkeypatch.setattr(WebCheckClient, "run", fake_run)
        raw = s.handle_tool_call("webcheck_run", {"url": "example.com", "group": "quick"})
        data = json.loads(raw)
        assert data["ok_count"] == 1

    def test_ssl_tool_mocked(self, monkeypatch):
        s = WebCheckMCPServer()

        def fake_one(self, check, url):
            return {"check": check, "ok": True, "data": {"subject": "x"}}

        monkeypatch.setattr(WebCheckClient, "check_one", fake_one)
        raw = s.handle_tool_call("webcheck_ssl", {"url": "example.com"})
        data = json.loads(raw)
        assert data["check"] == "ssl"
        assert data["ok"] is True

    def test_unknown_tool(self):
        s = WebCheckMCPServer()
        data = json.loads(s.handle_tool_call("nope", {}))
        assert "error" in data

    def test_missing_url(self):
        s = WebCheckMCPServer()
        data = json.loads(s.handle_tool_call("webcheck_run", {}))
        assert "error" in data


# ── CLI ───────────────────────────────────────────────────────────────────

class TestCLI:
    def test_manifest_cli(self, capsys):
        code = _cli(["--manifest"])
        assert code == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["server"]["name"] == "web-check-mcp"

    def test_list_cli(self, capsys):
        code = _cli(["list", "--group", "quick"])
        assert code == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == len(CHECK_GROUPS["quick"])

    def test_help_exit(self):
        code = _cli([])
        assert code == 1
