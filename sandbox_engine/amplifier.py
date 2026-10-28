"""Flake Amplifier: Adaptive Successive-Halving Thompson-Prior Search Engine for Coinflip.

Performs a 3-stage adaptive perturbation intensity search:
1. Round 1: Wide probe of top 4 candidate arms prioritized by Nemotron prior.
2. Round 2: Focused probe on top 2 surviving arms.
3. Round 3: Independent out-of-sample confirmation batch to prevent winner's curse.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

from sandbox_engine.batch_runner import SandboxBatchRunner
from sandbox_engine.math_utils import wilson_ci_95
from shared_contracts.schemas import (
    AmplifierArmResult,
    BatchExperimentResult,
    FlakeAmplifierReport,
    PerturbationIntensity,
    PerturbationType,
)

logger = logging.getLogger("sandbox_engine.amplifier")


class FlakeAmplifier:
    """Adaptive amplification search engine that discovers and confirms the optimal stress arm."""

    def __init__(
        self,
        batch_runner: SandboxBatchRunner,
        workspace_dir: Path | str,
        test_target: str,
        baseline_result: BatchExperimentResult,
        hypotheses: list[dict[str, Any]] | dict[str, Any],
        exploration_budget: int = 60,
        confirmation_budget: int = 40,
        fast_live_mode: bool = False,
        prior_results: dict[Any, BatchExperimentResult] | None = None,
    ) -> None:
        self.batch_runner = batch_runner
        self.workspace_dir = Path(workspace_dir).resolve()
        self.test_target = test_target
        self.baseline_result = baseline_result
        self.fast_live_mode = fast_live_mode
        self.prior_results = prior_results or {}

        # Parse hypotheses input
        if isinstance(hypotheses, dict):
            raw_arms = hypotheses.get("candidate_arms") or hypotheses.get("hypotheses") or []
            self.hypothesis_model = str(hypotheses.get("hypothesis_model", "nvidia/Nemotron-3_5-Lightning"))
            self.hypothesis_completion_id = hypotheses.get("hypothesis_completion_id")
            self.hypothesis_source: Literal["nemotron_live", "ast_heuristic_fallback"] = hypotheses.get(
                "hypothesis_source", "nemotron_live"
            )
            self.ast_detected_signals = list(hypotheses.get("ast_detected_signals", []))
        else:
            raw_arms = list(hypotheses)
            self.hypothesis_model = "nvidia/Nemotron-3_5-Lightning"
            self.hypothesis_completion_id = None
            self.hypothesis_source = "nemotron_live"
            self.ast_detected_signals = []

        self.candidate_arms = list(raw_arms[:4])

        # Allocate budget
        if fast_live_mode:
            if self.prior_results:
                self.exploration_budget = 20
                self.confirmation_budget = 20
                self.r1_runs = 0
                self.r2_runs = 10
            else:
                self.exploration_budget = exploration_budget if exploration_budget != 60 else 24
                self.confirmation_budget = confirmation_budget if confirmation_budget != 40 else 20
                if self.exploration_budget >= 28:
                    self.r1_runs = 4
                    self.r2_runs = 6
                else:
                    self.r1_runs = 3
                    self.r2_runs = 6
        else:
            self.exploration_budget = exploration_budget
            self.confirmation_budget = confirmation_budget
            self.r1_runs = 8 if exploration_budget == 60 else max(1, exploration_budget // 8)
            remaining = self.exploration_budget - (self.r1_runs * 4)
            self.r2_runs = 14 if exploration_budget == 60 else max(1, remaining // 2)

    async def run(self) -> tuple[FlakeAmplifierReport, BatchExperimentResult]:
        """Executes the full 3-stage adaptive search and confirmation.

        Returns:
            tuple[FlakeAmplifierReport, BatchExperimentResult]: Complete report and confirmation batch result.
        """
        # Ensure we have 4 candidate arms
        if len(self.candidate_arms) < 4:
            from sandbox_engine.llm_bridge import _heuristic_hypotheses

            defaults = _heuristic_hypotheses(self.ast_detected_signals)
            for d in defaults:
                if len(self.candidate_arms) >= 4:
                    break
                if not any(a.get("arm_id") == d.get("arm_id") for a in self.candidate_arms):
                    self.candidate_arms.append(d)

        runs_to_first_failure: int | None = None
        cumulative_runs = 0

        # ---------------------------------------------------------------------
        # ROUND 1: SUCCESSIVE HALVING WIDE PROBE
        # ---------------------------------------------------------------------
        logger.info(
            "[AMPLIFIER ROUND 1] Probing top %d candidate arms with %d runs per arm...",
            len(self.candidate_arms),
            self.r1_runs,
        )
        arm_state: dict[str, dict[str, Any]] = {}
        for arm_meta in self.candidate_arms:
            pert = PerturbationType(arm_meta["perturbation"])
            intensity = PerturbationIntensity(arm_meta["intensity"])
            arm_id = str(arm_meta.get("arm_id", f"{pert.value}:{intensity.value}"))
            rank = int(arm_meta.get("nemotron_prior_rank", 1))
            rationale = str(arm_meta.get("nemotron_rationale", ""))

            # Reuse Stage 2 prior batch results if available (0 extra runs!)
            prior_match = None
            if self.prior_results:
                if (pert, intensity) in self.prior_results:
                    prior_match = self.prior_results[(pert, intensity)]
                elif pert in self.prior_results:
                    prior_match = self.prior_results[pert]
                elif pert.value in self.prior_results:
                    prior_match = self.prior_results[pert.value]

            if prior_match is not None:
                batch_res = prior_match
            else:
                batch_res = await self.batch_runner.run_batch(
                    perturbation=pert,
                    num_runs=max(1, self.r1_runs),
                    intensity=intensity,
                )

            if batch_res.run_dots:
                for passed in batch_res.run_dots:
                    cumulative_runs += 1
                    if not passed and runs_to_first_failure is None:
                        runs_to_first_failure = cumulative_runs
            else:
                if batch_res.failures > 0 and runs_to_first_failure is None:
                    runs_to_first_failure = cumulative_runs + 1
                cumulative_runs += batch_res.total_runs

            prior_weight = max(0.0, (5 - rank) * 0.1)
            posterior_score = (batch_res.failures + prior_weight) / (batch_res.total_runs + 1.0)

            arm_state[arm_id] = {
                "arm_id": arm_id,
                "perturbation": pert,
                "intensity": intensity,
                "nemotron_prior_rank": rank,
                "nemotron_rationale": rationale,
                "round1_runs": batch_res.total_runs,
                "round1_failures": batch_res.failures,
                "round2_runs": 0,
                "round2_failures": 0,
                "posterior_score": posterior_score,
                "eliminated_in_round": None,
            }

        sorted_r1 = sorted(arm_state.values(), key=lambda x: x["posterior_score"], reverse=True)
        surviving_arms = sorted_r1[:2]
        eliminated_r1 = sorted_r1[2:]
        for arm in eliminated_r1:
            arm["eliminated_in_round"] = 1

        # ---------------------------------------------------------------------
        # ROUND 2: SUCCESSIVE HALVING FOCUSED PROBE
        # ---------------------------------------------------------------------
        logger.info(
            "[AMPLIFIER ROUND 2] Probing top 2 surviving arms (%s, %s) with %d runs per arm...",
            surviving_arms[0]["arm_id"],
            surviving_arms[1]["arm_id"],
            self.r2_runs,
        )
        for arm in surviving_arms:
            pert = arm["perturbation"]
            intensity = arm["intensity"]

            batch_res = await self.batch_runner.run_batch(
                perturbation=pert,
                num_runs=self.r2_runs,
                intensity=intensity,
            )

            if batch_res.run_dots:
                for passed in batch_res.run_dots:
                    cumulative_runs += 1
                    if not passed and runs_to_first_failure is None:
                        runs_to_first_failure = cumulative_runs
            else:
                if batch_res.failures > 0 and runs_to_first_failure is None:
                    runs_to_first_failure = cumulative_runs + 1
                cumulative_runs += batch_res.total_runs

            arm["round2_runs"] = batch_res.total_runs
            arm["round2_failures"] = batch_res.failures

        for arm in sorted_r1:
            total_exp_runs = arm["round1_runs"] + arm["round2_runs"]
            total_exp_fails = arm["round1_failures"] + arm["round2_failures"]
            arm["total_exploration_runs"] = total_exp_runs
            arm["total_exploration_failures"] = total_exp_fails
            arm["exploration_failure_rate"] = round(total_exp_fails / total_exp_runs, 4) if total_exp_runs > 0 else 0.0

        sorted_r2 = sorted(
            surviving_arms,
            key=lambda x: (x["exploration_failure_rate"], -x["nemotron_prior_rank"]),
            reverse=True,
        )
        winner = sorted_r2[0]
        runner_up = sorted_r2[1]
        winner["eliminated_in_round"] = None
        runner_up["eliminated_in_round"] = 2

        # ---------------------------------------------------------------------
        # ROUND 3: OUT-OF-SAMPLE CONFIRMATION BATCH (WINNER'S CURSE PREVENTION)
        # ---------------------------------------------------------------------
        winning_pert = winner["perturbation"]
        winning_intensity = winner["intensity"]
        winning_arm_id = winner["arm_id"]
        logger.info(
            "[AMPLIFIER ROUND 3] Confirming winning arm %s out-of-sample with %d runs...",
            winning_arm_id,
            self.confirmation_budget,
        )

        confirmation_res = await self.batch_runner.run_batch(
            perturbation=winning_pert,
            num_runs=self.confirmation_budget,
            intensity=winning_intensity,
        )

        if confirmation_res.run_dots:
            for passed in confirmation_res.run_dots:
                cumulative_runs += 1
                if not passed and runs_to_first_failure is None:
                    runs_to_first_failure = cumulative_runs
        else:
            if confirmation_res.failures > 0 and runs_to_first_failure is None:
                runs_to_first_failure = cumulative_runs + 1
            cumulative_runs += confirmation_res.total_runs

        conf_runs = confirmation_res.total_runs
        conf_failures = confirmation_res.failures
        confirmed_failure_rate = round(conf_failures / conf_runs, 4) if conf_runs > 0 else 0.0
        ci_lower, ci_upper = wilson_ci_95(conf_failures, conf_runs)

        base_rate = max(self.baseline_result.failure_rate, 0.01)
        amplification_factor = round(confirmed_failure_rate / base_rate, 2)

        # ---------------------------------------------------------------------
        # CONSTRUCT LEADERBOARD AND REPORT
        # ---------------------------------------------------------------------
        leaderboard_arms = [winner, runner_up] + eliminated_r1
        leaderboard = [
            AmplifierArmResult(
                arm_id=a["arm_id"],
                perturbation=a["perturbation"],
                intensity=a["intensity"],
                nemotron_prior_rank=a["nemotron_prior_rank"],
                nemotron_rationale=a["nemotron_rationale"],
                round1_runs=a["round1_runs"],
                round1_failures=a["round1_failures"],
                round2_runs=a["round2_runs"],
                round2_failures=a["round2_failures"],
                total_exploration_runs=a["total_exploration_runs"],
                total_exploration_failures=a["total_exploration_failures"],
                exploration_failure_rate=a["exploration_failure_rate"],
                eliminated_in_round=a["eliminated_in_round"],
            )
            for a in leaderboard_arms
        ]

        total_exp_runs_all = sum(a.total_exploration_runs for a in leaderboard)

        report = FlakeAmplifierReport(
            enabled=True,
            hypothesis_model=self.hypothesis_model,
            hypothesis_completion_id=self.hypothesis_completion_id,
            hypothesis_source=self.hypothesis_source,
            ast_detected_signals=self.ast_detected_signals,
            search_algorithm="successive_halving_thompson",
            exploration_budget=total_exp_runs_all,
            confirmation_budget=conf_runs,
            winning_arm_id=winning_arm_id,
            winning_perturbation=winning_pert,
            winning_intensity=winning_intensity,
            baseline_failure_rate=self.baseline_result.failure_rate,
            confirmation_runs=conf_runs,
            confirmation_failures=conf_failures,
            confirmed_failure_rate=confirmed_failure_rate,
            confirmed_ci_95_lower=ci_lower,
            confirmed_ci_95_upper=ci_upper,
            amplification_factor=amplification_factor,
            runs_to_first_failure=runs_to_first_failure,
            leaderboard=leaderboard,
        )

        logger.info(
            "[AMPLIFIER COMPLETE] Winning arm: %s | Confirmed: %d/%d (%.1f%%) | Amplification: %.2fx",
            winning_arm_id,
            conf_failures,
            conf_runs,
            confirmed_failure_rate * 100,
            amplification_factor,
        )

        return report, confirmation_res

    # Convenience alias
    run_adaptive_search = run
