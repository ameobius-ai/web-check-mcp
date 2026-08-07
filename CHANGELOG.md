# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-08-07

### Added

#### Core Features
- **MCP Server** with 8 tools: `webcheck_run`, `webcheck_ssl`, `webcheck_dns`, `webcheck_security`, `webcheck_headers`, `webcheck_whois`, `webcheck_list_checks`, `webcheck_health`
- **31 OSINT checks** wrapped from Lissy93/web-check API
- **6 check presets**: `quick`, `security`, `server`, `quality`, `heavy`, `all`
- **CLI interface** with subcommands: `list`, `health`, `run`, `check`, `--manifest`, `--stdio`
- **Parallel fan-out** for multi-check runs via ThreadPoolExecutor
- **Payload truncation** to prevent agent context overflow (default 12000 chars)
- **Dual-mode STDIO framing** (NDJSON + Content-Length auto-detection)
- **Tool annotations** (`readOnlyHint`, `openWorldHint`) for MCP clients

#### Infrastructure
- **GitHub Actions CI** — multi-OS (Ubuntu, macOS), multi-Python (3.10, 3.11, 3.12)
- **Docker image** — python:3.12-slim based, non-root user, healthcheck
- **docker-compose.yml** — self-host option with upstream web-check
- **Automated PyPI publishing** via release workflow on tag push
- **GitHub Releases** with auto-generated changelog
- **Dependabot** for pip, github-actions, docker ecosystems
- **Codecov integration** for coverage tracking
- **Security scanning** via pip-audit and bandit
- **Pre-commit hooks** with ruff

#### Documentation
- **SECURITY.md** — vulnerability reporting policy
- **CONTRIBUTING.md** — developer guide with setup instructions
- **ROADMAP.md** — project tracking and status
- **Issue templates** — bug report and feature request
- **PR template** — with review checklist
- **README.md** — comprehensive usage guide with examples

#### Testing
- **52+ unit tests** covering client, server, and STDIO modules
- **90%+ code coverage** (pytest-cov)
- **Mocked network** tests via FakeOpener fixture
- **Integration tests** for MCP STDIO handshake

### Changed

- **Zero third-party dependencies** — Python 3.10+ stdlib only
- **Multi-base failover** — automatic fallback between web-check.xyz and web-check.as93.net
- **Smart URL normalization** — adds `https://` and `/api` suffix automatically
- **Type hints** throughout codebase for better IDE support

### Fixed

- **mypy type error** in `client.py:405` — sorted() with None values
- **Version sync** between pyproject.toml and server.json
- **Dockerfile security** — removed editable install, added non-root user

### Security

- Non-root Docker user
- SSL verification enabled by default
- Timeout enforcement on all requests (default 25s)
- No secrets in codebase (all via environment variables)
- Dependabot for automated vulnerability updates

## [0.2.0] - 2026-07-25

### Added
- Initial release
- Basic MCP server implementation
- Core OSINT checks wrapper
- CLI interface
- Docker support

## [0.1.0] - 2026-07-25

### Added
- Project scaffolding
- Initial client implementation

[0.3.0]: https://github.com/ameobius-ai/web-check-mcp/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ameobius-ai/web-check-mcp/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ameobius-ai/web-check-mcp/releases/tag/v0.1.0
