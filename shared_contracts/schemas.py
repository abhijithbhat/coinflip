from __future__ import annotations

from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field


class PerturbationType(str, Enum):
    """The 7 OS stress and execution perturbation conditions for Coinflip."""
    BASELINE = "baseline"
    SHUFFLE_ORDER = "shuffle_order"
    SEED_CHANGE = "seed_change"
    CLOCK_SHIFT = "clock_shift"
    NETWORK_CUT = "network_cut"
    CPU_HALF_CORES = "cpu_half_cores"
    CPU_HEAVY_LOAD = "cpu_heavy_load"


class CausalInferenceMetrics(BaseModel):
    """Causal inference and contingency statistical significance metrics."""
    fisher_p_value: float = Field(..., description="p-value from 2x2 contingency analysis / Fisher exact test")
    relative_risk: float = Field(..., description="Relative risk ratio (stress failure rate / baseline failure rate)")
    absolute_rate_delta: float = Field(..., description="Absolute change in failure rate under perturbation")
    is_statistically_significant: bool = Field(..., description="Whether p_value < 0.05 rejecting null hypothesis")


class ASTGatekeeperReport(BaseModel):
    """Deterministic AST semantic anti-cheat gatekeeper audit report."""
    passed_gatekeeper: bool = Field(..., description="True if patch preserves assertions and does not suppress tests")
    status_code: Literal[
        "VERIFIED_CLEAN",
        "WARN_SLEEP_INFLATION",
        "BLOCKED_ASSERTION_TAMPERING",
        "BLOCKED_TEST_SUPPRESSION",
    ] = Field(..., description="Categorical outcome from AST analysis")
    original_assert_count: int = Field(..., description="Count of meaningful assertions in original test code")
    patched_assert_count: int = Field(..., description="Count of meaningful assertions in patched test code")
    assertions_preserved: bool = Field(..., description="Whether original assertion invariants were preserved")
    no_skip_decorators: bool = Field(..., description="True if no @pytest.mark.skip or skip decorators were introduced")
    no_bare_exception_swallowing: bool = Field(..., description="True if no try/except pass assertion swallowing detected")
    sleep_inflation_detected: bool = Field(..., description="True if time.sleep was increased without adding synchronization")
    synchronization_primitives_detected: list[str] = Field(
        default_factory=list,
        description="List of detected synchronization mechanisms (e.g. wait_for_completion, Event, Lock)",
    )
    summary: str = Field(..., description="Human-readable explanation of AST analysis verdict")


class SPRTExecutionTelemetry(BaseModel):
    """Sequential Probability Ratio Test (SPRT) early-stopping telemetry."""
    enabled: bool = Field(default=True, description="Whether SPRT early stopping was active")
    early_stopped: bool = Field(..., description="Whether the batch terminated before full run budget")
    decision: Literal["EARLY_REJECT_STRESS", "FULL_SAMPLE_CERTIFIED", "FULL_SAMPLE_REJECTED"] = Field(
        ...,
        description="SPRT boundary decision",
    )
    runs_executed_stress: int = Field(..., description="Actual runs completed under stress before decision")
    target_runs_stress: int = Field(..., description="Nominal target run budget (e.g. 1000)")
    runs_saved: int = Field(..., description="Compute runs saved by early stopping (target - executed)")
    compute_saved_pct: float = Field(..., description="Percentage of compute runs saved (0.0 to 100.0)")
    log_likelihood_ratio: float = Field(..., description="Final Wald log-likelihood ratio")
    rejection_threshold_b: float = Field(..., description="Wald boundary B threshold for rejection")


class ThreadRaceTimelineProfile(BaseModel):
    """Sub-millisecond thread execution race and safety margin timeline telemetry."""
    measured_quiet_worker_ms: float = Field(..., description="Worker task duration on quiet baseline machine (ms)")
    measured_quiet_assert_ms: float = Field(..., description="Time to test assertion check on quiet machine (ms)")
    quiet_margin_ms: float = Field(..., description="Safety margin on quiet machine (assert_ms - worker_ms)")
    measured_stress_worker_ms: float = Field(..., description="Worker task duration under CPU stress (ms)")
    measured_stress_assert_ms: float = Field(..., description="Time to test assertion check under CPU stress (ms)")
    stress_race_violation_ms: float = Field(
        ...,
        description="Race violation delta under CPU stress (negative indicates worker finished after assert)",
    )
    explanation: str = Field(..., description="Plain-English explanation of thread race timeline")


class CryptographicAttestation(BaseModel):
    """SHA-256 Merkle tree cryptographic integrity proof for Coinflip certificate traces."""
    algorithm: str = Field(default="SHA-256-Merkle", description="Hashing and tree aggregation algorithm")
    repo_snapshot_sha256: str = Field(..., description="Deterministic SHA-256 hash of repository snapshot files")
    patch_diff_sha256: str = Field(..., description="SHA-256 hash of the certified git diff patch")
    experiment_ledger_merkle_root: str = Field(
        ...,
        description="Binary SHA-256 Merkle root across all Stage 1, 2, and 4 experiment records",
    )
    certificate_digest_sha256: str = Field(
        ...,
        description="Signed certificate digest binding repo, patch, ledger root, and verdict",
    )
    verified: bool = Field(default=True, description="Whether attestation passed cryptographic verification")


class SingleRunResult(BaseModel):
    """Telemetry and outcome of an individual test invocation."""
    run_id: int = Field(..., description="Unique sequence index for this run within the batch")
    passed: bool = Field(..., description="Whether the test passed (exit_code == 0)")
    exit_code: int = Field(..., description="Process exit code from test runner")
    duration_ms: float = Field(..., description="Execution wall-clock time in milliseconds")
    error_snippet: Optional[str] = Field(
        default=None,
        description="Truncated error message or stack trace if test failed",
    )


class BatchExperimentResult(BaseModel):
    """Aggregated statistical outcome of a parallel batch under a specific perturbation condition.
    
    Used in Stage 1 (Baseline measurement), Stage 2 (Stress ledger), and Stage 4 (Certification).
    """
    perturbation: PerturbationType = Field(..., description="Perturbation condition tested")
    label: str = Field(..., description="Human-readable description of this condition")
    total_runs: int = Field(..., description="Total number of runs in this experiment batch")
    failures: int = Field(..., description="Number of failed runs")
    passes: int = Field(..., description="Number of passed runs")
    failure_rate: float = Field(..., description="Observed failure rate (failures / total_runs)")
    ci_95_lower: float = Field(..., description="Lower bound of 95% Wilson score confidence interval")
    ci_95_upper: float = Field(..., description="Upper bound of 95% Wilson score confidence interval")
    execution_backend: str = Field(
        ...,
        description="Execution engine backend: 'nebius_sandbox' or 'local_isolated'",
    )
    sample_failure_logs: list[str] = Field(
        default_factory=list,
        description="Up to 10 unique failure tracebacks or stderr logs captured from failed runs",
    )
    run_dots: list[bool] = Field(
        default_factory=list,
        description="Chronological pass/fail indicators (True=pass, False=fail) for UI dot-matrix",
    )
    causal_metrics: Optional[CausalInferenceMetrics] = Field(
        default=None,
        description="Optional causal inference and statistical significance metrics",
    )


class CandidateFixEvaluation(BaseModel):
    """Result of evaluating an AI-generated patch under normal and stress conditions in Stages 3 & 4."""
    attempt_number: int = Field(..., description="Sequential attempt count (1-based)")
    fix_title: str = Field(
        ...,
        description="Short summary of the candidate patch (e.g., 'Quick Fix: Raise timeout' vs 'Coinflip Fix: Event sync')",
    )
    root_cause_diagnosis: str = Field(
        ...,
        description="Explanation of the underlying bug generated by deep reasoning model",
    )
    git_diff_patch: str = Field(..., description="Standard Unified Git Diff representing the proposed patch")
    normal_cert_result: BatchExperimentResult = Field(
        ...,
        description="Verification batch under normal/baseline conditions (e.g. 1,000 runs)",
    )
    stress_cert_result: BatchExperimentResult = Field(
        ...,
        description="Verification batch under the triggering stress condition (e.g. 1,000 runs)",
    )
    upper_bound_95_normal: float = Field(
        ...,
        description="95% confidence upper bound on failure rate under normal conditions",
    )
    upper_bound_95_stress: float = Field(
        ...,
        description="95% confidence upper bound on failure rate under stress conditions",
    )
    target_limit: float = Field(
        default=0.005,
        description="Maximum acceptable failure rate threshold (default 0.005 or 0.5%)",
    )
    verdict: Literal["CERTIFIED", "REJECTED", "BROKEN"] = Field(
        ...,
        description="Evaluation verdict: CERTIFIED if both normal & stress upper bounds <= target_limit, REJECTED if stress fails, BROKEN if normal fails",
    )
    rejection_reason: Optional[str] = Field(
        default=None,
        description="Detailed explanation if verdict is REJECTED or BROKEN",
    )
    ast_audit: Optional[ASTGatekeeperReport] = Field(
        default=None,
        description="Optional AST semantic gatekeeper anti-cheat audit report",
    )
    sprt_telemetry: Optional[SPRTExecutionTelemetry] = Field(
        default=None,
        description="Optional sequential probability ratio test early-stopping telemetry",
    )


class CoinflipCertificateTrace(BaseModel):
    """Complete, end-to-end trace artifact representing Stages 1 through 5 of a Coinflip run.
    
    Powers UI Replay Mode, live dashboard telemetry, and deterministic validation reports.
    """
    trace_id: str = Field(..., description="Unique identifier for this trace session or replay")
    timestamp_utc: str = Field(..., description="ISO 8601 UTC timestamp of execution")
    is_recorded_replay: bool = Field(
        ...,
        description="True if this is pre-recorded reference data for demo/replay; False if produced live",
    )
    project_name: str = Field(..., description="Target repository or service name")
    test_identifier: str = Field(..., description="Fully-qualified test path or test function name")
    stage1_baseline: BatchExperimentResult = Field(
        ...,
        description="Stage 1: Initial baseline measurement of flakiness",
    )
    stage2_ledger: list[BatchExperimentResult] = Field(
        ...,
        description="Stage 2: Perturbation ledger testing all 7 conditions",
    )
    triggering_stress_condition: PerturbationType = Field(
        ...,
        description="The condition identified as dramatically amplifying the flake rate",
    )
    fix_attempts: list[CandidateFixEvaluation] = Field(
        ...,
        description="Stages 3 & 4: Sequence of candidate patches and their stress-certification results",
    )
    final_verdict: Literal["PASS", "NOT_YET_CERTIFIED"] = Field(
        ...,
        description="Overall certificate verdict: PASS if a fix is CERTIFIED under stress; NOT_YET_CERTIFIED otherwise",
    )
    models_used: dict[str, str] = Field(
        ...,
        description="Mapping of role to model ID used (e.g. bulk log reading vs deep reasoning)",
    )
    race_timeline: Optional[ThreadRaceTimelineProfile] = Field(
        default=None,
        description="Optional sub-millisecond thread race timeline telemetry",
    )
    attestation: Optional[CryptographicAttestation] = Field(
        default=None,
        description="Optional SHA-256 Merkle cryptographic attestation",
    )
    nemotron_reasoning_trace: Optional[str] = Field(
        default=None,
        description="Optional full reasoning trace captured from Nemotron 3 Ultra",
    )
