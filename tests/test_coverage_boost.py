"""Additional tests to improve coverage to 90%+."""

from __future__ import annotations

import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.client import CHECKS, WebCheckClient
from src.server import WebCheckMCPServer, _cli


class FakeOpener:
    """Mock HTTP opener for testing."""

    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []

    def __call__(self, url, timeout=25):
        self.calls.append(url)
        for key, response in self.responses.items():
            if key in url:
                return response
        return 200, {"ok": True}


class TestMainModule:
    """Test __main__.py entry point."""

    def test_main_module_import(self):
        """Test that __main__ can be imported."""
        from src import __main__

        assert hasattr(__main__, "main")

    def test_main_module_callable(self):
        """Test that main() is callable."""
        from src.__main__ import main

        assert callable(main)


class TestClientEdgeCases:
    """Test edge cases in client.py to improve coverage."""

    def test_normalize_target_empty(self):
        """Test _normalize_target with empty URL."""
        from src.client import _normalize_target

        with pytest.raises(ValueError, match="url is required"):
            _normalize_target("")

    def test_normalize_target_whitespace(self):
        """Test _normalize_target with whitespace."""
        from src.client import _normalize_target

        result = _normalize_target("  example.com  ")
        assert result == "https://example.com"

    def test_ssl_context_with_verify_disabled(self):
        """Test _ssl_context when verify_ssl=False."""
        client = WebCheckClient(verify_ssl=False)
        ctx = client._ssl_context()
        assert ctx is not None
        assert ctx.check_hostname is False

    def test_http_get_with_opener_bytes(self):
        """Test _http_get with opener returning bytes."""
        opener = FakeOpener({"/test": (200, b'{"data": "bytes"}')})
        client = WebCheckClient(opener=opener)
        status, data, _err = client._http_get("http://test/api/test")
        assert status == 200
        assert data["data"] == "bytes"

    def test_http_get_json_decode_error(self):
        """Test _http_get with invalid JSON."""
        opener = FakeOpener({"/test": (200, "not json")})
        client = WebCheckClient(opener=opener, max_chars=100)
        status, data, _err = client._http_get("http://test/api/test")
        assert status == 200
        assert "raw" in data

    def test_http_get_http_error(self):
        """Test _http_get with HTTPError."""
        import urllib.error

        def mock_opener(url, timeout=25):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b'{"error": "not found"}'))

        client = WebCheckClient(opener=mock_opener)
        status, data, _err = client._http_get("http://test/api/missing")
        assert status == 404
        assert "error" in data

    def test_http_get_generic_exception(self):
        """Test _http_get with generic exception."""

        def mock_opener(url, timeout=25):
            raise ConnectionError("Network error")

        client = WebCheckClient(opener=mock_opener)
        status, data, _err = client._http_get("http://test/api/fail")
        assert status == 0
        assert "error" in data

    def test_is_blocking_status_codes(self):
        """Test _is_blocking_status with various codes."""
        client = WebCheckClient()

        assert client._is_blocking_status(403, {}) is True
        assert client._is_blocking_status(429, {}) is True
        assert client._is_blocking_status(503, {}) is True
        assert client._is_blocking_status(200, {}) is False
        assert client._is_blocking_status(404, {}) is False

    def test_is_blocking_status_vercel_challenge(self):
        """Test _is_blocking_status with Vercel challenge."""
        client = WebCheckClient()

        # Vercel challenge detection
        data = {"raw": "<!DOCTYPE html><x-vercel challenge>"}
        assert client._is_blocking_status(200, data) is True

        data = {"raw": "CHALLENGE page"}
        assert client._is_blocking_status(200, data) is True

    def test_candidate_bases_deduplication(self):
        """Test _candidate_bases removes duplicates."""
        client = WebCheckClient(base_url="https://web-check.as93.net/api", fallback=True)
        bases = client._candidate_bases()
        assert len(bases) == len(set(bases))

    def test_candidate_bases_no_fallback(self):
        """Test _candidate_bases without fallback."""
        client = WebCheckClient(base_url="http://localhost:3000/api", fallback=False)
        bases = client._candidate_bases()
        assert len(bases) == 1
        assert bases[0] == "http://localhost:3000/api"

    def test_check_one_with_skipped_data(self):
        """Test check_one with skipped response."""
        opener = FakeOpener({"/ssl": (200, {"skipped": True, "reason": "no data"})})
        client = WebCheckClient(opener=opener)
        result = client.check_one("ssl", "example.com")
        # skipped without error should still be ok
        assert "skipped" in result.get("data", {}) or result.get("ok") is False

    def test_check_one_with_error_data(self):
        """Test check_one with error in response data."""
        opener = FakeOpener({"/dns": (200, {"error": "DNS lookup failed"})})
        client = WebCheckClient(opener=opener)
        result = client.check_one("dns", "example.com")
        assert result["ok"] is False

    def test_run_single_check(self):
        """Test run() with single check (no ThreadPoolExecutor)."""
        opener = FakeOpener({"/ssl": (200, {"subject": "CN=example.com"})})
        client = WebCheckClient(opener=opener)
        result = client.run("example.com", checks=["ssl"])
        assert result["ok_count"] == 1
        assert len(result["results"]) == 1

    def test_run_with_exception_in_thread(self):
        """Test run() when check raises exception in thread."""

        def failing_opener(url, timeout=25):
            if "/ports" in url:
                raise TimeoutError("Connection timeout")
            return 200, {"ok": True}

        client = WebCheckClient(opener=failing_opener, max_workers=2)
        result = client.run("example.com", checks=["ports", "ssl"])
        assert result["fail_count"] >= 1

    def test_run_resolved_base_url(self):
        """Test run() reports resolved_base_url."""
        opener = FakeOpener({"/ssl": (200, {"ok": True}), "/dns": (200, {"ok": True})})
        client = WebCheckClient(opener=opener, base_url="http://test/api")
        result = client.run("example.com", checks=["ssl", "dns"])
        assert "resolved_base_url" in result

    def test_health_with_failed_probe(self):
        """Test health() when probe fails."""
        opener = FakeOpener({"/get-ip": (503, {"error": "Service unavailable"})})
        client = WebCheckClient(opener=opener)
        health = client.health()
        assert health["reachable"] is False
        assert health["status"] == 503


class TestServerEdgeCases:
    """Test edge cases in server.py to improve coverage."""

    def test_call_tool_missing_url(self):
        """Test call_tool with missing required URL parameter."""
        server = WebCheckMCPServer()
        result = server.call_tool("webcheck_ssl", {})
        text = result[0]["text"]
        data = json.loads(text)
        assert "error" in data
        assert "Missing required parameter" in data["error"]

    def test_call_tool_exception(self):
        """Test call_tool with exception during execution."""

        def failing_check(*args, **kwargs):
            raise RuntimeError("Unexpected error")

        server = WebCheckMCPServer(opener=failing_check)
        result = server.call_tool("webcheck_ssl", {"url": "example.com"})
        text = result[0]["text"]
        data = json.loads(text)
        assert "error" in data

    def test_call_tool_all_endpoints(self):
        """Test call_tool for all tool endpoints."""
        server = WebCheckMCPServer()

        # Mock successful responses
        def mock_opener(url, timeout=25):
            return 200, {"ok": True, "data": "test"}

        server._opener = mock_opener

        tools = [
            ("webcheck_list_checks", {"group": "quick"}),
            ("webcheck_health", {}),
            ("webcheck_run", {"url": "example.com", "group": "quick"}),
            ("webcheck_ssl", {"url": "example.com"}),
            ("webcheck_dns", {"url": "example.com"}),
            ("webcheck_security", {"url": "example.com"}),
            ("webcheck_headers", {"url": "example.com"}),
            ("webcheck_whois", {"url": "example.com"}),
        ]

        for tool_name, args in tools:
            result = server.call_tool(tool_name, args)
            assert len(result) > 0
            assert result[0]["type"] == "text"
            data = json.loads(result[0]["text"])
            assert "error" not in data or data.get("ok") is not None

    def test_cli_help(self):
        """Test CLI --help output."""
        with pytest.raises(SystemExit) as exc_info:
            _cli(["--help"])
        assert exc_info.value.code == 0

    def test_cli_unknown_command(self):
        """Test CLI with no command."""
        code = _cli([])
        assert code == 1

    def test_cli_list_command(self):
        """Test CLI list command."""
        code = _cli(["list", "--group", "quick"])
        assert code == 0

    def test_cli_list_all(self):
        """Test CLI list command without group."""
        code = _cli(["list"])
        assert code == 0


class TestTruncatePayloadEdgeCases:
    """Test truncate_payload edge cases."""

    def test_truncate_zero_max_chars(self):
        """Test truncate with max_chars=0."""
        from src.client import truncate_payload

        data = {"key": "value"}
        result = truncate_payload(data, 0)
        assert result == data

    def test_truncate_nested_dict(self):
        """Test truncate with deeply nested dict."""
        from src.client import truncate_payload

        data = {"level1": {"level2": {"level3": "x" * 1000}}}
        result = truncate_payload(data, 500)
        assert "_truncated" in result or len(json.dumps(result)) <= 500

    def test_truncate_very_long_string(self):
        """Test truncate with very long string."""
        from src.client import truncate_payload

        data = "x" * 10000
        result = truncate_payload(data, 100)
        assert isinstance(result, str)
        assert len(result) <= 150
        assert "[truncated]" in result

    def test_truncate_type_error(self):
        """Test truncate with non-serializable object."""
        from src.client import truncate_payload

        class NonSerializable:
            pass

        data = {"obj": NonSerializable()}
        result = truncate_payload(data, 1000)
        # Should not raise, just convert to string
        assert result is not None


class TestQueryParameterNames:
    """Test _query_param_name for all checks."""

    def test_all_checks_have_param(self):
        """Test that all checks return a valid param name."""
        from src.client import _query_param_name

        for check_name in CHECKS:
            param = _query_param_name(check_name)
            assert param in ["url", "domain", "urlString"]

    def test_specific_param_names(self):
        """Test specific parameter names."""
        from src.client import _query_param_name

        assert _query_param_name("whois") == "domain"
        assert _query_param_name("txt-records") == "domain"
        assert _query_param_name("trace-route") == "urlString"
        assert _query_param_name("ssl") == "url"
        assert _query_param_name("dns") == "url"


class TestBaseURLNormalization:
    """Test _normalize_base edge cases."""

    def test_normalize_with_trailing_slash(self):
        """Test normalize removes trailing slash."""
        from src.client import _normalize_base

        result = _normalize_base("http://localhost:3000/")
        assert not result.endswith("/")

    def test_normalize_adds_api_suffix(self):
        """Test normalize adds /api when needed."""
        from src.client import _normalize_base

        result = _normalize_base("http://localhost:3000")
        assert result.endswith("/api")

        result = _normalize_base("https://web-check.xyz")
        assert result.endswith("/api")

    def test_normalize_preserves_api_suffix(self):
        """Test normalize preserves existing /api."""
        from src.client import _normalize_base

        result = _normalize_base("http://localhost:3000/api")
        assert result.endswith("/api")
        assert result.count("/api") == 1


class TestFallbackLogic:
    """Test fallback logic in detail."""

    def test_fallback_auto_enable_public_base(self):
        """Test fallback auto-enables for public bases."""
        client = WebCheckClient(base_url="https://web-check.xyz/api")
        assert client.fallback is True

    def test_fallback_auto_disable_local(self):
        """Test fallback auto-disables for local bases."""
        client = WebCheckClient(base_url="http://localhost:3000/api")
        assert client.fallback is False

    def test_fallback_explicit_override(self):
        """Test explicit fallback parameter overrides auto."""
        client = WebCheckClient(base_url="https://web-check.xyz/api", fallback=False)
        assert client.fallback is False

    def test_resolved_base_sticky(self):
        """Test resolved base URL is reused."""
        opener = FakeOpener(
            {"web-check.xyz": (429, {"error": "rate limit"}), "web-check.as93.net": (200, {"ip": "1.2.3.4"})}
        )

        client = WebCheckClient(base_url="https://web-check.xyz/api", opener=opener, fallback=True)

        # First call should try fallback
        client.check_one("get-ip", "example.com")
        assert client._resolved_base is not None

        # Second call should use resolved base
        result2 = client.check_one("get-ip", "example.com")
        assert result2["ok"] is True
