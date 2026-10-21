"""Flaky test: Token cache TTL validation sensitive to wall-clock skew.

This test creates a token cache entry with a 0.10s TTL and retrieves it.
Under normal conditions, issuance and retrieval happen within microseconds,
passing reliably. Under CLOCK_SHIFT, monkey-patched time.time() incurs a
+0.15s skew between calls, making the token appear expired immediately.
"""

from token_cache import TokenCache


def test_cache_stores_and_retrieves():
    """Stores a session token and retrieves it before TTL expires.

    BUG: TokenCache relies on time.time() instead of time.monotonic().
    When NTP clock adjustments or CLOCK_SHIFT perturbations occur,
    time.time() shifts between calls, exceeding the 0.10s TTL.
    """
    cache = TokenCache(ttl_seconds=0.10)
    try:
        cache.store("session_token", "eyJhbGciOiJIUzI1NiJ9.test_payload")
        result = cache.retrieve("session_token")
        assert result == "eyJhbGciOiJIUzI1NiJ9.test_payload", (
            f"Expected session token, got {result!r} — "
            "token expired prematurely due to wall-clock skew"
        )
    finally:
        cache.cleanup()
