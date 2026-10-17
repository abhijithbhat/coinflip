"""Comprehensive Test Suite for FastAPI Backend (/agent_and_ui/test_app.py).

Tests:
1. GET /api/health endpoint.
2. GET /api/trace and GET /api/traces/hero (data enrichment with streak curve & badge).
3. GET /api/traces (listing available JSON trace files).
4. GET /api/traces/{name} (fetching by trace name, 404 handling).
5. GET /api/streak-curve (mathematical curve decay points and Rule of Three metadata).
6. POST /api/run-live (graceful fallback on Windows subprocess failures + mocked success).
7. Root endpoint and static mounting behavior.
8. CORS middleware headers.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from agent_and_ui.app import HERO_BADGE, app
from shared_contracts.schemas import (
    BatchExperimentResult,
    CandidateFixEvaluation,
    CoinflipCertificateTrace,
    PerturbationType,
)

client = TestClient(app)


# -------------------------------------------------------------------------------
# 1. /api/health
# -------------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_health_returns_ok_and_service_name(self):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "coinflip-agent-ui"


# -------------------------------------------------------------------------------
# 2. /api/trace and /api/traces/hero
# -------------------------------------------------------------------------------


class TestTraceEndpoints:
    def test_get_trace_loads_and_enriches_hero_data(self):
        response = client.get("/api/trace")
        assert response.status_code == 200
        data = response.json()

        # Contract fields
        assert "trace_id" in data
        assert "stage1_baseline" in data
        assert "stage2_ledger" in data
        assert "fix_attempts" in data
        assert "final_verdict" in data
        assert "models_used" in data

        # Enriched fields
        assert "streak_curve_data" in data
        assert isinstance(data["streak_curve_data"], list)
        assert len(data["streak_curve_data"]) == 21

        assert "execution_mode_badge" in data
        assert data["execution_mode_badge"] == HERO_BADGE

    def test_get_traces_hero_alias_matches_trace(self):
        res_trace = client.get("/api/trace")
        res_hero = client.get("/api/traces/hero")
        assert res_hero.status_code == 200
        assert res_hero.json()["trace_id"] == res_trace.json()["trace_id"]
        assert res_hero.json()["execution_mode_badge"] == HERO_BADGE


# -------------------------------------------------------------------------------
# 3. /api/traces & /api/traces/{name}
# -------------------------------------------------------------------------------


class TestTracesListEndpoints:
    def test_list_traces_contains_sample_hero_trace(self):
        response = client.get("/api/traces")
        assert response.status_code == 200
        data = response.json()
        assert "traces" in data
        assert "sample_hero_trace.json" in data["traces"]
        # Also provides files key for frontend flexibility
        assert "sample_hero_trace.json" in data["files"]

    def test_get_named_trace_exact_hero_filename(self):
        response = client.get("/api/traces/sample_hero_trace.json")
        assert response.status_code == 200
        data = response.json()
        assert "trace_id" in data
        assert data["execution_mode_badge"] == HERO_BADGE

    def test_get_named_trace_non_existent_returns_404(self):
        response = client.get("/api/traces/definitely_not_a_trace_file.json")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# -------------------------------------------------------------------------------
# 4. /api/streak-curve
# -------------------------------------------------------------------------------


class TestStreakCurveEndpoint:
    def test_streak_curve_returns_21_points(self):
        response = client.get("/api/streak-curve")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 21

        # Check required mathematical fields on each point
        for point in data:
            assert "true_failure_rate" in point
            assert "true_failure_rate_pct" in point
            assert "pass_1_run" in point
            assert "pass_10_runs" in point
            assert "pass_100_runs" in point

    def test_streak_curve_first_point_contains_rule_of_three_bars(self):
        response = client.get("/api/streak-curve")
        assert response.status_code == 200
        data = response.json()
        first_point = data[0]
        assert "rule_of_three_bars" in first_point
        bars = first_point["rule_of_three_bars"]
        assert len(bars) == 4
        runs_tested = [b["runs"] for b in bars]
        assert runs_tested == [100, 300, 1000, 3000]


# -------------------------------------------------------------------------------
# 5. POST /api/run-live (Fallback & Mocked Success)
# -------------------------------------------------------------------------------


class TestRunLiveEndpoint:
    def test_run_live_fallback_on_subprocess_error(self):
        """When local Windows worker / subprocess fails, must gracefully return hero trace."""
        with patch("sandbox_engine.orchestrator.CoinflipOrchestrator.run", side_effect=RuntimeError("ProcessPool worker failed")):
            response = client.post("/api/run-live")
            assert response.status_code == 200
            data = response.json()

            # Graceful fallback indicators
            assert data.get("is_fallback") is True
            assert "fallback_note" in data
            assert "Live run subprocess encountered an issue" in data["fallback_note"]

            # Valid trace structure is preserved so the UI never crashes
            assert "trace_id" in data
            assert "stage1_baseline" in data
            assert "stage2_ledger" in data
            assert "streak_curve_data" in data
            assert "Subprocess Fallback" in data["execution_mode_badge"]

    def test_run_live_with_custom_payload_still_graceful(self):
        payload = {
            "runs_per_condition": 20,
            "project_name": "test-service",
            "test_target": "tests/test_fake.py",
        }
        with patch("sandbox_engine.orchestrator.CoinflipOrchestrator.run", side_effect=FileNotFoundError("test_fake.py not found")):
            response = client.post("/api/run-live", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data.get("is_fallback") is True
            assert "trace_id" in data
            assert "FileNotFoundError" in data["fallback_note"]

    def test_run_live_success_mock(self):
        """When CoinflipOrchestrator succeeds, returns live trace with is_fallback=False."""
        mock_baseline = BatchExperimentResult(
            perturbation=PerturbationType.BASELINE,
            label="Baseline (normal OS conditions)",
            total_runs=30,
            failures=3,
            passes=27,
            failure_rate=0.10,
            ci_95_lower=0.035,
            ci_95_upper=0.256,
            execution_backend="local_isolated",
            sample_failure_logs=["TimeoutError: test timed out"],
            run_dots=[True] * 27 + [False] * 3,
        )

        mock_trace = CoinflipCertificateTrace(
            trace_id="test_mock_trace_123",
            timestamp_utc="2026-10-17T12:00:00Z",
            is_recorded_replay=False,
            project_name="mock-project",
            test_identifier="mock-project::test_target.py",
            stage1_baseline=mock_baseline,
            stage2_ledger=[mock_baseline],
            triggering_stress_condition=PerturbationType.CPU_HEAVY_LOAD,
            fix_attempts=[],
            final_verdict="NOT_YET_CERTIFIED",
            models_used={"bulk_log_reading": "fast", "deep_reasoning": "ultra"},
        )

        with patch("sandbox_engine.orchestrator.CoinflipOrchestrator.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_trace
            response = client.post("/api/run-live", json={"runs_per_condition": 30})

            assert response.status_code == 200
            data = response.json()
            assert data["trace_id"] == "test_mock_trace_123"
            assert data["is_fallback"] is False
            assert data["execution_mode_badge"] == "Live Execution (Coinflip Engine)"
            assert "streak_curve_data" in data


# -------------------------------------------------------------------------------
# 6. Root & Static Mounting
# -------------------------------------------------------------------------------


class TestRootAndCORS:
    def test_root_endpoint_serves_frontend_or_service_notice(self):
        response = client.get("/")
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            # Production static frontend is mounted and served
            assert "<html" in response.text.lower()
            assert "coinflip" in response.text.lower()
        else:
            # Fallback service notice
            data = response.json()
            assert data["status"] == "ok"
            assert data["service"] == "coinflip-agent-ui"
            assert "/api/health" in data["endpoints"]

    def test_frontend_static_assets_accessible(self):
        # Verify static asset or index is reachable
        response = client.get("/")
        assert response.status_code == 200
        assert "<!doctype html>" in response.text.lower() or "<html" in response.text.lower()

    def test_cors_headers_present(self):
        response = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        assert response.status_code == 200
        origin = response.headers.get("access-control-allow-origin")
        assert origin in ("*", "http://localhost:5173")
