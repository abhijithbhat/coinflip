"""Compiler-Grade AST Semantic Anti-Cheat Gatekeeper for Coinflip.

Analyzes candidate test code patches using Python's ast module to deterministically
enforce scientific rigor across all 14 test-weakening and assertion-tampering tricks:
1. Deleted assertions or reduced assertion count (BLOCKED_ASSERTION_TAMPERING).
2. Literal tautologies: assert True, assert 1, assert "ok" (BLOCKED_ASSERTION_TAMPERING).
3. Boolean short-circuit tautologies: assert x or True, assert True or x (BLOCKED_ASSERTION_TAMPERING).
4. Law-of-excluded-middle tautologies: assert x or not x, assert not x or x (BLOCKED_ASSERTION_TAMPERING).
5. Self-comparison tautologies: assert x == x, assert x is x, assert x <= x, assert x >= x, assert x in [x] (BLOCKED_ASSERTION_TAMPERING).
6. Dead conditional assertions: if False: assert ..., if 0: assert ..., if None: assert ... (BLOCKED_ASSERTION_TAMPERING).
7. Early return before assertions in test_* functions (BLOCKED_TEST_SUPPRESSION).
8. Exception swallowing around assertions: try/except catching Exception/AssertionError or with contextlib.suppress(...) (BLOCKED_TEST_SUPPRESSION).
9. Test suppression & rerun decorators: @pytest.mark.skip, @pytest.mark.xfail, @pytest.mark.flaky, @retry, @rerun (BLOCKED_TEST_SUPPRESSION).
10. Weakened assertion operators: replacing strict equality with is not None, !=, >=, <=, bool(x) (BLOCKED_ASSERTION_TAMPERING).
11. Numeric time.sleep(N) inflation without synchronization primitives (WARN_SLEEP_INFLATION).
12-14. Legitimate synchronization fixes (threading.Event, wait(), monotonic(), lock/copy isolation, fixtures) certified as VERIFIED_CLEAN.
"""

from __future__ import annotations

import ast
import re
from typing import Any, Optional

from shared_contracts.schemas import ASTGatekeeperReport


class ASTSemanticGatekeeper:
    """Deterministic AST analyzer that audits candidate patches prior to Stage 4 stress verification."""

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

        # 1. Assertion analysis (counts, tautologies)
        orig_total, orig_meaningful, orig_taut, orig_taut_reasons = self._analyze_assertions(orig_ast)
        patch_total, patch_meaningful, patch_taut, patch_taut_reasons = self._analyze_assertions(patch_ast)

        # 2. Dead conditional assertions (e.g. if False: assert ...)
        patch_dead_conditionals = self._detect_dead_conditional_assertions(patch_ast)

        # 3. Weakened assertion operators (e.g. replacing == with is not None, !=, bool(x))
        patch_weakened_operators = self._detect_weakened_assertions(orig_ast, patch_ast)

        # Check assertion tampering
        tampering_reasons: list[str] = []

        # Reduced assertion count
        if orig_meaningful > 0 and patch_meaningful < orig_meaningful:
            tampering_reasons.append(
                f"assertion count reduced from {orig_meaningful} to {patch_meaningful}"
            )
        elif orig_total > 0 and patch_total == 0:
            tampering_reasons.append("all assertions deleted")

        # Tautological assertions introduced
        new_tautologies = [r for r in patch_taut_reasons if r not in orig_taut_reasons]
        if new_tautologies:
            tampering_reasons.extend(new_tautologies)

        # Dead conditional assertions
        if patch_dead_conditionals:
            tampering_reasons.extend(patch_dead_conditionals)

        # Weakened operators
        if patch_weakened_operators:
            tampering_reasons.extend(patch_weakened_operators)

        assertions_preserved = len(tampering_reasons) == 0

        # 4. Suppression analysis: decorators, calls, early returns, exception swallowing
        suppression_reasons: list[str] = []

        # Early return before assertions
        early_returns = self._detect_early_return_before_assert(orig_ast, patch_ast)
        if early_returns:
            suppression_reasons.extend(early_returns)

        # Exception swallowing (try/except or with contextlib.suppress)
        swallow_reasons = self._detect_exception_swallowing(orig_ast, patch_ast)
        no_bare_exception_swallowing = len(swallow_reasons) == 0
        if not no_bare_exception_swallowing:
            suppression_reasons.extend(swallow_reasons)

        # Skip / flaky / rerun / retry decorators or skip calls
        decorator_reasons = self._detect_suppression_decorators(orig_ast, patch_ast)
        no_skip_decorators = len(decorator_reasons) == 0
        if not no_skip_decorators:
            suppression_reasons.extend(decorator_reasons)

        # 5. Sleep inflation vs synchronization analysis
        orig_sleeps, orig_sync = self._extract_sleep_and_sync(orig_ast)
        patch_sleeps, patch_sync = self._extract_sleep_and_sync(patch_ast)

        orig_max_sleep = max(orig_sleeps, default=0.0)
        patch_max_sleep = max(patch_sleeps, default=0.0)
        orig_sum_sleep = sum(orig_sleeps)
        patch_sum_sleep = sum(patch_sleeps)

        new_sync_primitives = [s for s in patch_sync if s not in orig_sync]
        has_new_sync = len(new_sync_primitives) > 0
        if not orig_sync and patch_sync:
            has_new_sync = True
            new_sync_primitives = patch_sync

        sleep_inflation_detected = False

        if not has_new_sync:
            if patch_max_sleep > (orig_max_sleep + 1e-6) or patch_sum_sleep > (orig_sum_sleep + 1e-6):
                sleep_inflation_detected = True

        # 6. Formulate gatekeeper decision
        if not assertions_preserved:
            passed_gatekeeper = False
            status_code = "BLOCKED_ASSERTION_TAMPERING"
            summary = (
                f"Blocked Assertion Tampering: Candidate patch violates test integrity "
                f"({'; '.join(tampering_reasons)}). Real verification assertions must not be removed or weakened."
            )
        elif suppression_reasons:
            passed_gatekeeper = False
            status_code = "BLOCKED_TEST_SUPPRESSION"
            summary = (
                f"Blocked Test Suppression: Candidate patch attempted to suppress test execution "
                f"({'; '.join(suppression_reasons)})."
            )
        elif sleep_inflation_detected:
            passed_gatekeeper = True  # Permitted into Stage 4 so CPU stress test proves it fails empirically
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
            synchronization_primitives_detected=new_sync_primitives if new_sync_primitives else patch_sync,
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
                return ast.parse("def _dummy():\n" + "\n".join(f"    {line}" for line in cleaned.splitlines()))
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

        # Fallback: line-by-line replacement of removed lines with added lines
        replaced = self._apply_diff_replacement_heuristic(original_code, cleaned)
        if replaced:
            return replaced

        # Fallback 2: extract added lines ('+') from diff
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

    def _apply_diff_replacement_heuristic(self, original: str, diff_text: str) -> Optional[str]:
        """Heuristic search-and-replace for unified diffs when hunk headers are absent or shifted."""
        orig_lines = original.splitlines(keepends=True)
        diff_lines = diff_text.splitlines()

        rem_lines: list[str] = []
        add_lines: list[str] = []

        for line in diff_lines:
            if line.startswith("-") and not line.startswith("---"):
                rem_lines.append(line[1:].rstrip())
            elif line.startswith("+") and not line.startswith("+++"):
                add_lines.append(line[1:].rstrip())

        if not rem_lines and not add_lines:
            return None

        # Try to find rem_lines block in original
        orig_stripped = [l.rstrip() for l in orig_lines]
        for i in range(len(orig_stripped) - len(rem_lines) + 1):
            if orig_stripped[i : i + len(rem_lines)] == rem_lines:
                # Replace matching block with add_lines
                prefix = orig_lines[:i]
                suffix = orig_lines[i + len(rem_lines) :]
                new_block = [f"{l}\n" for l in add_lines]
                candidate = "".join(prefix + new_block + suffix)
                try:
                    self._parse_source(candidate)
                    return candidate
                except Exception:
                    pass

        return None

    def _apply_diff_text(self, original: str, diff_text: str) -> Optional[str]:
        """Simple in-memory unified diff applier for single test snippets."""
        orig_lines = original.splitlines(keepends=True)
        hunk_pattern = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
        result_lines: list[str] = []
        diff_lines = diff_text.splitlines(keepends=True)

        hunk_active = False
        target_orig_idx = 0

        for line in diff_lines:
            m = hunk_pattern.match(line)
            if m:
                hunk_active = True
                orig_start = int(m.group(1)) - 1
                while target_orig_idx < orig_start and target_orig_idx < len(orig_lines):
                    result_lines.append(orig_lines[target_orig_idx])
                    target_orig_idx += 1
                continue

            if hunk_active:
                if line.startswith("+") and not line.startswith("+++"):
                    result_lines.append(line[1:])
                elif line.startswith("-") and not line.startswith("---"):
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

    def _is_tautological_assert(self, test_node: ast.AST) -> tuple[bool, str]:
        """Detects whether an assertion condition is tautological.

        Covers:
        1. Literal constants: assert True, assert 1, assert "ok"
        2. Boolean short-circuit: assert x or True, assert True or x
        3. Law of excluded middle: assert x or not x, assert not x or x
        4. Self-comparison: assert x == x, assert x is x, assert x <= x, assert x >= x, assert x in [x]
        """
        # 1. Literal truthy constants: assert True, assert 1, assert "ok"
        if isinstance(test_node, ast.Constant):
            if bool(test_node.value) is True:
                return True, f"Literal truthy constant '{test_node.value}' in assertion"

        # 2 & 3. Boolean operators (Or)
        if isinstance(test_node, ast.BoolOp) and isinstance(test_node.op, ast.Or):
            # Short-circuit tautology with truthy constant: assert x or True, assert True or x
            for val in test_node.values:
                if isinstance(val, ast.Constant) and bool(val.value) is True:
                    return True, f"Boolean short-circuit tautology with truthy constant '{val.value}'"

            # Law-of-excluded-middle tautology: assert x or not x, assert not x or x
            vals = test_node.values
            for i in range(len(vals)):
                for j in range(len(vals)):
                    if i == j:
                        continue
                    v_i = vals[i]
                    v_j = vals[j]
                    # Check if v_j is Not(v_i)
                    if isinstance(v_j, ast.UnaryOp) and isinstance(v_j.op, ast.Not):
                        if ast.dump(v_i) == ast.dump(v_j.operand):
                            return True, "Law-of-excluded-middle tautology (x or not x)"
                    # Check if v_i is Not(v_j)
                    if isinstance(v_i, ast.UnaryOp) and isinstance(v_i.op, ast.Not):
                        if ast.dump(v_i.operand) == ast.dump(v_j):
                            return True, "Law-of-excluded-middle tautology (not x or x)"

        # 4. Comparisons: assert x == x, assert x is x, assert x <= x, assert x >= x, assert x in [x]
        if isinstance(test_node, ast.Compare):
            left_dump = ast.dump(test_node.left)
            for op, comp in zip(test_node.ops, test_node.comparators):
                comp_dump = ast.dump(comp)
                # Self-comparison equality or identity
                if isinstance(op, (ast.Eq, ast.Is, ast.LtE, ast.GtE)):
                    if left_dump == comp_dump:
                        return True, f"Self-comparison tautology: {type(op).__name__} on identical expression"
                # Self-membership: assert x in [x], assert x in (x,)
                if isinstance(op, ast.In):
                    if isinstance(comp, (ast.List, ast.Tuple, ast.Set)):
                        if any(ast.dump(elt) == left_dump for elt in comp.elts):
                            return True, "Self-membership tautology (assert x in [x])"

        return False, ""

    def _detect_dead_conditional_assertions(self, tree: ast.AST) -> list[str]:
        """Detects assertions inside dead conditional branches (e.g. if False: assert ...)."""
        dead_reasons: list[str] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                is_dead = False
                desc = ""

                # Falsy constant: if False:, if 0:, if None:, if "":
                if isinstance(node.test, ast.Constant):
                    if not bool(node.test.value):
                        is_dead = True
                        desc = repr(node.test.value)
                elif isinstance(node.test, ast.Name) and node.test.id in ("False", "None"):
                    is_dead = True
                    desc = node.test.id
                # Constant comparison evaluating to False: if 1 == 2:, if 0 == 1:
                elif isinstance(node.test, ast.Compare):
                    if (
                        isinstance(node.test.left, ast.Constant)
                        and len(node.test.comparators) == 1
                        and isinstance(node.test.comparators[0], ast.Constant)
                    ):
                        l_val = node.test.left.value
                        r_val = node.test.comparators[0].value
                        op = node.test.ops[0]
                        res = None
                        try:
                            if isinstance(op, ast.Eq):
                                res = l_val == r_val
                            elif isinstance(op, ast.NotEq):
                                res = l_val != r_val
                            elif isinstance(op, ast.Lt):
                                res = l_val < r_val
                            elif isinstance(op, ast.LtE):
                                res = l_val <= r_val
                            elif isinstance(op, ast.Gt):
                                res = l_val > r_val
                            elif isinstance(op, ast.GtE):
                                res = l_val >= r_val
                            elif isinstance(op, ast.Is):
                                res = l_val is r_val
                            elif isinstance(op, ast.IsNot):
                                res = l_val is not r_val
                        except Exception:
                            pass
                        if res is False:
                            is_dead = True
                            desc = f"{l_val} {type(op).__name__} {r_val}"

                if is_dead:
                    has_assert = any(
                        isinstance(child, ast.Assert)
                        or (
                            isinstance(child, ast.Call)
                            and isinstance(child.func, ast.Attribute)
                            and child.func.attr.startswith("assert")
                        )
                        for child in ast.walk(node)
                    )
                    if has_assert:
                        dead_reasons.append(f"Dead conditional assertion under 'if {desc}:'")

        return dead_reasons

    def _detect_early_return_before_assert(
        self, orig_ast: ast.AST, patch_ast: ast.AST
    ) -> list[str]:
        """Detects if patched test_* function added an early return before assertions."""
        # Count existing returns in original test functions
        orig_test_returns: dict[str, int] = {}
        for node in ast.walk(orig_ast):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
                orig_test_returns[node.name] = len(returns)

        early_return_reasons: list[str] = []
        for node in ast.walk(patch_ast):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                orig_count = orig_test_returns.get(node.name, 0)
                returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
                asserts = [
                    n
                    for n in ast.walk(node)
                    if isinstance(n, ast.Assert)
                    or (
                        isinstance(n, ast.Call)
                        and isinstance(n.func, ast.Attribute)
                        and n.func.attr.startswith("assert")
                    )
                ]

                if returns and asserts and len(returns) > orig_count:
                    min_assert_line = min(getattr(a, "lineno", 0) for a in asserts)
                    for r in returns:
                        r_line = getattr(r, "lineno", 0)
                        if r_line < min_assert_line:
                            early_return_reasons.append(
                                f"early return statement added at line {r_line} before assertion at line {min_assert_line} in {node.name}"
                            )
                            break

        return early_return_reasons

    def _detect_exception_swallowing(
        self, orig_ast: ast.AST, patch_ast: ast.AST
    ) -> list[str]:
        """Detects if patched code introduces try/except or contextlib.suppress swallowing assertions."""
        orig_try_dumps = {ast.dump(n) for n in ast.walk(orig_ast) if isinstance(n, (ast.Try, ast.With))}
        swallow_targets = {"Exception", "BaseException", "AssertionError"}
        reasons: list[str] = []

        for node in ast.walk(patch_ast):
            if ast.dump(node) in orig_try_dumps:
                continue

            # 1. try/except block
            if isinstance(node, ast.Try):
                has_assert = any(
                    isinstance(child, ast.Assert)
                    or (
                        isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Attribute)
                        and child.func.attr.startswith("assert")
                    )
                    for child in node.body
                )
                for handler in node.handlers:
                    is_swallow = False
                    if handler.type is None:
                        is_swallow = True
                    elif isinstance(handler.type, ast.Name) and handler.type.id in swallow_targets:
                        is_swallow = True
                    elif isinstance(handler.type, ast.Attribute) and handler.type.attr in swallow_targets:
                        is_swallow = True
                    elif isinstance(handler.type, ast.Tuple):
                        for elt in handler.type.elts:
                            if isinstance(elt, ast.Name) and elt.id in swallow_targets:
                                is_swallow = True
                            elif isinstance(elt, ast.Attribute) and elt.attr in swallow_targets:
                                is_swallow = True

                    if is_swallow:
                        has_raise = any(isinstance(stmt, ast.Raise) for stmt in ast.walk(handler))
                        if not has_raise:
                            reasons.append("exception-swallowing try/except block wrapping assertion")
                            break

            # 2. with contextlib.suppress(...)
            elif isinstance(node, ast.With):
                for item in node.items:
                    expr = item.context_expr
                    if isinstance(expr, ast.Call):
                        name = self._get_call_name(expr)
                        if name in ("contextlib.suppress", "suppress"):
                            reasons.append("with contextlib.suppress(...) block suppressing test assertions")

        return reasons

    def _detect_suppression_decorators(
        self, orig_ast: ast.AST, patch_ast: ast.AST
    ) -> list[str]:
        """Detects if patched code adds skip, xfail, flaky, rerun, or retry decorators or calls."""
        orig_dec_names = set()
        for node in ast.walk(orig_ast):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                for dec in node.decorator_list:
                    name = self._get_decorator_name(dec)
                    if name:
                        orig_dec_names.add(name)

        reasons: list[str] = []
        blocked_keywords = ("skip", "xfail", "flaky", "rerun", "retry")

        for node in ast.walk(patch_ast):
            # Check decorators
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                for dec in node.decorator_list:
                    name = self._get_decorator_name(dec)
                    if name and name not in orig_dec_names:
                        name_lower = name.lower()
                        if any(kw in name_lower for kw in blocked_keywords):
                            reasons.append(f"test suppression / rerun decorator '@{name}' added")

            # Check calls to pytest.skip(), pytest.xfail(), etc.
            elif isinstance(node, ast.Call):
                name = self._get_call_name(node)
                if name in ("pytest.skip", "pytest.xfail", "unittest.skipTest", "skip"):
                    reasons.append(f"direct test suppression call '{name}()' added")

        return reasons

    def _detect_weakened_assertions(
        self, orig_ast: ast.AST, patch_ast: ast.AST
    ) -> list[str]:
        """Detects if strict equality (ast.Eq) was replaced with weakened operators.

        Weakened operators:
        - ast.IsNot with None (e.g. assert x is not None)
        - ast.NotEq (e.g. assert x != 0)
        - ast.GtE / ast.LtE inequalities (e.g. assert x >= 0, assert x <= 100)
        - bool(x) call (e.g. assert bool(x))
        """
        orig_assert_dumps = {ast.dump(n.test) for n in ast.walk(orig_ast) if isinstance(n, ast.Assert)}
        reasons: list[str] = []

        for node in ast.walk(patch_ast):
            if isinstance(node, ast.Assert):
                test = node.test
                # If this assertion already existed in original code, it was not weakened by the patch
                if ast.dump(test) in orig_assert_dumps:
                    continue

                is_weakened = False
                desc = ""

                # Compare operators
                if isinstance(test, ast.Compare):
                    for op, comp in zip(test.ops, test.comparators):
                        # assert x is not None
                        if isinstance(op, ast.IsNot) and isinstance(comp, ast.Constant) and comp.value is None:
                            is_weakened = True
                            desc = "strict equality replaced with 'is not None'"
                        # assert x != ...
                        elif isinstance(op, ast.NotEq):
                            is_weakened = True
                            desc = "strict equality replaced with '!='"
                        # assert x >= ... or assert x <= ...
                        elif isinstance(op, (ast.GtE, ast.LtE)):
                            is_weakened = True
                            desc = f"strict equality replaced with inequality '{type(op).__name__}'"

                # bool(x) call
                elif isinstance(test, ast.Call) and isinstance(test.func, ast.Name) and test.func.id == "bool":
                    is_weakened = True
                    desc = "strict equality replaced with 'bool(x)'"

                if is_weakened:
                    reasons.append(f"Weakened assertion operator: {desc}")

        return reasons

    def _analyze_assertions(
        self, tree: ast.AST
    ) -> tuple[int, int, int, list[str]]:
        """Counts (total_assertions, meaningful_assertions, tautological_assertions, tautological_reasons)."""
        total = 0
        meaningful = 0
        tautological = 0
        taut_reasons: list[str] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                total += 1
                is_taut, reason = self._is_tautological_assert(node.test)
                if is_taut:
                    tautological += 1
                    taut_reasons.append(reason)
                else:
                    meaningful += 1

            elif isinstance(node, ast.Call):
                func = node.func
                # self.assert* calls
                if isinstance(func, ast.Attribute) and func.attr.startswith("assert"):
                    total += 1
                    is_taut = False
                    reason = ""
                    if func.attr in ("assertTrue", "assertFalse") and node.args:
                        is_taut, reason = self._is_tautological_assert(node.args[0])
                    elif func.attr == "assertEqual" and len(node.args) >= 2:
                        cmp_node = ast.Compare(
                            left=node.args[0],
                            ops=[ast.Eq()],
                            comparators=[node.args[1]],
                        )
                        is_taut, reason = self._is_tautological_assert(cmp_node)

                    if is_taut:
                        tautological += 1
                        taut_reasons.append(reason)
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
                        if (
                            expr.func.attr == "raises"
                            and isinstance(expr.func.value, ast.Name)
                            and expr.func.value.id == "pytest"
                        ):
                            total += 1
                            meaningful += 1

        return total, meaningful, tautological, taut_reasons

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
            "wait_for_drain",
            "wait",
            "join",
            "acquire",
            "release",
            "notify",
            "notify_all",
            "set",
            "reset_instance",
            "monotonic",
            "perf_counter",
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
            "Random",
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
                    if attr in sync_method_names:
                        rec_name = self._get_decorator_name(node.func.value)
                        if rec_name:
                            sync_primitives.append(f"{rec_name}.{attr}")
                        else:
                            sync_primitives.append(attr)

                # Check instantiation: e.g. threading.Event(), Event(), random.Random()
                if call_name:
                    base_name = call_name.split(".")[-1]
                    if base_name in sync_type_names or call_name in ("freeze_time", "random.Random"):
                        sync_primitives.append(call_name)

            # Check context managers: with freeze_time(...), with lock:
            elif isinstance(node, ast.With):
                for item in node.items:
                    expr = item.context_expr
                    if isinstance(expr, ast.Call):
                        c_name = self._get_call_name(expr)
                        if c_name and ("freeze_time" in c_name or "lock" in c_name.lower()):
                            sync_primitives.append(c_name)

            # Check autouse fixture reset: @pytest.fixture(autouse=True)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    d_name = self._get_decorator_name(dec)
                    if d_name and "fixture" in d_name:
                        sync_primitives.append(d_name)

        # Deduplicate while preserving insertion order
        seen: set[str] = set()
        deduped_sync: list[str] = []
        for s in sync_primitives:
            if s not in seen:
                seen.add(s)
                deduped_sync.append(s)

        return sleep_durations, deduped_sync
