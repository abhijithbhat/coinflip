"""Stage 4 Candidate Fix Verifier and Stress Certifier for Coinflip.

Implements the statistical certification gate from Page 9 of the Concept Brief:
- Pre-flight AST Semantic Anti-Cheat Gatekeeper: Rejects assertion tampering and skip decorators
  before executing any test runs (0 compute wasted!).
- Wald's Sequential Probability Ratio Test (SPRT) Early-Stopping: Samples stress runs in probe
  chunks and terminates immediately upon detecting stress flakiness (saving 90%+ compute!).
- 1,000-Run Dual-Condition Certification: Evaluates full normal and stress batches under the
  Rule of Three (< 0.30% UCB at 95% confidence).
- Assigns verdicts: CERTIFIED, REJECTED, or BROKEN.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

from sandbox_engine.ast_gatekeeper import ASTSemanticGatekeeper
from sandbox_engine.batch_runner import SandboxBatchRunner
from sandbox_engine.image_builder import SandboxImageBuilder
from sandbox_engine.math_utils import upper_confidence_bound_95, wald_sprt_check, wilson_ci_95
from shared_contracts.schemas import (
    BatchExperimentResult,
    CandidateFixEvaluation,
    PerturbationType,
    SPRTExecutionTelemetry,
)

logger = logging.getLogger("sandbox_engine.patch_verifier")


class Stage4PatchVerifier:
    """Certifies AI-generated candidate patches against quiet and stress test conditions."""

    def __init__(
        self,
        image_builder: SandboxImageBuilder,
        base_snapshot_id: str,
        test_target: str,
        max_concurrency: int = 45,
        mode: Literal["auto", "local_isolated", "nebius_sandbox"] = "auto",
        stats_provider: Any = None,
    ) -> None:
        self.image_builder = image_builder
        self.base_snapshot_id = base_snapshot_id
        self.test_target = test_target
        self.max_concurrency = max_concurrency
        self.mode = mode
        self.ast_gatekeeper = ASTSemanticGatekeeper()

        if stats_provider is not None:
            self.stats_provider = stats_provider
        else:
            try:
                import agent_and_ui.stats_engine as tejas_stats  # type: ignore
                self.stats_provider = tejas_stats
            except (ImportError, ModuleNotFoundError):
                import sandbox_engine.math_utils as fallback_stats
                self.stats_provider = fallback_stats

    async def verify_patch(
        self,
        attempt_number: int,
        fix_title: str,
        root_cause_diagnosis: str,
        patch_content: str | dict[str, str],
        triggering_stress_condition: PerturbationType = PerturbationType.CPU_HEAVY_LOAD,
        cert_runs: int = 1000,
        target_limit: float = 0.005,
        target_file_rel: str | None = None,
        enable_sprt: bool = True,
        probe_chunk_size: int = 50,
    ) -> CandidateFixEvaluation:
        """Evaluates a candidate fix across both normal and stress conditions with AST & SPRT.

        Args:
            attempt_number: Sequential attempt count (1, 2, ...).
            fix_title: Descriptive name of the candidate patch.
            root_cause_diagnosis: Diagnostic explanation from deep reasoning model.
            patch_content: Unified diff or replacement dict representing the fix.
            triggering_stress_condition: The condition identified in Stage 2 that exposed the flake.
            cert_runs: Number of runs per condition (default 1,000).
            target_limit: Upper bound threshold for certification (default 0.005 or 0.5%).
            target_file_rel: Optional relative file path for single-file patches.
            enable_sprt: Whether to apply Wald's SPRT early-stopping on stress runs.
            probe_chunk_size: Initial stress probe chunk size (default 50).

        Returns:
            CandidateFixEvaluation: Validated Stage 4 certification result.
        """
        base_path = self.image_builder.get_snapshot_path(self.base_snapshot_id)
        target_file = target_file_rel or self.test_target
        target_full_path = base_path / target_file
        orig_code = target_full_path.read_text(encoding="utf-8") if target_full_path.exists() else ""

        # ---------------------------------------------------------------------
        # STEP A: PRE-FLIGHT AST SEMANTIC ANTI-CHEAT GATEKEEPER
        # ---------------------------------------------------------------------
        ast_report = None
        diff_str = patch_content if isinstance(patch_content, str) else str(patch_content)

        if orig_code:
            try:
                ast_report = self.ast_gatekeeper.audit(orig_code, diff_str)
                if not ast_report.passed_gatekeeper:
                    logger.warning(
                        "Pre-flight AST Gatekeeper rejected patch '%s': %s",
                        fix_title,
                        ast_report.summary,
                    )
                    # Block immediately with 0 Sandbox runs executed
                    dummy_res = BatchExperimentResult(
                        perturbation=PerturbationType.BASELINE,
                        label="Pre-flight Blocked (0 runs)",
                        total_runs=0,
                        failures=0,
                        passes=0,
                        failure_rate=0.0,
                        ci_95_lower=0.0,
                        ci_95_upper=1.0,
                        execution_backend="local_isolated",
                        sample_failure_logs=[],
                        run_dots=[],
                    )
                    return CandidateFixEvaluation(
                        attempt_number=attempt_number,
                        fix_title=fix_title,
                        root_cause_diagnosis=root_cause_diagnosis,
                        git_diff_patch=diff_str,
                        normal_cert_result=dummy_res,
                        stress_cert_result=dummy_res,
                        upper_bound_95_normal=1.0,
                        upper_bound_95_stress=1.0,
                        target_limit=target_limit,
                        verdict="REJECTED",
                        rejection_reason=f"Pre-flight AST Gatekeeper rejected patch: {ast_report.summary}",
                        ast_audit=ast_report,
                        sprt_telemetry=None,
                    )
            except Exception as e:
                logger.warning("AST Gatekeeper check encountered exception (skipping pre-flight block): %s", e)

        # ---------------------------------------------------------------------
        # STEP B: CREATE PATCHED SNAPSHOT & EXECUTE VERIFICATION BATCHES
        # ---------------------------------------------------------------------
        patched_snapshot_id = self.image_builder.create_patched_snapshot(
            base_snapshot_id=self.base_snapshot_id,
            patch_content=patch_content,
            target_file_rel=target_file_rel,
        )
        patched_path = self.image_builder.get_snapshot_path(patched_snapshot_id)

        try:
            runner = SandboxBatchRunner(
                repo_dir=patched_path,
                test_target=self.test_target,
                max_concurrency=self.max_concurrency,
                mode=self.mode,
            )

            sprt_telemetry: SPRTExecutionTelemetry | None = None

            # Path 1: Wald's SPRT Early Stopping on Stress Runs
            if enable_sprt and cert_runs >= 100:
                logger.info(
                    "Running SPRT initial probe chunk (%d runs) under %s for '%s'...",
                    probe_chunk_size,
                    triggering_stress_condition.value,
                    fix_title,
                )
                stress_probe = await runner.run_batch(
                    perturbation=triggering_stress_condition,
                    num_runs=probe_chunk_size,
                )

                sprt_eval = wald_sprt_check(
                    failures=stress_probe.failures,
                    runs_done=stress_probe.total_runs,
                    target_runs=cert_runs,
                    target_limit=target_limit,
                )

                if sprt_eval.decision == "EARLY_REJECT_STRESS":
                    logger.info(
                        "SPRT early-stop triggered! Rejection confirmed in %d runs (saved %d runs / %.1f%% compute).",
                        stress_probe.total_runs,
                        sprt_eval.runs_saved,
                        sprt_eval.compute_saved_pct,
                    )
                    # Run matching quiet baseline probe to establish that it looked fine on a quiet machine
                    normal_result = await runner.run_batch(
                        perturbation=PerturbationType.BASELINE,
                        num_runs=probe_chunk_size,
                    )
                    stress_result = stress_probe
                    sprt_telemetry = sprt_eval

                else:
                    # Stress probe completed cleanly (0 failures) -> Run remaining stress runs
                    remaining_stress = cert_runs - probe_chunk_size
                    if remaining_stress > 0:
                        logger.info(
                            "Probe clean (0 failures). Completing remaining %d stress runs for '%s'...",
                            remaining_stress,
                            fix_title,
                        )
                        remaining_res = await runner.run_batch(
                            perturbation=triggering_stress_condition,
                            num_runs=remaining_stress,
                        )
                        # Aggregate stress probe + remaining
                        total_runs = stress_probe.total_runs + remaining_res.total_runs
                        failures = stress_probe.failures + remaining_res.failures
                        passes = stress_probe.passes + remaining_res.passes
                        ci_stress = wilson_ci_95(failures, total_runs)
                        stress_result = BatchExperimentResult(
                            perturbation=triggering_stress_condition,
                            label=stress_probe.label,
                            total_runs=total_runs,
                            failures=failures,
                            passes=passes,
                            failure_rate=round(failures / total_runs, 4) if total_runs else 0.0,
                            ci_95_lower=ci_stress[0],
                            ci_95_upper=ci_stress[1],
                            execution_backend=stress_probe.execution_backend,
                            sample_failure_logs=stress_probe.sample_failure_logs + remaining_res.sample_failure_logs,
                            run_dots=stress_probe.run_dots + remaining_res.run_dots,
                        )
                    else:
                        stress_result = stress_probe

                    # Run full normal certification runs
                    logger.info("Running %d normal certification runs for '%s'...", cert_runs, fix_title)
                    normal_result = await runner.run_batch(
                        perturbation=PerturbationType.BASELINE,
                        num_runs=cert_runs,
                    )

                    sprt_telemetry = wald_sprt_check(
                        failures=stress_result.failures,
                        runs_done=stress_result.total_runs,
                        target_runs=cert_runs,
                        target_limit=target_limit,
                    )

            else:
                # Standard non-SPRT execution
                logger.info("Running %d normal certification runs for '%s'...", cert_runs, fix_title)
                normal_result = await runner.run_batch(
                    perturbation=PerturbationType.BASELINE,
                    num_runs=cert_runs,
                )
                logger.info(
                    "Running %d stress certification runs under %s for '%s'...",
                    cert_runs,
                    triggering_stress_condition.value,
                    fix_title,
                )
                stress_result = await runner.run_batch(
                    perturbation=triggering_stress_condition,
                    num_runs=cert_runs,
                )
                sprt_telemetry = wald_sprt_check(
                    failures=stress_result.failures,
                    runs_done=stress_result.total_runs,
                    target_runs=cert_runs,
                    target_limit=target_limit,
                )

            # Compute upper confidence bounds
            upper_bound_normal = self.stats_provider.upper_confidence_bound_95(
                normal_result.failures, normal_result.total_runs
            )
            upper_bound_stress = self.stats_provider.upper_confidence_bound_95(
                stress_result.failures, stress_result.total_runs
            )

            # Assign Coinflip Certification Verdict Rules
            if normal_result.failures > 0:
                verdict: Literal["CERTIFIED", "REJECTED", "BROKEN"] = "BROKEN"
                rejection_reason = (
                    f"Candidate fix fails under normal baseline conditions: "
                    f"{normal_result.failures}/{normal_result.total_runs} failed "
                    f"({normal_result.failure_rate * 100:.1f}% failure rate)."
                )

            elif stress_result.failures > 0 or (sprt_telemetry and sprt_telemetry.decision == "EARLY_REJECT_STRESS"):
                verdict = "REJECTED"
                early_msg = (
                    f" [SPRT early-stopped at {stress_result.total_runs} runs: "
                    f"saved {sprt_telemetry.runs_saved} runs / {sprt_telemetry.compute_saved_pct}% compute]"
                    if (sprt_telemetry and sprt_telemetry.early_stopped)
                    else ""
                )
                rejection_reason = (
                    f"Looks fixed on a quiet machine ({normal_result.passes}/{normal_result.total_runs} passed), "
                    f"but fails under {triggering_stress_condition.value} stress: "
                    f"{stress_result.failures}/{stress_result.total_runs} failed "
                    f"({stress_result.failure_rate * 100:.1f}%).{early_msg}"
                )

            elif cert_runs >= 600 and (upper_bound_normal > target_limit or upper_bound_stress > target_limit):
                verdict = "REJECTED"
                rejection_reason = (
                    f"Upper bound under stress ({upper_bound_stress * 100:.2f}%) "
                    f"exceeds target limit ({target_limit * 100:.2f}%)."
                )

            else:
                verdict = "CERTIFIED"
                rejection_reason = None

            return CandidateFixEvaluation(
                attempt_number=attempt_number,
                fix_title=fix_title,
                root_cause_diagnosis=root_cause_diagnosis,
                git_diff_patch=diff_str,
                normal_cert_result=normal_result,
                stress_cert_result=stress_result,
                upper_bound_95_normal=upper_bound_normal,
                upper_bound_95_stress=upper_bound_stress,
                target_limit=target_limit,
                verdict=verdict,
                rejection_reason=rejection_reason,
                ast_audit=ast_report,
                sprt_telemetry=sprt_telemetry,
            )

        finally:
            self.image_builder.cleanup_snapshot(patched_snapshot_id)
