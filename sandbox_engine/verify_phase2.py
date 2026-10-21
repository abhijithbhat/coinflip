#!/usr/bin/env python3
"""Phase 2 Verification Script for Coinflip.

Validates:
1. SandboxImageBuilder: Creation of immutable base snapshots and patched snapshots.
2. Stage4PatchVerifier: Evaluation of candidate patches against quiet vs stress conditions.
3. Page 9 Concept Brief reproduction:
   - Original Test: Broken / Flaky (fails under baseline, spikes under stress)
   - Quick Fix (raising sleep): Deceptively passes quiet (0.0%), rejected under stress (REJECTED)
   - Coinflip Real Fix (event synchronization): Certified under both conditions (CERTIFIED)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import shutil
import sys
import tempfile

# Ensure workspace root is in sys.path
workspace_root = Path(__file__).resolve().parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from sandbox_engine.ast_gatekeeper import ASTSemanticGatekeeper
from sandbox_engine.batch_runner import SandboxBatchRunner
from sandbox_engine.image_builder import SandboxImageBuilder
from sandbox_engine.math_utils import upper_confidence_bound_95
from sandbox_engine.patch_verifier import Stage4PatchVerifier
from shared_contracts.schemas import CandidateFixEvaluation, PerturbationType

ORIGINAL_TEST_CODE = '''import hashlib
import os
import random
import threading
import time

class BackgroundWorker:
    def __init__(self):
        self.is_completed = False
        self.done_event = threading.Event()

    def run(self) -> None:
        is_cpu_stress = (
            os.environ.get("COINFLIP_CPU_LOAD") == "1"
            or os.environ.get("COINFLIP_PERTURBATION") in ("cpu_heavy_load", "cpu_half_cores")
        )
        if is_cpu_stress:
            for i in range(8):
                _ = hashlib.sha256(f"job_{i}".encode()).digest()
                time.sleep(0.008)
        else:
            is_stochastic_tail = random.random() < 0.12
            for i in range(8):
                _ = hashlib.sha256(f"job_{i}".encode()).digest()
                time.sleep(0.0035 if is_stochastic_tail else 0.001)
        self.is_completed = True
        self.done_event.set()

    def wait_for_completion(self, timeout: float = 5.0) -> bool:
        return self.done_event.wait(timeout=timeout)

def test_job_finishes():
    worker = BackgroundWorker()
    t = threading.Thread(target=worker.run)
    t.start()
    # Flawed pattern: fixed arbitrary sleep (races worker under load)
    time.sleep(0.025)
    assert worker.is_completed is True, "Background worker timed out before completion"
    t.join(timeout=1.0)
'''

QUICK_FIX_DIFF = '''--- a/test_worker.py
+++ b/test_worker.py
@@ -34,4 +34,4 @@
     t.start()
     # Flawed pattern: fixed arbitrary sleep (races worker under load)
-    time.sleep(0.025)
+    time.sleep(0.040)
     assert worker.is_completed is True, "Background worker timed out before completion"
'''

REAL_FIX_DIFF = '''--- a/test_worker.py
+++ b/test_worker.py
@@ -34,4 +34,4 @@
     t.start()
     # Flawed pattern: fixed arbitrary sleep (races worker under load)
-    time.sleep(0.025)
-    assert worker.is_completed is True, "Background worker timed out before completion"
+    finished = worker.wait_for_completion(timeout=5.0)
+    assert finished is True and worker.is_completed is True, "Background worker timed out"
'''


async def run_phase2_verification(mode: Literal["auto", "local_isolated", "nebius_sandbox"] = "auto") -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix="coinflip_phase2_fixture_"))
    snapshots_dir = Path(tempfile.mkdtemp(prefix="coinflip_phase2_snapshots_"))

    try:
        # 1. Setup base repository fixture
        test_file = temp_dir / "test_worker.py"
        test_file.write_text(ORIGINAL_TEST_CODE, encoding="utf-8")
        print(f"[Phase 2 Verification] Created base fixture at {test_file}")

        # 2. Build immutable snapshot using SandboxImageBuilder
        builder = SandboxImageBuilder(snapshots_root=snapshots_dir, mode=mode)
        base_snapshot_id = builder.create_base_snapshot(temp_dir)
        base_path = builder.get_snapshot_path(base_snapshot_id)
        print(f"[Phase 2 Verification] Created base snapshot: {base_snapshot_id}")

        # 3. Measure original flaky test (Stage 1 / Baseline vs Stress)
        print("\n[Step 1] Measuring Original Flaky Test across 50 quiet and 50 stress runs...")
        orig_runner = SandboxBatchRunner(
            repo_dir=base_path,
            test_target="test_worker.py",
            max_concurrency=4,
            mode=mode,
        )
        orig_normal = await orig_runner.run_batch(PerturbationType.BASELINE, num_runs=50)
        orig_stress = await orig_runner.run_batch(PerturbationType.CPU_HEAVY_LOAD, num_runs=50)

        orig_upper_normal = upper_confidence_bound_95(orig_normal.failures, orig_normal.total_runs)
        orig_upper_stress = upper_confidence_bound_95(orig_stress.failures, orig_stress.total_runs)

        # 4. Initialize Stage 4 Patch Verifier
        verifier = Stage4PatchVerifier(
            image_builder=builder,
            base_snapshot_id=base_snapshot_id,
            test_target="test_worker.py",
            max_concurrency=4,
            mode=mode,
        )

        # 5. Evaluate Candidate Fix 1: Naive Quick Fix (raising sleep to 0.040s)
        print("\n[Step 2] Evaluating Candidate Fix 1: Naive Quick Fix (raising sleep to 0.040s)...")
        eval_fix_1 = await verifier.verify_patch(
            attempt_number=1,
            fix_title="Quick Fix: Raise wait(25ms) to wait(40ms)",
            root_cause_diagnosis=(
                "Worker occasionally exceeds 25ms. Raising arbitrary sleep to 40ms eliminates failures "
                "on a quiet machine, but the race condition remains unhandled under CPU pressure."
            ),
            patch_content=QUICK_FIX_DIFF,
            triggering_stress_condition=PerturbationType.CPU_HEAVY_LOAD,
            cert_runs=50,
            target_limit=0.005,
        )
        CandidateFixEvaluation.model_validate(eval_fix_1)

        # 6. Evaluate Candidate Fix 2: Coinflip Real Fix (Worker Event Synchronization)
        print("\n[Step 3] Evaluating Candidate Fix 2: Coinflip Real Fix (Worker Event Synchronization)...")
        eval_fix_2 = await verifier.verify_patch(
            attempt_number=2,
            fix_title="Coinflip Fix: Wait for worker completion event",
            root_cause_diagnosis=(
                "Replaced arbitrary sleep with worker.wait_for_completion(timeout=5.0) via threading.Event, "
                "eliminating the race condition entirely."
            ),
            patch_content=REAL_FIX_DIFF,
            triggering_stress_condition=PerturbationType.CPU_HEAVY_LOAD,
            cert_runs=50,
            target_limit=0.005,
        )
        CandidateFixEvaluation.model_validate(eval_fix_2)

        # 7. Print Master Comparison Table (Matching Page 9 of Concept Brief)
        print("\n" + "=" * 105)
        print("COINFLIP CERTIFICATE & PATCH VERDICT REPORT (CONCEPT BRIEF PAGE 9 COMPARISON)")
        print("=" * 105)
        print(
            f"{'CANDIDATE VERSION':<30} | "
            f"{'NORMAL (QUIET)':<16} | "
            f"{'STRESS (BUSY CPU)':<18} | "
            f"{'UPPER BOUND':<12} | "
            f"{'VERDICT':<10}"
        )
        print("-" * 105)

        # Row 1: Original Test
        orig_norm_str = f"{orig_normal.failures}/{orig_normal.total_runs} ({orig_normal.failure_rate*100:.1f}%)"
        orig_stress_str = f"{orig_stress.failures}/{orig_stress.total_runs} ({orig_stress.failure_rate*100:.1f}%)"
        orig_verdict = "BROKEN"
        print(
            f"{'Original Test':<30} | "
            f"{orig_norm_str:<16} | "
            f"{orig_stress_str:<18} | "
            f"{orig_upper_stress*100:.2f}%{'':<6} | "
            f"{orig_verdict:<10}"
        )

        # Row 2: Candidate Fix 1 (Quick Fix)
        f1_norm_str = f"{eval_fix_1.normal_cert_result.failures}/{eval_fix_1.normal_cert_result.total_runs} ({eval_fix_1.normal_cert_result.failure_rate*100:.1f}%)"
        f1_stress_str = f"{eval_fix_1.stress_cert_result.failures}/{eval_fix_1.stress_cert_result.total_runs} ({eval_fix_1.stress_cert_result.failure_rate*100:.1f}%)"
        print(
            f"{eval_fix_1.fix_title[:30]:<30} | "
            f"{f1_norm_str:<16} | "
            f"{f1_stress_str:<18} | "
            f"{eval_fix_1.upper_bound_95_stress*100:.2f}%{'':<6} | "
            f"{eval_fix_1.verdict:<10}"
        )

        # Row 3: Candidate Fix 2 (Coinflip Real Fix)
        f2_norm_str = f"{eval_fix_2.normal_cert_result.failures}/{eval_fix_2.normal_cert_result.total_runs} ({eval_fix_2.normal_cert_result.failure_rate*100:.1f}%)"
        f2_stress_str = f"{eval_fix_2.stress_cert_result.failures}/{eval_fix_2.stress_cert_result.total_runs} ({eval_fix_2.stress_cert_result.failure_rate*100:.1f}%)"
        print(
            f"{eval_fix_2.fix_title[:30]:<30} | "
            f"{f2_norm_str:<16} | "
            f"{f2_stress_str:<18} | "
            f"{eval_fix_2.upper_bound_95_stress*100:.2f}%{'':<6} | "
            f"{eval_fix_2.verdict:<10}"
        )
        print("=" * 105)

        # 8. Assertions on Verification Invariants
        print("\n[Verification Checks]")
        print(f"1. Original Test flakiness: Baseline={orig_normal.failure_rate*100:.1f}%, Stress={orig_stress.failure_rate*100:.1f}%")
        assert orig_stress.failure_rate > orig_normal.failure_rate, "Original test should flake more under stress"

        print(f"2. Quick Fix Verdict: {eval_fix_1.verdict} (Expected: REJECTED)")
        assert eval_fix_1.verdict == "REJECTED", f"Expected REJECTED, got {eval_fix_1.verdict}"
        print(f"   Rejection Reason: {eval_fix_1.rejection_reason}")

        print(f"3. Real Fix Verdict: {eval_fix_2.verdict} (Expected: CERTIFIED)")
        assert eval_fix_2.verdict == "CERTIFIED", f"Expected CERTIFIED, got {eval_fix_2.verdict}"
        print(f"   Upper Bound (Normal): {eval_fix_2.upper_bound_95_normal*100:.2f}%")
        print(f"   Upper Bound (Stress): {eval_fix_2.upper_bound_95_stress*100:.2f}%")

        print("\nAll Phase 2 Invariants, Snapshot Operations, and Stage 4 Verifications PASSED!")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        shutil.rmtree(snapshots_dir, ignore_errors=True)


def test_ast_semantic_gatekeeper_14_vectors() -> None:
    """Verifies that ASTSemanticGatekeeper blocks all 14 tampering vectors and passes 5 real benchmark fixes."""
    print("\n" + "=" * 90)
    print("TESTING AST SEMANTIC GATEKEEPER: 14 TAMPERING VECTORS & 5 BENCHMARK FIXES")
    print("=" * 90)

    gk = ASTSemanticGatekeeper()

    base_worker_test = """
import time
import threading

def test_worker():
    time.sleep(0.009)
    assert worker.is_completed is True, "Worker did not complete in time"
"""

    base_rate_test = """
def test_read_rate():
    rate = get_rate("domestic")
    assert rate == 5.99, f"Expected default rate 5.99, got {rate}"
"""

    tampering_cases = [
        # 1. Deleted assertions / reduced assertion count
        (
            "Vector 01: Deleted Assertions",
            base_worker_test,
            """
import time
def test_worker():
    time.sleep(0.009)
""",
            "BLOCKED_ASSERTION_TAMPERING",
        ),
        # 2. Literal tautology: assert True
        (
            "Vector 02: Literal assert True",
            base_worker_test,
            """
import time
def test_worker():
    time.sleep(0.009)
    assert True
""",
            "BLOCKED_ASSERTION_TAMPERING",
        ),
        # 3. Literal tautology: assert 1
        (
            "Vector 03: Literal assert 1",
            base_worker_test,
            """
import time
def test_worker():
    time.sleep(0.009)
    assert 1
""",
            "BLOCKED_ASSERTION_TAMPERING",
        ),
        # 4. Literal tautology: assert "ok"
        (
            "Vector 04: Literal assert 'ok'",
            base_worker_test,
            """
import time
def test_worker():
    time.sleep(0.009)
    assert "ok"
""",
            "BLOCKED_ASSERTION_TAMPERING",
        ),
        # 5. Boolean short-circuit: assert x or True
        (
            "Vector 05: Short-circuit assert x or True",
            base_worker_test,
            """
import time
def test_worker():
    time.sleep(0.009)
    assert worker.is_completed or True
""",
            "BLOCKED_ASSERTION_TAMPERING",
        ),
        # 6. Boolean short-circuit: assert True or x
        (
            "Vector 06: Short-circuit assert True or x",
            base_worker_test,
            """
import time
def test_worker():
    time.sleep(0.009)
    assert True or worker.is_completed
""",
            "BLOCKED_ASSERTION_TAMPERING",
        ),
        # 7. Law of excluded middle: assert x or not x
        (
            "Vector 07: Law of excluded middle assert x or not x",
            base_worker_test,
            """
import time
def test_worker():
    time.sleep(0.009)
    assert worker.is_completed or not worker.is_completed
""",
            "BLOCKED_ASSERTION_TAMPERING",
        ),
        # 8. Law of excluded middle: assert not x or x
        (
            "Vector 08: Law of excluded middle assert not x or x",
            base_worker_test,
            """
import time
def test_worker():
    time.sleep(0.009)
    assert not worker.is_completed or worker.is_completed
""",
            "BLOCKED_ASSERTION_TAMPERING",
        ),
        # 9. Self-comparison: assert x == x
        (
            "Vector 09: Self-comparison assert x == x",
            base_worker_test,
            """
import time
def test_worker():
    time.sleep(0.009)
    assert worker.is_completed == worker.is_completed
""",
            "BLOCKED_ASSERTION_TAMPERING",
        ),
        # 10. Self-membership: assert x in [x]
        (
            "Vector 10: Self-membership assert x in [x]",
            base_worker_test,
            """
import time
def test_worker():
    time.sleep(0.009)
    assert worker.is_completed in [worker.is_completed]
""",
            "BLOCKED_ASSERTION_TAMPERING",
        ),
        # 11. Dead conditional: if False: assert ...
        (
            "Vector 11: Dead conditional if False: assert ...",
            base_worker_test,
            """
import time
def test_worker():
    time.sleep(0.009)
    if False:
        assert worker.is_completed is True
""",
            "BLOCKED_ASSERTION_TAMPERING",
        ),
        # 12. Early return before assert
        (
            "Vector 12: Early return before assertions",
            base_worker_test,
            """
import time
def test_worker():
    return
    time.sleep(0.009)
    assert worker.is_completed is True
""",
            "BLOCKED_TEST_SUPPRESSION",
        ),
        # 13. Exception swallowing around assertions (try/except: pass)
        (
            "Vector 13: Exception swallowing try/except: pass",
            base_worker_test,
            """
import time
def test_worker():
    try:
        assert worker.is_completed is True
    except Exception:
        pass
""",
            "BLOCKED_TEST_SUPPRESSION",
        ),
        # 14. Test suppression / rerun decorator: @pytest.mark.flaky(reruns=5)
        (
            "Vector 14: Suppression decorator @pytest.mark.flaky",
            base_worker_test,
            """
import pytest
import time
@pytest.mark.flaky(reruns=5)
def test_worker():
    time.sleep(0.009)
    assert worker.is_completed is True
""",
            "BLOCKED_TEST_SUPPRESSION",
        ),
        # 15. Weakened assertion operator: assert rate is not None (replacing rate == 5.99)
        (
            "Vector 15: Weakened operator assert rate is not None",
            base_rate_test,
            """
def test_read_rate():
    rate = get_rate("domestic")
    assert rate is not None
""",
            "BLOCKED_ASSERTION_TAMPERING",
        ),
    ]

    for label, orig_code, patch_code, expected_status in tampering_cases:
        rep = gk.audit(orig_code, patch_code)
        assert rep.passed_gatekeeper is False, f"Failed to block {label}! rep={rep}"
        assert rep.status_code == expected_status, f"Expected {expected_status} for {label}, got {rep.status_code}"
        print(f"  [BLOCKED] {label:<50} -> {rep.status_code} (PASS)")

    # 16. Verify Sleep Inflation without sync primitives is warned
    sleep_inflation_patch = """
import time
def test_worker():
    time.sleep(0.050)
    assert worker.is_completed is True, "Worker did not complete in time"
"""
    rep_sleep = gk.audit(base_worker_test, sleep_inflation_patch)
    assert rep_sleep.passed_gatekeeper is True
    assert rep_sleep.status_code == "WARN_SLEEP_INFLATION"
    assert rep_sleep.sleep_inflation_detected is True
    print(f"  [WARNED]  {'Sleep Inflation without synchronization':<50} -> WARN_SLEEP_INFLATION (PASS)")

    # 17. Verify all 5 Certified Real Benchmark Fixes pass as VERIFIED_CLEAN
    benchmark_fixes = [
        (
            "Benchmark 1: hero_worker_race (wait_for_completion)",
            base_worker_test,
            """
import threading
def test_worker():
    finished = worker.wait_for_completion(timeout=5.0)
    assert finished is True and worker.is_completed is True, "Worker timed out"
""",
        ),
        (
            "Benchmark 2: case_01_test_order_pollution (autouse reset fixture)",
            base_rate_test,
            """
import pytest
@pytest.fixture(autouse=True)
def reset_rate_limiter():
    RateLimiter.reset_instance()
    yield
    RateLimiter.reset_instance()

def test_read_rate():
    rate = get_rate("domestic")
    assert rate == 5.99, f"Expected default rate 5.99, got {rate}"
""",
        ),
        (
            "Benchmark 3: case_02_unpinned_seed_sampling (deterministic Random)",
            """
def test_batch_score():
    score = compute_score()
    assert score >= 75.0
""",
            """
import random
def test_batch_score():
    rng = random.Random(0xDEADBEEF)
    score = compute_score(rng=rng)
    assert score >= 75.0
""",
        ),
        (
            "Benchmark 4: case_03_token_expiry_clock (freeze_time context)",
            """
def test_cache_ttl():
    cache = FileCacheTTL()
    token = cache.retrieve("tok")
    assert token == "valid"
""",
            """
from freezegun import freeze_time
def test_cache_ttl():
    with freeze_time("2026-10-18 12:00:00"):
        cache = FileCacheTTL()
        token = cache.retrieve("tok")
        assert token == "valid"
""",
        ),
        (
            "Benchmark 5: case_04_async_queue_race (wait_for_drain)",
            """
import time
def test_queue():
    time.sleep(0.026)
    assert len(eq.flushed) == 10
""",
            """
def test_queue():
    drained = eq.wait_for_drain(timeout=5.0)
    assert drained is True and len(eq.flushed) == 10
""",
        ),
    ]

    for label, orig_code, fix_code in benchmark_fixes:
        rep_fix = gk.audit(orig_code, fix_code)
        assert rep_fix.passed_gatekeeper is True, f"Real fix rejected: {label}! rep={rep_fix}"
        assert rep_fix.status_code == "VERIFIED_CLEAN", f"Expected VERIFIED_CLEAN for {label}, got {rep_fix.status_code}"
        assert len(rep_fix.synchronization_primitives_detected) > 0, f"No sync detected for {label}"
        print(f"  [CLEAN]   {label:<50} -> VERIFIED_CLEAN {rep_fix.synchronization_primitives_detected} (PASS)")

    print("\n✅ ALL 14+ TAMPERING VECTORS BLOCKED & ALL 5 REAL BENCHMARK FIXES CERTIFIED CLEAN!")
    print("=" * 90 + "\n")


def main() -> None:
    test_ast_semantic_gatekeeper_14_vectors()
    mode = "local_isolated" if ("--local" in sys.argv or "local_isolated" in sys.argv) else "auto"
    asyncio.run(run_phase2_verification(mode=mode))


if __name__ == "__main__":
    main()
