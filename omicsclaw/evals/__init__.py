"""Scripted, hermetic, deterministic agent evals.

A :class:`Case` scripts the model's replies with a
:class:`ScriptedProvider`, and :func:`run_case` runs it through the
production assembly (:func:`~omicsclaw.entry.build_app` with
``provider=``) and a real session, then checks its assertions. Skill
scripts can be answered from recorded :class:`StubResult` fixtures, and
:func:`build_report` turns a suite's results into JSON, Markdown and a CI
step summary.

This package imports from :mod:`omicsclaw.entry` and the layers below
it. Nothing else in ``omicsclaw`` imports it.
"""

from .assertions import (
    Assertion,
    Error,
    Failure,
    MaxToolCalls,
    MaxTurns,
    NoError,
    NoWriteOutside,
    OutputContains,
    OutputExcludes,
    PermissionRequested,
    SkillInvoked,
    ToolArgs,
    ToolCalled,
    ToolNotCalled,
)
from .case import ApprovalRecord, Case, FsChange, Headroom, Result, SkillRun
from .hermetic import hermetic_env
from .provider import RecordedCall, ScriptedProvider, ScriptedTurn, tool_call

_LAZY = {
    "SuiteReport": "report",
    "build_report": "report",
    "step_summary": "report",
    "write_json": "report",
    "write_markdown": "report",
    "arun_case": "runner",
    "run_case": "runner",
    "StubResult": "stubs",
    "record_stub_result": "stubs",
    "stubbed_skill_runs": "stubs",
}


def __getattr__(name: str):
    """Import the report, runner and stub names on first use.

    ``report`` and ``stubs`` are also command-line modules
    (``python -m omicsclaw.evals.report``); importing them here eagerly
    would make ``runpy`` warn that the module was already imported.

    :raises AttributeError: *name* is not part of this package.
    """
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    value = getattr(import_module(f".{module}", __name__), name)
    globals()[name] = value
    return value


__all__ = [
    "ApprovalRecord",
    "Assertion",
    "Case",
    "Error",
    "Failure",
    "FsChange",
    "Headroom",
    "MaxToolCalls",
    "MaxTurns",
    "NoError",
    "NoWriteOutside",
    "OutputContains",
    "OutputExcludes",
    "PermissionRequested",
    "RecordedCall",
    "Result",
    "ScriptedProvider",
    "ScriptedTurn",
    "SkillInvoked",
    "SkillRun",
    "StubResult",
    "SuiteReport",
    "ToolArgs",
    "ToolCalled",
    "ToolNotCalled",
    "arun_case",
    "build_report",
    "hermetic_env",
    "record_stub_result",
    "run_case",
    "step_summary",
    "stubbed_skill_runs",
    "tool_call",
    "write_json",
    "write_markdown",
]
