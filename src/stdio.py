"""Dual-mode MCP stdio transport for web-check-mcp (WC-010).

The MCP 2024-11-05 stdio spec uses newline-delimited JSON (NDJSON).
Several hosts built on the TypeScript SDK instead speak LSP-style
``Content-Length`` framing. This module speaks both:

* incoming messages are auto-detected per message
* replies are written back using the framing of the last parsed request

Run standalone::

    python -m src.stdio
"""
from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from typing import Any, TextIO

NDJSON = "ndjson"
CONTENT_LENGTH = "content-length"

# Protocol version advertised when the client does not request one.
PROTOCOL_VERSION = "2024-11-05"

_MISSING = object()


def encode_message(obj: dict[str, Any], mode: str = NDJSON) -> str:
    """Serialize a JSON-RPC object for stdout.

    ``ndjson`` emits one compact JSON object followed by a newline.
    ``content-length`` emits LSP-style headers; the length counts UTF-8 bytes.
    """
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if mode == CONTENT_LENGTH:
        n = len(body.encode("utf-8"))
        return f"Content-Length: {n}\r\n\r\n{body}"
    return body + "\n"


def iter_messages(stream: TextIO) -> Iterator[tuple[dict[str, Any] | None, str, str | None]]:
    """Yield ``(message | None, framing_mode, parse_error | None)``.

    Blank lines between messages are skipped. A malformed body yields a
    ``None`` message plus the decoder error so the caller can reply -32700.
    """
    while True:
        first = stream.readline()
        if first == "":
            return
        stripped = first.strip()
        if not stripped:
            continue

        if stripped.lower().startswith("content-length:"):
            headers: dict[str, str] = {}
            key, _, val = stripped.partition(":")
            headers[key.strip().lower()] = val.strip()
            while True:
                hline = stream.readline()
                if hline == "":
                    return
                if hline.strip() == "":
                    break
                k, _, v = hline.partition(":")
                if k:
                    headers[k.strip().lower()] = v.strip()
            try:
                length = int(headers.get("content-length", "0"))
            except ValueError:
                length = 0
            if length <= 0:
                continue
            body = stream.read(length)
            if body == "":
                return
            try:
                yield json.loads(body), CONTENT_LENGTH, None
            except json.JSONDecodeError as e:
                yield None, CONTENT_LENGTH, str(e)
            continue

        try:
            yield json.loads(stripped), NDJSON, None
        except json.JSONDecodeError as e:
            yield None, NDJSON, str(e)


def write_message(obj: dict[str, Any], mode: str, out: TextIO | None = None) -> None:
    dest = out if out is not None else sys.stdout
    dest.write(encode_message(obj, mode=mode))
    dest.flush()


def handle_rpc(server: Any, request: dict[str, Any]) -> tuple[dict[str, Any] | None, bool]:
    """Dispatch one JSON-RPC request against an MCP server object.

    Returns ``(response | None, should_stop)``. Requests without an ``id``
    are notifications and never produce a response.
    """
    method = request.get("method", "")
    req_id = request.get("id", _MISSING)
    has_id = req_id is not _MISSING
    params = request.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    def _resp(result: Any = None, error: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if not has_id:
            return None
        out: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id}
        if error is not None:
            out["error"] = error
        else:
            out["result"] = result if result is not None else {}
        return out

    if method == "initialize":
        return _resp(
            {
                "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {"name": server.name, "version": server.version},
                "instructions": (
                    "Web Check OSINT tools. Prefer webcheck_run with group=quick; "
                    "call webcheck_health if reachability is unclear."
                ),
            }
        ), False

    if method == "tools/list":
        return _resp({"tools": server.list_tools()}), False

    if method == "tools/call":
        result = server.handle_tool_call(params.get("name", ""), params.get("arguments") or {})
        return _resp({"content": [{"type": "text", "text": result}]}), False

    if method in ("resources/list", "prompts/list"):
        key = "resources" if method.startswith("resources") else "prompts"
        return _resp({key: []}), False

    if method == "ping":
        return _resp({}), False

    if method == "shutdown":
        return _resp({}), True

    if str(method).startswith("notifications/"):
        return _resp({}), False

    return _resp(error={"code": -32601, "message": f"Method not found: {method}"}), False


def run_stdio(
    server: Any | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> None:
    """Serve MCP over stdio until EOF or a ``shutdown`` request."""
    if server is None:
        from .server import WebCheckMCPServer

        server = WebCheckMCPServer()

    mode = NDJSON
    in_stream = stdin if stdin is not None else sys.stdin
    out_stream = stdout if stdout is not None else sys.stdout

    for message, frame_mode, err in iter_messages(in_stream):
        mode = frame_mode or mode
        if err is not None or message is None:
            write_message(
                {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
                mode,
                out_stream,
            )
            continue

        response, stop = handle_rpc(server, message)
        if response is not None:
            write_message(response, mode, out_stream)
        if stop:
            break


def main() -> None:
    run_stdio()


if __name__ == "__main__":
    main()
