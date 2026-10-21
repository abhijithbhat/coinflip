"""Naive Quick Fix: Inline cache reset inside test_a.

This fix manually resets the region key inside test_a_default_tenant_config.
While it works for this single test, it does not clean up state on teardown,
leaving the global cache polluted for any other test that might follow test_b.

Coinflip Verdict: REJECTED (brittle inline fix)
"""

from config_service import _GLOBAL_CONFIG_CACHE, get_active_config


def test_a_default_tenant_config():
    _GLOBAL_CONFIG_CACHE["region"] = "us-east-1"  # Naive inline fix
    config = get_active_config()
    assert config["region"] == "us-east-1", f"Expected us-east-1, got {config['region']}"


def test_b_mutate_tenant_config():
    _GLOBAL_CONFIG_CACHE["region"] = "eu-central-1"
    assert get_active_config()["region"] == "eu-central-1"
