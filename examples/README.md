# Examples

## library_demo.py

Use WebCheckClient as a Python library — health, single check, run, security bundle.

```bash
python examples/library_demo.py
```

## mcp_stdio_demo.py

Drive the MCP server over stdin/stdout JSON-RPC — initialize, tools/list, tools/call.

```bash
python examples/mcp_stdio_demo.py
```

## Claude Desktop / Hermes config

```json
{
  "mcpServers": {
    "web-check": {
      "command": "web-check-mcp",
      "args": ["--stdio"],
      "env": {
        "WEB_CHECK_BASE_URL": "https://web-check.as93.net/api"
      }
    }
  }
}
```

Or from source:

```json
{
  "mcpServers": {
    "web-check": {
      "command": "python3",
      "args": ["-m", "src.server", "--stdio"],
      "cwd": "/absolute/path/to/web-check-mcp"
    }
  }
}
```
