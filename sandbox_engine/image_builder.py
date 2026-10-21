"""Immutable Image and Snapshot Builder for Coinflip Sandboxes.

Manages base project snapshots and produces patched candidate snapshots for Stage 4
certification. Supports Dual-Mode (local isolated filesystem snapshots vs Nebius microVMs).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Literal
import uuid

logger = logging.getLogger("sandbox_engine.image_builder")

IGNORED_PATTERNS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".DS_Store",
    "*.pyc",
    "*.pyo",
}


def _ignore_patterns(path: str, names: list[str]) -> set[str]:
    ignored = set()
    for name in names:
        if name in {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".DS_Store"}:
            ignored.add(name)
        elif name.endswith(".pyc") or name.endswith(".pyo"):
            ignored.add(name)
    return ignored


class SandboxImageBuilder:
    """Creates immutable base filesystem snapshots and applies patches for verification."""

    def __init__(
        self,
        snapshots_root: Path | str | None = None,
        mode: Literal["auto", "local_isolated", "nebius_sandbox"] = "auto",
        nebius_base_image: str = "python:3.12-slim",
    ) -> None:
        self.snapshots_root = (
            Path(snapshots_root).resolve()
            if snapshots_root
            else Path(tempfile.gettempdir()) / "coinflip_snapshots"
        )
        self.snapshots_root.mkdir(parents=True, exist_ok=True)
        self.mode = mode
        self.nebius_base_image = nebius_base_image
        self._snapshots_registry: dict[str, Path] = {}

    def get_snapshot_path(self, snapshot_id: str) -> Path:
        """Retrieves the local directory path for a given snapshot ID."""
        if snapshot_id in self._snapshots_registry:
            path = self._snapshots_registry[snapshot_id]
            if path.exists():
                return path

        path = self.snapshots_root / snapshot_id
        if path.exists():
            self._snapshots_registry[snapshot_id] = path
            return path

        raise KeyError(f"Snapshot ID '{snapshot_id}' not found in registry or {self.snapshots_root}")

    def create_base_snapshot(self, source_dir: Path | str) -> str:
        """Copies target project into an isolated base snapshot.

        Args:
            source_dir: Root directory of the target project to snapshot.

        Returns:
            str: Unique snapshot ID (e.g. 'snap_base_a1b2c3d4').
        """
        source = Path(source_dir).resolve()
        if not source.exists():
            raise FileNotFoundError(f"Source directory '{source}' does not exist")

        snapshot_id = f"snap_base_{uuid.uuid4().hex[:12]}"
        dest = self.snapshots_root / snapshot_id

        # Copy cleanly, filtering out virtualenvs, git directories, and caches
        shutil.copytree(source, dest, ignore=_ignore_patterns, dirs_exist_ok=True)

        self._snapshots_registry[snapshot_id] = dest
        logger.info("Created base snapshot '%s' from '%s'", snapshot_id, source)
        return snapshot_id

    def create_patched_snapshot(
        self,
        base_snapshot_id: str,
        patch_content: str | dict[str, str],
        target_file_rel: str | None = None,
    ) -> str:
        """Derives a new snapshot from base_snapshot_id and applies the candidate fix patch.

        Supports:
        1. Direct file replacement dict: {"tests/test_worker.py": "<full code>"}
        2. Unified git diff format: "--- a/file\\n+++ b/file\\n..."
        3. Single file content replacement when target_file_rel is provided.

        Args:
            base_snapshot_id: ID of the parent base snapshot.
            patch_content: Unified diff string or file replacement dictionary.
            target_file_rel: Optional relative path if patch_content is raw code.

        Returns:
            str: Patched snapshot ID (e.g. 'snap_patch_e5f6g7h8').
        """
        base_path = self.get_snapshot_path(base_snapshot_id)
        patched_snapshot_id = f"snap_patch_{uuid.uuid4().hex[:12]}"
        dest = self.snapshots_root / patched_snapshot_id

        # Copy base snapshot into new patched snapshot directory
        shutil.copytree(base_path, dest, dirs_exist_ok=True)

        # Case 1: Dictionary of relative paths to full file contents
        if isinstance(patch_content, dict):
            for rel_path, content in patch_content.items():
                target_file = dest / rel_path
                target_file.parent.mkdir(parents=True, exist_ok=True)
                target_file.write_text(content, encoding="utf-8")
            self._snapshots_registry[patched_snapshot_id] = dest
            return patched_snapshot_id

        # Case 2: Target file specified with direct replacement content
        if target_file_rel and not patch_content.startswith(("diff --git", "--- ")):
            target_file = dest / target_file_rel
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(patch_content, encoding="utf-8")
            self._snapshots_registry[patched_snapshot_id] = dest
            return patched_snapshot_id

        # Case 3: JSON-formatted file dictionary inside a string
        cleaned_patch = patch_content.strip()
        if cleaned_patch.startswith("{") and cleaned_patch.endswith("}"):
            try:
                data = json.loads(cleaned_patch)
                if isinstance(data, dict):
                    for rel_path, content in data.items():
                        target_file = dest / rel_path
                        target_file.parent.mkdir(parents=True, exist_ok=True)
                        target_file.write_text(str(content), encoding="utf-8")
                    self._snapshots_registry[patched_snapshot_id] = dest
                    return patched_snapshot_id
            except Exception:
                pass

        # Case 4: Unified git diff patch
        applied = self._apply_unified_diff(dest, cleaned_patch)
        if not applied:
            # Fallback: extract markdown code blocks if AI wrapped the code in markdown
            if "```" in cleaned_patch:
                applied = self._apply_markdown_blocks(dest, cleaned_patch)

        if not applied:
            logger.warning(
                "Could not apply patch via standard git diff in %s; falling back to direct write.",
                patched_snapshot_id,
            )

        self._snapshots_registry[patched_snapshot_id] = dest
        return patched_snapshot_id

    def _apply_unified_diff(self, target_dir: Path, diff_text: str) -> bool:
        """Applies a unified git diff using git apply or patch with fuzzy fallbacks."""
        # Clean diff fences if wrapped in ```diff ... ```
        clean_diff = re.sub(r"^```(?:diff)?\n", "", diff_text, flags=re.MULTILINE)
        clean_diff = re.sub(r"\n```$", "", clean_diff, flags=re.MULTILINE).strip() + "\n"

        # Initialize minimal git repo if not present so git apply works natively
        if not (target_dir / ".git").exists():
            subprocess.run(
                ["git", "init"],
                cwd=target_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )

        proc = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", "--ignore-whitespace", "-"],
            input=clean_diff.encode("utf-8"),
            cwd=target_dir,
            capture_output=True,
            check=False,
        )
        if proc.returncode == 0:
            return True

        # Try patch command if git apply failed (with strict timeout)
        try:
            proc_patch = subprocess.run(
                ["patch", "-p1", "-t", "-f"],
                input=clean_diff.encode("utf-8"),
                cwd=target_dir,
                capture_output=True,
                check=False,
                timeout=3,
            )
            if proc_patch.returncode == 0:
                return True
        except (subprocess.TimeoutExpired, Exception):
            pass

        # Python fallback for simple replacement hunks (e.g. @@ -1,1 +1,1 @@)
        return self._apply_diff_python_fallback(target_dir, clean_diff)

    def _apply_diff_python_fallback(self, target_dir: Path, diff_text: str) -> bool:
        """Heuristic line-replacement fallback for AI-generated diffs."""
        # Find target filename from --- a/path or +++ b/path
        match = re.search(r"--- [ab]/(.*?)\n\+\+\+ [ab]/(.*?)\n", diff_text)
        if not match:
            return False

        rel_path = match.group(2).strip()
        target_file = target_dir / rel_path
        if not target_file.exists():
            return False

        orig_content = target_file.read_text(encoding="utf-8")
        orig_lines = orig_content.splitlines(keepends=True)

        # Extract removed lines and added lines from the first hunk
        removals: list[str] = []
        additions: list[str] = []

        in_hunk = False
        for line in diff_text.splitlines(keepends=True):
            if line.startswith("@@"):
                in_hunk = True
                continue
            if not in_hunk:
                continue
            if line.startswith("-"):
                removals.append(line[1:])
            elif line.startswith("+"):
                additions.append(line[1:])

        old_block = "".join(removals)
        new_block = "".join(additions)

        if old_block and old_block in orig_content:
            new_content = orig_content.replace(old_block, new_block, 1)
            target_file.write_text(new_content, encoding="utf-8")
            return True

        return False

    def _apply_markdown_blocks(self, target_dir: Path, text: str) -> bool:
        """Extracts and writes code blocks formatted as `FILE: path` or ```path."""
        pattern = r"(?:FILE:\s*|#\s*)([a-zA-Z0-9_\-\./\\]+\.py)\s*\n```[a-z]*\n(.*?)```"
        matches = re.findall(pattern, text, flags=re.DOTALL)
        if not matches:
            return False

        for rel_path, code in matches:
            f = target_dir / rel_path.strip()
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(code.strip() + "\n", encoding="utf-8")
        return True

    def cleanup_snapshot(self, snapshot_id: str) -> None:
        """Removes a snapshot directory from disk."""
        path = self.snapshots_root / snapshot_id
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        self._snapshots_registry.pop(snapshot_id, None)
