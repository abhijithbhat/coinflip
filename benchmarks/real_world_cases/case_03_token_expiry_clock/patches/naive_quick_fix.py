"""Naive Quick Fix: Slightly increase TTL to mask jitter.

Bumps TTL from 0.10s to 0.12s. While this may tolerate small millisecond
delays on quiet systems, it fails under CLOCK_SHIFT where wall-clock skew
is +0.15s between calls.

Coinflip Verdict: REJECTED (fails under CLOCK_SHIFT)
"""

from token_cache import TokenCache


def test_cache_stores_and_retrieves():
    """Stores and retrieves with slightly increased TTL."""
    cache = TokenCache(ttl_seconds=0.12)  # Naive fix: 0.12s still < 0.15s clock shift
    try:
        cache.store("session_token", "eyJhbGciOiJIUzI1NiJ9.test_payload")
        result = cache.retrieve("session_token")
        assert result == "eyJhbGciOiJIUzI1NiJ9.test_payload", (
            f"Expected session token, got {result!r}"
        )
    finally:
        cache.cleanup()
