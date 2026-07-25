"""MCP Server for Lissy93 Web Check — OSINT website recon for agents.

Wraps WebCheckClient in Model Context Protocol tools.
Zero third-party deps (Python stdlib only).

Modes:
  python -m src.server --stdio      # JSON-RPC over stdin/stdout
  python -m src.server --manifest   # print tool manifest
  python -m src.server --cli ...    # CLI (see argparse)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

from . import __version__
from .client import (
    CHECK_GROUPS,
    CHECKS,
    DEFAULT_BASE_URL,
    DEFAULT_MAX_CHARS,
    DEFAULT_TIMEOUT,
    WebCheckClient,
)

_READ_OPEN = {
    "readOnlyHint": True,
    "openWorldHint": True,
    "destructiveHint": False,
}


def _tool(
    name: str,
    description: str,
    properties: Dict[str, Any],
    required: Optional[List[str]] = None,
) -> Dict[str, Any]:
    schema: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return {
        "name": name,
        "description": description,
        "inputSchema": schema,
        "annotations": dict(_READ_OPEN),
    }


_URL_PROP = {"type": "string", "description": "Target URL or domain (https:// added if missing)"}
_BASE_PROP = {
    "type": "string",
    "description": f"Web Check API base (default env WEB_CHECK_BASE_URL or {DEFAULT_BASE_URL})",
}
_TIMEOUT_PROP = {"type": "integer", "description": "Per-request timeout seconds", "default": DEFAULT_TIMEOUT}
_MAX_CHARS_PROP = {
    "type": "integer",
    "description": "Truncate each check payload to this many JSON chars",
    "default": DEFAULT_MAX_CHARS,
}

TOOL_DEFS: List[Dict[str, Any]] = [
    _tool(
        "webcheck_list_checks",
        "List available Web Check endpoints/groups (ssl, dns, headers, ports, …).",
        {
            "group": {
                "type": "string",
                "description": "Optional preset: quick|security|server|quality|heavy|all",
            }
        },
        required=[],
    ),
    _tool(
        "webcheck_health",
        "Probe whether the configured Web Check API base URL is reachable.",
        {"base_url": _BASE_PROP, "timeout": _TIMEOUT_PROP},
        required=[],
    ),
    _tool(
        "webcheck_run",
        "Run one or more Web Check jobs against a URL (parallel fan-out). "
        "Prefer group=quick for recon; avoid heavy (screenshot/ports/traceroute) unless needed.",
        {
            "url": _URL_PROP,
            "checks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Explicit check names (e.g. ssl, dns, headers). Overrides group.",
            },
            "group": {
                "type": "string",
                "description": "Preset group if checks omitted: quick|security|server|quality|heavy|all",
                "default": "quick",
            },
            "base_url": _BASE_PROP,
            "timeout": _TIMEOUT_PROP,
            "max_workers": {"type": "integer", "default": 6},
            "max_chars": _MAX_CHARS_PROP,
        },
        required=["url"],
    ),
    _tool(
        "webcheck_ssl",
        "Fetch SSL certificate chain for a URL via Web Check /ssl.",
        {"url": _URL_PROP, "base_url": _BASE_PROP, "timeout": _TIMEOUT_PROP, "max_chars": _MAX_CHARS_PROP},
        required=["url"],
    ),
    _tool(
        "webcheck_dns",
        "Fetch DNS records for a domain via Web Check /dns.",
        {"url": _URL_PROP, "base_url": _BASE_PROP, "timeout": _TIMEOUT_PROP, "max_chars": _MAX_CHARS_PROP},
        required=["url"],
    ),
    _tool(
        "webcheck_security",
        "Security bundle: ssl, tls, hsts, http-security, firewall, dnssec, security-txt, threats, block-lists.",
        {
            "url": _URL_PROP,
            "base_url": _BASE_PROP,
            "timeout": _TIMEOUT_PROP,
            "max_workers": {"type": "integer", "default": 6},
            "max_chars": _MAX_CHARS_PROP,
        },
        required=["url"],
    ),
    _tool(
        "webcheck_headers",
        "Fetch HTTP response headers via Web Check /headers.",
        {"url": _URL_PROP, "base_url": _BASE_PROP, "timeout": _TIMEOUT_PROP, "max_chars": _MAX_CHARS_PROP},
        required=["url"],
    ),
    _tool(
        "webcheck_whois",
        "WHOIS / domain registration data via Web Check /whois.",
        {"url": _URL_PROP, "base_url": _BASE_PROP, "timeout": _TIMEOUT_PROP, "max_chars": _MAX_CHARS_PROP},
        required=["url"],
    ),
]


class WebCheckMCPServer:
    """MCP server exposing Web Check as agent tools."""

    def __init__(
        self,
        name: str = "web-check-mcp",
        version: str = __version__,
        default_base_url: Optional[str] = None,
    ):
        self.name = name
        self.version = version
        self.default_base_url = default_base_url or os.environ.get(
            "WEB_CHECK_BASE_URL", DEFAULT_BASE_URL
        )

    def list_tools(self) -> List[Dict]:
        return TOOL_DEFS

    def manifest(self) -> Dict:
        return {
            "server": {"name": self.name, "version": self.version},
            "capabilities": {"tools": {"listChanged": True}, "resources": {}, "prompts": {}},
            "tools": self.list_tools(),
            "config": {
                "default_base_url": self.default_base_url,
                "check_count": len(CHECKS),
                "groups": sorted(CHECK_GROUPS.keys()),
            },
        }

    def _client(self, args: Dict[str, Any]) -> WebCheckClient:
        return WebCheckClient(
            base_url=args.get("base_url") or self.default_base_url,
            timeout=int(args.get("timeout") or DEFAULT_TIMEOUT),
            max_workers=int(args.get("max_workers") or 6),
            max_chars=int(args.get("max_chars") or DEFAULT_MAX_CHARS),
        )

    def handle_tool_call(self, name: str, args: Dict[str, Any]) -> str:
        args = args or {}
        try:
            if name == "webcheck_list_checks":
                client = WebCheckClient(base_url=self.default_base_url)
                group = args.get("group")
                items = client.list_checks(group=group)
                return json.dumps(
                    {
                        "group": group or "all",
                        "count": len(items),
                        "checks": items,
                        "groups": {k: v for k, v in CHECK_GROUPS.items()},
                    },
                    ensure_ascii=False,
                )

            if name == "webcheck_health":
                client = self._client(args)
                return json.dumps(client.health(), ensure_ascii=False)

            if name == "webcheck_run":
                client = self._client(args)
                result = client.run(
                    url=args["url"],
                    checks=args.get("checks"),
                    group=args.get("group") or ("quick" if not args.get("checks") else None),
                    max_workers=args.get("max_workers"),
                )
                return json.dumps(result, ensure_ascii=False)

            if name == "webcheck_ssl":
                client = self._client(args)
                return json.dumps(client.check_one("ssl", args["url"]), ensure_ascii=False)

            if name == "webcheck_dns":
                client = self._client(args)
                return json.dumps(client.check_one("dns", args["url"]), ensure_ascii=False)

            if name == "webcheck_security":
                client = self._client(args)
                return json.dumps(
                    client.run(url=args["url"], group="security", max_workers=args.get("max_workers")),
                    ensure_ascii=False,
                )

            if name == "webcheck_headers":
                client = self._client(args)
                return json.dumps(client.check_one("headers", args["url"]), ensure_ascii=False)

            if name == "webcheck_whois":
                client = self._client(args)
                return json.dumps(client.check_one("whois", args["url"]), ensure_ascii=False)

            return json.dumps({"error": f"Unknown tool: {name}"})
        except KeyError as e:
            return json.dumps({"error": f"Missing required parameter: {e}", "tool": name})
        except Exception as e:  # noqa: BLE001
            return json.dumps({"error": str(e), "tool": name})


def _run_stdio() -> None:
    server = WebCheckMCPServer()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            print(
                json.dumps(
                    {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}}
                ),
                flush=True,
            )
            continue

        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params") or {}

        if method == "initialize":
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": True}},
                    "serverInfo": {"name": server.name, "version": server.version},
                },
            }
        elif method == "notifications/initialized":
            # notification — no response required, but some clients expect ack
            if req_id is None:
                continue
            response = {"jsonrpc": "2.0", "id": req_id, "result": {}}
        elif method == "tools/list":
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": server.list_tools()},
            }
        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments") or {}
            result = server.handle_tool_call(tool_name, tool_args)
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": result}]},
            }
        elif method == "ping":
            response = {"jsonrpc": "2.0", "id": req_id, "result": {}}
        elif method == "shutdown":
            response = {"jsonrpc": "2.0", "id": req_id, "result": {}}
            print(json.dumps(response), flush=True)
            break
        else:
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

        print(json.dumps(response), flush=True)


def _cli(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="web-check-mcp — agent wrapper for Lissy93 Web Check API"
    )
    parser.add_argument("--stdio", action="store_true", help="STDIO JSON-RPC MCP mode")
    parser.add_argument("--manifest", action="store_true", help="Print MCP manifest JSON")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("WEB_CHECK_BASE_URL", DEFAULT_BASE_URL),
        help="Web Check API base URL",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    parser.add_argument("--max-workers", type=int, default=6)

    sub = parser.add_subparsers(dest="cmd")

    p_list = sub.add_parser("list", help="List checks")
    p_list.add_argument("--group", default=None)

    p_health = sub.add_parser("health", help="Probe API base")

    p_run = sub.add_parser("run", help="Run checks against a URL")
    p_run.add_argument("url")
    p_run.add_argument("--group", default="quick")
    p_run.add_argument("--check", action="append", dest="checks", default=None)

    p_one = sub.add_parser("check", help="Run a single named check")
    p_one.add_argument("check_name")
    p_one.add_argument("url")

    args = parser.parse_args(argv)

    if args.stdio:
        _run_stdio()
        return 0
    if args.manifest:
        print(json.dumps(WebCheckMCPServer(default_base_url=args.base_url).manifest(), indent=2))
        return 0

    client = WebCheckClient(
        base_url=args.base_url,
        timeout=args.timeout,
        max_workers=args.max_workers,
        max_chars=args.max_chars,
    )

    if args.cmd == "list":
        print(json.dumps(client.list_checks(group=args.group), indent=2))
        return 0
    if args.cmd == "health":
        h = client.health()
        print(json.dumps(h, indent=2))
        return 0 if h.get("reachable") else 2
    if args.cmd == "run":
        out = client.run(url=args.url, checks=args.checks, group=None if args.checks else args.group)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0 if out.get("ok_count", 0) > 0 else 2
    if args.cmd == "check":
        one = client.check_one(args.check_name, args.url)
        print(json.dumps(one, indent=2, ensure_ascii=False))
        return 0 if one.get("ok") else 2

    parser.print_help()
    return 1


def main() -> None:
    raise SystemExit(_cli())


if __name__ == "__main__":
    main()
