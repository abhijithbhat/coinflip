"""High-throughput worker pool runner for Coinflip.

Executes test chunks inside a persistent worker process to eliminate cold interpreter
startup overhead for 300-run experiments and 1,000-run certification batches.
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import io
import json
import os
from pathlib import Path
import random
import socket
import sys
import threading
import time
import traceback
from typing import Any, Callable

# Ensure workspace root is in sys.path
workspace_root = Path(__file__).resolve().parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from sandbox_engine.perturbations import build_perturbation_context
from shared_contracts.schemas import PerturbationType, SingleRunResult

# Save unpatched builtins
_ORIG_TIME = time.time
_ORIG_SOCKET_CONNECT = socket.socket.connect


def run_worker_chunk(
    temp_dir: Path,
    test_target: str,
    perturbation: PerturbationType,
    run_ids: list[int],
    base_seed: int = 1000,
) -> list[SingleRunResult]:
    """Executes a list of run_ids sequentially within this worker process."""
    hooks_dir = Path(__file__).resolve().parent
    if str(temp_dir) not in sys.path:
        sys.path.insert(0, str(temp_dir))
    if str(hooks_dir) not in sys.path:
        sys.path.insert(0, str(hooks_dir))

    os.chdir(str(temp_dir))

    # Fast-path detection: Check if test_target is a python file containing 0-arg test functions
    target_path = (temp_dir / test_target).resolve()
    direct_test_funcs: list[Callable[[], None]] = []
    can_direct_exec = False

    if target_path.exists() and target_path.suffix == ".py":
        try:
            spec = importlib.util.spec_from_file_location("coinflip_chunk_target", str(target_path))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                funcs = [
                    getattr(mod, name)
                    for name in dir(mod)
                    if name.startswith("test_") and callable(getattr(mod, name))
                ]
                if funcs and all(len(inspect.signature(f).parameters) == 0 for f in funcs):
                    direct_test_funcs = funcs
                    can_direct_exec = True
        except Exception:
            can_direct_exec = False
    # Under CPU_HEAVY_LOAD, run an in-process thread to create GIL contention
    burner_stop_event: threading.Event | None = None
    if perturbation == PerturbationType.CPU_HEAVY_LOAD:
        burner_stop_event = threading.Event()

        def _burn(stop_evt: threading.Event) -> None:
            x = 1.0001
            while not stop_evt.is_set():
                x = (x * 1.00001) % 1000.0

        t = threading.Thread(target=_burn, args=(burner_stop_event,), daemon=True)
        t.start()

    results: list[SingleRunResult] = []

    try:
        if can_direct_exec and direct_test_funcs:
            # High-throughput in-process execution loop
            for run_id in run_ids:
                ctx = build_perturbation_context(perturbation, run_id=run_id, base_seed=base_seed)
                os.environ.update(ctx.env_vars)

                # Perturbation hooks
                if perturbation == PerturbationType.SEED_CHANGE:
                    seed_val = int(ctx.env_vars.get("COINFLIP_RANDOM_SEED", 42))
                    random.seed(seed_val)
                    if "numpy.random" in sys.modules:
                        getattr(sys.modules["numpy.random"], "seed")(seed_val % (2**32 - 1))

                if perturbation == PerturbationType.CLOCK_SHIFT:
                    time.time = lambda: _ORIG_TIME() + 3600.0
                else:
                    time.time = _ORIG_TIME

                if perturbation == PerturbationType.NETWORK_CUT:
                    def _blocked(*args: Any, **kwargs: Any) -> None:
                        raise OSError("Network disabled by Coinflip Sandbox")
                    socket.socket.connect = _blocked  # type: ignore[assignment]
                else:
                    socket.socket.connect = _ORIG_SOCKET_CONNECT  # type: ignore[assignment]

                # Run test functions
                funcs_to_run = list(direct_test_funcs)
                if perturbation == PerturbationType.SHUFFLE_ORDER:
                    rng = random.Random(base_seed + run_id)
                    rng.shuffle(funcs_to_run)

                start_t = time.perf_counter()
                passed = True
                exit_code = 0
                error_snippet = None

                try:
                    for f in funcs_to_run:
                        f()
                except Exception as e:
                    passed = False
                    exit_code = 1
                    tb_lines = traceback.format_exc().strip().splitlines()
                    error_snippet = "\n".join(tb_lines[-15:]) if tb_lines else str(e)

                duration_ms = round((time.perf_counter() - start_t) * 1000.0, 2)
                results.append(
                    SingleRunResult(
                        run_id=run_id,
                        passed=passed,
                        exit_code=exit_code,
                        duration_ms=duration_ms,
                        error_snippet=error_snippet,
                    )
                )

        else:
            # Fallback path: pytest.main for fixture-heavy tests
            import pytest

            for run_id in run_ids:
                ctx = build_perturbation_context(perturbation, run_id=run_id, base_seed=base_seed)
                os.environ.update(ctx.env_vars)

                pytest_args = [
                    test_target,
                    "-q",
                    "--tb=short",
                    "-p",
                    "_pytest_hooks",
                    *ctx.pytest_args,
                ]

                buf = io.StringIO()
                old_stdout = sys.stdout
                old_stderr = sys.stderr
                sys.stdout = buf
                sys.stderr = buf

                start_t = time.perf_counter()
                try:
                    exit_code = int(pytest.main(pytest_args))
                except Exception as e:
                    exit_code = 1
                    buf.write(f"\nPytest main exception: {e}")
                finally:
                    sys.stdout = old_stdout
                    sys.stderr = old_stderr

                duration_ms = round((time.perf_counter() - start_t) * 1000.0, 2)
                passed = (exit_code == 0)
                error_snippet = None

                if not passed:
                    output_text = buf.getvalue().strip()
                    lines = [line for line in output_text.splitlines() if line.strip()]
                    error_snippet = "\n".join(lines[-15:]) if lines else "Test failed with non-zero exit code"

                results.append(
                    SingleRunResult(
                        run_id=run_id,
                        passed=passed,
                        exit_code=exit_code,
                        duration_ms=duration_ms,
                        error_snippet=error_snippet,
                    )
                )

    finally:
        # Restore patched functions
        time.time = _ORIG_TIME
        socket.socket.connect = _ORIG_SOCKET_CONNECT  # type: ignore[assignment]
        if burner_stop_event is not None:
            burner_stop_event.set()

    return results


def run_inprocess_worker_pool(
    temp_dir: Path | str,
    test_target: str,
    perturbation: PerturbationType | str,
    run_ids: list[int],
    base_seed: int = 1000,
    num_workers: int | None = None,
) -> list[SingleRunResult]:
    """Runs a batch of test runs across in-process workers, throttling non-stress runs.

    When perturbation is not in ('cpu_heavy_load', 'cpu_half_cores'), caps num_workers to
    min(2, max(1, len(run_ids) // 10)) to guarantee zero self-inflicted CPU contention
    during baseline and quiet runs.
    """
    if isinstance(temp_dir, str):
        temp_dir = Path(temp_dir).resolve()
    if isinstance(perturbation, str):
        perturbation = PerturbationType(perturbation)

    pert_val = perturbation.value if hasattr(perturbation, "value") else str(perturbation)
    if pert_val not in ("cpu_heavy_load", "cpu_half_cores"):
        capped = min(2, max(1, len(run_ids) // 10))
        num_workers = min(num_workers, capped) if num_workers is not None else capped
    else:
        num_workers = num_workers or min(len(run_ids), max(4, os.cpu_count() or 4))

    if num_workers <= 1 or len(run_ids) <= 1:
        return run_worker_chunk(
            temp_dir=temp_dir,
            test_target=test_target,
            perturbation=perturbation,
            run_ids=run_ids,
            base_seed=base_seed,
        )

    # Partition run_ids across worker chunks
    chunks: list[list[int]] = [[] for _ in range(num_workers)]
    for i, rid in enumerate(run_ids):
        chunks[i % num_workers].append(rid)
    active_chunks = [c for c in chunks if c]

    all_results: list[SingleRunResult] = []
    for chunk in active_chunks:
        chunk_res = run_worker_chunk(
            temp_dir=temp_dir,
            test_target=test_target,
            perturbation=perturbation,
            run_ids=chunk,
            base_seed=base_seed,
        )
        all_results.extend(chunk_res)

    all_results.sort(key=lambda r: r.run_id)
    return all_results


def main() -> None:
    parser = argparse.ArgumentParser(description="Coinflip Test Chunk Worker")
    parser.add_argument("--temp-dir", required=True, help="Path to isolated test workspace")
    parser.add_argument("--test-target", required=True, help="Test target identifier")
    parser.add_argument("--perturbation", required=True, help="Perturbation condition")
    parser.add_argument("--run-ids", required=True, help="Comma-separated run IDs")
    parser.add_argument("--base-seed", type=int, default=1000, help="Base seed for perturbation")
    args = parser.parse_args()

    temp_dir = Path(args.temp_dir).resolve()
    perturbation = PerturbationType(args.perturbation)
    run_ids = [int(x.strip()) for x in args.run_ids.split(",") if x.strip()]

    results = run_worker_chunk(
        temp_dir=temp_dir,
        test_target=args.test_target,
        perturbation=perturbation,
        run_ids=run_ids,
        base_seed=args.base_seed,
    )

    serialized = [r.model_dump() for r in results]
    print(json.dumps(serialized))


if __name__ == "__main__":
    main()
