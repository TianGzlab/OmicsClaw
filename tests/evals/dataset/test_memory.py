"""memory: memory_write and memory_search; the précis in the next exchange's prompt."""

from __future__ import annotations

import pytest

from omicsclaw.evals import NoError, ScriptedProvider, ScriptedTurn, ToolArgs, tool_call

from ._checks import SentContains, ToolResultContains
from ._harness import check, seed

TITLE = "Leiden resolution preference"
CONTENT = "For PBMC data the user wants Leiden clustering at resolution 1.0."


def _add():
    return tool_call(
        "memory_write",
        {"action": "add", "title": TITLE, "content": CONTENT, "category": "preference", "importance": 8},
    )


def _write_then_search():
    return ScriptedProvider(
        ScriptedTurn(tool_calls=(_add(),)),
        ScriptedTurn(tool_calls=(tool_call("memory_search", {"query": "Leiden resolution"}),)),
        ScriptedTurn(text="Saved and found your preference."),
    )


def _precis():
    return ScriptedProvider(
        ScriptedTurn(tool_calls=(_add(),)),
        ScriptedTurn(text="I will remember that."),
        ScriptedTurn(text="Using resolution 1.0 as you prefer."),
    )


CASES = [
    seed(
        "memory/write_then_search",
        "Remember that I like Leiden at resolution 1.0 for PBMC.",
        _write_then_search,
        ToolArgs("memory_write", {"action": "add"}),
        ToolResultContains("memory_search", TITLE),
        NoError(),
    ),
    seed(
        "memory/precis_reaches_next_exchange",
        "Remember that I like Leiden at resolution 1.0 for PBMC.",
        _precis,
        SentContains(TITLE, call=2, role="system"),
        SentContains("## Long-term memory", call=2, role="system"),
        NoError(),
        followups=("Cluster my PBMC data.",),
    ),
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_case(case, tmp_path, eval_results):
    check(case, tmp_path, eval_results)
