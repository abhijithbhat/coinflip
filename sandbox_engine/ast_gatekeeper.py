"""Compiler-Grade AST Semantic Anti-Cheat Gatekeeper for Coinflip.

Analyzes candidate test code patches using Python's ast module to deterministically
enforce scientific rigor:
1. Rejects assertion tampering (deleted assertions, tautological 'assert True' / 'assert 1 == 1').
2. Rejects test suppression (@pytest.mark.skip, @unittest.skip, pytest.skip(), or try/except swallowing).
3. Identifies sleep-inflation vs. deterministic synchronization (flags naive sleep increases
   with WARN_SLEEP_INFLATION while permitting them to fail empirically in Stage 4 stress tests;
   verifies real event/lock synchronization as VERIFIED_CLEAN).
"""

from __future__ import annotations

import ast
import re
from typing import Any, Optional

from shared_contracts.schemas import ASTGatekeeperReport


class ASTSemanticGatekeeper:
    """Deterministic AST analyzer that audits candidate patches prior to or during Stage 4."""

    def __init__(self) -> None:
        pass

    def audit(self, original_code: str, patched_code: str) -> ASTGatekeeperReport:
        """Audits original test code vs patched test code or diff.

        Args:
            original_code: Python source code of original test.
            patched_code: Python source code of patched test, or unified git diff.

        Returns:
            ASTGatekeeperReport: Deterministic audit verdict and telemetry.
        """
        orig_ast = self._parse_source(original_code, label="original")
        resolved_patched_code = self._resolve_patched_source(original_code, patched_code)
        patch_ast = self._parse_source(resolved_patched_code, label="patched")

        # 1. Assertion analysis
        orig_total, orig_meaningful, orig_taut = self._analyze_assertions(orig_ast)
        patch_total, patch_meaningful, patch_taut = self._analyze_assertions(patch_ast)

        # Check assertion preservation
        assertions_preserved = True
        if orig_meaningful > 0:
            if patch_meaningful < orig_meaningful:
                assertions_preserved = False
            # Check if meaningful assertions were replaced by tautologies
            if patch_taut > orig_taut and patch_meaningful <= orig_meaningful and patch_total <= orig_total:
                assertions_preserved = False
        elif orig_total > 0 and patch_total == 0:
            assertions_preserved = False

        # 2. Suppression analysis
        orig_no_skip, orig_no_swallow = self._analyze_suppression(orig_ast)
        patch_no_skip, patch_no_swallow = self._analyze_suppression(patch_ast)

        # Suppression was introduced if patched has it but original didn't
        no_skip_decorators = patch_no_skip if orig_no_skip else True
        no_bare_exception_swallowing = patch_no_swallow if orig_no_swallow else True

        # 3. Sleep inflation vs synchronization analysis
        orig_sleeps, _ = self._extract_sleep_and_sync(orig_ast)
        patch_sleeps, patch_sync = self._extract_sleep_and_sync(patch_ast)

        orig_max_sleep = max(orig_sleeps, default=0.0)
        patch_max_sleep = max(patch_sleeps, default=0.0)
        orig_sum_sleep = sum(orig_sleeps)
        patch_sum_sleep = sum(patch_sleeps)

        has_sync_primitives = len(patch_sync) > 0
        sleep_inflation_detected = False

        if not has_sync_primitives:
            if patch_max_sleep > (orig_max_sleep + 1e-6) or patch_sum_sleep > (orig_sum_sleep + 1e-6):
                sleep_inflation_detected = True

        # 4. Formulate gatekeeper decision
        if not assertions_preserved:
            passed_gatekeeper = False
            status_code = "BLOCKED_ASSERTION_TAMPERING"
            summary = (
                f"Blocked Assertion Tampering: Original test contained {orig_meaningful} valid assertion(s), "
                f"but candidate patch contains only {patch_meaningful} valid assertion(s) "
                f"({patch_taut} tautological). Real verification assertions must not be removed."
            )
        elif not no_skip_decorators or not no_bare_exception_swallowing:
            passed_gatekeeper = False
            status_code = "BLOCKED_TEST_SUPPRESSION"
            reasons = []
            if not no_skip_decorators:
                reasons.append("test skip decorator or skip invocation added")
            if not no_bare_exception_swallowing:
                reasons.append("exception-swallowing try/except block wrapping assertion")
            summary = (
                f"Blocked Test Suppression: Candidate patch attempted to suppress test execution ({', '.join(reasons)})."
            )
        elif sleep_inflation_detected:
            passed_gatekeeper = True  # Permitted into Stage 4 so CPU stress test proves it fails
            status_code = "WARN_SLEEP_INFLATION"
            summary = (
                f"Warning: Sleep Inflation Detected. Candidate patch increased sleep duration from "
                f"{orig_max_sleep:.4f}s to {patch_max_sleep:.4f}s without adding deterministic synchronization. "
                f"Allowed to proceed to Stage 4 Dual-Condition Gate for empirical stress verification."
            )
        else:
            passed_gatekeeper = True
            status_code = "VERIFIED_CLEAN"
            sync_desc = f" [{', '.join(patch_sync)}]" if patch_sync else ""
            summary = (
                f"Verified Clean: All assertions preserved ({patch_meaningful}/{orig_meaningful}), "
                f"no suppression detected, and deterministic synchronization verified{sync_desc}."
            )

        return ASTGatekeeperReport(
            passed_gatekeeper=passed_gatekeeper,
            status_code=status_code,
            original_assert_count=orig_meaningful,
            patched_assert_count=patch_meaningful,
            assertions_preserved=assertions_preserved,
            no_skip_decorators=no_skip_decorators,
            no_bare_exception_swallowing=no_bare_exception_swallowing,
            sleep_inflation_detected=sleep_inflation_detected,
            synchronization_primitives_detected=patch_sync,
            summary=summary,
        )

    def __call__(self, original_code: str, patched_code: str) -> ASTGatekeeperReport:
        return self.audit(original_code, patched_code)

    @classmethod
    def check(cls, original_code: str, patched_code: str) -> ASTGatekeeperReport:
        return cls().audit(original_code, patched_code)

    def _parse_source(self, code: str, label: str = "code") -> ast.AST:
        """Parses Python source code into an AST node."""
        cleaned = code.strip()
        # Handle markdown wrapping ```python ... ```
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        try:
            return ast.parse(cleaned)
        except SyntaxError as e:
            # Try indenting as a block if it's a bare function body snippet
            try:
                return ast.parse(f"def _dummy():\n" + "\n".join(f"    {line}" for line in cleaned.splitlines()))
            except SyntaxError:
                raise ValueError(f"Failed to parse {label} Python source code for AST audit: {e}") from e

    def _resolve_patched_source(self, original_code: str, patched_code: str) -> str:
        """Determines if patched_code is direct Python or a unified diff, returning valid Python."""
        cleaned = patched_code.strip()
        # If it parses directly, it's valid Python source
        try:
            self._parse_source(cleaned)
            return cleaned
        except Exception:
            pass

        # Check if it looks like a unified diff
        if any(cleaned.startswith(marker) for marker in ("diff --git", "--- ", "@@ ")):
            applied = self._apply_diff_text(original_code, cleaned)
            if applied:
                return applied

        # Fallback: extract added lines ('+') from diff
        added_lines: list[str] = []
        for line in cleaned.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added_lines.append(line[1:])
            elif not line.startswith("-") and not line.startswith("---") and not line.startswith("@@"):
                added_lines.append(line)
        candidate = "\n".join(added_lines)
        try:
            self._parse_source(candidate)
            return candidate
        except Exception:
            return patched_code

    def _apply_diff_text(self, original: str, diff_text: str) -> Optional[str]:
        """Simple in-memory unified diff applier for single test snippets."""
        orig_lines = original.splitlines(keepends=True)
        # Parse hunk headers
        hunk_pattern = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
        result_lines: list[str] = []
        diff_lines = diff_text.splitlines(keepends=True)

        idx = 0
        hunk_active = False
        target_orig_idx = 0

        for line in diff_lines:
            m = hunk_pattern.match(line)
            if m:
                hunk_active = True
                orig_start = int(m.group(1)) - 1
                # Copy original lines up to orig_start
                while target_orig_idx < orig_start and target_orig_idx < len(orig_lines):
                    result_lines.append(orig_lines[target_orig_idx])
                    target_orig_idx += 1
                continue

            if hunk_active:
                if line.startswith("+"):
                    result_lines.append(line[1:])
                elif line.startswith("-"):
                    target_orig_idx += 1
                elif line.startswith(" "):
                    if target_orig_idx < len(orig_lines):
                        result_lines.append(orig_lines[target_orig_idx])
                        target_orig_idx += 1
                    else:
                        result_lines.append(line[1:])

        while target_orig_idx < len(orig_lines):
            result_lines.append(orig_lines[target_orig_idx])
            target_orig_idx += 1

        res = "".join(result_lines)
        try:
            self._parse_source(res)
            return res
        except Exception:
            return None

    def _is_tautological_assert(self, test_node: ast.AST) -> bool:
        """Detects whether an assertion condition is tautological (e.g., assert True, assert 1 == 1)."""
        # Constant truthy values: assert True, assert 1, assert "ok"
        if isinstance(test_node, ast.Constant):
            if bool(test_node.value) is True:
                return True

        # Equality comparisons: assert 1 == 1, assert "a" == "a", assert x == x
        if isinstance(test_node, ast.Compare):
            if len(test_node.ops) == 1 and isinstance(test_node.ops[0], (ast.Eq, ast.Is)):
                left = test_node.left
                comparator = test_node.comparators[0]
                if isinstance(left, ast.Constant) and isinstance(comparator, ast.Constant):
                    if left.value == comparator.value:
                        return True
                elif isinstance(left, ast.Name) and isinstance(comparator, ast.Name):
                    if left.id == comparator.id:
                        return True

        return False

    def _analyze_assertions(self, tree: ast.AST) -> tuple[int, int, int]:
        """Counts (total_assertions, meaningful_assertions, tautological_assertions)."""
        total = 0
        meaningful = 0
        tautological = 0

        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                total += 1
                if self._is_tautological_assert(node.test):
                    tautological += 1
                else:
                    meaningful += 1

            elif isinstance(node, ast.Call):
                func = node.func
                # self.assert* calls
                if isinstance(func, ast.Attribute) and func.attr.startswith("assert"):
                    total += 1
                    is_taut = False
                    if func.attr in ("assertTrue", "assertFalse") and node.args:
                        is_taut = self._is_tautological_assert(node.args[0])
                    elif func.attr == "assertEqual" and len(node.args) >= 2:
                        cmp_node = ast.Compare(
                            left=node.args[0],
                            ops=[ast.Eq()],
                            comparators=[node.args[1]],
                        )
                        is_taut = self._is_tautological_assert(cmp_node)

                    if is_taut:
                        tautological += 1
                    else:
                        meaningful += 1

                # pytest.raises(...)
                elif isinstance(func, ast.Attribute) and func.attr == "raises":
                    if isinstance(func.value, ast.Name) and func.value.id == "pytest":
                        total += 1
                        meaningful += 1

            elif isinstance(node, ast.With):
                for item in node.items:
                    expr = item.context_expr
                    if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute):
                        if expr.func.attr == "raises" and isinstance(expr.func.value, ast.Name) and expr.func.value.id == "pytest":
                            total += 1
                            meaningful += 1

        return total, meaningful, tautological

    def _analyze_suppression(self, tree: ast.AST) -> tuple[bool, bool]:
        """Detects whether skip decorators or bare exception swallowing are present."""
        no_skip_decorators = True
        no_bare_exception_swallowing = True

        skip_marker_names = {
            "skip", "xfail", "skipif",
            "pytest.mark.skip", "pytest.mark.xfail", "pytest.mark.skipif",
            "unittest.skip", "unittest.skipIf", "unittest.skipUnless",
        }

        for node in ast.walk(tree):
            # Check function and class decorators
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                for dec in node.decorator_list:
                    dec_name = self._get_decorator_name(dec)
                    if dec_name and any(dec_name == s or dec_name.endswith(f".{s}") for s in skip_marker_names):
                        no_skip_decorators = False

            # Check calls to pytest.skip() or pytest.xfail()
            elif isinstance(node, ast.Call):
                name = self._get_call_name(node)
                if name in ("pytest.skip", "pytest.xfail", "unittest.skipTest", "skip"):
                    no_skip_decorators = False

            # Check try/except blocks swallowing assertions
            elif isinstance(node, ast.Try):
                has_assert_in_try = any(
                    isinstance(child, (ast.Assert, ast.Call))
                    for child in ast.walk(node)
                    if child is not node and not any(
                        isinstance(h, ast.ExceptHandler) and self._is_descendant(child, h)
                        for h in node.handlers
                    )
                )

                for handler in node.handlers:
                    # Catch Exception, BaseException, or bare except
                    is_broad_except = False
                    if handler.type is None:
                        is_broad_except = True
                    elif isinstance(handler.type, ast.Name) and handler.type.id in ("Exception", "BaseException"):
                        is_broad_except = True

                    if is_broad_except:
                        # Check if body is just pass or empty/ellipsis
                        body_stmts = [
                            s for s in handler.body
                            if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
                        ]
                        has_re_raise = any(isinstance(s, ast.Raise) for s in handler.body)
                        if (not body_stmts or all(isinstance(s, ast.Pass) for s in body_stmts)) and not has_re_raise:
                            if has_assert_in_try or len(node.body) > 0:
                                no_bare_exception_swallowing = False

        return no_skip_decorators, no_bare_exception_swallowing

    def _is_descendant(self, child: ast.AST, parent: ast.AST) -> bool:
        """Returns True if child node is inside parent node tree."""
        for n in ast.walk(parent):
            if n is child:
                return True
        return False

    def _get_decorator_name(self, node: ast.AST) -> Optional[str]:
        """Extracts identifier string from decorator AST node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            val = self._get_decorator_name(node.value)
            return f"{val}.{node.attr}" if val else node.attr
        elif isinstance(node, ast.Call):
            return self._get_decorator_name(node.func)
        return None

    def _get_call_name(self, node: ast.Call) -> Optional[str]:
        """Extracts dotted identifier string from Call node."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            val = self._get_decorator_name(node.func.value)
            return f"{val}.{node.func.attr}" if val else node.func.attr
        return None

    def _extract_sleep_and_sync(self, tree: ast.AST) -> tuple[list[float], list[str]]:
        """Extracts sleep durations and detected synchronization primitives."""
        sleep_durations: list[float] = []
        sync_primitives: list[str] = []

        sync_method_names = {
            "wait_for_completion",
            "wait",
            "join",
            "acquire",
            "notify",
            "notify_all",
            "set",
        }

        sync_type_names = {
            "Event",
            "Lock",
            "RLock",
            "Condition",
            "Semaphore",
            "BoundedSemaphore",
            "Barrier",
            "Queue",
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call_name = self._get_call_name(node)
                # Check sleep calls
                if call_name in ("time.sleep", "asyncio.sleep", "sleep"):
                    if node.args and isinstance(node.args[0], ast.Constant):
                        if isinstance(node.args[0].value, (int, float)):
                            sleep_durations.append(float(node.args[0].value))

                # Check synchronization calls
                if isinstance(node.func, ast.Attribute):
                    attr = node.func.attr
                    if attr == "wait_for_completion":
                        sync_primitives.append("wait_for_completion")
                    elif attr in sync_method_names:
                        # Include receiver name if available: e.g. done_event.wait, thread.join
                        rec_name = self._get_decorator_name(node.func.value)
                        if rec_name:
                            sync_primitives.append(f"{rec_name}.{attr}")
                        else:
                            sync_primitives.append(attr)

                # Check instantiation: e.g. threading.Event(), Event(), threading.Lock()
                if call_name:
                    base_name = call_name.split(".")[-1]
                    if base_name in sync_type_names:
                        sync_primitives.append(call_name)

        # Deduplicate while preserving insertion order
        seen: set[str] = set()
        deduped_sync: list[str] = []
        for s in sync_primitives:
            if s not in seen:
                seen.add(s)
                deduped_sync.append(s)

        return sleep_durations, deduped_sync
