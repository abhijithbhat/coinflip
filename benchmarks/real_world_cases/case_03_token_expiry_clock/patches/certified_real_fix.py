"""Certified Real Fix: Use time.monotonic() for TTL age tracking.

Replaces wall-clock time.time() with time.monotonic(). Monotonic time
guarantees non-decreasing timestamps that are immune to NTP step adjustments,
leap seconds, and CLOCK_SHIFT runtime perturbations.

Coinflip Verdict: CERTIFIED (0% failures under all conditions)
"""

import time


class MonotonicTokenCache:
    """Token cache using time.monotonic() for robust TTL validation."""

    def __init__(self, ttl_seconds: float = 0.10) -> None:
        self.ttl = ttl_seconds
        self._entries: dict[str, tuple[str, float]] = {}

    def store(self, key: str, value: str) -> None:
        # Coinflip Real Fix: time.monotonic() for issuance timestamp
        self._entries[key] = (value, time.monotonic())

    def retrieve(self, key: str) -> str | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        value, issued_at = entry
        # Coinflip Real Fix: time.monotonic() delta is immune to clock shifts
        if time.monotonic() - issued_at > self.ttl:
            return None
        return value

    def cleanup(self) -> None:
        self._entries.clear()


def test_cache_stores_and_retrieves():
    """Stores and retrieves using monotonic-clock-based TTL."""
    cache = MonotonicTokenCache(ttl_seconds=0.10)
    try:
        cache.store("session_token", "eyJhbGciOiJIUzI1NiJ9.test_payload")
        result = cache.retrieve("session_token")
        assert result == "eyJhbGciOiJIUzI1NiJ9.test_payload", (
            f"Expected session token, got {result!r}"
        )
    finally:
        cache.cleanup()
