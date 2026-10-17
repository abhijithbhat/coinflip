"""Perturbation manager for generating OS stress and runtime environments.

Translates PerturbationType conditions into environment variables, command-line
arguments, and execution parameters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import random

from shared_contracts.schemas import PerturbationType

HOOKS_MODULE_PATH = Path(__file__).parent / "_pytest_hooks.py"

PERTURBATION_LABELS: dict[PerturbationType, str] = {
    PerturbationType.BASELINE: "Normal run (baseline quiet machine)",
    PerturbationType.SHUFFLE_ORDER: "Randomized test execution order",
    PerturbationType.SEED_CHANGE: "Alternative random & hash seeds",
    PerturbationType.CLOCK_SHIFT: "Clock skew / timing offset (+1 hour)",
    PerturbationType.NETWORK_CUT: "Network cut (socket connections disabled)",
    PerturbationType.CPU_HALF_CORES: "Restricted CPU cores / affinity",
    PerturbationType.CPU_HEAVY_LOAD: "Heavy background CPU contention (4x load)",
}


@dataclass
class PerturbationContext:
    """Execution context generated for a single test run under a perturbation."""
    perturbation: PerturbationType
    label: str
    env_vars: dict[str, str] = field(default_factory=dict)
    pytest_args: list[str] = field(default_factory=list)
    needs_external_cpu_stress: bool = False


def get_perturbation_label(perturbation: PerturbationType) -> str:
    """Returns the descriptive human-readable label for a perturbation condition."""
    return PERTURBATION_LABELS.get(perturbation, perturbation.value)


def build_perturbation_context(
    perturbation: PerturbationType,
    run_id: int,
    base_seed: int = 1000,
) -> PerturbationContext:
    """Generates the environment variables and pytest arguments for a given run under a perturbation.

    Args:
        perturbation: The target PerturbationType.
        run_id: The run index within the batch (used to derive deterministic variant seeds).
        base_seed: Base seed for reproducible perturbation variance.

    Returns:
        PerturbationContext: Encapsulating env vars, pytest arguments, and stress flags.
    """
    label = get_perturbation_label(perturbation)
    env: dict[str, str] = {}
    pytest_args: list[str] = []
    external_cpu_stress = False

    # Unique seed derived from run_id for variance across runs
    run_seed = base_seed + run_id * 37

    if perturbation == PerturbationType.BASELINE:
        # Standard clean execution, no special perturbation flags
        pass

    elif perturbation == PerturbationType.SHUFFLE_ORDER:
        env["COINFLIP_SHUFFLE"] = "1"
        env["COINFLIP_RANDOM_SEED"] = str(run_seed)

    elif perturbation == PerturbationType.SEED_CHANGE:
        env["PYTHONHASHSEED"] = str(run_seed % 4294967295)
        env["COINFLIP_RANDOM_SEED"] = str(run_seed)

    elif perturbation == PerturbationType.CLOCK_SHIFT:
        # Shift clock forward by 1 hour (3600 seconds)
        env["COINFLIP_CLOCK_SHIFT_SEC"] = "3600.0"

    elif perturbation == PerturbationType.NETWORK_CUT:
        env["COINFLIP_NET_CUT"] = "1"

    elif perturbation == PerturbationType.CPU_HALF_CORES:
        env["COINFLIP_HALF_CORES"] = "1"
        env["OMP_NUM_THREADS"] = "1"
        env["MKL_NUM_THREADS"] = "1"
        env["OPENBLAS_NUM_THREADS"] = "1"
        env["NUMEXPR_NUM_THREADS"] = "1"

    elif perturbation == PerturbationType.CPU_HEAVY_LOAD:
        env["COINFLIP_CPU_LOAD"] = "1"
        external_cpu_stress = True

    return PerturbationContext(
        perturbation=perturbation,
        label=label,
        env_vars=env,
        pytest_args=pytest_args,
        needs_external_cpu_stress=external_cpu_stress,
    )
