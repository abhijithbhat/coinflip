#!/usr/bin/env python3
"""Generates the reference trace fixture for Coinflip.

Produces shared_contracts/sample_hero_trace.json and validates it against
the CoinflipCertificateTrace Pydantic model.
"""

from __future__ import annotations

import json
from pathlib import Path
import random
import sys

# Ensure workspace root is in sys.path
workspace_root = Path(__file__).resolve().parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from shared_contracts.schemas import (
    ASTGatekeeperReport,
    BatchExperimentResult,
    CandidateFixEvaluation,
    CoinflipCertificateTrace,
    PerturbationType,
    ThreadRaceTimelineProfile,
)


def _generate_dots(total: int, failures: int, seed: int = 42) -> list[bool]:
    """Generates a reproducible list of pass/fail booleans (True=Pass, False=Fail)."""
    rng = random.Random(seed)
    dots = [False] * failures + [True] * (total - failures)
    rng.shuffle(dots)
    return dots


def create_reference_trace() -> CoinflipCertificateTrace:
    sample_worker_failure_log = (
        "Traceback (most recent call last):\n"
        '  File "/app/tests/test_worker.py", line 42, in test_job_finishes\n'
        "    assert result.is_completed is True, 'Expected background job to finish'\n"
        "AssertionError: Expected background job to finish\n"
        "  Status: JobState.RUNNING (processed 84/100 items)\n"
    )

    stage1_baseline = BatchExperimentResult(
        perturbation=PerturbationType.BASELINE,
        label="Normal run (baseline quiet machine)",
        total_runs=300,
        failures=21,
        passes=279,
        failure_rate=0.07,
        ci_95_lower=0.046,
        ci_95_upper=0.105,
        execution_backend="local_isolated",
        sample_failure_logs=[sample_worker_failure_log],
        run_dots=_generate_dots(300, 21, seed=101),
    )

    stage2_ledger = [
        BatchExperimentResult(
            perturbation=PerturbationType.BASELINE,
            label="Normal run (baseline quiet machine)",
            total_runs=300,
            failures=21,
            passes=279,
            failure_rate=0.07,
            ci_95_lower=0.046,
            ci_95_upper=0.105,
            execution_backend="local_isolated",
            sample_failure_logs=[sample_worker_failure_log],
            run_dots=_generate_dots(300, 21, seed=101),
        ),
        BatchExperimentResult(
            perturbation=PerturbationType.SHUFFLE_ORDER,
            label="Randomized test execution order",
            total_runs=300,
            failures=21,
            passes=279,
            failure_rate=0.07,
            ci_95_lower=0.046,
            ci_95_upper=0.105,
            execution_backend="local_isolated",
            sample_failure_logs=[sample_worker_failure_log],
            run_dots=_generate_dots(300, 21, seed=102),
        ),
        BatchExperimentResult(
            perturbation=PerturbationType.SEED_CHANGE,
            label="Alternative random & hash seeds",
            total_runs=300,
            failures=18,
            passes=282,
            failure_rate=0.06,
            ci_95_lower=0.038,
            ci_95_upper=0.093,
            execution_backend="local_isolated",
            sample_failure_logs=[sample_worker_failure_log],
            run_dots=_generate_dots(300, 18, seed=103),
        ),
        BatchExperimentResult(
            perturbation=PerturbationType.CLOCK_SHIFT,
            label="Clock skew / timing offset drift",
            total_runs=300,
            failures=21,
            passes=279,
            failure_rate=0.07,
            ci_95_lower=0.046,
            ci_95_upper=0.105,
            execution_backend="local_isolated",
            sample_failure_logs=[sample_worker_failure_log],
            run_dots=_generate_dots(300, 21, seed=104),
        ),
        BatchExperimentResult(
            perturbation=PerturbationType.NETWORK_CUT,
            label="Simulated network isolation",
            total_runs=300,
            failures=21,
            passes=279,
            failure_rate=0.07,
            ci_95_lower=0.046,
            ci_95_upper=0.105,
            execution_backend="local_isolated",
            sample_failure_logs=[sample_worker_failure_log],
            run_dots=_generate_dots(300, 21, seed=105),
        ),
        BatchExperimentResult(
            perturbation=PerturbationType.CPU_HALF_CORES,
            label="Constrained CPU cores (core affinity halved)",
            total_runs=300,
            failures=93,
            passes=207,
            failure_rate=0.31,
            ci_95_lower=0.260,
            ci_95_upper=0.364,
            execution_backend="local_isolated",
            sample_failure_logs=[sample_worker_failure_log],
            run_dots=_generate_dots(300, 93, seed=106),
        ),
        BatchExperimentResult(
            perturbation=PerturbationType.CPU_HEAVY_LOAD,
            label="Heavy background CPU contention (4x load)",
            total_runs=300,
            failures=174,
            passes=126,
            failure_rate=0.58,
            ci_95_lower=0.523,
            ci_95_upper=0.635,
            execution_backend="local_isolated",
            sample_failure_logs=[sample_worker_failure_log],
            run_dots=_generate_dots(300, 174, seed=107),
        ),
    ]

    # Fix Attempt 1: The classic deceptive quick fix (fails under stress)
    quick_fix_diff = (
        "--- a/tests/test_worker.py\n"
        "+++ b/tests/test_worker.py\n"
        "@@ -15,3 +15,3 @@\n"
        "     worker.start_background_task()\n"
        "-    time.sleep(1.0)\n"
        "+    time.sleep(2.0)\n"
        "     assert worker.is_completed is True\n"
    )

    fix_attempt_1 = CandidateFixEvaluation(
        attempt_number=1,
        fix_title="Quick Fix: Raise wait(1s) to wait(2s)",
        root_cause_diagnosis=(
            "Naive fix: Worker occasionally requires slightly longer than 1 second on loaded runners. "
            "Increasing static sleep to 2 seconds reduces failure probability on quiet machines but does not eliminate the race condition."
        ),
        git_diff_patch=quick_fix_diff,
        normal_cert_result=BatchExperimentResult(
            perturbation=PerturbationType.BASELINE,
            label="1,000 Normal Verification Runs",
            total_runs=1000,
            failures=0,
            passes=1000,
            failure_rate=0.0,
            ci_95_lower=0.0,
            ci_95_upper=0.003,
            execution_backend="local_isolated",
            sample_failure_logs=[],
            run_dots=[True] * 1000,
        ),
        stress_cert_result=BatchExperimentResult(
            perturbation=PerturbationType.CPU_HEAVY_LOAD,
            label="1,000 Stress Verification Runs (CPU Heavy Load)",
            total_runs=1000,
            failures=61,
            passes=939,
            failure_rate=0.061,
            ci_95_lower=0.047,
            ci_95_upper=0.078,
            execution_backend="local_isolated",
            sample_failure_logs=[sample_worker_failure_log],
            run_dots=_generate_dots(1000, 61, seed=201),
        ),
        upper_bound_95_normal=0.003,
        upper_bound_95_stress=0.078,
        target_limit=0.005,
        verdict="REJECTED",
        rejection_reason=(
            "Stress test failure rate upper bound (7.80%) exceeds target threshold of 0.50% under CPU heavy load."
        ),
        ast_audit=ASTGatekeeperReport(
            passed_gatekeeper=True,
            status_code="WARN_SLEEP_INFLATION",
            original_assert_count=1,
            patched_assert_count=1,
            assertions_preserved=True,
            no_skip_decorators=True,
            no_bare_exception_swallowing=True,
            sleep_inflation_detected=True,
            synchronization_primitives_detected=[],
            summary=(
                "Warning: Sleep Inflation Detected. Candidate patch increased sleep duration from "
                "1.0000s to 2.0000s without adding deterministic synchronization. "
                "Allowed to proceed to Stage 4 Dual-Condition Gate for empirical stress verification."
            ),
        ),
    )

    # Fix Attempt 2: The Coinflip certified fix (event synchronization)
    coinflip_fix_diff = (
        "--- a/tests/test_worker.py\n"
        "+++ b/tests/test_worker.py\n"
        "@@ -14,4 +14,4 @@\n"
        "     worker = BackgroundWorker()\n"
        "     worker.start_background_task()\n"
        "-    time.sleep(1.0)\n"
        "-    assert worker.is_completed is True\n"
        "+    finished = worker.wait_for_completion(timeout_seconds=10.0)\n"
        "+    assert finished is True, 'Worker timed out waiting for event signal'\n"
    )

    fix_attempt_2 = CandidateFixEvaluation(
        attempt_number=2,
        fix_title="Coinflip Fix: Wait for worker completion event",
        root_cause_diagnosis=(
            "Root cause: The test checked the result before the background worker finished (a timing race condition exposed under CPU load). "
            "Replaced arbitrary time.sleep with deterministic threading.Event synchronization, removing the race condition entirely."
        ),
        git_diff_patch=coinflip_fix_diff,
        normal_cert_result=BatchExperimentResult(
            perturbation=PerturbationType.BASELINE,
            label="1,000 Normal Verification Runs",
            total_runs=1000,
            failures=0,
            passes=1000,
            failure_rate=0.0,
            ci_95_lower=0.0,
            ci_95_upper=0.003,
            execution_backend="local_isolated",
            sample_failure_logs=[],
            run_dots=[True] * 1000,
        ),
        stress_cert_result=BatchExperimentResult(
            perturbation=PerturbationType.CPU_HEAVY_LOAD,
            label="1,000 Stress Verification Runs (CPU Heavy Load)",
            total_runs=1000,
            failures=0,
            passes=1000,
            failure_rate=0.0,
            ci_95_lower=0.0,
            ci_95_upper=0.003,
            execution_backend="local_isolated",
            sample_failure_logs=[],
            run_dots=[True] * 1000,
        ),
        upper_bound_95_normal=0.003,
        upper_bound_95_stress=0.003,
        target_limit=0.005,
        verdict="CERTIFIED",
        rejection_reason=None,
        ast_audit=ASTGatekeeperReport(
            passed_gatekeeper=True,
            status_code="VERIFIED_CLEAN",
            original_assert_count=1,
            patched_assert_count=1,
            assertions_preserved=True,
            no_skip_decorators=True,
            no_bare_exception_swallowing=True,
            sleep_inflation_detected=False,
            synchronization_primitives_detected=["wait_for_completion"],
            summary="Verified Clean: All assertions preserved (1/1), no suppression detected, and deterministic synchronization verified [wait_for_completion].",
        ),
    )

    trace = CoinflipCertificateTrace(
        trace_id="reference-hero-trace-contract-v1-initial-schema-fixture",
        timestamp_utc="2026-10-16T12:00:00Z",
        is_recorded_replay=True,
        project_name="example-service",
        test_identifier="tests/test_worker.py::test_job_finishes",
        stage1_baseline=stage1_baseline,
        stage2_ledger=stage2_ledger,
        triggering_stress_condition=PerturbationType.CPU_HEAVY_LOAD,
        fix_attempts=[fix_attempt_1, fix_attempt_2],
        final_verdict="PASS",
        models_used={
            "bulk_log_reading": "nvidia/Nemotron-3_5-Lightning",
            "deep_reasoning": "nvidia/Nemotron-3-Ultra-550b-a55b",
        },
        race_timeline=ThreadRaceTimelineProfile(
            measured_quiet_worker_ms=11.42,
            measured_quiet_assert_ms=20.00,
            quiet_margin_ms=8.58,
            measured_stress_worker_ms=26.40,
            measured_stress_assert_ms=20.00,
            stress_race_violation_ms=-6.40,
            explanation=(
                "Quiet baseline displays a positive safety margin of +8.58ms "
                "(worker finishes in 11.42ms before assert fires at 20.00ms). "
                "Under CPU heavy load, thread contention delays worker completion to 26.40ms, "
                "producing a 6.40ms race violation (assert fires 6.40ms before background worker completes)."
            ),
        ),
    )

    from sandbox_engine.attestation import attest_trace
    return attest_trace(trace)


def main() -> None:
    output_path = Path(__file__).parent / "sample_hero_trace.json"
    trace = create_reference_trace()

    # Serialize to JSON with formatting
    trace_json = trace.model_dump_json(indent=2)
    output_path.write_text(trace_json, encoding="utf-8")
    print(f"Successfully generated {output_path} ({len(trace_json)} bytes)")

    # Validate that model_validate_json loads the file with zero errors
    loaded = CoinflipCertificateTrace.model_validate_json(output_path.read_text(encoding="utf-8"))
    assert loaded.final_verdict == "PASS"
    assert len(loaded.stage2_ledger) == 7
    assert len(loaded.fix_attempts) == 2
    print("Zero errors: CoinflipCertificateTrace.model_validate_json passed successfully!")


if __name__ == "__main__":
    main()
