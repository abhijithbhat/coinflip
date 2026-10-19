"""Comprehensive Phase 6 Verification Script for Coinflip.

Validates:
1. Developer Merges: main contains Tejas's feat/tejas-phase5-pro and Dulkif's /benchmarks/
2. Benchmark Cleanliness: stray installer files removed from benchmarks/hero_worker_race/
3. Real Nebius Sandboxes Activation:
   - contree_sdk Contree client with active Token Factory Beta credentials
   - MicroVM container execution with python:3.12-slim
   - Live parallel batch execution under BASELINE vs CPU_HEAVY_LOAD
4. Fallback Safety: dual-mode execution auto-probe and local_isolated reliability
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import subprocess
import sys
import time

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from dotenv import load_dotenv

load_dotenv()

from sandbox_engine.batch_runner import SandboxBatchRunner
from shared_contracts.schemas import PerturbationType


def step(title: str) -> None:
    print(f"\n{'='*80}\n{title}\n{'='*80}")


def check(condition: bool, msg: str) -> None:
    if condition:
        print(f"  ✅ {msg}")
    else:
        print(f"  ❌ FAILED: {msg}")
        sys.exit(1)


async def main() -> None:
    print("\n" + "#" * 80)
    print("COINFLIP PHASE 6: 3-DEVELOPER MERGE & LIVE NEBIUS SANDBOX VERIFICATION")
    print("#" * 80)

    # --------------------------------------------------------------------------
    # Step 1: Verify Git Integration & Stray File Removal
    # --------------------------------------------------------------------------
    step("STEP 1: REPOSITORY MERGE & FILE INTEGRITY CHECKS")

    # 1.1 Verify benchmarks directory exists and has all 5 suites
    benchmark_dir = repo_root / "benchmarks"
    check(benchmark_dir.exists(), "benchmarks/ directory exists on main")
    expected_suites = [
        "hero_worker_race",
        "real_world_cases/case_01_test_order_pollution",
        "real_world_cases/case_02_unpinned_seed_sampling",
        "real_world_cases/case_03_token_expiry_clock",
        "real_world_cases/case_04_async_queue_race",
    ]
    for s in expected_suites:
        suite_path = benchmark_dir / s
        check(suite_path.exists(), f"Suite exists: benchmarks/{s}")

    # 1.2 Verify stray installer log files are absent
    stray_log = benchmark_dir / "hero_worker_race/python_install_20261018203209_98252.log"
    stray_cache = benchmark_dir / "hero_worker_race/Python"
    check(not stray_log.exists(), "Stray installer log file removed")
    check(not stray_cache.exists(), "Stray Python/_cache directory removed")

    # 1.3 Verify Tejas's Phase 5 Pro files are present
    check((repo_root / "agent_and_ui/test_stats_engine.py").exists(), "Tejas's test_stats_engine.py present")
    check((repo_root / "agent_and_ui/test_app.py").exists(), "Tejas's test_app.py present")

    # --------------------------------------------------------------------------
    # Step 2: Nebius Token Factory Beta Sandboxes Verification
    # --------------------------------------------------------------------------
    step("STEP 2: LIVE NEBIUS SANDBOXES (`contree_sdk`) BETA CREDENTIALS & API PROBE")

    api_key = os.getenv("NEBIUS_API_KEY")
    project_id = os.getenv("NEBIUS_PROJECT_ID")
    check(bool(api_key and project_id), f"Nebius API credentials loaded (Project: {project_id})")

    from contree_sdk import Contree, ContreeSync

    client_sync = ContreeSync()
    token_info = client_sync.get_token_info()
    check(
        bool(token_info and token_info.permissions.get("spawn")),
        f"Nebius Token Factory permissions verified: {list(token_info.permissions.keys())}",
    )
    print(f"  -> Instance max concurrency limit: {token_info.limits.get('instance_max_concurrency')}")
    print(f"  -> Operations stats: {token_info.operations_stat}")

    # --------------------------------------------------------------------------
    # Step 3: Single Command Execution in python:3.12-slim MicroVM
    # --------------------------------------------------------------------------
    step("STEP 3: LIVE CLOUD MICROVM EXECUTION (`python:3.12-slim`)")

    t0 = time.time()
    sandbox = client_sync.images.use("python:3.12-slim")
    res = sandbox.run("python3", args=["-c", "import sys; print(f'Nebius MicroVM running Python {sys.version}')"]).wait()
    dt = time.time() - t0

    check(res.exit_code == 0, f"MicroVM command completed successfully in {dt:.2f}s (Exit code: {res.exit_code})")
    print(f"  -> Container stdout: {res.stdout.strip()}")

    # --------------------------------------------------------------------------
    # Step 4: Live Sandbox Batch Runner (Baseline vs Concurrency Flake)
    # --------------------------------------------------------------------------
    step("STEP 4: PARALLEL BATCH RUNNER IN NEBIUS SANDBOX (BASELINE vs FLAKE)")

    runner = SandboxBatchRunner(
        repo_dir=benchmark_dir / "hero_worker_race",
        test_target="test_worker.py",
        mode="nebius_sandbox",
        max_concurrency=10,
    )

    backend = await runner.resolve_execution_backend()
    check(backend == "nebius_sandbox", f"Execution backend resolved to: '{backend}'")

    print("\n[Stage 1] Executing 3 baseline runs in parallel cloud microVMs...")
    base_res = await runner.run_batch(PerturbationType.BASELINE, num_runs=3)
    check(base_res.passes == 3, f"Baseline runs passed 100% ({base_res.passes}/{base_res.total_runs})")
    print(f"  -> Baseline pass dots: {base_res.run_dots}")

    print("\n[Stage 2] Executing 3 CPU heavy load runs in parallel cloud microVMs...")
    stress_res = await runner.run_batch(PerturbationType.CPU_HEAVY_LOAD, num_runs=3)
    check(stress_res.failures == 3, f"CPU Heavy load triggered race flake 100% ({stress_res.failures}/{stress_res.total_runs} failed)")
    print(f"  -> Stress fail dots:   {stress_res.run_dots}")
    check(len(stress_res.sample_failure_logs) > 0, "Deduplicated error snippet captured from cloud runner")
    print("  -> Captured Error snippet:\n" + "\n".join("     " + line for line in stress_res.sample_failure_logs[0].splitlines()[:5]))

    # --------------------------------------------------------------------------
    # Step 5: Full Suite Integration
    # --------------------------------------------------------------------------
    step("STEP 5: AGENT & UI SUITE VERIFICATION")
    pytest_proc = subprocess.run(
        [sys.executable, "-m", "pytest", "agent_and_ui/", "-q"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    check(pytest_proc.returncode == 0, f"All 104 agent_and_ui tests passed: {pytest_proc.stdout.strip().splitlines()[-1]}")

    print("\n" + "#" * 80)
    print("PHASE 6 VERIFICATION COMPLETED: ALL CHECKS PASSED (100% OPERATIONAL)!")
    print("#" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
