"""Pytest plugin providing inline perturbation hooks for Coinflip.

This module implements test-level perturbations (ordering, random seeds, clock skew,
network cutoff, core constraints, and CPU stress contention) without requiring external
third-party pytest plugins.
"""

from __future__ import annotations

import os
import random
import socket
import sys
import threading
import time
from typing import Any

# Globals for managing test-level background CPU stressors
_BURNER_STOP_EVENT: threading.Event | None = None
_BURNER_THREADS: list[threading.Thread] = []

# Save original unpatched functions
_ORIG_TIME = time.time
_ORIG_SOCKET_CONNECT = socket.socket.connect
_ORIG_CREATE_CONNECTION = socket.create_connection


def pytest_configure(config: Any) -> None:
    """Configures global monkeypatches at pytest session initialization."""
    # 1. Clock Shift: monkeypatch time.time() to simulate time drift/skew
    shift_sec_str = os.environ.get("COINFLIP_CLOCK_SHIFT_SEC")
    if shift_sec_str:
        try:
            shift_sec = float(shift_sec_str)
            if shift_sec != 0.0:
                time.time = lambda: _ORIG_TIME() + shift_sec
        except ValueError:
            pass

    # 2. Network Cut: block socket connections
    if os.environ.get("COINFLIP_NET_CUT") == "1":
        def _blocked_connect(*args: Any, **kwargs: Any) -> None:
            raise OSError("Network disabled by Coinflip Sandbox")

        socket.socket.connect = _blocked_connect  # type: ignore[assignment]
        socket.create_connection = _blocked_connect  # type: ignore[assignment]

    # 3. CPU Core Affinity: restrict to single core on Linux if supported
    if os.environ.get("COINFLIP_HALF_CORES") == "1":
        if hasattr(os, "sched_setaffinity"):
            try:
                os.sched_setaffinity(0, {0})
            except Exception:
                pass


def pytest_collection_modifyitems(session: Any, config: Any, items: list[Any]) -> None:
    """Shuffles test execution order when COINFLIP_SHUFFLE is enabled."""
    if os.environ.get("COINFLIP_SHUFFLE") == "1":
        seed_val = int(os.environ.get("COINFLIP_RANDOM_SEED", "42"))
        rng = random.Random(seed_val)
        rng.shuffle(items)


def pytest_runtest_setup(item: Any) -> None:
    """Invoked immediately prior to executing each individual test function."""
    global _BURNER_STOP_EVENT, _BURNER_THREADS

    # 1. Re-seed Python and common RNGs if requested
    seed_str = os.environ.get("COINFLIP_RANDOM_SEED")
    if seed_str:
        try:
            seed = int(seed_str)
            random.seed(seed)
            if "numpy.random" in sys.modules:
                getattr(sys.modules["numpy.random"], "seed")(seed % (2**32 - 1))
        except ValueError:
            pass

    # 2. CPU Heavy Load: spawn background busy-loop threads to create thread/core contention
    if os.environ.get("COINFLIP_CPU_LOAD") == "1":
        if _BURNER_STOP_EVENT is None:
            _BURNER_STOP_EVENT = threading.Event()
            _BURNER_THREADS = []

            def _burn(stop_evt: threading.Event) -> None:
                # Busy-loop doing floating-point and memory hashing
                x = 1.0001
                while not stop_evt.is_set():
                    x = (x * 1.00001) % 1000.0

            # Start workers to saturate available virtual execution slots
            worker_count = max(2, min(4, os.cpu_count() or 2))
            for _ in range(worker_count):
                t = threading.Thread(target=_burn, args=(_BURNER_STOP_EVENT,), daemon=True)
                _BURNER_THREADS.append(t)
                t.start()


def pytest_runtest_teardown(item: Any) -> None:
    """Invoked immediately after executing each test function."""
    global _BURNER_STOP_EVENT, _BURNER_THREADS

    if _BURNER_STOP_EVENT is not None:
        _BURNER_STOP_EVENT.set()
        # Daemon threads will terminate promptly; do not block with sequential join timeouts
        _BURNER_THREADS.clear()
        _BURNER_STOP_EVENT = None

