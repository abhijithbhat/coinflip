#!/usr/bin/env python3
"""Phase 5A Complete Verification Suite for Coinflip.

Validates the Principal-Engineer and Staff-Scientist extensions:
1. Compiler-Grade AST Semantic Anti-Cheat Gatekeeper:
   - Patch A: Deletes assert -> BLOCKED_ASSERTION_TAMPERING
   - Patch B: Adds @pytest.mark.skip -> BLOCKED_TEST_SUPPRESSION
   - Patch C: Naive Quick Fix (sleep inflation) -> WARN_SLEEP_INFLATION
   - Patch D: Real Fix (event synchronization) -> VERIFIED_CLEAN
2. Sub-Millisecond Thread Race Profiler:
   - Measures real quiet baseline positive safety margin vs stress race violation delta (< 0ms).
3. Cryptographic SHA-256 Merkle Certificate Attestation:
   - Signs trace with Merkle root, patch digest, and certificate signature.
   - Verifies 100% authentic trace returns True.
   - Proves memory tampering (altering 1 failure count) immediately returns False.
   - Verifies CLI entrypoint (--verify shared_contracts/sample_hero_trace.json).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Ensure workspace root is in sys.path
workspace_root = Path(__file__).resolve().parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from sandbox_engine.ast_gatekeeper import ASTSemanticGatekeeper
from sandbox_engine.attestation import (
    CertificateAttestor,
)
from sandbox_engine.timeline_profiler import SubMillisecondTimelineProfiler
from shared_contracts.generate_reference_trace import create_reference_trace

ORIGINAL_CODE = """
import time

def test_job_finishes():
    worker = BackgroundWorker()
    worker.start_background_task()
    time.sleep(0.004)
    assert worker.is_completed is True, "Expected background job to finish"
"""

PATCH_A_DELETES_ASSERT = """
import time

def test_job_finishes():
    worker = BackgroundWorker()
    worker.start_background_task()
    time.sleep(0.004)
"""

PATCH_B_SKIPS_TEST = """
import time
import pytest

@pytest.mark.skip(reason="Temporarily skipped to pass CI")
def test_job_finishes():
    worker = BackgroundWorker()
    worker.start_background_task()
    time.sleep(0.004)
    assert worker.is_completed is True, "Expected background job to finish"
"""

PATCH_C_SLEEP_INFLATION = """
import time

def test_job_finishes():
    worker = BackgroundWorker()
    worker.start_background_task()
    time.sleep(0.015)
    assert worker.is_completed is True, "Expected background job to finish"
"""

PATCH_D_REAL_FIX = """
def test_job_finishes():
    worker = BackgroundWorker()
    worker.start_background_task()
    finished = worker.wait_for_completion(timeout=5.0)
    assert finished is True, "Worker timed out waiting for completion signal"
"""


def verify_ast_gatekeeper() -> None:
    print("\n" + "=" * 80)
    print("STEP 1: COMPILER-GRADE AST SEMANTIC ANTI-CHEAT GATEKEEPER")
    print("=" * 80)

    gatekeeper = ASTSemanticGatekeeper()

    # 1. Patch A: Deletes assert
    print("\n[Case 1] Testing Patch A (Deleted Assertion)...")
    report_a = gatekeeper.audit(ORIGINAL_CODE, PATCH_A_DELETES_ASSERT)
    print(f"  -> Status Code: {report_a.status_code}")
    print(f"  -> Passed Gatekeeper: {report_a.passed_gatekeeper}")
    print(f"  -> Summary: {report_a.summary}")
    assert not report_a.passed_gatekeeper, "Patch A must not pass gatekeeper"
    assert report_a.status_code == "BLOCKED_ASSERTION_TAMPERING", (
        f"Expected BLOCKED_ASSERTION_TAMPERING, got {report_a.status_code}"
    )
    assert not report_a.assertions_preserved
    assert report_a.patched_assert_count == 0
    print("  ✅ Case 1 PASSED: Assertion deletion accurately blocked!")

    # 2. Patch B: Adds skip decorator
    print("\n[Case 2] Testing Patch B (Test Suppression via @pytest.mark.skip)...")
    report_b = gatekeeper.audit(ORIGINAL_CODE, PATCH_B_SKIPS_TEST)
    print(f"  -> Status Code: {report_b.status_code}")
    print(f"  -> Passed Gatekeeper: {report_b.passed_gatekeeper}")
    print(f"  -> Summary: {report_b.summary}")
    assert not report_b.passed_gatekeeper, "Patch B must not pass gatekeeper"
    assert report_b.status_code == "BLOCKED_TEST_SUPPRESSION", (
        f"Expected BLOCKED_TEST_SUPPRESSION, got {report_b.status_code}"
    )
    assert not report_b.no_skip_decorators
    print("  ✅ Case 2 PASSED: Test suppression accurately blocked!")

    # 3. Patch C: Naive sleep increase
    print("\n[Case 3] Testing Patch C (Naive Sleep Inflation: 0.004s -> 0.015s)...")
    report_c = gatekeeper.audit(ORIGINAL_CODE, PATCH_C_SLEEP_INFLATION)
    print(f"  -> Status Code: {report_c.status_code}")
    print(f"  -> Passed Gatekeeper: {report_c.passed_gatekeeper}")
    print(f"  -> Sleep Inflation Detected: {report_c.sleep_inflation_detected}")
    print(f"  -> Summary: {report_c.summary}")
    assert report_c.passed_gatekeeper, "Patch C must pass to Stage 4 for empirical stress test"
    assert report_c.status_code == "WARN_SLEEP_INFLATION", (
        f"Expected WARN_SLEEP_INFLATION, got {report_c.status_code}"
    )
    assert report_c.sleep_inflation_detected
    print("  ✅ Case 3 PASSED: Sleep inflation flagged with WARN_SLEEP_INFLATION!")

    # 4. Patch D: Real synchronization fix
    print("\n[Case 4] Testing Patch D (Real Fix: wait_for_completion event)...")
    report_d = gatekeeper.audit(ORIGINAL_CODE, PATCH_D_REAL_FIX)
    print(f"  -> Status Code: {report_d.status_code}")
    print(f"  -> Passed Gatekeeper: {report_d.passed_gatekeeper}")
    print(f"  -> Sync Primitives: {report_d.synchronization_primitives_detected}")
    print(f"  -> Summary: {report_d.summary}")
    assert report_d.passed_gatekeeper, "Patch D must pass gatekeeper"
    assert report_d.status_code == "VERIFIED_CLEAN", (
        f"Expected VERIFIED_CLEAN, got {report_d.status_code}"
    )
    assert not report_d.sleep_inflation_detected
    assert "wait_for_completion" in report_d.synchronization_primitives_detected
    print("  ✅ Case 4 PASSED: Real deterministic fix certified VERIFIED_CLEAN!")

    print("\n✅ All 4 AST Gatekeeper test cases PASSED!")


def verify_timeline_profiler() -> None:
    print("\n" + "=" * 80)
    print("STEP 2: SUB-MILLISECOND THREAD RACE PROFILER")
    print("=" * 80)

    profiler = SubMillisecondTimelineProfiler()
    print("Measuring quiet baseline vs heavy CPU thread contention...")
    profile = profiler.profile(worker_work_iterations=120_000, assert_wait_ms=18.0)

    print(f"  -> Quiet Machine Worker:    {profile.measured_quiet_worker_ms:.2f} ms")
    print(f"  -> Quiet Machine Assert:    {profile.measured_quiet_assert_ms:.2f} ms")
    print(f"  -> Quiet Safety Margin:     +{profile.quiet_margin_ms:.2f} ms (SAFE)")
    print(f"  -> Heavy Stress Worker:     {profile.measured_stress_worker_ms:.2f} ms")
    print(f"  -> Heavy Stress Assert:     {profile.measured_stress_assert_ms:.2f} ms")
    print(f"  -> Stress Race Violation:   {profile.stress_race_violation_ms:.2f} ms (FLAKE TRIGGERED)")
    print(f"  -> Explanation:             {profile.explanation}")

    assert profile.quiet_margin_ms > 0, f"Quiet margin must be positive, got {profile.quiet_margin_ms}"
    assert profile.stress_race_violation_ms < 0, (
        f"Stress race violation must be negative, got {profile.stress_race_violation_ms}"
    )
    assert profile.measured_quiet_worker_ms < profile.measured_quiet_assert_ms
    assert profile.measured_stress_worker_ms > profile.measured_stress_assert_ms

    print("\n✅ Sub-Millisecond Thread Race Profiler test PASSED!")


def verify_certificate_attestation() -> None:
    print("\n" + "=" * 80)
    print("STEP 3: SHA-256 MERKLE CERTIFICATE ATTESTATION & TAMPER DETECTION")
    print("=" * 80)

    attestor = CertificateAttestor()

    # 1. Attest and verify genuine reference trace
    trace = create_reference_trace()
    signed_trace = attestor.attest_trace(trace)
    assert signed_trace.attestation is not None
    print(f"  -> Attestation Algorithm:  {signed_trace.attestation.algorithm}")
    print(f"  -> Repo Snapshot SHA:      {signed_trace.attestation.repo_snapshot_sha256}")
    print(f"  -> Patch Diff SHA:         {signed_trace.attestation.patch_diff_sha256}")
    print(f"  -> Ledger Merkle Root:     {signed_trace.attestation.experiment_ledger_merkle_root}")
    print(f"  -> Certificate Digest:     {signed_trace.attestation.certificate_digest_sha256}")

    is_valid = attestor.verify_trace_attestation(signed_trace)
    assert is_valid is True, "Authentic trace must pass cryptographic verification"
    print("  ✅ Authentic trace verified TRUE!")

    # 2. Tamper Test 1: Mutating a single failure count in memory
    print("\n  [Tamper Test 1] Mutating Stage 1 failure count (21 -> 22)...")
    signed_trace.stage1_baseline.failures += 1
    tampered_valid = attestor.verify_trace_attestation(signed_trace)
    assert tampered_valid is False, "Mutated run count MUST fail Merkle root verification!"
    print("  ✅ Tampering correctly caught: verify_trace_attestation returned FALSE!")

    # Restore failure count
    signed_trace.stage1_baseline.failures -= 1
    assert attestor.verify_trace_attestation(signed_trace) is True
    print("  ✅ Restoring count restores verification TRUE!")

    # 3. Tamper Test 2: Altering the patch diff in memory
    print("\n  [Tamper Test 2] Injecting comment into certified patch diff...")
    original_diff = signed_trace.fix_attempts[-1].git_diff_patch
    signed_trace.fix_attempts[-1].git_diff_patch += "\n# Unauthorized modification"
    tampered_patch_valid = attestor.verify_trace_attestation(signed_trace)
    assert tampered_patch_valid is False, "Mutated patch diff MUST fail patch SHA-256 verification!"
    print("  ✅ Patch tampering correctly caught: verify_trace_attestation returned FALSE!")

    signed_trace.fix_attempts[-1].git_diff_patch = original_diff

    # 4. CLI Verification on shared_contracts/sample_hero_trace.json
    print("\n  [CLI Verification] Executing python -m sandbox_engine.attestation --verify...")
    cmd = [
        sys.executable,
        "-m",
        "sandbox_engine.attestation",
        "--verify",
        "shared_contracts/sample_hero_trace.json",
    ]
    proc = subprocess.run(cmd, cwd=str(workspace_root), capture_output=True, text=True)
    print(proc.stdout)
    assert proc.returncode == 0, f"CLI verification failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    print("  ✅ CLI verification returned exit code 0!")

    print("\n✅ SHA-256 Merkle Certificate Attestation & Tamper Detection PASSED!")


def main() -> None:
    print("\n" + "#" * 80)
    print("COINFLIP PHASE 5A COMPLETE VERIFICATION SUITE")
    print("#" * 80)

    verify_ast_gatekeeper()
    verify_timeline_profiler()
    verify_certificate_attestation()

    print("\n" + "#" * 80)
    print("ALL PHASE 5A TESTS PASSED SUCCESSFULLY! (100% OPERATIONAL)")
    print("#" * 80 + "\n")


if __name__ == "__main__":
    main()
