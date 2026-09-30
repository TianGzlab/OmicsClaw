"""Helpers shared by the eval package's unit tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from omicsclaw.evals import Case, Result, ScriptedProvider


def make_case(case_id: str = "tool_calling/sample", **overrides: Any) -> Case:
    """A case with no assertions, for tests that only need its identity."""
    fields: dict[str, Any] = {
        "id": case_id,
        "category": case_id.split("/", 1)[0],
        "prompt": "hello",
        "provider": ScriptedProvider,
        "assertions": (),
    }
    fields.update(overrides)
    return Case(**fields)


def make_result(**overrides: Any) -> Result:
    """A passing, empty result; keyword arguments replace fields."""
    fields: dict[str, Any] = {
        "case": make_case(),
        "passed": True,
        "turn_count": 1,
        "engine_turns": 1,
        "stop_reason": None,
        "tool_calls_executed": (),
        "tool_calls": (),
        "tool_results": (),
        "final_output": "",
        "run_error": None,
        "failures": (),
        "warnings": (),
        "duration_s": 0.0,
        "provider_calls": (),
        "side_calls": (),
        "skill_runs": (),
        "approvals": (),
        "fs_changes": (),
        "compactions": (),
        "workspace": Path("/tmp/eval-ws"),
    }
    fields.update(overrides)
    return Result(**fields)
