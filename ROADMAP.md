# Web Check MCP — Roadmap

> Project tracking for the MCP wrapper around Lissy93/web-check OSINT API.

## Status Legend

- 🟢 Done
- 🔧 In Progress  
- 📋 Planned
- 💡 Idea

---

## v0.3.0 (Current)

### ✅ Completed

- [x] **Core MCP Server** — 8 tools (`run`, `ssl`, `dns`, `security`, `headers`, `whois`, `list_checks`, `health`)
- [x] **31 OSINT checks** via upstream API
- [x] **6 presets** — `quick`, `security`, `server`, `quality`, `heavy`, `all`
- [x] **CLI interface** — manifest, list, health, run, check
- [x] **Zero pip dependencies** — stdlib only (Python 3.10+)
- [x] **Parallel fan-out** for multi-check runs
- [x] **Auto-failover** between public APIs (as93.net ↔ web-check.xyz)
- [x] **Docker support** — slim Python 3.12 image
- [x] **Test suite** — 52 tests passing
- [x] **CI pipeline** — GitHub Actions with pytest

### 🔧 In Progress

- [ ] **Fix mypy type error** in client.py:405 (#1)
- [ ] **Sync versions** between pyproject.toml and server.json (#2)
- [ ] **Add dev extras** to pyproject.toml (#3)

### 📋 Planned

- [ ] **Improve test coverage** from 81% to 90%+ (#4)
- [ ] **Comprehensive README** with usage examples (#5)
- [ ] **Pre-commit hooks** for code quality (#6)
- [ ] **Contributing guide** (CONTRIBUTING.md)
- [ ] **Release automation** — auto-publish to PyPI on tag

---

## v0.4.0 (Next Minor)

### 💡 Ideas

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

- [x] GitHub Actions CI
- [x] PyPI publishing
- [x] Docker image
- [x] License (MIT)

### Planned

- [ ] Codecov integration
- [ ] Dependabot for dependencies
- [ ] Security policy (SECURITY.md)
- [ ] Issue templates
- [ ] PR templates

---

## Metrics

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Test Coverage | 81% | 90%+ | 📋 |
| Type Coverage | 99% | 100% | 🔧 |
| Documentation | Minimal | Comprehensive | 📋 |
| CI Time | ~2min | <1min | ✅ |
| PyPI Downloads | New | TBD | 💡 |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## License

MIT — see [LICENSE](LICENSE) for details.

---

*Last updated: 2026-08-08*
