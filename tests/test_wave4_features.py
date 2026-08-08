"""Tests for Wave 4 production readiness features."""

from __future__ import annotations

import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.client import (
    CircuitBreaker,
    RateLimiter,
    ResultCache,
    WebCheckClient,
)


class FakeOpener:
    """Mock HTTP opener for testing."""

    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0
        self.calls = []

    def __call__(self, url, timeout=25):
        self.calls.append(url)
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response
        return 200, {"ok": True}


class FakeClock:
    """Deterministic monotonic clock for rate-limit tests."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        assert seconds >= 0
        self.sleeps.append(seconds)
        self.now += seconds

    def advance(self, seconds):
        self.now += seconds


class TestRetryLogic:
    """Test retry logic with exponential backoff."""

    def test_no_retry_on_success(self):
        """Successful request should not retry."""
        opener = FakeOpener([(200, {"data": "success"})])
        client = WebCheckClient(opener=opener)
        result = client.check_one("ssl", "example.com")

        assert result["ok"] is True
        assert opener.call_count == 1  # Only one call, no retries

    def test_retry_on_500_error(self):
        """Should retry on 5xx errors."""
        opener = FakeOpener([(500, {"error": "Internal Server Error"}), (200, {"data": "success"})])
        client = WebCheckClient(opener=opener)

        with patch.object(time, "sleep"):  # Speed up test
            result = client.check_one("ssl", "example.com")

        assert result["ok"] is True
        assert opener.call_count == 2  # First attempt failed, second succeeded

    def test_retry_on_connection_error(self):
        """Should retry on connection errors (status 0)."""
        opener = FakeOpener([(0, {"error": "Connection refused"}), (200, {"data": "success"})])
        client = WebCheckClient(opener=opener)

        with patch.object(time, "sleep"):
            result = client.check_one("ssl", "example.com")

        assert result["ok"] is True
        assert opener.call_count == 2

    def test_max_retries_exceeded(self):
        """Should fail after max retries exceeded."""
        opener = FakeOpener(
            [
                (500, {"error": "error1"}),
                (500, {"error": "error2"}),
                (500, {"error": "error3"}),
                (500, {"error": "error4"}),
            ]
        )
        client = WebCheckClient(opener=opener)

        with patch.object(time, "sleep"):
            result = client.check_one("ssl", "example.com")

        assert result["ok"] is False
        assert opener.call_count == 4  # 1 initial + 3 retries (default)

    def test_no_retry_on_4xx_errors(self):
        """Should not retry on 4xx client errors."""
        opener = FakeOpener([(404, {"error": "Not Found"})])
        client = WebCheckClient(opener=opener)
        result = client.check_one("ssl", "example.com")

        assert result["ok"] is False
        assert opener.call_count == 1  # No retry on 404

    def test_retry_with_env_var(self):
        """Should respect WEB_CHECK_MAX_RETRIES env var."""
        opener = FakeOpener([(500, {"error": "error1"}), (500, {"error": "error2"})])

        with patch.dict(os.environ, {"WEB_CHECK_MAX_RETRIES": "1"}):
            client = WebCheckClient(opener=opener)
            with patch.object(time, "sleep"):
                client.check_one("ssl", "example.com")

        assert opener.call_count == 2  # 1 initial + 1 retry

    def test_retry_disabled(self):
        """Should not retry when max_retries=0."""
        opener = FakeOpener([(500, {"error": "error"})])

        with patch.dict(os.environ, {"WEB_CHECK_MAX_RETRIES": "0"}):
            client = WebCheckClient(opener=opener)
            client.check_one("ssl", "example.com")

        assert opener.call_count == 1  # No retries


class TestResultCache:
    """Test in-memory caching layer."""

    def test_cache_miss_on_first_call(self):
        """First call should be cache miss."""
        cache = ResultCache(ttl_seconds=300)
        result = cache.get("https://example.com", "ssl")

        assert result is None
        assert cache.misses == 1
        assert cache.hits == 0

    def test_cache_hit_on_second_call(self):
        """Second call with same params should be cache hit."""
        cache = ResultCache(ttl_seconds=300)
        test_data = {"check": "ssl", "ok": True}

        cache.set("https://example.com", "ssl", test_data)
        result = cache.get("https://example.com", "ssl")

        assert result == test_data
        assert cache.hits == 1
        assert cache.misses == 0

    def test_cache_expiration(self):
        """Cache should expire after TTL."""
        cache = ResultCache(ttl_seconds=1)
        test_data = {"check": "ssl", "ok": True}

        cache.set("https://example.com", "ssl", test_data)
        time.sleep(1.1)  # Wait for expiration
        result = cache.get("https://example.com", "ssl")

        assert result is None
        assert cache.misses == 1

    def test_cache_disabled_with_zero_ttl(self):
        """Cache should be disabled when TTL=0."""
        cache = ResultCache(ttl_seconds=0)
        test_data = {"check": "ssl", "ok": True}

        cache.set("https://example.com", "ssl", test_data)
        result = cache.get("https://example.com", "ssl")

        assert result is None  # Cache disabled

    def test_cache_stats(self):
        """Cache stats should track hits and misses."""
        cache = ResultCache(ttl_seconds=300)
        test_data = {"check": "ssl", "ok": True}

        cache.set("https://example.com", "ssl", test_data)
        cache.get("https://example.com", "ssl")  # hit
        cache.get("https://other.com", "ssl")  # miss
        cache.get("https://example.com", "ssl")  # hit

        stats = cache.stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 66.7
        assert stats["size"] == 1
        assert stats["ttl_seconds"] == 300

    def test_cache_clear(self):
        """Cache clear should remove all entries."""
        cache = ResultCache(ttl_seconds=300)
        cache.set("https://example.com", "ssl", {"data": 1})
        cache.set("https://other.com", "dns", {"data": 2})

        assert cache.stats()["size"] == 2

        cache.clear()

        assert cache.stats()["size"] == 0
        assert cache.hits == 0
        assert cache.misses == 0

    def test_client_uses_cache(self):
        """WebCheckClient should use cache for repeated calls."""
        opener = FakeOpener([(200, {"check": "ssl", "ok": True})])
        client = WebCheckClient(opener=opener)

        # First call - cache miss
        result1 = client.check_one("ssl", "example.com")
        assert result1["ok"] is True
        assert opener.call_count == 1

        # Second call - cache hit
        result2 = client.check_one("ssl", "example.com")
        assert result2["ok"] is True
        assert opener.call_count == 1  # No second API call
        assert result2.get("cached") is True


class TestCircuitBreaker:
    """Test circuit breaker pattern."""

    def test_circuit_starts_closed(self):
        """Circuit should start in CLOSED state."""
        cb = CircuitBreaker()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.can_execute() is True

    def test_circuit_opens_after_failures(self):
        """Circuit should open after failure_threshold."""
        cb = CircuitBreaker(failure_threshold=3)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.CLOSED

        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN
        assert cb.can_execute() is False

    def test_circuit_blocks_when_open(self):
        """Circuit should block requests when OPEN."""
        cb = CircuitBreaker(failure_threshold=2)

        cb.record_failure()
        cb.record_failure()

        assert cb.state == CircuitBreaker.OPEN
        assert cb.can_execute() is False

    def test_circuit_half_open_after_timeout(self):
        """Circuit should transition to HALF_OPEN after recovery_timeout."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

        time.sleep(1.1)  # Wait for recovery
        assert cb.state == CircuitBreaker.HALF_OPEN
        assert cb.can_execute() is True

    def test_circuit_closes_on_success(self):
        """Circuit should close on success in HALF_OPEN state."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)

        cb.record_failure()
        cb.record_failure()
        time.sleep(1.1)
        assert cb.state == CircuitBreaker.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitBreaker.CLOSED

    def test_circuit_reopens_on_failure(self):
        """Circuit should reopen on failure in HALF_OPEN state."""
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)

        cb.record_failure()
        cb.record_failure()
        time.sleep(1.1)
        assert cb.state == CircuitBreaker.HALF_OPEN

        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

    def test_circuit_reset(self):
        """Circuit reset should return to CLOSED state."""
        cb = CircuitBreaker(failure_threshold=2)

        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreaker.OPEN

        cb.reset()
        assert cb.state == CircuitBreaker.CLOSED
        assert cb.can_execute() is True

    def test_per_base_url_circuits(self):
        """Client should track circuits per base_url."""
        opener = FakeOpener(
            [
                (500, {"error": "error1"}),
                (500, {"error": "error2"}),
                (500, {"error": "error3"}),
                (500, {"error": "error4"}),
                (500, {"error": "error5"}),
            ]
        )
        client = WebCheckClient(opener=opener, base_url="https://test.com/api")

        # Trigger failures to open circuit
        for _ in range(5):
            with patch.object(time, "sleep"):
                client.check_one("ssl", "example.com")

        # Circuit should be open for this base
        assert len(client._circuit_breakers) > 0


class TestRateLimiter:
    """Test token bucket rate limiting and HTTP-path integration."""

    def test_initial_tokens(self):
        limiter = RateLimiter(tokens_per_second=1.0, bucket_size=10)
        assert limiter.tokens == 10

    def test_acquire_reduces_tokens(self):
        clock = FakeClock()
        limiter = RateLimiter(tokens_per_second=1.0, bucket_size=10, clock=clock, sleeper=clock.sleep)

        assert limiter.acquire(timeout=1.0) is True
        assert limiter.tokens == 9

    def test_burst_capacity(self):
        clock = FakeClock()
        limiter = RateLimiter(tokens_per_second=1.0, bucket_size=5, clock=clock, sleeper=clock.sleep)

        for _ in range(5):
            assert limiter.acquire(timeout=1.0) is True

        assert limiter.tokens == pytest.approx(0, abs=1e-3)
        assert clock.now == 0

    def test_refill_over_time(self):
        clock = FakeClock()
        limiter = RateLimiter(tokens_per_second=10.0, bucket_size=10, clock=clock, sleeper=clock.sleep)

        for _ in range(10):
            limiter.acquire(timeout=1.0)

        clock.advance(0.5)
        limiter._refill()

        assert limiter.tokens == pytest.approx(5.0)

    def test_timeout_on_empty_bucket(self):
        clock = FakeClock()
        limiter = RateLimiter(tokens_per_second=0.1, bucket_size=1, clock=clock, sleeper=clock.sleep)

        assert limiter.acquire(timeout=1.0) is True
        assert limiter.acquire(timeout=0.5) is False
        assert clock.now == pytest.approx(0.5)
        assert limiter.stats()["total_timeouts"] == 1

    def test_stats(self):
        clock = FakeClock()
        limiter = RateLimiter(tokens_per_second=1.0, bucket_size=10, clock=clock, sleeper=clock.sleep)

        limiter.acquire(timeout=1.0)
        limiter.acquire(timeout=1.0)

        stats = limiter.stats()
        assert stats["tokens_per_second"] == 1.0
        assert stats["bucket_size"] == 10
        assert stats["current_tokens"] == 8
        assert stats["total_waits"] == 0
        assert stats["total_timeouts"] == 0

    def test_env_var_configuration(self):
        with patch.dict(os.environ, {"WEB_CHECK_RATE_LIMIT": "2.5"}):
            client = WebCheckClient()
            assert client._rate_limiter.tokens_per_second == 2.5

    def test_rejects_non_positive_configuration(self):
        with pytest.raises(ValueError, match="tokens_per_second"):
            RateLimiter(tokens_per_second=0)
        with pytest.raises(ValueError, match="bucket_size"):
            RateLimiter(bucket_size=0)

    def test_sequential_http_attempts_follow_fake_clock_rate(self):
        clock = FakeClock()
        limiter = RateLimiter(tokens_per_second=2.0, bucket_size=2, clock=clock, sleeper=clock.sleep)
        opener = FakeOpener([(200, {"ok": True}) for _ in range(5)])
        client = WebCheckClient(base_url="https://test.com/api", opener=opener, fallback=False)
        client._rate_limiter = limiter

        for index in range(5):
            status, _data, error = client._http_get(f"https://test.com/api/status?n={index}")
            assert status == 200
            assert error is None

        assert opener.call_count == 5
        assert clock.now == pytest.approx((5 - 2) / 2.0)
        assert limiter.stats()["total_waits"] == 3

    def test_rate_limiter_is_consulted_on_every_retry_attempt(self):
        opener = FakeOpener([(500, {"error": "retry"}), (200, {"ok": True})])
        client = WebCheckClient(base_url="https://test.com/api", opener=opener, fallback=False)
        limiter = Mock(spec=RateLimiter)
        limiter.acquire.return_value = True
        client._rate_limiter = limiter

        with patch.object(time, "sleep"):
            result = client.check_one("ssl", "example.com")

        assert result["ok"] is True
        assert opener.call_count == 2
        assert limiter.acquire.call_count == 2
        limiter.acquire.assert_called_with(timeout=0.0)

    def test_cache_hit_does_not_consume_another_token(self):
        opener = FakeOpener([(200, {"ok": True})])
        with patch.dict(os.environ, {"WEB_CHECK_CACHE_TTL": "300"}):
            client = WebCheckClient(base_url="https://test.com/api", opener=opener, fallback=False)
        limiter = Mock(spec=RateLimiter)
        limiter.acquire.return_value = True
        client._rate_limiter = limiter

        first = client.check_one("ssl", "example.com")
        second = client.check_one("ssl", "example.com")

        assert first["ok"] is True
        assert second["cached"] is True
        assert opener.call_count == 1
        assert limiter.acquire.call_count == 1

    def test_health_exposes_rate_limit_stats(self):
        clock = FakeClock()
        limiter = RateLimiter(tokens_per_second=2.0, bucket_size=2, clock=clock, sleeper=clock.sleep)
        client = WebCheckClient(
            base_url="https://test.com/api",
            opener=FakeOpener([(200, {"ip": "1.2.3.4"})]),
            fallback=False,
        )
        client._rate_limiter = limiter

        health = client.health()

        assert health["rate_limit_stats"] == limiter.stats()
        assert health["rate_limit_stats"]["current_tokens"] == 1.0

    def test_concurrent_burst_never_overspends_bucket(self):
        limiter = RateLimiter(tokens_per_second=0.001, bucket_size=3)
        barrier = threading.Barrier(12)

        def acquire_once(_index):
            barrier.wait()
            return limiter.acquire(timeout=0.02)

        with ThreadPoolExecutor(max_workers=12) as pool:
            outcomes = list(pool.map(acquire_once, range(12)))

        assert sum(outcomes) == 3
        assert limiter.stats()["total_timeouts"] == 9


class TestInputValidation:
    """Test input validation functions."""

    def test_validate_url_valid(self):
        """Should accept valid URLs."""
        from src.server import _validate_url

        # Valid URLs
        assert _validate_url("https://example.com") == "https://example.com"
        assert _validate_url("http://localhost:3000") == "http://localhost:3000"
        assert _validate_url("example.com") == "https://example.com"  # Auto-adds https

    def test_validate_url_invalid(self):
        """Should reject invalid URLs."""
        from src.server import _validate_url

        with pytest.raises(ValueError, match="must be a non-empty string"):
            _validate_url("")

        with pytest.raises(ValueError, match="must be a non-empty string"):
            _validate_url(None)

        with pytest.raises(ValueError):
            _validate_url("   ")  # Whitespace only

    def test_validate_check_name_valid(self):
        """Should accept valid check names."""
        from src.server import _validate_check_name

        assert _validate_check_name("ssl") == "ssl"
        assert _validate_check_name("dns") == "dns"
        assert _validate_check_name("/ssl") == "ssl"  # Strips leading slash

    def test_validate_check_name_invalid(self):
        """Should reject invalid check names."""
        from src.server import _validate_check_name

        with pytest.raises(ValueError, match="Unknown check"):
            _validate_check_name("invalid-check")

        with pytest.raises(ValueError, match="must be a non-empty string"):
            _validate_check_name("")

    def test_validate_group_name_valid(self):
        """Should accept valid group names."""
        from src.server import _validate_group_name

        assert _validate_group_name("quick") == "quick"
        assert _validate_group_name("security") == "security"
        assert _validate_group_name("all") == "all"

    def test_validate_group_name_invalid(self):
        """Should reject invalid group names."""
        from src.server import _validate_group_name

        with pytest.raises(ValueError, match="Unknown group"):
            _validate_group_name("invalid-group")

        with pytest.raises(ValueError, match="must be a non-empty string"):
            _validate_group_name("")

    def test_validate_positive_int(self):
        """Should validate positive integers."""
        from src.server import _validate_positive_int

        assert _validate_positive_int(5, "test", 1, 10) == 5
        assert _validate_positive_int("10", "test", 1, 100) == 10

        with pytest.raises(ValueError, match="must be between"):
            _validate_positive_int(0, "test", 1, 10)

        with pytest.raises(ValueError, match="must be between"):
            _validate_positive_int(11, "test", 1, 10)

        with pytest.raises(ValueError, match="must be a valid integer"):
            _validate_positive_int("abc", "test", 1, 10)
