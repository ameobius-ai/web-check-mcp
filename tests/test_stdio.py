"""Tests for dual-mode MCP stdio framing (WC-010)."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.server import WebCheckMCPServer
from src.stdio import (
    CONTENT_LENGTH,
    NDJSON,
    PROTOCOL_VERSION,
    encode_message,
    handle_rpc,
    iter_messages,
    run_stdio,
)


def _stream(*requests, mode=NDJSON):
    return io.StringIO("".join(encode_message(r, mode) for r in requests))


class _BrokenPipeOnFlush:
    def __init__(self):
        self._value = ""

    def write(self, value: str) -> int:
        self._value += value
        return len(value)

    def flush(self) -> None:
        raise BrokenPipeError(32, "Broken pipe")

    def getvalue(self) -> str:
        return self._value


class TestEncoding:
    def test_ndjson_is_compact_and_newline_terminated(self):
        assert encode_message({"a": 1}, NDJSON) == '{"a":1}\n'

    def test_content_length_counts_utf8_bytes(self):
        obj = {"msg": "caf\u00e9"}
        raw = encode_message(obj, CONTENT_LENGTH)
        header, body = raw.split("\r\n\r\n", 1)
        assert header.startswith("Content-Length: ")
        assert int(header.split(":", 1)[1]) == len(body.encode("utf-8"))
        assert json.loads(body) == obj


class TestDecoding:
    def test_reads_ndjson(self):
        msgs = list(iter_messages(_stream({"jsonrpc": "2.0", "id": 1, "method": "ping"})))
        assert len(msgs) == 1
        msg, mode, err = msgs[0]
        assert err is None
        assert mode == NDJSON
        assert msg["method"] == "ping"

    def test_reads_content_length(self):
        msgs = list(iter_messages(_stream({"jsonrpc": "2.0", "id": 7, "method": "initialize"}, mode=CONTENT_LENGTH)))
        assert len(msgs) == 1
        msg, mode, err = msgs[0]
        assert err is None
        assert mode == CONTENT_LENGTH
        assert msg["id"] == 7

    def test_reads_mixed_framing_in_one_stream(self):
        raw = encode_message({"id": 1, "method": "ping"}, NDJSON) + encode_message(
            {"id": 2, "method": "ping"}, CONTENT_LENGTH
        )
        modes = [m[1] for m in iter_messages(io.StringIO(raw))]
        assert modes == [NDJSON, CONTENT_LENGTH]

    def test_skips_blank_lines(self):
        raw = "\n\n" + encode_message({"id": 1, "method": "ping"}, NDJSON)
        assert len(list(iter_messages(io.StringIO(raw)))) == 1

    def test_reports_malformed_json(self):
        msg, mode, err = next(iter(iter_messages(io.StringIO("{not-json\n"))))
        assert msg is None
        assert mode == NDJSON
        assert err


class TestHandleRpc:
    def setup_method(self):
        self.server = WebCheckMCPServer()

    def test_initialize_echoes_client_protocol(self):
        resp, stop = handle_rpc(
            self.server,
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        )
        assert stop is False
        assert resp["result"]["protocolVersion"] == "2025-06-18"
        assert resp["result"]["serverInfo"]["name"] == "web-check-mcp"
        assert "instructions" in resp["result"]

    def test_initialize_falls_back_to_default_protocol(self):
        resp, _ = handle_rpc(self.server, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert resp["result"]["protocolVersion"] == PROTOCOL_VERSION

    def test_notification_produces_no_response(self):
        resp, stop = handle_rpc(self.server, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert resp is None
        assert stop is False

    def test_tools_list(self):
        resp, _ = handle_rpc(self.server, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert len(resp["result"]["tools"]) == 8

    def test_empty_resource_and_prompt_catalogs(self):
        res, _ = handle_rpc(self.server, {"jsonrpc": "2.0", "id": 3, "method": "resources/list"})
        pro, _ = handle_rpc(self.server, {"jsonrpc": "2.0", "id": 4, "method": "prompts/list"})
        assert res["result"] == {"resources": []}
        assert pro["result"] == {"prompts": []}

    def test_shutdown_stops_the_loop(self):
        resp, stop = handle_rpc(self.server, {"jsonrpc": "2.0", "id": 9, "method": "shutdown"})
        assert stop is True
        assert resp["result"] == {}

    def test_unknown_method_returns_method_not_found(self):
        resp, _ = handle_rpc(self.server, {"jsonrpc": "2.0", "id": 5, "method": "nope/x"})
        assert resp["error"]["code"] == -32601


class TestStdioLoop:
    def test_ndjson_session(self):
        stdin = _stream(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
        )
        stdout = io.StringIO()
        run_stdio(server=WebCheckMCPServer(), stdin=stdin, stdout=stdout)

        lines = [ln for ln in stdout.getvalue().splitlines() if ln.strip()]
        assert len(lines) == 3  # the notification is silent
        assert json.loads(lines[0])["result"]["serverInfo"]["name"] == "web-check-mcp"
        assert len(json.loads(lines[1])["result"]["tools"]) == 8

    def test_content_length_session_replies_in_kind(self):
        stdin = _stream(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "ping"},
            {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
            mode=CONTENT_LENGTH,
        )
        stdout = io.StringIO()
        run_stdio(server=WebCheckMCPServer(), stdin=stdin, stdout=stdout)

        raw = stdout.getvalue()
        assert "Content-Length:" in raw
        replies = list(iter_messages(io.StringIO(raw)))
        assert len(replies) == 3
        assert all(mode == CONTENT_LENGTH for _, mode, _ in replies)
        assert replies[1][0]["id"] == 2

    def test_malformed_input_gets_parse_error(self):
        stdout = io.StringIO()
        run_stdio(server=WebCheckMCPServer(), stdin=io.StringIO("{oops\n"), stdout=stdout)
        assert json.loads(stdout.getvalue())["error"]["code"] == -32700

    def test_broken_pipe_from_injected_stdout_exits_quietly(self):
        stdout = _BrokenPipeOnFlush()
        stdin = _stream({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})

        run_stdio(server=WebCheckMCPServer(), stdin=stdin, stdout=stdout)

        assert json.loads(stdout.getvalue())["id"] == 1

    def test_subprocess_exits_cleanly_when_host_closes_output_pipe(self):
        proc = subprocess.Popen(
            [sys.executable, "-m", "src.server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert proc.stdin is not None
        assert proc.stdout is not None
        assert proc.stderr is not None

        try:
            proc.stdout.close()
            proc.stdin.write(
                encode_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            )
            proc.stdin.close()
            return_code = proc.wait(timeout=5)
            stderr = proc.stderr.read()
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
            if not proc.stdin.closed:
                proc.stdin.close()
            proc.stderr.close()

        assert return_code == 0
        assert stderr == ""
