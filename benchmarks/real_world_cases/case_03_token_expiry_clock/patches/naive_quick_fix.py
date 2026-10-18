"""Naive Quick Fix: Increase TTL to exceed the clock shift.

Bumps TTL from 300 to 4000 seconds. Under clock_shift (+3600s), age = 3600
which is now < 4000, so the entry passes. But this is fragile — any larger
clock shift or real-world NTP jump would still break it.

Coinflip Verdict: REJECTED (passes THIS shift but fragile to larger shifts)
"""

from token_cache import FileCacheTTL


def test_cache_stores_and_retrieves():
    """Stores and retrieves with inflated TTL."""
    cache = FileCacheTTL(ttl_seconds=4000)  # Naive fix: 4000 > 3600
    try:
        cache.store("session_token", "eyJhbGciOiJIUzI1NiJ9.test_payload")
        result = cache.retrieve("session_token")
        assert result == "eyJhbGciOiJIUzI1NiJ9.test_payload", (
            f"Expected session token, got {result!r}"
        )
    finally:
        cache.cleanup()
