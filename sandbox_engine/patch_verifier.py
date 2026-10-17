"""Stage 4 Candidate Fix Verifier and Stress Certifier for Coinflip.

Implements the statistical certification gate from Page 9 of the Concept Brief:
- Runs normal verification (e.g. 1,000 runs)
- Runs stress verification under the triggering condition (e.g. 1,000 runs)
- Evaluates 95% upper confidence bounds against the target limit (default 0.5%)
- Assigns verdicts: CERTIFIED, REJECTED, or BROKEN.
"""

from __future__ import annotations

import logging
from typing import Literal

from sandbox_engine.batch_runner import SandboxBatchRunner
from sandbox_engine.image_builder import SandboxImageBuilder
from sandbox_engine.math_utils import upper_confidence_bound_95
from shared_contracts.schemas import (
    CandidateFixEvaluation,
    PerturbationType,
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
    ) -> CandidateFixEvaluation:
        """Evaluates a candidate fix across both normal and stress conditions.

        Args:
            attempt_number: Sequential attempt count (1, 2, ...).
            fix_title: Descriptive name of the candidate patch.
            root_cause_diagnosis: Diagnostic explanation from deep reasoning model.
            patch_content: Unified diff or replacement dict representing the fix.
            triggering_stress_condition: The condition identified in Stage 2 that exposed the flake.
            cert_runs: Number of runs per condition (default 1,000).
            target_limit: Upper bound threshold for certification (default 0.005 or 0.5%).
            target_file_rel: Optional relative file path for single-file patches.

        Returns:
            CandidateFixEvaluation: Validated Stage 4 certification result.
        """
        # 1. Create a clean patched snapshot from the base snapshot
        patched_snapshot_id = self.image_builder.create_patched_snapshot(
            base_snapshot_id=self.base_snapshot_id,
            patch_content=patch_content,
            target_file_rel=target_file_rel,
        )
        patched_path = self.image_builder.get_snapshot_path(patched_snapshot_id)

        try:
            # 2. Build batch runner for the patched snapshot
            runner = SandboxBatchRunner(
                repo_dir=patched_path,
                test_target=self.test_target,
                max_concurrency=self.max_concurrency,
                mode=self.mode,
            )

            # 3. Stage 4A: Normal verification on a quiet machine (BASELINE)
            logger.info("Running %d normal certification runs for '%s'...", cert_runs, fix_title)
            normal_result = await runner.run_batch(
                perturbation=PerturbationType.BASELINE,
                num_runs=cert_runs,
            )

            # 4. Stage 4B: Stress verification under the triggering condition
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

            # 5. Compute conservative 95% upper confidence bounds
            upper_bound_normal = self.stats_provider.upper_confidence_bound_95(
                normal_result.failures, normal_result.total_runs
            )
            upper_bound_stress = self.stats_provider.upper_confidence_bound_95(
                stress_result.failures, stress_result.total_runs
            )

            # 6. Apply the Coinflip Certification Verdict Rules (Concept Brief Page 9)
            if normal_result.failures > 0:
                # Test fails even on quiet machine -> Broken patch
                verdict: Literal["CERTIFIED", "REJECTED", "BROKEN"] = "BROKEN"
                rejection_reason = (
                    f"Candidate fix fails under normal baseline conditions: "
                    f"{normal_result.failures}/{normal_result.total_runs} failed "
                    f"({normal_result.failure_rate * 100:.1f}% failure rate)."
                )

            elif stress_result.failures > 0:
                # Test passes on quiet machine but fails under stress -> Deceptive quick fix
                verdict = "REJECTED"
                rejection_reason = (
                    f"Looks fixed on a quiet machine (0/{normal_result.total_runs} failed), "
                    f"but fails under {triggering_stress_condition.value} stress: "
                    f"{stress_result.failures}/{stress_result.total_runs} failed "
                    f"({stress_result.failure_rate * 100:.1f}%)."
                )

            elif cert_runs >= 600 and (upper_bound_normal > target_limit or upper_bound_stress > target_limit):
                # When statistically powered (>=600 runs), upper bound must strictly satisfy target limit
                verdict = "REJECTED"
                rejection_reason = (
                    f"Upper bound under stress ({upper_bound_stress * 100:.2f}%) "
                    f"exceeds target limit ({target_limit * 100:.2f}%)."
                )

            else:
                # 0 failures under both quiet and stress (and upper bounds <= target_limit when powered) -> Certified
                verdict = "CERTIFIED"
                rejection_reason = None

            # Render git diff representation for trace
            diff_str = patch_content if isinstance(patch_content, str) else str(patch_content)

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
            )

        finally:
            # Clean up temporary patched snapshot directory
            self.image_builder.cleanup_snapshot(patched_snapshot_id)
