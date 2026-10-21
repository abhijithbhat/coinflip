#!/usr/bin/env python3
"""Generates and validates the reference trace fixture for Coinflip.

Loads or generates shared_contracts/sample_hero_trace.json (which is byte-for-byte
identical to shared_contracts/recorded_traces/hero.json) and validates it against
the CoinflipCertificateTrace Pydantic model with full cryptographic attestation.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

# Ensure workspace root is in sys.path
workspace_root = Path(__file__).resolve().parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from sandbox_engine.attestation import CertificateAttestor
from shared_contracts.schemas import CoinflipCertificateTrace

SAMPLE_HERO_PATH = Path(__file__).resolve().parent / "sample_hero_trace.json"
RECORDED_HERO_PATH = Path(__file__).resolve().parent / "recorded_traces" / "hero.json"


def create_reference_trace() -> CoinflipCertificateTrace:
    """Returns the attested Hero reference trace without any hardcoded counts."""
    # Prefer sample_hero_trace.json if available
    target_path = SAMPLE_HERO_PATH if SAMPLE_HERO_PATH.exists() else RECORDED_HERO_PATH

    if not target_path.exists():
        from sandbox_engine.generate_corpus_traces import generate_suite_trace

        trace = asyncio.run(generate_suite_trace("hero"))
        json_str = trace.model_dump_json(indent=2)
        RECORDED_HERO_PATH.parent.mkdir(parents=True, exist_ok=True)
        RECORDED_HERO_PATH.write_text(json_str, encoding="utf-8")
        shutil.copyfile(str(RECORDED_HERO_PATH), str(SAMPLE_HERO_PATH))
        return trace

    return CoinflipCertificateTrace.model_validate_json(target_path.read_text(encoding="utf-8"))


def main() -> None:
    # Ensure recorded_traces/hero.json and sample_hero_trace.json are synced
    if RECORDED_HERO_PATH.exists() and not SAMPLE_HERO_PATH.exists():
        shutil.copyfile(str(RECORDED_HERO_PATH), str(SAMPLE_HERO_PATH))
    elif SAMPLE_HERO_PATH.exists() and not RECORDED_HERO_PATH.exists():
        RECORDED_HERO_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(SAMPLE_HERO_PATH), str(RECORDED_HERO_PATH))

    trace = create_reference_trace()

    # Re-verify cryptographic attestation
    attestor = CertificateAttestor()
    is_valid = attestor.verify_trace_attestation(trace)
    assert is_valid is True, "Attestation verification failed for reference trace"

    # Verify byte-for-byte identity between hero.json and sample_hero_trace.json
    if RECORDED_HERO_PATH.exists() and SAMPLE_HERO_PATH.exists():
        assert RECORDED_HERO_PATH.read_bytes() == SAMPLE_HERO_PATH.read_bytes(), (
            "sample_hero_trace.json must be byte-for-byte identical to recorded_traces/hero.json"
        )

    print(f"Successfully validated {SAMPLE_HERO_PATH} ({len(SAMPLE_HERO_PATH.read_bytes())} bytes)")
    print(f"  Verdict:      {trace.final_verdict}")
    print(f"  Attestation:  {trace.attestation.algorithm if trace.attestation else 'None'} (verified={is_valid})")
    print(f"  Attempts:     {len(trace.fix_attempts)}")
    print("Zero errors: CoinflipCertificateTrace.model_validate_json passed successfully!")


if __name__ == "__main__":
    main()
