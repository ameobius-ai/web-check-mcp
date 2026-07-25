# Web Check, but for Agents: Announcing web-check-mcp

> A zero-dependency MCP server that gives Claude, Cursor, and Hermes 31 OSINT checks for any website — wrapping Lissy93's brilliant Web Check into something an agent can actually call.

## TL;DR

```bash
pip install web-check-mcp
web-check-mcp --stdio
```

```json
{
  "mcpServers": {
    "web-check": {
      "command": "web-check-mcp",
      "args": ["--stdio"],
      "env": { "WEB_CHECK_BASE_URL": "https://web-check.as93.net/api" }
    }
  }
}
```

Now your agent can answer "what's discord.com's SSL chain, DNS, WAF, open ports, and tech stack?" in one tool call — parallel, JSON, context-truncated.

Repo: [github.com/AMEOBIUS-space/web-check-mcp](https://github.com/AMEOBIUS-space/web-check-mcp)
PyPI: [pypi.org/project/web-check-mcp](https://pypi.org/project/web-check-mcp/)

## Why

[Lissy93/web-check](https://github.com/lissy93/web-check) is a 34k★ OSINT dashboard: give it a URL, get SSL chain, DNS records, cookies, headers, domain WHOIS, robots.txt, server geo, redirect chain, open ports, traceroute, DNSSEC, carbon footprint, security headers, TLS ciphers, firewall detection, archive history, mail config (SPF/DKIM/DMARC), HSTS, screenshot, threat feeds, and more — 31 endpoints in total, documented as an OpenAPI spec.

But it's a web UI. For an agent, you'd have to either:

- open a browser and scrape the rendered dashboard (slow, brittle),
- hand-craft `curl` calls and hope the JSON isn't too noisy,
- or give up and use four different single-purpose APIs.

**web-check-mcp** fixes that. It's a thin Python client + MCP server that:

- Exposes **8 agent tools**: `webcheck_run`, `webcheck_ssl`, `webcheck_dns`, `webcheck_security`, `webcheck_headers`, `webcheck_whois`, `webcheck_list_checks`, `webcheck_health`
- Runs checks in **parallel** (ThreadPoolExecutor, capped workers)
- **Truncates** each payload to a configurable char budget so a single `ssl` response doesn't blow your context window
- **Falls back** from the Vercel-hosted `web-check.xyz` (which sometimes 429s datacenter IPs) to the Netlify mirror `web-check.as93.net`, and remembers which base worked
- Ships a proper MCP **initialize handshake**, tool annotations (`readOnlyHint`, `openWorldHint`), and a `notifications/initialized` ack
- Has **zero pip dependencies** — pure Python 3.10+ stdlib

## The interesting part: multi-base failover

Here's the non-obvious bit. Web Check's public API is hosted on two CDNs:

| Base | Behavior |
|------|----------|
| `web-check.xyz/api` (Vercel) | Sometimes returns 429 with a Vercel challenge HTML body |
| `web-check.as93.net/api` (Netlify) | More permissive — Cloudflare front, rarely challenges |

A 429 is obvious. The tricky case is **HTTP 200 with a challenge HTML body** — `{"raw": "<!DOCTYPE html>...x-vercel..."}`. The client detects both:

```python
def _is_blocking_status(self, status, data):
    if status in (403, 429, 503):
        return True
    if status == 200 and isinstance(data, dict):
        raw = data.get("raw", "")
        if "x-vercel" in raw or "challenge" in raw[:500].lower():
            return True
    return False
```

When the primary base blocks, the client tries the next one, and the first base that returns a real JSON answer gets "sticky" — subsequent calls skip the probing. That's `self._resolved_base`.

## Tool design

Agents don't want 31 tools — they want a small, predictable surface. So:

- **`webcheck_run`** is the workhorse: `url` + `group` (or explicit `checks[]`) → parallel fan-out → `{ok_count, fail_count, results[]}`. Default `group=quick` runs 6 fast checks.
- **Presets**: `quick` / `security` / `server` / `quality` / `heavy` / `all`. `heavy` (screenshot, ports, traceroute) is opt-in so agents don't accidentally spin up Chromium.
- **Specialized wrappers** (`webcheck_ssl`, `webcheck_dns`, …) for the common single-check case — one-shot, no fan-out overhead.
- **`webcheck_health`** so the agent can self-diagnose: "is the API up? which base resolved?"

## Output truncation

This matters more than people think. A raw `ssl` response for a big site can be 15 KB of JSON. A `tech-stack` or `linked-pages` can be 50 KB. Run six of those in parallel and you've burned 200 KB of context for a single recon step.

`truncate_payload(data, max_chars=12000)` recursively shrinks:

- Long strings → head + `…[truncated]`
- Long lists → first N items + `{_items_kept, _items_total, _truncated}`
- Dicts that still overflow → preview + original char count

Agents stay useful even on dense targets.

## CLI

Not everything has to be MCP. The same code is a CLI:

```bash
$ web-check-mcp list --group quick
$ web-check-mcp health
$ web-check-mcp run discord.com --group quick
$ web-check-mcp check ssl discord.com
```

## Tests

35 pytest tests, all network paths mocked with an injectable `opener` callable. The `FakeOpener` returns `(status, body)` tuples keyed on URL substring — enough to simulate Vercel 429 + Netlify 200 + challenge HTML without touching the network.

```bash
$ python -m pytest tests/ -v
35 passed in 0.08s
```

## What's next

- Bundle a Docker image that ships upstream `lissy93/web-check` + this MCP server pre-wired to `localhost:3000` — one container, UI + API + agent surface.
- GitHub Actions CI matrix on Python 3.10/3.11/3.12 (ubuntu + macos).
- SARIF export for the security bundle, so `webcheck_security` can feed `github/codeql-action/upload-sarif`.
- More bases (Cloudflare Workers mirror? community-hosted?).

## Credits

All credit for the actual OSINT checks goes to [Alicia Sykes (Lissy93)](https://github.com/Lissy93) and the Web Check contributors. This package is a thin agent-facing wrapper; it does nothing the upstream doesn't already do — it just makes it callable.

MIT licensed. Not affiliated with the upstream project.
