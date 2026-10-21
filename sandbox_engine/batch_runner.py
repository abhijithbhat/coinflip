"""Parallel batch execution engine for Coinflip.

Supports Dual-Mode Execution:
- 'local_isolated': Isolated temporary workspace with asyncio subprocess worker pools.
- 'nebius_sandbox': MicroVM-isolated parallel container execution using contree-sdk.
- 'auto': Automatically probes contree status and falls back cleanly to local_isolated.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Literal, Self

from sandbox_engine.math_utils import wilson_ci_95
from sandbox_engine.perturbations import (
    HOOKS_MODULE_PATH,
    PerturbationContext,
    build_perturbation_context,
    get_perturbation_label,
)
from shared_contracts.schemas import (
    BatchExperimentResult,
    PerturbationType,
    SingleRunResult,
)

logger = logging.getLogger("sandbox_engine.batch_runner")


class BackgroundCpuStressor:
    """Spawns background CPU busy-loop worker processes to saturate CPU cores during stress runs."""

    def __init__(self, num_workers: int | None = None) -> None:
        self.num_workers = num_workers or min(2, max(1, (os.cpu_count() or 2) // 4))
        self.processes: list[subprocess.Popen[bytes]] = []

    def __enter__(self) -> Self:
        burn_script = (
            "import math\n"
            "x = 1.0001\n"
            "while True:\n"
            "    x = (x * 1.00001) % 1000.0\n"
        )
        for _ in range(self.num_workers):
            try:
                p = subprocess.Popen(
                    [sys.executable, "-c", burn_script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.processes.append(p)
            except Exception as e:
                logger.warning("Failed to spawn CPU burner process: %s", e)
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        for p in self.processes:
            try:
                p.terminate()
                p.kill()
            except Exception:
                pass
        self.processes.clear()


class SandboxBatchRunner:
    """Manages parallel test execution batches under controlled perturbation conditions."""

    def __init__(
        self,
        repo_dir: Path | str,
        test_target: str,
        max_concurrency: int = 45,
        mode: Literal["auto", "local_isolated", "nebius_sandbox"] = "auto",
        nebius_image_tag: str = "python:3.12-slim",
    ) -> None:
        self.repo_dir = Path(repo_dir).resolve()
        self.test_target = test_target
        self.max_concurrency = min(max_concurrency, 45)  # Enforce Nebius Beta 50-operation limit
        self.mode = mode
        self.nebius_image_tag = nebius_image_tag
        self._cached_backend: str | None = None

    async def probe_sandbox_availability(self) -> bool:
        """Probes whether the Nebius Sandboxes service is active on the configured project."""
        api_key = os.getenv("NEBIUS_API_KEY")
        project_id = os.getenv("NEBIUS_PROJECT_ID")
        if not api_key or not project_id:
            return False

        try:
            from contree_sdk import Contree

            client = Contree()
            info = await client.get_token_info()
            return bool(info.permissions.get("spawn", False) or info.permissions.get("spawn_disposable", False))
        except Exception as e:
            logger.debug("Nebius Sandboxes probe failed: %s", e)
            return False

    async def resolve_execution_backend(self) -> str:
        """Determines the active execution backend ('nebius_sandbox' or 'local_isolated')."""
        if self._cached_backend is not None:
            return self._cached_backend

        if self.mode == "nebius_sandbox":
            self._cached_backend = "nebius_sandbox"
        elif self.mode == "local_isolated":
            self._cached_backend = "local_isolated"
        else:  # "auto"
            is_active = await self.probe_sandbox_availability()
            if is_active:
                logger.info("[AutoProbe] Nebius Sandboxes is active. Using 'nebius_sandbox' backend.")
                self._cached_backend = "nebius_sandbox"
            else:
                logger.info(
                    "[AutoProbe] Nebius Sandboxes inactive (awaiting Beta access). "
                    "Falling back cleanly to 'local_isolated' backend."
                )
                self._cached_backend = "local_isolated"

        return self._cached_backend

    async def _run_single_local(
        self,
        run_id: int,
        temp_dir: Path,
        ctx: PerturbationContext,
        semaphore: asyncio.Semaphore,
    ) -> SingleRunResult:
        """Executes a single test invocation in an isolated subprocess."""
        async with semaphore:
            env = os.environ.copy()
            env.update(ctx.env_vars)
            # Ensure isolated temp_dir and hooks module are in PYTHONPATH
            existing_pypath = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = f"{temp_dir}:{HOOKS_MODULE_PATH.parent}:{existing_pypath}"

            cmd = [
                sys.executable,
                "-m",
                "pytest",
                self.test_target,
                "-q",
                "--tb=short",
                "-p",
                "_pytest_hooks",
                *ctx.pytest_args,
            ]

            start_t = time.perf_counter()
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(temp_dir),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_b, stderr_b = await proc.communicate()
            duration_ms = round((time.perf_counter() - start_t) * 1000.0, 2)

            passed = (proc.returncode == 0)
            error_snippet = None

            if not passed:
                output_text = (stdout_b.decode(errors="replace") + "\n" + stderr_b.decode(errors="replace")).strip()
                lines = [line for line in output_text.splitlines() if line.strip()]
                # Extract up to the last 15 lines of traceback / assertion failure
                error_snippet = "\n".join(lines[-15:]) if lines else "Process exited with non-zero status"

            return SingleRunResult(
                run_id=run_id,
                passed=passed,
                exit_code=proc.returncode or 0,
                duration_ms=duration_ms,
                error_snippet=error_snippet,
            )

    async def _run_worker_pool_chunk(
        self,
        temp_dir: Path,
        perturbation: PerturbationType,
        chunk_run_ids: list[int],
    ) -> list[SingleRunResult]:
        """Runs a chunk of test iterations inside a reusable worker process."""
        workspace_root = Path(__file__).resolve().parent.parent
        env = os.environ.copy()
        existing_pypath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{temp_dir}:{HOOKS_MODULE_PATH.parent}:{workspace_root}:{existing_pypath}"

        cmd = [
            sys.executable,
            "-m",
            "sandbox_engine._worker_pool",
            "--temp-dir",
            str(temp_dir),
            "--test-target",
            self.test_target,
            "--perturbation",
            perturbation.value,
            "--run-ids",
            ",".join(map(str, chunk_run_ids)),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(temp_dir),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, _stderr_b = await proc.communicate()

        try:
            raw_text = stdout_b.decode(errors="replace").strip()
            # If extra debug output preceded JSON, find the outermost array
            json_start = raw_text.find("[")
            json_end = raw_text.rfind("]")
            if json_start != -1 and json_end != -1:
                items = json.loads(raw_text[json_start : json_end + 1])
                return [SingleRunResult.model_validate(item) for item in items]
            raise ValueError(f"No JSON array found in worker output: {raw_text[:200]}")
        except Exception as e:
            logger.error("Failed to parse worker pool JSON output: %s", e)
            return [
                SingleRunResult(run_id=rid, passed=False, exit_code=1, duration_ms=0.0, error_snippet=str(e))
                for rid in chunk_run_ids
            ]

    async def _run_batch_local(
        self,
        perturbation: PerturbationType,
        num_runs: int,
    ) -> list[SingleRunResult]:
        """Runs the batch using isolated local temporary directories and high-speed worker pools."""
        temp_dir = Path(tempfile.mkdtemp(prefix="coinflip_batch_"))
        try:
            # Copy repository contents into isolated workspace
            if self.repo_dir.exists():
                shutil.copytree(self.repo_dir, temp_dir, dirs_exist_ok=True)

            # Copy pytest hooks directly into the workspace
            if HOOKS_MODULE_PATH.exists():
                shutil.copy2(HOOKS_MODULE_PATH, temp_dir / "_pytest_hooks.py")

            ctx = build_perturbation_context(perturbation, run_id=0)

            # Use high-throughput in-process worker pool for sub-0.5s isolated execution
            from sandbox_engine._worker_pool import run_inprocess_worker_pool

            return await asyncio.to_thread(
                run_inprocess_worker_pool,
                temp_dir=temp_dir,
                test_target=self.test_target,
                perturbation=perturbation,
                run_ids=list(range(num_runs)),
                base_seed=1000,
            )

            # Small batches (<= 12 runs): standard individual subprocess execution
            if perturbation in (PerturbationType.CPU_HEAVY_LOAD, PerturbationType.CPU_HALF_CORES):
                local_concurrency = min(self.max_concurrency, 4)
            else:
                local_concurrency = min(2, max(1, num_runs // 10))
            semaphore = asyncio.Semaphore(local_concurrency)

            if ctx.needs_external_cpu_stress:
                with BackgroundCpuStressor():
                    tasks = [
                        self._run_single_local(
                            run_id=i,
                            temp_dir=temp_dir,
                            ctx=build_perturbation_context(perturbation, run_id=i),
                            semaphore=semaphore,
                        )
                        for i in range(num_runs)
                    ]
                    results = await asyncio.gather(*tasks)
            else:
                tasks = [
                    self._run_single_local(
                        run_id=i,
                        temp_dir=temp_dir,
                        ctx=build_perturbation_context(perturbation, run_id=i),
                        semaphore=semaphore,
                    )
                    for i in range(num_runs)
                ]
                results = await asyncio.gather(*tasks)

            return results
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def _get_or_prepare_image(self, client: Any) -> Any:
        """Finds or prepares a Nebius image with Python 3.12 and pytest installed."""
        candidates = [self.nebius_image_tag, "coinflip-runner:latest", "python:3.12-slim"]
        seen: set[str] = set()
        for tag in candidates:
            if tag in seen:
                continue
            seen.add(tag)
            try:
                img = await client.images.use(tag)
                chk = await img.run("python3", args=["-m", "pytest", "--version"], timeout=15)
                if chk.exit_code == 0:
                    return img
                # If pytest is not preinstalled, install it into this layer
                logger.info("Installing pytest into Nebius image '%s'...", tag)
                baked = await img.run("pip", args=["install", "--no-cache-dir", "pytest"], disposable=False)
                try:
                    tagged = await baked.tag_as("coinflip-runner:latest")
                    return tagged
                except Exception:
                    return baked
            except Exception as e:
                logger.debug("Image candidate '%s' check failed: %s", tag, e)
        raise RuntimeError(f"Could not initialize Nebius Sandbox image with pytest for '{self.nebius_image_tag}'")

    async def _run_batch_nebius(
        self,
        perturbation: PerturbationType,
        num_runs: int,
    ) -> list[SingleRunResult]:
        """Runs the batch inside Nebius Sandboxes microVMs via contree-sdk."""
        from contree_sdk import Contree

        client = Contree()
        base_img = await self._get_or_prepare_image(client)

        # Upload repository files and hooks into /workspace
        files_to_upload: dict[str, Path] = {}
        if self.repo_dir.exists():
            for root, _, files in os.walk(self.repo_dir):
                for f in files:
                    if f.endswith((".py", ".json", ".txt", ".cfg", ".ini", ".toml")):
                        local_p = Path(root) / f
                        rel_p = local_p.relative_to(self.repo_dir)
                        files_to_upload[f"/workspace/{rel_p}"] = local_p

        if HOOKS_MODULE_PATH.exists():
            files_to_upload["/workspace/_pytest_hooks.py"] = HOOKS_MODULE_PATH

        # Bake workspace files into derived image once so runs execute with zero per-run upload overhead
        workspace_img = await base_img.apply_files(files=files_to_upload)

        # Determine normalized test target within /workspace
        test_target_arg = self.test_target
        try:
            p = Path(self.test_target.split("::")[0])
            if p.is_absolute() and self.repo_dir in p.parents:
                rel = p.relative_to(self.repo_dir)
                test_target_arg = str(rel) + (("::" + self.test_target.split("::", 1)[1]) if "::" in self.test_target else "")
        except Exception:
            pass

        semaphore = asyncio.Semaphore(min(self.max_concurrency, 45))

        async def _run_single_sandbox(run_id: int) -> SingleRunResult:
            ctx = build_perturbation_context(perturbation, run_id=run_id)
            env = {"PYTHONPATH": "/workspace"}
            env.update(ctx.env_vars)

            cmd_args = [test_target_arg, "-q", "--tb=short", "-p", "_pytest_hooks", *ctx.pytest_args]

            async with semaphore:
                start_t = time.perf_counter()
                res = await workspace_img.run(
                    "pytest",
                    args=cmd_args,
                    cwd="/workspace",
                    env=env,
                    disposable=True,
                )
                duration_ms = round((time.perf_counter() - start_t) * 1000.0, 2)
                passed = (res.exit_code == 0)
                error_snippet = None
                if not passed:
                    out = (res.stdout or "") + "\n" + (res.stderr or "")
                    lines = [line for line in out.strip().splitlines() if line.strip()]
                    error_snippet = "\n".join(lines[-15:]) if lines else "Process exited with non-zero status"

                return SingleRunResult(
                    run_id=run_id,
                    passed=passed,
                    exit_code=res.exit_code,
                    duration_ms=duration_ms,
                    error_snippet=error_snippet,
                )

        tasks = [_run_single_sandbox(i) for i in range(num_runs)]
        results = list(await asyncio.gather(*tasks))
        results.sort(key=lambda r: r.run_id)
        return results

    async def run_batch(
        self,
        perturbation: PerturbationType,
        num_runs: int,
    ) -> BatchExperimentResult:
        """Executes a full experiment batch under the specified perturbation condition.

        Args:
            perturbation: The PerturbationType condition to test.
            num_runs: Total number of iterations to execute.

        Returns:
            BatchExperimentResult: Complete statistical outcome with Wilson confidence intervals.
        """
        backend = await self.resolve_execution_backend()
        label = get_perturbation_label(perturbation)

        if backend == "nebius_sandbox":
            try:
                run_results = await self._run_batch_nebius(perturbation, num_runs)
            except Exception as e:
                logger.warning(
                    "Nebius Sandbox execution encountered error: %s. Falling back to local_isolated.",
                    e,
                )
                backend = "local_isolated"
                self._cached_backend = "local_isolated"
                run_results = await self._run_batch_local(perturbation, num_runs)
        else:
            run_results = await self._run_batch_local(perturbation, num_runs)

        # Aggregate metrics
        passes = sum(1 for r in run_results if r.passed)
        failures = len(run_results) - passes
        total_runs = len(run_results)
        failure_rate = round(failures / total_runs, 4) if total_runs > 0 else 0.0

        ci_lower, ci_upper = wilson_ci_95(failures, total_runs)

        # Chronological pass/fail dots for UI dot-matrix
        run_dots = [r.passed for r in run_results]

        # Extract unique deduplicated failure snippets (up to 10)
        seen_logs: set[str] = set()
        sample_failure_logs: list[str] = []
        for r in run_results:
            if r.error_snippet and r.error_snippet not in seen_logs:
                seen_logs.add(r.error_snippet)
                sample_failure_logs.append(r.error_snippet)
                if len(sample_failure_logs) >= 10:
                    break

        return BatchExperimentResult(
            perturbation=perturbation,
            label=label,
            total_runs=total_runs,
            failures=failures,
            passes=passes,
            failure_rate=failure_rate,
            ci_95_lower=ci_lower,
            ci_95_upper=ci_upper,
            execution_backend=backend,
            sample_failure_logs=sample_failure_logs,
            run_dots=run_dots,
        )
