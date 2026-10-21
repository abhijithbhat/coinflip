"""Shared configuration service with module-level cache (singleton pattern).

This simulates a real-world pattern where configuration values are cached
at module level and shared across all tests in the same process/session.
Without isolation or state resets, test execution order shuffling exposes
polluted state.

Pure Python stdlib — zero external packages.
"""

from __future__ import annotations

# Module-level cache — shared across all tests in the same process.
# This is the "global singleton" that causes pollution across tests.
_GLOBAL_CONFIG_CACHE: dict[str, str] = {
    "region": "us-east-1",
    "tier": "standard",
}


def get_active_config() -> dict[str, str]:
    """Returns the current active configuration dictionary.

    Returns the shared global cache directly, allowing mutations in one test
    to pollute subsequent tests.
    """
    return _GLOBAL_CONFIG_CACHE


def set_tenant_region(region: str) -> None:
    """Mutates tenant region in the shared global configuration cache."""
    _GLOBAL_CONFIG_CACHE["region"] = region


def reset_config() -> None:
    """Resets global configuration to pristine default state."""
    _GLOBAL_CONFIG_CACHE.clear()
    _GLOBAL_CONFIG_CACHE.update({
        "region": "us-east-1",
        "tier": "standard",
    })


# Compatibility aliases
def get_shipping_rate(region: str = "domestic") -> float:
    return 12.99 if _GLOBAL_CONFIG_CACHE.get("region") != "us-east-1" else 5.99


def configure_premium_shipping(region: str = "domestic") -> None:
    set_tenant_region("eu-central-1")
