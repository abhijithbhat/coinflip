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
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from agent_and_ui.app import HERO_BADGE, app
from shared_contracts.schemas import (
    BatchExperimentResult,
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

    def test_health_returns_nebius_and_traces_loaded(self):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "nebius_configured" in data
        assert isinstance(data["nebius_configured"], bool)
        assert data["traces_loaded"] == 5

    def test_health_head_method_and_cache_control(self):
        response = client.head("/api/health")
        assert response.status_code == 200
        assert response.headers.get("cache-control") == "no-store"


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
    def test_run_live_error_raises_503(self):
        """When local Windows worker / subprocess fails, must raise 503 instead of silent fallback."""
        with patch("sandbox_engine.orchestrator.CoinflipOrchestrator.run", side_effect=RuntimeError("ProcessPool worker failed")):
            response = client.post("/api/run-live")
            assert response.status_code == 503
            assert "Live execution unavailable" in response.json()["detail"]

    def test_run_live_with_custom_payload_error_raises_503(self):
        payload = {
            "runs_per_condition": 20,
            "project_name": "test-service",
            "test_target": "tests/test_fake.py",
        }
        with patch("sandbox_engine.orchestrator.CoinflipOrchestrator.run", side_effect=FileNotFoundError("test_fake.py not found")):
            response = client.post("/api/run-live", json=payload)
            assert response.status_code == 503
            assert "Live execution unavailable" in response.json()["detail"]

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

    @pytest.mark.parametrize("case_id", ["hero", "order_pollution", "seed_sampling", "clock_expiry", "async_queue_race"])
    def test_run_live_all_5_cases(self, case_id: str):
        """Tests that all 5 benchmark cases are dispatched properly via POST /api/run-live."""
        mock_baseline = BatchExperimentResult(
            perturbation=PerturbationType.BASELINE,
            label="Baseline (normal OS conditions)",
            total_runs=30,
            failures=2,
            passes=28,
            failure_rate=0.067,
            ci_95_lower=0.018,
            ci_95_upper=0.213,
            execution_backend="local_isolated",
            sample_failure_logs=[],
            run_dots=[True] * 28 + [False] * 2,
        )

        mock_trace = CoinflipCertificateTrace(
            trace_id=f"test_live_{case_id}",
            timestamp_utc="2026-10-18T12:00:00Z",
            is_recorded_replay=False,
            project_name=f"project-{case_id}",
            test_identifier=f"test_{case_id}.py",
            stage1_baseline=mock_baseline,
            stage2_ledger=[mock_baseline],
            triggering_stress_condition=PerturbationType.CPU_HEAVY_LOAD,
            fix_attempts=[],
            final_verdict="NOT_YET_CERTIFIED",
            models_used={"bulk_log_reading": "fast", "deep_reasoning": "ultra"},
        )

        with patch("sandbox_engine.orchestrator.CoinflipOrchestrator.run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_trace
            response = client.post("/api/run-live", json={"case_id": case_id, "runs_per_condition": 30})
            assert response.status_code == 200
            data = response.json()
            assert data["trace_id"] == f"test_live_{case_id}"
            assert data["is_fallback"] is False
            assert "streak_curve_data" in data
            assert mock_run.called


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


# -------------------------------------------------------------------------------
# 7. Phase 5: Enrichment pass-through
# -------------------------------------------------------------------------------


class TestTraceEnrichment:
    def test_trace_has_causal_analytics(self):
        response = client.get("/api/trace")
        assert response.status_code == 200
        data = response.json()
        for row in data.get("stage2_ledger", []):
            assert "causal_analytics" in row

    def test_trace_has_attestation(self):
        response = client.get("/api/trace")
        assert response.status_code == 200
        data = response.json()
        assert "attestation" in data
        att = data["attestation"]
        assert att["algorithm"] == "SHA-256-Merkle"
        assert att["verified"] is True

    def test_trace_has_nemotron_reasoning_trace(self):
        response = client.get("/api/trace")
        assert response.status_code == 200
        data = response.json()
        assert "nemotron_reasoning_trace" in data

    def test_trace_has_race_timeline(self):
        response = client.get("/api/trace")
        assert response.status_code == 200
        data = response.json()
        assert "race_timeline" in data

    def test_trace_has_amplifier_report(self):
        response = client.get("/api/trace")
        assert response.status_code == 200
        data = response.json()
        assert "amplifier_report" in data
        rep = data["amplifier_report"]
        assert rep["amplification_factor"] >= 10.0
        assert rep["confirmed_failure_rate"] >= 0.85
        assert rep["winning_condition"] == "cpu_heavy_load"
        assert rep["winning_intensity"] == "L3_EXTREME"
        assert "fresh Confirmation Batch" in rep["winners_curse_callout"]


# -------------------------------------------------------------------------------
# 8. Phase 5: Archetype Catalog in /api/traces
# -------------------------------------------------------------------------------


class TestArchetypeCatalog:
    def test_list_traces_includes_archetype_catalog(self):
        response = client.get("/api/traces")
        assert response.status_code == 200
        data = response.json()
        assert "archetype_catalog" in data
        catalog = data["archetype_catalog"]
        names = [a["name"] for a in catalog]
        assert "hero" in names
        assert "order_pollution" in names
        assert "seed_sampling" in names
        assert "clock_expiry" in names
        assert "async_queue_race" in names

    def test_get_archetype_by_name_hero(self):
        response = client.get("/api/traces/hero")
        assert response.status_code == 200
        data = response.json()
        assert "trace_id" in data

    def test_get_archetype_by_name_order_pollution(self):
        response = client.get("/api/traces/order_pollution")
        assert response.status_code == 200
        data = response.json()
        # Should have enrichment keys
        assert "streak_curve_data" in data

    def test_get_archetype_by_name_seed_sampling(self):
        response = client.get("/api/traces/seed_sampling")
        assert response.status_code == 200
        data = response.json()
        assert "streak_curve_data" in data

    def test_get_archetype_by_name_clock_expiry(self):
        response = client.get("/api/traces/clock_expiry")
        assert response.status_code == 200
        data = response.json()
        assert "streak_curve_data" in data

    def test_get_archetype_by_name_async_queue_race(self):
        response = client.get("/api/traces/async_queue_race")
        assert response.status_code == 200
        data = response.json()
        assert "trace_id" in data
        assert "streak_curve_data" in data


# -------------------------------------------------------------------------------
# 9. Phase 5: GET /api/stream-live (SSE)
# -------------------------------------------------------------------------------


class TestStreamLiveEndpoint:
    def test_stream_live_returns_event_stream(self):
        response = client.get("/api/stream-live")
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

    def test_stream_live_contains_all_stage_events(self):
        response = client.get("/api/stream-live")
        assert response.status_code == 200
        body = response.text
        assert "stage1_measure" in body
        assert "stage2_perturbation" in body
        assert "stage3_nemotron_reasoning" in body
        assert "stage4_sprt_early_reject" in body
        assert "stage3_nemotron_retry" in body
        assert "stage4_1000_certified" in body
        assert "stage5_attestation_signed" in body
        assert "done" in body

    def test_stream_live_events_are_valid_json(self):
        import re
        response = client.get("/api/stream-live")
        body = response.text
        data_lines = re.findall(r"^data: (.+)$", body, re.MULTILINE)
        for line in data_lines:
            parsed = json.loads(line)
            assert isinstance(parsed, dict)

    def test_stream_live_with_custom_case_id(self):
        response = client.get("/api/stream-live?case_id=async_queue_race")
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        body = response.text
        assert "stage1_measure" in body
        assert "done" in body


# -------------------------------------------------------------------------------
# 10. Phase 5: POST /api/verify-attestation
# -------------------------------------------------------------------------------


class TestVerifyAttestationEndpoint:
    def test_verify_attestation_default_hero(self):
        response = client.post("/api/verify-attestation")
        assert response.status_code == 200
        data = response.json()
        assert data["verified"] is True
        assert data["algorithm"] == "SHA-256-Merkle"
        assert len(data["ledger_merkle_root"]) == 64
        assert len(data["patch_sha256"]) == 64
        assert len(data["trace_payload_sha256"]) == 64

    def test_verify_attestation_with_custom_trace(self):
        # Minimal trace payload
        trace = {
            "trace_id": "test_verify_123",
            "execution_mode": "live_custom",
            "stage1_baseline": {
                "perturbation": "baseline",
                "total_runs": 100,
                "failures": 5,
                "passes": 95,
            },
            "stage2_ledger": [],
            "fix_attempts": [],
            "final_verdict": "NOT_YET_CERTIFIED",
        }
        response = client.post("/api/verify-attestation", json={"trace": trace})
        assert response.status_code == 200
        data = response.json()
        assert data["verified"] is True
        assert data["algorithm"] == "SHA-256-Merkle"

    def test_verify_attestation_get_hero_trace_verified(self):
        """Trace returned by /api/traces/hero verifies cleanly with verified: True."""
        response = client.get("/api/traces/hero")
        assert response.status_code == 200
        hero_data = response.json()
        resp = client.post("/api/verify-attestation", json={"trace": hero_data})
        assert resp.status_code == 200
        result = resp.json()
        assert result["verified"] is True
        assert result["algorithm"] == "SHA-256-Merkle"
        assert result["ledger_merkle_root"]

    def test_verify_attestation_post_run_live_verified(self):
        """Live trace returned by POST /api/run-live verifies cleanly with verified: True."""
        live_resp = client.post("/api/run-live", json={"case": "hero", "runs_per_condition": 10})
        assert live_resp.status_code == 200
        live_data = live_resp.json()
        resp = client.post("/api/verify-attestation", json={"trace": live_data})
        assert resp.status_code == 200
        result = resp.json()
        assert result["verified"] is True
        assert result["algorithm"] == "SHA-256-Merkle"
        assert result["ledger_merkle_root"]

    def test_verify_attestation_tampered_failures_999(self):
        """Submitting a trace with tampered failures: 999 returns verified: False with HTTP 200."""
        response = client.get("/api/traces/hero")
        assert response.status_code == 200
        hero_data = response.json()

        # Tamper with failures: 999
        hero_data["stage1_baseline"]["failures"] = 999

        resp = client.post("/api/verify-attestation", json={"trace": hero_data})
        assert resp.status_code == 200
        result = resp.json()
        assert result["verified"] is False
        assert "Tampering detected" in result["reason"]

    def test_verify_attestation_tampered_custom_trace_failures_999(self):
        """Submitting a custom trace with tampered failures: 999 returns verified: False with HTTP 200."""
        trace = {
            "trace_id": "test_verify_tampered",
            "execution_mode": "live_custom",
            "stage1_baseline": {
                "perturbation": "baseline",
                "total_runs": 100,
                "failures": 999,
                "passes": 95,
            },
            "stage2_ledger": [],
            "fix_attempts": [],
            "final_verdict": "NOT_YET_CERTIFIED",
        }
        resp = client.post("/api/verify-attestation", json={"trace": trace})
        assert resp.status_code == 200
        result = resp.json()
        assert result["verified"] is False
        assert "Tampering detected" in result["reason"]


class TestStreamLivePipelineProgress:
    def test_stream_live_pipeline_progress(self):
        async def fake_pipeline(*args, **kwargs):
            on_event = kwargs.get("on_stage_event")
            if on_event:
                on_event("stage1_measure", {"stage": 1, "status": "running"})
                on_event("stage4_1000_certified", {"stage": 4, "status": "certified"})

        with patch("sandbox_engine.orchestrator.CoinflipOrchestrator.run_full_pipeline", side_effect=fake_pipeline):
            resp = client.get("/api/stream-live")
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            text = resp.text
            assert "stage1_measure" in text
            assert "stage4_1000_certified" in text


class TestBuiltinProfilesDynamic:
    def test_builtin_profiles_have_dynamic_metrics(self):
        from agent_and_ui.app import BUILTIN_PROFILES
        for case in ("hero", "order_pollution", "seed_sampling", "clock_expiry", "async_queue_race"):
            assert case in BUILTIN_PROFILES
            prof = BUILTIN_PROFILES[case]
            assert "baseline_failures" in prof
            assert "baseline_runs" in prof
            assert "stress_failures" in prof
            assert prof["baseline_runs"] > 0


class TestRateLimiter:
    def test_rate_limiter_blocks_after_max_runs(self):
        import time
        from agent_and_ui.app import RATE_LIMIT_MAX_RUNS, _LIVE_RUN_HISTORY

        test_ip = "203.0.113.55"
        now = time.time()
        _LIVE_RUN_HISTORY[test_ip] = [now - (i + 1) for i in range(RATE_LIMIT_MAX_RUNS)]

        headers = {"x-forwarded-for": test_ip}
        res = client.post("/api/run-live", json={"case_id": "hero"}, headers=headers)
        assert res.status_code == 429
        assert "Rate limit exceeded" in res.json()["detail"]

        stream_res = client.get("/api/stream-live?case_id=hero", headers=headers)
        assert stream_res.status_code == 429
        assert "Rate limit exceeded" in stream_res.json()["detail"]



