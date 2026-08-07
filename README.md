# Web Check MCP

<!-- mcp-name: io.github.AMEOBIUS-space/web-check-mcp -->

[![PyPI](https://img.shields.io/pypi/v/web-check-mcp)](https://pypi.org/project/web-check-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/web-check-mcp)](https://pypi.org/project/web-check-mcp/)
[![CI](https://github.com/AMEOBIUS-space/web-check-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/AMEOBIUS-space/web-check-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![codecov](https://codecov.io/gh/ameobius-ai/web-check-mcp/branch/main/graph/badge.svg)](https://codecov.io/gh/ameobius-ai/web-check-mcp)
[![Security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)
[![code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Imports: isort](https://img.shields.io/badge/%20imports-isort-%231674b1)](https://pycqa.github.io/isort/)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)


> Agent wrapper for [Lissy93/web-check](https://github.com/Lissy93/web-check) — 31 OSINT checks as MCP tools + CLI.

Gap verified 2026-07-25: no public MCP/SDK/Hermes skill existed for this API. This package fills it.

## Features

- **8 MCP tools**: `webcheck_run`, `webcheck_ssl`, `webcheck_dns`, `webcheck_security`, `webcheck_headers`, `webcheck_whois`, `webcheck_list_checks`, `webcheck_health`
- **31 OpenAPI checks** from upstream (`ssl`, `dns`, `headers`, `ports`, `firewall`, `whois`, …)
- **Presets**: `quick` | `security` | `server` | `quality` | `heavy` | `all`
- **Parallel fan-out** + **payload truncation** (agent-context safe)
- **Zero pip deps** — Python 3.10+ stdlib only
- **STDIO JSON-RPC** with `initialize` handshake + tool annotations (`readOnlyHint` + `openWorldHint`)

## Public API works (with fallback)

Two public bases are tried automatically:

| Base | Status |
|------|--------|
| `web-check.as93.net/api` (Netlify mirror) | **200 OK** — more open, Cloudflare front |
| `web-check.xyz/api` (Vercel primary) | **200/429** — may challenge datacenter IPs |

Set `WEB_CHECK_BASE_URL` explicitly to skip probing. Fallback auto-enables when base starts with `https://web-check.` and can be forced via `WebCheckClient(fallback=True)`.

No key, no auth.

## Self-host (optional)

For heavy load or offline use:

```bash
docker run -d --name web-check -p 3000:3000 lissy93/web-check
export WEB_CHECK_BASE_URL=http://127.0.0.1:3000/api
```

Or compose (upstream + thin MCP image):

```bash
docker compose up -d web-check
# MCP stdio still launched by host; see Dockerfile ENTRYPOINT
```

Upstream Go rewrite [`xray-web/web-check-api`](https://github.com/xray-web/web-check-api) is early WIP — prefer Node/Docker image for full endpoint parity.

## Quick Start

```bash
# from repo root
pip install -e .
# or: python3 -m pip install web-check-mcp

# Manifest
python3 -m src.server --manifest

# List checks
python3 -m src.server list --group quick

# Health probe
python3 -m src.server health

# Run quick recon (needs live API)
python3 -m src.server run example.com --group quick

# Single check
python3 -m src.server check ssl example.com

# MCP STDIO (Claude Desktop / Hermes / Cursor)
python3 -m src.server --stdio
```

### Library

```python
from src.client import WebCheckClient

client = WebCheckClient(base_url="http://127.0.0.1:3000/api")
print(client.run("example.com", group="quick"))
print(client.check_one("ssl", "example.com"))
```

## MCP client config

```json
{
  "mcpServers": {
    "web-check": {
      "command": "python3",
      "args": ["-m", "src.server", "--stdio"],
      "cwd": "/absolute/path/to/web-check-mcp",
      "env": {
        "WEB_CHECK_BASE_URL": "http://127.0.0.1:3000/api"
      }
    }
  }
}
```

After `pip install web-check-mcp`:

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

Official registry metadata lives in [`server.json`](./server.json) (`io.github.AMEOBIUS-space/web-check-mcp`). Publish with `mcp-publisher` after the next PyPI release that includes the `mcp-name` marker above.

## Tool Reference

| Tool | Description |
|------|-------------|
| `webcheck_list_checks` | Catalog of endpoints / groups |
| `webcheck_health` | Probe API base reachability |
| `webcheck_run` | Parallel multi-check (default group=`quick`) |
| `webcheck_ssl` | Certificate chain |
| `webcheck_dns` | DNS records |
| `webcheck_security` | Security preset bundle |
| `webcheck_headers` | HTTP headers |
| `webcheck_whois` | Domain WHOIS |

Env: `WEB_CHECK_BASE_URL`, `WEB_CHECK_TIMEOUT`, `WEB_CHECK_MAX_WORKERS`, `WEB_CHECK_MAX_CHARS`.

## Tests

```bash
python3 -m pytest tests/ -v
```

All network paths mocked — no live API required for CI.

## License

MIT. Upstream Web Check © Alicia Sykes, MIT.

Not affiliated with Lissy93; thin agent-facing client only.
