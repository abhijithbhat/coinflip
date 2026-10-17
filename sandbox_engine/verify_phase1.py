#!/usr/bin/env python3
"""Phase 1 Verification Script for Coinflip.

Validates:
1. SandboxBatchRunner execution across BASELINE, SHUFFLE_ORDER, NETWORK_CUT, and CPU_HEAVY_LOAD.
2. Demonstrates that CPU_HEAVY_LOAD produces an amplified failure rate on a race-condition test.
3. Verifies that all results conform to Pydantic schemas in shared_contracts/schemas.py.
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
from shared_contracts.schemas import BatchExperimentResult, PerturbationType

FLAKY_TEST_CONTENT = """import hashlib
import threading
import time

class BackgroundWorker:
    def __init__(self, target_units: int = 65000):
        self.is_completed = False
        self.items_processed = 0
        self.target_units = target_units

    def run(self) -> None:
        for i in range(self.target_units):
            hashlib.sha256(f"chunk_{i}".encode()).digest()
            self.items_processed += 1
        self.is_completed = True

def test_job_finishes():
    worker = BackgroundWorker()
    t = threading.Thread(target=worker.run)
    t.start()
    # Flawed pattern: fixed arbitrary sleep instead of event-based synchronization
    time.sleep(0.022)
    assert worker.is_completed is True, (
        f"Expected background job to finish, but was still running "
        f"({worker.items_processed}/{worker.target_units} items processed)"
    )
    t.join(timeout=1.0)
"""


async def run_phase1_verification() -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix="coinflip_hero_test_"))
    try:
        # 1. Create mini-project with flaky worker test
        test_file = temp_dir / "test_worker.py"
        test_file.write_text(FLAKY_TEST_CONTENT, encoding="utf-8")
        print(f"[Phase 1 Verification] Created test fixture at {test_file}")

        # 2. Instantiate SandboxBatchRunner in auto mode
        runner = SandboxBatchRunner(
            repo_dir=temp_dir,
            test_target="test_worker.py",
            max_concurrency=16,
            mode="auto",
        )

        backend = await runner.resolve_execution_backend()
        print(f"[Phase 1 Verification] Active Backend: {backend}\n")

        conditions_to_test = [
            (PerturbationType.BASELINE, 40),
            (PerturbationType.SHUFFLE_ORDER, 40),
            (PerturbationType.NETWORK_CUT, 40),
            (PerturbationType.CPU_HEAVY_LOAD, 40),
        ]

        results: dict[PerturbationType, BatchExperimentResult] = {}

        for perturbation, num_runs in conditions_to_test:
            print(f"Executing {num_runs} runs for {perturbation.value}...")
            batch_res = await runner.run_batch(perturbation, num_runs=num_runs)
            # Schema validation
            BatchExperimentResult.model_validate(batch_res)
            results[perturbation] = batch_res

        # 3. Print clean verification table
        print("\n" + "=" * 92)
        print(f"{'PERTURBATION CONDITION':<24} | {'RUNS':<6} | {'PASS':<6} | {'FAIL':<6} | {'RATE':<8} | {'95% WILSON CI':<18} | {'BACKEND'}")
        print("=" * 92)

        for perturbation, res in results.items():
            ci_str = f"[{res.ci_95_lower:.3f}, {res.ci_95_upper:.3f}]"
            rate_str = f"{res.failure_rate * 100:.1f}%"
            print(
                f"{res.perturbation.value:<24} | "
                f"{res.total_runs:<6} | "
                f"{res.passes:<6} | "
                f"{res.failures:<6} | "
                f"{rate_str:<8} | "
                f"{ci_str:<18} | "
                f"{res.execution_backend}"
            )
        print("=" * 92 + "\n")

        # 4. Invariant checks
        baseline_rate = results[PerturbationType.BASELINE].failure_rate
        heavy_load_rate = results[PerturbationType.CPU_HEAVY_LOAD].failure_rate

        print(f"Baseline Failure Rate:   {baseline_rate * 100:.1f}%")
        print(f"Heavy Load Failure Rate: {heavy_load_rate * 100:.1f}%\n")

        assert heavy_load_rate > baseline_rate, (
            f"Expected CPU_HEAVY_LOAD rate ({heavy_load_rate}) to be greater than BASELINE ({baseline_rate})"
        )

        if results[PerturbationType.CPU_HEAVY_LOAD].sample_failure_logs:
            print("Captured Sample Failure Log (CPU_HEAVY_LOAD):")
            sample_snippet = results[PerturbationType.CPU_HEAVY_LOAD].sample_failure_logs[0]
            print("-" * 50)
            print(sample_snippet)
            print("-" * 50)

        print("\nAll Phase 1 Invariants and Pydantic Schema validations PASSED successfully!")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main() -> None:
    asyncio.run(run_phase1_verification())


if __name__ == "__main__":
    main()
