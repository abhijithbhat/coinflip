#!/usr/bin/env python3
"""Phase 3 End-to-End Verification Script for Coinflip.

Validates the full 5-stage Coinflip pipeline:
1. Real pytest executions across all 7 perturbation conditions.
2. Real runtime calls to NVIDIA Nemotron models on Nebius Token Factory:
   - nvidia/Nemotron-3_5-Lightning for log summarization
   - nvidia/Nemotron-3-Ultra-550b-a55b for deep reasoning & certified patch synthesis.
3. Captures both the REJECTED quick fix and the CERTIFIED root-cause fix.
4. Overwrites shared_contracts/sample_hero_trace.json with 100% real run data.
5. Prints the complete COINFLIP CERTIFICATE in the terminal.
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

from sandbox_engine.orchestrator import CoinflipOrchestrator
from shared_contracts.schemas import CoinflipCertificateTrace

HERO_TEST_CODE = '''import hashlib
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


async def run_phase3_verification() -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix="coinflip_hero_service_"))
    output_trace_path = workspace_root / "shared_contracts" / "sample_hero_trace.json"

    try:
        # 1. Setup target service fixture
        test_file = temp_dir / "test_worker.py"
        test_file.write_text(HERO_TEST_CODE, encoding="utf-8")
        print(f"[Phase 3 Verification] Initialized test repository at {test_file}")

        # 2. Instantiate CoinflipOrchestrator
        orchestrator = CoinflipOrchestrator(
            repo_dir=temp_dir,
            test_target="test_worker.py",
            project_name="example-service",
            max_concurrency=4,
            mode="auto",
            output_trace_path=output_trace_path,
        )

        print("\n" + "=" * 95)
        print("LAUNCHING COINFLIP 5-STAGE ORCHESTRATOR (LIVE NEMOTRON + SANDBOX PIPELINE)")
        print("=" * 95 + "\n")

        # 3. Execute full pipeline
        trace = await orchestrator.run(
            stage1_runs=30,
            stage2_runs=25,
            stage4_cert_runs=35,
            target_limit=0.005,
            demonstrate_rejection_catch=True,
        )

        # 4. Validate output trace schema
        validated_trace = CoinflipCertificateTrace.model_validate_json(
            output_trace_path.read_text(encoding="utf-8")
        )
        print(f"\n[OK] Validated trace saved to {output_trace_path} ({len(output_trace_path.read_text())} bytes)")

        # 5. Print the Complete Coinflip Certificate
        print("\n" + "#" * 95)
        print("                       OFFICIAL COINFLIP CERTIFICATE")
        print("#" * 95)
        print(f"Project:             {validated_trace.project_name}")
        print(f"Test Identifier:     {validated_trace.test_identifier}")
        print(f"Trace Session ID:    {validated_trace.trace_id}")
        print(f"Timestamp (UTC):     {validated_trace.timestamp_utc}")
        print(f"Live / Real Run:     {not validated_trace.is_recorded_replay}")
        print("-" * 95)
        print("STAGE 1: BASELINE MEASUREMENT")
        s1 = validated_trace.stage1_baseline
        print(f"  Failures:          {s1.failures} / {s1.total_runs} ({s1.failure_rate * 100:.1f}%)")
        print(f"  95% Wilson CI:     [{s1.ci_95_lower:.3f}, {s1.ci_95_upper:.3f}]")
        print(f"  Backend:           {s1.execution_backend}")
        print("-" * 95)
        print("STAGE 2: PERTURBATION EXPERIMENT LEDGER")
        for res in validated_trace.stage2_ledger:
            marker = " <-- [TRIGGERING STRESS]" if res.perturbation == validated_trace.triggering_stress_condition else ""
            print(f"  {res.perturbation.value:<18} | {res.failures:>2}/{res.total_runs:<2} failed ({res.failure_rate * 100:>5.1f}%) | CI: [{res.ci_95_lower:.3f}, {res.ci_95_upper:.3f}]{marker}")
        print("-" * 95)
        print("STAGES 3 & 4: CANDIDATE FIX EVALUATIONS & CERTIFICATION GATE")
        for fix in validated_trace.fix_attempts:
            print(f"\n  Attempt #{fix.attempt_number}: {fix.fix_title}")
            print(f"  Diagnosis:        {fix.root_cause_diagnosis}")
            norm_str = f"{fix.normal_cert_result.failures}/{fix.normal_cert_result.total_runs} ({fix.normal_cert_result.failure_rate * 100:.1f}%)"
            stress_str = f"{fix.stress_cert_result.failures}/{fix.stress_cert_result.total_runs} ({fix.stress_cert_result.failure_rate * 100:.1f}%)"
            print(f"  Quiet Machine:    {norm_str}")
            print(f"  Under Stress:     {stress_str}")
            print(f"  Verdict:          [{fix.verdict}]")
            if fix.rejection_reason:
                print(f"  Catch Reason:     {fix.rejection_reason}")
        print("-" * 95)
        print("MODELS USED (NEBIUS TOKEN FACTORY):")
        for role, m_id in validated_trace.models_used.items():
            print(f"  {role:<20}: {m_id}")
        print("-" * 95)
        print(f"FINAL CERTIFICATE VERDICT: {validated_trace.final_verdict}")
        print("#" * 95 + "\n")

        # Invariant Assertions
        assert validated_trace.final_verdict == "PASS"
        assert len(validated_trace.fix_attempts) >= 2
        assert validated_trace.fix_attempts[0].verdict == "REJECTED"
        assert validated_trace.fix_attempts[1].verdict == "CERTIFIED"
        print("All Phase 3 Invariants, Live Model Calls, and 5-Stage Orchestrations PASSED!")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main() -> None:
    asyncio.run(run_phase3_verification())


if __name__ == "__main__":
    main()
