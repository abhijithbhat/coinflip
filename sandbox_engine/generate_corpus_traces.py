#!/usr/bin/env python3
"""Generates the 5-Archetype Real Recorded Trace Corpus for Coinflip.

Executes REAL end-to-end runs of all 5 de-rigged benchmark suites through
CoinflipOrchestrator, signs each trace with CertificateAttestor (SHA-256 Merkle root
and HMAC-SHA256 signature), and writes them to:
  shared_contracts/recorded_traces/{hero,order_pollution,seed_sampling,clock_expiry,async_queue_race}.json
and ensures shared_contracts/sample_hero_trace.json is byte-for-byte identical to hero.json.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import sys
from pathlib import Path
from typing import Any

# Ensure workspace root is in sys.path
workspace_root = Path(__file__).resolve().parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from sandbox_engine.attestation import CertificateAttestor
from sandbox_engine.orchestrator import CoinflipOrchestrator
from shared_contracts.schemas import CoinflipCertificateTrace

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sandbox_engine.generate_corpus_traces")

TRACES_DIR = workspace_root / "shared_contracts" / "recorded_traces"
SAMPLE_HERO_PATH = workspace_root / "shared_contracts" / "sample_hero_trace.json"

SUITE_CONFIGS: dict[str, dict[str, Any]] = {
    "hero": {
        "title": "Hero Worker Race (CPU Thread Race)",
        "repo_dir": workspace_root / "benchmarks" / "hero_worker_race",
        "test_target": "test_worker.py",
        "project_name": "example-service",
        "trace_id": "coinflip-corpus-hero-trace",
    },
    "order_pollution": {
        "title": "Test Order Pollution (Shared Cache)",
        "repo_dir": workspace_root / "benchmarks" / "real_world_cases" / "case_01_test_order_pollution",
        "test_target": "test_config_cache.py",
        "project_name": "config-service",
        "trace_id": "coinflip-corpus-order-pollution-trace",
    },
    "seed_sampling": {
        "title": "Unpinned Seed Sampling (Hash + Random)",
        "repo_dir": workspace_root / "benchmarks" / "real_world_cases" / "case_02_unpinned_seed_sampling",
        "test_target": "test_sampler.py",
        "project_name": "ml-pipeline",
        "trace_id": "coinflip-corpus-seed-sampling-trace",
    },
    "clock_expiry": {
        "title": "Token Expiry Clock (Mixed Clock Sources)",
        "repo_dir": workspace_root / "benchmarks" / "real_world_cases" / "case_03_token_expiry_clock",
        "test_target": "test_token_ttl.py",
        "project_name": "auth-gateway",
        "trace_id": "coinflip-corpus-clock-expiry-trace",
    },
    "async_queue_race": {
        "title": "Async Queue Race (Producer-Consumer)",
        "repo_dir": workspace_root / "benchmarks" / "real_world_cases" / "case_04_async_queue_race",
        "test_target": "test_event_queue.py",
        "project_name": "event-bus",
        "trace_id": "coinflip-corpus-async-queue-race-trace",
    },
}


async def generate_suite_trace(key: str) -> CoinflipCertificateTrace:
    """Executes a real 5-stage run of the given benchmark suite and cryptographically attests it."""
    cfg = SUITE_CONFIGS[key]
    logger.info("Executing REAL run for %s (%s)...", key, cfg["title"])

    orchestrator = CoinflipOrchestrator(
        repo_dir=cfg["repo_dir"],
        test_target=cfg["test_target"],
        project_name=cfg["project_name"],
        mode="local_isolated",
        execution_backend="local_isolated",
    )

    trace = await orchestrator.run(
        stage1_runs=30,
        stage2_runs=25,
        stage4_cert_runs=30,
        demonstrate_rejection_catch=True,
        fast_live_mode=True,
    )

    trace.trace_id = cfg["trace_id"]
    trace.is_recorded_replay = True
    trace.trace_origin = "recorded_execution"

    # Re-attest with exact benchmark repository snapshot and trace_id
    attestor = CertificateAttestor()
    trace = attestor.attest_trace(trace, repo_dir=cfg["repo_dir"])
    assert attestor.verify_trace_attestation(trace) is True, f"Attestation verification failed for {key}"
    return trace


def _load_or_generate(key: str) -> CoinflipCertificateTrace:
    """Helper to load a recorded trace from disk or generate it if missing."""
    target_file = TRACES_DIR / f"{key}.json"
    if target_file.exists():
        try:
            return CoinflipCertificateTrace.model_validate_json(target_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return asyncio.run(generate_suite_trace(key))


def create_hero_trace() -> CoinflipCertificateTrace:
    """Returns the attested Hero trace."""
    return _load_or_generate("hero")


def create_order_pollution_trace() -> CoinflipCertificateTrace:
    """Returns the attested Order Pollution trace."""
    return _load_or_generate("order_pollution")


def create_seed_sampling_trace() -> CoinflipCertificateTrace:
    """Returns the attested Seed Sampling trace."""
    return _load_or_generate("seed_sampling")


def create_clock_expiry_trace() -> CoinflipCertificateTrace:
    """Returns the attested Clock Expiry trace."""
    return _load_or_generate("clock_expiry")


def create_async_queue_race_trace() -> CoinflipCertificateTrace:
    """Returns the attested Async Queue Race trace."""
    return _load_or_generate("async_queue_race")


async def generate_all_corpus_traces() -> dict[str, CoinflipCertificateTrace]:
    """Runs all 5 benchmark suites, writes signed traces to disk, and updates sample_hero_trace.json."""
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    results: dict[str, CoinflipCertificateTrace] = {}

    print("\n" + "=" * 80)
    print("COINFLIP REAL 5-ARCHETYPE TRACE CORPUS GENERATOR")
    print("=" * 80)

    for key in SUITE_CONFIGS:
        trace = await generate_suite_trace(key)
        results[key] = trace

        out_path = TRACES_DIR / f"{key}.json"
        out_path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")

        print(f"  ✅ Generated & Attested: {out_path.relative_to(workspace_root)}")
        if trace.attestation:
            print(f"     -> Merkle Root: {trace.attestation.experiment_ledger_merkle_root}")
            print(f"     -> HMAC Sig:    {trace.attestation.hmac_signature[:24]}...")
            print(f"     -> Cert Digest: {trace.attestation.certificate_digest_sha256[:24]}...")
            print(f"     -> Verified:    {trace.attestation.verified}")

        # Keep sample_hero_trace.json byte-for-byte identical to recorded_traces/hero.json
        if key == "hero":
            shutil.copyfile(str(out_path), str(SAMPLE_HERO_PATH))
            print(f"  ✅ Synchronized root hero trace (byte-for-byte): {SAMPLE_HERO_PATH.relative_to(workspace_root)}")

    print("=" * 80)
    print("All 5 real traces successfully generated, cryptographically signed, and persisted!\n")
    return results


def main() -> None:
    asyncio.run(generate_all_corpus_traces())


if __name__ == "__main__":
    main()
