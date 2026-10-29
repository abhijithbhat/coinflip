from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from sandbox_engine.amplifier import FlakeAmplifier
from sandbox_engine.attestation import CertificateAttestor
from sandbox_engine.llm_bridge import NemotronBridge, extract_ast_signals
from sandbox_engine.patch_verifier import Stage4PatchVerifier
from shared_contracts.schemas import (
    BatchExperimentResult,
    CandidateFixEvaluation,
    CoinflipCertificateTrace,
    FlakeAmplifierReport,
    PerturbationIntensity,
    PerturbationType,
)


def test_extract_ast_signals_threading_and_sleep() -> None:
    code = """
import threading
import time

def test_race():
    t = threading.Thread(target=lambda: time.sleep(0.01))
    t.start()
    time.sleep(0.005)
"""
    signals = extract_ast_signals(code)
    assert "imports:threading" in signals
    assert "calls:Thread.start" in signals
    assert "calls:time.sleep" in signals


def test_extract_ast_signals_random_and_time_and_socket() -> None:
    code = """
import random
import time
import socket
import asyncio

GLOBAL_REGISTRY = {}

def mutate():
    GLOBAL_REGISTRY["key"] = 123
    r = random.sample([1, 2, 3], 2)
    now = time.time()
    s = socket.socket()
"""
    signals = extract_ast_signals(code)
    assert "imports:random" in signals
    assert "calls:random.sample" in signals
    assert "calls:time.time" in signals
    assert "imports:socket" in signals
    assert "imports:asyncio" in signals
    assert "module_global_dict_mutation" in signals


def test_rank_amplification_hypotheses_ast_fallback_threading() -> None:
    bridge = NemotronBridge(api_key=None)
    code = """
import threading
import time

def test_race():
    t = threading.Thread(target=lambda: time.sleep(0.01))
    t.start()
    time.sleep(0.005)
"""
    res = bridge.rank_amplification_hypotheses(test_code=code, target_code="")
    assert res["hypothesis_source"] in ("nemotron_live", "ast_heuristic_fallback")
    assert len(res["ast_detected_signals"]) >= 2
    assert len(res["hypotheses"]) == 4

    top_arm = res["hypotheses"][0]
    assert top_arm["perturbation"] in [PerturbationType.CPU_HEAVY_LOAD, PerturbationType.CPU_HALF_CORES]
    assert top_arm["prior_rank"] == 1
    assert "rationale" in top_arm
    assert top_arm["intensity"] in [PerturbationIntensity.L2_MODERATE, PerturbationIntensity.L3_EXTREME]


def test_rank_amplification_hypotheses_ast_fallback_random() -> None:
    bridge = NemotronBridge(api_key=None)
    code = """
import random

def test_random_pick():
    assert random.choice([1, 2, 3]) == 1
"""
    res = bridge.rank_amplification_hypotheses(test_code=code)
    assert res["hypotheses"][0]["perturbation"] == PerturbationType.SEED_CHANGE
    assert res["hypotheses"][0]["intensity"] == PerturbationIntensity.L3_EXTREME


def test_rank_amplification_hypotheses_live_mock() -> None:
    bridge = NemotronBridge(api_key="mock_key")
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.id = "nebius_comp_hyp_12345"
    mock_resp.model = "nvidia/Nemotron-3_5-Lightning"
    mock_choice = MagicMock()
    mock_choice.message.content = """```json
[
  {"perturbation": "cpu_heavy_load", "intensity": "L3_EXTREME", "rationale": "High thread contention triggers the sleep race condition."},
  {"perturbation": "cpu_half_cores", "intensity": "L2_MODERATE", "rationale": "Reduced core count forces preemptive context switching."},
  {"perturbation": "clock_shift", "intensity": "L2_MODERATE", "rationale": "Altering clock drift disrupts sleep assertions."},
  {"perturbation": "shuffle_order", "intensity": "L1_MILD", "rationale": "Changing execution order exposes test pollution."}
]
```"""
    mock_resp.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_resp
    bridge.client = mock_client
    bridge._client = mock_client

    code = "import threading\nt = threading.Thread(target=None)\nt.start()"
    res = bridge.rank_amplification_hypotheses(test_code=code)

    assert res["hypothesis_source"] == "nemotron_live"
    assert res["completion_id"] == "nebius_comp_hyp_12345"
    assert bridge.models_used.get("hypothesis_prior") == "nvidia/Nemotron-3_5-Lightning"
    assert len(res["hypotheses"]) == 4
    assert res["hypotheses"][0]["perturbation"] == PerturbationType.CPU_HEAVY_LOAD
    assert res["hypotheses"][0]["intensity"] == PerturbationIntensity.L3_EXTREME


def test_flake_amplifier_search_fast_live_mode() -> None:
    async def _test() -> None:
        async def mock_run_batch(
            perturbation: PerturbationType,
            num_runs: int,
            intensity: PerturbationIntensity | None = None,
            seed_offset: int = 0,
        ) -> BatchExperimentResult:
            arm_id = f"{perturbation.value}:{intensity.value if intensity else 'default'}"
            if arm_id == "cpu_heavy_load:L3_EXTREME":
                failures = int(round(num_runs * 0.8))
            elif arm_id == "cpu_half_cores:L2_MODERATE":
                failures = int(round(num_runs * 0.3))
            else:
                failures = 0

            return BatchExperimentResult(
                perturbation=perturbation,
                intensity=intensity,
                label=arm_id,
                total_runs=num_runs,
                passes=num_runs - failures,
                failures=failures,
                failure_rate=failures / num_runs,
                ci_95_lower=0.0,
                ci_95_upper=1.0,
                run_dots=[False] * failures + [True] * (num_runs - failures),
                execution_backend="local_process_pool",
            )

        mock_runner = MagicMock()
        mock_runner.run_batch = AsyncMock(side_effect=mock_run_batch)

        hypotheses = {
            "hypothesis_source": "nemotron_live",
            "ast_detected_signals": ["imports:threading"],
            "hypotheses": [
                {
                    "perturbation": PerturbationType.CPU_HEAVY_LOAD,
                    "intensity": PerturbationIntensity.L3_EXTREME,
                    "prior_rank": 1,
                    "rationale": "Heavy load maximizes thread preemption.",
                },
                {
                    "perturbation": PerturbationType.CPU_HALF_CORES,
                    "intensity": PerturbationIntensity.L2_MODERATE,
                    "prior_rank": 2,
                    "rationale": "Half cores causes scheduling stalls.",
                },
                {
                    "perturbation": PerturbationType.CLOCK_SHIFT,
                    "intensity": PerturbationIntensity.L1_MILD,
                    "prior_rank": 3,
                    "rationale": "Clock shift checks timing drift.",
                },
                {
                    "perturbation": PerturbationType.SHUFFLE_ORDER,
                    "intensity": PerturbationIntensity.L1_MILD,
                    "prior_rank": 4,
                    "rationale": "Shuffle test order checks state leakage.",
                },
            ],
        }

        baseline = BatchExperimentResult(
            perturbation=PerturbationType.BASELINE,
            label="Baseline (No Perturbation)",
            total_runs=30,
            passes=27,
            failures=3,
            failure_rate=0.10,
            ci_95_lower=0.03,
            ci_95_upper=0.25,
            execution_backend="local_process_pool",
        )

        amplifier = FlakeAmplifier(
            batch_runner=mock_runner,
            workspace_dir=Path("/tmp"),
            test_target="tests/test_demo.py",
            baseline_result=baseline,
            hypotheses=hypotheses,
            fast_live_mode=True,  # 24 exploration, 20 confirmation
        )

        report, conf_batch = await amplifier.run()

        # Verify Report Invariants
        assert isinstance(report, FlakeAmplifierReport)
        assert report.winning_arm_id == "cpu_heavy_load:L3_EXTREME"
        assert report.winning_perturbation == PerturbationType.CPU_HEAVY_LOAD
        assert report.winning_intensity == PerturbationIntensity.L3_EXTREME
        assert report.total_exploration_runs == 60
        assert report.total_confirmation_runs == 40
        assert report.confirmation_runs == 40
        assert report.confirmation_failures == 32  # 80% of 40
        assert report.confirmed_failure_rate == 0.8
        assert report.amplification_factor == 8.0  # 0.8 / 0.10
        assert report.wilson_ci_95[0] > 0.5  # CI computed on confirmation batch
        assert report.runs_to_first_failure == 1

        # Check elimination tracking
        elim_r1 = [arm for arm in report.ranked_arms if arm.eliminated_in_round == 1]
        elim_r2 = [arm for arm in report.ranked_arms if arm.eliminated_in_round == 2]
        survivor = [arm for arm in report.ranked_arms if arm.eliminated_in_round is None]

        assert len(elim_r1) == 2
        assert len(elim_r2) == 1
        assert len(survivor) == 1
        assert survivor[0].arm_id == "cpu_heavy_load:L3_EXTREME"

        # Verify confirmation batch returned matches
        assert conf_batch is not None
        assert conf_batch.perturbation == PerturbationType.CPU_HEAVY_LOAD
        assert conf_batch.intensity == PerturbationIntensity.L3_EXTREME
        assert conf_batch.total_runs == 40
        assert conf_batch.failures == 32

    asyncio.run(_test())


def test_attestation_with_amplifier_report() -> None:
    baseline = BatchExperimentResult(
        perturbation=PerturbationType.BASELINE,
        label="Baseline",
        total_runs=20,
        passes=18,
        failures=2,
        failure_rate=0.10,
        ci_95_lower=0.02,
        ci_95_upper=0.30,
        execution_backend="local_process_pool",
    )
    amplifier_report = FlakeAmplifierReport(
        hypothesis_model="nvidia/Nemotron-3_5-Lightning",
        hypothesis_source="nemotron_live",
        exploration_budget=24,
        confirmation_budget=20,
        baseline_failure_rate=0.10,
        winning_arm_id="cpu_heavy_load:L3_EXTREME",
        winning_perturbation=PerturbationType.CPU_HEAVY_LOAD,
        winning_intensity=PerturbationIntensity.L3_EXTREME,
        confirmed_failure_rate=0.85,
        confirmed_ci_95_lower=0.70,
        confirmed_ci_95_upper=0.95,
        amplification_factor=8.5,
        runs_to_first_failure=1,
        confirmation_runs=20,
        confirmation_failures=17,
        leaderboard=[],
    )
    fix_attempt = CandidateFixEvaluation(
        attempt_number=1,
        fix_title="Deterministic Event Wait",
        root_cause_diagnosis="Race condition on sleep",
        git_diff_patch="+ event.wait()",
        upper_bound_95_normal=0.05,
        upper_bound_95_stress=0.05,
        verdict="CERTIFIED",
        sprt_decision="ACCEPT",
        normal_cert_result=baseline,
        stress_cert_result=baseline,
    )
    trace = CoinflipCertificateTrace(
        trace_id="test_amp_trace_123",
        timestamp_utc="2026-10-24T12:00:00Z",
        is_recorded_replay=False,
        project_name="amp-test",
        test_identifier="amp-test::test_race.py",
        stage1_baseline=baseline,
        stage2_ledger=[baseline],
        triggering_stress_condition=PerturbationType.CPU_HEAVY_LOAD,
        amplifier_report=amplifier_report,
        fix_attempts=[fix_attempt],
        final_verdict="PASS",
        models_used={"hypothesis_prior": "nvidia/Nemotron-3_5-Lightning"},
    )

    attestor = CertificateAttestor()
    attested_trace = attestor.attest_trace(trace)

    assert attested_trace.attestation is not None
    assert attestor.verify_trace_attestation(attested_trace) is True
    assert len(attested_trace.attestation.experiment_ledger_merkle_root) == 64


def test_stage4_patch_verifier_forwards_intensity() -> None:
    async def _test() -> None:
        mock_runner = MagicMock()
        batch_res = BatchExperimentResult(
            perturbation=PerturbationType.CPU_HEAVY_LOAD,
            intensity=PerturbationIntensity.L3_EXTREME,
            label="CPU Heavy Load",
            total_runs=10,
            passes=10,
            failures=0,
            failure_rate=0.0,
            ci_95_lower=0.0,
            ci_95_upper=0.3,
            execution_backend="local_process_pool",
        )
        mock_runner.run_batch = AsyncMock(return_value=batch_res)

        verifier = Stage4PatchVerifier(
            image_builder=MagicMock(),
            base_snapshot_id="snap_123",
            test_target="test_worker.py",
        )

        verifier.image_builder.create_isolated_snapshot = MagicMock(return_value=Path("/tmp"))

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("sandbox_engine.patch_verifier.SandboxBatchRunner", MagicMock(return_value=mock_runner))
            eval_res = await verifier.verify_patch(
                attempt_number=2,
                fix_title="Certified Fix",
                root_cause_diagnosis="Sync invariant",
                patch_content="def test_worker(): pass\n",
                triggering_stress_condition=PerturbationType.CPU_HEAVY_LOAD,
                triggering_intensity=PerturbationIntensity.L3_EXTREME,
                cert_runs=10,
                fast_live_mode=True,
            )

        stress_calls = [
            call for call in mock_runner.run_batch.call_args_list
            if (call.args and call.args[0] == PerturbationType.CPU_HEAVY_LOAD)
            or (call.kwargs.get("perturbation") == PerturbationType.CPU_HEAVY_LOAD)
        ]
        assert len(stress_calls) > 0
        assert stress_calls[0].kwargs.get("intensity") == PerturbationIntensity.L3_EXTREME
        assert eval_res.verdict == "CERTIFIED"

    asyncio.run(_test())
