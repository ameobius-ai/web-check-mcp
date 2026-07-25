# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.3.0] — 2026-07-25

### Fixed
- **Correct query-param names for three endpoints** (WC-023)  
  `/txt-records` and `/whois` now send `?domain=` and `/trace-route` sends
  `?urlString=` per the upstream OpenAPI spec. All three previously sent
  `?url=` which caused silent failures on those checks.
- **`--stdio` now speaks both NDJSON and Content-Length framing** (WC-010 / WC-010b)  
  Hosts built on the TypeScript SDK use LSP-style `Content-Length` headers;
  the old loop only understood newline-delimited JSON, so handshakes with TS
  hosts would silently stall. The new transport auto-detects framing per
  message and replies in kind.
- **`notifications/initialized` is now correctly silent** — no longer replies
  with a spurious response that confused some hosts.
- **`resources/list` and `prompts/list` return empty arrays** instead of
  `-32601 Method not found`, which several hosts treat as a fatal error on
  connect.
- **`initialize` echoes the client’s `protocolVersion`** instead of always
  advertising `2024-11-05`.

### Added
- **`src/stdio.py`** — standalone dual-mode MCP stdio transport with 18 unit
  tests (`TestStdioFraming`, `TestHandleRpc`, `TestStdioLoop`).
- **`scripts/live_smoke.py` + `.github/workflows/live-smoke.yml`** (WC-015)  
  Optional weekly / manual-dispatch workflow that probes each public base in
  isolation (`fallback=False`) and writes a Markdown table to the run summary.
  Non-blocking by default; `--strict` flag enables hard failure.
- **`docs/openapi-drift.md`** — full drift audit table against upstream spec,
  param mismatch explanations, re-audit trigger.
- **`list_checks()` now includes a `param` field** per entry (the query-param
  name that endpoint expects).

### Changed
- `WebCheckMCPServer` now accepts `opener` and `fallback` kwargs for
  test injection — no global mock needed.
- `call_tool()` returns `list[{type, text}]` as the MCP spec expects;
  `handle_tool_call()` kept as a backward-compatible string wrapper.
- `main()` now accepts `argv` so tests can drive the CLI without patching
  `sys.argv`.
- `/quality` summary clarified: the `apiKey` requirement is server-side
  (Google PageSpeed env var on the web-check backend), not a client param.

## [0.2.0] — 2026-07-25

### Added
- Multi-base failover: auto-retry `web-check.as93.net` (Netlify) when
  `web-check.xyz` (Vercel) returns 429/403 or a Vercel challenge page.
- Browser-like User-Agent to improve pass-through on Vercel.
- Resolved-base stickiness — first successful base is reused per client.
- `health()` and `run()` report `resolved_base_url` and `bases_used`.
- 5 new fallback tests (35 total).

## [0.1.0] — 2026-07-25

### Added
- Initial release: 31 OpenAPI checks, 8 MCP tools, parallel fan-out,
  payload truncation, STDIO JSON-RPC, CLI, zero pip deps.
