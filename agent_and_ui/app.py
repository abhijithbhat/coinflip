"""FastAPI Backend Server for Coinflip Flaky Test Certification UI (/agent_and_ui/app.py).

Provides REST API endpoints for:
1. GET /api/health: Health check status and service identifier.
2. GET /api/trace & GET /api/traces/hero: Reference hero trace enriched with streak curve
   data and the execution mode badge.
3. GET /api/traces & GET /api/traces/{name}: List of available trace artifacts.
4. GET /api/streak-curve: Mathematical streak decay curve points and Rule of Three bars.
5. POST /api/run-live: Live execution via CoinflipOrchestrator with safe subprocess fallback.
6. Mounts /agent_and_ui/frontend at / if frontend/index.html exists.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent_and_ui.stats_engine import generate_streak_curve_data

logger = logging.getLogger("coinflip.app")

BASE_DIR = Path(__file__).resolve().parent.parent
SHARED_CONTRACTS_DIR = BASE_DIR / "shared_contracts"
HERO_TRACE_FILE = SHARED_CONTRACTS_DIR / "sample_hero_trace.json"
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
FRONTEND_INDEX = FRONTEND_DIR / "index.html"

HERO_BADGE = "Replaying real recorded execution (2,000+ certification runs + NVIDIA Nemotron 3 Ultra)"


class RunLiveRequest(BaseModel):
    """Optional payload configuration for POST /api/run-live."""

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
    return data


app = FastAPI(
    title="Coinflip Agent UI Backend",
    description="FastAPI service powering the Coinflip Flaky Test Investigator and Certification UI.",
    version="1.0.0",
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
    """Lists available .json trace files in shared_contracts/."""
    files = sorted([f.name for f in SHARED_CONTRACTS_DIR.glob("*.json")])
    return {"traces": files, "files": files}


@app.get("/api/traces/{trace_name}")
def get_trace_by_name(trace_name: str) -> dict[str, Any]:
    """Retrieves a specific trace by filename or keyword."""
    if trace_name in ("hero", "sample_hero_trace.json"):
        return load_hero_trace()

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
    return data


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
    If the local Windows worker subprocess fails or throws an exception,
    gracefully catches the error and falls back to returning the enriched hero trace
    with a clear explanation note so the UI never crashes.
    """
    req = payload or RunLiveRequest()

    clamped_runs = max(10, min(45, req.runs_per_condition))
    stage1_runs = req.stage1_runs if req.stage1_runs is not None else clamped_runs
    stage2_runs = req.stage2_runs if req.stage2_runs is not None else clamped_runs
    stage4_runs = req.stage4_cert_runs if req.stage4_cert_runs is not None else clamped_runs

    try:
        from sandbox_engine.orchestrator import CoinflipOrchestrator

        benchmarks_dir = BASE_DIR / "benchmarks"
        project_bench_dir = benchmarks_dir / req.project_name
        target_repo = project_bench_dir if project_bench_dir.exists() else benchmarks_dir

        orchestrator = CoinflipOrchestrator(
            repo_dir=target_repo,
            test_target=req.test_target,
            project_name=req.project_name,
            max_concurrency=clamped_runs,
        )

        trace = await orchestrator.run(
            stage1_runs=stage1_runs,
            stage2_runs=stage2_runs,
            stage4_cert_runs=stage4_runs,
            target_limit=req.target_limit,
            demonstrate_rejection_catch=req.demonstrate_rejection_catch,
        )

        data = trace.model_dump() if hasattr(trace, "model_dump") else trace.dict()
        data["streak_curve_data"] = generate_streak_curve_data()
        data["execution_mode_badge"] = "Live Execution (Coinflip Engine)"
        data["is_fallback"] = False
        return data

    except Exception as exc:
        logger.warning(
            "Live execution subprocess failed (%s: %s). Falling back to hero trace.",
            type(exc).__name__,
            exc,
        )
        hero = load_hero_trace()
        hero["is_fallback"] = True
        hero["fallback_note"] = (
            f"Live run subprocess encountered an issue ({type(exc).__name__}: {exc}). "
            "Gracefully fell back to pre-recorded Hero Trace so UI inspection is uninterrupted."
        )
        hero["execution_mode_badge"] = (
            "Replaying real recorded execution (2,000+ certification runs + NVIDIA Nemotron 3 Ultra) [Subprocess Fallback]"
        )
        return hero


# Mount /agent_and_ui/frontend at / if frontend/index.html exists
if FRONTEND_INDEX.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
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
                "/docs",
            ],
        }
