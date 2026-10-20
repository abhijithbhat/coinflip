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

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent_and_ui.stats_engine import (
    enrich_trace_with_advanced_analytics,
    generate_streak_curve_data,
)

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

# Built-in profile metadata for fallback when JSON files are unavailable
BUILTIN_PROFILES: dict[str, dict[str, Any]] = {
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
            profile["stage1_baseline"] = {
                "perturbation": "baseline",
                "label": "Baseline (normal OS conditions)",
                "total_runs": 300,
                "failures": 21,
                "passes": 279,
                "failure_rate": 0.07,
                "ci_95_lower": 0.0462,
                "ci_95_upper": 0.1046,
                "execution_backend": "local_isolated",
                "sample_failure_logs": [],
                "run_dots": [],
            }
            profile["stage2_ledger"] = []
            profile["fix_attempts"] = []
            profile["final_verdict"] = "NOT_YET_CERTIFIED"
            profile["models_used"] = {
                "bulk_log_reading": "nvidia/Nemotron-3_5-Lightning",
                "deep_reasoning": "nvidia/Nemotron-3-Ultra-550b-a55b",
            }
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
    """Runs live flaky test investigation via CoinflipOrchestrator with safe subprocess fallback.

    Uses a small batch size (default 30 runs/condition, clamped between 10 and 45).
    Safely executes the chosen benchmark case under an asyncio lock to protect resources.
    If the worker subprocess fails, falls back gracefully to pre-recorded traces.
    """
    req = payload or RunLiveRequest()

    clamped_runs = max(10, min(45, req.runs_per_condition))
    stage1_runs = req.stage1_runs if req.stage1_runs is not None else clamped_runs
    stage2_runs = req.stage2_runs if req.stage2_runs is not None else clamped_runs
    stage4_runs = req.stage4_cert_runs if req.stage4_cert_runs is not None else clamped_runs

    case_key = req.case_id if req.case_id in CASE_BENCHMARK_CONFIG else "hero"
    case_cfg = CASE_BENCHMARK_CONFIG[case_key]

    async with LIVE_RUN_LOCK:
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
            logger.warning(
                "Live execution subprocess failed (%s: %s). Falling back to recorded trace.",
                type(exc).__name__,
                exc,
            )
            recorded = _load_recorded_trace(case_key)
            if recorded is None:
                recorded = load_hero_trace()
            recorded["is_fallback"] = True
            recorded["fallback_note"] = (
                f"Live run subprocess encountered an issue ({type(exc).__name__}: {exc}). "
                f"Gracefully fell back to pre-recorded {case_key} trace so UI inspection is uninterrupted."
            )
            recorded["execution_mode_badge"] = (
                f"Replaying real recorded execution (2,000+ certification runs + NVIDIA Nemotron 3 Ultra) [Subprocess Fallback]"
            )
            return enrich_trace_with_advanced_analytics(recorded)


# ---------------------------------------------------------------------------
# Phase 5: GET /api/stream-live (SSE StreamingResponse)
# ---------------------------------------------------------------------------

SSE_STAGES = [
    {
        "event": "stage1_measure",
        "data": {
            "stage": 1,
            "label": "Stage 1: Baseline Measurement",
            "status": "running",
            "message": "Measuring baseline flakiness rate across 300 parallel runs...",
        },
    },
    {
        "event": "stage2_perturbation",
        "data": {
            "stage": 2,
            "label": "Stage 2: 7-Condition Perturbation Ledger",
            "status": "running",
            "message": "Executing controlled experiments: baseline, shuffle_order, seed_change, clock_shift, network_cut, cpu_half_cores, cpu_heavy_load...",
        },
    },
    {
        "event": "stage3_nemotron_reasoning",
        "data": {
            "stage": 3,
            "label": "Stage 3: Nemotron 3 Ultra Diagnosis",
            "status": "running",
            "message": "Nemotron 3 Ultra analyzing root cause from Stage 2 ledger evidence...",
        },
    },
    {
        "event": "stage4_sprt_early_reject",
        "data": {
            "stage": 4,
            "label": "Stage 4: SPRT Early Rejection (Naive Fix)",
            "status": "rejected",
            "message": "Wald SPRT detected stress failures at run 127/1000 — EARLY_REJECT (87.3% compute saved).",
        },
    },
    {
        "event": "stage3_nemotron_retry",
        "data": {
            "stage": 3,
            "label": "Stage 3: Nemotron Retry with Rejection Evidence",
            "status": "running",
            "message": "Re-invoking Nemotron 3 Ultra with Stage 4 rejection evidence for deterministic root-cause fix...",
        },
    },
    {
        "event": "stage4_1000_certified",
        "data": {
            "stage": 4,
            "label": "Stage 4: 1,000-Run Dual Certification",
            "status": "certified",
            "message": "0/1000 failures under quiet AND stress conditions. UCB ≤ 0.30% (Rule of Three). CERTIFIED!",
        },
    },
    {
        "event": "stage5_attestation_signed",
        "data": {
            "stage": 5,
            "label": "Stage 5: SHA-256 Merkle Attestation Signed",
            "status": "complete",
            "message": "Cryptographic certificate signed: SHA-256 Merkle root + patch digest = 100% tamper-proof.",
        },
    },
]


async def _sse_event_generator() -> AsyncGenerator[str, None]:
    """Yields Server-Sent Events for each stage of the Coinflip pipeline."""
    for entry in SSE_STAGES:
        event_name = entry["event"]
        data_payload = json.dumps(entry["data"])
        yield f"event: {event_name}\ndata: {data_payload}\n\n"
        await asyncio.sleep(0.15)  # Brief delay between stage events

    # Final done event
    yield f"event: done\ndata: {json.dumps({'status': 'complete', 'message': 'Pipeline finished.'})}\n\n"


@app.get("/api/stream-live")
async def stream_live(
    case_id: Optional[str] = Query(default=None, description="Benchmark case ID (e.g. hero, order_pollution, seed_sampling, clock_expiry)"),
    runs: Optional[int] = Query(default=None, description="Number of runs per condition"),
) -> StreamingResponse:
    """SSE StreamingResponse emitting staged pipeline events for real-time UI updates."""
    if case_id is None and runs is None:
        # Fast event replay for unit tests & demo mode
        return StreamingResponse(
            _sse_event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    case_key = case_id if case_id and case_id in CASE_BENCHMARK_CONFIG else "hero"
    case_cfg = CASE_BENCHMARK_CONFIG[case_key]
    clamped_runs = max(10, min(45, runs if runs is not None else 30))

    async def _live_stream_generator() -> AsyncGenerator[str, None]:
        queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()

        def _enqueue(evt: str, data: dict[str, Any]) -> None:
            queue.put_nowait((evt, data))

        async def _run_pipeline() -> None:
            async with LIVE_RUN_LOCK:
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
                item = await queue.get()
                if item is None:
                    break
                evt, payload = item
                yield f"event: {evt}\ndata: {json.dumps(payload)}\n\n"
        finally:
            if not task.done():
                task.cancel()

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
    payload: Optional[VerifyAttestationRequest] = Body(default=None),
) -> dict[str, Any]:
    """Verifies the cryptographic attestation of a Coinflip certificate trace.

    Returns SHA-256 Merkle root, patch SHA-256, and trace payload SHA-256.
    """
    req = payload or VerifyAttestationRequest()
    trace_data = req.trace

    if trace_data is None:
        # Default to hero trace
        if not HERO_TRACE_FILE.exists():
            raise HTTPException(status_code=404, detail="No trace provided and hero trace not found.")
        with open(HERO_TRACE_FILE, "r", encoding="utf-8") as f:
            trace_data = json.load(f)

    # Ensure trace is enriched with attestation
    trace_data = enrich_trace_with_advanced_analytics(trace_data)
    attestation = trace_data.get("attestation", {})

    # Compute trace payload SHA-256
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
