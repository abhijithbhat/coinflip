"""
Deterministic Statistics Engine for Coinflip (/agent_and_ui/stats_engine.py).

Provides pure mathematical functions (zero AI calls) for:
1. Two-sided 95% Wilson score confidence intervals.
2. One-sided 95% upper confidence bounds (Rule of Three for 0 failures, one-sided Wilson for k > 0).
3. Automated fix verdict evaluation (CERTIFIED vs. REJECTED vs. BROKEN).
4. Mathematical curve generation for the streak & Rule-of-Three visual charts.
"""

from __future__ import annotations

import math
from typing import Any

# Standard normal critical values
Z_95_TWO_SIDED: float = 1.959963984540054  # 95% two-sided (alpha/2 = 0.025)
Z_95_ONE_SIDED: float = 1.6448536269514722  # 95% one-sided (alpha = 0.05)


def wilson_ci_95(failures: int, total_runs: int) -> tuple[float, float]:
    """
    Compute the 95% Wilson score binomial confidence interval (lower, upper)
    rounded to 4 decimal places.

    Example:
        wilson_ci_95(21, 300) -> (0.0462, 0.1046)
    """
    if total_runs <= 0:
        raise ValueError("total_runs must be greater than 0.")
    if failures < 0 or failures > total_runs:
        raise ValueError(f"failures ({failures}) must be between 0 and total_runs ({total_runs}).")

    p_hat = failures / total_runs
    z = Z_95_TWO_SIDED
    z2 = z * z

    denominator = 1.0 + (z2 / total_runs)
    center = p_hat + (z2 / (2.0 * total_runs))
    radicand = (p_hat * (1.0 - p_hat) / total_runs) + (z2 / (4.0 * total_runs * total_runs))
    margin = z * math.sqrt(max(0.0, radicand))

    lower = max(0.0, (center - margin) / denominator)
    upper = min(1.0, (center + margin) / denominator)

    return (round(lower, 4), round(upper, 4))


def exact_binomial_upper_bound_95(total_runs: int, confidence: float = 0.95) -> float:
    """
    Compute the exact Clopper-Pearson binomial upper bound when failures == 0:
        1.0 - (1.0 - confidence) ** (1.0 / total_runs)
    """
    if total_runs <= 0:
        raise ValueError("total_runs must be greater than 0.")
    if not (0.0 < confidence < 1.0):
        raise ValueError("confidence must be strictly between 0 and 1.")

    bound = 1.0 - ((1.0 - confidence) ** (1.0 / total_runs))
    return round(min(1.0, bound), 4)


def upper_confidence_bound_95(failures: int, total_runs: int) -> float:
    """
    Compute the 95% one-sided upper confidence bound on the failure rate.

    - When failures == 0 and total_runs > 0: implements the Rule of Three (3.0 / total_runs),
      so 0 / 1,000 returns 0.0030 (0.30%).
    - When failures > 0: computes the one-sided 95% Wilson upper confidence bound (z = 1.64485).
    """
    if total_runs <= 0:
        raise ValueError("total_runs must be greater than 0.")
    if failures < 0 or failures > total_runs:
        raise ValueError(f"failures ({failures}) must be between 0 and total_runs ({total_runs}).")

    if failures == 0:
        return round(min(1.0, 3.0 / total_runs), 4)

    if failures == total_runs:
        return 1.0

    p_hat = failures / total_runs
    z = Z_95_ONE_SIDED
    z2 = z * z

    denominator = 1.0 + (z2 / total_runs)
    center = p_hat + (z2 / (2.0 * total_runs))
    radicand = (p_hat * (1.0 - p_hat) / total_runs) + (z2 / (4.0 * total_runs * total_runs))
    margin = z * math.sqrt(max(0.0, radicand))

    upper = min(1.0, (center + margin) / denominator)
    return round(upper, 4)


def evaluate_fix_verdict(
    normal_failures: int,
    normal_runs: int,
    stress_failures: int,
    stress_runs: int,
    target_limit: float = 0.005,
) -> dict[str, Any]:
    """
    Evaluate whether a candidate fix is CERTIFIED, REJECTED, or BROKEN.

    Rules:
    - Returns "BROKEN" if normal_failures > 0.
    - Returns "REJECTED" if normal_failures == 0 (looks fixed on a quiet machine!)
      but stress_failures > 0 or upper_bound_95_stress > target_limit, or if
      normal_runs are insufficient to prove upper_bound_95_normal <= target_limit.
    - Returns "CERTIFIED" only if both upper bounds are <= target_limit
      (and 0 failures if runs < 600).
    """
    if normal_runs <= 0 or stress_runs <= 0:
        raise ValueError("Both normal_runs and stress_runs must be greater than 0.")

    normal_rate = round(normal_failures / normal_runs, 4)
    stress_rate = round(stress_failures / stress_runs, 4)

    upper_normal = upper_confidence_bound_95(normal_failures, normal_runs)
    upper_stress = upper_confidence_bound_95(stress_failures, stress_runs)

    ci_normal = wilson_ci_95(normal_failures, normal_runs)
    ci_stress = wilson_ci_95(stress_failures, stress_runs)

    # Case 1: Fails even under normal conditions -> BROKEN
    if normal_failures > 0:
        reason = (
            f"Candidate fix failed {normal_failures}/{normal_runs} times ({normal_rate * 100:.2f}%) "
            f"even on a normal machine (95% upper bound: {upper_normal * 100:.2f}% > "
            f"target {target_limit * 100:.2f}%)."
        )
        return {
            "verdict": "BROKEN",
            "certified": False,
            "normal_failures": normal_failures,
            "normal_runs": normal_runs,
            "normal_failure_rate": normal_rate,
            "normal_ci_95": ci_normal,
            "upper_bound_95_normal": upper_normal,
            "stress_failures": stress_failures,
            "stress_runs": stress_runs,
            "stress_failure_rate": stress_rate,
            "stress_ci_95": ci_stress,
            "upper_bound_95_stress": upper_stress,
            "target_limit": target_limit,
            "rejection_reason": reason,
        }

    # Case 2: Passes on a quiet machine (normal_failures == 0), now check stress & bounds
    if stress_failures > 0:
        reason = (
            f"Naive fix detected: passed {normal_runs}/{normal_runs} runs on a quiet machine (0.0% failure), "
            f"but failed {stress_failures}/{stress_runs} runs ({stress_rate * 100:.2f}%) under stress "
            f"(95% upper bound: {upper_stress * 100:.2f}% > target {target_limit * 100:.2f}%)."
        )
        return {
            "verdict": "REJECTED",
            "certified": False,
            "normal_failures": normal_failures,
            "normal_runs": normal_runs,
            "normal_failure_rate": normal_rate,
            "normal_ci_95": ci_normal,
            "upper_bound_95_normal": upper_normal,
            "stress_failures": stress_failures,
            "stress_runs": stress_runs,
            "stress_failure_rate": stress_rate,
            "stress_ci_95": ci_stress,
            "upper_bound_95_stress": upper_stress,
            "target_limit": target_limit,
            "rejection_reason": reason,
        }

    # If runs < 600 and we require 0 failures (already guaranteed here since normal_failures == 0 and stress_failures == 0),
    # check if upper bounds meet target_limit
    if upper_normal > target_limit or upper_stress > target_limit:
        reason = (
            f"Zero failures observed, but sample size ({normal_runs} normal, {stress_runs} stress) "
            f"yields 95% upper bounds ({upper_normal * 100:.2f}% normal, {upper_stress * 100:.2f}% stress) "
            f"above target limit ({target_limit * 100:.2f}%)."
        )
        return {
            "verdict": "REJECTED",
            "certified": False,
            "normal_failures": normal_failures,
            "normal_runs": normal_runs,
            "normal_failure_rate": normal_rate,
            "normal_ci_95": ci_normal,
            "upper_bound_95_normal": upper_normal,
            "stress_failures": stress_failures,
            "stress_runs": stress_runs,
            "stress_failure_rate": stress_rate,
            "stress_ci_95": ci_stress,
            "upper_bound_95_stress": upper_stress,
            "target_limit": target_limit,
            "rejection_reason": reason,
        }

    # Case 3: Both upper bounds <= target_limit (and 0 failures if runs < 600) -> CERTIFIED
    return {
        "verdict": "CERTIFIED",
        "certified": True,
        "normal_failures": normal_failures,
        "normal_runs": normal_runs,
        "normal_failure_rate": normal_rate,
        "normal_ci_95": ci_normal,
        "upper_bound_95_normal": upper_normal,
        "stress_failures": stress_failures,
        "stress_runs": stress_runs,
        "stress_failure_rate": stress_rate,
        "stress_ci_95": ci_stress,
        "upper_bound_95_stress": upper_stress,
        "target_limit": target_limit,
        "rejection_reason": None,
    }


def generate_streak_curve_data() -> list[dict[str, Any]]:
    """
    Generate the mathematical points for the chart on Page 5 of the Concept Brief:
    "Chance a STILL-BROKEN test looks fine" across true failure rates from 0% to 20%
    for 1 run, 10 runs in a row, and 100 runs in a row: (1 - p)**k,
    plus the Rule of Three bar metadata for 100, 300, 1,000, and 3,000 runs.
    """
    rule_of_three_bars = [
        {
            "runs": n,
            "zero_failures_upper_bound": round(3.0 / n, 4),
            "zero_failures_upper_bound_pct": round((3.0 / n) * 100, 2),
            "exact_binomial_upper_bound": exact_binomial_upper_bound_95(n),
            "label": f"failure rate below {(3.0 / n) * 100:g}% (~{n:,} runs with zero failures)",
        }
        for n in (100, 300, 1000, 3000)
    ]

    curve_points: list[dict[str, Any]] = []
    for pct in range(0, 21):
        p = pct / 100.0
        pass_1 = round((1.0 - p) ** 1, 4)
        pass_10 = round((1.0 - p) ** 10, 4)
        pass_100 = round((1.0 - p) ** 100, 4)

        point: dict[str, Any] = {
            "true_failure_rate": round(p, 4),
            "true_failure_rate_pct": pct,
            "pass_1_run": pass_1,
            "pass_10_runs": pass_10,
            "pass_100_runs": pass_100,
            "pass_1_run_pct": round(pass_1 * 100, 2),
            "pass_10_runs_pct": round(pass_10 * 100, 2),
            "pass_100_runs_pct": round(pass_100 * 100, 2),
        }
        if pct == 0:
            point["rule_of_three_bars"] = rule_of_three_bars
        curve_points.append(point)

    return curve_points