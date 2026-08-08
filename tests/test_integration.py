"""Integration tests with real MCP clients."""

import json
import subprocess

import pytest


@pytest.mark.integration
class TestMCPIntegration:
    """Test MCP server with real JSON-RPC communication."""

    def test_stdio_handshake(self):
        """Test MCP STDIO handshake."""
        proc = subprocess.Popen(
            ["python", "-m", "src.server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            init_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05"},
            }

            proc.stdin.write(json.dumps(init_request) + "\n")
            proc.stdin.flush()

            response = json.loads(proc.stdout.readline())

            assert response["id"] == 1
            assert "result" in response
            assert response["result"]["serverInfo"]["name"] == "web-check-mcp"

            tools_request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}

            proc.stdin.write(json.dumps(tools_request) + "\n")
            proc.stdin.flush()

            response = json.loads(proc.stdout.readline())

            assert response["id"] == 2
            assert len(response["result"]["tools"]) == 8

        finally:
            proc.terminate()
            proc.wait(timeout=5)

    def test_all_tools_respond(self):
        """Test that all 8 tools respond."""
        from src.server import WebCheckMCPServer

        server = WebCheckMCPServer()

        tools = [
            ("webcheck_list_checks", {}),
            ("webcheck_health", {}),
            ("webcheck_ssl", {"url": "example.com"}),
            ("webcheck_dns", {"url": "example.com"}),
            ("webcheck_headers", {"url": "example.com"}),
            ("webcheck_whois", {"url": "example.com"}),
            ("webcheck_security", {"url": "example.com"}),
            ("webcheck_run", {"url": "example.com", "group": "quick"}),
        ]

        for tool_name, args in tools:
            result = server.call_tool(tool_name, args)
            assert len(result) > 0
            assert result[0]["type"] == "text"
            json.loads(result[0]["text"])
