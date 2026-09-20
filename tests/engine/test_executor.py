"""Contract tests for ``omicsclaw.engine.executor`` (plan 0027 §6, task C).

Everything here is about what happens when tools disagree about how long
they take. A turn that runs one tool has no scheduling policy worth
testing; a turn that runs three, one of which hangs, one of which raises
and one of which returns instantly, is where the Observations get
mispaired, the run gets killed and the stream goes quiet — traps 1, 2, 4,
5 and 6 of plan 0027 §7, one named test each.

Nothing here sleeps to wait for a race to resolve. Ordering is forced
with :class:`asyncio.Event` so a scheduling change cannot make a test
flap, and the one deadline in the file is a hang guard rather than a
timing assertion.

No provider and no tool registry is involved: the executor is a Protocol,
so a fifteen-line local double drives every case.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, TypeVar

from omicsclaw.engine import executor as executor_module
from omicsclaw.engine.config import EngineConfig
from omicsclaw.engine.executor import (
    ConcurrencyAwareExecutor,
    DeadlineAwareExecutor,
    TimeoutPause,
    ToolExecutor,
    execute_tool_calls,
    observations,
)
from omicsclaw.engine.types import EngineEvent, EngineEventType
from omicsclaw.schema import Role, ToolCall, ToolDefinition, ToolResult

_T = TypeVar("_T")

_DEADLINE = 5.0
"""Seconds any one scenario may take. A hang guard, not a measurement.

A scheduling bug — a semaphore never released, a queue drained by a count
that never arrives — deadlocks rather than fails, and a deadlock wedges
the whole suite instead of naming the test that caught it. Wide enough
that no correct run approaches it.
"""


class FunctionExecutor:
    """A tool layer that is one async function, and nothing else.

    Structurally typed on purpose: it never subclasses
    :class:`~omicsclaw.engine.executor.ToolExecutor` and never imports
    it, which is how we know the Protocol is satisfiable by shape — and
    how step 4's registry will satisfy it without importing the engine.
    """

    def __init__(
        self,
        behaviour: Callable[[ToolCall], Awaitable[ToolResult]],
    ) -> None:
        self._behaviour = behaviour
        self.started: list[str] = []

    def available_tools(self) -> Sequence[ToolDefinition]:
        return ()

    async def execute(self, call: ToolCall) -> ToolResult:
        self.started.append(call.id)
        return await self._behaviour(call)


def _call(index: int, name: str = "") -> ToolCall:
    return ToolCall(id=f"c{index}", name=name or f"t{index}", arguments="{}")


def _ok(call: ToolCall, output: str) -> ToolResult:
    return ToolResult(tool_call_id=call.id, name=call.name, output=output)


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    """Drive one scenario to completion under the hang guard.

    ``pytest-asyncio`` is not installed, so async tests are driven by
    ``asyncio.run`` — the convention ``tests/provider/`` already follows.
    """

    async def guarded() -> _T:
        return await asyncio.wait_for(main, _DEADLINE)

    return asyncio.run(guarded())


async def _collect(stream: AsyncIterator[EngineEvent]) -> list[EngineEvent]:
    return [event async for event in stream]


def _finished(events: Sequence[EngineEvent]) -> list[ToolResult]:
    return [
        event.tool_result
        for event in events
        if event.type is EngineEventType.TOOL_RESULT and event.tool_result
    ]


def _started(events: Sequence[EngineEvent]) -> list[ToolCall]:
    return [
        event.tool_call
        for event in events
        if event.type is EngineEventType.TOOL_START and event.tool_call
    ]


def _drive(
    behaviour: Callable[[ToolCall], Awaitable[ToolResult]],
    calls: Sequence[ToolCall],
    config: EngineConfig | None = None,
    turn: int = 0,
) -> tuple[list[EngineEvent], list[ToolResult | None]]:
    """Run a whole turn and hand back both of its outputs.

    The results list holds ``ToolResult | None`` — one slot per call, in
    call order — which is the contract rather than an artefact of this
    helper, so nothing here compacts it.
    """

    async def scenario() -> tuple[list[EngineEvent], list[ToolResult | None]]:
        results: list[ToolResult | None] = []
        events = await _collect(
            execute_tool_calls(
                FunctionExecutor(behaviour),
                calls,
                config or EngineConfig(),
                results,
                turn,
            )
        )
        return events, results

    return _run(scenario())


def _answered(results: Sequence[ToolResult | None]) -> list[ToolResult]:
    """The slots, asserted full.

    A test that wants to project results into Observations has to say out
    loud that every call was answered, because ``observations`` takes
    answered results and filling an empty slot is the loop's job rather
    than the scheduler's.
    """
    assert all(result is not None for result in results)
    return [result for result in results if result is not None]


# --- Protocol conformance -------------------------------------------------


def test_a_structurally_matching_class_satisfies_the_protocol():
    async def behaviour(call: ToolCall) -> ToolResult:  # pragma: no cover
        return _ok(call, "")

    assert isinstance(FunctionExecutor(behaviour), ToolExecutor)


def test_a_class_missing_a_method_does_not_satisfy_the_protocol():
    """``available_tools`` is part of the contract, not a convenience.

    It is the method the loop must re-read every turn, so an executor
    that omits it would silently offer the model no tools at all.
    """

    class Incomplete:
        async def execute(self, call):  # pragma: no cover
            raise NotImplementedError

    assert not isinstance(Incomplete(), ToolExecutor)


# --- trap 1: Observations must stay in call order -------------------------


def test_results_land_in_call_order_when_the_tools_finish_in_reverse():
    """Completion order stops being call order the moment speeds differ.

    A mispaired result files B's output under A's ``tool_call_id``, after
    which the model reasons from the wrong answer — silently, and for the
    rest of the run.
    """
    second_finished = asyncio.Event()

    async def behaviour(call: ToolCall) -> ToolResult:
        if call.id == "c1":
            await second_finished.wait()
            return _ok(call, "output of c1")
        second_finished.set()
        return _ok(call, "output of c2")

    events, results = _drive(behaviour, (_call(1, "slow"), _call(2, "quick")))

    assert [r.name for r in _finished(events)] == ["quick", "slow"]
    assert [r.tool_call_id for r in results] == ["c1", "c2"]
    assert [r.output for r in results] == ["output of c1", "output of c2"]


def test_observations_pair_with_their_calls_even_when_execution_reverses():
    """Trap 1 end to end: executed 3-2-1, injected 1-2-3."""
    gates = {1: asyncio.Event(), 2: asyncio.Event()}
    order: list[str] = []

    async def behaviour(call: ToolCall) -> ToolResult:
        index = int(call.id[1:])
        if index in gates:
            await gates[index].wait()
        order.append(call.id)
        if index - 1 in gates:
            gates[index - 1].set()
        return _ok(call, f"output of {call.id}")

    _, results = _drive(behaviour, tuple(_call(i) for i in (1, 2, 3)))
    messages = observations(_answered(results), EngineConfig())

    assert order == ["c3", "c2", "c1"]
    assert [m.tool_call_id for m in messages] == ["c1", "c2", "c3"]
    assert [m.content for m in messages] == [
        "output of c1",
        "output of c2",
        "output of c3",
    ]


def test_every_call_gets_a_slot_even_when_its_worker_produced_nothing():
    """The contract, stated as an invariant rather than as a happy path.

    One slot per call, in call order, ``None`` where the worker produced
    nothing — that is what lets the loop pair Observations by position
    and never re-derive the pairing from ``tool_call_id``, which is a
    field neither unique nor guaranteed to survive a wrapping registry.
    A compacted list cannot express "this one, specifically, is missing".
    """

    async def behaviour(call: ToolCall) -> ToolResult:
        if call.name == "vanishes":
            raise asyncio.CancelledError
        return _ok(call, f"output of {call.id}")

    calls = (_call(1, "runs"), _call(2, "vanishes"), _call(3, "runs_too"))
    _, results = _drive(behaviour, calls)

    assert len(results) == len(calls)
    assert results[1] is None
    assert [r.output if r else None for r in results] == [
        "output of c1",
        None,
        "output of c3",
    ]


def test_the_slots_stay_in_call_order_when_the_missing_one_is_the_first():
    """The ordering claim is only worth something when the gap moves.

    A compacted list happens to look right whenever the empty slot is
    last; putting it first is what separates "one slot per call" from
    "the survivors, in order".
    """

    async def behaviour(call: ToolCall) -> ToolResult:
        if call.id == "c1":
            raise asyncio.CancelledError
        return _ok(call, f"output of {call.id}")

    _, results = _drive(behaviour, (_call(1), _call(2), _call(3)))

    assert results[0] is None
    assert [r.tool_call_id if r else None for r in results] == [None, "c2", "c3"]


def test_the_scheduler_is_an_async_generator_which_is_why_it_has_an_out_param():
    """PEP 525 forbids a non-empty ``return`` in an async generator.

    So a routine that both streams events and hands back this turn's
    results cannot be spelled without an outcome holder — the same seam
    plan 0027 §6 blesses for the loop kernel. Should this ever stop being
    a generator, the out-parameter should go with it.
    """
    assert inspect.isasyncgenfunction(execute_tool_calls)


def test_results_are_appended_to_whatever_the_caller_already_held():
    """The out-parameter is appended to, never reassigned.

    Plan 0027 §6: PEP 525 forbids a non-empty ``return`` in an async
    generator, so this list is how a turn's Observations get back to the
    loop. A caller accumulating across turns must keep what it had.
    """

    async def behaviour(call: ToolCall) -> ToolResult:
        return _ok(call, "new")

    earlier = ToolResult(tool_call_id="c0", name="earlier", output="kept")

    async def scenario() -> list[ToolResult]:
        results = [earlier]
        await _collect(
            execute_tool_calls(
                FunctionExecutor(behaviour), (_call(1),), EngineConfig(), results
            )
        )
        return results

    results = _run(scenario())

    assert results[0] is earlier
    assert [r.tool_call_id for r in results] == ["c0", "c1"]


def test_a_turn_with_no_calls_yields_nothing_and_appends_nothing():
    async def behaviour(call: ToolCall) -> ToolResult:  # pragma: no cover
        raise AssertionError("nothing should have been executed")

    events, results = _drive(behaviour, ())

    assert events == []
    assert results == []


# --- events are emitted live ----------------------------------------------


def test_each_call_is_announced_before_its_own_result_arrives():
    async def behaviour(call: ToolCall) -> ToolResult:
        return _ok(call, "done")

    events, _ = _drive(behaviour, (_call(1, "spatial_de"),))

    assert [e.type for e in events] == [
        EngineEventType.TOOL_START,
        EngineEventType.TOOL_RESULT,
    ]
    assert _started(events)[0] == _call(1, "spatial_de")
    assert _finished(events)[0].output == "done"


def test_a_finished_tool_is_announced_before_a_slow_sibling_returns():
    """The whole reason the workers feed a queue instead of a ``gather``.

    Batched emission — every start, then wait for all, then every result
    — would hold a fast tool's Observation hostage to the slowest tool of
    the turn, which is exactly when a progress display is worth having.
    Under that implementation the loop below never sees a ``TOOL_RESULT``
    and the hang guard fails the test.
    """

    async def scenario() -> tuple[list[EngineEvent], bool, list[ToolResult]]:
        released = asyncio.Event()

        async def behaviour(call: ToolCall) -> ToolResult:
            if call.name == "slow":
                await released.wait()
            return _ok(call, call.name)

        results: list[ToolResult] = []
        stream = execute_tool_calls(
            FunctionExecutor(behaviour),
            (_call(1, "slow"), _call(2, "fast")),
            EngineConfig(),
            results,
        )
        seen: list[EngineEvent] = []
        while not _finished(seen):
            seen.append(await anext(stream))
        still_blocked = not released.is_set()
        released.set()
        seen.extend(await _collect(stream))
        return seen, still_blocked, results

    seen, still_blocked, results = _run(scenario())

    assert still_blocked
    assert _finished(seen)[0].name == "fast"
    assert [r.name for r in results] == ["slow", "fast"]


def test_every_event_is_stamped_with_the_turn_that_produced_it():
    """Without it a Surface cannot attribute a late result to its turn."""

    async def behaviour(call: ToolCall) -> ToolResult:
        return _ok(call, "done")

    events, _ = _drive(behaviour, (_call(1), _call(2)), turn=7)

    assert [e.turn for e in events] == [7, 7, 7, 7]


def test_a_turn_number_is_optional_and_defaults_to_zero():
    async def behaviour(call: ToolCall) -> ToolResult:
        return _ok(call, "done")

    events, _ = _drive(behaviour, (_call(1),))

    assert [e.turn for e in events] == [0, 0]


# --- trap 5: a raising executor must not kill the run ---------------------


def test_a_raising_executor_becomes_a_failed_observation_not_a_dead_run():
    """Step 4's registry will report its own failures; a Protocol is
    satisfied by shape, so a third-party one might not."""

    async def behaviour(call: ToolCall) -> ToolResult:
        if call.name == "explodes":
            raise ValueError("threshold must be positive")
        return _ok(call, "fine")

    events, results = _drive(
        behaviour, (_call(1, "explodes"), _call(2, "survivor"))
    )

    assert [r.tool_call_id for r in results] == ["c1", "c2"]
    assert results[0].is_error
    assert results[0].name == "explodes"
    assert "ValueError" in results[0].output
    assert "threshold must be positive" in results[0].output
    assert results[1].is_error is False
    assert results[1].output == "fine"
    assert len(_finished(events)) == 2


def test_a_failed_observation_is_streamed_like_any_other():
    """``is_error`` is shown to the consumer, never swallowed."""

    async def behaviour(call: ToolCall) -> ToolResult:
        raise RuntimeError("no such skill")

    events, _ = _drive(behaviour, (_call(1, "typo"),))

    assert [e.type for e in events] == [
        EngineEventType.TOOL_START,
        EngineEventType.TOOL_RESULT,
    ]
    assert _finished(events)[0].is_error


# --- trap 6: one tool's timeout must not touch its siblings ---------------


def test_a_tool_that_overruns_its_timeout_does_not_take_its_sibling_with_it():
    """One slow tool degrades to one ``is_error`` Observation the model
    can react to, not a dead turn."""

    async def behaviour(call: ToolCall) -> ToolResult:
        if call.name == "hangs":
            await asyncio.sleep(30)
        return _ok(call, "fine")

    config = EngineConfig(tool_timeout=0.05)
    _, results = _drive(behaviour, (_call(1, "hangs"), _call(2, "prompt")), config)

    assert [r.tool_call_id for r in results] == ["c1", "c2"]
    assert results[0].is_error
    assert "timed out" in results[0].output
    assert "0.05s" in results[0].output
    assert results[1].is_error is False
    assert results[1].output == "fine"


def test_a_timeout_is_not_mistaken_for_a_cancelled_scope():
    """On 3.11+ ``wait_for`` raises ``TimeoutError``, which is an
    ``Exception`` and not a ``CancelledError``.

    Trap 4 says cancellation propagates untouched; trap 6 says a timeout
    becomes an Observation. Catching the wrong base class collapses the
    two and a slow tool would end the run.
    """

    async def behaviour(call: ToolCall) -> ToolResult:
        await asyncio.sleep(30)
        raise AssertionError("unreachable")  # pragma: no cover

    config = EngineConfig(tool_timeout=0.05)
    events, results = _drive(behaviour, (_call(1, "hangs"),), config)

    assert not isinstance(TimeoutError(), asyncio.CancelledError)
    assert len(results) == 1
    assert results[0].is_error
    assert len(_finished(events)) == 1


def test_a_tools_own_timeout_error_is_reported_as_the_tools_and_not_the_engines():
    """On 3.11+ ``TimeoutError`` is the builtin, so a tool with an HTTP
    read budget of its own raises the very class an expired engine budget
    does.

    Reported as the engine's, this Observation reads ``tool 'spatial_de'
    timed out after 60s``: the host is gone, the two seconds that really
    elapsed are replaced by sixty that did not, and the model is pointed
    at "make it fit in the budget" when the truth is "that service is
    unreachable". The engine may claim its timeout only when its own
    budget is what fired.
    """
    detail = (
        "HTTPSConnectionPool(host='ensembl.org', port=443): "
        "Read timed out. (read timeout=2)"
    )

    async def behaviour(call: ToolCall) -> ToolResult:
        raise TimeoutError(detail)

    config = EngineConfig(tool_timeout=60.0)
    _, results = _drive(behaviour, (_call(1, "spatial_de"),), config)
    result = results[0]

    assert result is not None and result.is_error
    assert result.output == f"tool 'spatial_de' raised TimeoutError: {detail}"
    assert "60s" not in result.output


def test_a_tool_timeout_error_is_not_a_timeout_when_no_budget_was_imposed():
    """``tool_timeout <= 0`` means the engine never started a clock, so
    there is nothing it can honestly call an overrun. The old wording
    announced a timeout anyway, just without a number."""

    async def behaviour(call: ToolCall) -> ToolResult:
        raise TimeoutError("the tool gave up on its own")

    for timeout in (0.0, -1.0):
        config = EngineConfig(tool_timeout=timeout)
        _, results = _drive(behaviour, (_call(1, "slow_api"),), config)
        result = results[0]

        assert result is not None
        assert result.output == (
            "tool 'slow_api' raised TimeoutError: the tool gave up on its own"
        )


def test_a_tool_timeout_of_zero_or_less_imposes_no_limit():
    """``wait_for(coro, 0)`` fires immediately, so applying it
    unconditionally would fail every tool on an unlimited config."""

    async def behaviour(call: ToolCall) -> ToolResult:
        await asyncio.sleep(0.05)
        return _ok(call, "slow but finished")

    for timeout in (0.0, -1.0):
        config = EngineConfig(tool_timeout=timeout)
        _, results = _drive(behaviour, (_call(1, "unhurried"),), config)
        assert results[0].is_error is False
        assert results[0].output == "slow but finished"


# --- the concurrency cap --------------------------------------------------


def _peak_simultaneity(limit: int, count: int = 5) -> tuple[int, list[str]]:
    """Run ``count`` cooperating tools, and report the high-water mark.

    Each tool yields control ``count + 2`` times before returning, so
    every sibling the cap admits has been given the chance to start
    before the first one finishes. ``asyncio.sleep(0)`` is a scheduling
    yield rather than a delay, so the figure is deterministic.
    """
    calls = tuple(_call(index) for index in range(1, count + 1))
    state = {"live": 0, "peak": 0}

    async def behaviour(call: ToolCall) -> ToolResult:
        state["live"] += 1
        state["peak"] = max(state["peak"], state["live"])
        for _ in range(count + 2):
            await asyncio.sleep(0)
        state["live"] -= 1
        return _ok(call, call.name)

    config = EngineConfig(max_concurrent_tools=limit)
    _, results = _drive(behaviour, calls, config)
    return state["peak"], [r.tool_call_id for r in results]


def test_the_concurrency_cap_bounds_how_many_tools_run_at_once():
    peak, order = _peak_simultaneity(limit=2)

    assert peak == 2
    assert order == ["c1", "c2", "c3", "c4", "c5"]


def test_a_tool_is_announced_when_the_cap_admits_it_and_not_when_it_is_queued():
    """``TOOL_START`` means "this tool is running", not "this tool is in
    the queue".

    Emitting it before the semaphore is acquired passes every other test
    in this file — the results are identical and the cap still holds —
    while a progress display shows five tools running when two are, which
    is the one job the event has. Here the third start must not be
    available until a sibling has finished and freed a slot.
    """

    async def scenario() -> tuple[list[EngineEvent], bool, int]:
        released = asyncio.Event()
        entered = {"count": 0}

        async def behaviour(call: ToolCall) -> ToolResult:
            entered["count"] += 1
            await released.wait()
            return _ok(call, call.name)

        results: list[ToolResult | None] = []
        stream = execute_tool_calls(
            FunctionExecutor(behaviour),
            tuple(_call(index) for index in range(1, 6)),
            EngineConfig(max_concurrent_tools=2),
            results,
        )
        seen = [await anext(stream), await anext(stream)]
        third = asyncio.ensure_future(anext(stream))
        # Every worker has now had many chances to be scheduled, so a
        # start that was going to be queued has been queued.
        for _ in range(50):
            await asyncio.sleep(0)
        still_two = not third.done()
        running = entered["count"]
        released.set()
        seen.append(await third)
        seen.extend(await _collect(stream))
        return seen, still_two, running

    seen, still_two, running = _run(scenario())

    assert still_two
    assert [c.id for c in _started(seen[:2])] == ["c1", "c2"]
    assert running == 2
    assert len(_started(seen)) == 5
    assert len(_finished(seen)) == 5


def test_a_cap_of_zero_lets_every_tool_of_the_turn_run_at_once():
    """The other half of the pair.

    On its own, ``peak == 2`` above would also be satisfied by an
    implementation that never ran anything concurrently at all; this
    test is what makes that claim mean something.
    """
    peak, order = _peak_simultaneity(limit=0)

    assert peak == 5
    assert order == ["c1", "c2", "c3", "c4", "c5"]


# --- trap 4: cancellation is not a failure --------------------------------


def test_cancelling_the_consumer_leaves_the_cancellation_alone():
    """A cancelled scope stays cancelled — it never becomes a result.

    Turning it into one would tell a caller who cancelled a run that the
    run had an opinion about it.
    """

    async def scenario() -> tuple[bool, BaseException, list[ToolResult]]:
        blocked = asyncio.Event()

        async def behaviour(call: ToolCall) -> ToolResult:
            await blocked.wait()
            raise AssertionError("unreachable")  # pragma: no cover

        results: list[ToolResult] = []
        stream = execute_tool_calls(
            FunctionExecutor(behaviour), (_call(1, "blocks"),), EngineConfig(), results
        )
        started = asyncio.Event()

        async def consume() -> None:
            async for event in stream:
                if event.type is EngineEventType.TOOL_START:
                    started.set()

        consumer = asyncio.ensure_future(consume())
        await started.wait()
        consumer.cancel()
        outcome = (await asyncio.gather(consumer, return_exceptions=True))[0]
        return consumer.cancelled(), outcome, results

    cancelled, outcome, results = _run(scenario())

    assert cancelled
    assert isinstance(outcome, asyncio.CancelledError)
    assert results == []


def test_a_tool_that_reports_cancellation_is_not_turned_into_a_result():
    """``except Exception``, and never ``BaseException``.

    A :exc:`asyncio.CancelledError` says somebody stopped the work, not
    that the work produced an answer. Manufacturing an ``is_error``
    Observation out of one would report a cancelled scope to the model as
    a tool that ran and failed, and the run would carry on regardless.
    Its slot stays empty; its siblings are unaffected.
    """

    async def behaviour(call: ToolCall) -> ToolResult:
        if call.name == "cancelled":
            raise asyncio.CancelledError
        return _ok(call, "fine")

    events, results = _drive(behaviour, (_call(1, "cancelled"), _call(2, "ok")))

    assert results[0] is None
    assert results[1] is not None and results[1].tool_call_id == "c2"
    assert [r.name for r in _finished(events)] == ["ok"]


def test_abandoning_the_generator_leaves_no_tool_still_running():
    """A consumer that walks away must not orphan the turn's tools.

    Without the cancel-and-await in the generator's ``finally`` the two
    blocked workers outlive the stream that created them, still holding
    whatever the tool layer gave them.
    """

    async def scenario() -> tuple[int, set[asyncio.Task[Any]], list[ToolResult]]:
        blocked = asyncio.Event()
        observed = {"cancelled": 0}

        async def behaviour(call: ToolCall) -> ToolResult:
            try:
                await blocked.wait()
            except asyncio.CancelledError:
                observed["cancelled"] += 1
                raise
            raise AssertionError("unreachable")  # pragma: no cover

        results: list[ToolResult] = []
        before = asyncio.all_tasks()
        stream = execute_tool_calls(
            FunctionExecutor(behaviour),
            (_call(1, "blocks"), _call(2, "blocks_too")),
            EngineConfig(),
            results,
        )
        starts = [await anext(stream), await anext(stream)]
        assert all(e.type is EngineEventType.TOOL_START for e in starts)
        await stream.aclose()
        return observed["cancelled"], asyncio.all_tasks() - before, results

    cancelled, leftovers, results = _run(scenario())

    assert cancelled == 2
    assert leftovers == set()
    assert results == []


# --- trap 2: an empty Observation is a wasted turn or a 400 ---------------


def test_an_empty_tool_output_becomes_the_configured_placeholder():
    """Some backends reject an empty ``tool_result`` outright, and even
    where it is accepted it spends a turn saying nothing.

    Substituted here, inside the engine, before anything reaches an
    adapter — so no adapter has to remember to do it.
    """
    results = [ToolResult(tool_call_id="c1", name="quiet")]
    message = observations(results, EngineConfig())[0]

    assert message.content == "[tool completed with no output]"
    assert message.role is Role.TOOL
    assert message.tool_call_id == "c1"
    assert message.name == "quiet"


def test_the_placeholder_wording_is_configurable():
    """So a deployment can phrase it in the language it prompts in."""
    config = EngineConfig().with_overrides(empty_output_placeholder="[无输出]")
    message = observations([ToolResult(tool_call_id="c1")], config)[0]

    assert message.content == "[无输出]"


def test_a_tool_that_said_something_is_projected_verbatim():
    results = [ToolResult(tool_call_id="c1", name="spatial_de", output="3 markers")]

    assert observations(results, EngineConfig())[0].content == "3 markers"


def test_a_failed_observation_carries_its_error_flag_into_history():
    """``ToolResult.is_error`` is what lets an adapter use a vendor's
    native failure signal instead of leaving the model to parse prose."""
    results = [
        ToolResult(tool_call_id="c1", name="de", output="boom", is_error=True)
    ]
    message = observations(results, EngineConfig())[0]

    assert message.is_error
    assert message.content == "boom"
    assert message.role is Role.TOOL


def test_an_empty_failure_keeps_its_verdict_and_gains_a_body():
    """The placeholder replaces the content, never the ``is_error`` flag —
    a tool that failed silently must not read as a tool that succeeded."""
    results = [ToolResult(tool_call_id="c1", name="de", is_error=True)]
    message = observations(results, EngineConfig())[0]

    assert message.content == EngineConfig().empty_output_placeholder
    assert message.is_error


def test_observations_keep_the_order_of_the_results_they_were_given():
    results = [
        ToolResult(tool_call_id="c1", output="first"),
        ToolResult(tool_call_id="c2", output=""),
        ToolResult(tool_call_id="c3", output="third"),
    ]
    messages = observations(results, EngineConfig())

    assert [m.tool_call_id for m in messages] == ["c1", "c2", "c3"]
    assert [m.content for m in messages] == [
        "first",
        "[tool completed with no output]",
        "third",
    ]


def test_observations_of_nothing_is_an_empty_tuple():
    """A tuple rather than a list, matching the frozen shapes around it."""
    assert observations([], EngineConfig()) == ()
    assert isinstance(observations([], EngineConfig()), tuple)


# --- the write barrier ----------------------------------------------------


class _Witness:
    """Records which tools were inside the executor at the same time.

    Sampled at every yield point rather than on entry alone, so two tools
    that merely started in the same tick are not counted as having
    overlapped unless they were both still there when the loop came back.
    """

    def __init__(self) -> None:
        self._live: set[str] = set()
        self.together: dict[str, set[str]] = {}

    async def execute(self, call: ToolCall) -> ToolResult:
        name = call.name
        self._live.add(name)
        self.together.setdefault(name, set())
        try:
            for _ in range(3):
                for other in self._live:
                    self.together[other] |= self._live - {other}
                await asyncio.sleep(0)
            return _ok(call, name)
        finally:
            self._live.discard(name)


class ConcurrencyExecutor(FunctionExecutor):
    """A tool layer that also says which of its tools may run in parallel.

    Structurally typed like its base, so satisfying
    :class:`~omicsclaw.engine.executor.ConcurrencyAwareExecutor` is again
    a matter of shape.
    """

    def __init__(
        self,
        behaviour: Callable[[ToolCall], Awaitable[ToolResult]],
        safe: Sequence[str] = (),
    ) -> None:
        super().__init__(behaviour)
        self._safe = frozenset(safe)
        self.asked: list[str] = []

    def is_concurrency_safe(self, name: str) -> bool:
        self.asked.append(name)
        return name in self._safe


def _drive_executor(
    executor: ToolExecutor,
    calls: Sequence[ToolCall],
    config: EngineConfig | None = None,
) -> tuple[list[EngineEvent], list[ToolResult | None]]:
    """``_drive``, for a scenario that needs a particular executor object."""

    async def scenario() -> tuple[list[EngineEvent], list[ToolResult | None]]:
        results: list[ToolResult | None] = []
        events = await _collect(
            execute_tool_calls(executor, calls, config or EngineConfig(), results)
        )
        return events, results

    return _run(scenario())


def test_a_structurally_matching_class_satisfies_the_concurrency_protocol():
    aware = ConcurrencyExecutor(_Witness().execute)
    plain = FunctionExecutor(_Witness().execute)

    assert isinstance(aware, ConcurrencyAwareExecutor)
    assert not isinstance(plain, ConcurrencyAwareExecutor)


def test_two_calls_that_are_not_concurrency_safe_never_overlap():
    """Plan 0028 §11 debt #1: two writes to one path in one turn.

    The whole point of the barrier, and the assertion is in the tightening
    direction — a scheduler that ignored the flag would put both names in
    each other's company set.
    """
    witness = _Witness()
    executor = ConcurrencyExecutor(witness.execute, safe=())

    _drive_executor(executor, [_call(0, "w1"), _call(1, "w2")])

    assert witness.together == {"w1": set(), "w2": set()}


def test_an_unsafe_call_does_not_overlap_with_a_safe_sibling():
    """A barrier is alone, not merely apart from its own kind."""
    witness = _Witness()
    executor = ConcurrencyExecutor(witness.execute, safe=("r1",))

    _drive_executor(executor, [_call(0, "r1"), _call(1, "w1")])

    assert witness.together == {"r1": set(), "w1": set()}


def test_safe_calls_on_the_far_side_of_a_barrier_still_run_together():
    """The barrier orders the turn; it does not serialise the whole turn.

    Without this the cheap fix — run everything one at a time as soon as
    any call is unsafe — would pass every other test in this section while
    throwing away the parallelism the layer exists for.
    """
    witness = _Witness()
    executor = ConcurrencyExecutor(witness.execute, safe=("r1", "r2", "r3"))

    _drive_executor(
        executor,
        [_call(0, "r1"), _call(1, "w1"), _call(2, "r2"), _call(3, "r3")],
    )

    assert witness.together["w1"] == set(), "the barrier ran alone"
    assert witness.together["r2"] == {"r3"}, "and its safe successors together"
    assert witness.together["r3"] == {"r2"}
    assert witness.together["r1"] == set(), "nothing to share its batch with"


def test_batching_leaves_results_in_call_order():
    """Trap 1 again, now that completion order can differ across batches."""
    witness = _Witness()
    executor = ConcurrencyExecutor(witness.execute, safe=("r1", "r2"))
    calls = [_call(0, "w1"), _call(1, "r1"), _call(2, "r2"), _call(3, "w2")]

    events, results = _drive_executor(executor, calls)

    assert [result.name for result in _answered(results)] == ["w1", "r1", "r2", "w2"]
    assert [call.name for call in _started(events)] == ["w1", "r1", "r2", "w2"]


def test_an_executor_that_cannot_answer_is_scheduled_as_it_always_was():
    """The two-method seam keeps working, unchanged and unbatched."""
    witness = _Witness()

    _drive_executor(FunctionExecutor(witness.execute), [_call(0, "a"), _call(1, "b")])

    assert witness.together == {"a": {"b"}, "b": {"a"}}


def test_the_barrier_can_be_switched_off():
    witness = _Witness()
    executor = ConcurrencyExecutor(witness.execute, safe=())

    _drive_executor(
        executor,
        [_call(0, "w1"), _call(1, "w2")],
        EngineConfig(serialize_unsafe_tools=False),
    )

    assert witness.together == {"w1": {"w2"}, "w2": {"w1"}}
    assert executor.asked == [], "and the executor is not even consulted"


def test_an_executor_that_raises_the_question_is_read_as_unsafe():
    """A broken answer resolves to the guarded value, not to an error.

    Scheduling is decided before any tool runs, so an exception here would
    otherwise fail calls that were never going to have a problem.
    """
    witness = _Witness()

    class Broken(FunctionExecutor):
        def is_concurrency_safe(self, name: str) -> bool:
            raise RuntimeError("no idea")

    _drive_executor(Broken(witness.execute), [_call(0, "a"), _call(1, "b")])

    assert witness.together == {"a": set(), "b": set()}


def test_the_concurrency_cap_still_bounds_a_batch():
    """``max_concurrent_tools`` and the barrier are separate ceilings.

    Both halves are asserted. The upper bound alone would also pass
    against an implementation that ran everything one at a time, which is
    the failure this pairing exists to notice: a cap of two has to mean
    "two ran together", not merely "no more than two did".
    """
    witness = _Witness()
    executor = ConcurrencyExecutor(witness.execute, safe=("r1", "r2", "r3"))

    _drive_executor(
        executor,
        [_call(0, "r1"), _call(1, "r2"), _call(2, "r3")],
        EngineConfig(max_concurrent_tools=2),
    )

    assert all(len(seen) <= 1 for seen in witness.together.values())
    assert any(seen for seen in witness.together.values()), "two really did overlap"


def test_abandoning_a_batched_turn_leaves_no_tool_still_running():
    """Cancellation reaches batches that started and the ones that did not."""
    running: list[str] = []
    finished: list[str] = []

    async def behaviour(call: ToolCall) -> ToolResult:
        running.append(call.name)
        try:
            await asyncio.sleep(_DEADLINE)
        finally:
            finished.append(call.name)
        return _ok(call, "never")  # pragma: no cover

    executor = ConcurrencyExecutor(behaviour, safe=())
    calls = [_call(0, "w1"), _call(1, "w2")]

    async def scenario() -> None:
        results: list[ToolResult | None] = []
        stream = execute_tool_calls(executor, calls, EngineConfig(), results)
        await stream.__anext__()
        await stream.aclose()
        assert results == [], "a turn nobody finished reports nothing"

    _run(scenario())

    assert running == ["w1"], "the second batch never started"
    assert finished == ["w1"], "and the first was cancelled rather than left"


def test_each_worker_reads_its_own_copy_of_the_ambient_context():
    """The property ``omicsclaw/tools/context.py`` builds its isolation on.

    One Task per call, and ``Task.__init__`` copies the context, so a tool
    rebinding a variable cannot reach its siblings. Written down here
    because the tool layer depends on it and cannot enforce it.

    **The refactor that would break it is not the obvious one.** Swapping
    ``ensure_future`` for :class:`asyncio.TaskGroup` or
    :func:`asyncio.gather` is safe — both make Tasks, and a Task copies.
    What is not safe is awaiting the calls **inline** instead of in Tasks,
    or passing several of them one shared ``context=``.
    """
    probe: ContextVar[str] = ContextVar("test.probe", default="outer")
    seen: dict[str, str] = {}

    async def behaviour(call: ToolCall) -> ToolResult:
        probe.set(call.name)
        await asyncio.sleep(0)
        seen[call.name] = probe.get()
        return _ok(call, call.name)

    executor = ConcurrencyExecutor(behaviour, safe=("a", "b"))
    _drive_executor(executor, [_call(0, "a"), _call(1, "b")])

    assert seen == {"a": "a", "b": "b"}
    assert probe.get() == "outer", "and no worker wrote back into the turn"


# --- per-tool duration on the event ---------------------------------------


def test_a_finished_tool_reports_how_long_it_took():
    async def behaviour(call: ToolCall) -> ToolResult:
        await asyncio.sleep(0.05)
        return _ok(call, "slow")

    events, _ = _drive(behaviour, [_call(0)])
    (finished,) = [e for e in events if e.type is EngineEventType.TOOL_RESULT]

    assert finished.duration_s is not None
    assert finished.duration_s >= 0.05


def test_only_a_finished_tool_carries_a_duration():
    """``TOOL_START`` has nothing to report yet, and says so with ``None``."""

    async def behaviour(call: ToolCall) -> ToolResult:
        return _ok(call, "quick")

    events, _ = _drive(behaviour, [_call(0)])

    assert all(
        event.duration_s is None
        for event in events
        if event.type is not EngineEventType.TOOL_RESULT
    )


# --- the per-call timeout can be paused from inside the call --------------


_PAUSE: ContextVar[TimeoutPause | None] = ContextVar("test.pause", default=None)


class PausingExecutor:
    """A tool layer that takes the engine's pause and hands it to its tool.

    Publishes through a :class:`~contextvars.ContextVar` rather than an
    attribute, which is what
    :class:`~omicsclaw.tools.registry.ToolRegistry` does and what keeps
    two concurrent calls from reading each other's pause.
    """

    def __init__(
        self,
        body: Callable[[ToolCall, TimeoutPause | None], Awaitable[ToolResult]],
    ) -> None:
        self._body = body

    def available_tools(self) -> Sequence[ToolDefinition]:
        return ()

    @contextmanager
    def use_timeout_pause(self, pause: TimeoutPause) -> Iterator[None]:
        token = _PAUSE.set(pause)
        try:
            yield
        finally:
            _PAUSE.reset(token)

    async def execute(self, call: ToolCall) -> ToolResult:
        return await self._body(call, _PAUSE.get())


def test_a_structurally_matching_class_satisfies_the_deadline_protocol():
    async def body(call, pause):  # pragma: no cover
        return _ok(call, "")

    assert isinstance(PausingExecutor(body), DeadlineAwareExecutor)
    assert not isinstance(FunctionExecutor(body), DeadlineAwareExecutor)


def test_a_wait_inside_the_pause_is_not_charged_to_the_tool_timeout():
    """What a human's thinking time costs: nothing.

    The wait is twice the budget, which without the pause is the
    ``tool 'X' timed out`` this exists to stop being said.

    **The work after the pause is what makes this test load-bearing, and
    it is one ``await``.** ``asyncio.Timeout`` only fires at an await
    point, and ``__aexit__`` cancels its handler on the way out — so a
    tool that returns the instant the pause ends never reaches one, and a
    deadline restored to a moment *in the past* is indistinguishable here
    from a correct one. That is precisely the bug this whole seam exists
    to fix, restored under a different name, and without these 50
    milliseconds nothing in the suite would notice it.
    """

    async def body(call: ToolCall, pause: TimeoutPause | None) -> ToolResult:
        assert pause is not None
        with pause():
            await asyncio.sleep(0.6)
        await asyncio.sleep(0.05)
        return _ok(call, "approved")

    _, results = _drive_executor(
        PausingExecutor(body), [_call(0)], EngineConfig(tool_timeout=0.3)
    )

    assert _answered(results)[0].output == "approved"


def test_the_same_wait_outside_the_pause_still_times_out():
    """The tightening half: the budget is paused, never removed."""

    async def body(call: ToolCall, pause: TimeoutPause | None) -> ToolResult:
        await asyncio.sleep(0.6)
        return _ok(call, "never")  # pragma: no cover

    _, results = _drive_executor(
        PausingExecutor(body), [_call(0)], EngineConfig(tool_timeout=0.3)
    )

    assert _answered(results)[0].is_error is True
    assert "timed out after 0.3s" in _answered(results)[0].output


def test_what_was_left_of_the_budget_comes_back_after_the_pause():
    """A tool that pauses and then overruns is still reported as overrunning.

    The mutation this catches is a pause that reschedules to ``None`` and
    forgets to restore, which would make every tool that ever asks for
    approval untimed for the rest of its run.
    """

    async def body(call: ToolCall, pause: TimeoutPause | None) -> ToolResult:
        assert pause is not None
        with pause():
            await asyncio.sleep(0.3)
        await asyncio.sleep(0.6)
        return _ok(call, "never")  # pragma: no cover

    _, results = _drive_executor(
        PausingExecutor(body), [_call(0)], EngineConfig(tool_timeout=0.3)
    )

    assert _answered(results)[0].is_error is True
    assert "timed out after 0.3s" in _answered(results)[0].output


def test_an_executor_whose_pause_seam_is_broken_only_loses_the_pause():
    """A half-implemented optional seam must not fail every tool call.

    Both shapes an opted-in executor gets wrong: a ``use_timeout_pause``
    that raises, and one that hands back something that is not a context
    manager. Either used to make the call fail with a ``TypeError`` the
    model would be asked to fix — and only when a timeout was configured,
    so it would not reproduce under a test that left ``tool_timeout`` at
    zero.
    """

    class Raises(PausingExecutor):
        def use_timeout_pause(self, pause: TimeoutPause) -> Iterator[None]:
            raise RuntimeError("no idea how to hold this")

    class NotAScope(PausingExecutor):
        def use_timeout_pause(self, pause: TimeoutPause) -> Any:
            return 42

    async def body(call: ToolCall, pause: TimeoutPause | None) -> ToolResult:
        assert pause is None, "a seam that did not open publishes nothing"
        return _ok(call, "ran anyway")

    for executor in (Raises(body), NotAScope(body)):
        _, results = _drive_executor(
            executor, [_call(0)], EngineConfig(tool_timeout=1.0)
        )
        assert _answered(results)[0].output == "ran anyway", type(executor).__name__


def test_no_pause_is_offered_when_the_engine_imposed_no_budget():
    """``tool_timeout <= 0`` means there is no clock to stop."""
    seen: list[TimeoutPause | None] = []

    async def body(call: ToolCall, pause: TimeoutPause | None) -> ToolResult:
        seen.append(pause)
        return _ok(call, "unbudgeted")

    _drive_executor(
        PausingExecutor(body), [_call(0)], EngineConfig(tool_timeout=0.0)
    )

    assert seen == [None]


def test_a_nested_pause_leaves_the_restore_to_the_outer_one():
    """Two pauses in one call must not reinstate a stale deadline.

    The inner pause sees a budget that is already disabled and does
    nothing, so the outer one still restores the seconds that were left
    when *it* started.
    """

    async def body(call: ToolCall, pause: TimeoutPause | None) -> ToolResult:
        assert pause is not None
        with pause():
            with pause():
                await asyncio.sleep(0.4)
            await asyncio.sleep(0.4)
        await asyncio.sleep(0.6)
        return _ok(call, "never")  # pragma: no cover

    _, results = _drive_executor(
        PausingExecutor(body), [_call(0)], EngineConfig(tool_timeout=0.3)
    )

    assert _answered(results)[0].is_error is True
    assert "timed out after 0.3s" in _answered(results)[0].output


# --- the module's public surface ------------------------------------------


def test_the_module_exports_exactly_its_public_names():
    assert executor_module.__all__ == [
        "ConcurrencyAwareExecutor",
        "DeadlineAwareExecutor",
        "TimeoutPause",
        "ToolExecutor",
        "execute_tool_calls",
        "observations",
    ]
