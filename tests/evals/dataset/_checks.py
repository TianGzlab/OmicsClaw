"""Checks the seed cases need that the package's twelve assertions do not cover.

They satisfy the :class:`~omicsclaw.evals.Assertion` protocol and are
all hard. They stay in the dataset rather than the package until more
than this dataset needs them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from omicsclaw.engine import StopReason
from omicsclaw.evals import Failure, Result
from omicsclaw.schema import Message


def _messages(result: Result, call: int, role: str | None) -> tuple[Message, ...] | None:
    try:
        messages = result.provider_calls[call].messages
    except IndexError:
        return None
    if role is None:
        return messages
    return tuple(message for message in messages if message.role == role)


def occurrences(result: Result, text: str, *, call: int, role: str | None = None) -> int:
    """How often *text* appears in the messages of main-line call *call*."""
    messages = _messages(result, call, role) or ()
    return sum(message.content.count(text) for message in messages)


@dataclass(frozen=True)
class SentContains:
    """Main-line call *call* was sent *text*.

    :param text: One string, or several that must appear in this order
        across the call's messages.
    :param call: Index into the main-line calls; ``-1`` is the last.
    :param role: Only look at messages with this role.
    :param times: When set, the (single) text must occur exactly this
        many times.
    """

    text: str | tuple[str, ...]
    call: int = -1
    role: str | None = None
    times: int | None = None

    @property
    def name(self) -> str:
        shown = self.text if isinstance(self.text, str) else " < ".join(self.text)
        return f"SentContains({shown[:40]!r}, call={self.call})"

    def check(self, result: Result) -> Failure | None:
        messages = _messages(result, self.call, self.role)
        if messages is None:
            return Failure(self.name, f"there is no call {self.call}; {len(result.provider_calls)} were made")
        joined = "\n".join(message.content for message in messages)
        texts = (self.text,) if isinstance(self.text, str) else self.text
        if self.times is not None:
            seen = joined.count(texts[0])
            if seen == self.times:
                return None
            return Failure(self.name, f"expected {self.times} occurrence(s), saw {seen}")
        position = 0
        for text in texts:
            found = joined.find(text, position)
            if found < 0:
                return Failure(self.name, f"{text[:80]!r} not sent (in order) on call {self.call}")
            position = found + len(text)
        return None


@dataclass(frozen=True)
class ToolResultContains:
    """Some result of *tool* contains *text*; with *is_error*, has that flag."""

    tool: str
    text: str
    is_error: bool | None = None

    @property
    def name(self) -> str:
        return f"ToolResultContains({self.tool}, {self.text[:40]!r})"

    def check(self, result: Result) -> Failure | None:
        names = {call.id: call.name for call in result.tool_calls}
        outputs = [
            item
            for item in result.tool_results
            if (item.name or names.get(item.tool_call_id)) == self.tool
        ]
        for item in outputs:
            if self.text in item.output and (self.is_error is None or item.is_error is self.is_error):
                return None
        seen = [(item.is_error, item.output[:160]) for item in outputs]
        return Failure(self.name, f"no matching {self.tool} result; seen: {seen}")


@dataclass(frozen=True)
class StopReasonIs:
    """The last completed exchange stopped for *reason*."""

    reason: StopReason

    @property
    def name(self) -> str:
        return f"StopReasonIs({self.reason})"

    def check(self, result: Result) -> Failure | None:
        if result.stop_reason is self.reason:
            return None
        return Failure(self.name, f"stopped with {result.stop_reason}")


@dataclass(frozen=True)
class CountIs:
    """A count taken from the result equals *n* (or is at least *n*).

    :param label: What is counted, for the report.
    :param what: Computes the count from the result.
    :param n: The expected count.
    :param at_least: Compare with ``>=`` instead of ``==``.
    """

    label: str
    what: Callable[[Result], int]
    n: int
    at_least: bool = False

    @property
    def name(self) -> str:
        return f"CountIs({self.label} {'>=' if self.at_least else '=='} {self.n})"

    def check(self, result: Result) -> Failure | None:
        seen = self.what(result)
        if seen >= self.n if self.at_least else seen == self.n:
            return None
        return Failure(self.name, f"counted {seen}")


def user_changes(result: Result) -> list[tuple[str, str]]:
    """File changes outside the workspace's ``.omicsclaw/`` state, as ``(kind, relative path)``."""
    changes = []
    root = result.workspace.resolve()
    for change in result.fs_changes:
        path = Path(change.path).resolve()
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            relative = str(path)
        if relative.startswith(".omicsclaw/"):
            continue
        changes.append((change.kind, relative))
    return changes
