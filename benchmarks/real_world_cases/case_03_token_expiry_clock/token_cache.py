"""Token cache with TTL validation using wall-clock time.

This module implements an in-memory token cache that validates session
freshness against a short TTL. It uses time.time() to record issuance time
and compute entry age.

Under external CLOCK_SHIFT perturbations (NTP step adjustments / clock drift),
time.time() experiences wall-clock skew between calls, causing tokens to appear
prematurely expired.

Pure Python stdlib — zero external packages.
"""

from __future__ import annotations

import time


class TokenCache:
    """Token cache with TTL-based validation.

    Freshness is checked by comparing current time.time() against
    the issuance timestamp recorded with time.time().
    """

    def __init__(self, ttl_seconds: float = 0.10) -> None:
        self.ttl = ttl_seconds
        self._entries: dict[str, tuple[str, float]] = {}

    def store(self, key: str, value: str) -> None:
        """Stores a token value and records issuance timestamp via time.time()."""
        self._entries[key] = (value, time.time())

    def retrieve(self, key: str) -> str | None:
        """Retrieves a token if it hasn't expired according to time.time().

        BUG: Uses wall-clock time.time(). Under external clock shifts (e.g. NTP
        adjustments or CLOCK_SHIFT perturbation), the delta between calls exceeds
        self.ttl, causing false expirations.
        """
        entry = self._entries.get(key)
        if entry is None:
            return None
        value, issued_at = entry
        if time.time() - issued_at > self.ttl:
            return None
        return value

    def cleanup(self) -> None:
        """Cleans up cache storage."""
        self._entries.clear()


# Alias for compatibility
FileCacheTTL = TokenCache
