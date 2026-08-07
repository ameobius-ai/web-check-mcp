# Web Check MCP — Roadmap

> Project tracking for the MCP wrapper around Lissy93/web-check OSINT API.

## Status Legend

- ✅ Done
- 🔧 In Progress
- 📋 Planned
- 💡 Idea

---

## v0.3.0 (Current)

### Completed

- [x] **Core MCP Server** — 8 tools (run, ssl, dns, security, headers, whois, list_checks, health)
- [x] **31 OSINT checks** via upstream API
- [x] **6 presets** — quick, security, server, quality, heavy, all
- [x] **CLI interface** — manifest, list, health, run, check
- [x] **Zero pip dependencies** — stdlib only (Python 3.10+)
- [x] **Parallel fan-out** for multi-check runs
- [x] **Auto-failover** between public APIs
- [x] **Docker support** — slim Python 3.12 image (non-root user, healthcheck)
- [x] **Test suite** — 90+ tests, 90%+ coverage
- [x] **CI pipeline** — GitHub Actions with pytest, mypy, ruff, coverage
- [x] **Type safety** — Clean mypy
- [x] **Version sync** — pyproject.toml + server.json aligned at 0.3.0
- [x] **Dev extras** — pip install -e .[dev]
- [x] **CONTRIBUTING.md** — Developer guide
- [x] **Pre-commit hooks** — ruff + basic hooks
- [x] **SECURITY.md** — Vulnerability reporting policy
- [x] **Issue templates** — Bug report + feature request
- [x] **PR template** — With checklist
- [x] **.dockerignore** — Cleaner Docker builds
- [x] **Dockerfile security** — Non-root user, no editable install, healthcheck
- [x] **Enhanced CI** — Coverage, mypy, pip-audit, bandit, Docker build test
- [x] **Dependabot** — Automated dependency updates (pip, github-actions, docker)
- [x] **PyPI classifiers** — Better discoverability
- [x] **Project URLs** — Homepage, docs, issues, changelog
- [x] **mypy config** — Comprehensive type checking
- [x] **black config** — Code formatter
- [x] **Release workflow** — Automated PyPI publishing on tag
- [x] **GitHub Release** — Auto-create releases with changelog

### In Progress

- [ ] **Coverage tracking** — Codecov integration (waiting for first upload)

---

## v0.4.0 (Next Minor)

### Planned

- [ ] **Update CHANGELOG.md** with all v0.3.0 improvements
- [ ] **Add more badges** to README (coverage, downloads, security)
- [ ] **Enable GitHub Discussions** for community Q&A
- [ ] **Add CodeQL** for advanced security scanning
- [ ] **Stale issues bot** — Auto-close inactive issues
- [ ] **GitHub Pages** — Static documentation site
- [ ] **Performance benchmarks** — Track CI time and package size
- [ ] **Integration tests** — End-to-end MCP client testing

### Ideas

- [ ] **Streaming responses** for long-running checks
- [ ] **Cache layer** to avoid redundant API calls
- [ ] **Custom check groups** via config file
- [ ] **Webhook notifications** for security alerts
- [ ] **Multi-tenant support** for self-hosted instances
- [ ] **Batch processing** for multiple domains
- [ ] **Historical tracking** of check results
- [ ] **Plugin system** for custom check implementations

---

## Infrastructure

### Completed

- [x] GitHub Actions CI (multi-OS, multi-Python)
- [x] PyPI publishing (automated on tag)
- [x] Docker image (secure, non-root, healthcheck)
- [x] License (MIT)
- [x] Dependabot (pip, github-actions, docker)
- [x] Issue + PR templates
- [x] SECURITY.md
- [x] CONTRIBUTING.md
- [x] .pre-commit-config.yaml
- [x] .dockerignore

### Planned

- [ ] Codecov integration
- [ ] CodeQL security scanning
- [ ] Stale bot for inactive issues
- [ ] GitHub Pages documentation site
- [ ] GitHub Discussions

---

## Metrics

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Test Coverage | 90%+ | 95% | ✅ |
| Type Coverage | 100% | 100% | ✅ |
| Issues Closed | 15/15 | — | ✅ |
| CI Time | ~3min | <2min | 🔧 |
| Docker Image Size | ~150MB | <100MB | 📋 |
| PyPI Downloads | New | TBD | 💡 |
| GitHub Stars | New | TBD | 💡 |

---

## Recent Commits (Wave 2 — Infrastructure)

| Commit | Description | Issues |
|--------|-------------|--------|
| `71e1888` | Release workflow + pyproject improvements | #14, #15 |
| `95c0f33` | Enhanced CI + Dependabot | #12, #13 |
| `4a3d66d` | Docker improvements | #10, #11 |
| `e6f9b43` | SECURITY.md + GitHub templates | #7, #8, #9 |
| `9955bda` | Comprehensive coverage tests | #4 |
| `3ce97fc` | CONTRIBUTING.md + pre-commit | #5, #6 |
| `d83e339` | Fix mypy, sync versions, dev extras | #1, #2, #3 |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## Security

See [SECURITY.md](SECURITY.md) for vulnerability reporting.

## License

MIT — see [LICENSE](LICENSE) for details.

---

*Last updated: 2026-08-08*
*Total issues resolved: 15*
*Total commits in main: 15+*
