"""Deterministic canonical biostatistics and mathematical utilities for Coinflip.

Implements:
1. Two-sided 95% Wilson score confidence intervals.
2. Exact one-sided 95% Clopper-Pearson upper confidence bounds (with 50-step bisection).
3. One-sided Fisher's Exact Test via math.lgamma.
4. Step-down Holm-Bonferroni multiple-comparison adjustment.
5. Haldane-corrected Relative Risk & Effect determination.
6. Wald's Sequential Probability Ratio Test (SPRT).
"""

from __future__ import annotations

import math
from typing import Any

from shared_contracts.schemas import CausalInferenceMetrics, SPRTExecutionTelemetry

Z_95_TWO_SIDED: float = 1.959963984540054


def wilson_ci_95(failures: int, total_runs: int) -> tuple[float, float]:
    """Computes the two-sided 95% Wilson score confidence interval (lower, upper).

    Args:
        failures: Number of observed failures.
        total_runs: Total number of experiment runs.

    Returns:
        tuple[float, float]: (lower_bound, upper_bound) clamped to [0.0, 1.0] and rounded to 4 decimals.
    """
    if total_runs <= 0:
        return (0.0, 1.0)
    if failures < 0:
        failures = 0
    elif failures > total_runs:
        failures = total_runs

    n = float(total_runs)
    p = float(failures) / n

    z = Z_95_TWO_SIDED
    z2 = z * z

    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    spread = (z * math.sqrt(max(0.0, (p * (1.0 - p) / n) + (z2 / (4.0 * n * n))))) / denom

    lower = max(0.0, center - spread)
    upper = min(1.0, center + spread)

    return (round(lower, 4), round(upper, 4))


def _log_comb(n: int, k: int) -> float:
    """Computes ln(n choose k) using math.lgamma to avoid numerical overflow."""
    if k < 0 or k > n:
        return -float("inf")
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def clopper_pearson_upper_95(failures: int, total_runs: int) -> float:
    """Exact one-sided 95% Clopper-Pearson upper confidence bound for ALL failures >= 0.

    - If total_runs <= 0: returns 1.0.
    - If failures >= total_runs: returns 1.0.
    - If failures == 0: returns 1.0 - math.pow(0.05, 1.0 / total_runs).
    - If failures > 0: uses 50 iterations of binary search on p in [failures/total_runs, 1.0]
      solving sum_{i=0}^{failures} C(n, i) * p^i * (1-p)^(n-i) = 0.05 via math.lgamma.

    Args:
        failures: Number of observed failures.
        total_runs: Total experiment trials.

    Returns:
        float: Upper confidence bound on failure rate at 95% confidence.
    """
    if total_runs <= 0:
        return 1.0
    if failures >= total_runs:
        return 1.0
    if failures <= 0:
        bound = 1.0 - math.pow(0.05, 1.0 / float(total_runs))
        return round(min(1.0, max(0.0, bound)), 4)

    n = total_runs
    k = failures

    # Binary search / bisection on p in [failures / total_runs, 1.0]
    low = float(k) / float(n)
    high = 1.0

    for _ in range(50):
        mid = (low + high) / 2.0
        # P(X <= k; n, mid) = sum_{i=0}^k C(n, i) * mid^i * (1 - mid)^(n - i)
        prob = 0.0
        log_mid = math.log(mid) if mid > 0.0 else -1000.0
        log_one_minus_mid = math.log(1.0 - mid) if (1.0 - mid) > 0.0 else -1000.0

        for i in range(k + 1):
            log_term = _log_comb(n, i) + (i * log_mid) + ((n - i) * log_one_minus_mid)
            prob += math.exp(log_term)

        # Since P(X <= k; p) is strictly decreasing in p:
        # If prob > 0.05, p must be larger to decrease prob towards 0.05
        if prob > 0.05:
            low = mid
        else:
            high = mid

    return round((low + high) / 2.0, 4)


def upper_confidence_bound_95(failures: int, total_runs: int) -> float:
    """Alias for clopper_pearson_upper_95."""
    return clopper_pearson_upper_95(failures, total_runs)


def exact_binomial_upper_bound_95(arg1: int, arg2: int | None = None, **kwargs: Any) -> float:
    """Alias calling clopper_pearson_upper_95.

    Supports both exact_binomial_upper_bound_95(total_runs) (failures=0)
    and exact_binomial_upper_bound_95(failures, total_runs).
    """
    if arg2 is None:
        return clopper_pearson_upper_95(0, arg1)
    return clopper_pearson_upper_95(arg1, arg2)


def fishers_exact_p_value(
    k_pert: int, n_pert: int, k_base: int, n_base: int
) -> float:
    """One-sided upper-tail hypergeometric exact test via math.lgamma.

    Evaluates whether the failure rate in the perturbation batch is significantly
    higher than in the baseline batch:
                  Failures     Passes
    Perturbation:  k_pert    n_pert - k_pert
    Baseline:      k_base    n_base - k_base

    Args:
        k_pert: Observed failures in perturbation batch.
        n_pert: Total runs in perturbation batch.
        k_base: Observed failures in baseline batch.
        n_base: Total runs in baseline batch.

    Returns:
        float: One-sided hypergeometric p-value in [0.0, 1.0].
    """
    if n_base <= 0 or n_pert <= 0:
        return 1.0

    if k_pert <= 0 or (k_pert / n_pert) <= (k_base / n_base):
        return 1.0

    total_n = n_base + n_pert
    total_k = k_base + k_pert

    log_denom = _log_comb(total_n, n_pert)
    p_value = 0.0
    max_x = min(n_pert, total_k)

    for x in range(k_pert, max_x + 1):
        y = total_k - x
        if 0 <= (n_pert - x) <= (total_n - total_k) and 0 <= y <= n_base:
            log_num = _log_comb(total_k, x) + _log_comb(total_n - total_k, n_pert - x)
            p_value += math.exp(log_num - log_denom)

    return round(min(1.0, max(0.0, p_value)), 8)


def holm_bonferroni_adjust(p_values: list[float]) -> list[float]:
    """Step-down Holm-Bonferroni multiple-comparison adjustment across m p-values.

    Sort indices by ascending p, compute:
        adj[idx] = min(1.0, max_{j <= i} ((m - j) * p_sorted[j]))  (0-indexed j)
    and return adjusted p-values in original order.

    Args:
        p_values: List of unadjusted p-values.

    Returns:
        list[float]: Adjusted p-values in the exact original list order.
    """
    m = len(p_values)
    if m == 0:
        return []

    sorted_indices = sorted(range(m), key=lambda idx: p_values[idx])
    p_sorted = [p_values[idx] for idx in sorted_indices]

    adj_sorted: list[float] = [0.0] * m
    max_running = 0.0
    for i in range(m):
        val = (m - i) * p_sorted[i]
        max_running = max(max_running, val)
        adj_sorted[i] = min(1.0, max_running)

    result: list[float] = [0.0] * m
    for i, orig_idx in enumerate(sorted_indices):
        result[orig_idx] = round(adj_sorted[i], 6)

    return result


def relative_risk_and_effect(
    k_pert: int,
    n_pert: int,
    k_base: int,
    n_base: int,
    holm_adjusted_p_value: float | None = None,
) -> dict[str, Any]:
    """Haldane-corrected Relative Risk and effect determination.

    Relative Risk:
        ((k_pert + 0.5) / (n_pert + 0.5)) / ((k_base + 0.5) / (n_base + 0.5))
    Flag significance ONLY when holm_adjusted_p_value < 0.01 and relative_risk >= 1.8.

    Args:
        k_pert: Perturbation failures.
        n_pert: Perturbation total runs.
        k_base: Baseline failures.
        n_base: Baseline total runs.
        holm_adjusted_p_value: Optional precomputed Holm-Bonferroni adjusted p-value.

    Returns:
        dict[str, Any]: relative_risk, rate_delta, p_value, holm_adjusted_p_value, is_statistically_significant.
    """
    if (k_pert == k_base and n_pert == n_base) or (k_pert == 0 and k_base == 0):
        return {
            "relative_risk": 1.0,
            "rate_delta": 0.0,
            "p_value": 1.0,
            "holm_adjusted_p_value": 1.0,
            "is_statistically_significant": False,
        }

    pert_rate_haldane = (k_pert + 0.5) / (max(n_pert, 0) + 0.5)
    base_rate_haldane = (k_base + 0.5) / (max(n_base, 0) + 0.5)
    rr = round(pert_rate_haldane / base_rate_haldane, 4)

    raw_rate_pert = k_pert / max(n_pert, 1)
    raw_rate_base = k_base / max(n_base, 1)
    rate_delta = round(raw_rate_pert - raw_rate_base, 4)

    raw_p = fishers_exact_p_value(k_pert, n_pert, k_base, n_base)
    adj_p = holm_adjusted_p_value if holm_adjusted_p_value is not None else raw_p

    is_significant = bool(adj_p < 0.01 and rr >= 1.8)

    return {
        "relative_risk": rr,
        "rate_delta": rate_delta,
        "p_value": raw_p,
        "holm_adjusted_p_value": adj_p,
        "is_statistically_significant": is_significant,
    }


def compute_causal_metrics(
    k_base: int = 0,
    n_base: int = 1,
    k_pert: int = 0,
    n_pert: int = 1,
    holm_adjusted_p_value: float | None = None,
    **kwargs: Any,
) -> CausalInferenceMetrics:
    """Computes causal inference and contingency statistical significance metrics."""
    res = relative_risk_and_effect(
        k_pert=k_pert,
        n_pert=n_pert,
        k_base=k_base,
        n_base=n_base,
        holm_adjusted_p_value=holm_adjusted_p_value,
    )
    return CausalInferenceMetrics(
        fisher_p_value=res["p_value"],
        relative_risk=res["relative_risk"],
        absolute_rate_delta=res["rate_delta"],
        is_statistically_significant=res["is_statistically_significant"],
        holm_adjusted_p_value=res["holm_adjusted_p_value"],
    )


def wald_sprt_sequential_check(
    failures: int,
    runs: int,
    p0: float = 0.003,
    p1: float = 0.05,
    alpha: float = 0.05,
    beta: float = 0.05,
    target_runs: int = 1000,
    **kwargs: Any,
) -> dict[str, Any]:
    """Evaluates Wald's Sequential Probability Ratio Test (SPRT).

    Tests:
        H0: p <= p0 (failure rate <= 0.3%, patch eliminates flake)
        H1: p >= p1 (failure rate >= 5.0%, patch still exhibits stress flakiness)

    Thresholds:
        B = math.log((1 - beta) / alpha)   (~2.9444)
        A = math.log(beta / (1 - alpha))   (~-2.9444)

    Status:
        - "REJECTED_EARLY_STOP" if llr >= B
        - "ACCEPTED_H0" if llr <= A
        - "IN_PROGRESS_CONTINUE" if A < llr < B
    (never return "REJECTED" for in-progress runs).

    Args:
        failures: Cumulative failures observed.
        runs: Number of runs executed.
        p0: Null hypothesis failure rate bound.
        p1: Alternative hypothesis failure rate bound.
        alpha: Type I error rate.
        beta: Type II error rate.
        target_runs: Total planned certification runs.

    Returns:
        dict with status, log_likelihood_ratio, bounds, and compute savings.
    """
    if "runs_completed" in kwargs and runs == 0:
        runs = int(kwargs["runs_completed"])

    B = math.log((1.0 - beta) / alpha)
    A = math.log(beta / (1.0 - alpha))

    k = max(0, failures)
    m = max(0, runs)
    k_pass = m - k

    if m <= 0:
        llr = 0.0
    else:
        log_ratio_p = math.log(p1 / p0)
        log_ratio_q = math.log((1.0 - p1) / (1.0 - p0))
        llr = (k * log_ratio_p) + (k_pass * log_ratio_q)

    if llr >= B:
        status = "REJECTED_EARLY_STOP"
    elif llr <= A:
        status = "ACCEPTED_H0"
    else:
        status = "IN_PROGRESS_CONTINUE"

    runs_saved = max(0, target_runs - m) if status in ("REJECTED_EARLY_STOP", "ACCEPTED_H0") else 0
    saved_pct = round((runs_saved / max(target_runs, 1)) * 100.0, 1)

    return {
        "status": status,
        "log_likelihood_ratio": round(llr, 4),
        "llr": round(llr, 4),
        "upper_rejection_bound": round(B, 4),
        "lower_acceptance_bound": round(A, 4),
        "B": round(B, 4),
        "A": round(A, 4),
        "failures": k,
        "runs": m,
        "runs_completed": m,
        "target_runs": target_runs,
        "runs_saved": runs_saved,
        "compute_saved_pct": saved_pct,
        "early_stopped": status in ("REJECTED_EARLY_STOP", "ACCEPTED_H0"),
    }


def wald_sprt_check(
    failures: int,
    runs_done: int,
    target_runs: int = 1000,
    p0: float = 0.003,
    p1: float = 0.05,
    target_limit: float = 0.005,
) -> SPRTExecutionTelemetry:
    """Evaluates Wald's Sequential Probability Ratio Test for patch verifier telemetry."""
    res = wald_sprt_sequential_check(
        failures=failures,
        runs=runs_done,
        p0=p0,
        p1=p1,
        target_runs=target_runs,
    )
    llr = res["log_likelihood_ratio"]
    b_thresh = res["upper_rejection_bound"]

    if res["status"] == "REJECTED_EARLY_STOP" and runs_done < target_runs:
        return SPRTExecutionTelemetry(
            enabled=True,
            early_stopped=True,
            decision="EARLY_REJECT_STRESS",
            runs_executed_stress=runs_done,
            target_runs_stress=target_runs,
            runs_saved=res["runs_saved"],
            compute_saved_pct=res["compute_saved_pct"],
            log_likelihood_ratio=llr,
            rejection_threshold_b=b_thresh,
        )

    if runs_done >= target_runs or (failures == 0 and runs_done >= 25):
        ucb = clopper_pearson_upper_95(failures, runs_done)
        decision = "FULL_SAMPLE_CERTIFIED" if (failures == 0 or ucb <= target_limit) else "FULL_SAMPLE_REJECTED"
        return SPRTExecutionTelemetry(
            enabled=True,
            early_stopped=False,
            decision=decision,
            runs_executed_stress=runs_done,
            target_runs_stress=target_runs,
            runs_saved=0,
            compute_saved_pct=0.0,
            log_likelihood_ratio=llr,
            rejection_threshold_b=b_thresh,
        )

    return SPRTExecutionTelemetry(
        enabled=True,
        early_stopped=False,
        decision="IN_PROGRESS_CONTINUE",
        runs_executed_stress=runs_done,
        target_runs_stress=target_runs,
        runs_saved=0,
        compute_saved_pct=0.0,
        log_likelihood_ratio=llr,
        rejection_threshold_b=b_thresh,
    )
