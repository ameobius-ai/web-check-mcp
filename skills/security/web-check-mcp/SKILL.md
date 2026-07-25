---
name: web-check-mcp
description: Run OSINT website recon via web-check-mcp (31 checks, 8 MCP tools, zero pip deps).
version: 0.2.0
metadata:
  hermes:
    tags: [security, osint, mcp, web-check, recon]
    category: security
---

# Web Check MCP

Thin agent wrapper around [Lissy93/web-check](https://github.com/Lissy93/web-check): SSL, DNS, headers, WHOIS, firewall, ports, and 25+ more OpenAPI checks — as MCP tools + CLI. Pure Python 3.10+ stdlib.

Repo: https://github.com/AMEOBIUS-space/web-check-mcp  
PyPI: `pip install web-check-mcp` (0.2.0+)

## When to Use

- User asks to recon a domain/URL (SSL chain, DNS, security headers, WAF, WHOIS, tech stack, …)
- Need a quick multi-check snapshot before deeper investigation
- Prefer structured JSON over scraping the Web Check UI

## Setup

### Install

```bash
pip install web-check-mcp
# or from source: pip install -e /path/to/web-check-mcp
```

### Hermes MCP config (`~/.hermes/config.yaml`)

```yaml
mcp_servers:
  web-check:
    command: web-check-mcp
    args: ["--stdio"]
    # optional — defaults to https://web-check.as93.net/api with xyz failover
    env:
      WEB_CHECK_BASE_URL: "https://web-check.as93.net/api"
```

From a local checkout instead of the console script:

```yaml
mcp_servers:
  web-check:
    command: python3
    args: ["-m", "src.server", "--stdio"]
    cwd: "/absolute/path/to/web-check-mcp"
```

Reload MCP after config changes (`/reload-mcp` or restart Hermes).

### Copy this skill into Hermes (optional)

```bash
mkdir -p ~/.hermes/skills/security
cp -R skills/security/web-check-mcp ~/.hermes/skills/security/
# or: hermes skills path → drop SKILL.md under security/web-check-mcp/
```

## Procedure

1. **Health first** — call `webcheck_health`. Confirm `reachable: true` and note `resolved_base_url`.
2. **Quick recon** — `webcheck_run` with `url` + `group: quick` (get-ip, status, headers, dns, ssl, redirects).
3. **Deepen only as needed**:
   - Security bundle → `webcheck_security` or `group: security`
   - Single fact → `webcheck_ssl` / `webcheck_dns` / `webcheck_headers` / `webcheck_whois`
   - Catalog → `webcheck_list_checks` (optional `group`)
4. **Avoid `heavy` unless asked** — screenshot / ports / traceroute are slow and noisy.
5. **Summarize for the user** — lead with ok/fail counts, resolved base, and the few checks that matter; do not dump full truncated JSON unless requested.

### Tool map

| Tool | Use |
|------|-----|
| `webcheck_health` | API reachability + which public base won |
| `webcheck_list_checks` | Endpoint catalog / groups |
| `webcheck_run` | Parallel multi-check (`group` or `checks[]`) |
| `webcheck_ssl` | Certificate chain |
| `webcheck_dns` | DNS records |
| `webcheck_security` | Security preset bundle |
| `webcheck_headers` | HTTP response headers |
| `webcheck_whois` | Domain registration / RDAP |

### Presets (`group`)

`quick` · `security` · `server` · `quality` · `heavy` · `all`

### Env knobs

| Var | Default | Notes |
|-----|---------|-------|
| `WEB_CHECK_BASE_URL` | `https://web-check.as93.net/api` | Self-host: `http://127.0.0.1:3000/api` |
| `WEB_CHECK_TIMEOUT` | `25` | Seconds per request |
| `WEB_CHECK_MAX_WORKERS` | `6` | Parallel fan-out |
| `WEB_CHECK_MAX_CHARS` | `12000` | Per-check JSON truncation |

### CLI (non-MCP)

```bash
web-check-mcp health
web-check-mcp run example.com --group quick
web-check-mcp check ssl example.com
web-check-mcp list --group security
web-check-mcp --manifest
```

Exit `2` on failed `health` / `check` / empty `run` — useful in scripts.

### Self-host (optional)

```bash
docker run -d --name web-check -p 3000:3000 lissy93/web-check
export WEB_CHECK_BASE_URL=http://127.0.0.1:3000/api
# or: docker compose up -d web-check  (see repo docker-compose.yml)
```

## Pitfalls

- **Vercel 429 / challenge HTML** — `web-check.xyz` may block datacenter IPs. Client auto-fails over to Netlify `as93.net` and sticks to the winner. Prefer default base; only pin xyz if you know it works from your network.
- **HTTP 200 + HTML body** — treated as blocking (challenge page), not success.
- **Truncation** — large payloads get `_truncated` markers; raise `WEB_CHECK_MAX_CHARS` only if context budget allows.
- **Import path** — library import is `from src.client import WebCheckClient` (package layout smell; works on PyPI 0.2.0).
- **No API key** — public mirrors are best-effort; heavy/production load → self-host upstream.
- **Rate limits** — batch domains slowly; don't fan out `all`/`heavy` across many hosts in parallel sessions.

## Verification

```bash
web-check-mcp health          # reachable true
web-check-mcp --manifest       # server name web-check-mcp, 8 tools
web-check-mcp run example.com --group quick   # ok_count > 0
```

In Hermes: after MCP load, tools should appear as `webcheck_*`. Call health, then one quick run on `example.com`.
