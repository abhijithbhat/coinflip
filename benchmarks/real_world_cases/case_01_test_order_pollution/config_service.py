"""Shared configuration service with module-level cache (singleton pattern).

This simulates a real-world pattern where configuration values are cached
at module level and shared across all tests in the same pytest session.
This is the root cause of order-dependent test pollution.

Pure Python stdlib — zero external packages.
"""

# Module-level cache — shared across all tests in the same pytest session.
# This is the "global singleton" that causes pollution across tests.
_rate_config_cache: dict[str, float] = {}


def get_shipping_rate(region: str = "domestic") -> float:
    """Returns the shipping rate for a region from cache, loading default if needed.

    Args:
        region: Shipping region identifier.

    Returns:
        The shipping rate for the region.
    """
    if region not in _rate_config_cache:
        # Load "default" config — domestic = 5.99
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
    _rate_config_cache.clear()
