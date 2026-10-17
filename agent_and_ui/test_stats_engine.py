"""Unit tests for /agent_and_ui/stats_engine.py."""

import pytest
from agent_and_ui.stats_engine import (
    wilson_ci_95,
    upper_confidence_bound_95,
    exact_binomial_upper_bound_95,
    evaluate_fix_verdict,
    generate_streak_curve_data,
)


def test_wilson_ci_95_pdf_benchmark():
    """21 failures in 300 runs (7.0%) must return (0.0462, 0.1046) matching Page 7 & 8 of the PDF."""
    lower, upper = wilson_ci_95(21, 300)
    assert lower == pytest.approx(0.0462, abs=1e-4)
    assert upper == pytest.approx(0.1046, abs=1e-4)


def test_wilson_ci_95_boundaries():
    """Check 0% and 100% failure edge cases."""
    low_0, up_0 = wilson_ci_95(0, 1000)
    assert low_0 == 0.0
    assert 0.0030 <= up_0 <= 0.0040

    low_all, up_all = wilson_ci_95(300, 300)
    assert up_all == 1.0
    assert 0.98 < low_all < 1.0


def test_upper_confidence_bound_95_rule_of_three():
    """0 failures in 1,000 runs must return 0.0030 (0.30% Rule of Three)."""
    assert upper_confidence_bound_95(0, 1000) == 0.0030
    assert upper_confidence_bound_95(0, 300) == 0.0100
    assert upper_confidence_bound_95(0, 100) == 0.0300
    assert upper_confidence_bound_95(0, 3000) == 0.0010


def test_exact_binomial_upper_bound_95():
    """Exact binomial bound for 0/1000 is 1 - 0.05^(1/1000) ~= 0.0030."""
    assert exact_binomial_upper_bound_95(1000) == 0.0030


def test_upper_confidence_bound_95_nonzero_failures():
    """When failures > 0, computes one-sided 95% Wilson upper bound."""
    bound = upper_confidence_bound_95(61, 1000)  # 6.1% failure under stress
    assert 0.070 <= bound <= 0.076


def test_evaluate_fix_verdict_states():
    """Verify BROKEN, REJECTED, and CERTIFIED transitions from Page 9 of the PDF."""
    # 1. Original test: 21/300 normal, 174/300 stress -> BROKEN
    broken = evaluate_fix_verdict(21, 300, 174, 300, target_limit=0.005)
    assert broken["verdict"] == "BROKEN"
    assert broken["certified"] is False

    # 2. Naive Quick Fix: 0/1000 normal, 61/1000 stress (6.1%) -> REJECTED
    rejected = evaluate_fix_verdict(0, 1000, 61, 1000, target_limit=0.005)
    assert rejected["verdict"] == "REJECTED"
    assert rejected["certified"] is False
    assert rejected["rejection_reason"] is not None
    assert "Naive fix detected" in rejected["rejection_reason"]

    # 3. Coinflip Certified Fix: 0/1000 normal, 0/1000 stress -> CERTIFIED (0.0030 <= 0.005)
    certified = evaluate_fix_verdict(0, 1000, 0, 1000, target_limit=0.005)
    assert certified["verdict"] == "CERTIFIED"
    assert certified["certified"] is True
    assert certified["upper_bound_95_normal"] == 0.0030
    assert certified["upper_bound_95_stress"] == 0.0030
    assert certified["rejection_reason"] is None


def test_generate_streak_curve_data():
    """Verify Page 5 streak curve math at p = 5% (0.95, 0.5987 -> 60%, 0.0059 -> 0.6%)."""
    data = generate_streak_curve_data()
    assert len(data) == 21  # 0% through 20%

    p5 = next(item for item in data if item["true_failure_rate_pct"] == 5)
    assert p5["pass_1_run"] == 0.9500
    assert p5["pass_10_runs"] == pytest.approx(0.5987, abs=1e-4)
    assert p5["pass_100_runs"] == pytest.approx(0.0059, abs=1e-4)