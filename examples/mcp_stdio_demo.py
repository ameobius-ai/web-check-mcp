"""Example: MCP stdio session against web-check-mcp.

Pipes a tools/list then a tools/call and prints the response.
"""
import json
import subprocess
import sys


def call(server_proc, method, params=None, req_id=1):
    req = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
    server_proc.stdin.write(json.dumps(req) + "\n")
    server_proc.stdin.flush()
    line = server_proc.stdout.readline()
    return json.loads(line)


def main():
    proc = subprocess.Popen(
        [sys.executable, "-m", "src.server", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        cwd=__import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))),
    )
    try:
        init = call(proc, "initialize")
        print("server:", init["result"]["serverInfo"])
        listed = call(proc, "tools/list", req_id=2)
        names = [t["name"] for t in listed["result"]["tools"]]
        print(f"{len(names)} tools: {', '.join(names)}")

        ran = call(
            proc,
            "tools/call",
            {"name": "webcheck_run", "arguments": {"url": "discord.com", "group": "quick"}},
            req_id=3,
        )
        text = ran["result"]["content"][0]["text"]
        data = json.loads(text)
        print(f"ok={data['ok_count']}/{len(data['results'])} base={data.get('resolved_base_url')}")
    finally:
        if proc.stdin is not None:
            proc.stdin.close()
        proc.wait(timeout=5)


if __name__ == "__main__":
    main()
