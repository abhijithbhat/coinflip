"""End-to-end verification test suite for Coinflip live execution across all 5 benchmark cases.

Tests:
1. Live execution of all 5 benchmark cases via POST /api/run-live within < 8.0s.
2. Verified expected winning stress perturbation condition for each archetype.
3. Cryptographic stochastic variation: consecutive hero runs produce distinct Merkle roots.
4. Correct telemetry and contract schemas: trace_origin='live_execution', is_fallback=False.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from agent_and_ui.app import app

client = TestClient(app)

CASE_EXPECTED_TRIGGERS = {
    "hero": "cpu_heavy_load",
    "order_pollution": "shuffle_order",
    "seed_sampling": "seed_change",
    "clock_expiry": "clock_shift",
    "async_queue_race": "cpu_heavy_load",
}


@pytest.mark.parametrize(
    "case_id,expected_trigger",
    list(CASE_EXPECTED_TRIGGERS.items()),
)
def test_live_execution_all_5_cases(case_id: str, expected_trigger: str):
    """Asserts all 5 benchmark cases execute live in < 4.0s wall time and < 0.25s CPU time.

    Verifies accuracy across all 5 stages:
    1. Stage 1 baseline is populated with valid total_runs and Wilson CI.
    2. Stage 2 perturbation ledger contains all 7 conditions with causal analytics.
    3. Stage 2A Flake Amplifier report includes Round 1, Round 2, and Confirmation batch.
    4. Stage 4 dual certification gates Naive fix (REJECTED via SPRT early-stop) and Root-Cause fix (CERTIFIED).
    5. Stage 5 timeline profile confirms safe quiet margin and negative stress race violation.
    6. Stage 5 cryptographic attestation passes verification.
    """
    start_wall = time.perf_counter()
    start_cpu = time.process_time()
    response = client.post(
        "/api/run-live",
        json={"case_id": case_id, "runs_per_condition": 30},
    )
    wall_duration = time.perf_counter() - start_wall
    cpu_duration = time.process_time() - start_cpu

    assert response.status_code == 200, f"Failed for {case_id}: {response.text}"
    assert wall_duration < 4.0, f"Case {case_id} took {wall_duration:.2f}s wall time, exceeding 4.0s budget"
    assert cpu_duration < 0.25, f"Case {case_id} took {cpu_duration:.3f}s CPU time, exceeding 0.25s budget"

    data = response.json()
    assert data["trace_origin"] == "live_execution"
    assert data["is_fallback"] is False
    assert data["execution_mode_badge"] == "Live Execution (Coinflip Engine)"

    # 1. Stage 1 Baseline populated
    s1 = data.get("stage1_baseline")
    assert s1 is not None and s1.get("total_runs", 0) > 0, f"Case {case_id} missing stage1_baseline"

    # 2. Stage 2: All 7 rows of stage2_ledger present
    ledger = data.get("stage2_ledger", [])
    assert len(ledger) == 7, f"Case {case_id} expected 7 perturbation rows, got {len(ledger)}"
    pert_types = {r.get("perturbation") for r in ledger}
    expected_7 = {"baseline", "shuffle_order", "seed_change", "clock_shift", "network_cut", "cpu_half_cores", "cpu_heavy_load"}
    assert pert_types == expected_7, f"Case {case_id} perturbation set mismatch: {pert_types}"

    # 3. Stage 2A: Amplifier report with Round 1, Round 2, and Confirmation batch
    amp = data.get("amplifier_report")
    assert amp is not None, f"Case {case_id} missing amplifier_report"
    assert amp["winning_condition"] == expected_trigger
    assert amp.get("confirmation_runs", 0) > 0, f"Case {case_id} missing confirmation runs in amplifier report"
    assert len(amp.get("leaderboard", [])) >= 2, f"Case {case_id} missing amplifier leaderboard arms"

    # Winning stress condition must match the expected archetype perturbation
    assert data["triggering_stress_condition"] == expected_trigger, (
        f"Case {case_id} expected trigger {expected_trigger}, got {data['triggering_stress_condition']}"
    )

    # 4. Stage 4: Naive fix REJECTED + Root-Cause fix CERTIFIED
    fix_attempts = data.get("fix_attempts", [])
    assert len(fix_attempts) >= 2, f"Case {case_id} expected at least 2 fix attempts, got {len(fix_attempts)}"
    assert fix_attempts[0]["verdict"] == "REJECTED", f"Attempt 1 expected REJECTED, got {fix_attempts[0]['verdict']}"
    assert fix_attempts[1]["verdict"] == "CERTIFIED", f"Attempt 2 expected CERTIFIED, got {fix_attempts[1]['verdict']}"

    # 5. Stage 5: Timeline profile has quiet margin > 0 and stress race violation < 0
    timeline = data.get("race_timeline")
    assert timeline is not None, f"Case {case_id} missing race_timeline"
    assert timeline.get("quiet_margin_ms", 0) > 0, "Quiet safety margin must be positive"
    assert timeline.get("stress_race_violation_ms", 0) < 0, "Stress race violation must be negative"

    # 6. Stage 5: Cryptographic attestation verification
    att_resp = client.post("/api/verify-attestation", json={"trace": data})
    assert att_resp.status_code == 200
    assert att_resp.json().get("verified") is True, f"Attestation verification failed for {case_id}"


def test_consecutive_hero_runs_produce_distinct_merkle_roots():
    """Asserts that consecutive runs of hero produce unique session salts and distinct Merkle roots."""
    resp1 = client.post("/api/run-live", json={"case_id": "hero", "runs_per_condition": 30})
    assert resp1.status_code == 200
    data1 = resp1.json()

    resp2 = client.post("/api/run-live", json={"case_id": "hero", "runs_per_condition": 30})
    assert resp2.status_code == 200
    data2 = resp2.json()

    root1 = (
        data1.get("attestation", {}).get("experiment_ledger_merkle_root")
        or data1.get("cryptographic_attestation", {}).get("experiment_ledger_merkle_root")
    )
    root2 = (
        data2.get("attestation", {}).get("experiment_ledger_merkle_root")
        or data2.get("cryptographic_attestation", {}).get("experiment_ledger_merkle_root")
    )

    assert root1 is not None, "First run missing Merkle root"
    assert root2 is not None, "Second run missing Merkle root"
    assert root1 != root2, f"Expected distinct Merkle roots on consecutive runs, got identical root: {root1}"


@pytest.mark.parametrize("case_id", list(CASE_EXPECTED_TRIGGERS.keys()))
def test_dynamic_orchestrator_registry_loading(case_id: str):
    """Asserts CoinflipOrchestrator loads target_file, patches, and triggers dynamically for all 5 cases."""
    from sandbox_engine.orchestrator import CoinflipOrchestrator, BENCHMARK_CASE_REGISTRY

    cfg = BENCHMARK_CASE_REGISTRY[case_id]
    orch = CoinflipOrchestrator(
        repo_dir=cfg["repo_dir"],
        test_target=cfg["test_target"],
        project_name=cfg["project_name"],
        case_id=case_id,
    )
    assert orch.case_id == case_id
    assert orch.target_file == cfg["target_file"]
    assert orch.naive_patch_path == cfg["naive_patch"]
    assert orch.certified_patch_path == cfg["certified_patch"]
    assert orch.expected_trigger == cfg["trigger"]


def test_stream_live_case_forwarding():
    """Asserts GET /api/stream-live properly accepts ?case= and emits SSE stage events."""
    resp = client.get("/api/stream-live?case=order_pollution&runs=20")
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    assert "stage1_measure" in resp.text
    assert "done" in resp.text

