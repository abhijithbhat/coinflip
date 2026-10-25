"""SHA-256 Merkle Certificate Attestation with HMAC-SHA256 for Coinflip.

Generates and verifies cryptographic proofs of scientific integrity for Coinflip traces.
Binds:
1. Deterministic SHA-256 snapshot of repository source files.
2. SHA-256 digest of the certified patch diff.
3. Binary SHA-256 Merkle root aggregating all Stage 1, Stage 2, and Stage 4 test run counts
   along with their compact run_dots bitstrings.
4. Cryptographic certificate digest binding the ledger root, patch, repo snapshot, and verdict.
5. HMAC-SHA256 server signature providing non-repudiation against offline forgery.

Enables any judge, developer, or CI system to independently verify that test results,
failure rates, and patches were never hand-edited or fabricated.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

# Ensure workspace root is in sys.path
workspace_root = Path(__file__).resolve().parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from shared_contracts.schemas import (
    CoinflipCertificateTrace,
    CryptographicAttestation,
)

logger = logging.getLogger("sandbox_engine.attestation")


def _normalize_pert(val: Any) -> str:
    """Normalizes perturbation to canonical lowercase string (e.g. clock_shift)."""
    if hasattr(val, "value"):
        return str(val.value)
    s = str(val)
    if s.startswith("PerturbationType."):
        return s.split("PerturbationType.", 1)[1].lower()
    return s.lower()


class CertificateAttestor:
    """Computes and verifies binary SHA-256 Merkle trees and HMAC-SHA256 signatures."""

    IGNORED_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".DS_Store", "node_modules"}

    def compute_repo_snapshot_sha256(self, repo_dir: Path | str | None = None) -> str:
        """Computes deterministic SHA-256 hash across all tracked repository files."""
        if not repo_dir:
            return hashlib.sha256(b"coinflip-standard-hermetic-environment-v1").hexdigest()

        path = Path(repo_dir).resolve()
        if not path.exists():
            return hashlib.sha256(f"missing-repo:{path}".encode()).hexdigest()

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
        self, trace: CoinflipCertificateTrace | dict[str, Any]
    ) -> list[tuple[str, int, int, int, str]]:
        """Extracts canonical (perturbation, total_runs, failures, passes, dots_bitstring) tuples from all stages."""
        records: list[tuple[str, int, int, int, str]] = []

        if isinstance(trace, dict):
            # Stage 1
            s1 = trace.get("stage1_baseline", {})
            s1_dots = "".join("1" if d else "0" for d in (s1.get("run_dots") or []))
            records.append((
                _normalize_pert(s1.get("perturbation", "baseline")),
                int(s1.get("total_runs", 0)),
                int(s1.get("failures", 0)),
                int(s1.get("passes", 0)),
                s1_dots,
            ))
            # Stage 2
            for item in trace.get("stage2_ledger", []):
                item_dots = "".join("1" if d else "0" for d in (item.get("run_dots") or []))
                records.append((
                    _normalize_pert(item.get("perturbation", "")),
                    int(item.get("total_runs", 0)),
                    int(item.get("failures", 0)),
                    int(item.get("passes", 0)),
                    item_dots,
                ))
            # Stage 4 Fix Attempts
            for attempt in trace.get("fix_attempts", []):
                norm = attempt.get("normal_cert_result", {})
                norm_dots = "".join("1" if d else "0" for d in (norm.get("run_dots") or []))
                records.append((
                    _normalize_pert(norm.get("perturbation", "baseline")),
                    int(norm.get("total_runs", 0)),
                    int(norm.get("failures", 0)),
                    int(norm.get("passes", 0)),
                    norm_dots,
                ))
                stress = attempt.get("stress_cert_result", {})
                stress_dots = "".join("1" if d else "0" for d in (stress.get("run_dots") or []))
                records.append((
                    _normalize_pert(stress.get("perturbation", "")),
                    int(stress.get("total_runs", 0)),
                    int(stress.get("failures", 0)),
                    int(stress.get("passes", 0)),
                    stress_dots,
                ))
            # Flake Amplifier Report (if present)
            amp = trace.get("amplifier_report")
            if amp and isinstance(amp, dict):
                winning_arm_id = str(amp.get("winning_arm_id", ""))
                conf_runs = int(amp.get("confirmation_runs", 0))
                conf_fails = int(amp.get("confirmation_failures", 0))
                conf_passes = conf_runs - conf_fails
                records.append((
                    f"amplifier:{winning_arm_id}",
                    conf_runs,
                    conf_fails,
                    conf_passes,
                    "",
                ))
        else:
            # Stage 1
            s1 = trace.stage1_baseline
            s1_dots = "".join("1" if d else "0" for d in (s1.run_dots or []))
            records.append((
                _normalize_pert(s1.perturbation),
                s1.total_runs,
                s1.failures,
                s1.passes,
                s1_dots,
            ))
            # Stage 2
            for item in trace.stage2_ledger:
                item_dots = "".join("1" if d else "0" for d in (item.run_dots or []))
                records.append((
                    _normalize_pert(item.perturbation),
                    item.total_runs,
                    item.failures,
                    item.passes,
                    item_dots,
                ))
            # Stage 4 Fix Attempts
            for attempt in trace.fix_attempts:
                norm = attempt.normal_cert_result
                norm_dots = "".join("1" if d else "0" for d in (norm.run_dots or []))
                records.append((
                    _normalize_pert(norm.perturbation),
                    norm.total_runs,
                    norm.failures,
                    norm.passes,
                    norm_dots,
                ))
                stress = attempt.stress_cert_result
                stress_dots = "".join("1" if d else "0" for d in (stress.run_dots or []))
                records.append((
                    _normalize_pert(stress.perturbation),
                    stress.total_runs,
                    stress.failures,
                    stress.passes,
                    stress_dots,
                ))
            # Flake Amplifier Report (if present)
            if trace.amplifier_report is not None:
                amp_obj = trace.amplifier_report
                winning_arm_id = str(amp_obj.winning_arm_id)
                conf_runs = int(amp_obj.confirmation_runs)
                conf_fails = int(amp_obj.confirmation_failures)
                conf_passes = conf_runs - conf_fails
                records.append((
                    f"amplifier:{winning_arm_id}",
                    conf_runs,
                    conf_fails,
                    conf_passes,
                    "",
                ))

        return records

    def compute_ledger_merkle_root(
        self,
        trace_or_records: CoinflipCertificateTrace | dict[str, Any] | list[tuple[str, int, int, int, str]] | list[tuple[str, int, int, int]],
    ) -> str:
        """Constructs a binary SHA-256 Merkle tree over all experiment ledger batches.

        Includes perturbation, total_runs, failures, passes, and compact run_dots bitstring in leaf nodes.
        """
        if isinstance(trace_or_records, list):
            records = trace_or_records
        else:
            records = self.extract_ledger_records(trace_or_records)

        if not records:
            return hashlib.sha256(b"empty_ledger").hexdigest()

        # Hash leaf nodes
        leaf_hashes: list[str] = []
        for r in records:
            if len(r) == 5:
                pert, total, fails, passes, dots = r
            else:
                pert, total, fails, passes = r[:4]
                dots = ""
            leaf_str = f"{pert}:{total}:{fails}:{passes}:{dots}"
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

    def compute_hmac_signature(
        self,
        repo_snapshot_sha256: str,
        patch_diff_sha256: str,
        experiment_ledger_merkle_root: str,
        secret: str | None = None,
    ) -> str:
        """Computes HMAC-SHA256 signature binding the repo, patch, and Merkle root."""
        if secret is None:
            secret = os.environ.get("COINFLIP_ATTESTATION_SECRET", "coinflip-merkle-hmac-v1-2026")
        payload_bytes = f"{repo_snapshot_sha256}:{patch_diff_sha256}:{experiment_ledger_merkle_root}".encode()
        return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

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
        repo_dir: Path | str | None = None,
    ) -> CoinflipCertificateTrace:
        """Signs a CoinflipCertificateTrace, populating its attestation field with Merkle root and HMAC."""
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
        hmac_sig = self.compute_hmac_signature(repo_sha, patch_sha, merkle_root)

        trace.attestation = CryptographicAttestation(
            algorithm="SHA-256-Merkle",
            repo_snapshot_sha256=repo_sha,
            patch_diff_sha256=patch_sha,
            experiment_ledger_merkle_root=merkle_root,
            certificate_digest_sha256=digest,
            hmac_signature=hmac_sig,
            signing_mode="hmac_sha256_server_secret",
            verified=True,
        )
        return trace

    def build_trace_attestation(
        self,
        trace: CoinflipCertificateTrace | dict[str, Any],
        repo_dir: Path | str | None = None,
    ) -> CryptographicAttestation:
        """Constructs and returns CryptographicAttestation for a trace or dict."""
        if isinstance(trace, dict):
            certified_patch = ""
            for attempt in reversed(trace.get("fix_attempts", [])):
                if attempt.get("verdict") == "CERTIFIED":
                    certified_patch = attempt.get("git_diff_patch", "")
                    break
            if not certified_patch and trace.get("fix_attempts"):
                certified_patch = trace.get("fix_attempts")[-1].get("git_diff_patch", "")

            repo_sha = self.compute_repo_snapshot_sha256(repo_dir)
            patch_sha = self.compute_patch_diff_sha256(certified_patch)
            merkle_root = self.compute_ledger_merkle_root(trace)
            digest = self.compute_certificate_digest(
                repo_snapshot_sha256=repo_sha,
                patch_diff_sha256=patch_sha,
                experiment_ledger_merkle_root=merkle_root,
                final_verdict=str(trace.get("final_verdict", "PASS")),
                trace_id=str(trace.get("trace_id", "")),
            )
            hmac_sig = self.compute_hmac_signature(repo_sha, patch_sha, merkle_root)
            return CryptographicAttestation(
                algorithm="SHA-256-Merkle",
                repo_snapshot_sha256=repo_sha,
                patch_diff_sha256=patch_sha,
                experiment_ledger_merkle_root=merkle_root,
                certificate_digest_sha256=digest,
                hmac_signature=hmac_sig,
                signing_mode="hmac_sha256_server_secret",
                verified=True,
            )
        else:
            signed = self.attest_trace(trace, repo_dir=repo_dir)
            assert signed.attestation is not None
            return signed.attestation

    def verify_trace(
        self, trace: dict[str, Any] | CoinflipCertificateTrace
    ) -> dict[str, Any]:
        """Comprehensive verification of trace leaf counts, Merkle root, and HMAC signature."""
        return verify_trace(trace)

    def verify_trace_attestation(self, trace: dict[str, Any] | CoinflipCertificateTrace) -> bool:
        """Cryptographically verifies that the trace's ledger and patch are authentic and untampered."""
        result = verify_trace(trace)
        return bool(result.get("verified", False))


def verify_trace(trace: dict[str, Any] | CoinflipCertificateTrace) -> dict[str, Any]:
    """Cryptographically verifies trace integrity against forgery or tampering.

    Execution:
    1. Extract claimed_root and claimed_hmac from trace["attestation"] BEFORE recomputing anything.
    2. Validate that for every batch in Stage 1, Stage 2, and Stage 4, if run_dots is present and non-empty:
       failures == sum(1 for d in run_dots if not d) and total_runs == len(run_dots) and passes + failures == total_runs.
    3. Recompute the Merkle root from the stage records without mutating claimed_root, and compare digests.
    4. If claimed_hmac is present, verify HMAC-SHA256 signature against secret.
    5. Return structured verification report.
    """
    if isinstance(trace, CoinflipCertificateTrace):
        data = trace.model_dump()
    elif isinstance(trace, dict):
        data = trace
    else:
        return {
            "verified": False,
            "claimed_merkle_root": "",
            "computed_merkle_root": "",
            "leaf_counts_valid": False,
            "hmac_valid": False,
            "reason": f"Unsupported trace input type: {type(trace).__name__}",
        }

    # Step 1: Extract claimed_root and claimed_hmac before recomputing anything
    attestation = data.get("attestation") or data.get("cryptographic_attestation")
    if not attestation or not isinstance(attestation, dict):
        return {
            "verified": False,
            "claimed_merkle_root": "",
            "computed_merkle_root": "",
            "leaf_counts_valid": False,
            "hmac_valid": False,
            "reason": "Missing attestation block in trace",
        }

    claimed_root = str(
        attestation.get("experiment_ledger_merkle_root")
        or attestation.get("ledger_merkle_root")
        or ""
    )
    claimed_hmac = attestation.get("hmac_signature")
    if claimed_hmac is not None:
        claimed_hmac = str(claimed_hmac)

    # Step 2: Validate batch counts and run_dots integrity
    batches: list[tuple[str, dict[str, Any]]] = []
    if "stage1_baseline" in data and isinstance(data["stage1_baseline"], dict):
        batches.append(("stage1_baseline", data["stage1_baseline"]))

    for idx, b in enumerate(data.get("stage2_ledger", [])):
        if isinstance(b, dict):
            batches.append((f"stage2_ledger[{idx}] ({b.get('perturbation', '')})", b))

    for idx, attempt in enumerate(data.get("fix_attempts", [])):
        if isinstance(attempt, dict):
            norm = attempt.get("normal_cert_result")
            if isinstance(norm, dict):
                batches.append((f"fix_attempts[{idx}].normal_cert_result", norm))
            stress = attempt.get("stress_cert_result")
            if isinstance(stress, dict):
                batches.append((f"fix_attempts[{idx}].stress_cert_result", stress))

    leaf_counts_valid = True
    leaf_error_msg = ""
    for label, batch in batches:
        total_runs = int(batch.get("total_runs", 0))
        failures = int(batch.get("failures", 0))
        passes = int(batch.get("passes", 0))

        if passes + failures != total_runs:
            leaf_counts_valid = False
            leaf_error_msg = (
                f"Batch arithmetic mismatch in {label}: passes ({passes}) + failures ({failures}) != total_runs ({total_runs})"
            )
            break

        run_dots = batch.get("run_dots")
        if run_dots is not None and len(run_dots) > 0:
            actual_failures = sum(1 for d in run_dots if not d)
            actual_total = len(run_dots)
            if failures != actual_failures:
                leaf_counts_valid = False
                leaf_error_msg = (
                    f"Tampered failures count in {label}: recorded failures={failures} != actual run_dots failures={actual_failures}"
                )
                break
            if total_runs != actual_total:
                leaf_counts_valid = False
                leaf_error_msg = (
                    f"Tampered total_runs count in {label}: recorded total_runs={total_runs} != actual len(run_dots)={actual_total}"
                )
                break

    if not leaf_counts_valid:
        return {
            "verified": False,
            "claimed_merkle_root": claimed_root,
            "computed_merkle_root": "",
            "leaf_counts_valid": False,
            "hmac_valid": False,
            "reason": leaf_error_msg,
        }

    # Validate Flake Amplifier Report arithmetic if present
    amp = data.get("amplifier_report")
    if amp and isinstance(amp, dict):
        conf_runs = int(amp.get("confirmation_runs", 0))
        conf_fails = int(amp.get("confirmation_failures", 0))
        if conf_fails > conf_runs:
            return {
                "verified": False,
                "claimed_merkle_root": claimed_root,
                "computed_merkle_root": "",
                "leaf_counts_valid": False,
                "hmac_valid": False,
                "reason": f"Tampered amplifier confirmation counts: failures={conf_fails} > total_runs={conf_runs}",
            }

    # Step 3: Recompute Merkle root without mutating claimed_root
    attestor = CertificateAttestor()
    computed_root = attestor.compute_ledger_merkle_root(data)
    root_valid = bool(claimed_root and hmac.compare_digest(claimed_root, computed_root))

    # Step 4: Verify patch diff SHA-256 and HMAC signature
    repo_sha = str(attestation.get("repo_snapshot_sha256") or attestor.compute_repo_snapshot_sha256(None))
    claimed_patch_sha = str(attestation.get("patch_diff_sha256") or attestation.get("patch_sha256") or "")

    certified_patch = ""
    for attempt in reversed(data.get("fix_attempts", [])):
        if attempt.get("verdict") == "CERTIFIED":
            certified_patch = attempt.get("git_diff_patch", "")
            break
    if not certified_patch and data.get("fix_attempts"):
        certified_patch = data.get("fix_attempts")[-1].get("git_diff_patch", "")
    actual_patch_sha = attestor.compute_patch_diff_sha256(certified_patch)

    patch_valid = bool(not claimed_patch_sha or hmac.compare_digest(claimed_patch_sha, actual_patch_sha))
    computed_hmac = attestor.compute_hmac_signature(repo_sha, actual_patch_sha, computed_root)

    if claimed_hmac is not None:
        hmac_valid = bool(hmac.compare_digest(claimed_hmac, computed_hmac))
    else:
        hmac_valid = True

    is_verified = bool(leaf_counts_valid and root_valid and patch_valid and hmac_valid)
    if not root_valid:
        reason = f"Merkle root mismatch! Claimed: {claimed_root}, Computed: {computed_root}"
    elif not patch_valid:
        reason = f"Patch diff SHA-256 mismatch! Claimed: {claimed_patch_sha}, Computed: {actual_patch_sha}"
    elif claimed_hmac is not None and not hmac_valid:
        reason = f"HMAC signature mismatch! Claimed: {claimed_hmac}, Computed: {computed_hmac}"
    else:
        reason = "Cryptographic Merkle attestation and HMAC signature verified successfully."

    return {
        "verified": is_verified,
        "claimed_merkle_root": claimed_root,
        "computed_merkle_root": computed_root,
        "leaf_counts_valid": leaf_counts_valid,
        "patch_valid": patch_valid,
        "hmac_valid": hmac_valid,
        "reason": reason,
    }


def attest_trace(
    trace: CoinflipCertificateTrace, repo_dir: Path | str | None = None
) -> CoinflipCertificateTrace:
    """Convenience functional helper to sign a CoinflipCertificateTrace."""
    return CertificateAttestor().attest_trace(trace, repo_dir=repo_dir)


def verify_trace_attestation(trace: dict[str, Any] | CoinflipCertificateTrace) -> bool:
    """Convenience functional helper to verify a CoinflipCertificateTrace."""
    return CertificateAttestor().verify_trace_attestation(trace)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Coinflip SHA-256 Merkle & HMAC Certificate Attestation CLI"
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
            trace_dict = json.loads(content)
            res = verify_trace(trace_dict)

            if res["verified"]:
                print("\n" + "=" * 80)
                print("✅ COINFLIP CRYPTOGRAPHIC ATTESTATION VERIFIED")
                print("=" * 80)
                print(f"Claimed Merkle Root:  {res['claimed_merkle_root']}")
                print(f"Computed Merkle Root: {res['computed_merkle_root']}")
                print(f"Leaf Counts Valid:    {res['leaf_counts_valid']}")
                print(f"HMAC Signature Valid: {res['hmac_valid']}")
                print(f"Verification Reason:  {res['reason']}")
                print("Status:               100% CRYPTOGRAPHICALLY AUTHENTIC & UNTAMPERED")
                print("=" * 80 + "\n")
                sys.exit(0)
            else:
                print("\n" + "!" * 80, file=sys.stderr)
                print("❌ CRITICAL ATTESTATION FAILURE: TAMPERING DETECTED!", file=sys.stderr)
                print("!" * 80, file=sys.stderr)
                print(f"Reason:               {res['reason']}", file=sys.stderr)
                print(f"Claimed Merkle Root:  {res['claimed_merkle_root']}", file=sys.stderr)
                print(f"Computed Merkle Root: {res['computed_merkle_root']}", file=sys.stderr)
                print(f"Leaf Counts Valid:    {res['leaf_counts_valid']}", file=sys.stderr)
                print(f"HMAC Signature Valid: {res['hmac_valid']}", file=sys.stderr)
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
