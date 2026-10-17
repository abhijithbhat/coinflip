"""Deterministic mathematical and statistical utilities for Coinflip.

Implements Wilson score confidence intervals and the Rule of Three upper confidence bounds
without heavy external statistical dependencies.
"""

from __future__ import annotations

import math


def wilson_ci_95(failures: int, total_runs: int) -> tuple[float, float]:
    """Computes the two-sided 95% Wilson score confidence interval (lower, upper).

    For failures=21 and total_runs=300 (observed p=0.07), returns approximately
    (0.046, 0.105) or (4.6% to 10.5%).

    Args:
        failures: Number of observed failures (must be non-negative and <= total_runs).
        total_runs: Total number of experiment runs (must be positive).

    Returns:
        tuple[float, float]: (lower_bound, upper_bound) clamped to [0.0, 1.0].
    """
    if total_runs <= 0:
        return (0.0, 1.0)
    if failures < 0:
        failures = 0
    elif failures > total_runs:
        failures = total_runs

    n = float(total_runs)
    p = float(failures) / n

    # Standard normal quantile for two-sided 95% CI: z ≈ 1.95996398454
    z = 1.959963984540054
    z2 = z * z

    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    spread = (z * math.sqrt((p * (1.0 - p) / n) + (z2 / (4.0 * n * n)))) / denom

    lower = max(0.0, center - spread)
    upper = min(1.0, center + spread)

    return (round(lower, 4), round(upper, 4))


def upper_confidence_bound_95(failures: int, total_runs: int) -> float:
    """Computes the conservative 95% upper confidence bound on failure rate.

    - When failures == 0: applies the Rule of Three (3.0 / n), so 0/1000 clean runs
      returns 0.0030 (0.30%).
    - When failures > 0: computes a conservative 95% one-sided binomial upper bound
      using the Wilson score method with z = 1.64485362695.

    Args:
        failures: Number of observed failures.
        total_runs: Total number of experiment runs.

    Returns:
        float: Upper bound on the true failure rate at 95% confidence.
    """
    if total_runs <= 0:
        return 1.0
    if failures <= 0:
        # Rule of Three: P(true rate <= 3 / n) >= 0.95 given 0 failures in n trials
        return round(min(1.0, 3.0 / float(total_runs)), 4)

    n = float(total_runs)
    p = float(failures) / n

    # One-sided 95% confidence interval quantile: z = 1.6448536269514722
    z = 1.6448536269514722
    z2 = z * z

    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    spread = (z * math.sqrt((p * (1.0 - p) / n) + (z2 / (4.0 * n * n)))) / denom

    upper = min(1.0, center + spread)
    return round(upper, 4)
