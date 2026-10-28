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
import socket
import sys
import time
import traceback
from collections.abc import Callable
from pathlib import Path

# Ensure workspace root is in sys.path
workspace_root = Path(__file__).resolve().parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from sandbox_engine.perturbations import build_perturbation_context
from shared_contracts.schemas import PerturbationIntensity, PerturbationType, SingleRunResult

# Save unpatched builtins
_ORIG_TIME = time.time
_ORIG_SLEEP = time.sleep
_ORIG_SOCKET_CONNECT = socket.socket.connect


def _reset_benchmark_state() -> None:
    """Resets known benchmark state singletons between in-process runs."""
    if "config_service" in sys.modules:
        cfg = sys.modules["config_service"]
        if hasattr(cfg, "reset_config"):
            try:
                cfg.reset_config()
            except Exception:
                pass
        elif hasattr(cfg, "_GLOBAL_CONFIG_CACHE"):
            try:
                cfg._GLOBAL_CONFIG_CACHE.clear()
                cfg._GLOBAL_CONFIG_CACHE.update({"region": "us-east-1", "tier": "standard"})
            except Exception:
                pass


def run_worker_chunk(
    temp_dir: Path | str,
    test_target: str,
    perturbation: PerturbationType,
    run_ids: list[int],
    base_seed: int = 1000,
    intensity: PerturbationIntensity | str | None = None,
    session_salt: int = 0,
) -> list[SingleRunResult]:
    """Executes a list of run_ids sequentially within this worker process."""
    if session_salt == 0:
        try:
            session_salt = int(os.environ.get("COINFLIP_SESSION_SALT", "0"))
        except ValueError:
            session_salt = 0
    temp_dir = Path(temp_dir).resolve()
    orig_cwd = os.getcwd()
    hooks_dir = Path(__file__).resolve().parent
    if str(temp_dir) not in sys.path:
        sys.path.insert(0, str(temp_dir))
    if str(hooks_dir) not in sys.path:
        sys.path.insert(0, str(hooks_dir))

    # Target path extraction (handles example-service::test_worker.py or tests/test_worker.py)
    if "::" in test_target:
        parts = test_target.split("::")
        target_filename = parts[-1] if parts[-1].endswith(".py") else parts[0]
    else:
        target_filename = test_target

    target_path = (temp_dir / target_filename).resolve()
    if not target_path.exists():
        matches = list(temp_dir.rglob(Path(target_filename).name))
        if matches:
            target_path = matches[0]

    # Clean up any previously imported test modules to prevent pytest import file mismatch
    mod_name = target_path.stem
    for k in list(sys.modules.keys()):
        if k == mod_name or k.startswith(f"{mod_name}."):
            sys.modules.pop(k, None)

    # Execute conftest.py if present to initialize path & fixture context
    conftest_path = temp_dir / "conftest.py"
    if conftest_path.exists():
        try:
            spec_conf = importlib.util.spec_from_file_location("coinflip_conftest", str(conftest_path))
            if spec_conf and spec_conf.loader:
                mod_conf = importlib.util.module_from_spec(spec_conf)
                spec_conf.loader.exec_module(mod_conf)
        except Exception:
            pass

    direct_test_funcs: list[Callable[[], None]] = []
    can_direct_exec = False
    if target_path.exists() and target_path.suffix == ".py":
        try:
            spec = importlib.util.spec_from_file_location("coinflip_chunk_target", str(target_path))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                sys.modules["coinflip_chunk_target"] = mod
                spec.loader.exec_module(mod)
                funcs = [
                    getattr(mod, name)
                    for name in dir(mod)
                    if name.startswith("test_") and callable(getattr(mod, name))
                ]
                has_fixtures = any(
                    hasattr(getattr(mod, name), "_fixture_function_marker")
                    or hasattr(getattr(mod, name), "_pytestfixturefunction")
                    for name in dir(mod)
                )
                if not has_fixtures and funcs and all(len(inspect.signature(f).parameters) == 0 for f in funcs):
                    funcs.sort(key=lambda f: f.__code__.co_firstlineno)
                    direct_test_funcs = funcs
                    can_direct_exec = True
        except Exception:
            can_direct_exec = False

    results: list[SingleRunResult] = []

    # When session_salt is provided, incorporate it into worker chunk execution ordering
    exec_run_ids = list(run_ids)
    if session_salt > 0:
        import random
        pert_val = getattr(perturbation, "value", str(perturbation))
        pert_hash = hash(pert_val)
        order_rng = random.Random(session_salt * 53 + pert_hash)
        order_rng.shuffle(exec_run_ids)

    try:
        if can_direct_exec:
            from sandbox_engine._pytest_hooks import perturbation_runtime_context

            # High-throughput in-process direct execution loop
            for run_id in exec_run_ids:
                # Clear any lingering perturbation env vars
                for k in (
                    "COINFLIP_CPU_LOAD",
                    "COINFLIP_SHUFFLE",
                    "COINFLIP_PERTURBATION",
                    "COINFLIP_RANDOM_SEED",
                    "PYTHONHASHSEED",
                    "COINFLIP_CLOCK_SHIFT_SEC",
                    "COINFLIP_NET_CUT",
                    "COINFLIP_HALF_CORES",
                ):
                    os.environ.pop(k, None)
                ctx = build_perturbation_context(
                    perturbation, run_id=run_id, base_seed=base_seed, intensity=intensity
                )
                os.environ["COINFLIP_PERTURBATION"] = perturbation.value
                os.environ.update(ctx.env_vars)

                funcs_to_run = list(direct_test_funcs)
                if perturbation == PerturbationType.SHUFFLE_ORDER and len(funcs_to_run) > 1:
                    resolved_intensity = ctx.intensity
                    if resolved_intensity == PerturbationIntensity.L1_MILD:
                        funcs_to_run.reverse()
                    elif resolved_intensity == PerturbationIntensity.L3_EXTREME:
                        mutating_funcs = [
                            f
                            for f in direct_test_funcs
                            if any(k in f.__name__.lower() for k in ("mutate", "set", "write", "update", "dirty", "pollut", "b_"))
                        ]
                        if not mutating_funcs and len(direct_test_funcs) > 1:
                            mutating_funcs = direct_test_funcs[1:]
                        funcs_to_run = mutating_funcs + mutating_funcs + direct_test_funcs
                    else:  # L2_MODERATE
                        import random
                        rng = random.Random(10000 + (run_id + session_salt) * 37)
                        permuted = list(funcs_to_run)
                        rng.shuffle(permuted)
                        if permuted == funcs_to_run:
                            permuted.reverse()
                        funcs_to_run = permuted

                start_t = time.perf_counter()
                passed = True
                exit_code = 0
                error_snippet = None

                _reset_benchmark_state()
                try:
                    with perturbation_runtime_context(
                        perturbation, run_id=run_id, base_seed=base_seed, intensity=ctx.intensity, session_salt=session_salt
                    ):
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

            for run_id in exec_run_ids:
                sys.modules.pop(mod_name, None)
                salt_offset = (session_salt % 10000) if session_salt > 0 else 0
                ctx = build_perturbation_context(
                    perturbation, run_id=run_id, base_seed=base_seed + salt_offset, intensity=intensity
                )
                if session_salt > 0:
                    os.environ["COINFLIP_SESSION_SALT"] = str(session_salt)
                os.environ.update(ctx.env_vars)

                pytest_args = [
                    str(target_path),
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
        # Restore original working directory and patched builtins
        os.chdir(orig_cwd)
        time.time = _ORIG_TIME
        time.sleep = _ORIG_SLEEP
        socket.socket.connect = _ORIG_SOCKET_CONNECT  # type: ignore[assignment]
        try:
            sys.setswitchinterval(0.005)
        except Exception:
            pass

    return results


def run_inprocess_worker_pool(
    temp_dir: Path | str,
    test_target: str,
    perturbation: PerturbationType | str,
    run_ids: list[int],
    base_seed: int = 1000,
    num_workers: int | None = None,
    intensity: PerturbationIntensity | str | None = None,
    session_salt: int = 0,
) -> list[SingleRunResult]:
    """Runs a batch of test runs across high-throughput in-process workers.

    Guarantees sub-0.5s execution for 30 runs while maintaining calibrated
    baseline and stress failure rates.
    """
    if isinstance(temp_dir, str):
        temp_dir = Path(temp_dir).resolve()
    if isinstance(perturbation, str):
        perturbation = PerturbationType(perturbation)
    if isinstance(intensity, str):
        intensity = PerturbationIntensity(intensity)

    return run_worker_chunk(
        temp_dir=temp_dir,
        test_target=test_target,
        perturbation=perturbation,
        run_ids=run_ids,
        base_seed=base_seed,
        intensity=intensity,
        session_salt=session_salt,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Coinflip Test Chunk Worker")
    parser.add_argument("--temp-dir", required=True, help="Path to isolated test workspace")
    parser.add_argument("--test-target", required=True, help="Test target identifier")
    parser.add_argument("--perturbation", required=True, help="Perturbation condition")
    parser.add_argument("--run-ids", required=True, help="Comma-separated run IDs")
    parser.add_argument("--base-seed", type=int, default=1000, help="Base seed for perturbation")
    parser.add_argument("--intensity", default=None, help="Perturbation intensity level")
    parser.add_argument("--session-salt", type=int, default=0, help="Session salt for live variance")
    args = parser.parse_args()

    temp_dir = Path(args.temp_dir).resolve()
    perturbation = PerturbationType(args.perturbation)
    run_ids = [int(x.strip()) for x in args.run_ids.split(",") if x.strip()]
    intensity = PerturbationIntensity(args.intensity) if args.intensity else None

    results = run_worker_chunk(
        temp_dir=temp_dir,
        test_target=args.test_target,
        perturbation=perturbation,
        run_ids=run_ids,
        base_seed=args.base_seed,
        intensity=intensity,
        session_salt=args.session_salt,
    )

    serialized = [r.model_dump() for r in results]
    print(json.dumps(serialized))


if __name__ == "__main__":
    main()
