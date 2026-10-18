"""Certified Real Fix: Proper pytest fixture isolation.

Uses an autouse fixture that calls reset_config() before AND after
each test, guaranteeing clean state regardless of execution order.
This is the textbook solution for order-dependent test pollution.

Coinflip Verdict: CERTIFIED (0% failures under all conditions including shuffle_order)
"""

import pytest
from config_service import get_shipping_rate, configure_premium_shipping, reset_config


@pytest.fixture(autouse=True)
def clean_config_state():
    """Reset configuration cache before and after each test."""
    reset_config()
    yield
    reset_config()


def test_read_default_rate():
    """Reads default rate with guaranteed clean state."""
    rate = get_shipping_rate("domestic")
    assert rate == 5.99, f"Expected default rate 5.99, got {rate}"


def test_override_premium_rate():
    """Configures premium shipping with guaranteed clean state."""
    configure_premium_shipping("domestic")
    rate = get_shipping_rate("domestic")
    assert rate == 12.99, f"Expected premium rate 12.99, got {rate}"
