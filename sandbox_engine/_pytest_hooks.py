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
    perturbation: str | None,
    run_id: int = 0,
    base_seed: int = 1000,
) -> Generator[None, None, None]:
    """Applies a runtime perturbation externally and restores state upon exit."""
    pert_normalized = str(perturbation).lower() if perturbation else ""
    if hasattr(perturbation, "value"):
        pert_normalized = str(perturbation.value).lower()

    global _BURNER_STOP_EVENT, _BURNER_THREADS
    burner_stop: threading.Event | None = None
    burner_threads: list[threading.Thread] = []
    clock_call_counter = 0

    try:
        # 1. CPU Contention / GIL Stress
        if pert_normalized in ("cpu_heavy_load", "cpu_load"):
            sys.setswitchinterval(0.000001)  # 1 microsecond GIL switch
            burner_stop = threading.Event()
            _BURNER_STOP_EVENT = burner_stop
            def _burn_heavy() -> None:
                x = 1.0001
                while not burner_stop.is_set():
                    x = (x * 1.00001) % 1000.0

            worker_count = max(2, min(4, os.cpu_count() or 2))
            for _ in range(worker_count):
                t = threading.Thread(target=_burn_heavy, daemon=True)
                burner_threads.append(t)
                _BURNER_THREADS.append(t)
                t.start()

        elif pert_normalized in ("cpu_half_cores", "half_cores"):
            sys.setswitchinterval(0.00005)  # 50 microsecond GIL switch
            burner_stop = threading.Event()
            _BURNER_STOP_EVENT = burner_stop
            def _burn_half() -> None:
                x = 1.0001
                while not burner_stop.is_set():
                    x = (x * 1.00001) % 1000.0

            t = threading.Thread(target=_burn_half, daemon=True)
            burner_threads.append(t)
            _BURNER_THREADS.append(t)
            t.start()

        # 2. Seed Change
        if pert_normalized in ("seed_change", "seed"):
            seed_str = os.environ.get("COINFLIP_RANDOM_SEED")
            if seed_str:
                try:
                    per_run_seed = int(seed_str)
                except ValueError:
                    per_run_seed = 10000 + run_id * 7919
            else:
                per_run_seed = 10000 + run_id * 7919
            random.seed(per_run_seed)
            if "numpy.random" in sys.modules:
                sys.modules["numpy.random"].seed(per_run_seed % (2**32 - 1))
        else:
            # Baseline and other non-seed perturbations: seed with fixed seed so unpinned tests are quiet
            random.seed(42)
            if "numpy.random" in sys.modules:
                sys.modules["numpy.random"].seed(42)

        # 3. Clock Shift (with wall-clock skew per call, leaving monotonic untouched)
        if pert_normalized in ("clock_shift", "clock"):
            def _shifted_time() -> float:
                nonlocal clock_call_counter
                clock_call_counter += 1
                return _ORIG_TIME() + 3600.0 + (clock_call_counter * 0.15)

            time.time = _shifted_time

        # 4. Network Cut
        if pert_normalized in ("network_cut", "net_cut"):
            def _blocked_connect(*args: Any, **kwargs: Any) -> None:
                raise OSError("Simulated network cut")

            socket.socket.connect = _blocked_connect  # type: ignore[assignment]
            socket.create_connection = _blocked_connect  # type: ignore[assignment]

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
        socket.socket.connect = _ORIG_SOCKET_CONNECT  # type: ignore[assignment]
        socket.create_connection = _ORIG_CREATE_CONNECTION  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Pytest Plugin Hooks
# ---------------------------------------------------------------------------

def pytest_configure(config: Any) -> None:
    """Configures global session state."""


def pytest_collection_modifyitems(session: Any, config: Any, items: list[Any]) -> None:
    """Reverses or shuffles test execution order when shuffle_order is active."""
    pert = os.environ.get("COINFLIP_PERTURBATION", "")
    is_shuffle = pert in ("shuffle_order", "shuffle") or os.environ.get("COINFLIP_SHUFFLE") == "1"
    if is_shuffle and len(items) > 1:
        # Reversing sibling test order naturally inverts test execution order
        items.reverse()


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

    _ACTIVE_CONTEXT = perturbation_runtime_context(pert, run_id=run_id)
    _ACTIVE_CONTEXT.__enter__()


def pytest_runtest_teardown(item: Any) -> None:
    """Invoked immediately after executing each test function."""
    global _ACTIVE_CONTEXT
    if _ACTIVE_CONTEXT is not None:
        try:
            _ACTIVE_CONTEXT.__exit__(None, None, None)
        finally:
            _ACTIVE_CONTEXT = None
