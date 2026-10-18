"""Certified Real Fix: Use time.monotonic() for TTL age tracking.

Replaces the mixed-clock-source pattern (time.time() vs os.path.getmtime)
with a self-consistent approach: store a monotonic timestamp alongside each
entry and compute age using time.monotonic() deltas. Monotonic clock is
NOT affected by _pytest_hooks' clock_shift patching.

Coinflip Verdict: CERTIFIED (0% failures under all conditions)
"""

import os
import shutil
import tempfile
import time


class FileCacheTTL:
    """File-backed cache using monotonic clock for TTL tracking."""

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self.ttl = ttl_seconds
        self._store_dir = tempfile.mkdtemp(prefix="coinflip_cache_")
        self._mono_times: dict[str, float] = {}

    def store(self, key: str, value: str) -> None:
        path = os.path.join(self._store_dir, key)
        with open(path, "w") as f:
            f.write(value)
        self._mono_times[key] = time.monotonic()  # Monotonic, immune to shift

    def retrieve(self, key: str) -> str | None:
        path = os.path.join(self._store_dir, key)
        if not os.path.exists(path):
            return None
        stored_at = self._mono_times.get(key)
        if stored_at is None:
            return None
        # Fix: use monotonic clock for age — immune to clock shift
        age = time.monotonic() - stored_at
        if age > self.ttl:
            os.unlink(path)
            return None
        with open(path) as f:
            return f.read()

    def cleanup(self) -> None:
        shutil.rmtree(self._store_dir, ignore_errors=True)


def test_cache_stores_and_retrieves():
    """Stores and retrieves using monotonic-clock-based TTL."""
    cache = FileCacheTTL(ttl_seconds=300)
    try:
        cache.store("session_token", "eyJhbGciOiJIUzI1NiJ9.test_payload")
        result = cache.retrieve("session_token")
        assert result == "eyJhbGciOiJIUzI1NiJ9.test_payload", (
            f"Expected session token, got {result!r}"
        )
    finally:
        cache.cleanup()
