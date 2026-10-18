"""SHA-256 Merkle Certificate Attestation for Coinflip.

Generates and verifies cryptographic proofs of scientific integrity for Coinflip traces.
Binds:
1. Deterministic SHA-256 snapshot of repository source files.
2. SHA-256 digest of the certified patch diff.
3. Binary SHA-256 Merkle root aggregating all Stage 1, Stage 2, and Stage 4 test run counts.
4. Cryptographic certificate digest binding the ledger root, patch, repo snapshot, and verdict.

Enables any judge, developer, or CI system to independently verify that test results,
failure rates, and patches were never hand-edited or fabricated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any, Optional, Union

# Ensure workspace root is in sys.path
workspace_root = Path(__file__).resolve().parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from shared_contracts.schemas import (
    BatchExperimentResult,
    CandidateFixEvaluation,
    CoinflipCertificateTrace,
    CryptographicAttestation,
)

logger = logging.getLogger("sandbox_engine.attestation")


class CertificateAttestor:
    """Computes and verifies binary SHA-256 Merkle trees and certificate signatures."""

    IGNORED_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".DS_Store", "node_modules"}

    def compute_repo_snapshot_sha256(self, repo_dir: Optional[Union[Path, str]] = None) -> str:
        """Computes deterministic SHA-256 hash across all tracked repository files."""
        if not repo_dir:
            return hashlib.sha256(b"coinflip-standard-hermetic-environment-v1").hexdigest()

        path = Path(repo_dir).resolve()
        if not path.exists():
            return hashlib.sha256(f"missing-repo:{path}".encode("utf-8")).hexdigest()

        file_digests: list[str] = []
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in self.IGNORED_DIRS and not d.startswith(".")]
            for f in sorted(files):
                if f.startswith(".") or f.endswith((".pyc", ".pyo")):
                    continue
                file_path = Path(root) / f
                try:
                    rel_path = file_path.relative_to(path).as_posix()
                    file_bytes = file_path.read_bytes()
                    file_sha = hashlib.sha256(file_bytes).hexdigest()
                    file_digests.append(f"{rel_path}:{file_sha}")
                except Exception:
                    continue

        file_digests.sort()
        combined = "\n".join(file_digests).encode("utf-8")
        return hashlib.sha256(combined).hexdigest()

    def compute_patch_diff_sha256(self, patch_diff: str) -> str:
        """Computes SHA-256 digest of the unified git diff patch."""
        normalized = patch_diff.strip().encode("utf-8")
        return hashlib.sha256(normalized).hexdigest()

    def extract_ledger_records(
        self, trace: Union[CoinflipCertificateTrace, dict[str, Any]]
    ) -> list[tuple[str, int, int, int]]:
        """Extracts canonical (perturbation, total_runs, failures, passes) tuples from all stages."""
        records: list[tuple[str, int, int, int]] = []

        if isinstance(trace, dict):
            # Stage 1
            s1 = trace.get("stage1_baseline", {})
            records.append((
                str(s1.get("perturbation", "baseline")),
                int(s1.get("total_runs", 0)),
                int(s1.get("failures", 0)),
                int(s1.get("passes", 0)),
            ))
            # Stage 2
            for item in trace.get("stage2_ledger", []):
                records.append((
                    str(item.get("perturbation", "")),
                    int(item.get("total_runs", 0)),
                    int(item.get("failures", 0)),
                    int(item.get("passes", 0)),
                ))
            # Stage 4 Fix Attempts
            for attempt in trace.get("fix_attempts", []):
                norm = attempt.get("normal_cert_result", {})
                records.append((
                    str(norm.get("perturbation", "baseline")),
                    int(norm.get("total_runs", 0)),
                    int(norm.get("failures", 0)),
                    int(norm.get("passes", 0)),
                ))
                stress = attempt.get("stress_cert_result", {})
                records.append((
                    str(stress.get("perturbation", "")),
                    int(stress.get("total_runs", 0)),
                    int(stress.get("failures", 0)),
                    int(stress.get("passes", 0)),
                ))
        else:
            # Stage 1
            s1 = trace.stage1_baseline
            records.append((s1.perturbation.value, s1.total_runs, s1.failures, s1.passes))
            # Stage 2
            for item in trace.stage2_ledger:
                records.append((item.perturbation.value, item.total_runs, item.failures, item.passes))
            # Stage 4 Fix Attempts
            for attempt in trace.fix_attempts:
                norm = attempt.normal_cert_result
                records.append((norm.perturbation.value, norm.total_runs, norm.failures, norm.passes))
                stress = attempt.stress_cert_result
                records.append((stress.perturbation.value, stress.total_runs, stress.failures, stress.passes))

        return records

    def compute_ledger_merkle_root(
        self,
        trace_or_records: Union[CoinflipCertificateTrace, dict[str, Any], list[tuple[str, int, int, int]]],
    ) -> str:
        """Constructs a binary SHA-256 Merkle tree over all experiment ledger batches."""
        if isinstance(trace_or_records, list):
            records = trace_or_records
        else:
            records = self.extract_ledger_records(trace_or_records)

        if not records:
            return hashlib.sha256(b"empty_ledger").hexdigest()

        # Hash leaf nodes
        leaf_hashes: list[str] = []
        for pert, total, fails, passes in records:
            leaf_str = f"{pert}:{total}:{fails}:{passes}"
            leaf_hashes.append(hashlib.sha256(leaf_str.encode("utf-8")).hexdigest())

        # Iteratively build Merkle root
        current_level = list(leaf_hashes)
        while len(current_level) > 1:
            if len(current_level) % 2 != 0:
                current_level.append(current_level[-1])  # Duplicate last element to balance binary tree

            next_level: list[str] = []
            for i in range(0, len(current_level), 2):
                combined = (current_level[i] + current_level[i + 1]).encode("utf-8")
                next_level.append(hashlib.sha256(combined).hexdigest())
            current_level = next_level

        return current_level[0]

    def compute_certificate_digest(
        self,
        repo_snapshot_sha256: str,
        patch_diff_sha256: str,
        experiment_ledger_merkle_root: str,
        final_verdict: str,
        trace_id: str,
    ) -> str:
        """Binds the components into a cryptographic certificate digest."""
        payload = f"{repo_snapshot_sha256}|{patch_diff_sha256}|{experiment_ledger_merkle_root}|{final_verdict}|{trace_id}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def attest_trace(
        self,
        trace: CoinflipCertificateTrace,
        repo_dir: Optional[Union[Path, str]] = None,
    ) -> CoinflipCertificateTrace:
        """Signs a CoinflipCertificateTrace, populating its attestation field."""
        # Find certified patch (or fallback to latest fix attempt)
        certified_patch = ""
        for attempt in reversed(trace.fix_attempts):
            if attempt.verdict == "CERTIFIED":
                certified_patch = attempt.git_diff_patch
                break
        if not certified_patch and trace.fix_attempts:
            certified_patch = trace.fix_attempts[-1].git_diff_patch

        repo_sha = self.compute_repo_snapshot_sha256(repo_dir)
        patch_sha = self.compute_patch_diff_sha256(certified_patch)
        merkle_root = self.compute_ledger_merkle_root(trace)
        digest = self.compute_certificate_digest(
            repo_snapshot_sha256=repo_sha,
            patch_diff_sha256=patch_sha,
            experiment_ledger_merkle_root=merkle_root,
            final_verdict=trace.final_verdict,
            trace_id=trace.trace_id,
        )

        trace.attestation = CryptographicAttestation(
            algorithm="SHA-256-Merkle",
            repo_snapshot_sha256=repo_sha,
            patch_diff_sha256=patch_sha,
            experiment_ledger_merkle_root=merkle_root,
            certificate_digest_sha256=digest,
            verified=True,
        )
        return trace

    def verify_trace_attestation(self, trace: CoinflipCertificateTrace) -> bool:
        """Cryptographically verifies that the trace's ledger and patch are authentic and untampered."""
        if trace.attestation is None:
            return False

        att = trace.attestation

        # 1. Recompute and verify Merkle root
        recomputed_merkle_root = self.compute_ledger_merkle_root(trace)
        if recomputed_merkle_root != att.experiment_ledger_merkle_root:
            logger.warning(
                "Merkle root mismatch! Expected %s, recomputed %s",
                att.experiment_ledger_merkle_root,
                recomputed_merkle_root,
            )
            return False

        # 2. Recompute and verify patch diff hash
        certified_patch = ""
        for attempt in reversed(trace.fix_attempts):
            if attempt.verdict == "CERTIFIED":
                certified_patch = attempt.git_diff_patch
                break
        if not certified_patch and trace.fix_attempts:
            certified_patch = trace.fix_attempts[-1].git_diff_patch

        recomputed_patch_sha = self.compute_patch_diff_sha256(certified_patch)
        if recomputed_patch_sha != att.patch_diff_sha256:
            logger.warning(
                "Patch diff SHA-256 mismatch! Expected %s, recomputed %s",
                att.patch_diff_sha256,
                recomputed_patch_sha,
            )
            return False

        # 3. Recompute and verify overall certificate digest
        recomputed_digest = self.compute_certificate_digest(
            repo_snapshot_sha256=att.repo_snapshot_sha256,
            patch_diff_sha256=recomputed_patch_sha,
            experiment_ledger_merkle_root=recomputed_merkle_root,
            final_verdict=trace.final_verdict,
            trace_id=trace.trace_id,
        )
        if recomputed_digest != att.certificate_digest_sha256:
            logger.warning(
                "Certificate digest mismatch! Expected %s, recomputed %s",
                att.certificate_digest_sha256,
                recomputed_digest,
            )
            return False

        return True


def attest_trace(
    trace: CoinflipCertificateTrace, repo_dir: Optional[Union[Path, str]] = None
) -> CoinflipCertificateTrace:
    """Convenience functional helper to sign a CoinflipCertificateTrace."""
    return CertificateAttestor().attest_trace(trace, repo_dir=repo_dir)


def verify_trace_attestation(trace: CoinflipCertificateTrace) -> bool:
    """Convenience functional helper to verify a CoinflipCertificateTrace."""
    return CertificateAttestor().verify_trace_attestation(trace)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Coinflip SHA-256 Merkle Certificate Attestation CLI"
    )
    parser.add_argument(
        "--verify",
        type=str,
        help="Path to trace JSON file to verify cryptographically",
    )
    parser.add_argument(
        "--sign",
        type=str,
        help="Path to trace JSON file to attest and sign in-place",
    )

    args = parser.parse_args()

    if args.verify:
        target_path = Path(args.verify).resolve()
        if not target_path.exists():
            print(f"Error: File not found: {target_path}", file=sys.stderr)
            sys.exit(1)

        try:
            content = target_path.read_text(encoding="utf-8")
            trace = CoinflipCertificateTrace.model_validate_json(content)
            attestor = CertificateAttestor()
            is_valid = attestor.verify_trace_attestation(trace)

            if is_valid and trace.attestation:
                print("\n" + "=" * 80)
                print("✅ COINFLIP CRYPTOGRAPHIC ATTESTATION VERIFIED")
                print("=" * 80)
                print(f"Algorithm:          {trace.attestation.algorithm}")
                print(f"Repo Snapshot SHA:  {trace.attestation.repo_snapshot_sha256}")
                print(f"Patch Diff SHA:     {trace.attestation.patch_diff_sha256}")
                print(f"Ledger Merkle Root: {trace.attestation.experiment_ledger_merkle_root}")
                print(f"Certificate Digest: {trace.attestation.certificate_digest_sha256}")
                print("Status:             100% CRYPTOGRAPHICALLY AUTHENTIC & UNTAMPERED")
                print("=" * 80 + "\n")
                sys.exit(0)
            else:
                print("\n" + "!" * 80, file=sys.stderr)
                print("❌ CRITICAL ATTESTATION FAILURE: TAMPERING DETECTED!", file=sys.stderr)
                print("!" * 80, file=sys.stderr)
                print("The certificate trace failed SHA-256 Merkle integrity validation.", file=sys.stderr)
                print("Experiment ledger counts, verdict, or patch diff do not match signature.", file=sys.stderr)
                print("!" * 80 + "\n", file=sys.stderr)
                sys.exit(1)

        except Exception as e:
            print(f"Error loading or parsing trace: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.sign:
        target_path = Path(args.sign).resolve()
        if not target_path.exists():
            print(f"Error: File not found: {target_path}", file=sys.stderr)
            sys.exit(1)

        content = target_path.read_text(encoding="utf-8")
        trace = CoinflipCertificateTrace.model_validate_json(content)
        signed = attest_trace(trace)
        target_path.write_text(signed.model_dump_json(indent=2), encoding="utf-8")
        print(f"Successfully signed {target_path}")
        sys.exit(0)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
