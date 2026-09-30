"""tool_calling: dispatch, observation, parallel read-only calls."""

from __future__ import annotations

import pytest

from omicsclaw.evals import NoError, ScriptedProvider, ScriptedTurn, ToolArgs, ToolCalled, tool_call

from ._checks import CountIs, SentContains, ToolResultContains, user_changes
from ._harness import check, seed


def _write_then_read():
    return ScriptedProvider(
        ScriptedTurn(tool_calls=(tool_call("write_file", {"path": "notes.md", "content": "Visium slide A1, 4992 spots"}),)),
        ScriptedTurn(tool_calls=(tool_call("read_file", {"path": "notes.md"}),)),
        ScriptedTurn(text="The note says slide A1 has 4992 spots."),
    )


def _edit_existing_file():
    return ScriptedProvider(
        ScriptedTurn(
            tool_calls=(
                tool_call(
                    "edit_file",
                    {"path": "params.yaml", "source_text": "resolution: 0.5", "target_text": "resolution: 1.0"},
                ),
            )
        ),
        ScriptedTurn(text="Resolution is now 1.0."),
    )


def _parallel_reads():
    return ScriptedProvider(
        ScriptedTurn(
            tool_calls=(
                tool_call("read_file", {"path": "a.txt"}),
                tool_call("read_file", {"path": "b.txt"}),
            )
        ),
        ScriptedTurn(text="Both files read."),
    )


CASES = [
    seed(
        "tool_calling/write_then_read",
        "Write a note about the slide, then read it back.",
        _write_then_read,
        ToolCalled("write_file"),
        ToolCalled("read_file"),
        ToolResultContains("read_file", "Visium"),
        NoError(),
    ),
    seed(
        "tool_calling/edit_existing_file",
        "Set the clustering resolution in params.yaml to 1.0.",
        _edit_existing_file,
        ToolArgs("edit_file", {"path": "params.yaml"}),
        ToolResultContains("edit_file", "params.yaml", is_error=False),
        CountIs("user file changes", lambda r: len(user_changes(r)), 1),
        CountIs("modified params.yaml", lambda r: user_changes(r).count(("modified", "params.yaml")), 1),
        CountIs(
            "resolution 1.0 on disk",
            lambda r: (r.workspace / "params.yaml").read_text().count("resolution: 1.0"),
            1,
        ),
        files={"params.yaml": "method: leiden\nresolution: 0.5\nn_neighbors: 15\n"},
    ),
    seed(
        "tool_calling/parallel_read_only_calls",
        "Read a.txt and b.txt.",
        _parallel_reads,
        ToolCalled("read_file", min_times=2),
        SentContains(("ALPHA-CONTENT", "BETA-CONTENT"), call=1),
        CountIs("engine_turns", lambda r: r.engine_turns, 2),
        files={"a.txt": "ALPHA-CONTENT\n", "b.txt": "BETA-CONTENT\n"},
    ),
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_case(case, tmp_path, eval_results):
    check(case, tmp_path, eval_results)
