"""error_handling: provider errors, retries, the turn ceiling, an unknown tool."""

from __future__ import annotations

import pytest

from omicsclaw.engine import StopReason
from omicsclaw.evals import Error, NoError, OutputContains, ScriptedProvider, ScriptedTurn, tool_call
from omicsclaw.provider import ProviderError

from ._checks import CountIs, StopReasonIs, ToolResultContains
from ._harness import check, seed


def _bad_request():
    return ScriptedProvider(
        ScriptedTurn(err=ProviderError("invalid request", provider="scripted", status_code=400)),
        ScriptedTurn(text="should never be reached"),
    )


def _transient():
    return ScriptedProvider(
        ScriptedTurn(err=ProviderError("overloaded", provider="scripted", status_code=503)),
        ScriptedTurn(text="Recovered after one retry."),
    )


def _keeps_reading():
    return ScriptedProvider(
        *(ScriptedTurn(tool_calls=(tool_call("read_file", {"path": "a.txt"}),)) for _ in range(6)),
    )


def _unknown_tool():
    return ScriptedProvider(
        ScriptedTurn(tool_calls=(tool_call("no_such_tool", {"x": 1}),)),
        ScriptedTurn(text="That tool does not exist; I used none."),
    )


CASES = [
    seed(
        "error_handling/provider_error_fails_exchange",
        "Summarize the run.",
        _bad_request,
        Error(ProviderError),
        CountIs("turn_count", lambda r: r.turn_count, 1),
    ),
    seed(
        "error_handling/transient_error_retried",
        "Summarize the run.",
        _transient,
        NoError(),
        OutputContains("Recovered after one retry."),
        CountIs("turn_count", lambda r: r.turn_count, 2),
        CountIs("engine_turns", lambda r: r.engine_turns, 1),
    ),
    seed(
        "error_handling/max_turns_ceiling",
        "Keep reading a.txt.",
        _keeps_reading,
        StopReasonIs(StopReason.MAX_TURNS),
        NoError(),
        CountIs("turn_count", lambda r: r.turn_count, 3),
        CountIs("read_file calls kept in the trajectory", lambda r: r.tool_calls_executed.count("read_file"), 3),
        max_turns=3,
        files={"a.txt": "alpha\n"},
    ),
    seed(
        "error_handling/unknown_tool_is_observation",
        "Use the special tool.",
        _unknown_tool,
        ToolResultContains("no_such_tool", "read_file", is_error=True),
        NoError(),
        StopReasonIs(StopReason.CONVERGED),
        CountIs("approvals", lambda r: len(r.approvals), 0),
        CountIs("turn_count", lambda r: r.turn_count, 2),
    ),
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_case(case, tmp_path, eval_results):
    check(case, tmp_path, eval_results)
