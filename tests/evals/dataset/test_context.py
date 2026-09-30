"""context: a tool error is an observation; history carries across exchanges."""

from __future__ import annotations

import pytest

from omicsclaw.engine import StopReason
from omicsclaw.evals import NoError, OutputContains, ScriptedProvider, ScriptedTurn, tool_call

from ._checks import CountIs, SentContains, StopReasonIs, ToolResultContains
from ._harness import check, seed

FIRST_QUESTION = "Which normalization did the QC-ALPHA run use?"
FIRST_ANSWER = "It used log1p after total-count scaling (ANSWER-ONE)."
SECOND_ANSWER = "Then the next step is HVG selection (ANSWER-TWO)."


def _tool_error():
    return ScriptedProvider(
        ScriptedTurn(tool_calls=(tool_call("read_file", {"path": "missing.h5ad"}),)),
        ScriptedTurn(text="That file does not exist; please upload it."),
    )


def _two_exchanges():
    return ScriptedProvider(ScriptedTurn(text=FIRST_ANSWER), ScriptedTurn(text=SECOND_ANSWER))


def _system_messages(result, call):
    return sum(1 for message in result.provider_calls[call].messages if message.role == "system")


CASES = [
    seed(
        "context/tool_error_is_observation",
        "Open missing.h5ad.",
        _tool_error,
        ToolResultContains("read_file", "missing.h5ad", is_error=True),
        NoError(),
        StopReasonIs(StopReason.CONVERGED),
        CountIs("engine_turns", lambda r: r.engine_turns, 2),
    ),
    seed(
        "context/history_carried_across_exchanges",
        FIRST_QUESTION,
        _two_exchanges,
        SentContains((FIRST_QUESTION, FIRST_ANSWER), call=1),
        CountIs("system messages on call 1", lambda r: _system_messages(r, 1), 1),
        OutputContains("ANSWER-TWO"),
        followups=("And what comes next?",),
    ),
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_case(case, tmp_path, eval_results):
    check(case, tmp_path, eval_results)
