"""
Unit & Integration Tests for /agent_and_ui/nemotron_agent.py.

Test Groups
-----------
A. Gotcha 1 - _extract_response_text: reasoning_content fallback when content is None/empty.
B. Gotcha 2 - _parse_fenced_json: fenced ```json extraction, raw JSON, object-scan fallback.
C. _build_git_diff: unified diff generation when model skips the diff field.
D. summarize_failure_logs: empty-list sentinel, dedup, offline fallback.
E. propose_experiments: valid ranked list, offline fallback structure.
F. generate_naive_quick_fix: sleep replacement patterns (tuple return type check).
G. diagnose_and_propose_fix: offline fallback returns tuple[str,str,str]; rejection-loop
   path builds context string; module-level proxy also returns tuple.
H. NemotronBridge alias: the module exports NemotronBridge as an alias for NemotronAgent.
I. Live smoke test: calls Nebius Token Factory with Nemotron-3_5-Lightning (skipped if no key).
"""

from __future__ import annotations

import os
import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Module under test
from agent_and_ui.nemotron_agent import (
    NemotronAgent,
    NemotronBridge,
    _build_git_diff,
    _extract_attr,
    _extract_response_text,
    _parse_fenced_json,
    diagnose_and_propose_fix,
    generate_naive_quick_fix,
    get_agent,
    propose_experiments,
    summarize_failure_logs,
)


# -------------------------------------------------------------------------------
# A. Gotcha 1 - _extract_response_text
# -------------------------------------------------------------------------------


class TestExtractResponseText:
    def test_content_present_returns_content(self):
        msg = MagicMock()
        msg.content = "  Hello World  "
        msg.reasoning_content = None
        result = _extract_response_text(msg)
        assert result == "Hello World"

    def test_content_none_falls_back_to_reasoning_content(self):
        msg = MagicMock()
        msg.content = None
        msg.reasoning_content = "The fix is: use threading.Event.wait()"
        result = _extract_response_text(msg)
        assert "threading.Event" in result

    def test_content_empty_string_falls_back_to_reasoning_content(self):
        msg = MagicMock()
        msg.content = "   "
        msg.reasoning_content = "Root cause is a timing race."
        result = _extract_response_text(msg)
        assert "Root cause" in result

    def test_reasoning_content_in_model_extra_dict(self):
        msg = MagicMock(spec=[])
        msg.content = ""
        msg.reasoning_content = None
        msg.model_extra = {"reasoning_content": "Exposed via model_extra dict"}
        result = _extract_response_text(msg)
        assert "Exposed" in result or "model_extra" in result

    def test_both_empty_returns_empty_string(self):
        msg = MagicMock()
        msg.content = None
        msg.reasoning_content = None
        del msg.model_extra
        result = _extract_response_text(msg)
        assert result == ""


# -------------------------------------------------------------------------------
# B. Gotcha 2 - _parse_fenced_json
# -------------------------------------------------------------------------------


class TestParseFencedJson:
    def test_fenced_json_block(self):
        raw = '```json\n{"key": "value", "number": 42}\n```'
        result = _parse_fenced_json(raw)
        assert result == {"key": "value", "number": 42}

    def test_fenced_block_without_json_label(self):
        raw = "```\n[1, 2, 3]\n```"
        result = _parse_fenced_json(raw)
        assert result == [1, 2, 3]

    def test_last_fenced_block_wins(self):
        raw = (
            'Let me think...\n'
            '```json\n{"wrong": true}\n```\n'
            'Here is the answer:\n'
            '```json\n{"correct": true}\n```'
        )
        result = _parse_fenced_json(raw)
        assert result == {"correct": True}

    def test_raw_json_object(self):
        raw = '{"fix_title": "My fix", "patched_code": "import os"}'
        result = _parse_fenced_json(raw)
        assert result["fix_title"] == "My fix"

    def test_raw_json_array(self):
        raw = '[{"perturbation": "cpu_heavy_load", "rank": 1}]'
        result = _parse_fenced_json(raw)
        assert isinstance(result, list) and result[0]["rank"] == 1

    def test_json_embedded_in_prose_object_scan(self):
        raw = 'Here is the result: {"answer": 99} -- end'
        result = _parse_fenced_json(raw)
        assert result == {"answer": 99}

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="Empty response"):
            _parse_fenced_json("")

    def test_unparseable_raises(self):
        with pytest.raises(ValueError, match="Could not parse JSON"):
            _parse_fenced_json("Just plain text with no JSON at all.")


# -------------------------------------------------------------------------------
# C. _build_git_diff
# -------------------------------------------------------------------------------


class TestBuildGitDiff:
    def test_diff_contains_minus_and_plus_lines(self):
        original = "def foo():\n    time.sleep(0.009)\n    assert True\n"
        patched = "def foo():\n    t.join()\n    assert True\n"
        diff = _build_git_diff(original, patched, filename="test_worker.py")
        assert "--- a/test_worker.py" in diff
        assert "+++ b/test_worker.py" in diff
        assert "-    time.sleep" in diff
        assert "+    t.join()" in diff

    def test_identical_files_produce_empty_diff(self):
        code = "print('hello')\n"
        diff = _build_git_diff(code, code)
        assert diff == ""


# -------------------------------------------------------------------------------
# D. summarize_failure_logs
# -------------------------------------------------------------------------------


class TestSummarizeFailureLogs:
    def _offline_agent(self):
        """Agent whose _call_with_fallback immediately raises RuntimeError (no network hit)."""
        agent = NemotronAgent(api_key="dummy")
        agent._call_with_fallback = MagicMock(
            side_effect=RuntimeError("simulated offline: no API")
        )
        return agent

    def test_empty_list_returns_sentinel(self):
        agent = self._offline_agent()
        result = agent.summarize_failure_logs([])
        assert "No failure logs" in result

    def test_whitespace_only_logs_returns_sentinel(self):
        agent = self._offline_agent()
        result = agent.summarize_failure_logs(["   ", "\n", ""])
        assert "No non-empty" in result

    def test_offline_fallback_returns_non_empty_string(self):
        """When API fails, offline fallback must return a non-empty summary string."""
        agent = self._offline_agent()
        logs = ["AssertionError: worker timed out"] * 5
        result = agent.summarize_failure_logs(logs)
        assert isinstance(result, str) and len(result) > 0

    def test_dedup_call_returns_string(self):
        """Dedup logic runs before API call; offline fallback returns count-based string."""
        agent = self._offline_agent()
        logs = ["AssertionError: timeout"] * 3 + ["RuntimeError: socket reset"]
        result = agent.summarize_failure_logs(logs)
        assert isinstance(result, str)

    def test_module_level_proxy_delegates_to_class(self):
        with patch("agent_and_ui.nemotron_agent._default_agent", None):
            with patch.object(NemotronAgent, "summarize_failure_logs", return_value="mocked summary") as m:
                result = summarize_failure_logs(["some log"])
                m.assert_called_once_with(["some log"])
                assert result == "mocked summary"


# -------------------------------------------------------------------------------
# E. propose_experiments
# -------------------------------------------------------------------------------


VALID_PERTURBATIONS = {
    "shuffle_order", "seed_change", "clock_shift",
    "network_cut", "cpu_half_cores", "cpu_heavy_load",
}


class TestProposeExperiments:
    def _offline_agent(self):
        """Agent whose _call_with_fallback immediately raises RuntimeError (no network hit)."""
        agent = NemotronAgent(api_key="dummy")
        agent._call_with_fallback = MagicMock(
            side_effect=RuntimeError("simulated offline: no API")
        )
        return agent

    def test_offline_fallback_returns_6_items(self):
        agent = self._offline_agent()
        result = agent.propose_experiments("def test(): pass", "worker timed out")
        assert isinstance(result, list) and len(result) == 6
        for item in result:
            assert item["perturbation"] in VALID_PERTURBATIONS
            assert isinstance(item["rank"], int)
            assert isinstance(item["hypothesis"], str) and len(item["hypothesis"]) > 10

    def test_offline_fallback_cpu_heavy_load_is_rank_1(self):
        agent = self._offline_agent()
        result = agent.propose_experiments("def test(): pass", "worker timed out")
        rank1 = next(r for r in result if r["rank"] == 1)
        assert rank1["perturbation"] == "cpu_heavy_load"

    def test_mocked_api_normalizes_valid_json(self):
        agent = NemotronAgent(api_key="dummy")
        api_response = (
            '```json\n'
            '[{"perturbation": "cpu_heavy_load", "rank": 1, "hypothesis": "CPU stress exposes race."},'
            ' {"perturbation": "clock_shift", "rank": 2, "hypothesis": "Wallclock assumption."}]\n'
            '```'
        )
        with patch.object(agent, "_call_with_fallback", return_value=(api_response, "test-model")):
            result = agent.propose_experiments("code", "summary")
        assert len(result) == 2
        assert result[0]["perturbation"] == "cpu_heavy_load"
        assert result[0]["rank"] == 1

    def test_mocked_api_filters_invalid_perturbation_names(self):
        agent = NemotronAgent(api_key="dummy")
        api_response = (
            '```json\n'
            '[{"perturbation": "not_a_real_perturbation", "rank": 1, "hypothesis": "Some hyp."}]\n'
            '```'
        )
        with patch.object(agent, "_call_with_fallback", return_value=(api_response, "test-model")):
            result = agent.propose_experiments("code", "summary")
        assert len(result) == 6  # falls back to deterministic list


# -------------------------------------------------------------------------------
# F. generate_naive_quick_fix
# -------------------------------------------------------------------------------


FLAKY_CODE_9MS = "import time\ndef test_worker():\n    time.sleep(0.009)\n    assert worker.done\n"
FLAKY_CODE_22MS = "import time\ndef test_worker():\n    time.sleep(0.022)\n    assert worker.done\n"
FLAKY_CODE_24MS = "import time\ndef test_worker():\n    time.sleep(0.024)\n    assert worker.done\n"
FLAKY_CODE_100MS = "import time\ndef test_worker():\n    time.sleep(0.100)\n    assert worker.done\n"
CLEAN_CODE = "def test_worker():\n    worker.join()\n    assert worker.done\n"


class TestGenerateNaiveQuickFix:
    def test_returns_three_string_tuple(self):
        agent = NemotronAgent(api_key="dummy")
        result = agent.generate_naive_quick_fix(FLAKY_CODE_9MS, "worker timed out")
        assert isinstance(result, tuple) and len(result) == 3
        title, diagnosis, patched = result
        assert all(isinstance(x, str) for x in (title, diagnosis, patched))

    def test_replaces_9ms_sleep(self):
        agent = NemotronAgent(api_key="dummy")
        _, _, patched = agent.generate_naive_quick_fix(FLAKY_CODE_9MS, "")
        assert "time.sleep(0.050)" in patched
        assert "time.sleep(0.009)" not in patched

    def test_replaces_22ms_sleep(self):
        agent = NemotronAgent(api_key="dummy")
        _, _, patched = agent.generate_naive_quick_fix(FLAKY_CODE_22MS, "")
        assert "time.sleep(0.050)" in patched
        assert "time.sleep(0.022)" not in patched

    def test_replaces_24ms_sleep(self):
        agent = NemotronAgent(api_key="dummy")
        _, _, patched = agent.generate_naive_quick_fix(FLAKY_CODE_24MS, "")
        assert "time.sleep(0.050)" in patched

    def test_replaces_generic_sleep_via_regex(self):
        agent = NemotronAgent(api_key="dummy")
        _, _, patched = agent.generate_naive_quick_fix(FLAKY_CODE_100MS, "")
        assert "time.sleep(0.050)" in patched

    def test_no_sleep_returns_code_unchanged(self):
        agent = NemotronAgent(api_key="dummy")
        _, _, patched = agent.generate_naive_quick_fix(CLEAN_CODE, "")
        assert patched == CLEAN_CODE

    def test_module_level_proxy_returns_tuple(self):
        with patch("agent_and_ui.nemotron_agent._default_agent", None):
            with patch.object(
                NemotronAgent, "generate_naive_quick_fix",
                return_value=("title", "diag", "code"),
            ):
                result = generate_naive_quick_fix("def test(): pass", "logs")
        assert result == ("title", "diag", "code")


# -------------------------------------------------------------------------------
# G. diagnose_and_propose_fix
# -------------------------------------------------------------------------------


def _make_batch(perturbation="baseline", failures=21, total_runs=300):
    return {
        "perturbation": perturbation,
        "total_runs": total_runs,
        "failures": failures,
        "failure_rate": round(failures / total_runs, 4),
        "ci_95_lower": 0.046,
        "ci_95_upper": 0.105,
    }


FLAKY_CODE = (
    "import time, threading\n"
    "def test_job():\n"
    "    worker = Worker()\n"
    "    t = threading.Thread(target=worker.run)\n"
    "    t.start()\n"
    "    time.sleep(0.022)\n"
    "    assert worker.is_completed\n"
    "    t.join()\n"
)


class TestDiagnoseAndProposeFix:
    def _stage1(self):
        return _make_batch("baseline", 21, 300)

    def _stage2(self):
        return [
            _make_batch("baseline", 3, 30),
            _make_batch("cpu_heavy_load", 28, 30),
        ]

    def test_returns_three_string_tuple_via_mocked_api(self):
        agent = NemotronAgent(api_key="dummy")
        api_response = (
            '```json\n'
            '{"fix_title": "Deterministic Fix", '
            '"root_cause_diagnosis": "Fixed sleep races CPU.", '
            '"patched_code": "def test(): worker.join(); assert worker.done", '
            '"git_diff_patch": ""}\n'
            '```'
        )
        with patch.object(agent, "_call_with_fallback", return_value=(api_response, "test-model")):
            result = agent.diagnose_and_propose_fix(
                test_code=FLAKY_CODE,
                stage1_baseline=self._stage1(),
                stage2_ledger=self._stage2(),
            )
        assert isinstance(result, tuple) and len(result) == 3
        title, diagnosis, patched = result
        assert "Deterministic Fix" in title
        assert "race" in diagnosis or "CPU" in diagnosis
        assert "worker.join" in patched or "worker.done" in patched

    def test_auto_generates_git_diff_when_not_provided(self):
        agent = NemotronAgent(api_key="dummy")
        fixed_code = FLAKY_CODE.replace("time.sleep(0.022)", "t.join()")
        api_response = (
            '```json\n'
            '{"fix_title": "Event Fix", '
            '"root_cause_diagnosis": "Race condition.", '
            '"patched_code": "' + fixed_code.replace('"', '\\"').replace('\n', '\\n') + '", '
            '"git_diff_patch": ""}\n'
            '```'
        )
        with patch.object(agent, "_call_with_fallback", return_value=(api_response, "test-model")):
            title, diagnosis, patched = agent.diagnose_and_propose_fix(
                test_code=FLAKY_CODE,
                stage1_baseline=self._stage1(),
                stage2_ledger=self._stage2(),
            )
        assert "t.join()" in patched

    def test_rejection_loop_evidence_in_prompt(self):
        agent = NemotronAgent(api_key="dummy")
        rejected_attempt = {
            "fix_title": "Naive Sleep Fix",
            "rejection_reason": "Failed under CPU_HEAVY_LOAD stress: 61/1000 runs.",
            "patched_code": "time.sleep(0.050)",
            "diff_patch": "",
        }
        captured: list[Any] = []

        def capture_call(primary_model, fallback_model, messages, **kwargs):
            captured.extend(messages)
            return (
                '```json\n{"fix_title":"Real Fix","root_cause_diagnosis":"event sync",'
                '"patched_code":"t.join()","git_diff_patch":""}\n```',
                primary_model,
            )

        with patch.object(agent, "_call_with_fallback", side_effect=capture_call):
            agent.diagnose_and_propose_fix(
                test_code=FLAKY_CODE,
                stage1_baseline=self._stage1(),
                stage2_ledger=self._stage2(),
                previous_rejected_attempts=[rejected_attempt],
            )

        full = " ".join(m.get("content", "") for m in captured)
        assert "Naive Sleep Fix" in full or "REJECTION" in full
        assert "CPU_HEAVY_LOAD" in full or "time.sleep" in full

    def test_module_level_proxy_returns_tuple(self):
        with patch("agent_and_ui.nemotron_agent._default_agent", None):
            with patch.object(
                NemotronAgent,
                "diagnose_and_propose_fix",
                return_value=("fix title", "root cause", "patched code"),
            ):
                result = diagnose_and_propose_fix(
                    test_code="def test(): pass",
                    stage1_baseline=_make_batch(),
                    stage2_ledger=[_make_batch("cpu_heavy_load", 28, 30)],
                )
        assert result == ("fix title", "root cause", "patched code")

    def test_non_dict_json_raises_value_error(self):
        agent = NemotronAgent(api_key="dummy")
        api_response = '```json\n[1, 2, 3]\n```'
        with patch.object(agent, "_call_with_fallback", return_value=(api_response, "test-model")):
            with pytest.raises(ValueError, match="Expected JSON object"):
                agent.diagnose_and_propose_fix(
                    test_code=FLAKY_CODE,
                    stage1_baseline=self._stage1(),
                    stage2_ledger=self._stage2(),
                )


# -------------------------------------------------------------------------------
# H. NemotronBridge alias
# -------------------------------------------------------------------------------


class TestNemotronBridgeAlias:
    def test_bridge_alias_is_nemotron_agent(self):
        assert NemotronBridge is NemotronAgent

    def test_bridge_alias_is_instantiable_with_expected_methods(self):
        bridge = NemotronBridge(api_key="dummy")
        assert hasattr(bridge, "summarize_failure_logs")
        assert hasattr(bridge, "diagnose_and_propose_fix")
        assert hasattr(bridge, "generate_naive_quick_fix")
        assert hasattr(bridge, "propose_experiments")


# -------------------------------------------------------------------------------
# I. Live Smoke Test - Nebius Token Factory
# -------------------------------------------------------------------------------


NEBIUS_API_KEY = os.getenv("NEBIUS_API_KEY", "")

live_test = pytest.mark.skipif(
    not NEBIUS_API_KEY or NEBIUS_API_KEY.startswith("YOUR_"),
    reason="NEBIUS_API_KEY not set - skipping live smoke test",
)


@live_test
def test_live_summarize_failure_logs_lightning():
    """
    Live smoke test: calls nvidia/Nemotron-3_5-Lightning via Nebius Token Factory.
    Verifies the API is reachable and the response is a non-empty string.
    """
    agent = NemotronAgent()
    logs = [
        "AssertionError: Expected background job to finish, but was still running (63412/65000 items processed)",
        "AssertionError: Expected background job to finish, but was still running (61890/65000 items processed)",
    ]
    result = agent.summarize_failure_logs(logs)
    assert isinstance(result, str), "Expected a string from summarize_failure_logs"
    assert len(result) > 20, f"Response too short (len={len(result)}): {result!r}"
    print(f"\n[live smoke] summarize_failure_logs ({len(result)} chars):\n{result[:300]}")

