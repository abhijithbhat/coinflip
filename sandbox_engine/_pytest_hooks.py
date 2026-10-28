"""Pytest plugin providing inline perturbation hooks for Coinflip.

Implements real, generic runtime perturbations externally without requiring
any cooperation or environment variable reads from the code under test:
- CPU_HEAVY_LOAD: Lower GIL switch interval via sys.setswitchinterval(0.000001) + daemon burner threads.
- CPU_HALF_CORES: Lower GIL switch interval via sys.setswitchinterval(0.00005) + burner thread.
- SHUFFLE_ORDER: Reverse/shuffle sibling test functions during collection/execution.
- SEED_CHANGE: Deterministic per-run seed (10000 + run_id * 7919).
- CLOCK_SHIFT: time.time() returns real_time + 3600.0 + call_counter * 0.15 (monotonic/perf_counter untouched).
- NETWORK_CUT: socket connect raises OSError("Simulated network cut").
"""

from __future__ import annotations

import contextlib
import os
import random
import socket
import sys
import threading
import time
from collections.abc import Generator
from typing import Any

from shared_contracts.schemas import PerturbationIntensity

ADVERSARIAL_BOUNDARY_SEEDS = [
    0, 1, 2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61,
    67, 71, 73, 79, 83, 89, 97, 101, 103, 107, 109, 113, 127, 255, 256,
    65535, 65536, 2147483647, 4294967295, 0x55555555, 0xAAAAAAAA, 0x12345678,
]

# Save original unpatched functions and settings
_ORIG_TIME = time.time
_ORIG_SLEEP = time.sleep
_ORIG_SWITCH = sys.getswitchinterval()
_ORIG_SOCKET_CONNECT = socket.socket.connect
_ORIG_CREATE_CONNECTION = socket.create_connection

_ACTIVE_CONTEXT: Any = None
_BURNER_STOP_EVENT: Any = None
_BURNER_THREADS: list[Any] = []


@contextlib.contextmanager
def perturbation_runtime_context(
    perturbation: str | Any | None,
    run_id: int = 0,
    base_seed: int = 1000,
    intensity: PerturbationIntensity | str | None = None,
    session_salt: int = 0,
) -> Generator[None, None, None]:
    """Applies a runtime perturbation externally with intensity support and restores state upon exit."""
    if session_salt == 0:
        salt_str = os.environ.get("COINFLIP_SESSION_SALT", "0")
        try:
            session_salt = int(salt_str)
        except ValueError:
            session_salt = 0

    is_fast_live = os.environ.get("COINFLIP_FAST_LIVE_MODE") == "1" or os.environ.get("COINFLIP_FAST_MODE") == "1"

    pert_normalized = str(perturbation).lower() if perturbation else ""
    if hasattr(perturbation, "value"):
        pert_normalized = str(perturbation.value).lower()

    if intensity is not None:
        if isinstance(intensity, PerturbationIntensity):
            resolved_intensity = intensity
        else:
            try:
                resolved_intensity = PerturbationIntensity(str(intensity).strip())
            except ValueError:
                resolved_intensity = PerturbationIntensity.L2_MODERATE
    else:
        env_intensity = os.environ.get("COINFLIP_INTENSITY")
        if env_intensity:
            try:
                resolved_intensity = PerturbationIntensity(env_intensity.strip())
            except ValueError:
                resolved_intensity = PerturbationIntensity.L2_MODERATE
        elif pert_normalized in ("cpu_heavy_load", "cpu_load"):
            resolved_intensity = PerturbationIntensity.L3_EXTREME
        elif pert_normalized in ("cpu_half_cores", "half_cores"):
            resolved_intensity = PerturbationIntensity.L1_MILD
        else:
            resolved_intensity = PerturbationIntensity.L2_MODERATE

    global _BURNER_STOP_EVENT, _BURNER_THREADS
    burner_stop: threading.Event | None = None
    burner_threads: list[threading.Thread] = []
    clock_call_counter = 0
    orig_random_methods: dict[str, Any] = {}
    orig_rng_state = random.getstate()

    try:
        # 1. CPU Contention / GIL Stress (CPU_HEAVY_LOAD & CPU_HALF_CORES)
        if pert_normalized in ("cpu_heavy_load", "cpu_load", "cpu_half_cores", "half_cores"):
            if is_fast_live:
                if resolved_intensity == PerturbationIntensity.L1_MILD:
                    switch_interval = 0.00005
                    worker_count = 1
                    is_extreme = False
                elif resolved_intensity == PerturbationIntensity.L2_MODERATE:
                    switch_interval = 0.00001
                    worker_count = 2
                    is_extreme = False
                else:  # L3_EXTREME
                    switch_interval = 0.000005
                    worker_count = 3
                    is_extreme = True
            else:
                if resolved_intensity == PerturbationIntensity.L1_MILD:
                    switch_interval = 0.00005  # 50 microseconds
                    worker_count = 2
                    is_extreme = False
                elif resolved_intensity == PerturbationIntensity.L2_MODERATE:
                    switch_interval = 0.000005  # 5 microseconds
                    worker_count = 4
                    is_extreme = False
                else:  # L3_EXTREME
                    switch_interval = 0.000001  # 1 microsecond
                    worker_count = 8
                    is_extreme = True

            if session_salt > 0:
                jitter_factor = 1.0 + (((session_salt * 17 + run_id * 13) % 15) - 7) * 0.02
                switch_interval = max(0.0000005, switch_interval * jitter_factor)

            sys.setswitchinterval(switch_interval)

            burner_stop = threading.Event()
            _BURNER_STOP_EVENT = burner_stop

            def _burn_loop() -> None:
                if is_fast_live:
                    burn_start = time.perf_counter()
                    x = 1.0001
                    burn_ceiling = 0.004
                    if session_salt > 0:
                        burn_ceiling *= (1.0 + (((session_salt * 19 + run_id * 31) % 17) - 8) * 0.02)
                    while not burner_stop.is_set():
                        x = (x * 1.00001) % 1000.0
                        if (time.perf_counter() - burn_start) > burn_ceiling:
                            time.sleep(0.0005)
                            burn_start = time.perf_counter()
                elif is_extreme:
                    d: dict[int, float] = {}
                    x = 1.0001
                    idx = 0
                    while not burner_stop.is_set():
                        x = (x * 1.00001) % 1000.0
                        d[idx % 500] = x
                        idx += 1
                else:
                    x = 1.0001
                    while not burner_stop.is_set():
                        x = (x * 1.00001) % 1000.0

            for _ in range(worker_count):
                t = threading.Thread(target=_burn_loop, daemon=True)
                burner_threads.append(t)
                _BURNER_THREADS.append(t)
                t.start()

        # 2. Seed Change
        if pert_normalized in ("seed_change", "seed"):
            if resolved_intensity == PerturbationIntensity.L1_MILD:
                per_run_seed = 10000 + (run_id + session_salt) * 7919
                seed_str = os.environ.get("COINFLIP_RANDOM_SEED")
                if seed_str:
                    try:
                        per_run_seed = int(seed_str) + session_salt
                    except ValueError:
                        pass
            else:
                salt_offset = (session_salt * 31) if session_salt > 0 else 0
                per_run_seed = ADVERSARIAL_BOUNDARY_SEEDS[(run_id + salt_offset) % len(ADVERSARIAL_BOUNDARY_SEEDS)]

            random.seed(per_run_seed)
            if "numpy.random" in sys.modules:
                try:
                    sys.modules["numpy.random"].seed(per_run_seed % (2**32 - 1))
                except Exception:
                    pass

            if resolved_intensity == PerturbationIntensity.L3_EXTREME:
                call_counter = 0
                methods_to_patch = ["random", "randint", "randrange", "choice", "choices", "sample", "shuffle", "uniform"]
                for m_name in methods_to_patch:
                    if hasattr(random, m_name):
                        orig_fn = getattr(random, m_name)
                        orig_random_methods[m_name] = orig_fn

                        def _make_reseed_wrapper(fn: Any) -> Any:
                            def _wrapped(*args: Any, **kwargs: Any) -> Any:
                                nonlocal call_counter
                                call_counter += 1
                                sub_seed = (per_run_seed + call_counter * 1013904223) % (2**32 - 1)
                                random.seed(sub_seed)
                                return fn(*args, **kwargs)
                            return _wrapped

                        setattr(random, m_name, _make_reseed_wrapper(orig_fn))
        else:
            # Baseline and other non-seed perturbations: seed with fixed seed so unpinned tests are quiet
            random.seed(42)
            if "numpy.random" in sys.modules:
                try:
                    sys.modules["numpy.random"].seed(42)
                except Exception:
                    pass

        # 3. Clock Shift (with wall-clock skew per call, leaving monotonic untouched)
        if pert_normalized in ("clock_shift", "clock"):
            if resolved_intensity == PerturbationIntensity.L1_MILD:
                base_shift = 60.0
                call_skew = 0.03
            elif resolved_intensity == PerturbationIntensity.L3_EXTREME:
                base_shift = 86400.0
                call_skew = 0.50
            else:  # L2_MODERATE
                base_shift = 3600.0
                call_skew = 0.15

            if session_salt > 0:
                call_skew += (((session_salt + run_id * 19) % 7) - 3) * 0.005

            def _shifted_time() -> float:
                nonlocal clock_call_counter
                clock_call_counter += 1
                return _ORIG_TIME() + base_shift + (clock_call_counter * call_skew)

            time.time = _shifted_time

        # 4. Network Cut
        if pert_normalized in ("network_cut", "net_cut"):
            import errno
            net_call_counter = 0

            if resolved_intensity == PerturbationIntensity.L1_MILD:
                def _latent_connect(sock_self: Any, *args: Any, **kwargs: Any) -> Any:
                    _ORIG_SLEEP(0.025)
                    return _ORIG_SOCKET_CONNECT(sock_self, *args, **kwargs)

                def _latent_create(*args: Any, **kwargs: Any) -> Any:
                    _ORIG_SLEEP(0.025)
                    return _ORIG_CREATE_CONNECTION(*args, **kwargs)

                socket.socket.connect = _latent_connect  # type: ignore[assignment]
                socket.create_connection = _latent_create  # type: ignore[assignment]

            elif resolved_intensity == PerturbationIntensity.L2_MODERATE:
                def _timeout_connect(sock_self: Any, *args: Any, **kwargs: Any) -> Any:
                    nonlocal net_call_counter
                    net_call_counter += 1
                    _ORIG_SLEEP(0.150)
                    if net_call_counter % 2 == 1:
                        raise TimeoutError("Simulated network connection timeout")
                    return _ORIG_SOCKET_CONNECT(sock_self, *args, **kwargs)

                def _timeout_create(*args: Any, **kwargs: Any) -> Any:
                    nonlocal net_call_counter
                    net_call_counter += 1
                    _ORIG_SLEEP(0.150)
                    if net_call_counter % 2 == 1:
                        raise TimeoutError("Simulated network connection timeout")
                    return _ORIG_CREATE_CONNECTION(*args, **kwargs)

                socket.socket.connect = _timeout_connect  # type: ignore[assignment]
                socket.create_connection = _timeout_create  # type: ignore[assignment]

            else:  # L3_EXTREME
                def _blocked_connect(*args: Any, **kwargs: Any) -> None:
                    raise OSError(errno.ENETUNREACH, "Simulated network cut")

                socket.socket.connect = _blocked_connect  # type: ignore[assignment]
                socket.create_connection = _blocked_connect  # type: ignore[assignment]

        if session_salt > 0:
            def _jittered_sleep(secs: float) -> None:
                jitter_pct = (((session_salt * 37 + run_id * 23) % 19) - 9) * 0.012
                _ORIG_SLEEP(max(0.0001, secs * (1.0 + jitter_pct)))

            time.sleep = _jittered_sleep

        yield

    finally:
        # Clean teardown of burners
        if burner_stop is not None:
            burner_stop.set()
            burner_threads.clear()
        if _BURNER_STOP_EVENT is not None:
            _BURNER_STOP_EVENT.set()
            _BURNER_STOP_EVENT = None
        _BURNER_THREADS.clear()

        # Restore switch interval
        try:
            sys.setswitchinterval(_ORIG_SWITCH)
        except Exception:
            sys.setswitchinterval(0.005)

        # Restore patched functions
        time.time = _ORIG_TIME
        time.sleep = _ORIG_SLEEP
        socket.socket.connect = _ORIG_SOCKET_CONNECT  # type: ignore[assignment]
        socket.create_connection = _ORIG_CREATE_CONNECTION  # type: ignore[assignment]

        # Restore patched random methods if any
        for m_name, orig_fn in orig_random_methods.items():
            setattr(random, m_name, orig_fn)
        orig_random_methods.clear()
        try:
            random.setstate(orig_rng_state)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Pytest Plugin Hooks
# ---------------------------------------------------------------------------

def pytest_configure(config: Any) -> None:
    """Configures global session state."""


def pytest_collection_modifyitems(session: Any, config: Any, items: list[Any]) -> None:
    """Reverses, permutes, or prioritizes mutating tests when shuffle_order is active."""
    pert = os.environ.get("COINFLIP_PERTURBATION", "")
    is_shuffle = pert in ("shuffle_order", "shuffle") or os.environ.get("COINFLIP_SHUFFLE") == "1"
    if is_shuffle and len(items) > 1:
        intensity_str = os.environ.get("COINFLIP_INTENSITY", "L2_MODERATE")
        if intensity_str == "L1_MILD":
            items.reverse()
        elif intensity_str == "L3_EXTREME":
            items.sort(
                key=lambda it: 0 if any(k in it.name.lower() for k in ("mutate", "set", "write", "update", "dirty", "pollut", "b_")) else 1
            )
        else:  # L2_MODERATE
            try:
                seed_val = int(os.environ.get("COINFLIP_RANDOM_SEED", "1000"))
            except ValueError:
                seed_val = 1000
            try:
                seed_val += int(os.environ.get("COINFLIP_SESSION_SALT", "0"))
            except ValueError:
                pass
            rng = random.Random(seed_val)
            shuffled = list(items)
            rng.shuffle(shuffled)
            if shuffled == items:
                shuffled.reverse()
            items[:] = shuffled


def pytest_runtest_setup(item: Any) -> None:
    """Invoked immediately prior to executing each individual test function."""
    global _ACTIVE_CONTEXT
    pert = os.environ.get("COINFLIP_PERTURBATION")
    if not pert:
        if os.environ.get("COINFLIP_CPU_LOAD") == "1":
            pert = "cpu_heavy_load"
        elif os.environ.get("COINFLIP_CLOCK_SHIFT_SEC"):
            pert = "clock_shift"
        elif os.environ.get("COINFLIP_NET_CUT") == "1":
            pert = "network_cut"
        elif os.environ.get("COINFLIP_RANDOM_SEED"):
            pert = "seed_change"

    run_id = 0
    run_id_str = os.environ.get("COINFLIP_RUN_ID")
    if run_id_str:
        try:
            run_id = int(run_id_str)
        except ValueError:
            pass

    session_salt = 0
    salt_str = os.environ.get("COINFLIP_SESSION_SALT")
    if salt_str:
        try:
            session_salt = int(salt_str)
        except ValueError:
            pass

    intensity_str = os.environ.get("COINFLIP_INTENSITY")
    _ACTIVE_CONTEXT = perturbation_runtime_context(
        pert, run_id=run_id, intensity=intensity_str, session_salt=session_salt
    )
    _ACTIVE_CONTEXT.__enter__()


def pytest_runtest_teardown(item: Any) -> None:
    """Invoked immediately after executing each test function."""
    global _ACTIVE_CONTEXT
    if _ACTIVE_CONTEXT is not None:
        try:
            _ACTIVE_CONTEXT.__exit__(None, None, None)
        finally:
            _ACTIVE_CONTEXT = None
