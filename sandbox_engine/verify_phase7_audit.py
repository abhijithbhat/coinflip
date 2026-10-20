"""Phase 7 Audit Verification Script (sandbox_engine/verify_phase7_audit.py).

Validates all 7 Principal Engineer Audit Remediation criteria:
1. Byte-for-byte identity between shared_contracts/sample_hero_trace.json and shared_contracts/recorded_traces/hero.json.
2. All 5 recorded traces exist, have realistic non-zero Stage 1 baseline failure rates (0 < failure_rate < 0.25), and pass SHA-256 Merkle cryptographic attestation verification.
3. sandbox_engine/ci_gatekeeper.py runs and produces a valid GitHub PR Markdown verification certificate comment.
4. Zero .lovable or .wrangler generator files exist in the repository or git index.
"""

from __future__ import annotations

import filecmp
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from sandbox_engine.attestation import CertificateAttestor
from shared_contracts.schemas import CoinflipCertificateTrace


def test_hero_trace_byte_identity() -> None:
    """Verifies sample_hero_trace.json and recorded_traces/hero.json are 100% byte-for-byte identical."""
    print("\n[AUDIT CHECK 1] Verifying byte-for-byte identity of hero traces...")
    hero_sample = WORKSPACE_ROOT / "shared_contracts" / "sample_hero_trace.json"
    hero_recorded = WORKSPACE_ROOT / "shared_contracts" / "recorded_traces" / "hero.json"

    assert hero_sample.exists(), f"Missing file: {hero_sample}"
    assert hero_recorded.exists(), f"Missing file: {hero_recorded}"

    sample_bytes = hero_sample.read_bytes()
    recorded_bytes = hero_recorded.read_bytes()

    assert sample_bytes == recorded_bytes, (
        f"Byte mismatch between {hero_sample} ({len(sample_bytes)} bytes) and "
        f"{hero_recorded} ({len(recorded_bytes)} bytes)"
    )
    assert filecmp.cmp(hero_sample, hero_recorded, shallow=False), "filecmp.cmp failed for hero traces"

    # Verify both pass cryptographic attestation
    attestor = CertificateAttestor()
    trace1 = CoinflipCertificateTrace.model_validate_json(sample_bytes.decode("utf-8"))
    trace2 = CoinflipCertificateTrace.model_validate_json(recorded_bytes.decode("utf-8"))

    assert attestor.verify_trace_attestation(trace1) is True, "Attestation verification failed for sample_hero_trace.json"
    assert attestor.verify_trace_attestation(trace2) is True, "Attestation verification failed for recorded_traces/hero.json"

    print("  [PASS] sample_hero_trace.json and recorded_traces/hero.json are 100% byte-for-byte identical & verified.")


def test_all_5_recorded_traces_and_attestation() -> None:
    """Verifies all 5 recorded traces have non-zero Stage 1 baseline rates and valid cryptographic attestation."""
    print("\n[AUDIT CHECK 2] Verifying all 5 recorded corpus traces and Merkle attestations...")
    recorded_dir = WORKSPACE_ROOT / "shared_contracts" / "recorded_traces"
    expected_traces = [
        "hero.json",
        "order_pollution.json",
        "seed_sampling.json",
        "clock_expiry.json",
        "async_queue_race.json",
    ]

    attestor = CertificateAttestor()

    for trace_filename in expected_traces:
        trace_path = recorded_dir / trace_filename
        assert trace_path.exists(), f"Missing recorded trace: {trace_path}"

        raw_json = trace_path.read_text(encoding="utf-8")
        trace = CoinflipCertificateTrace.model_validate_json(raw_json)

        # Baseline failure rate check
        s1 = trace.stage1_baseline
        rate = s1.failure_rate
        assert 0 < rate < 0.25, (
            f"Trace {trace_filename} Stage 1 baseline failure rate {rate:.4f} is outside required bounds (0 < rate < 0.25)"
        )

        # Cryptographic attestation check
        is_attested = attestor.verify_trace_attestation(trace)
        assert is_attested is True, f"Trace {trace_filename} failed CertificateAttestor cryptographic verification!"

        print(
            f"  [PASS] {trace_filename:<22} runs={s1.total_runs:>3}, fails={s1.failures:>2}, "
            f"baseline_rate={rate * 100:.1f}%, Merkle={trace.attestation.experiment_ledger_merkle_root[:12]}... (VALID)"
        )


def test_ci_gatekeeper_markdown_report() -> None:
    """Verifies that sandbox_engine/ci_gatekeeper.py runs and produces a valid PR Markdown certificate report."""
    print("\n[AUDIT CHECK 3] Verifying sandbox_engine/ci_gatekeeper.py outputs valid Markdown certificate report...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_md = Path(tmp_dir) / "pr_comment.md"
        cmd = [
            sys.executable,
            "-m",
            "sandbox_engine.ci_gatekeeper",
            "--case",
            "hero",
            "--runs",
            "10",
            "--output",
            str(out_md),
        ]
        res = subprocess.run(cmd, cwd=WORKSPACE_ROOT, capture_output=True, text=True)
        assert res.returncode == 0, f"ci_gatekeeper failed with code {res.returncode}:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"

        assert out_md.exists(), "ci_gatekeeper did not generate output markdown file!"
        content = out_md.read_text(encoding="utf-8")

        # Required report sections
        assert "## 🪙 Coinflip Flaky-Test Gatekeeper Certification" in content, "Missing gatekeeper header"
        assert "Empirical Flakiness Discovery & Stress Ledger" in content, "Missing stress ledger section"
        assert "Dual-Certification Gatekeeper Evaluation" in content, "Missing dual-cert evaluation section"
        assert "Cryptographic Attestation (SHA-256 Merkle Proof)" in content, "Missing cryptographic attestation section"
        assert "SHA-256-Merkle" in content, "Missing algorithm declaration"
        assert "tamper_evident:       true" in content, "Missing tamper-evident proof"

        print("  [PASS] ci_gatekeeper.py successfully generated certified PR markdown comment.")


def test_zero_generator_artifacts() -> None:
    """Verifies that no .lovable, .wrangler, or third-party generator files exist in repository tracking or source code."""
    print("\n[AUDIT CHECK 4] Verifying zero .lovable or .wrangler generator files exist in repository...")

    # Check git tracking
    git_check = subprocess.run(["git", "ls-files"], cwd=WORKSPACE_ROOT, capture_output=True, text=True)
    assert git_check.returncode == 0, "Failed to run git ls-files"
    tracked_files = git_check.stdout.splitlines()

    for f in tracked_files:
        assert not f.startswith("agent_and_ui/frontend/.lovable"), f"Found tracked .lovable file: {f}"
        assert not f.startswith("agent_and_ui/frontend/.wrangler"), f"Found tracked .wrangler file: {f}"
        assert "lovable-error-reporting" not in f, f"Found tracked lovable error reporting file: {f}"

    # Check filesystem source trees
    frontend_src = WORKSPACE_ROOT / "agent_and_ui" / "frontend"
    assert not (frontend_src / ".lovable").exists(), "Directory agent_and_ui/frontend/.lovable still exists on disk!"
    assert not (frontend_src / ".wrangler").exists(), "Directory agent_and_ui/frontend/.wrangler still exists on disk!"
    assert not (frontend_src / "AGENTS.md").exists(), "File agent_and_ui/frontend/AGENTS.md still exists on disk!"
    assert not (frontend_src / "src" / "lib" / "lovable-error-reporting.ts").exists(), (
        "File lovable-error-reporting.ts still exists on disk!"
    )

    print("  [PASS] Zero .lovable, .wrangler, or generator files exist in repository.")


def test_live_execution_latency_and_statistical_integrity() -> None:
    """Verifies that live mini-batch execution runs in < 6.5s and maintains statistical integrity."""
    print("\n[AUDIT CHECK 5] Verifying live mini-batch runtime (< 6.5s) and statistical integrity...")
    import time
    from starlette.testclient import TestClient
    from agent_and_ui.app import app

    client = TestClient(app)
    t0 = time.perf_counter()
    resp = client.post("/api/run-live", json={"case_id": "hero", "runs_per_condition": 30})
    elapsed = time.perf_counter() - t0

    assert resp.status_code == 200, f"run-live failed with {resp.status_code}: {resp.text}"
    data = resp.json()

    print(f"  Live run-live duration: {elapsed:.2f}s (target < 6.5s)")
    assert elapsed < 6.5, f"Live mini-batch took {elapsed:.2f}s, exceeding 6.5s ceiling!"
    assert data.get("is_fallback") is False, "Live execution fell back to recorded trace!"
    assert data.get("execution_mode_badge") == "Live Execution (Coinflip Engine)"

    # Stage 1 baseline validation
    s1_fails = data["stage1_baseline"]["failures"]
    s1_total = data["stage1_baseline"]["total_runs"]
    s1_rate = s1_fails / max(1, s1_total)
    print(f"  Stage 1 baseline: {s1_fails}/{s1_total} ({s1_rate:.1%})")
    assert 0.03 <= s1_rate <= 0.20, f"Stage 1 baseline rate {s1_rate:.3f} outside expected 3%-20% window"

    # Stage 2 stress spike validation
    stress_item = next(
        (it for it in data["stage2_ledger"] if it["perturbation"] in ("cpu_half_cores", "cpu_heavy_load")),
        None,
    )
    assert stress_item is not None, "Missing CPU stress condition in Stage 2 ledger"
    stress_rate = stress_item["failure_rate"]
    print(f"  Stage 2 stress: {stress_item['failures']}/{stress_item['total_runs']} ({stress_rate:.1%})")
    assert stress_rate >= 0.80, f"Stage 2 stress rate {stress_rate:.3f} below 80% threshold"

    # Stage 4 fix evaluations
    attempts = data["fix_attempts"]
    assert len(attempts) >= 2, f"Expected at least 2 fix attempts, got {len(attempts)}"
    assert attempts[0]["verdict"] in ("REJECTED", "BROKEN"), f"Attempt 1 should be REJECTED, got {attempts[0]['verdict']}"
    assert attempts[1]["verdict"] == "CERTIFIED", f"Attempt 2 should be CERTIFIED, got {attempts[1]['verdict']}"

    print(f"  [PASS] Live mini-batch completed in {elapsed:.2f}s with perfect statistical integrity.")


def main() -> None:
    print("=" * 80)
    print("COINFLIP PHASE 7 AUDIT REMEDIATION VERIFICATION SUITE")
    print("=" * 80)

    test_hero_trace_byte_identity()
    test_all_5_recorded_traces_and_attestation()
    test_ci_gatekeeper_markdown_report()
    test_zero_generator_artifacts()
    test_live_execution_latency_and_statistical_integrity()

    print("\n" + "=" * 80)
    print("✅ ALL PHASE 7 AUDIT REMEDIATION VERIFICATIONS PASSED (100%)")
    print("=" * 80)


if __name__ == "__main__":
    main()
