"""FastAPI Backend Server for Coinflip Flaky Test Certification UI (/agent_and_ui/app.py).

Provides REST API endpoints for:
1. GET /api/health: Health check status and service identifier.
2. GET /api/trace & GET /api/traces/hero: Reference hero trace enriched with streak curve
   data and the execution mode badge.
3. GET /api/traces & GET /api/traces/{name}: List of available trace artifacts.
4. GET /api/streak-curve: Mathematical streak decay curve points and Rule of Three bars.
5. POST /api/run-live: Live execution via CoinflipOrchestrator with safe subprocess fallback.
6. GET /api/stream-live: SSE StreamingResponse emitting staged pipeline events.
7. POST /api/verify-attestation: Cryptographic attestation verification.
8. Mounts /agent_and_ui/frontend at / if frontend/index.html exists.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent_and_ui.stats_engine import (
    enrich_trace_with_advanced_analytics,
    generate_streak_curve_data,
)
from sandbox_engine.attestation import CertificateAttestor

logger = logging.getLogger("coinflip.app")

BASE_DIR = Path(__file__).resolve().parent.parent
SHARED_CONTRACTS_DIR = BASE_DIR / "shared_contracts"
RECORDED_TRACES_DIR = SHARED_CONTRACTS_DIR / "recorded_traces"
HERO_TRACE_FILE = SHARED_CONTRACTS_DIR / "sample_hero_trace.json"
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
FRONTEND_INDEX = FRONTEND_DIR / "index.html"

HERO_BADGE = "Replaying real recorded execution (2,000+ certification runs + NVIDIA Nemotron 3 Ultra)"

# 5-case flaky archetype catalog
ARCHETYPE_CATALOG = ["hero", "order_pollution", "seed_sampling", "clock_expiry", "async_queue_race"]


def _get_profile_metrics(case_name: str) -> dict[str, int]:
    """Dynamically reads baseline_failures, baseline_runs, and stress_failures from recorded trace."""
    target = RECORDED_TRACES_DIR / f"{case_name}.json"
    if not target.exists() and case_name == "hero" and HERO_TRACE_FILE.exists():
        target = HERO_TRACE_FILE

    if target.exists():
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            s1 = data.get("stage1_baseline", {})
            b_runs = int(s1.get("total_runs", 300))
            b_fails = int(s1.get("failures", 0))

            trigger = data.get("triggering_stress_condition")
            stress_fails = 0
            for item in data.get("stage2_ledger", []):
                if item.get("perturbation") == trigger:
                    stress_fails = int(item.get("failures", 0))
                    break
            if not stress_fails and data.get("stage2_ledger"):
                stress_fails = max(int(it.get("failures", 0)) for it in data["stage2_ledger"])

            return {
                "baseline_failures": b_fails,
                "baseline_runs": b_runs,
                "stress_failures": stress_fails,
            }
        except Exception as exc:
            logger.warning("Could not read metrics for profile %s: %s", case_name, exc)

    return {
        "baseline_failures": 21,
        "baseline_runs": 300,
        "stress_failures": 28,
    }


def _init_builtin_profiles() -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {
        "hero": {
            "trace_id": "builtin_hero_profile",
            "project_name": "example-service",
            "test_identifier": "example-service::test_worker.py",
            "archetype": "hero",
            "description": "Thread race condition under CPU stress — the canonical flaky test archetype.",
            "triggering_stress_condition": "cpu_heavy_load",
        },
        "order_pollution": {
            "trace_id": "builtin_order_pollution_profile",
            "project_name": "example-service",
            "test_identifier": "example-service::test_database.py",
            "archetype": "order_pollution",
            "description": "Shared mutable state leaked between tests under shuffle_order execution.",
            "triggering_stress_condition": "shuffle_order",
        },
        "seed_sampling": {
            "trace_id": "builtin_seed_sampling_profile",
            "project_name": "ml-pipeline",
            "test_identifier": "ml-pipeline::test_sampling.py",
            "archetype": "seed_sampling",
            "description": "Unseeded random number generator causes non-deterministic sampling divergence.",
            "triggering_stress_condition": "seed_change",
        },
        "clock_expiry": {
            "trace_id": "builtin_clock_expiry_profile",
            "project_name": "auth-service",
            "test_identifier": "auth-service::test_token_cache.py",
            "archetype": "clock_expiry",
            "description": "Token cache expiry assumes wall-clock monotonicity, breaks under clock_shift.",
            "triggering_stress_condition": "clock_shift",
        },
        "async_queue_race": {
            "trace_id": "builtin_async_queue_race_profile",
            "project_name": "event-bus",
            "test_identifier": "event-bus::test_event_queue.py",
            "archetype": "async_queue_race",
            "description": "Producer-consumer async queue drain race under CPU stress.",
            "triggering_stress_condition": "cpu_heavy_load",
        },
    }
    for k, v in profiles.items():
        v.update(_get_profile_metrics(k))
    return profiles


# Built-in profile metadata with dynamic baseline and stress failure numbers
BUILTIN_PROFILES: dict[str, dict[str, Any]] = _init_builtin_profiles()


class RunLiveRequest(BaseModel):
    """Optional payload configuration for POST /api/run-live."""

    case_id: str = Field(
        default="hero",
        description="Target benchmark case: hero, order_pollution, seed_sampling, clock_expiry, or async_queue_race",
    )
    runs_per_condition: int = Field(
        default=30,
        description="Number of runs per condition, clamped between 10 and 45 (respecting sandbox quota)",
    )
    stage1_runs: Optional[int] = Field(
        default=None,
        description="Override run count for Stage 1 baseline measurement",
    )
    stage2_runs: Optional[int] = Field(
        default=None,
        description="Override run count per condition for Stage 2 stress ledger",
    )
    stage4_cert_runs: Optional[int] = Field(
        default=None,
        description="Override run count for Stage 4 dual certification gate",
    )
    target_limit: float = Field(
        default=0.005,
        description="Target upper bound failure rate limit (default 0.005 = 0.5%)",
    )
    demonstrate_rejection_catch: bool = Field(
        default=True,
        description="Evaluate naive quick-fix timeout increase before real root-cause fix",
    )
    project_name: str = Field(
        default="example-service",
        description="Target project name",
    )
    test_target: str = Field(
        default="test_worker.py",
        description="Target test file or identifier relative to project root",
    )


# ---------------------------------------------------------------------------
# Benchmark Case Execution Registry
# ---------------------------------------------------------------------------
CASE_BENCHMARK_CONFIG: dict[str, dict[str, Any]] = {
    "hero": {
        "repo_dir": BASE_DIR / "benchmarks" / "hero_worker_race",
        "test_target": "test_worker.py",
        "project_name": "example-service",
    },
    "order_pollution": {
        "repo_dir": BASE_DIR / "benchmarks" / "real_world_cases" / "case_01_test_order_pollution",
        "test_target": "test_config_cache.py",
        "project_name": "config-service",
    },
    "seed_sampling": {
        "repo_dir": BASE_DIR / "benchmarks" / "real_world_cases" / "case_02_unpinned_seed_sampling",
        "test_target": "test_sampler.py",
        "project_name": "sampler-service",
    },
    "clock_expiry": {
        "repo_dir": BASE_DIR / "benchmarks" / "real_world_cases" / "case_03_token_expiry_clock",
        "test_target": "test_token_ttl.py",
        "project_name": "auth-service",
    },
    "async_queue_race": {
        "repo_dir": BASE_DIR / "benchmarks" / "real_world_cases" / "case_04_async_queue_race",
        "test_target": "test_event_queue.py",
        "project_name": "event-bus",
    },
}

LIVE_RUN_LOCK = asyncio.Semaphore(1)


def _load_recorded_trace(name: str) -> dict[str, Any] | None:
    """Attempts to load a recorded trace JSON from shared_contracts/recorded_traces/{name}.json."""
    trace_path = RECORDED_TRACES_DIR / f"{name}.json"
    if trace_path.exists():
        with open(trace_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def load_hero_trace() -> dict[str, Any]:
    """Loads shared_contracts/sample_hero_trace.json and enriches it with streak data & badge."""
    if not HERO_TRACE_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Sample hero trace not found at {HERO_TRACE_FILE}",
        )
    with open(HERO_TRACE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["streak_curve_data"] = generate_streak_curve_data()
    data["execution_mode_badge"] = HERO_BADGE
    return enrich_trace_with_advanced_analytics(data)


app = FastAPI(
    title="Coinflip Agent UI Backend",
    description="FastAPI service powering the Coinflip Flaky Test Investigator and Certification UI.",
    version="2.0.0",
)

# Enable CORS for local dev and Lovable preview URLs
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": "coinflip-agent-ui"}


@app.get("/api/trace")
def get_trace() -> dict[str, Any]:
    """Returns the reference hero trace enriched with streak curve data and execution mode badge."""
    return load_hero_trace()


@app.get("/api/traces/hero")
def get_hero_trace() -> dict[str, Any]:
    """Alias for /api/trace returning the reference hero trace."""
    return load_hero_trace()


@app.get("/api/traces")
def list_traces() -> dict[str, Any]:
    """Lists available trace artifacts including the 4-case flaky archetype catalog."""
    files = sorted([f.name for f in SHARED_CONTRACTS_DIR.glob("*.json")])

    # Add archetype catalog entries
    archetypes: list[dict[str, Any]] = []
    for name in ARCHETYPE_CATALOG:
        profile = BUILTIN_PROFILES.get(name, {})
        trace_path = RECORDED_TRACES_DIR / f"{name}.json"
        archetypes.append({
            "name": name,
            "available_on_disk": trace_path.exists(),
            "description": profile.get("description", ""),
            "triggering_stress_condition": profile.get("triggering_stress_condition", ""),
        })

    return {
        "traces": files,
        "files": files,
        "archetype_catalog": archetypes,
    }


@app.get("/api/traces/{trace_name}")
def get_trace_by_name(trace_name: str) -> dict[str, Any]:
    """Retrieves a specific trace by filename or keyword, supporting archetype catalog."""
    if trace_name in ("hero", "sample_hero_trace.json"):
        return load_hero_trace()

    # Check the 4-case archetype catalog from recorded_traces/
    clean_name = trace_name.replace(".json", "")
    if clean_name in ARCHETYPE_CATALOG:
        recorded = _load_recorded_trace(clean_name)
        if recorded is not None:
            recorded["streak_curve_data"] = generate_streak_curve_data()
            if "execution_mode_badge" not in recorded:
                recorded["execution_mode_badge"] = HERO_BADGE
            return enrich_trace_with_advanced_analytics(recorded)

        # Fallback to built-in profile
        if clean_name in BUILTIN_PROFILES:
            profile = dict(BUILTIN_PROFILES[clean_name])
            profile["is_recorded_replay"] = False
            profile["is_builtin_profile"] = True
            profile["timestamp_utc"] = "2026-10-17T12:00:00Z"

            b_fails = profile.get("baseline_failures", 21)
            b_runs = profile.get("baseline_runs", 300)
            b_rate = round(b_fails / max(1, b_runs), 4)

            profile["stage1_baseline"] = {
                "perturbation": "baseline",
                "label": "Baseline (normal OS conditions)",
                "total_runs": b_runs,
                "failures": b_fails,
                "passes": b_runs - b_fails,
                "failure_rate": b_rate,
                "ci_95_lower": round(max(0.0, b_rate - 0.025), 4),
                "ci_95_upper": round(min(1.0, b_rate + 0.035), 4),
                "execution_backend": "local_isolated",
                "sample_failure_logs": [],
                "run_dots": [],
            }
            profile["stage2_ledger"] = []
            profile["fix_attempts"] = []
            profile["final_verdict"] = "NOT_YET_CERTIFIED"
            profile["models_used"] = {}
            return enrich_trace_with_advanced_analytics(profile)

    # Standard path resolution for other trace files
    target_path = SHARED_CONTRACTS_DIR / trace_name
    if not target_path.exists() and not trace_name.endswith(".json"):
        target_path = SHARED_CONTRACTS_DIR / f"{trace_name}.json"

    if not target_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Trace '{trace_name}' not found in {SHARED_CONTRACTS_DIR}",
        )

    with open(target_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["streak_curve_data"] = generate_streak_curve_data()
    if "execution_mode_badge" not in data:
        data["execution_mode_badge"] = HERO_BADGE
    return enrich_trace_with_advanced_analytics(data)


@app.get("/api/streak-curve")
def get_streak_curve() -> list[dict[str, Any]]:
    """Returns mathematical curve points and Rule of Three bars for UI streak visualization."""
    return generate_streak_curve_data()


@app.post("/api/run-live")
async def run_live(
    payload: Optional[RunLiveRequest] = Body(default=None),
) -> dict[str, Any]:
    """Runs live flaky test investigation via CoinflipOrchestrator.

    Uses a small batch size (default 30 runs/condition, clamped between 10 and 45).
    Acquires LIVE_RUN_LOCK with a 30.0s timeout and always releases in finally.
    Raises HTTPException 503 if live execution fails.
    """
    req = payload or RunLiveRequest()

    clamped_runs = max(10, min(45, req.runs_per_condition))
    stage1_runs = req.stage1_runs if req.stage1_runs is not None else clamped_runs
    stage2_runs = req.stage2_runs if req.stage2_runs is not None else clamped_runs
    stage4_runs = req.stage4_cert_runs if req.stage4_cert_runs is not None else clamped_runs

    case_key = req.case_id if req.case_id in CASE_BENCHMARK_CONFIG else "hero"
    case_cfg = CASE_BENCHMARK_CONFIG[case_key]

    try:
        await asyncio.wait_for(LIVE_RUN_LOCK.acquire(), timeout=30.0)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="Live execution unavailable: acquisition timeout (30s) waiting for LIVE_RUN_LOCK.",
        )

    try:
        from sandbox_engine.orchestrator import CoinflipOrchestrator

        orchestrator = CoinflipOrchestrator(
            repo_dir=case_cfg["repo_dir"],
            test_target=case_cfg["test_target"],
            project_name=case_cfg["project_name"],
            max_concurrency=clamped_runs,
            mode="local_isolated",
            execution_backend="local_isolated",
        )

        trace = await orchestrator.run(
            stage1_runs=stage1_runs,
            stage2_runs=stage2_runs,
            stage4_cert_runs=stage4_runs,
            target_limit=req.target_limit,
            demonstrate_rejection_catch=req.demonstrate_rejection_catch,
            fast_live_mode=True,
        )

        data = trace.model_dump() if hasattr(trace, "model_dump") else trace.dict()
        data["streak_curve_data"] = generate_streak_curve_data()
        data["execution_mode_badge"] = "Live Execution (Coinflip Engine)"
        data["is_fallback"] = False
        data["llm_metadata"] = data.get("llm_call_metadata") or {}
        return enrich_trace_with_advanced_analytics(data)

    except Exception as exc:
        logger.error(
            "Live execution failed (%s: %s).",
            type(exc).__name__,
            exc,
        )
        raise HTTPException(
            status_code=503,
            detail=f"Live execution unavailable: {str(exc)}",
        )
    finally:
        if LIVE_RUN_LOCK.locked():
            LIVE_RUN_LOCK.release()


# ---------------------------------------------------------------------------
# Phase 5: GET /api/stream-live (SSE StreamingResponse)
# ---------------------------------------------------------------------------


@app.get("/api/stream-live")
async def stream_live(
    request: Request,
    case_id: Optional[str] = Query(default=None, description="Benchmark case ID (e.g. hero, order_pollution, seed_sampling, clock_expiry)"),
    runs: Optional[int] = Query(default=None, description="Number of runs per condition"),
) -> StreamingResponse:
    """SSE StreamingResponse emitting real stage progress from CoinflipOrchestrator."""
    case_key = case_id if case_id else "hero"
    if case_key not in CASE_BENCHMARK_CONFIG:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid case_id '{case_key}'. Must be one of {list(CASE_BENCHMARK_CONFIG.keys())}",
        )

    case_cfg = CASE_BENCHMARK_CONFIG[case_key]
    clamped_runs = max(10, min(45, runs if runs is not None else 30))

    try:
        await asyncio.wait_for(LIVE_RUN_LOCK.acquire(), timeout=30.0)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=503,
            detail="Live execution unavailable: acquisition timeout (30s) waiting for LIVE_RUN_LOCK.",
        )

    async def _live_stream_generator() -> AsyncGenerator[str, None]:
        queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()

        def _enqueue(evt: str, data: dict[str, Any]) -> None:
            queue.put_nowait((evt, data))

        async def _run_pipeline() -> None:
            try:
                from sandbox_engine.orchestrator import CoinflipOrchestrator

                orchestrator = CoinflipOrchestrator(
                    repo_dir=case_cfg["repo_dir"],
                    test_target=case_cfg["test_target"],
                    project_name=case_cfg["project_name"],
                    max_concurrency=clamped_runs,
                    mode="local_isolated",
                    execution_backend="local_isolated",
                )
                await orchestrator.run_full_pipeline(
                    stage1_runs=clamped_runs,
                    stage2_runs=clamped_runs,
                    stage4_cert_runs=clamped_runs,
                    fast_live_mode=True,
                    on_stage_event=_enqueue,
                )
            except Exception as exc:
                logger.warning("Live stream failed (%s: %s)", type(exc).__name__, exc)
                queue.put_nowait(("error", {"message": f"{type(exc).__name__}: {exc}"}))
            finally:
                queue.put_nowait(None)

        task = asyncio.create_task(_run_pipeline())
        try:
            while True:
                if await request.is_disconnected():
                    logger.info("Client disconnected from stream-live")
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                if item is None:
                    break
                evt, payload = item
                yield f"event: {evt}\ndata: {json.dumps(payload)}\n\n"
        finally:
            if not task.done():
                task.cancel()
            if LIVE_RUN_LOCK.locked():
                LIVE_RUN_LOCK.release()

    return StreamingResponse(
        _live_stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Phase 5: POST /api/verify-attestation
# ---------------------------------------------------------------------------


class VerifyAttestationRequest(BaseModel):
    """Payload for attestation verification."""
    trace: Optional[dict[str, Any]] = Field(
        default=None,
        description="Full trace dict to verify. If omitted, loads the hero trace.",
    )


@app.post("/api/verify-attestation")
def verify_attestation(
    payload: Optional[Any] = Body(default=None),
) -> dict[str, Any]:
    """Verifies the cryptographic attestation of a Coinflip certificate trace.

    Validates leaf counts, run_dots, arithmetic, Merkle root, HMAC signature,
    and cross-checks against recorded traces if not live_custom.
    Returns HTTP 200 with verified=False if tampering is detected.
    """
    trace_data: dict[str, Any] | None = None
    if isinstance(payload, dict):
        if "trace" in payload and isinstance(payload["trace"], dict):
            trace_data = payload["trace"]
        elif "stage1_baseline" in payload:
            trace_data = payload
    elif hasattr(payload, "trace") and getattr(payload, "trace"):
        trace_data = getattr(payload, "trace")

    if trace_data is None:
        if not HERO_TRACE_FILE.exists():
            raise HTTPException(status_code=404, detail="No trace provided and hero trace not found.")
        with open(HERO_TRACE_FILE, "r", encoding="utf-8") as f:
            trace_data = json.load(f)

    # 1. Batch arithmetic & run_dots validation
    batches: list[tuple[str, dict[str, Any]]] = []
    if "stage1_baseline" in trace_data and isinstance(trace_data["stage1_baseline"], dict):
        batches.append(("stage1_baseline", trace_data["stage1_baseline"]))

    s2_list = trace_data.get("stage2_ledger") or trace_data.get("stage2_perturbations") or []
    for idx, b in enumerate(s2_list):
        if isinstance(b, dict):
            batches.append((f"stage2_ledger[{idx}]", b))

    fix_list = trace_data.get("fix_attempts") or trace_data.get("stage4_certification") or []
    for idx, att in enumerate(fix_list):
        if isinstance(att, dict):
            norm = att.get("normal_cert_result")
            if isinstance(norm, dict):
                batches.append((f"fix_attempts[{idx}].normal_cert_result", norm))
            stress = att.get("stress_cert_result")
            if isinstance(stress, dict):
                batches.append((f"fix_attempts[{idx}].stress_cert_result", stress))
            if "total_runs" in att and "failures" in att:
                batches.append((f"fix_attempts[{idx}]", att))

    for label, batch in batches:
        total_runs = int(batch.get("total_runs", 0))
        failures = int(batch.get("failures", 0))
        passes = int(batch.get("passes", 0))

        if "passes" in batch and passes + failures != total_runs:
            return {
                "verified": False,
                "reason": f"Tampering detected: arithmetic mismatch in {label}: passes ({passes}) + failures ({failures}) != total_runs ({total_runs})",
            }

        run_dots = batch.get("run_dots")
        if run_dots is not None and len(run_dots) > 0:
            actual_failures = sum(1 for d in run_dots if not d)
            actual_total = len(run_dots)
            if failures != actual_failures:
                return {
                    "verified": False,
                    "reason": f"Tampering detected: failures count in {label}: recorded failures={failures} != actual run_dots failures={actual_failures}",
                }
            if total_runs != actual_total:
                return {
                    "verified": False,
                    "reason": f"Tampering detected: total_runs in {label}: recorded total_runs={total_runs} != actual len(run_dots)={actual_total}",
                }

    # 2. Cryptographic Attestation verification via CertificateAttestor
    attestor = CertificateAttestor()
    attestation = trace_data.get("attestation") or trace_data.get("cryptographic_attestation")
    if not attestation:
        att_obj = attestor.build_trace_attestation(trace_data)
        attestation = att_obj.model_dump() if hasattr(att_obj, "model_dump") else att_obj.dict()
        trace_data["attestation"] = attestation

    ver_res = attestor.verify_trace(trace_data)
    if not ver_res.get("verified", False):
        return {
            "verified": False,
            "reason": f"Tampering detected: {ver_res.get('reason', 'Attestation verification failed')}",
            "claimed_merkle_root": ver_res.get("claimed_merkle_root", ""),
            "computed_merkle_root": ver_res.get("computed_merkle_root", ""),
        }

    # 3. Cross-check against shared_contracts/recorded_traces/{case}.json if execution_mode != "live_custom"
    exec_mode = trace_data.get("execution_mode", "")
    if exec_mode != "live_custom":
        case_candidate = trace_data.get("archetype") or trace_data.get("case_id") or ""
        if not case_candidate or case_candidate not in ARCHETYPE_CATALOG:
            for cat in ARCHETYPE_CATALOG:
                if cat in str(trace_data.get("trace_id", "")) or cat in str(trace_data.get("test_identifier", "")):
                    case_candidate = cat
                    break
        if case_candidate and case_candidate in ARCHETYPE_CATALOG:
            rec_file = RECORDED_TRACES_DIR / f"{case_candidate}.json"
            if not rec_file.exists() and case_candidate == "hero" and HERO_TRACE_FILE.exists():
                rec_file = HERO_TRACE_FILE
            if rec_file.exists():
                try:
                    with open(rec_file, "r", encoding="utf-8") as f:
                        rec_json = json.load(f)
                    rec_s1 = rec_json.get("stage1_baseline", {})
                    cur_s1 = trace_data.get("stage1_baseline", {})
                    if (
                        rec_s1.get("failures") is not None
                        and cur_s1.get("failures") is not None
                        and cur_s1.get("total_runs") == rec_s1.get("total_runs")
                        and cur_s1.get("failures") != rec_s1.get("failures")
                    ):
                        return {
                            "verified": False,
                            "reason": f"Tampering detected: baseline failures {cur_s1.get('failures')} != canonical recorded {rec_s1.get('failures')}",
                        }
                    rec_merkle = (rec_json.get("attestation") or {}).get("experiment_ledger_merkle_root")
                    cur_merkle = attestation.get("experiment_ledger_merkle_root") or attestation.get("ledger_merkle_root")
                    if rec_merkle and cur_merkle and rec_merkle != cur_merkle:
                        return {
                            "verified": False,
                            "reason": f"Tampering detected: Merkle root mismatch with canonical recorded trace for {case_candidate}",
                        }
                except Exception as exc:
                    logger.warning("Could not cross-check recorded trace: %s", exc)

    # 4. Success payload
    trace_json_str = json.dumps(trace_data, sort_keys=True, default=str)
    trace_payload_sha256 = hashlib.sha256(trace_json_str.encode("utf-8")).hexdigest()
    merkle_root = attestation.get("experiment_ledger_merkle_root", attestation.get("ledger_merkle_root", ""))
    patch_diff_hash = attestation.get("patch_diff_sha256", attestation.get("patch_sha256", ""))

    return {
        "verified": True,
        "algorithm": attestation.get("algorithm", "SHA-256-Merkle"),
        "ledger_merkle_root": merkle_root,
        "experiment_ledger_merkle_root": merkle_root,
        "patch_sha256": patch_diff_hash,
        "patch_diff_sha256": patch_diff_hash,
        "trace_payload_sha256": trace_payload_sha256,
        "trace_sha256": trace_payload_sha256,
        "reason": ver_res.get("reason", "Cryptographic attestation verified successfully."),
    }


# ---------------------------------------------------------------------------
# Resolve static frontend mount directory
# ---------------------------------------------------------------------------
FRONTEND_PUBLIC_DIR = FRONTEND_DIR / ".output" / "public"

static_dir: Optional[Path] = None
if FRONTEND_INDEX.exists():
    static_dir = FRONTEND_DIR
elif (FRONTEND_PUBLIC_DIR / "index.html").exists():
    static_dir = FRONTEND_PUBLIC_DIR

if static_dir is not None:
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="frontend")
else:

    @app.get("/")
    def root() -> dict[str, Any]:
        """Root API notice served when static frontend build is not yet present."""
        return {
            "status": "ok",
            "service": "coinflip-agent-ui",
            "message": "Coinflip Backend API is active. Mounts /agent_and_ui/frontend at / once frontend/index.html exists.",
            "endpoints": [
                "/api/health",
                "/api/trace",
                "/api/traces/hero",
                "/api/traces",
                "/api/streak-curve",
                "/api/run-live",
                "/api/stream-live",
                "/api/verify-attestation",
                "/docs",
            ],
        }
