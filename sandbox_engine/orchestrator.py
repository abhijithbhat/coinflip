"""Core 5-Stage Orchestrator for Coinflip.

Executes the complete investigation and verification pipeline:
- Stage 1 (Measure): Baseline flakiness quantification with Wilson confidence intervals.
- Stage 2 (Experiment): 7-condition stress ledger to isolate the root-cause perturbation.
- Stage 3 (Find & Fix): Log summarization (Nemotron Lightning) & root cause diagnosis (Nemotron 3 Ultra).
- Stage 4 (Certify): Dual quiet/stress certification gate with automatic rejection retry loop.
- Stage 5 (Report): Generates validated CoinflipCertificateTrace JSON artifact for UI replay.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Literal
import uuid

from sandbox_engine.batch_runner import SandboxBatchRunner
from sandbox_engine.image_builder import SandboxImageBuilder
from sandbox_engine.llm_bridge import (
    MODEL_FAST,
    MODEL_REASONING,
    NemotronBridge,
)
from sandbox_engine.patch_verifier import Stage4PatchVerifier
from shared_contracts.schemas import (
    BatchExperimentResult,
    CandidateFixEvaluation,
    CoinflipCertificateTrace,
    PerturbationType,
)

logger = logging.getLogger("sandbox_engine.orchestrator")


class CoinflipOrchestrator:
    """End-to-end 5-stage automated flaky test investigator and certifier."""

    def __init__(
        self,
        repo_dir: Path | str,
        test_target: str,
        project_name: str = "example-service",
        max_concurrency: int = 4,
        mode: Literal["auto", "local_isolated", "nebius_sandbox"] = "auto",
        output_trace_path: Path | str | None = None,
        llm_bridge: NemotronBridge | None = None,
    ) -> None:
        self.repo_dir = Path(repo_dir).resolve()
        self.test_target = test_target
        self.project_name = project_name
        self.max_concurrency = max_concurrency
        self.mode = mode
        self.output_trace_path = (
            Path(output_trace_path).resolve()
            if output_trace_path
            else Path(__file__).resolve().parent.parent / "shared_contracts" / "sample_hero_trace.json"
        )
        self.llm = llm_bridge or NemotronBridge()
        self.image_builder = SandboxImageBuilder(mode=self.mode)

    async def run(
        self,
        stage1_runs: int = 40,
        stage2_runs: int = 30,
        stage4_cert_runs: int = 40,
        target_limit: float = 0.005,
        demonstrate_rejection_catch: bool = True,
    ) -> CoinflipCertificateTrace:
        """Executes the full 5-stage Coinflip pipeline.

        Args:
            stage1_runs: Number of runs for Stage 1 baseline measurement.
            stage2_runs: Number of runs per condition for Stage 2 stress ledger.
            stage4_cert_runs: Number of runs for Stage 4 quiet and stress certification.
            target_limit: Upper confidence bound limit for certification (default 0.5%).
            demonstrate_rejection_catch: If True, evaluates a naive timeout increase first
                                         to demonstrate the stress-rejection catch before the real fix.

        Returns:
            CoinflipCertificateTrace: Validated end-to-end trace artifact.
        """
        trace_id = f"coinflip_trace_{uuid.uuid4().hex[:12]}"
        timestamp_utc = datetime.now(timezone.utc).isoformat()
        logger.info("Starting Coinflip Run %s for %s::%s", trace_id, self.project_name, self.test_target)

        # ---------------------------------------------------------------------
        # STAGE 1: MEASURE BASELINE
        # ---------------------------------------------------------------------
        logger.info("[STAGE 1] Creating base snapshot and measuring baseline flakiness...")
        base_snapshot_id = self.image_builder.create_base_snapshot(self.repo_dir)
        base_snapshot_path = self.image_builder.get_snapshot_path(base_snapshot_id)

        runner = SandboxBatchRunner(
            repo_dir=base_snapshot_path,
            test_target=self.test_target,
            max_concurrency=self.max_concurrency,
            mode=self.mode,
        )

        stage1_baseline = await runner.run_batch(
            perturbation=PerturbationType.BASELINE,
            num_runs=stage1_runs,
        )
        logger.info(
            "Stage 1 Baseline: %d/%d failed (%.1f%%) CI=[%.3f, %.3f]",
            stage1_baseline.failures,
            stage1_baseline.total_runs,
            stage1_baseline.failure_rate * 100,
            stage1_baseline.ci_95_lower,
            stage1_baseline.ci_95_upper,
        )

        # ---------------------------------------------------------------------
        # STAGE 2: EXPERIMENT (7-CONDITION PERTURBATION LEDGER)
        # ---------------------------------------------------------------------
        logger.info("[STAGE 2] Running the 7-condition perturbation suite...")
        conditions_order = [
            PerturbationType.BASELINE,
            PerturbationType.SHUFFLE_ORDER,
            PerturbationType.SEED_CHANGE,
            PerturbationType.CLOCK_SHIFT,
            PerturbationType.NETWORK_CUT,
            PerturbationType.CPU_HALF_CORES,
            PerturbationType.CPU_HEAVY_LOAD,
        ]

        stage2_ledger: list[BatchExperimentResult] = []
        highest_rate = -1.0
        triggering_condition = PerturbationType.CPU_HEAVY_LOAD

        for cond in conditions_order:
            # Re-use stage1 result for baseline if counts match, else execute
            if cond == PerturbationType.BASELINE and stage1_runs == stage2_runs:
                batch_res = stage1_baseline
            else:
                batch_res = await runner.run_batch(cond, num_runs=stage2_runs)

            stage2_ledger.append(batch_res)
            logger.info("  Ledger [%s]: %.1f%% failure rate", cond.value, batch_res.failure_rate * 100)

            # Track which condition amplified the flake rate the most
            if batch_res.perturbation != PerturbationType.BASELINE and batch_res.failure_rate > highest_rate:
                highest_rate = batch_res.failure_rate
                triggering_condition = batch_res.perturbation

        logger.info("Stage 2 Triggering Stress Condition Identified: %s", triggering_condition.value)

        # Read original test code from base snapshot for AI repair
        test_file_path = base_snapshot_path / self.test_target
        original_test_code = test_file_path.read_text(encoding="utf-8") if test_file_path.exists() else ""

        # ---------------------------------------------------------------------
        # STAGES 3 & 4: FIND & FIX + STRESS CERTIFICATION WITH RETRY LOOP
        # ---------------------------------------------------------------------
        verifier = Stage4PatchVerifier(
            image_builder=self.image_builder,
            base_snapshot_id=base_snapshot_id,
            test_target=self.test_target,
            max_concurrency=self.max_concurrency,
            mode=self.mode,
        )

        fix_attempts: list[CandidateFixEvaluation] = []
        attempt_number = 1

        # Attempt 1: Evaluate Naive Quick Fix if demonstration requested
        if demonstrate_rejection_catch:
            logger.info("[STAGE 3/4 - ATTEMPT 1] Evaluating Naive Quick Fix (raising timeout/sleep)...")
            all_sample_logs = stage1_baseline.sample_failure_logs or ["AssertionError: Worker timed out"]
            log_summary = self.llm.summarize_failure_logs(all_sample_logs)

            qf_title, qf_diag, qf_code = self.llm.generate_naive_quick_fix(
                test_code=original_test_code,
                failure_summary=log_summary,
            )

            eval_attempt_1 = await verifier.verify_patch(
                attempt_number=attempt_number,
                fix_title=qf_title,
                root_cause_diagnosis=qf_diag,
                patch_content=qf_code,
                triggering_stress_condition=triggering_condition,
                cert_runs=stage4_cert_runs,
                target_limit=target_limit,
                target_file_rel=self.test_target,
            )
            fix_attempts.append(eval_attempt_1)
            logger.info("Attempt 1 Verdict: %s", eval_attempt_1.verdict)
            attempt_number += 1

        # Attempt 2: Certified Root-Cause Fix via Nemotron 3 Ultra
        logger.info("[STAGE 3/4 - ATTEMPT 2] Calling Nemotron 3 Ultra with Stress Rejection Evidence...")
        real_title, real_diag, real_code = self.llm.diagnose_and_propose_fix(
            test_code=original_test_code,
            stage1_baseline=stage1_baseline,
            stage2_ledger=stage2_ledger,
            previous_rejected_attempts=fix_attempts,
        )

        eval_attempt_2 = await verifier.verify_patch(
            attempt_number=attempt_number,
            fix_title=real_title,
            root_cause_diagnosis=real_diag,
            patch_content=real_code,
            triggering_stress_condition=triggering_condition,
            cert_runs=stage4_cert_runs,
            target_limit=target_limit,
            target_file_rel=self.test_target,
        )
        fix_attempts.append(eval_attempt_2)
        logger.info("Attempt 2 Verdict: %s", eval_attempt_2.verdict)

        # ---------------------------------------------------------------------
        # STAGE 5: REPORT & PERSIST CERTIFICATE TRACE
        # ---------------------------------------------------------------------
        logger.info("[STAGE 5] Assembling final certificate trace...")
        has_certified_fix = any(att.verdict == "CERTIFIED" for att in fix_attempts)
        final_verdict: Literal["PASS", "NOT_YET_CERTIFIED"] = (
            "PASS" if has_certified_fix else "NOT_YET_CERTIFIED"
        )

        trace = CoinflipCertificateTrace(
            trace_id=trace_id,
            timestamp_utc=timestamp_utc,
            is_recorded_replay=False,  # 100% Real Live Run!
            project_name=self.project_name,
            test_identifier=f"{self.project_name}::{self.test_target}",
            stage1_baseline=stage1_baseline,
            stage2_ledger=stage2_ledger,
            triggering_stress_condition=triggering_condition,
            fix_attempts=fix_attempts,
            final_verdict=final_verdict,
            models_used={
                "bulk_log_reading": MODEL_FAST,
                "deep_reasoning": MODEL_REASONING,
            },
        )

        # Validate schema and persist trace
        trace_json = trace.model_dump_json(indent=2)
        self.output_trace_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_trace_path.write_text(trace_json, encoding="utf-8")
        logger.info("Saved validated CoinflipCertificateTrace to %s", self.output_trace_path)

        return trace
