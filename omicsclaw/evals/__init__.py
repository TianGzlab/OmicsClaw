"""Scripted, hermetic, deterministic agent evals.

A :class:`Case` scripts the model's replies with a
:class:`ScriptedProvider`, and :func:`run_case` runs it through the
production assembly (:func:`~omicsclaw.entry.build_app` with
``provider=``) and a real session, then checks its assertions. Skill
scripts can be answered from recorded :class:`StubResult` fixtures, and
:func:`build_report` turns a suite's results into JSON, Markdown and a CI
step summary. :mod:`omicsclaw.evals.live` runs the routing seeds against
a real model and scores which skill it chose.

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
from .case import (
    ApprovalPolicy,
    ApprovalRecord,
    Case,
    CaseProvider,
    FsChange,
    Headroom,
    Result,
    SkillRun,
)
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
    "RecordingProvider": "live",
    "judge": "live",
    "live_case": "live",
    "routing_policy": "live",
    "StubResult": "stubs",
    "record_stub_result": "stubs",
    "stubbed_skill_runs": "stubs",
}


def __getattr__(name: str):
    """Import the report, runner and stub names on first use.

    ``live``, ``report`` and ``stubs`` are also command-line modules
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
    "ApprovalPolicy",
    "ApprovalRecord",
    "Assertion",
    "Case",
    "CaseProvider",
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
    "RecordingProvider",
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
    "judge",
    "live_case",
    "record_stub_result",
    "routing_policy",
    "run_case",
    "step_summary",
    "stubbed_skill_runs",
    "tool_call",
    "write_json",
    "write_markdown",
]
