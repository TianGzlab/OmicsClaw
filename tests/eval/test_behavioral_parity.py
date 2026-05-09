"""Real-LLM behavioral-parity test suite (``@pytest.mark.eval``).

Each EvalCase is parametrized into one async test that invokes the
``real_llm_runner`` fixture with the case's query, applies any populated
invariants, and writes the captured ``LLMRoundResult`` + invariant
outcomes to ``tests/eval/results/<UTC-timestamp>/<case_id>.json``.

Priority semantics:
- ``must`` failure → ``pytest.fail`` (build red, blocks merge of
  follow-on prompt changes until investigated).
- ``should`` failure → ``warnings.warn(UserWarning)`` (recorded in the
  per-case JSON + the markdown report; doesn't block CI).

Excluded from default ``pytest`` runs via ``addopts = '-m "not eval"'``.
Run explicitly with ``pytest -m eval`` after exporting ``LLM_API_KEY``.
"""

from __future__ import annotations

import dataclasses
import json
import os
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from tests.eval.assertions import (
    AssertResult,
    assert_calls_tools,
    assert_response_mentions,
    assert_routes_to_skill,
)
from tests.eval.conftest import LLMRoundResult
from tests.eval.invariants import EVAL_CASES, EvalCase

_RESULTS_DIR = Path(__file__).parent / "results"


@pytest.fixture(scope="session")
def eval_run_dir() -> Path:
    """Per-pytest-session output dir under ``tests/eval/results/<ts>/``.

    A single ``pytest -m eval`` invocation produces one timestamped dir
    so all 18 case artifacts share the run.
    """
    timestamp = os.environ.get("EVAL_RUN_TIMESTAMP")
    if not timestamp:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
        os.environ["EVAL_RUN_TIMESTAMP"] = timestamp
    run_dir = _RESULTS_DIR / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _serialize_result(
    case: EvalCase,
    result: LLMRoundResult,
    outcomes: list[tuple[str, AssertResult]],
) -> dict[str, Any]:
    return {
        "case": dataclasses.asdict(case),
        "model": result.model,
        "response_text": result.response_text,
        "tool_calls": [
            {"name": tc.name, "arguments": tc.arguments} for tc in result.tool_calls
        ],
        "invariant_outcomes": [
            {
                "name": name,
                "passed": outcome.passed,
                "reasons": list(outcome.reasons),
            }
            for name, outcome in outcomes
        ],
        "passed_overall": all(o.passed for _, o in outcomes),
    }


def _run_invariants(case: EvalCase, result: LLMRoundResult) -> list[tuple[str, AssertResult]]:
    """Apply every populated invariant to the captured round."""
    outcomes: list[tuple[str, AssertResult]] = []

    if case.expected_skill:
        outcomes.append(
            ("routes_to_skill", assert_routes_to_skill(result, case.expected_skill))
        )

    if case.must_call_tools or case.must_not_call_tools:
        outcomes.append(
            (
                "calls_tools",
                assert_calls_tools(
                    result,
                    must_call=case.must_call_tools,
                    must_not_call=case.must_not_call_tools,
                ),
            )
        )

    if case.must_mention or case.must_not_mention:
        outcomes.append(
            (
                "response_mentions",
                assert_response_mentions(
                    result,
                    must_mention=case.must_mention,
                    must_not_mention=case.must_not_mention,
                ),
            )
        )

    return outcomes


@pytest.mark.eval
@pytest.mark.asyncio
@pytest.mark.parametrize("case", EVAL_CASES, ids=lambda c: c.id)
async def test_behavioral_parity(case: EvalCase, real_llm_runner, eval_run_dir: Path) -> None:
    """Run the case through the real LLM and apply its invariants.

    The runner is async; this test awaits a single LLM round, then
    walks the populated invariant set. Per-case JSON written before
    any failure is raised so ``tests/eval/results/`` always reflects
    every captured run, even when must-failures abort the test.
    """
    result = await real_llm_runner(case.query)
    outcomes = _run_invariants(case, result)
    payload = _serialize_result(case, result, outcomes)

    artifact_path = eval_run_dir / f"{case.id}.json"
    artifact_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    failed = [(name, o) for name, o in outcomes if not o.passed]
    if not failed:
        return

    summary = "\n".join(
        f"  - {name}: {'; '.join(o.reasons)}" for name, o in failed
    )
    if case.priority == "must":
        pytest.fail(
            f"\nMUST-priority case {case.id!r} failed {len(failed)} invariant(s):\n"
            f"{summary}\n"
            f"  artifact: {artifact_path}"
        )
    else:
        warnings.warn(
            f"\nSHOULD-priority case {case.id!r} failed {len(failed)} invariant(s):\n"
            f"{summary}\n"
            f"  artifact: {artifact_path}",
            UserWarning,
            stacklevel=2,
        )
