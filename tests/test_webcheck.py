"""Unit tests for web-check-mcp (network-free, all HTTP mocked)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

# Ensure repo root on path so `src.*` imports work without pip install.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.client import (  # noqa: E402
    CHECK_GROUPS,
    CHECKS,
    WebCheckClient,
    _query_param_name,
    truncate_payload,
)
from src.server import WebCheckMCPServer  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeOpener:
    """Minimal stand-in for urllib.request.urlopen / client._opener."""

    def __init__(self, status: int = 200, body: Any = None, error: Exception | None = None):
        self.status = status
        self.body = body if body is not None else {"ok": True}
        self.error = error
        self.calls: list[str] = []

    def __call__(self, url: str, timeout: int = 10) -> tuple[int, str]:
        self.calls.append(url)
        if self.error:
            raise self.error
        return self.status, json.dumps(self.body)


# ---------------------------------------------------------------------------
# Catalog tests
# ---------------------------------------------------------------------------

class TestCatalog(unittest.TestCase):
    def test_check_count(self):
        self.assertEqual(len(CHECKS), 31)

    def test_tool_count(self):
        srv = WebCheckMCPServer()
        self.assertEqual(len(srv.tools()), 8)

    def test_groups_reference_valid_checks(self):
        for group, names in CHECK_GROUPS.items():
            if group == "all":
                continue
            for name in names:
                self.assertIn(name, CHECKS, f"{group!r} references unknown check {name!r}")

    def test_all_group_sorted(self):
        self.assertEqual(CHECK_GROUPS["all"], sorted(CHECKS.keys()))

    def test_list_checks_no_group(self):
        client = WebCheckClient(opener=FakeOpener())
        result = client.list_checks()
        self.assertEqual(len(result), 31)
        self.assertEqual({r["name"] for r in result}, set(CHECKS.keys()))

    def test_list_checks_group(self):
        client = WebCheckClient(opener=FakeOpener())
        result = client.list_checks(group="quick")
        self.assertEqual({r["name"] for r in result}, set(CHECK_GROUPS["quick"]))

    def test_list_checks_unknown_group(self):
        client = WebCheckClient(opener=FakeOpener())
        with self.assertRaises(ValueError):
            client.list_checks(group="nonexistent")

    # --- WC-023: query-param names ---
    def test_param_defaults_to_url(self):
        """Most checks should use the default 'url' param."""
        for name in ["archives", "dns", "ssl", "headers", "get-ip", "status"]:
            self.assertEqual(_query_param_name(name), "url", name)

    def test_param_domain_checks(self):
        """txt-records and whois use ?domain= per upstream OpenAPI spec."""
        self.assertEqual(_query_param_name("txt-records"), "domain")
        self.assertEqual(_query_param_name("whois"), "domain")

    def test_param_trace_route(self):
        """trace-route uses ?urlString= per upstream OpenAPI spec."""
        self.assertEqual(_query_param_name("trace-route"), "urlString")

    def test_list_checks_includes_param_field(self):
        """list_checks() now exposes the param name for each check."""
        client = WebCheckClient(opener=FakeOpener())
        by_name = {r["name"]: r for r in client.list_checks()}
        self.assertEqual(by_name["whois"]["param"], "domain")
        self.assertEqual(by_name["txt-records"]["param"], "domain")
        self.assertEqual(by_name["trace-route"]["param"], "urlString")
        self.assertEqual(by_name["dns"]["param"], "url")


# ---------------------------------------------------------------------------
# Truncation tests
# ---------------------------------------------------------------------------

class TestTruncate(unittest.TestCase):
    def test_short_string_unchanged(self):
        self.assertEqual(truncate_payload("hello", max_chars=100), "hello")

    def test_long_string_truncated(self):
        result = truncate_payload("x" * 200, max_chars=50)
        self.assertIsInstance(result, str)
        self.assertIn("truncated", result)

    def test_small_dict_unchanged(self):
        d = {"a": 1, "b": 2}
        self.assertEqual(truncate_payload(d, max_chars=1000), d)

    def test_large_dict_truncated(self):
        d = {str(i): "x" * 100 for i in range(20)}
        result = truncate_payload(d, max_chars=200)
        self.assertTrue(result.get("_truncated"))

    def test_list_truncated(self):
        lst = ["x" * 50] * 30
        result = truncate_payload(lst, max_chars=200)
        self.assertIsInstance(result, dict)
        self.assertIn("_items_kept", result)

    def test_zero_max_chars_passthrough(self):
        data = {"key": "value"}
        self.assertEqual(truncate_payload(data, max_chars=0), data)


# ---------------------------------------------------------------------------
# Client tests (network-free)
# ---------------------------------------------------------------------------

class TestClient(unittest.TestCase):
    def _client(self, status=200, body=None):
        return WebCheckClient(
            base_url="http://localhost:3000/api",
            opener=FakeOpener(status=status, body=body or {"ip": "1.2.3.4"}),
            fallback=False,
        )

    def test_check_one_ok(self):
        client = self._client()
        result = client.check_one("get-ip", "https://example.com")
        self.assertTrue(result["ok"])
        self.assertEqual(result["check"], "get-ip")

    def test_check_one_unknown(self):
        client = self._client()
        result = client.check_one("nonexistent", "https://example.com")
        self.assertFalse(result["ok"])
        self.assertIn("Unknown", result["error"])

    def test_check_one_http_error(self):
        client = WebCheckClient(
            base_url="http://localhost:3000/api",
            opener=FakeOpener(status=500, body={"error": "server error"}),
            fallback=False,
        )
        result = client.check_one("get-ip", "https://example.com")
        self.assertFalse(result["ok"])

    def test_run_quick(self):
        client = self._client(body={"ip": "1.2.3.4", "isUp": True})
        result = client.run("https://example.com", group="quick")
        self.assertIn("results", result)
        self.assertGreater(len(result["results"]), 0)

    def test_health_ok(self):
        client = self._client()
        h = client.health()
        self.assertTrue(h["reachable"])

    def test_normalize_no_scheme(self):
        client = self._client(body={"ip": "1.2.3.4"})
        result = client.check_one("get-ip", "example.com")
        self.assertIn("https://", result["endpoint"])

    def test_blocking_429(self):
        client = WebCheckClient(
            base_url="http://localhost:3000/api",
            opener=FakeOpener(status=429, body={"error": "rate limited"}),
            fallback=False,
        )
        result = client.check_one("get-ip", "https://example.com")
        self.assertFalse(result["ok"])

    # WC-023: verify correct param names hit the wire
    def test_whois_uses_domain_param(self):
        opener = FakeOpener(body={"domain": "example.com"})
        client = WebCheckClient(
            base_url="http://localhost:3000/api",
            opener=opener,
            fallback=False,
        )
        client.check_one("whois", "https://example.com")
        self.assertTrue(opener.calls, "opener should have been called")
        self.assertIn("domain=", opener.calls[0])
        self.assertNotIn("url=", opener.calls[0])

    def test_txt_records_uses_domain_param(self):
        opener = FakeOpener(body={"spf": "v=spf1"})
        client = WebCheckClient(
            base_url="http://localhost:3000/api",
            opener=opener,
            fallback=False,
        )
        client.check_one("txt-records", "https://example.com")
        self.assertIn("domain=", opener.calls[0])
        self.assertNotIn("url=", opener.calls[0])

    def test_trace_route_uses_urlstring_param(self):
        opener = FakeOpener(body={"message": "done", "result": []})
        client = WebCheckClient(
            base_url="http://localhost:3000/api",
            opener=opener,
            fallback=False,
        )
        client.check_one("trace-route", "https://example.com")
        self.assertIn("urlString=", opener.calls[0])
        self.assertNotIn("url=", opener.calls[0])

    def test_regular_check_uses_url_param(self):
        opener = FakeOpener(body={"ip": "1.2.3.4"})
        client = WebCheckClient(
            base_url="http://localhost:3000/api",
            opener=opener,
            fallback=False,
        )
        client.check_one("get-ip", "https://example.com")
        self.assertIn("url=", opener.calls[0])


# ---------------------------------------------------------------------------
# Fallback tests
# ---------------------------------------------------------------------------

class TestFallback(unittest.TestCase):
    def test_fallback_on_429(self):
        """Client should try next base when primary returns 429."""
        call_log: list[str] = []

        def opener(url: str, timeout: int = 10) -> tuple[int, str]:
            call_log.append(url)
            if "as93.net" in url:
                return 429, json.dumps({"error": "rate limited"})
            return 200, json.dumps({"ip": "1.2.3.4"})

        client = WebCheckClient(
            base_url="https://web-check.as93.net/api",
            opener=opener,
            fallback=True,
        )
        result = client.check_one("get-ip", "https://example.com")
        self.assertTrue(result["ok"])
        self.assertGreater(len(call_log), 1)

    def test_no_fallback_when_disabled(self):
        opener = FakeOpener(status=429, body={"error": "rate limited"})
        client = WebCheckClient(
            base_url="http://localhost:3000/api",
            opener=opener,
            fallback=False,
        )
        result = client.check_one("get-ip", "https://example.com")
        self.assertFalse(result["ok"])
        self.assertEqual(len(opener.calls), 1)

    def test_resolved_base_sticky(self):
        """Once a base answers OK, subsequent calls prefer it."""
        call_log: list[str] = []

        def opener(url: str, timeout: int = 10) -> tuple[int, str]:
            call_log.append(url)
            return 200, json.dumps({"ip": "1.2.3.4"})

        client = WebCheckClient(
            base_url="https://web-check.as93.net/api",
            opener=opener,
            fallback=True,
        )
        client.check_one("get-ip", "https://example.com")
        first_base = client._resolved_base
        client.check_one("get-ip", "https://example.com")
        self.assertEqual(client._resolved_base, first_base)

    def test_challenge_html_detection(self):
        """200 with Vercel challenge HTML body should be treated as blocking."""
        opener = FakeOpener(
            status=200,
            body={"raw": "<html>x-vercel-id challenge page</html>"},
        )
        client = WebCheckClient(
            base_url="http://localhost:3000/api",
            opener=opener,
            fallback=False,
        )
        result = client.check_one("get-ip", "https://example.com")
        self.assertFalse(result["ok"])

    def test_health_reflects_resolved_base(self):
        opener = FakeOpener(body={"ip": "1.2.3.4"})
        client = WebCheckClient(
            base_url="https://web-check.as93.net/api",
            opener=opener,
            fallback=False,
        )
        h = client.health()
        self.assertTrue(h["reachable"])
        self.assertIsNotNone(h["resolved_base_url"])


# ---------------------------------------------------------------------------
# MCP server tests
# ---------------------------------------------------------------------------

class TestMCPServer(unittest.TestCase):
    def setUp(self):
        self.opener = FakeOpener(body={"ip": "1.2.3.4"})
        self.server = WebCheckMCPServer(
            base_url="http://localhost:3000/api",
            opener=self.opener,
            fallback=False,
        )

    def test_tools_list(self):
        tools = self.server.tools()
        names = [t["name"] for t in tools]
        self.assertIn("web_check_run", names)
        self.assertIn("web_check_ssl", names)
        self.assertIn("web_check_health", names)

    def test_tool_health(self):
        result = self.server.call_tool("web_check_health", {})
        self.assertIsInstance(result, list)
        self.assertTrue(any("reachable" in str(r) for r in result))

    def test_tool_ssl(self):
        self.opener.body = {"subject": {"CN": "example.com"}}
        result = self.server.call_tool("web_check_ssl", {"url": "https://example.com"})
        self.assertIsInstance(result, list)

    def test_tool_unknown(self):
        result = self.server.call_tool("nonexistent_tool", {})
        text = " ".join(str(r) for r in result)
        self.assertIn("Unknown", text)

    def test_tool_missing_url(self):
        result = self.server.call_tool("web_check_ssl", {})
        text = " ".join(str(r) for r in result)
        self.assertTrue(any(k in text for k in ("required", "error", "missing", "url")))

    def test_tool_run_group(self):
        result = self.server.call_tool("web_check_run", {"url": "https://example.com", "group": "quick"})
        self.assertIsInstance(result, list)
        text = " ".join(str(r) for r in result)
        self.assertIn("example.com", text)


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------

class TestCLI(unittest.TestCase):
    def _run_cli(self, args: list[str]) -> int:
        from src.server import main as server_main
        try:
            server_main(args)
            return 0
        except SystemExit as exc:
            return int(exc.code) if exc.code is not None else 0

    def test_list_command(self):
        code = self._run_cli(["list"])
        self.assertIn(code, (0, 1))

    def test_manifest_command(self):
        code = self._run_cli(["manifest"])
        self.assertIn(code, (0, 1))

    def test_health_command(self):
        with patch("src.client.WebCheckClient.health") as mock_h:
            mock_h.return_value = {
                "reachable": True, "status": 200,
                "base_url": "http://localhost:3000/api",
                "resolved_base_url": "http://localhost:3000/api",
                "fallback_enabled": False, "public_bases": [], "error": None,
                "hint": "",
            }
            code = self._run_cli(["health"])
        self.assertEqual(code, 0)

    def test_health_command_unreachable(self):
        with patch("src.client.WebCheckClient.health") as mock_h:
            mock_h.return_value = {
                "reachable": False, "status": 0,
                "base_url": "http://localhost:3000/api",
                "resolved_base_url": None,
                "fallback_enabled": False, "public_bases": [], "error": "timeout",
                "hint": "",
            }
            code = self._run_cli(["health"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
