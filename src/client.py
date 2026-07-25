"""Web Check HTTP client — OpenAPI surface for Lissy93/web-check.

Pure stdlib. Talks to a self-hosted (or demo) Web Check API base URL.
Public demo at https://web-check.xyz often returns 403 from datacenter IPs;
prefer local Docker: `docker run -p 3000:3000 lissy93/web-check`.
"""
from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple


# Full OpenAPI path set from lissy93/web-check public/resources/openapi-spec.yml
CHECKS: Dict[str, Dict[str, str]] = {
    "archives": {"path": "/archives", "group": "quality", "summary": "Wayback archive first/last scan"},
    "block-lists": {"path": "/block-lists", "group": "security", "summary": "Blocklist membership"},
    "carbon": {"path": "/carbon", "group": "quality", "summary": "Carbon footprint estimate"},
    "cookies": {"path": "/cookies", "group": "server", "summary": "HTTP cookies"},
    "dns": {"path": "/dns", "group": "server", "summary": "DNS records"},
    "dns-server": {"path": "/dns-server", "group": "server", "summary": "Authoritative DNS server info"},
    "dnssec": {"path": "/dnssec", "group": "security", "summary": "DNSSEC status"},
    "firewall": {"path": "/firewall", "group": "security", "summary": "WAF / firewall detection"},
    "get-ip": {"path": "/get-ip", "group": "server", "summary": "Resolved IP address info"},
    "headers": {"path": "/headers", "group": "server", "summary": "HTTP response headers"},
    "hsts": {"path": "/hsts", "group": "security", "summary": "HSTS policy"},
    "http-security": {"path": "/http-security", "group": "security", "summary": "Security headers score"},
    "linked-pages": {"path": "/linked-pages", "group": "quality", "summary": "Outbound / internal links"},
    "mail-config": {"path": "/mail-config", "group": "server", "summary": "SPF/DKIM/DMARC/BIMI"},
    "ports": {"path": "/ports", "group": "server", "summary": "Common open ports (slow)"},
    "quality": {"path": "/quality", "group": "quality", "summary": "Page quality metrics"},
    "rank": {"path": "/rank", "group": "quality", "summary": "Tranco / popularity rank"},
    "redirects": {"path": "/redirects", "group": "server", "summary": "Redirect chain"},
    "robots-txt": {"path": "/robots-txt", "group": "quality", "summary": "robots.txt parse"},
    "screenshot": {"path": "/screenshot", "group": "quality", "summary": "Page screenshot (heavy)"},
    "security-txt": {"path": "/security-txt", "group": "security", "summary": "security.txt"},
    "sitemap": {"path": "/sitemap", "group": "quality", "summary": "sitemap.xml"},
    "social-tags": {"path": "/social-tags", "group": "quality", "summary": "Open Graph / Twitter cards"},
    "ssl": {"path": "/ssl", "group": "security", "summary": "SSL certificate chain"},
    "status": {"path": "/status", "group": "server", "summary": "HTTP status / reachability"},
    "tech-stack": {"path": "/tech-stack", "group": "quality", "summary": "Detected technologies"},
    "threats": {"path": "/threats", "group": "security", "summary": "Threat / malware signals"},
    "tls": {"path": "/tls", "group": "security", "summary": "TLS config / ciphers"},
    "trace-route": {"path": "/trace-route", "group": "server", "summary": "Traceroute (slow)"},
    "txt-records": {"path": "/txt-records", "group": "server", "summary": "DNS TXT records"},
    "whois": {"path": "/whois", "group": "server", "summary": "WHOIS / RDAP domain info"},
}

CHECK_GROUPS: Dict[str, List[str]] = {
    "quick": ["get-ip", "status", "headers", "dns", "ssl", "redirects"],
    "security": [
        "ssl", "tls", "hsts", "http-security", "firewall", "dnssec",
        "security-txt", "threats", "block-lists",
    ],
    "server": [
        "get-ip", "dns", "dns-server", "ports", "cookies", "headers",
        "whois", "mail-config", "txt-records", "redirects", "status",
    ],
    "quality": [
        "quality", "rank", "carbon", "tech-stack", "social-tags",
        "archives", "robots-txt", "sitemap", "linked-pages",
    ],
    "heavy": ["screenshot", "ports", "trace-route", "quality"],
    "all": sorted(CHECKS.keys()),
}

DEFAULT_BASE_URL = os.environ.get("WEB_CHECK_BASE_URL", "http://127.0.0.1:3000/api")
DEFAULT_TIMEOUT = int(os.environ.get("WEB_CHECK_TIMEOUT", "25"))
DEFAULT_MAX_WORKERS = int(os.environ.get("WEB_CHECK_MAX_WORKERS", "6"))
DEFAULT_MAX_CHARS = int(os.environ.get("WEB_CHECK_MAX_CHARS", "12000"))
USER_AGENT = "web-check-mcp/0.1.0 (+https://github.com/Lissy93/web-check)"


def _normalize_base(base_url: str) -> str:
    base = (base_url or DEFAULT_BASE_URL).rstrip("/")
    # Accept host-only forms: http://localhost:3000 -> .../api
    if not base.endswith("/api"):
        if base.endswith(":3000") or base.rstrip("/").endswith("web-check"):
            base = base + "/api"
    return base


def _normalize_target(url: str) -> str:
    target = (url or "").strip()
    if not target:
        raise ValueError("url is required")
    if "://" not in target:
        target = "https://" + target
    return target


def truncate_payload(data: Any, max_chars: int = DEFAULT_MAX_CHARS) -> Any:
    """Cap JSON-ish payloads so agent contexts don't explode."""
    if max_chars <= 0:
        return data
    try:
        raw = json.dumps(data, ensure_ascii=False, default=str)
    except TypeError:
        raw = str(data)
    if len(raw) <= max_chars:
        return data
    # Prefer shrinking large strings / lists
    if isinstance(data, dict):
        out: Dict[str, Any] = {}
        budget = max_chars
        for k, v in data.items():
            piece = truncate_payload(v, max(500, budget // max(1, len(data))))
            out[k] = piece
        encoded = json.dumps(out, ensure_ascii=False, default=str)
        if len(encoded) > max_chars:
            return {
                "_truncated": True,
                "_original_chars": len(raw),
                "_max_chars": max_chars,
                "preview": raw[: max_chars - 120] + "…",
            }
        out["_truncated"] = True
        out["_original_chars"] = len(raw)
        return out
    if isinstance(data, list):
        kept: List[Any] = []
        size = 2
        for item in data:
            enc = json.dumps(item, ensure_ascii=False, default=str)
            if size + len(enc) > max_chars and kept:
                break
            kept.append(truncate_payload(item, max_chars // 4))
            size += len(enc) + 1
        return {
            "_truncated": True,
            "_items_kept": len(kept),
            "_items_total": len(data),
            "items": kept,
        }
    if isinstance(data, str):
        if len(data) <= max_chars:
            return data
        return data[: max_chars - 20] + "…[truncated]"
    return {"_truncated": True, "preview": raw[: max_chars - 40] + "…"}


class WebCheckClient:
    """Thin client over Web Check REST endpoints."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        max_workers: int = DEFAULT_MAX_WORKERS,
        max_chars: int = DEFAULT_MAX_CHARS,
        verify_ssl: bool = True,
        opener: Optional[Callable[..., Any]] = None,
    ):
        self.base_url = _normalize_base(base_url)
        self.timeout = timeout
        self.max_workers = max(1, max_workers)
        self.max_chars = max_chars
        self.verify_ssl = verify_ssl
        self._opener = opener  # injectable for tests

    def list_checks(self, group: Optional[str] = None) -> List[Dict[str, str]]:
        if group:
            keys = CHECK_GROUPS.get(group)
            if keys is None:
                raise ValueError(
                    f"Unknown group '{group}'. Known: {', '.join(sorted(CHECK_GROUPS))}"
                )
        else:
            keys = sorted(CHECKS.keys())
        return [
            {
                "name": k,
                "path": CHECKS[k]["path"],
                "group": CHECKS[k]["group"],
                "summary": CHECKS[k]["summary"],
            }
            for k in keys
            if k in CHECKS
        ]

    def resolve_checks(
        self,
        checks: Optional[Sequence[str]] = None,
        group: Optional[str] = None,
    ) -> List[str]:
        if checks:
            out: List[str] = []
            for c in checks:
                name = c.strip().lstrip("/")
                if name not in CHECKS:
                    raise ValueError(f"Unknown check '{name}'. Use list_checks.")
                if name not in out:
                    out.append(name)
            return out
        if group:
            keys = CHECK_GROUPS.get(group)
            if keys is None:
                raise ValueError(f"Unknown group '{group}'")
            return list(keys)
        return list(CHECK_GROUPS["quick"])

    def _ssl_context(self) -> Optional[ssl.SSLContext]:
        if self.verify_ssl:
            return None  # default verification
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _http_get(self, url: str) -> Tuple[int, Any, Optional[str]]:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/plain, */*",
            },
            method="GET",
        )
        try:
            if self._opener is not None:
                raw = self._opener(url, timeout=self.timeout)
                if isinstance(raw, tuple):
                    status, body = raw[0], raw[1]
                else:
                    status, body = 200, raw
                if isinstance(body, (bytes, bytearray)):
                    text = body.decode("utf-8", errors="replace")
                else:
                    text = body if isinstance(body, str) else json.dumps(body)
                try:
                    return status, json.loads(text), None
                except json.JSONDecodeError:
                    return status, {"raw": text[: self.max_chars]}, None

            ctx = self._ssl_context()
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                status = getattr(resp, "status", 200) or 200
                text = resp.read().decode("utf-8", errors="replace")
                try:
                    return int(status), json.loads(text), None
                except json.JSONDecodeError:
                    return int(status), {"raw": text[: self.max_chars]}, None
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace") if e.fp else ""
            payload: Any
            try:
                payload = json.loads(body) if body else {"error": e.reason}
            except json.JSONDecodeError:
                payload = {"error": body or str(e.reason)}
            return int(e.code), payload, f"HTTP {e.code}"
        except Exception as e:  # noqa: BLE001 — surface to agent as structured error
            return 0, {"error": str(e)}, str(e)

    def check_one(self, check: str, url: str) -> Dict[str, Any]:
        name = check.strip().lstrip("/")
        if name not in CHECKS:
            return {
                "check": name,
                "ok": False,
                "status": 0,
                "error": f"Unknown check '{name}'",
                "data": None,
            }
        target = _normalize_target(url)
        path = CHECKS[name]["path"]
        qs = urllib.parse.urlencode({"url": target})
        endpoint = f"{self.base_url}{path}?{qs}"
        status, data, err = self._http_get(endpoint)
        ok = 200 <= status < 300 and err is None
        # Web-check sometimes returns 200 with {skipped|error}
        if isinstance(data, dict) and (data.get("error") or data.get("skipped")):
            ok = False if data.get("error") else ok
        return {
            "check": name,
            "group": CHECKS[name]["group"],
            "ok": ok,
            "status": status,
            "endpoint": endpoint,
            "error": err or (data.get("error") if isinstance(data, dict) else None),
            "data": truncate_payload(data, self.max_chars) if data is not None else None,
        }

    def run(
        self,
        url: str,
        checks: Optional[Sequence[str]] = None,
        group: Optional[str] = None,
        max_workers: Optional[int] = None,
    ) -> Dict[str, Any]:
        target = _normalize_target(url)
        names = self.resolve_checks(checks=checks, group=group)
        workers = max(1, max_workers or self.max_workers)
        results: Dict[str, Dict[str, Any]] = {}

        if len(names) == 1:
            results[names[0]] = self.check_one(names[0], target)
        else:
            with ThreadPoolExecutor(max_workers=min(workers, len(names))) as pool:
                futs = {pool.submit(self.check_one, n, target): n for n in names}
                for fut in as_completed(futs):
                    name = futs[fut]
                    try:
                        results[name] = fut.result()
                    except Exception as e:  # noqa: BLE001
                        results[name] = {
                            "check": name,
                            "ok": False,
                            "status": 0,
                            "error": str(e),
                            "data": None,
                        }

        ordered = [results[n] for n in names if n in results]
        ok_count = sum(1 for r in ordered if r.get("ok"))
        return {
            "url": target,
            "base_url": self.base_url,
            "checks_requested": names,
            "ok_count": ok_count,
            "fail_count": len(ordered) - ok_count,
            "results": ordered,
        }

    def health(self) -> Dict[str, Any]:
        """Probe base URL reachability via get-ip on example.com."""
        probe = self.check_one("get-ip", "https://example.com")
        return {
            "base_url": self.base_url,
            "reachable": bool(probe.get("ok") or probe.get("status") not in (0, None)),
            "status": probe.get("status"),
            "error": probe.get("error"),
            "hint": (
                "If unreachable/403: self-host with "
                "`docker run -p 3000:3000 lissy93/web-check` "
                "and set WEB_CHECK_BASE_URL=http://127.0.0.1:3000/api"
            ),
        }
