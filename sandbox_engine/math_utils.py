"""Deterministic mathematical and statistical utilities for Coinflip.

Implements Wilson score confidence intervals and the Rule of Three upper confidence bounds
without heavy external statistical dependencies.
"""

from __future__ import annotations

import math

from shared_contracts.schemas import CausalInferenceMetrics, SPRTExecutionTelemetry


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


def _log_comb(n: int, k: int) -> float:
    """Computes ln(n choose k) using math.lgamma for large numbers."""
    if k < 0 or k > n:
        return -float("inf")
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def fishers_exact_p_value(k_base: int, n_base: int, k_pert: int, n_pert: int) -> float:
    """Computes the one-sided Fisher's Exact Test p-value for perturbation failure rate increase.

    Evaluates the 2x2 contingency table:
                  Failures     Passes
    Baseline:      k_base   n_base - k_base
    Perturbation:  k_pert   n_pert - k_pert

    Args:
        k_base: Observed failures in baseline batch.
        n_base: Total runs in baseline batch.
        k_pert: Observed failures in perturbation batch.
        n_pert: Total runs in perturbation batch.

    Returns:
        float: One-sided hypergeometric p-value bounded in [0.0, 1.0].
    """
    if n_base <= 0 or n_pert <= 0:
        return 1.0

    # If perturbation has zero failures or failure rate <= baseline, no significant increase
    if k_pert == 0 or (k_pert / n_pert) <= (k_base / n_base):
        return 1.0

    total_n = n_base + n_pert
    total_k = k_base + k_pert

    # Hypergeometric upper tail sum: sum_{x = k_pert}^{min(n_pert, total_k)} P(X = x)
    log_denom = _log_comb(total_n, n_pert)
    p_value = 0.0
    max_x = min(n_pert, total_k)

    for x in range(k_pert, max_x + 1):
        y = total_k - x
        if 0 <= y <= n_base:
            log_num = _log_comb(n_pert, x) + _log_comb(n_base, y)
            log_prob = log_num - log_denom
            p_value += math.exp(log_prob)

    return round(min(1.0, max(0.0, p_value)), 8)


def compute_causal_metrics(
    k_base: int, n_base: int, k_pert: int, n_pert: int
) -> CausalInferenceMetrics:
    """Computes causal inference and contingency statistical significance metrics.

    Args:
        k_base: Baseline failure count.
        n_base: Baseline total runs.
        k_pert: Perturbation failure count.
        n_pert: Perturbation total runs.

    Returns:
        CausalInferenceMetrics: Validated metrics including Fisher p-value and Relative Risk.
    """
    p_val = fishers_exact_p_value(k_base, n_base, k_pert, n_pert)
    rate_base = k_base / max(1, n_base)
    rate_pert = k_pert / max(1, n_pert)
    delta = round(rate_pert - rate_base, 4)

    # Relative Risk calculation with continuity handling
    if rate_base > 0:
        rr = round(rate_pert / rate_base, 4)
    else:
        pseudo_base = 0.5 / max(1, n_base)
        pseudo_pert = (k_pert + 0.5) / max(1, n_pert)
        rr = round(pseudo_pert / pseudo_base, 4)

    is_significant = (p_val < 0.05) and (delta > 0.0)

    return CausalInferenceMetrics(
        fisher_p_value=p_val,
        relative_risk=rr,
        absolute_rate_delta=delta,
        is_statistically_significant=is_significant,
    )


def wald_sprt_check(
    failures: int,
    runs_done: int,
    target_runs: int = 1000,
    p0: float = 0.003,
    p1: float = 0.05,
    target_limit: float = 0.005,
) -> SPRTExecutionTelemetry:
    """Evaluates Wald's Sequential Probability Ratio Test (SPRT) for early-stop certification.

    Tests:
        H0: p <= p0 (failure rate <= 0.3%, patch eliminates flake)
        H1: p >= p1 (failure rate >= 5.0%, patch still exhibits stress flakiness)

    Args:
        failures: Cumulative failures observed so far under stress.
        runs_done: Number of runs executed so far under stress.
        target_runs: Nominal full certification budget (e.g., 1,000).
        p0: Null hypothesis failure rate bound (default: 0.003).
        p1: Alternative hypothesis failure rate bound (default: 0.05).
        target_limit: Maximum certified failure rate threshold (default: 0.005).

    Returns:
        SPRTExecutionTelemetry: Decision boundary telemetry and compute savings.
    """
    if runs_done <= 0:
        return SPRTExecutionTelemetry(
            enabled=True,
            early_stopped=False,
            decision="FULL_SAMPLE_REJECTED",
            runs_executed_stress=0,
            target_runs_stress=target_runs,
            runs_saved=0,
            compute_saved_pct=0.0,
            log_likelihood_ratio=0.0,
            rejection_threshold_b=2.9444,
        )

    # Type I error alpha = 0.05, Type II error beta = 0.05
    alpha = 0.05
    beta = 0.05
    b_threshold = math.log((1.0 - beta) / alpha)  # ln(0.95 / 0.05) ≈ 2.9444

    k = failures
    m = runs_done
    k_pass = m - k

    log_ratio_p = math.log(p1 / p0)
    log_ratio_q = math.log((1.0 - p1) / (1.0 - p0))

    llr = (k * log_ratio_p) + (k_pass * log_ratio_q)

    # Condition 1: Overwhelming evidence of flakiness -> Early Rejection!
    if llr >= b_threshold and m < target_runs:
        runs_saved = max(0, target_runs - m)
        saved_pct = round((runs_saved / target_runs) * 100.0, 1)
        return SPRTExecutionTelemetry(
            enabled=True,
            early_stopped=True,
            decision="EARLY_REJECT_STRESS",
            runs_executed_stress=m,
            target_runs_stress=target_runs,
            runs_saved=runs_saved,
            compute_saved_pct=saved_pct,
            log_likelihood_ratio=round(llr, 4),
            rejection_threshold_b=round(b_threshold, 4),
        )

    # Condition 2: Completed full sample budget
    if m >= target_runs:
        ucb = upper_confidence_bound_95(failures, m)
        decision = "FULL_SAMPLE_CERTIFIED" if (failures == 0 and ucb <= target_limit) else "FULL_SAMPLE_REJECTED"
        return SPRTExecutionTelemetry(
            enabled=True,
            early_stopped=False,
            decision=decision,
            runs_executed_stress=m,
            target_runs_stress=target_runs,
            runs_saved=0,
            compute_saved_pct=0.0,
            log_likelihood_ratio=round(llr, 4),
            rejection_threshold_b=round(b_threshold, 4),
        )

    # Inconclusive (continue sampling)
    return SPRTExecutionTelemetry(
        enabled=True,
        early_stopped=False,
        decision="FULL_SAMPLE_REJECTED",
        runs_executed_stress=m,
        target_runs_stress=target_runs,
        runs_saved=0,
        compute_saved_pct=0.0,
        log_likelihood_ratio=round(llr, 4),
        rejection_threshold_b=round(b_threshold, 4),
    )
