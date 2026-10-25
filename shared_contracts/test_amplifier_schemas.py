"""Unit tests for Flake Amplifier Pydantic v2 schemas and trace integration."""

from shared_contracts import (
    AmplifierArmResult,
    BatchExperimentResult,
    CoinflipCertificateTrace,
    FlakeAmplifierReport,
    PerturbationIntensity,
    PerturbationType,
)


def test_perturbation_intensity_enum_values():
    assert PerturbationIntensity.L1_MILD.value == "L1_MILD"
    assert PerturbationIntensity.L2_MODERATE.value == "L2_MODERATE"
    assert PerturbationIntensity.L3_EXTREME.value == "L3_EXTREME"
    assert str(PerturbationIntensity.L1_MILD) == "PerturbationIntensity.L1_MILD" or PerturbationIntensity.L1_MILD == "L1_MILD"


def test_amplifier_arm_result_model():
    arm = AmplifierArmResult(
        arm_id="cpu_heavy_load:L3_EXTREME",
        perturbation=PerturbationType.CPU_HEAVY_LOAD,
        intensity=PerturbationIntensity.L3_EXTREME,
        nemotron_prior_rank=1,
        nemotron_rationale="Tight GIL thrashing maximizes thread-race exposure",
        round1_runs=10,
        round1_failures=4,
        round2_runs=20,
        round2_failures=12,
        total_exploration_runs=30,
        total_exploration_failures=16,
        exploration_failure_rate=0.5333,
        eliminated_in_round=None,
    )
    dumped = arm.model_dump()
    assert dumped["arm_id"] == "cpu_heavy_load:L3_EXTREME"
    assert dumped["perturbation"] == "cpu_heavy_load"
    assert dumped["intensity"] == "L3_EXTREME"
    assert dumped["round1_runs"] == 10
    assert dumped["round2_failures"] == 12
    assert dumped["eliminated_in_round"] is None

    reconstructed = AmplifierArmResult.model_validate(dumped)
    assert reconstructed == arm


def test_flake_amplifier_report_model():
    arm1 = AmplifierArmResult(
        arm_id="cpu_heavy_load:L3_EXTREME",
        perturbation=PerturbationType.CPU_HEAVY_LOAD,
        intensity=PerturbationIntensity.L3_EXTREME,
        nemotron_prior_rank=1,
        nemotron_rationale="GIL switch interval 1µs",
        total_exploration_runs=30,
        total_exploration_failures=18,
        exploration_failure_rate=0.60,
    )
    arm2 = AmplifierArmResult(
        arm_id="clock_shift:L2_MODERATE",
        perturbation=PerturbationType.CLOCK_SHIFT,
        intensity=PerturbationIntensity.L2_MODERATE,
        nemotron_prior_rank=2,
        nemotron_rationale="Offset +1hr",
        total_exploration_runs=10,
        total_exploration_failures=1,
        exploration_failure_rate=0.10,
        eliminated_in_round=1,
    )

    report = FlakeAmplifierReport(
        hypothesis_model="nvidia/nemotron-3-super-120b-a12b",
        hypothesis_completion_id="chatcmpl-amplifier-001",
        hypothesis_source="nemotron_live",
        ast_detected_signals=["threading.Thread", "time.sleep", "shared_state"],
        search_algorithm="successive_halving_thompson",
        exploration_budget=80,
        confirmation_budget=200,
        winning_arm_id="cpu_heavy_load:L3_EXTREME",
        winning_perturbation=PerturbationType.CPU_HEAVY_LOAD,
        winning_intensity=PerturbationIntensity.L3_EXTREME,
        baseline_failure_rate=0.0667,
        confirmation_runs=200,
        confirmation_failures=126,
        confirmed_failure_rate=0.63,
        confirmed_ci_95_lower=0.56,
        confirmed_ci_95_upper=0.70,
        amplification_factor=9.45,
        runs_to_first_failure=2,
        leaderboard=[arm1, arm2],
    )

    assert report.enabled is True
    assert report.hypothesis_source == "nemotron_live"
    assert report.search_algorithm == "successive_halving_thompson"
    assert len(report.leaderboard) == 2
    assert report.amplification_factor == 9.45

    serialized = report.model_dump_json()
    deserialized = FlakeAmplifierReport.model_validate_json(serialized)
    assert deserialized.winning_arm_id == "cpu_heavy_load:L3_EXTREME"
    assert deserialized.winning_intensity == PerturbationIntensity.L3_EXTREME


def test_batch_experiment_result_with_intensity():
    res = BatchExperimentResult(
        perturbation=PerturbationType.CPU_HEAVY_LOAD,
        label="CPU Heavy Load (Stress)",
        total_runs=30,
        failures=18,
        passes=12,
        failure_rate=0.6,
        ci_95_lower=0.42,
        ci_95_upper=0.76,
        execution_backend="local_isolated",
        intensity=PerturbationIntensity.L3_EXTREME,
    )
    assert res.intensity == PerturbationIntensity.L3_EXTREME
    dumped = res.model_dump()
    assert dumped["intensity"] == "L3_EXTREME"


def test_batch_experiment_result_default_intensity_none():
    res = BatchExperimentResult(
        perturbation=PerturbationType.BASELINE,
        label="Baseline Quiet",
        total_runs=30,
        failures=2,
        passes=28,
        failure_rate=0.0667,
        ci_95_lower=0.018,
        ci_95_upper=0.21,
        execution_backend="local_isolated",
    )
    assert res.intensity is None


def test_coinflip_certificate_trace_with_amplifier_report():
    report = FlakeAmplifierReport(
        hypothesis_model="nvidia/nemotron-3-super-120b-a12b",
        exploration_budget=80,
        confirmation_budget=100,
        winning_arm_id="cpu_heavy_load:L3_EXTREME",
        winning_perturbation=PerturbationType.CPU_HEAVY_LOAD,
        winning_intensity=PerturbationIntensity.L3_EXTREME,
        baseline_failure_rate=0.05,
        confirmation_runs=100,
        confirmation_failures=65,
        confirmed_failure_rate=0.65,
        confirmed_ci_95_lower=0.55,
        confirmed_ci_95_upper=0.74,
        amplification_factor=13.0,
    )

    baseline_res = BatchExperimentResult(
        perturbation=PerturbationType.BASELINE,
        label="Baseline",
        total_runs=30,
        failures=2,
        passes=28,
        failure_rate=0.0667,
        ci_95_lower=0.018,
        ci_95_upper=0.21,
        execution_backend="local_isolated",
    )

    trace = CoinflipCertificateTrace(
        trace_id="test-amplifier-trace",
        timestamp_utc="2026-10-24T15:00:00Z",
        is_recorded_replay=False,
        project_name="hero_worker_race",
        test_identifier="benchmarks/hero_worker_race/test_worker.py::test_worker_task_completes",
        stage1_baseline=baseline_res,
        stage2_ledger=[baseline_res],
        triggering_stress_condition=PerturbationType.CPU_HEAVY_LOAD,
        fix_attempts=[],
        final_verdict="PASS",
        models_used={"diagnosis": "nvidia/nemotron-3-super-120b-a12b"},
        amplifier_report=report,
    )

    assert trace.amplifier_report is not None
    assert trace.amplifier_report.amplification_factor == 13.0
    assert trace.amplifier_report.winning_intensity == PerturbationIntensity.L3_EXTREME
