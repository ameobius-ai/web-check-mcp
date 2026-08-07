"""Validation tests for Wave 4."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.server import WebCheckMCPServer, _validate_check_name, _validate_url


class TestServerValidation:
    """Test server-side validation."""
    
    def test_webcheck_ssl_validates_url(self):
        """webcheck_ssl validates URL."""
        server = WebCheckMCPServer()
        result = server.call_tool("webcheck_ssl", {"url": ""})
        data = json.loads(result[0]["text"])
        assert "error" in data
        assert "must be a non-empty string" in data["error"]
    
    def test_webcheck_run_validates_group(self):
        """webcheck_run validates group."""
        server = WebCheckMCPServer()
        result = server.call_tool("webcheck_run", {"url": "example.com", "group": "invalid"})
        data = json.loads(result[0]["text"])
        assert "error" in data
        assert "Unknown group" in data["error"]
    
    def test_validate_url_auto_https(self):
        """_validate_url auto-adds https://"""
        assert _validate_url("example.com") == "https://example.com"
    
    def test_validate_check_name_strips_slash(self):
        """_validate_check_name strips leading slash."""
        assert _validate_check_name("/ssl") == "ssl"
