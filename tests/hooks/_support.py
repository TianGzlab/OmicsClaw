"""Doubles and the async runner the hook tests share.

Nothing here imports :mod:`omicsclaw.hooks` except for the types a double
has to produce, so a test that builds a hook out of these is evidence
that :class:`~omicsclaw.hooks.ToolHook` really is satisfied structurally.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

from omicsclaw.hooks import HookCall, HookDecision
from omicsclaw.schema import ToolDefinition
from omicsclaw.tools.base import ApprovalMode, RiskLevel, ToolPolicy

_T = TypeVar("_T")

_DEADLINE = 5.0
"""Seconds one scenario may take. A hang guard, not a measurement."""

ECHO_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
}


def run(main: Coroutine[Any, Any, _T]) -> _T:
    """``pytest-asyncio`` is not installed; this is the repository's convention."""

    async def guarded() -> _T:
        return await asyncio.wait_for(main, _DEADLINE)

    return asyncio.run(guarded())


class Echo:
    """A tool that returns what it was given, and remembers the calls."""

    policy = ToolPolicy(
        risk_level=RiskLevel.LOW,
        approval_mode=ApprovalMode.AUTO,
        read_only=True,
        concurrency_safe=True,
    )

    def __init__(self, name: str = "echo") -> None:
        self._name = name
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self._name, description="echo", input_schema=ECHO_SCHEMA
        )

    async def execute(self, arguments: str) -> str:
        self.calls.append(arguments)
        return f"echo:{arguments}"


class Raiser(Echo):
    """A tool that fails the way a real one does — by raising."""

    def __init__(self, error: BaseException, name: str = "echo") -> None:
        super().__init__(name)
        self._error = error

    async def execute(self, arguments: str) -> str:
        self.calls.append(arguments)
        raise self._error


class Recorder:
    """A hook that writes down every moment it is given.

    Satisfies :class:`~omicsclaw.hooks.ToolHook` by shape only — it
    inherits nothing — so the conformance tests are not testing
    :class:`~omicsclaw.hooks.Hook`.
    """

    def __init__(
        self,
        label: str,
        *,
        decision: HookDecision | None = None,
        rewrite: str | None = None,
    ) -> None:
        self.label = label
        self.log: list[str] = []
        self.seen: list[HookCall] = []
        self.failures: list[BaseException] = []
        self._decision = decision
        self._rewrite = rewrite

    async def before_execute(self, call: HookCall) -> HookDecision:
        self.log.append(f"before:{self.label}")
        self.seen.append(call)
        return self._decision if self._decision is not None else HookDecision()

    async def after_execute(self, call: HookCall, output: str) -> str:
        self.log.append(f"after:{self.label}")
        self.seen.append(call)
        return self._rewrite if self._rewrite is not None else output

    async def on_failure(self, call: HookCall, error: BaseException) -> None:
        self.log.append(f"failure:{self.label}")
        self.failures.append(error)
