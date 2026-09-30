"""What a case checks about its run.

An :class:`Assertion` looks at a :class:`~omicsclaw.evals.case.Result`
and returns ``None`` when it holds or a :class:`Failure` when it does
not. A soft failure is reported as a warning and does not fail the case;
a hard one does.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .case import Result

__all__ = [
    "Assertion",
    "Error",
    "Failure",
    "MaxToolCalls",
    "MaxTurns",
    "NoError",
    "NoWriteOutside",
    "OutputContains",
    "OutputExcludes",
    "PermissionRequested",
    "SkillInvoked",
    "ToolArgs",
    "ToolCalled",
    "ToolNotCalled",
    "is_subset",
]


@dataclass(frozen=True)
class Failure:
    """One assertion that did not hold.

    :param assertion: The name of the assertion, or of the Runner check.
    :param message: What was expected and what happened.
    :param is_soft: Whether this is a warning rather than a failure.
    """

    assertion: str
    message: str
    is_soft: bool = False

    def __str__(self) -> str:
        return f"{self.assertion}: {self.message}"


@runtime_checkable
class Assertion(Protocol):
    """Something a case checks about its :class:`~omicsclaw.evals.case.Result`."""

    @property
    def name(self) -> str:
        """A short label for reports, such as ``ToolCalled(read_file)``."""
        ...

    def check(self, result: Result) -> Failure | None:
        """Return ``None`` when the check holds, or the failure when it does not."""
        ...


def is_subset(subset: Any, value: Any) -> bool:
    """Whether *value* contains *subset*, recursively.

    A dict matches when every key of *subset* is in *value* with a
    matching value. A list matches a list of the same length whose items
    match position by position. Anything else must be equal.
    """
    if isinstance(subset, dict):
        if not isinstance(value, dict):
            return False
        return all(key in value and is_subset(item, value[key]) for key, item in subset.items())
    if isinstance(subset, list):
        if not isinstance(value, list) or len(subset) != len(value):
            return False
        return all(is_subset(a, b) for a, b in zip(subset, value))
    return subset == value


@dataclass(frozen=True)
class ToolCalled:
    """The engine dispatched *tool* at least *min_times* times.

    Counts every dispatched call, including ones later refused by the
    permission gate, by argument validation or because the tool does not
    exist.
    """

    tool: str
    min_times: int = 1

    @property
    def name(self) -> str:
        return f"ToolCalled({self.tool})"

    def check(self, result: Result) -> Failure | None:
        seen = result.tool_calls_executed.count(self.tool)
        if seen >= self.min_times:
            return None
        return Failure(
            self.name,
            f"expected at least {self.min_times} call(s) to {self.tool}, saw {seen}; "
            f"calls: {list(result.tool_calls_executed)}",
        )


@dataclass(frozen=True)
class ToolNotCalled:
    """The engine never dispatched *tool*."""

    tool: str

    @property
    def name(self) -> str:
        return f"ToolNotCalled({self.tool})"

    def check(self, result: Result) -> Failure | None:
        seen = result.tool_calls_executed.count(self.tool)
        if not seen:
            return None
        return Failure(self.name, f"{self.tool} was called {seen} time(s)")


@dataclass(frozen=True)
class OutputContains:
    """The final reply contains *text*."""

    text: str

    @property
    def name(self) -> str:
        return f"OutputContains({self.text!r})"

    def check(self, result: Result) -> Failure | None:
        if self.text in result.final_output:
            return None
        return Failure(self.name, f"final output was {result.final_output[:200]!r}")


@dataclass(frozen=True)
class OutputExcludes:
    """The final reply does not contain *text*."""

    text: str

    @property
    def name(self) -> str:
        return f"OutputExcludes({self.text!r})"

    def check(self, result: Result) -> Failure | None:
        if self.text not in result.final_output:
            return None
        return Failure(self.name, f"final output contains {self.text!r}")


@dataclass(frozen=True)
class NoError:
    """No exchange ended as failed.

    Stopping at ``max_turns`` is not an error; check
    :attr:`~omicsclaw.evals.case.Result.stop_reason` for that.
    """

    @property
    def name(self) -> str:
        return "NoError"

    def check(self, result: Result) -> Failure | None:
        if result.run_error is None:
            return None
        return Failure(
            self.name,
            f"exchange failed: {type(result.run_error).__name__}: {result.run_error}",
        )


@dataclass(frozen=True)
class Error:
    """An exchange ended as failed, with an exception of type *kind* if given."""

    kind: type[BaseException] | None = None

    @property
    def name(self) -> str:
        return f"Error({self.kind.__name__})" if self.kind else "Error"

    def check(self, result: Result) -> Failure | None:
        if result.run_error is None:
            return Failure(self.name, "expected the exchange to fail; it did not")
        if self.kind is not None and not isinstance(result.run_error, self.kind):
            return Failure(
                self.name,
                f"expected {self.kind.__name__}, got {type(result.run_error).__name__}",
            )
        return None


@dataclass(frozen=True)
class MaxTurns:
    """At most *n* main-line model calls were made. Soft."""

    n: int

    @property
    def name(self) -> str:
        return f"MaxTurns({self.n})"

    def check(self, result: Result) -> Failure | None:
        if result.turn_count <= self.n:
            return None
        return Failure(
            self.name, f"{result.turn_count} model calls, limit {self.n}", is_soft=True
        )


@dataclass(frozen=True)
class MaxToolCalls:
    """At most *n* tool calls were dispatched. Soft."""

    n: int

    @property
    def name(self) -> str:
        return f"MaxToolCalls({self.n})"

    def check(self, result: Result) -> Failure | None:
        seen = len(result.tool_calls_executed)
        if seen <= self.n:
            return None
        return Failure(self.name, f"{seen} tool calls, limit {self.n}", is_soft=True)


@dataclass(frozen=True)
class SkillInvoked:
    """A script of *skill* was run through ``bash``, stubbed or not.

    With *domain*, the skill's domain in the index must match too.
    """

    skill: str
    domain: str | None = None

    @property
    def name(self) -> str:
        return f"SkillInvoked({self.skill})"

    def check(self, result: Result) -> Failure | None:
        runs = [run for run in result.skill_runs if run.skill == self.skill]
        if not runs:
            seen = sorted({run.skill for run in result.skill_runs})
            return Failure(self.name, f"no run of {self.skill}; runs seen: {seen}")
        if self.domain is not None and not any(run.domain == self.domain for run in runs):
            return Failure(
                self.name,
                f"expected domain {self.domain!r}, got {sorted({r.domain for r in runs})}",
            )
        return None


@dataclass(frozen=True)
class ToolArgs:
    """At least one call to *tool* had JSON arguments containing *subset*.

    Containment follows :func:`is_subset`.
    """

    tool: str
    subset: dict[str, Any]

    @property
    def name(self) -> str:
        return f"ToolArgs({self.tool})"

    def check(self, result: Result) -> Failure | None:
        seen: list[str] = []
        for call in result.tool_calls:
            if call.name != self.tool:
                continue
            seen.append(call.arguments)
            try:
                decoded = json.loads(call.arguments)
            except ValueError:
                continue
            if is_subset(self.subset, decoded):
                return None
        if not seen:
            return Failure(self.name, f"{self.tool} was never called")
        return Failure(self.name, f"no call matched {self.subset}; arguments seen: {seen}")


@dataclass(frozen=True)
class PermissionRequested:
    """An approval was asked for *tool*; with *approved*, answered that way."""

    tool: str
    approved: bool | None = None

    @property
    def name(self) -> str:
        return f"PermissionRequested({self.tool})"

    def check(self, result: Result) -> Failure | None:
        asked = [record for record in result.approvals if record.tool == self.tool]
        if not asked:
            return Failure(
                self.name,
                f"no approval was asked for {self.tool}; "
                f"asked: {[r.tool for r in result.approvals]}",
            )
        if self.approved is None or any(r.approved is self.approved for r in asked):
            return None
        return Failure(
            self.name,
            f"expected an approval answered {self.approved}, got {[r.approved for r in asked]}",
        )


@dataclass(frozen=True)
class NoWriteOutside:
    """Every file change under the case's temporary directory is inside *root*.

    ``"workspace"`` is the case's workspace, and ``"workspace/<sub>"`` a
    directory inside it. The check compares snapshots of the case's
    temporary directory taken before and after the run, so it cannot see
    files written elsewhere, such as the capture file ``bash`` keeps in
    the system temporary directory while a command runs.
    """

    root: str = "workspace"

    @property
    def name(self) -> str:
        return f"NoWriteOutside({self.root})"

    def check(self, result: Result) -> Failure | None:
        head, _, rest = self.root.partition("/")
        if head != "workspace":
            raise ValueError(f"root must be 'workspace' or 'workspace/<sub>', not {self.root!r}")
        allowed = (result.workspace / rest).resolve() if rest else result.workspace.resolve()
        outside = [
            f"{change.kind} {change.path}"
            for change in result.fs_changes
            if not _within(Path(change.path), allowed)
        ]
        if not outside:
            return None
        return Failure(self.name, f"changes outside {self.root}: {outside}")


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
    except ValueError:
        return False
    return True
