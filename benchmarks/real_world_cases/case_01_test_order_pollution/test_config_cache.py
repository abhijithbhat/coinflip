"""Flaky test: Order-dependent test pollution via shared module-level cache.

In default top-to-bottom order, test_read_default_rate runs first (cache empty,
loads 5.99) and test_override_premium_rate runs second (sets 12.99). Both pass.

When COINFLIP_SHUFFLE=1 randomizes execution order, there's a 50% chance
test_override_premium_rate runs FIRST, polluting the cache with 12.99.
Then test_read_default_rate reads the polluted cache and FAILS.

Expected behavior across Coinflip's 7 perturbation conditions:
  - baseline:        0% failure (tests run in file order, no pollution)
  - shuffle_order:   ~50% failure — THIS IS THE TRIGGERING CONDITION
  - seed_change:     0% failure (seeds don't affect execution order)
  - clock_shift:     0% failure (clock doesn't affect execution order)
  - network_cut:     0% failure (no network in this test)
  - cpu_half_cores:  0% failure (CPU load doesn't affect execution order)
  - cpu_heavy_load:  0% failure (CPU load doesn't affect execution order)
"""

from config_service import get_shipping_rate, configure_premium_shipping


def test_read_default_rate():
    """Reads the default domestic shipping rate and asserts it's 5.99.

    BUG: Does not reset the module-level cache before reading. If
    test_override_premium_rate ran first and set the rate to 12.99,
    this test reads the polluted value and fails.
    """
    rate = get_shipping_rate("domestic")
    assert rate == 5.99, f"Expected default rate 5.99, got {rate}"


def test_override_premium_rate():
    """Configures premium shipping and asserts the premium rate is 12.99.

    This test ALWAYS passes regardless of order, but it mutates the
    module-level cache as a side effect, polluting state for any
    subsequent test that expects the default rate.
    """
    configure_premium_shipping("domestic")
    rate = get_shipping_rate("domestic")
    assert rate == 12.99, f"Expected premium rate 12.99, got {rate}"
