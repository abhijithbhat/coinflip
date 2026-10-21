"""Flaky test: Order-dependent test pollution via shared module-level cache.

In default top-to-bottom order:
1. test_a_default_tenant_config runs first (cache has default "us-east-1") -> PASS.
2. test_b_mutate_tenant_config runs second (mutates cache to "eu-central-1") -> PASS.

When SHUFFLE_ORDER reverses test execution order:
1. test_b_mutate_tenant_config runs first, mutating shared _GLOBAL_CONFIG_CACHE to "eu-central-1".
2. test_a_default_tenant_config runs second and reads polluted cache, failing its assertion!
"""

from config_service import _GLOBAL_CONFIG_CACHE, get_active_config


def test_a_default_tenant_config():
    """Asserts default tenant configuration has region us-east-1.

    BUG: Does not reset the module-level cache before reading. If
    test_b_mutate_tenant_config ran first and mutated region to eu-central-1,
    this test reads polluted state and fails.
    """
    config = get_active_config()
    assert config["region"] == "us-east-1", f"Expected us-east-1, got {config['region']}"


def test_b_mutate_tenant_config():
    """Mutates tenant configuration without restoring state.

    This test mutates the shared module-level cache as a side effect,
    polluting state for any subsequent test expecting default values.
    """
    _GLOBAL_CONFIG_CACHE["region"] = "eu-central-1"
    assert get_active_config()["region"] == "eu-central-1"
