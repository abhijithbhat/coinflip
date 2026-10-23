"""Unit tests for /agent_and_ui/stats_engine.py."""

import pytest
from agent_and_ui.stats_engine import (
    wilson_ci_95,
    clopper_pearson_upper_95,
    upper_confidence_bound_95,
    exact_binomial_upper_bound_95,
    evaluate_fix_verdict,
    generate_streak_curve_data,
    fishers_exact_p_value,
    holm_bonferroni_adjust,
    relative_risk_and_effect,
    wald_sprt_sequential_check,
    enrich_trace_with_advanced_analytics,
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
    """Exact Clopper-Pearson upper bound for k=0 matches Rule of Three asymptotically."""
    assert upper_confidence_bound_95(0, 1000) == 0.0030
    assert upper_confidence_bound_95(0, 300) == 0.0099
    assert upper_confidence_bound_95(0, 100) == 0.0295
    assert upper_confidence_bound_95(0, 3000) == 0.0010


def test_exact_binomial_upper_bound_95():
    """Exact binomial bound for 0/1000 is 1 - 0.05^(1/1000) ~= 0.0030."""
    assert exact_binomial_upper_bound_95(1000) == 0.0030
    assert exact_binomial_upper_bound_95(0, 1000) == 0.0030


def test_upper_confidence_bound_95_nonzero_failures():
    """When failures > 0, computes exact Clopper-Pearson 95% upper bound."""
    bound = upper_confidence_bound_95(61, 1000)  # 61 failures in 1000 runs
    assert bound == pytest.approx(0.0749, abs=1e-3)
    assert exact_binomial_upper_bound_95(61, 1000) == pytest.approx(0.0749, abs=1e-3)
    assert clopper_pearson_upper_95(61, 1000) == pytest.approx(0.0749, abs=1e-3)


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


# -------------------------------------------------------------------------------
# Phase 5: Fisher's Exact Test
# -------------------------------------------------------------------------------


class TestFishersExactPValue:
    def test_significant_perturbation(self):
        """cpu_heavy_load 28/30 vs baseline 3/30 should yield tiny p-value."""
        p = fishers_exact_p_value(28, 30, 3, 30)
        assert p < 0.001

    def test_equal_rates_returns_1(self):
        """Same failure rate should yield p=1.0."""
        p = fishers_exact_p_value(5, 100, 5, 100)
        assert p == 1.0

    def test_zero_perturbation_failures_returns_1(self):
        p = fishers_exact_p_value(0, 100, 10, 100)
        assert p == 1.0

    def test_zero_baseline_with_pert_failures(self):
        p = fishers_exact_p_value(21, 300, 0, 300)
        assert p < 0.01

    def test_non_triggering_noise_perturbation(self):
        """22/300 vs 21/300 should yield p > 0.40 (not significant noise)."""
        p = fishers_exact_p_value(22, 300, 21, 300)
        assert p > 0.40
        assert p == pytest.approx(0.5000, abs=1e-2)

    def test_edge_case_zero_runs(self):
        p = fishers_exact_p_value(5, 100, 0, 0)
        assert p == 1.0


# -------------------------------------------------------------------------------
# Phase 5: Relative Risk & Effect
# -------------------------------------------------------------------------------


class TestRelativeRiskAndEffect:
    def test_haldane_correction_with_zero_baseline(self):
        result = relative_risk_and_effect(21, 300, 0, 300)
        assert result["relative_risk"] > 1.0
        assert result["rate_delta"] > 0
        assert result["p_value"] < 0.01
        assert result["is_statistically_significant"] is True

    def test_equal_rates_not_significant(self):
        result = relative_risk_and_effect(5, 100, 5, 100)
        assert result["is_statistically_significant"] is False
        assert result["rate_delta"] == 0.0

    def test_high_pert_rate_significant(self):
        result = relative_risk_and_effect(28, 30, 3, 30)
        assert result["relative_risk"] >= 1.8
        assert result["is_statistically_significant"] is True

    def test_returns_all_expected_keys(self):
        result = relative_risk_and_effect(20, 100, 10, 100)
        assert "relative_risk" in result
        assert "rate_delta" in result
        assert "p_value" in result
        assert "is_statistically_significant" in result


# -------------------------------------------------------------------------------
# Phase 5: Holm-Bonferroni Adjustment
# -------------------------------------------------------------------------------


class TestHolmBonferroniAdjust:
    def test_holm_bonferroni_adjustment(self):
        p_vals = [0.001, 0.04, 0.02]
        adj = holm_bonferroni_adjust(p_vals)
        assert len(adj) == 3
        assert adj[0] == pytest.approx(0.003, abs=1e-4)
        assert adj[1] == pytest.approx(0.04, abs=1e-4)
        assert adj[2] == pytest.approx(0.04, abs=1e-4)

    def test_empty_p_values(self):
        assert holm_bonferroni_adjust([]) == []

    def test_significance_only_when_p_under_001_and_rr_above_18(self):
        # adj_p < 0.01 and RR >= 1.8 -> True
        res_sig = relative_risk_and_effect(28, 30, 3, 30, holm_adjusted_p_value=0.005)
        assert res_sig["is_statistically_significant"] is True

        # adj_p < 0.01 but RR < 1.8 -> False
        res_low_rr = relative_risk_and_effect(10, 100, 9, 100, holm_adjusted_p_value=0.001)
        assert res_low_rr["is_statistically_significant"] is False

        # RR >= 1.8 but adj_p >= 0.01 -> False
        res_high_p = relative_risk_and_effect(2, 30, 0, 30, holm_adjusted_p_value=0.05)
        assert res_high_p["is_statistically_significant"] is False


# -------------------------------------------------------------------------------
# Phase 5: Wald SPRT Sequential Check
# -------------------------------------------------------------------------------


class TestWaldSprtSequentialCheck:
    def test_early_reject_with_many_failures(self):
        result = wald_sprt_sequential_check(failures=10, runs=50, target_runs=1000)
        assert result["status"] == "REJECTED_EARLY_STOP"
        assert result["runs_saved"] > 0
        assert result["compute_saved_pct"] > 0

    def test_accepted_h0_zero_failures_many_runs(self):
        result = wald_sprt_sequential_check(failures=0, runs=1000, target_runs=1000)
        assert result["status"] == "ACCEPTED_H0"
        assert result["early_stopped"] is True

    def test_continue_status_early_in_run(self):
        result = wald_sprt_sequential_check(failures=0, runs=10, target_runs=1000)
        assert result["status"] == "IN_PROGRESS_CONTINUE"
        assert result["early_stopped"] is False

    def test_in_progress_continue_never_rejected_between_a_and_b(self):
        result = wald_sprt_sequential_check(failures=1, runs=50, target_runs=1000)
        assert result["status"] == "IN_PROGRESS_CONTINUE"

    def test_zero_runs_returns_in_progress_continue(self):
        result = wald_sprt_sequential_check(failures=0, runs=0, target_runs=1000)
        assert result["status"] == "IN_PROGRESS_CONTINUE"
        assert result["runs_completed"] == 0

    def test_returns_all_expected_keys(self):
        result = wald_sprt_sequential_check(failures=1, runs=100, target_runs=1000)
        expected_keys = {
            "status", "log_likelihood_ratio", "upper_rejection_bound",
            "lower_acceptance_bound", "runs_completed", "target_runs",
            "runs_saved", "compute_saved_pct", "early_stopped",
        }
        assert expected_keys.issubset(set(result.keys()))


# -------------------------------------------------------------------------------
# Phase 5: enrich_trace_with_advanced_analytics
# -------------------------------------------------------------------------------


class TestEnrichTraceWithAdvancedAnalytics:
    def _sample_trace(self) -> dict:
        return {
            "trace_id": "test_trace_123",
            "timestamp_utc": "2026-10-17T12:00:00Z",
            "is_recorded_replay": True,
            "project_name": "test-project",
            "test_identifier": "test-project::test_worker.py",
            "stage1_baseline": {
                "perturbation": "baseline",
                "label": "Baseline",
                "total_runs": 300,
                "failures": 21,
                "passes": 279,
                "failure_rate": 0.07,
                "ci_95_lower": 0.0462,
                "ci_95_upper": 0.1046,
                "execution_backend": "local_isolated",
                "sample_failure_logs": [],
                "run_dots": [],
            },
            "stage2_ledger": [
                {
                    "perturbation": "baseline",
                    "label": "Baseline",
                    "total_runs": 30,
                    "failures": 3,
                    "passes": 27,
                    "failure_rate": 0.10,
                    "ci_95_lower": 0.035,
                    "ci_95_upper": 0.256,
                    "execution_backend": "local_isolated",
                    "sample_failure_logs": [],
                    "run_dots": [],
                },
                {
                    "perturbation": "cpu_heavy_load",
                    "label": "CPU Heavy Load",
                    "total_runs": 30,
                    "failures": 28,
                    "passes": 2,
                    "failure_rate": 0.933,
                    "ci_95_lower": 0.779,
                    "ci_95_upper": 0.984,
                    "execution_backend": "local_isolated",
                    "sample_failure_logs": [],
                    "run_dots": [],
                },
            ],
            "triggering_stress_condition": "cpu_heavy_load",
            "fix_attempts": [
                {
                    "attempt_number": 1,
                    "fix_title": "Quick Fix: Raise timeout",
                    "root_cause_diagnosis": "Increase sleep",
                    "git_diff_patch": "- time.sleep(0.009)\n+ time.sleep(0.050)",
                    "normal_cert_result": {
                        "perturbation": "baseline",
                        "label": "Normal Cert",
                        "total_runs": 1000,
                        "failures": 0,
                        "passes": 1000,
                        "failure_rate": 0.0,
                        "ci_95_lower": 0.0,
                        "ci_95_upper": 0.0038,
                        "execution_backend": "local_isolated",
                        "sample_failure_logs": [],
                        "run_dots": [],
                    },
                    "stress_cert_result": {
                        "perturbation": "cpu_heavy_load",
                        "label": "Stress Cert",
                        "total_runs": 1000,
                        "failures": 61,
                        "passes": 939,
                        "failure_rate": 0.061,
                        "ci_95_lower": 0.048,
                        "ci_95_upper": 0.077,
                        "execution_backend": "local_isolated",
                        "sample_failure_logs": [],
                        "run_dots": [],
                    },
                    "upper_bound_95_normal": 0.003,
                    "upper_bound_95_stress": 0.073,
                    "target_limit": 0.005,
                    "verdict": "REJECTED",
                    "rejection_reason": "Stress failures detected",
                },
                {
                    "attempt_number": 2,
                    "fix_title": "Coinflip Fix: Event sync",
                    "root_cause_diagnosis": "Replace sleep with wait_for_completion",
                    "git_diff_patch": "- time.sleep(0.009)\n+ worker.wait_for_completion()",
                    "normal_cert_result": {
                        "perturbation": "baseline",
                        "label": "Normal Cert",
                        "total_runs": 1000,
                        "failures": 0,
                        "passes": 1000,
                        "failure_rate": 0.0,
                        "ci_95_lower": 0.0,
                        "ci_95_upper": 0.003,
                        "execution_backend": "local_isolated",
                        "sample_failure_logs": [],
                        "run_dots": [],
                    },
                    "stress_cert_result": {
                        "perturbation": "cpu_heavy_load",
                        "label": "Stress Cert",
                        "total_runs": 1000,
                        "failures": 0,
                        "passes": 1000,
                        "failure_rate": 0.0,
                        "ci_95_lower": 0.0,
                        "ci_95_upper": 0.003,
                        "execution_backend": "local_isolated",
                        "sample_failure_logs": [],
                        "run_dots": [],
                    },
                    "upper_bound_95_normal": 0.003,
                    "upper_bound_95_stress": 0.003,
                    "target_limit": 0.005,
                    "verdict": "CERTIFIED",
                    "rejection_reason": None,
                },
            ],
            "final_verdict": "PASS",
            "models_used": {
                "bulk_log_reading": "nvidia/Nemotron-3_5-Lightning",
                "deep_reasoning": "nvidia/Nemotron-3-Ultra-550b-a55b",
            },
        }

    def test_adds_causal_analytics_to_ledger(self):
        trace = self._sample_trace()
        result = enrich_trace_with_advanced_analytics(trace)
        for row in result["stage2_ledger"]:
            assert "causal_analytics" in row
            ca = row["causal_analytics"]
            assert "relative_risk" in ca
            assert "p_value" in ca
            assert "is_statistically_significant" in ca

    def test_adds_ast_audit_to_fix_attempts(self):
        trace = self._sample_trace()
        result = enrich_trace_with_advanced_analytics(trace)
        for attempt in result["fix_attempts"]:
            assert "ast_audit" in attempt
            audit = attempt["ast_audit"]
            assert "status_code" in audit
            assert "passed_gatekeeper" in audit
            assert "synchronization_primitives_detected" in audit

    def test_adds_sprt_telemetry_to_fix_attempts(self):
        trace = self._sample_trace()
        result = enrich_trace_with_advanced_analytics(trace)
        for attempt in result["fix_attempts"]:
            assert "sprt_telemetry" in attempt
            sprt = attempt["sprt_telemetry"]
            assert "decision" in sprt
            assert "log_likelihood_ratio" in sprt

    def test_adds_race_timeline(self):
        trace = self._sample_trace()
        result = enrich_trace_with_advanced_analytics(trace)
        rt = result["race_timeline"]
        assert rt["quiet_margin_ms"] > 0
        assert rt["stress_race_violation_ms"] < 0

    def test_adds_cryptographic_attestation(self):
        trace = self._sample_trace()
        result = enrich_trace_with_advanced_analytics(trace)
        att = result["attestation"]
        assert att["algorithm"] == "SHA-256-Merkle"
        assert len(att["experiment_ledger_merkle_root"]) == 64
        assert len(att["patch_diff_sha256"]) == 64
        assert att["verified"] is True

    def test_adds_nemotron_reasoning_trace(self):
        trace = self._sample_trace()
        result = enrich_trace_with_advanced_analytics(trace)
        assert "nemotron_reasoning_trace" in result
        reasoning = result["nemotron_reasoning_trace"]
        assert "<reasoning>" in reasoning
        assert "cpu_heavy_load" in reasoning

    def test_adds_streak_curve_data(self):
        trace = self._sample_trace()
        result = enrich_trace_with_advanced_analytics(trace)
        assert "streak_curve_data" in result
        assert len(result["streak_curve_data"]) == 21

    def test_idempotent_enrichment(self):
        """Enriching twice should not crash or duplicate data."""
        trace = self._sample_trace()
        result1 = enrich_trace_with_advanced_analytics(trace)
        result2 = enrich_trace_with_advanced_analytics(result1)
        assert result2["attestation"]["algorithm"] == "SHA-256-Merkle"