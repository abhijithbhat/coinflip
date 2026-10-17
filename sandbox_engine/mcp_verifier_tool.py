"""Coinflip MCP Verifier Tool & CLI for External AI Coding Agents.

Implements the agent-callable verification tool from Concept Brief Pages 6 & 10:
External AI agents (Cursor, Devin, Claude Code, Codex, Antigravity) call:
`verify_patch_in_sandbox(repo_path, test_identifier, patch_diff, stress_condition, runs)`
to verify whether a passing green test is genuine or deceptively masking concurrency/timing flakes.

CLI usage:
    python -m sandbox_engine.mcp_verifier_tool --help
    python -m sandbox_engine.mcp_verifier_tool --repo-path ./my_project --test tests/test_foo.py --runs 100
    python -m sandbox_engine.mcp_verifier_tool --mcp
"""

from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any

from sandbox_engine.batch_runner import SandboxBatchRunner
from sandbox_engine.image_builder import SandboxImageBuilder
from sandbox_engine.math_utils import upper_confidence_bound_95, wilson_ci_95
from shared_contracts.schemas import PerturbationType

logger = logging.getLogger("sandbox_engine.mcp_verifier_tool")


async def verify_patch_in_sandbox_async(
    repo_path: str,
    test_identifier: str,
    patch_diff: str = "",
    stress_condition: str = "cpu_heavy_load",
    runs: int = 100,
    mode: str = "auto",
    target_limit: float = 0.005,
) -> dict[str, Any]:
    """Asynchronously certifies candidate patches under quiet and stress conditions.

    Args:
        repo_path: Path to the target repository directory.
        test_identifier: Relative path or pytest test identifier (e.g. 'tests/test_worker.py').
        patch_diff: Unified diff string or file replacement code. If empty, tests existing code.
        stress_condition: Perturbation condition to test (default: 'cpu_heavy_load').
        runs: Number of iterations to execute per condition (default: 100).
        mode: Execution backend ('auto', 'local_isolated', 'nebius_sandbox').
        target_limit: Target failure rate upper bound for certification (default: 0.5%).

    Returns:
        dict: Empirical pass/fail metrics, upper confidence bound, and trustworthiness verdict.
    """
    repo = Path(repo_path).resolve()
    if not repo.exists():
        return {
            "trustworthy": False,
            "verdict": "ERROR",
            "summary": f"Repository path not found: {repo}",
            "error": f"Repository path not found: {repo}",
        }

    # Resolve perturbation type
    try:
        stress_perturbation = PerturbationType(stress_condition)
    except ValueError:
        stress_perturbation = PerturbationType.CPU_HEAVY_LOAD

    # 1. Create base or patched snapshot
    image_builder = SandboxImageBuilder(mode=mode)
    base_snapshot_id = image_builder.create_base_snapshot(repo)

    if patch_diff and patch_diff.strip():
        # Derive patched snapshot
        patched_snapshot_id = image_builder.create_patched_snapshot(
            base_snapshot_id=base_snapshot_id,
            patch_content=patch_diff,
            target_file_rel=test_identifier if not patch_diff.strip().startswith("---") else None,
        )
        test_workspace = image_builder.get_snapshot_path(patched_snapshot_id)
    else:
        test_workspace = image_builder.get_snapshot_path(base_snapshot_id)

    # 2. Run Normal / Quiet Baseline runs
    runner = SandboxBatchRunner(
        repo_dir=test_workspace,
        test_target=test_identifier,
        max_concurrency=45,
        mode=mode,
    )

    normal_batch = await runner.run_batch(
        perturbation=PerturbationType.BASELINE,
        num_runs=runs,
    )

    # 3. Run Stress runs under triggering condition
    stress_batch = await runner.run_batch(
        perturbation=stress_perturbation,
        num_runs=runs,
    )

    # 4. Statistical upper confidence bounds (Rule of Three or Wilson UCB)
    upper_normal = upper_confidence_bound_95(normal_batch.failures, normal_batch.total_runs)
    upper_stress = upper_confidence_bound_95(stress_batch.failures, stress_batch.total_runs)

    # 5. Formulate verdict
    if normal_batch.failures > 0:
        verdict = "REJECTED_BASELINE_FAILURE"
        trustworthy = False
        summary = (
            f"Patch is NOT trustworthy: failed {normal_batch.failures}/{normal_batch.total_runs} "
            f"normal baseline runs ({normal_batch.failure_rate * 100:.1f}% failure rate)."
        )
    elif stress_batch.failures > 0:
        verdict = "REJECTED_STRESS_FAILURE"
        trustworthy = False
        summary = (
            f"DECEPTIVE PASS DETECTED: Patch passed all {normal_batch.total_runs} normal runs, "
            f"but failed {stress_batch.failures}/{stress_batch.total_runs} runs under "
            f"'{stress_perturbation.value}' stress ({stress_batch.failure_rate * 100:.1f}% failure rate, "
            f"95% UCB: {upper_stress * 100:.2f}% vs limit {target_limit * 100:.2f}%)."
        )
    else:
        verdict = "CERTIFIED"
        trustworthy = True
        summary = (
            f"Patch is CERTIFIED & TRUSTWORTHY: passed {normal_batch.total_runs} normal runs "
            f"and {stress_batch.total_runs} stress runs with 0 failures "
            f"(95% UCB <= {upper_stress * 100:.2f}%)."
        )

    return {
        "trustworthy": trustworthy,
        "verdict": verdict,
        "test_identifier": test_identifier,
        "stress_condition": stress_perturbation.value,
        "target_limit": target_limit,
        "normal_runs": {
            "total": normal_batch.total_runs,
            "passed": normal_batch.total_runs - normal_batch.failures,
            "failed": normal_batch.failures,
            "failure_rate": normal_batch.failure_rate,
            "ci_95": [normal_batch.ci_95_lower, normal_batch.ci_95_upper],
            "upper_confidence_bound_95": upper_normal,
        },
        "stress_runs": {
            "condition": stress_perturbation.value,
            "total": stress_batch.total_runs,
            "passed": stress_batch.total_runs - stress_batch.failures,
            "failed": stress_batch.failures,
            "failure_rate": stress_batch.failure_rate,
            "ci_95": [stress_batch.ci_95_lower, stress_batch.ci_95_upper],
            "upper_confidence_bound_95": upper_stress,
        },
        "summary": summary,
        "sample_failure_logs": stress_batch.sample_failure_logs or normal_batch.sample_failure_logs or [],
    }


def verify_patch_in_sandbox(
    repo_path: str,
    test_identifier: str,
    patch_diff: str = "",
    stress_condition: str = "cpu_heavy_load",
    runs: int = 100,
    mode: str = "auto",
    target_limit: float = 0.005,
) -> dict[str, Any]:
    """Synchronous interface for external AI coding agents to call Coinflip Sandbox Verifier."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(
                asyncio.run,
                verify_patch_in_sandbox_async(
                    repo_path=repo_path,
                    test_identifier=test_identifier,
                    patch_diff=patch_diff,
                    stress_condition=stress_condition,
                    runs=runs,
                    mode=mode,
                    target_limit=target_limit,
                ),
            ).result()
    else:
        return asyncio.run(
            verify_patch_in_sandbox_async(
                repo_path=repo_path,
                test_identifier=test_identifier,
                patch_diff=patch_diff,
                stress_condition=stress_condition,
                runs=runs,
                mode=mode,
                target_limit=target_limit,
            )
        )


def _run_mcp_stdio_server() -> None:
    """Lightweight Model Context Protocol (MCP) JSON-RPC stdio server."""
    tool_definition = {
        "name": "verify_patch_in_sandbox",
        "description": (
            "Empirically verifies whether a passing green test is genuine or masking concurrency flakes "
            "by executing dual quiet and stress test batches in isolated sandboxes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Absolute or relative path to the repository to test.",
                },
                "test_identifier": {
                    "type": "string",
                    "description": "Test target file path or pytest node ID (e.g. tests/test_worker.py).",
                },
                "patch_diff": {
                    "type": "string",
                    "description": "Unified git diff or patched code to apply before testing.",
                    "default": "",
                },
                "stress_condition": {
                    "type": "string",
                    "enum": [p.value for p in PerturbationType],
                    "default": "cpu_heavy_load",
                    "description": "Perturbation condition to apply during stress runs.",
                },
                "runs": {
                    "type": "integer",
                    "default": 100,
                    "description": "Number of runs to execute per condition (e.g. 100 or 300).",
                },
            },
            "required": ["repo_path", "test_identifier"],
        },
    }

    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            req_id = req.get("id")
            method = req.get("method")

            if method == "tools/list":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"tools": [tool_definition]},
                }
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
            elif method == "tools/call":
                params = req.get("params", {})
                args = params.get("arguments", {})
                result = verify_patch_in_sandbox(
                    repo_path=args.get("repo_path", "."),
                    test_identifier=args.get("test_identifier", ""),
                    patch_diff=args.get("patch_diff", ""),
                    stress_condition=args.get("stress_condition", "cpu_heavy_load"),
                    runs=int(args.get("runs", 100)),
                )
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result, indent=2),
                            }
                        ],
                        "isError": not result.get("trustworthy", False),
                    },
                }
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
            else:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {},
                }
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
        except Exception as e:
            err_resp = {
                "jsonrpc": "2.0",
                "id": req.get("id") if "req" in locals() else None,
                "error": {"code": -32603, "message": str(e)},
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m sandbox_engine.mcp_verifier_tool",
        description="Coinflip Sandbox Patch Verifier & Trustworthiness Certifier for AI Coding Agents.",
    )
    parser.add_argument(
        "--repo-path",
        default=".",
        help="Path to repository directory (default: current directory)",
    )
    parser.add_argument(
        "--test",
        "--test-identifier",
        dest="test_identifier",
        default="test_worker.py",
        help="Target test file or identifier relative to repo (e.g. tests/test_worker.py)",
    )
    parser.add_argument(
        "--patch",
        "--patch-diff",
        dest="patch_diff",
        default="",
        help="Patch diff string or path to a .patch / .diff file to apply before testing",
    )
    parser.add_argument(
        "--stress-condition",
        default="cpu_heavy_load",
        choices=[p.value for p in PerturbationType],
        help="Perturbation stress condition to evaluate (default: cpu_heavy_load)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=100,
        help="Number of iterations to execute for quiet and stress tests (default: 100)",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "local_isolated", "nebius_sandbox"],
        default="auto",
        help="Execution mode (default: auto)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON results",
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Run in MCP JSON-RPC stdio server mode for direct tool calling by AI agents",
    )

    args = parser.parse_args()

    if args.mcp:
        _run_mcp_stdio_server()
        return

    # If patch_diff is a file path that exists, read its contents
    patch_content = args.patch_diff
    if patch_content and Path(patch_content).exists():
        patch_content = Path(patch_content).read_text(encoding="utf-8")

    result = verify_patch_in_sandbox(
        repo_path=args.repo_path,
        test_identifier=args.test_identifier,
        patch_diff=patch_content,
        stress_condition=args.stress_condition,
        runs=args.runs,
        mode=args.mode,
    )

    if args.json:
        print(json.dumps(result, indent=2))
        return

    # Human-readable CLI formatting
    status_icon = "✅" if result["trustworthy"] else "❌"
    print("\n" + "=" * 80)
    print(f"COINFLIP AGENT VERIFICATION REPORT {status_icon} [{result['verdict']}]")
    print("=" * 80)
    print(f"Target:       {result['test_identifier']}")
    print(f"Trustworthy:  {result['trustworthy']}")
    print(f"Verdict:      {result['verdict']}")
    print(f"Summary:      {result['summary']}")
    print("-" * 80)
    print(f"Normal Runs:  {result['normal_runs']['passed']}/{result['normal_runs']['total']} passed "
          f"({result['normal_runs']['failure_rate']*100:.1f}% failure rate) "
          f"[95% UCB: {result['normal_runs']['upper_confidence_bound_95']*100:.2f}%]")
    print(f"Stress Runs:  {result['stress_runs']['passed']}/{result['stress_runs']['total']} passed "
          f"({result['stress_runs']['failure_rate']*100:.1f}% failure rate) "
          f"[95% UCB: {result['stress_runs']['upper_confidence_bound_95']*100:.2f}%]")
    print("=" * 80 + "\n")

    sys.exit(0 if result["trustworthy"] else 1)


if __name__ == "__main__":
    main()
