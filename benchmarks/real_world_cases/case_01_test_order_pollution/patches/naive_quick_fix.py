"""Naive Quick Fix: Inline cache clear before the failing test.

This fix manually clears the config cache at the start of
test_read_default_rate. It works in the current file, but is fragile:
any NEW test that also reads the default rate would need the same hack.

Coinflip Verdict: REJECTED (brittle, doesn't scale to new tests)
"""

from config_service import get_shipping_rate, configure_premium_shipping, _rate_config_cache


def test_read_default_rate():
    """Reads default rate after manually clearing cache."""
    _rate_config_cache.clear()  # Naive inline hack
    rate = get_shipping_rate("domestic")
    assert rate == 5.99, f"Expected default rate 5.99, got {rate}"


def test_override_premium_rate():
    """Configures premium shipping and asserts premium rate."""
    configure_premium_shipping("domestic")
    rate = get_shipping_rate("domestic")
    assert rate == 12.99, f"Expected premium rate 12.99, got {rate}"
