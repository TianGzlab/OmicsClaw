"""The registry satisfies the engine's seam — structurally (plan 0028 §9-3).

Step 3 published :class:`omicsclaw.engine.executor.ToolExecutor` as the
smallest Protocol that lets a loop act, and step 4 is the first thing
meant to satisfy it. The point of it being a Protocol is that the
dependency runs one way only: this test file imports both packages, but
``omicsclaw/tools/`` imports neither ``omicsclaw.engine`` nor anything
else outside :mod:`omicsclaw.schema` — enforced next door, in
``test_tools_is_a_leaf_layer.py``.

``isinstance`` alone would be weak evidence: a ``runtime_checkable``
Protocol checks that the attributes exist and nothing about their
signatures, so a registry with an ``execute`` taking the wrong arguments
would still pass it. The last test therefore runs a real turn of real
calls through the engine's own scheduler, which is the only check that
the two halves actually fit.

The seam has two **optional** further halves, and the registry answers
both: ``ConcurrencyAwareExecutor``, which is what finally reads
:attr:`~omicsclaw.tools.base.ToolPolicy.concurrency_safe`, and
``DeadlineAwareExecutor``, which carries the engine's per-call timeout
pause down to a tool waiting on a human. They are tested here for the
same reason the first two are: the tool layer cannot import the Protocols
it satisfies, so nothing but a test that sees both packages can notice
the day a signature drifts.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator, Coroutine, Iterator, Sequence
from contextlib import contextmanager
from typing import Any, TypeVar

from omicsclaw.engine.config import EngineConfig
from omicsclaw.engine.executor import (
    ConcurrencyAwareExecutor,
    DeadlineAwareExecutor,
    ToolExecutor,
    execute_tool_calls,
    observations,
)
from omicsclaw.engine.types import EngineEvent
from omicsclaw.schema import Role, ToolCall, ToolDefinition, ToolResult
from omicsclaw.tools import ToolPolicy, ToolRegistry, pause_tool_timeout

_T = TypeVar("_T")
_DEADLINE = 5.0


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    async def guarded() -> _T:
        return await asyncio.wait_for(main, _DEADLINE)

    return asyncio.run(guarded())


class Fake:
    def __init__(self, name: str, output: str = "", raises: bool = False) -> None:
        self._name = name
        self._output = output or f"{name} ran"
        self._raises = raises

    @property
    def name(self) -> str:
        return self._name

    def definition(self) -> ToolDefinition:
        return ToolDefinition(name=self._name, description=f"the {self._name} tool")

    async def execute(self, arguments: str) -> str:
        if self._raises:
            raise RuntimeError("it went wrong")
        return self._output


class NotAnExecutor:
    """Half the shape, to show the ``isinstance`` check is not vacuous."""

    async def execute(self, call: ToolCall) -> ToolResult:  # pragma: no cover
        raise NotImplementedError


def test_a_registry_is_a_tool_executor():
    assert isinstance(ToolRegistry(), ToolExecutor)


def test_the_isinstance_check_can_fail():
    """Without this, the test above would pass against anything at all."""
    assert not isinstance(NotAnExecutor(), ToolExecutor)


def test_the_two_method_signatures_match_the_protocol():
    """What ``runtime_checkable`` cannot see, checked by hand.

    A Protocol's ``isinstance`` verifies member *presence*. The parameter
    lists are the part that would actually break a call, so they are
    compared here rather than assumed.
    """
    for method in ("available_tools", "execute"):
        expected = inspect.signature(getattr(ToolExecutor, method))
        actual = inspect.signature(getattr(ToolRegistry, method))
        assert list(actual.parameters) == list(expected.parameters), method


def test_a_registry_drives_a_whole_turn_through_the_engines_scheduler():
    """The end-to-end fit, including the failures the loop has to survive.

    Three calls: one that works, one whose tool raises, one naming a tool
    that does not exist. All three must come back as Observations in call
    order — the registry turning both failures into ``is_error`` results
    is what lets the turn complete at all.
    """
    registry = ToolRegistry([Fake("ok"), Fake("boom", raises=True)])
    calls = [
        ToolCall(id="c0", name="ok"),
        ToolCall(id="c1", name="boom"),
        ToolCall(id="c2", name="ghost"),
    ]
    results: list[ToolResult | None] = []

    async def drive() -> list[EngineEvent]:
        stream: AsyncIterator[EngineEvent] = execute_tool_calls(
            registry, calls, EngineConfig(), results
        )
        return [event async for event in stream]

    _run(drive())

    assert len(results) == 3
    assert [r.tool_call_id for r in results if r] == ["c0", "c1", "c2"]
    assert [bool(r and r.is_error) for r in results] == [False, True, True]
    assert results[0] and results[0].output == "ok ran"
    assert results[1] and "RuntimeError" in results[1].output
    assert results[2] and "ghost" in results[2].output


def test_the_observations_a_registry_produces_are_projectable():
    """The last hop: a registry's results become history the model reads."""
    registry = ToolRegistry([Fake("ok", output="")])
    result = _run(registry.execute(ToolCall(id="c0", name="ok")))

    messages = observations([result], EngineConfig())

    assert len(messages) == 1
    assert messages[0].role is Role.TOOL
    assert messages[0].tool_call_id == "c0"
    assert messages[0].name == "ok"


def test_available_tools_is_the_sequence_the_protocol_promises():
    registry = ToolRegistry([Fake("a"), Fake("b")])

    definitions: Sequence[ToolDefinition] = registry.available_tools()

    assert isinstance(definitions, tuple)
    assert all(isinstance(d, ToolDefinition) for d in definitions)


# ---- the two optional seams ---------------------------------------------


def test_a_registry_answers_both_optional_protocols():
    registry = ToolRegistry()

    assert isinstance(registry, ConcurrencyAwareExecutor)
    assert isinstance(registry, DeadlineAwareExecutor)
    assert not isinstance(NotAnExecutor(), ConcurrencyAwareExecutor)
    assert not isinstance(NotAnExecutor(), DeadlineAwareExecutor)


def test_the_optional_signatures_match_the_protocols():
    for protocol, method in (
        (ConcurrencyAwareExecutor, "is_concurrency_safe"),
        (DeadlineAwareExecutor, "use_timeout_pause"),
    ):
        expected = inspect.signature(getattr(protocol, method))
        actual = inspect.signature(getattr(ToolRegistry, method))
        assert list(actual.parameters) == list(expected.parameters), method


def test_a_tool_that_declared_nothing_is_not_concurrency_safe():
    """``ToolPolicy()`` is the guarded set, and this is one of its fields."""
    registry = ToolRegistry([Fake("ok")])

    assert registry.is_concurrency_safe("ok") is False


def test_an_unregistered_name_is_not_concurrency_safe():
    assert ToolRegistry().is_concurrency_safe("ghost") is False


def test_the_deployments_policy_is_the_one_the_scheduler_reads():
    """Plan 0028 §4 Q5, pinned in the tightening direction.

    The author says this tool parallelises; the deployment says it does
    not. A registry that answered from ``tool.policy`` would report
    ``True`` here, and the barrier a deployment asked for would exist in
    ``policy_for`` and nowhere else.
    """
    tool = Fake("ok")
    tool.policy = ToolPolicy(concurrency_safe=True)
    registry = ToolRegistry()
    registry.register(tool, ToolPolicy(concurrency_safe=False))

    assert registry.is_concurrency_safe("ok") is False


def test_the_pause_the_engine_hands_over_reaches_a_running_tool():
    """The conduit, checked end to end rather than by reading the method.

    ``use_timeout_pause`` is only useful if what a tool reads back through
    :func:`~omicsclaw.tools.pause_tool_timeout` is the object the engine
    handed the registry, and if the publication is gone again afterwards.
    """
    registry = ToolRegistry()
    entered: list[str] = []

    @contextmanager
    def pause() -> Iterator[None]:
        entered.append("in")
        try:
            yield
        finally:
            entered.append("out")

    with registry.use_timeout_pause(pause):
        with pause_tool_timeout() as paused:
            assert paused is True

    with pause_tool_timeout() as paused:
        assert paused is False, "the publication did not outlive the scope"

    assert entered == ["in", "out"]
