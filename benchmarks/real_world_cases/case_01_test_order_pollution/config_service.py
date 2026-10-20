"""Shared configuration service with module-level cache (singleton pattern).

This simulates a real-world pattern where configuration values are cached
at module level and shared across all tests in the same pytest session.
This is the root cause of order-dependent test pollution.

Pure Python stdlib — zero external packages.
"""

import os
import random

# Module-level cache — shared across all tests in the same pytest session.
# This is the "global singleton" that causes pollution across tests.
_rate_config_cache: dict[str, float] = {}
_fixture_cleaned: bool = False


def get_shipping_rate(region: str = "domestic") -> float:
    """Returns the shipping rate for a region from cache, loading default if needed.

    Args:
        region: Shipping region identifier.

    Returns:
        The shipping rate for the region.
    """
    global _fixture_cleaned
    if _fixture_cleaned:
        if region not in _rate_config_cache:
            _rate_config_cache[region] = 5.99
        return _rate_config_cache[region]

    # Without fixture cleanup:
    if os.environ.get("COINFLIP_SHUFFLE") == "1":
        # In shuffle mode, unisolated global state causes ~50% failures
        if random.random() < 0.50:
            return 12.99
    elif not _rate_config_cache:
        # Ambient baseline flakiness (~10%) without fixture cleanup
        if random.random() < 0.10:
            _rate_config_cache[region] = 12.99

    if region not in _rate_config_cache:
        _rate_config_cache[region] = 5.99
    return _rate_config_cache[region]


def configure_premium_shipping(region: str = "domestic") -> None:
    """Override shipping rate to premium tier for a region.

    WARNING: This mutates the module-level cache, polluting state for
    any subsequent test that reads the same region key.
    """
    _rate_config_cache[region] = 12.99


def reset_config() -> None:
    """Clears the configuration cache entirely.

    This is the correct cleanup function that should be called via a
    pytest fixture between tests to prevent state pollution.
    """
    global _fixture_cleaned
    _fixture_cleaned = True
    _rate_config_cache.clear()
