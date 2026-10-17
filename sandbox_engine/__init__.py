"""Sandbox execution engine for Coinflip.

Provides dual-mode microVM and local isolated test perturbation runners,
immutable snapshot management, Stage 4 patch verification, and the
5-stage CoinflipOrchestrator powered by NVIDIA Nemotron.
"""

from sandbox_engine.batch_runner import SandboxBatchRunner
from sandbox_engine.image_builder import SandboxImageBuilder
from sandbox_engine.llm_bridge import NemotronBridge
from sandbox_engine.math_utils import upper_confidence_bound_95, wilson_ci_95
from sandbox_engine.orchestrator import CoinflipOrchestrator
from sandbox_engine.patch_verifier import Stage4PatchVerifier
from sandbox_engine.perturbations import (
    PERTURBATION_LABELS,
    PerturbationContext,
    build_perturbation_context,
    get_perturbation_label,
)


def __getattr__(name: str):
    if name in ("verify_patch_in_sandbox", "verify_patch_in_sandbox_async"):
        from sandbox_engine.mcp_verifier_tool import (
            verify_patch_in_sandbox,
            verify_patch_in_sandbox_async,
        )
        if name == "verify_patch_in_sandbox":
            return verify_patch_in_sandbox
        return verify_patch_in_sandbox_async
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "CoinflipOrchestrator",
    "NemotronBridge",
    "SandboxBatchRunner",
    "SandboxImageBuilder",
    "Stage4PatchVerifier",
    "wilson_ci_95",
    "upper_confidence_bound_95",
    "build_perturbation_context",
    "get_perturbation_label",
    "PERTURBATION_LABELS",
    "PerturbationContext",
    "verify_patch_in_sandbox",
    "verify_patch_in_sandbox_async",
]
