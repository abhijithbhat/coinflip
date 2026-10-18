"""Flaky test: Cache TTL validation that mixes wall-clock sources.

This test creates a file-backed cache entry, then immediately retrieves it.
Under normal conditions, the entry is fresh. Under clock_shift, the
monkey-patched time.time() disagrees with os.path.getmtime(), making
the entry appear 3600 seconds old and triggering expiry.

Expected behavior across Coinflip's 7 perturbation conditions:
  - baseline:        0% failure (time.time() matches file mtime)
  - shuffle_order:   0% failure
  - seed_change:     0% failure
  - clock_shift:     100% failure — THIS IS THE TRIGGERING CONDITION
  - network_cut:     0% failure
  - cpu_half_cores:  0% failure
  - cpu_heavy_load:  0% failure
"""

from token_cache import FileCacheTTL


def test_cache_stores_and_retrieves():
    """Stores a session token and immediately retrieves it.

    BUG: The cache's retrieve() method computes entry age as
    time.time() - os.path.getmtime(). Under clock_shift (+3600s),
    time.time() is shifted but getmtime() isn't, so age = 3600.
    With TTL = 300s, the entry appears expired immediately.
    """
    cache = FileCacheTTL(ttl_seconds=300)
    try:
        cache.store("session_token", "eyJhbGciOiJIUzI1NiJ9.test_payload")
        result = cache.retrieve("session_token")
        assert result == "eyJhbGciOiJIUzI1NiJ9.test_payload", (
            f"Expected session token, got {result!r} — "
            "entry may have been expired prematurely"
        )
    finally:
        cache.cleanup()
