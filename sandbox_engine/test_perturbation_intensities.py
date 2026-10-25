"""Unit tests for Flake Amplifier generic perturbation hooks and intensity levels."""

import errno
import random
import socket
import sys
import time

import pytest

from sandbox_engine._pytest_hooks import perturbation_runtime_context
from sandbox_engine.perturbations import (
    build_perturbation_context,
    resolve_default_intensity,
)
from shared_contracts.schemas import PerturbationIntensity, PerturbationType


def test_resolve_default_intensity():
    # Defaults when intensity is None:
    assert resolve_default_intensity(PerturbationType.CPU_HEAVY_LOAD, None) == PerturbationIntensity.L3_EXTREME
    assert resolve_default_intensity(PerturbationType.CPU_HALF_CORES, None) == PerturbationIntensity.L1_MILD
    assert resolve_default_intensity(PerturbationType.SEED_CHANGE, None) == PerturbationIntensity.L2_MODERATE
    assert resolve_default_intensity(PerturbationType.CLOCK_SHIFT, None) == PerturbationIntensity.L2_MODERATE
    assert resolve_default_intensity(PerturbationType.SHUFFLE_ORDER, None) == PerturbationIntensity.L2_MODERATE
    assert resolve_default_intensity(PerturbationType.NETWORK_CUT, None) == PerturbationIntensity.L2_MODERATE
    assert resolve_default_intensity(PerturbationType.BASELINE, None) == PerturbationIntensity.L2_MODERATE

    # Explicit intensity overrides defaults:
    assert resolve_default_intensity(PerturbationType.CPU_HEAVY_LOAD, PerturbationIntensity.L1_MILD) == PerturbationIntensity.L1_MILD
    assert resolve_default_intensity(PerturbationType.CPU_HALF_CORES, "L3_EXTREME") == PerturbationIntensity.L3_EXTREME


def test_build_perturbation_context_with_intensity():
    ctx = build_perturbation_context(
        PerturbationType.CPU_HEAVY_LOAD,
        run_id=5,
        intensity=PerturbationIntensity.L3_EXTREME,
    )
    assert ctx.intensity == PerturbationIntensity.L3_EXTREME
    assert ctx.env_vars["COINFLIP_INTENSITY"] == "L3_EXTREME"


def test_cpu_heavy_load_intensity_switch_intervals():
    # L1_MILD: 50µs (0.00005s)
    with perturbation_runtime_context(
        PerturbationType.CPU_HEAVY_LOAD, run_id=0, intensity=PerturbationIntensity.L1_MILD
    ):
        assert abs(sys.getswitchinterval() - 0.00005) < 1e-6

    # L2_MODERATE: 5µs (0.000005s)
    with perturbation_runtime_context(
        PerturbationType.CPU_HEAVY_LOAD, run_id=0, intensity=PerturbationIntensity.L2_MODERATE
    ):
        assert abs(sys.getswitchinterval() - 0.000005) < 1e-7

    # L3_EXTREME: 1µs (0.000001s)
    with perturbation_runtime_context(
        PerturbationType.CPU_HEAVY_LOAD, run_id=0, intensity=PerturbationIntensity.L3_EXTREME
    ):
        assert abs(sys.getswitchinterval() - 0.000001) < 1e-8

    # Restored after context exit
    assert sys.getswitchinterval() >= 0.001


def test_clock_shift_intensity_offsets():
    orig_time = time.time()

    # L1_MILD: +60s
    with perturbation_runtime_context(
        PerturbationType.CLOCK_SHIFT, run_id=0, intensity=PerturbationIntensity.L1_MILD
    ):
        shifted = time.time()
        assert shifted - orig_time >= 59.0

    # L2_MODERATE: +3600s
    with perturbation_runtime_context(
        PerturbationType.CLOCK_SHIFT, run_id=0, intensity=PerturbationIntensity.L2_MODERATE
    ):
        shifted = time.time()
        assert shifted - orig_time >= 3590.0

    # L3_EXTREME: +86400s
    with perturbation_runtime_context(
        PerturbationType.CLOCK_SHIFT, run_id=0, intensity=PerturbationIntensity.L3_EXTREME
    ):
        shifted = time.time()
        assert shifted - orig_time >= 86390.0

    # Restored
    assert abs(time.time() - orig_time) < 10.0


def test_network_cut_intensity_behavior():
    # L3_EXTREME: raises OSError(ENETUNREACH)
    with perturbation_runtime_context(
        PerturbationType.NETWORK_CUT, run_id=0, intensity=PerturbationIntensity.L3_EXTREME
    ):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(OSError) as exc_info:
                s.connect(("127.0.0.1", 80))
            assert exc_info.value.errno == errno.ENETUNREACH
        finally:
            s.close()


def test_seed_change_intensities():
    # L1_MILD: deterministic sequential seed sweep
    with perturbation_runtime_context(
        PerturbationType.SEED_CHANGE, run_id=2, intensity=PerturbationIntensity.L1_MILD
    ):
        val1 = random.randint(1, 1000000)

    with perturbation_runtime_context(
        PerturbationType.SEED_CHANGE, run_id=2, intensity=PerturbationIntensity.L1_MILD
    ):
        val2 = random.randint(1, 1000000)

    assert val1 == val2

    # L2_MODERATE: adversarial boundary seed sweep
    with perturbation_runtime_context(
        PerturbationType.SEED_CHANGE, run_id=0, intensity=PerturbationIntensity.L2_MODERATE
    ):
        val_l2 = random.randint(1, 1000000)
    assert isinstance(val_l2, int)

    # L3_EXTREME: boundary seed + re-seeding
    with perturbation_runtime_context(
        PerturbationType.SEED_CHANGE, run_id=0, intensity=PerturbationIntensity.L3_EXTREME
    ):
        val_l3 = random.randint(1, 1000000)
    assert isinstance(val_l3, int)
