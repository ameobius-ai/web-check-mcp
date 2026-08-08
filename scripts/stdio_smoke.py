"""Manual stdio smoke test: NDJSON + Content-Length framing against the real server process."""
import json
import subprocess
import sys

CMD = [sys.executable, "-m", "src.server", "--stdio"]


def ndjson_session():
    proc = subprocess.Popen(CMD, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, cwd="/data/web-check-mcp")
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
    ]
    out, _ = proc.communicate("".join(json.dumps(m) + "\n" for m in msgs), timeout=30)
    lines = [json.loads(ln) for ln in out.splitlines() if ln.strip()]
    assert len(lines) == 3, f"expected 3 replies, got {len(lines)}"
    assert lines[0]["result"]["serverInfo"]["name"] == "web-check-mcp"
    assert len(lines[1]["result"]["tools"]) == 8
    print("NDJSON session OK: handshake + 8 tools + shutdown")


def content_length_session():
    proc = subprocess.Popen(CMD, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, cwd="/data/web-check-mcp")
    msgs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "ping"},
        {"jsonrpc": "2.0", "id": 3, "method": "shutdown"},
    ]
    raw = ""
    for m in msgs:
        body = json.dumps(m, separators=(",", ":"))
        raw += f"Content-Length: {len(body.encode())}\r\n\r\n{body}"
    out, _ = proc.communicate(raw, timeout=30)
    assert out.count("Content-Length:") == 3, f"expected 3 framed replies: {out[:200]!r}"
    print("Content-Length session OK: 3 framed replies")


if __name__ == "__main__":
    ndjson_session()
    content_length_session()
    print("STDIO SMOKE: ALL OK")
