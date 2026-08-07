"""Web Check HTTP client — OpenAPI surface for Lissy93/web-check.

Pure stdlib. Talks to a self-hosted (or demo) Web Check API base URL.
Public demo at https://web-check.xyz often returns 403 from datacenter IPs;
prefer local Docker: `docker run -p 3000:3000 lissy93/web-check`.
"""
from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps
from typing import Any

def _with_retry(max_retries=None):
    """Retry transient failures (5xx, connection errors) with exponential backoff."""
    if max_retries is None:
        max_retries = int(os.environ.get("WEB_CHECK_MAX_RETRIES", "3"))
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    status, data, err = func(*args, **kwargs)
                    # Retry on 5xx errors and connection errors (status 0)
                    if (status >= 500 or status == 0) and attempt < max_retries:
                        delay = 1.0 * (2 ** attempt)  # 1s, 2s, 4s

                        time.sleep(delay)
                        continue
                    return status, data, err
                except Exception as e:
                    last_error = e
                    if attempt < max_retries:
                        delay = 1.0 * (2 ** attempt)
                        time.sleep(delay)
                        continue
                    raise
            return 0, {"error": str(last_error)}, str(last_error)
        return wrapper
    return decorator


# Full OpenAPI path set from lissy93/web-check public/resources/openapi-spec.yml
# 'param' overrides the default query-param name ('url') when the upstream spec
# uses a different name.  Without 'param', the client sends ?url=<target>.
CHECKS: dict[str, dict[str, str]] = {
    "archives":     {"path": "/archives",     "group": "quality",   "summary": "Wayback archive first/last scan"},
    "block-lists":  {"path": "/block-lists",  "group": "security",  "summary": "Blocklist membership"},
    "carbon":       {"path": "/carbon",       "group": "quality",   "summary": "Carbon footprint estimate"},
    "cookies":      {"path": "/cookies",      "group": "server",    "summary": "HTTP cookies"},
    "dns":          {"path": "/dns",          "group": "server",    "summary": "DNS records"},
    "dns-server":   {"path": "/dns-server",   "group": "server",    "summary": "Authoritative DNS server info"},
    "dnssec":       {"path": "/dnssec",       "group": "security",  "summary": "DNSSEC status"},
    "firewall":     {"path": "/firewall",     "group": "security",  "summary": "WAF / firewall detection"},
    "get-ip":       {"path": "/get-ip",       "group": "server",    "summary": "Resolved IP address info"},
    "headers":      {"path": "/headers",      "group": "server",    "summary": "HTTP response headers"},
    "hsts":         {"path": "/hsts",         "group": "security",  "summary": "HSTS policy"},
    "http-security":{"path": "/http-security","group": "security",  "summary": "Security headers score"},
    "linked-pages": {"path": "/linked-pages", "group": "quality",   "summary": "Outbound / internal links"},
    "mail-config":  {"path": "/mail-config",  "group": "server",    "summary": "SPF/DKIM/DMARC/BIMI"},
    "ports":        {"path": "/ports",        "group": "server",    "summary": "Common open ports (slow)"},
    # /quality also requires ?apiKey= (Google PageSpeed); without it the server
    # returns 204 Skipped.  The apiKey must be set via the web-check backend env.
    "quality": {"path": "/quality", "group": "quality", "summary": "Page quality metrics (needs apiKey on server)"},
    "rank":         {"path": "/rank",         "group": "quality",   "summary": "Tranco / popularity rank"},
    "redirects":    {"path": "/redirects",    "group": "server",    "summary": "Redirect chain"},
    "robots-txt":   {"path": "/robots-txt",   "group": "quality",   "summary": "robots.txt parse"},
    "screenshot":   {"path": "/screenshot",   "group": "quality",   "summary": "Page screenshot (heavy)"},
    "security-txt": {"path": "/security-txt", "group": "security",  "summary": "security.txt"},
    "sitemap":      {"path": "/sitemap",      "group": "quality",   "summary": "sitemap.xml"},
    "social-tags":  {"path": "/social-tags",  "group": "quality",   "summary": "Open Graph / Twitter cards"},
    "ssl":          {"path": "/ssl",          "group": "security",  "summary": "SSL certificate chain"},
    "status":       {"path": "/status",       "group": "server",    "summary": "HTTP status / reachability"},
    "tech-stack":   {"path": "/tech-stack",   "group": "quality",   "summary": "Detected technologies"},
    "threats":      {"path": "/threats",      "group": "security",  "summary": "Threat / malware signals"},
    "tls":          {"path": "/tls",          "group": "security",  "summary": "TLS config / ciphers"},
    # /trace-route uses ?urlString= per upstream OpenAPI spec
    "trace-route": {"path": "/trace-route", "group": "server", "summary": "Traceroute (slow)", "param": "urlString"},
    # /txt-records and /whois use ?domain= per upstream OpenAPI spec
    "txt-records": {"path": "/txt-records", "group": "server", "summary": "DNS TXT records", "param": "domain"},
    "whois": {"path": "/whois", "group": "server", "summary": "WHOIS / RDAP domain info", "param": "domain"},
}

CHECK_GROUPS: dict[str, list[str]] = {
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

DEFAULT_BASE_URL = os.environ.get("WEB_CHECK_BASE_URL", "https://web-check.as93.net/api")
DEFAULT_TIMEOUT = int(os.environ.get("WEB_CHECK_TIMEOUT", "25"))
DEFAULT_MAX_WORKERS = int(os.environ.get("WEB_CHECK_MAX_WORKERS", "6"))
DEFAULT_MAX_CHARS = int(os.environ.get("WEB_CHECK_MAX_CHARS", "12000"))
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Ordered list of bases tried on health/run if primary fails.
# Vercel often challenges datacenter IPs with 429; Netlify mirror is more open.
PUBLIC_BASE_URLS = [
    "https://web-check.as93.net/api",  # Netlify — Cloudflare front, more permissive
    "https://web-check.xyz/api",       # Vercel primary (UI works from browser, API may 429)
]


def _normalize_base(base_url: str) -> str:
    base = (base_url or DEFAULT_BASE_URL).rstrip("/")
    # Accept host-only forms: http://localhost:3000 -> .../api
    if not base.endswith("/api") and (base.endswith(":3000") or base.rstrip("/").endswith("web-check")):
        base = base + "/api"
    return base


def _normalize_target(url: str) -> str:
    target = (url or "").strip()
    if not target:
        raise ValueError("url is required")
    if "://" not in target:
        target = "https://" + target
    return target


def _query_param_name(check_name: str) -> str:
    """Return the query-param name the upstream API expects for this check.

    Most endpoints use ``?url=<target>``, but a few differ per the OpenAPI spec:
    - /txt-records  -> ``?domain=``
    - /whois        -> ``?domain=``
    - /trace-route  -> ``?urlString=``
    """
    return CHECKS.get(check_name, {}).get("param", "url")


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
        out: dict[str, Any] = {}
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
        kept: list[Any] = []
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



import hashlib
from typing import Optional


class CircuitBreaker:
    """Circuit breaker pattern for failing APIs.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Circuit tripped, fail fast without making requests
    - HALF_OPEN: Testing if service recovered, allow one probe request
    
    Transitions:
    - CLOSED -> OPEN: After failure_threshold consecutive failures
    - OPEN -> HALF_OPEN: After recovery_timeout seconds
    - HALF_OPEN -> CLOSED: On successful request
    - HALF_OPEN -> OPEN: On failed request
    """
    
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0
        self._last_success_time = 0
    
    @property
    def state(self) -> str:
        """Current circuit state, auto-transitions OPEN -> HALF_OPEN on timeout."""
        if self._state == self.OPEN and time.time() - self._last_failure_time >= self.recovery_timeout:
            self._state = self.HALF_OPEN
        return self._state
        return self._state
    
    def can_execute(self) -> bool:
        """Check if request should be allowed."""
        state = self.state
        return state in (self.CLOSED, self.HALF_OPEN)




            return False
    
    def record_success(self):
        """Record successful request."""
        self._failure_count = 0
        self._state = self.CLOSED
        self._last_success_time = time.time()
    
    def record_failure(self):
        """Record failed request."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        
        if self._failure_count >= self.failure_threshold:
            self._state = self.OPEN
    
    def reset(self):
        """Manually reset circuit breaker."""
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0




class RateLimiter:
    """Token bucket rate limiter.
    
    Allows burst up to bucket_size, then limits to tokens_per_second.
    """
    
    def __init__(self, tokens_per_second: float = 1.0, bucket_size: int = 10):
        self.tokens_per_second = tokens_per_second
        self.bucket_size = bucket_size
        self.tokens = bucket_size
        self.last_update = time.time()
        self.total_wait_time = 0.0
        self.total_waits = 0
    
    def _refill(self):
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_update
        self.tokens = min(self.bucket_size, self.tokens + elapsed * self.tokens_per_second)
        self.last_update = now
    
    def acquire(self, timeout: float = 30.0) -> bool:
        """Acquire a token, waiting if necessary. Returns False on timeout."""
        start_time = time.time()
        
        while True:
            self._refill()
            
            if self.tokens >= 1:
                self.tokens -= 1
                if self.total_waits > 0:
                    self.total_wait_time += time.time() - start_time
                return True
            
            # Not enough tokens, wait
            if timeout > 0 and (time.time() - start_time) >= timeout:
                return False
            
            # Wait for next token
            wait_time = (1 - self.tokens) / self.tokens_per_second
            time.sleep(min(wait_time, 0.1))  # Sleep in small increments
            self.total_waits += 1
    
    def stats(self) -> dict:
        """Return rate limiter statistics."""
        return {
            "tokens_per_second": self.tokens_per_second,
            "bucket_size": self.bucket_size,
            "current_tokens": round(self.tokens, 2),
            "total_waits": self.total_waits,
            "avg_wait_time": round(self.total_wait_time / self.total_waits, 3) if self.total_waits > 0 else 0
        }


class ResultCache:
    """Simple TTL-based in-memory cache for check results."""
    
    def __init__(self, ttl_seconds: int = 300):
        self.ttl = ttl_seconds
        self._cache: dict[str, tuple[float, any]] = {}
        self.hits = 0
        self.misses = 0
    
    def _make_key(self, url: str, check: str) -> str:
        """Create cache key from URL and check name."""
        return hashlib.sha256(f"{url}:{check}".encode()).hexdigest()
    
    def get(self, url: str, check: str) -> any | None:
        """Get cached result if valid, else None."""
        if self.ttl <= 0:
            return None
        
        key = self._make_key(url, check)
        if key in self._cache:
            timestamp, data = self._cache[key]
            if time.time() - timestamp < self.ttl:
                self.hits += 1
                return data
            else:
                # Expired
                del self._cache[key]
        
        self.misses += 1
        return None
    
    def set(self, url: str, check: str, data: any):
        """Cache result with current timestamp."""
        if self.ttl <= 0:
            return
        
        key = self._make_key(url, check)
        self._cache[key] = (time.time(), data)
    
    def stats(self) -> dict:
        """Return cache statistics."""
        total = self.hits + self.misses
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total * 100, 1) if total > 0 else 0,
            "size": len(self._cache),
            "ttl_seconds": self.ttl
        }
    
    def clear(self):
        """Clear all cached entries."""
        self._cache.clear()
        self.hits = 0
        self.misses = 0


class WebCheckClient:
    """Thin client over Web Check REST endpoints.

    Multi-base failover: when ``fallback=True`` (default for public bases),
    failed probes are retried against PUBLIC_BASE_URLS. The first base that
    returns a 2xx/4xx JSON body wins; 429/403 from Vercel triggers fallback.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        max_workers: int = DEFAULT_MAX_WORKERS,
        max_chars: int = DEFAULT_MAX_CHARS,
        verify_ssl: bool = True,
        opener: Callable[..., Any] | None = None,
        fallback: bool | None = None,
    ):
        self.base_url = _normalize_base(base_url)
        self.timeout = timeout
        self.max_workers = max(1, max_workers)
        self.max_chars = max_chars
        self.verify_ssl = verify_ssl
        self._opener = opener  # injectable for tests
        # Enable fallback automatically when using a public base or the
        # default local base that the user did not explicitly set.
        self.fallback = bool(fallback) if fallback is not None else (
            self.base_url.startswith("https://web-check.")
        )
        self._resolved_base: str | None = None

    def list_checks(self, group: str | None = None) -> list[dict[str, str]]:
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
                "param": _query_param_name(k),
            }
            for k in keys
            if k in CHECKS
        ]

    def resolve_checks(
        self,
        checks: Sequence[str] | None = None,
        group: str | None = None,
    ) -> list[str]:
        if checks:
            out: list[str] = []
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

    def _ssl_context(self) -> ssl.SSLContext | None:
        if self.verify_ssl:
            return None  # default verification
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    @_with_retry()
    def _http_get(self, url: str) -> tuple[int, Any, str | None]:
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
        except Exception as e:
            return 0, {"error": str(e)}, str(e)

    def _candidate_bases(self) -> list[str]:
        """Bases to try, primary first. De-duplicates normalized forms."""
        seen: set = set()
        out: list[str] = []
        primary = _normalize_base(self.base_url)
        for b in [primary] + (list(PUBLIC_BASE_URLS) if self.fallback else []):
            nb = _normalize_base(b)
            if nb and nb not in seen:
                seen.add(nb)
                out.append(nb)
        return out

    def _is_blocking_status(self, status: int, data: Any) -> bool:
        """429/403 or non-JSON challenge body signals a base is unusable."""
        if status in (403, 429, 503):
            return True
        if status == 200 and isinstance(data, dict):
            raw = data.get("raw", "")
            # Vercel challenge returns HTML with these markers
            if "x-vercel" in raw or "challenge" in raw[:500].lower():
                return True
        return False

    def check_one(self, check: str, url: str) -> dict[str, Any]:
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
        # Check cache first
        cached = self._cache.get(target, name)
        if cached is not None:
            cached["cached"] = True
            return cached

        path = CHECKS[name]["path"]
        # Use the param name the upstream API expects (most use 'url',
        # but /txt-records and /whois use 'domain', /trace-route uses 'urlString').
        param = _query_param_name(name)
        qs = urllib.parse.urlencode({param: target})

        bases = self._candidate_bases()
        # Filter bases by circuit breaker state
        filtered_bases = []
        for base in bases:
            if base not in self._circuit_breakers:
                self._circuit_breakers[base] = CircuitBreaker()
            cb = self._circuit_breakers[base]
            if cb.can_execute():
                filtered_bases.append(base)
        
        if not filtered_bases:
            # All circuits open, return error
            return {
                "check": name,
                "ok": False,
                "status": 0,
                "error": "All API endpoints are unavailable (circuit breakers open)",
                "data": None
            }
        bases = filtered_bases

        # If we previously resolved a working base, try it first and alone.
        if self._resolved_base and self._resolved_base in bases:
            bases = [self._resolved_base] + [b for b in bases if b != self._resolved_base]

        last: dict[str, Any] = {}
        used_base: str | None = None
        for base in bases:
            endpoint = f"{base}{path}?{qs}"
            status, data, err = self._http_get(endpoint)
            blocking = self._is_blocking_status(status, data)
            ok = 200 <= status < 300 and err is None and not blocking
            if isinstance(data, dict) and (data.get("error") or data.get("skipped")):
                ok = False if data.get("error") else ok
            last = {
                "check": name,
                "group": CHECKS[name]["group"],
                "ok": ok,
                "status": status,
                "endpoint": endpoint,
                "base_url": base,
                "error": err or (data.get("error") if isinstance(data, dict) else None),
                "data": truncate_payload(data, self.max_chars) if data is not None else None,
            }
            used_base = base
            if ok or not (blocking or status == 0):
                # Record circuit breaker state
                cb = self._circuit_breakers[base]
                if ok:
                    cb.record_success()
                elif status >= 500 or status == 0:
                    cb.record_failure()
                # Either succeeded or got a definitive non-blocking answer.
                if ok:
                    self._resolved_base = base
                break
        if used_base and last.get("ok"):
            self._resolved_base = used_base
        # Cache successful results
        if last.get("ok"):
            self._cache.set(target, name, last)
        return last

    def run(
        self,
        url: str,
        checks: Sequence[str] | None = None,
        group: str | None = None,
        max_workers: int | None = None,
    ) -> dict[str, Any]:
        target = _normalize_target(url)
        names = self.resolve_checks(checks=checks, group=group)
        workers = max(1, max_workers or self.max_workers)
        results: dict[str, dict[str, Any]] = {}

        if len(names) == 1:
            results[names[0]] = self.check_one(names[0], target)
        else:
            with ThreadPoolExecutor(max_workers=min(workers, len(names))) as pool:
                futs = {pool.submit(self.check_one, n, target): n for n in names}
                for fut in as_completed(futs):
                    name = futs[fut]
                    try:
                        results[name] = fut.result()
                    except Exception as e:
                        results[name] = {
                            "check": name,
                            "ok": False,
                            "status": 0,
                            "error": str(e),
                            "data": None,
                        }

        ordered = [results[n] for n in names if n in results]
        ok_count = sum(1 for r in ordered if r.get("ok"))
        bases_used: list[str] = sorted([str(r.get("base_url")) for r in ordered if r.get("base_url")])
        return {
            "url": target,
            "base_url": self.base_url,
            "resolved_base_url": self._resolved_base or bases_used[0] if bases_used else None,
            "bases_used": bases_used,
            "checks_requested": names,
            "ok_count": ok_count,
            "fail_count": len(ordered) - ok_count,
            "results": ordered,
        }

    def health(self) -> dict[str, Any]:
        """Probe base URL reachability via get-ip on example.com.

        With fallback enabled, tries PUBLIC_BASE_URLS in order and reports
        which base actually answered.
        """
        probe = self.check_one("get-ip", "https://example.com")
        return {
            "base_url": self.base_url,
            "resolved_base_url": probe.get("base_url") or self._resolved_base,
            "reachable": bool(probe.get("ok")),
            "status": probe.get("status"),
            "error": probe.get("error"),
            "fallback_enabled": self.fallback,
            "public_bases": PUBLIC_BASE_URLS,
            "cache_stats": self._cache.stats(),
            "hint": (
                "Public web-check.xyz (Vercel) may 429 datacenter IPs; "
                "Netlify mirror web-check.as93.net is more open. "
                "For production: self-host `docker run -p 3000:3000 lissy93/web-check` "
                "and set WEB_CHECK_BASE_URL=http://127.0.0.1:3000/api"
            ),
        }
