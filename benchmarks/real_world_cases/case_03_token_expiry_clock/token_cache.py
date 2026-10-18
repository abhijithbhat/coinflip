"""File-backed cache with TTL validation.

This module implements a simple file-backed cache that stores values as
files and uses the file's OS modification time (os.path.getmtime) as the
"stored at" timestamp. The freshness check compares this OS timestamp
against time.time() to compute the entry's age.

BUG: Under clock_shift, _pytest_hooks monkey-patches time.time() to
return real_time + 3600, but os.path.getmtime() still returns real OS
time. The mismatch makes entries appear 3600 seconds old immediately
after creation, causing 100% expiry failures.

Pure Python stdlib — zero external packages.
"""

import os
import shutil
import tempfile
import time


class FileCacheTTL:
    """File-backed cache with TTL-based expiry.

    Stores values as files in a temporary directory. Freshness is checked
    by comparing the file's OS modification time against time.time().

    Attributes:
        ttl: Maximum age in seconds before an entry is considered expired.
    """

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self.ttl = ttl_seconds
        self._store_dir = tempfile.mkdtemp(prefix="coinflip_cache_")

    def store(self, key: str, value: str) -> None:
        """Store a value in the cache.

        Args:
            key: Cache key (used as filename).
            value: String value to store.
        """
        path = os.path.join(self._store_dir, key)
        with open(path, "w") as f:
            f.write(value)

    def retrieve(self, key: str) -> str | None:
        """Retrieve a value if it hasn't expired.

        BUG: Computes age as time.time() - os.path.getmtime(). Under
        clock_shift, time.time() is shifted +3600 but getmtime() returns
        the real OS timestamp. This makes age = 3600+ immediately,
        exceeding any reasonable TTL.

        Args:
            key: Cache key to look up.

        Returns:
            The stored string value, or None if expired/missing.
        """
        path = os.path.join(self._store_dir, key)
        if not os.path.exists(path):
            return None
        stored_at = os.path.getmtime(path)  # Real OS time (NOT patched)
        current_time = time.time()            # PATCHED under clock_shift
        age = current_time - stored_at
        if age > self.ttl:
            os.unlink(path)
            return None  # Expired!
        with open(path) as f:
            return f.read()

    def cleanup(self) -> None:
        """Remove the cache directory."""
        shutil.rmtree(self._store_dir, ignore_errors=True)
