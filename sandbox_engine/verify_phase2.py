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

from sandbox_engine.batch_runner import SandboxBatchRunner
from sandbox_engine.image_builder import SandboxImageBuilder
from sandbox_engine.math_utils import upper_confidence_bound_95
from sandbox_engine.patch_verifier import Stage4PatchVerifier
from shared_contracts.schemas import CandidateFixEvaluation, PerturbationType

ORIGINAL_TEST_CODE = '''import hashlib
import threading
import time

class BackgroundWorker:
    def __init__(self):
        self.is_completed = False
        self.done_event = threading.Event()

    def run(self) -> None:
        for i in range(8):
            _ = hashlib.sha256(f"job_{i}".encode()).digest()
            time.sleep(0.001)
        self.is_completed = True
        self.done_event.set()

    def wait_for_completion(self, timeout: float = 5.0) -> bool:
        return self.done_event.wait(timeout=timeout)

def test_job_finishes():
    worker = BackgroundWorker()
    t = threading.Thread(target=worker.run)
    t.start()
    # Flawed pattern: fixed arbitrary sleep (races worker under load)
    time.sleep(0.009)
    assert worker.is_completed is True, "Background worker timed out before completion"
    t.join(timeout=1.0)
'''

QUICK_FIX_DIFF = '''--- a/test_worker.py
+++ b/test_worker.py
@@ -21,3 +21,3 @@
     t.start()
-    time.sleep(0.009)
+    time.sleep(0.050)
     assert worker.is_completed is True, "Background worker timed out before completion"
'''

REAL_FIX_DIFF = '''--- a/test_worker.py
+++ b/test_worker.py
@@ -21,3 +21,3 @@
     t.start()
-    time.sleep(0.009)
-    assert worker.is_completed is True, "Background worker timed out before completion"
+    finished = worker.wait_for_completion(timeout=5.0)
+    assert finished is True and worker.is_completed is True, "Background worker timed out"
'''


async def run_phase2_verification() -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix="coinflip_phase2_fixture_"))
    snapshots_dir = Path(tempfile.mkdtemp(prefix="coinflip_phase2_snapshots_"))

    try:
        # 1. Setup base repository fixture
        test_file = temp_dir / "test_worker.py"
        test_file.write_text(ORIGINAL_TEST_CODE, encoding="utf-8")
        print(f"[Phase 2 Verification] Created base fixture at {test_file}")

        # 2. Build immutable snapshot using SandboxImageBuilder
        builder = SandboxImageBuilder(snapshots_root=snapshots_dir, mode="auto")
        base_snapshot_id = builder.create_base_snapshot(temp_dir)
        base_path = builder.get_snapshot_path(base_snapshot_id)
        print(f"[Phase 2 Verification] Created base snapshot: {base_snapshot_id}")

        # 3. Measure original flaky test (Stage 1 / Baseline vs Stress)
        print("\n[Step 1] Measuring Original Flaky Test across 50 quiet and 50 stress runs...")
        orig_runner = SandboxBatchRunner(
            repo_dir=base_path,
            test_target="test_worker.py",
            max_concurrency=4,
            mode="auto",
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
            mode="auto",
        )

        # 5. Evaluate Candidate Fix 1: Naive Quick Fix (raising sleep to 0.050s)
        print("\n[Step 2] Evaluating Candidate Fix 1: Naive Quick Fix (raising sleep to 0.050s)...")
        eval_fix_1 = await verifier.verify_patch(
            attempt_number=1,
            fix_title="Quick Fix: Raise wait(9ms) to wait(50ms)",
            root_cause_diagnosis=(
                "Worker occasionally exceeds 9ms. Raising arbitrary sleep to 50ms eliminates failures "
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


def main() -> None:
    asyncio.run(run_phase2_verification())


if __name__ == "__main__":
    main()
