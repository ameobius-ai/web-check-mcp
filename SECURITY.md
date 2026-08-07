# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.3.x   | :white_check_mark: |
| < 0.3   | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. Please report them responsibly.

### How to Report

**Option 1: GitHub Security Advisories (Preferred)**

1. Go to https://github.com/ameobius-ai/web-check-mcp/security/advisories/new
2. Fill in description, steps to reproduce, impact, suggested fix
3. Submit the advisory

**Option 2: Email**

Send details to: security@ameobius.ai

### Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial Assessment**: Within 7 days
- **Status Updates**: Weekly until resolved
- **Resolution**: Critical issues within 30 days

### Responsible Disclosure

Please do not publicly disclose before we address it. Do not exploit beyond proof-of-concept.

We will acknowledge promptly, validate, fix, and credit you (if desired).

### Scope

**In scope**: web-check-mcp package, MCP server, CLI

**Out of scope**: Upstream Lissy93/web-check (report there), self-hosted custom configs, third-party deps

### Security Best Practices

1. Use self-hosted instances for production
2. Set appropriate timeouts via WEB_CHECK_TIMEOUT
3. Limit parallel workers via WEB_CHECK_MAX_WORKERS
4. Monitor API usage on public endpoints
5. Keep dependencies updated

### Security Features

- Zero third-party dependencies (reduced attack surface)
- Payload truncation (prevents agent context overflow)
- Multi-base failover (automatic fallback)
- SSL verification enabled by default
- Timeout enforcement on all requests

Thank you for helping keep web-check-mcp secure!
