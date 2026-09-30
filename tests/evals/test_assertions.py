"""The twelve assertions, one holding and one failing example each."""

from __future__ import annotations

from pathlib import Path

import pytest

from omicsclaw.evals import (
    ApprovalRecord,
    Error,
    FsChange,
    MaxToolCalls,
    MaxTurns,
    NoError,
    NoWriteOutside,
    OutputContains,
    OutputExcludes,
    PermissionRequested,
    SkillInvoked,
    SkillRun,
    ToolArgs,
    ToolCalled,
    ToolNotCalled,
    tool_call,
)
from omicsclaw.evals.assertions import is_subset
from omicsclaw.provider import ProviderError

from ._support import make_result

WS = Path("/tmp/eval-ws")


def _passes(assertion, **fields) -> bool:
    return assertion.check(make_result(**fields)) is None


def test_tool_called_counts_dispatched_calls():
    calls = ("read_file", "read_file", "bash")
    assert _passes(ToolCalled("read_file", min_times=2), tool_calls_executed=calls)
    assert not _passes(ToolCalled("read_file", min_times=3), tool_calls_executed=calls)


def test_tool_not_called():
    assert _passes(ToolNotCalled("bash"), tool_calls_executed=("read_file",))
    assert not _passes(ToolNotCalled("bash"), tool_calls_executed=("bash",))


def test_output_contains_and_excludes():
    assert _passes(OutputContains("Leiden"), final_output="ran Leiden at 1.0")
    assert not _passes(OutputContains("Louvain"), final_output="ran Leiden")
    assert _passes(OutputExcludes("Louvain"), final_output="ran Leiden")
    assert not _passes(OutputExcludes("Leiden"), final_output="ran Leiden")


def test_no_error_and_error():
    failure = ProviderError("bad request", status_code=400)
    assert _passes(NoError())
    assert not _passes(NoError(), run_error=failure)
    assert _passes(Error(), run_error=failure)
    assert _passes(Error(ProviderError), run_error=failure)
    assert not _passes(Error(TimeoutError), run_error=failure)
    assert not _passes(Error())


def test_the_two_efficiency_checks_are_soft():
    over_turns = MaxTurns(2).check(make_result(turn_count=3))
    over_calls = MaxToolCalls(1).check(make_result(tool_calls_executed=("a", "b")))
    assert over_turns is not None and over_turns.is_soft
    assert over_calls is not None and over_calls.is_soft
    assert _passes(MaxTurns(3), turn_count=3)
    assert _passes(MaxToolCalls(2), tool_calls_executed=("a", "b"))


def test_skill_invoked_with_and_without_domain():
    runs = (SkillRun("sc-clustering", "singlecell", "python ...", stubbed=True),)
    assert _passes(SkillInvoked("sc-clustering"), skill_runs=runs)
    assert _passes(SkillInvoked("sc-clustering", domain="singlecell"), skill_runs=runs)
    assert not _passes(SkillInvoked("sc-clustering", domain="spatial"), skill_runs=runs)
    assert not _passes(SkillInvoked("sc-de"), skill_runs=runs)


def test_tool_args_matches_a_json_subset():
    calls = (
        tool_call("edit_file", {"path": "params.yaml", "old": "0.5", "new": "1.0"}),
        tool_call("read_file", {"path": "x"}),
    )
    assert _passes(ToolArgs("edit_file", {"path": "params.yaml"}), tool_calls=calls)
    assert not _passes(ToolArgs("edit_file", {"path": "other.yaml"}), tool_calls=calls)
    assert not _passes(ToolArgs("bash", {}), tool_calls=calls)


def test_is_subset_recurses_into_dicts_and_lists():
    value = {"a": {"b": 1, "c": [1, {"d": 2, "e": 3}]}, "f": "g"}
    assert is_subset({"a": {"c": [1, {"d": 2}]}}, value)
    assert not is_subset({"a": {"c": [1]}}, value)
    assert not is_subset({"a": {"c": [2, {"d": 2}]}}, value)
    assert not is_subset({"a": {"b": 2}}, value)
    assert not is_subset({"z": 1}, value)
    assert is_subset({}, value)


def test_permission_requested_with_the_answer():
    asked = (ApprovalRecord("bash", "high", "rm -rf", approved=False, scripted=True),)
    assert _passes(PermissionRequested("bash"), approvals=asked)
    assert _passes(PermissionRequested("bash", approved=False), approvals=asked)
    assert not _passes(PermissionRequested("bash", approved=True), approvals=asked)
    assert not _passes(PermissionRequested("write_file"), approvals=asked)


def test_no_write_outside_the_workspace_or_a_subdirectory():
    inside = (FsChange(str(WS / "notes.md"), "created"),)
    escaped = (FsChange(str(WS.parent / "outside" / "leak.txt"), "created"),)
    state = (FsChange(str(WS / ".omicsclaw" / "memory.db"), "modified"),)
    assert _passes(NoWriteOutside(), fs_changes=inside, workspace=WS)
    assert not _passes(NoWriteOutside(), fs_changes=escaped, workspace=WS)
    assert _passes(NoWriteOutside("workspace/.omicsclaw"), fs_changes=state, workspace=WS)
    assert not _passes(NoWriteOutside("workspace/.omicsclaw"), fs_changes=inside, workspace=WS)


def test_no_write_outside_refuses_a_root_outside_the_workspace():
    with pytest.raises(ValueError):
        NoWriteOutside("elsewhere").check(make_result())


def test_every_assertion_has_a_name():
    for assertion in (
        ToolCalled("a"), ToolNotCalled("a"), OutputContains("a"), OutputExcludes("a"),
        NoError(), Error(), MaxTurns(1), MaxToolCalls(1), SkillInvoked("a"),
        ToolArgs("a", {}), PermissionRequested("a"), NoWriteOutside(),
    ):
        assert assertion.name
