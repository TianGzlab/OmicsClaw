"""Contract tests for ``omicsclaw.tools.context`` (plan 0028, task B).

Plan 0028 trap 11 is the reason this file imports ``omicsclaw.engine``.
The mechanism under test is not "a ``contextvar`` can be read back"; it is
"a value a surface set before the turn is readable **inside a tool running
in a worker the engine started**". Those are different claims, and only
the second is worth anything: ``execute_tool_calls`` schedules each call
with :func:`asyncio.ensure_future`, and whether the ambient context
survives that hop is a property of the engine that this package depends on
and does not control. So every propagation test here drives the real
``execute_tool_calls`` with a real :class:`~omicsclaw.tools.ToolRegistry`,
and none of them reads a variable back in the coroutine that set it.

**The layering rule does not apply to this file.** Plan 0028 §9-4 forbids
``omicsclaw/tools/`` — the *package* — from importing anything but
``omicsclaw.schema``, and ``test_tools_is_a_leaf_layer.py`` enforces it by
globbing ``omicsclaw/tools/**/*.py``. ``tests/tools/`` is not scanned,
which is correct: a test proving the production rule holds has to be able
to see both sides of it.

The other subject is plan 0028 §4 Q4's five questions. Each has at least
one named test, and the fourth — what an unbound approval channel means —
has three, because it is the only one of the five whose wrong answer is a
security hole rather than a bug.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Coroutine, TypeVar

import pytest

from omicsclaw.engine.config import EngineConfig
from omicsclaw.engine.executor import execute_tool_calls
from omicsclaw.schema import ToolCall, ToolResult
from omicsclaw.tools import (
    ApprovalDecision,
    ApprovalDenied,
    ApprovalMode,
    ApprovalRequest,
    ApprovalUnavailable,
    FunctionTool,
    ProgressUpdate,
    RiskLevel,
    ToolContext,
    ToolPolicy,
    ToolRegistry,
    context_value,
    current_context,
    report_progress,
    require_approval,
    reset_tool_context,
    set_tool_context,
    use_tool_context,
)

_T = TypeVar("_T")

_DEADLINE = 5.0
"""A hang guard, not a measurement: a barrier that never releases deadlocks."""

_PARALLEL = ToolPolicy(approval_mode=ApprovalMode.AUTO, concurrency_safe=True)
"""What a tool has to declare to be scheduled beside its siblings.

``ToolPolicy()`` leaves ``concurrency_safe`` at ``False``, which the
engine's scheduler runs as a barrier, so a tool built for a concurrency
test that did not say this would be run alone and the test would wait for
a sibling that had not started."""


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    return asyncio.run(asyncio.wait_for(main, _DEADLINE))


async def _drive(
    registry: ToolRegistry,
    names: list[str],
) -> list[ToolResult | None]:
    """One turn's calls, through the engine's own concurrent scheduler.

    Not a convenience: this is the path plan 0028 trap 11 requires. The
    default :class:`EngineConfig` leaves ``max_concurrent_tools`` at 0, so
    there is no ceiling on how many workers start at once — but a call
    only shares a batch with its neighbours when its tool declares
    ``concurrency_safe=True``, so a test that needs two tools genuinely in
    flight has to say so on the policy. ``_PARALLEL`` below is that
    declaration.
    """
    calls = [
        ToolCall(id=f"c{index}", name=name, arguments="{}")
        for index, name in enumerate(names)
    ]
    results: list[ToolResult | None] = []
    async for _ in execute_tool_calls(registry, calls, EngineConfig(), results):
        pass
    return results


def _outputs(results: list[ToolResult | None]) -> list[str]:
    return [r.output if r is not None else "<no result>" for r in results]


# ---- Q4.1: the channel carries a reference, not a decision ---------------


def test_the_channel_is_a_callback_the_tool_awaits_per_call():
    """Plan 0028 §4 Q4's first question, and the reason it is a reference.

    A decision computed before the turn cannot be about the arguments the
    tool actually received. Here one channel answers two tools
    differently, having looked at each request — which is only possible
    because what travels in the context is the callback itself.
    """
    asked: list[ApprovalRequest] = []

    async def channel(request: ApprovalRequest) -> ApprovalDecision:
        asked.append(request)
        approved = request.tool_name == "harmless"
        return ApprovalDecision(approved, reason="" if approved else "too risky")

    async def harmless() -> str:
        await require_approval("harmless")
        return "ran"

    async def dangerous() -> str:
        await require_approval("dangerous", reason="deletes 412 files")
        return "ran"

    registry = ToolRegistry(
        [
            FunctionTool("harmless", "d", harmless),
            FunctionTool("dangerous", "d", dangerous),
        ]
    )

    async def main() -> list[ToolResult | None]:
        with use_tool_context(approval=channel):
            return await _drive(registry, ["harmless", "dangerous"])

    results = _run(main())

    assert [r.is_error for r in results] == [False, True]
    assert results[0].output == "ran"
    assert "too risky" in results[1].output
    assert [r.tool_name for r in asked] == ["harmless", "dangerous"]
    assert asked[1].reason == "deletes 412 files"


def test_the_request_carries_the_raw_arguments_a_human_would_be_shown():
    """An approval prompt showing re-encoded arguments shows something else.

    The payload is deliberately one a decode-and-re-encode would rewrite —
    the first assertion says so — because a payload already in canonical
    form would let a re-encoding implementation pass this test.

    A hand-written tool has the raw string in hand; a function wrapped by
    :class:`~omicsclaw.tools.FunctionTool` does not, and passes whatever
    it can reconstruct. That is a real limitation of the adapter rather
    than of this channel, and it is recorded on ``FunctionTool``.
    """
    seen: list[str] = []
    payload = '{"b":1,\n    "a": 2}'
    assert json.dumps(json.loads(payload)) != payload

    async def channel(request: ApprovalRequest) -> bool:
        seen.append(request.arguments)
        return True

    async def main() -> None:
        with use_tool_context(approval=channel):
            await require_approval("probe", payload)

    _run(main())

    assert seen == [payload]


# ---- Q4.2 / Q4.3: who binds, who reads ----------------------------------


def test_a_surface_binds_and_a_tool_reads_without_the_registry_taking_part():
    """The registry makes the channel exist and has no opinion about it."""
    registry = ToolRegistry(
        [FunctionTool("where", "d", lambda: context_value("workspace", "<unset>"))]
    )

    async def main() -> list[str]:
        with use_tool_context(values={"workspace": "/data/run-7"}):
            return _outputs(await _drive(registry, ["where"]))

    assert _run(main()) == ["/data/run-7"]
    assert not hasattr(registry, "approval")
    assert not [name for name in dir(registry) if "approv" in name.lower()]


def test_a_tool_run_with_nothing_bound_sees_an_empty_context():
    """A script or a test is not a surface, and must not need to pretend to be."""
    registry = ToolRegistry(
        [FunctionTool("where", "d", lambda: context_value("workspace", "<unset>"))]
    )

    assert _run(_drive(registry, ["where"]))[0].output == "<unset>"
    assert current_context() == ToolContext()


def test_the_binding_is_restored_even_when_the_turn_raises():
    """A stale channel left on a pooled task is the crosstalk bug, deferred."""
    with pytest.raises(RuntimeError):
        with use_tool_context(values={"session_id": "s1"}):
            assert context_value("session_id") == "s1"
            raise RuntimeError("the turn failed")

    assert context_value("session_id") is None


def test_binding_replaces_rather_than_inheriting_the_surrounding_context():
    """An omitted argument means "I did not set that", never "keep the last one".

    Inheritance would make a nested scope silently carry the outer
    session's approval channel, which is the crosstalk failure wearing a
    different hat.
    """

    async def channel(_: ApprovalRequest) -> bool:
        return True

    with use_tool_context(approval=channel, values={"session_id": "s1"}):
        with use_tool_context(values={"session_id": "s2"}):
            assert current_context().approval is None
            assert context_value("session_id") == "s2"
        assert current_context().approval is channel


def test_the_raw_bind_and_reset_pair_works_for_a_surface_that_owns_its_task():
    token = set_tool_context(ToolContext(values={"chat_id": "42"}))
    try:
        assert context_value("chat_id") == "42"
    finally:
        reset_tool_context(token)

    assert context_value("chat_id") is None


def test_the_values_bag_covers_every_key_the_legacy_seam_injects():
    """Plan 0028 §5: ``context_params`` must have a one-for-one replacement.

    The names are the ones ``ToolSpec.context_params`` actually declares
    across ``omicsclaw/runtime/tools/builders/``, plus the two
    ``query_engine.py`` adds to every request. Two of them are callables,
    which is the point: the bag carries references as happily as strings,
    so a tool needing a runtime object is not a special case.
    """
    cancel_event = asyncio.Event()
    legacy_keys = {
        "session_id": "s1",
        "chat_id": "42",
        "surface": "telegram",
        "workspace": "/w",
        "pipeline_workspace": "/w/pipe",
        "thread_id": "t9",
        "policy_state": object(),
        "cancel_event": cancel_event,
        "run_runtime": object(),
        "candidate_chain_gate": True,
        "model_override": "gpt-4o",
        "provider_override": "openai",
        "tool_result_root": "/w/results",
        "request_tool_approval": lambda *_: True,
    }

    with use_tool_context(values=legacy_keys):
        assert {key: context_value(key) for key in legacy_keys} == legacy_keys
        assert context_value("cancel_event") is cancel_event


def test_the_values_bag_is_not_writable_through_a_tool():
    """One tool must not be able to edit the turn for the ones beside it."""
    with use_tool_context(values={"workspace": "/w"}):
        with pytest.raises(TypeError):
            current_context().values["workspace"] = "/elsewhere"  # type: ignore[index]


def test_the_values_bag_is_not_writable_through_the_raw_binder_either():
    """The same property, through :func:`set_tool_context`.

    It was true of one binding path and not the other, which is the worse
    way round: ``use_tool_context`` wrapped the bag it built, while
    ``set_tool_context`` handed a caller's live dict straight through —
    and ``set_tool_context`` is the form recommended to a surface that
    owns a whole Task, so it is the binding that lives longest and is
    read by the most tools. Sealing in :class:`ToolContext`'s constructor
    is what makes the two paths one property instead of two.
    """
    context = ToolContext(values={"workspace": "/w"})
    token = set_tool_context(context)
    try:
        with pytest.raises(TypeError):
            current_context().values["workspace"] = "/elsewhere"  # type: ignore[index]
        assert context_value("workspace") == "/w"
    finally:
        reset_tool_context(token)


def test_the_bag_a_surface_keeps_is_copied_rather_than_shared():
    """Read-only from this side is not read-only if the caller kept the dict.

    A :class:`~types.MappingProxyType` is a *view*. Wrapping without
    copying would leave the surface's own dict able to rewrite the turn
    under a tool that already read it — and a surface holding that dict is
    the ordinary case, since it is how the surface assembled the values in
    the first place.
    """
    bag = {"workspace": "/w"}
    token = set_tool_context(ToolContext(values=bag))
    try:
        bag["workspace"] = "/elsewhere"

        assert context_value("workspace") == "/w"
    finally:
        reset_tool_context(token)


# ---- Q4.4: nothing bound means refused ----------------------------------


def test_a_tool_needing_approval_fails_closed_when_no_channel_is_bound():
    """Plan 0028 §4 Q4's fourth question, which the plan refused to leave open.

    The tool does not run, the model is told why, and the run continues.
    Silence is not consent — and the assertion that matters is
    ``ran == []``, because a message-only check would still pass an
    implementation that ran the tool and then complained.
    """
    ran: list[str] = []

    async def destructive() -> str:
        await require_approval("destructive", policy=ToolPolicy())
        ran.append("yes")
        return "deleted everything"

    registry = ToolRegistry([FunctionTool("destructive", "d", destructive)])

    results = _run(_drive(registry, ["destructive"]))

    assert ran == []
    assert results[0].is_error is True
    assert "requires approval" in results[0].output
    assert "no approval channel" in results[0].output
    assert "deleted everything" not in results[0].output


def test_the_refusal_names_the_mode_and_risk_that_caused_it():
    """An operator reading the log has to be able to tell which rule fired.

    The policy is declared on the tool and reaches
    :func:`require_approval` through the registry's resolution, which is
    the path a mounted tool actually takes. It used to be passed as the
    ``policy=`` argument, which worked only while that argument outranked
    the registry — the arrangement under which ``register(policy=)``
    gated nothing.
    """
    declared = ToolPolicy(
        approval_mode=ApprovalMode.DENY_UNLESS_TRUSTED,
        risk_level=RiskLevel.MEDIUM,
    )

    async def probe() -> str:
        await require_approval("probe")
        return "ran"

    registry = ToolRegistry([FunctionTool("probe", "d", probe, policy=declared)])

    output = _run(_drive(registry, ["probe"]))[0].output

    assert "deny_unless_trusted" in output
    assert "medium" in output


def test_an_auto_policy_tool_runs_with_no_channel_bound():
    """Fail-closed must not mean unusable: a tool declared safe is not asked."""
    declared = ToolPolicy(approval_mode=ApprovalMode.AUTO)

    async def probe() -> str:
        decision = await require_approval("probe")
        return f"ran ({decision.reason})"

    registry = ToolRegistry([FunctionTool("probe", "d", probe, policy=declared)])

    assert _run(_drive(registry, ["probe"]))[0].output == "ran (policy: auto)"


def test_a_call_that_omits_the_policy_asks_rather_than_proceeds():
    """``ToolPolicy()`` is ``ASK``, so the forgetful call is the safe one."""
    with pytest.raises(ApprovalUnavailable):
        _run(require_approval("probe"))


def test_a_channel_that_answers_nothing_is_a_refusal():
    """A callback that opened a dialog and forgot to return is not a yes."""

    async def forgetful(_: ApprovalRequest) -> None:
        return None

    async def main() -> None:
        with use_tool_context(approval=forgetful):
            await require_approval("probe")

    with pytest.raises(ApprovalDenied) as raised:
        _run(main())

    assert "returned no decision" in str(raised.value)


def test_an_unavailable_channel_is_caught_as_a_denial():
    """Both are the same answer to the tool; the split is for the operator."""
    assert issubclass(ApprovalUnavailable, ApprovalDenied)

    with pytest.raises(ApprovalDenied):
        _run(require_approval("probe"))


@pytest.mark.parametrize("answer", [True, False])
def test_a_plain_boolean_channel_is_accepted(answer: bool):
    """A test double should be one lambda, not a protocol implementation."""

    async def main() -> ApprovalDecision:
        with use_tool_context(approval=lambda _: answer):
            return await require_approval("probe")

    if answer:
        assert _run(main()).approved is True
    else:
        with pytest.raises(ApprovalDenied):
            _run(main())


def test_a_channel_answering_something_unrecognised_still_does_not_run_the_tool():
    """A deployment bug is surfaced rather than guessed into an approval."""
    ran: list[str] = []

    async def probe() -> str:
        await require_approval("probe")
        ran.append("yes")
        return "ran"

    registry = ToolRegistry([FunctionTool("probe", "d", probe)])

    async def main() -> list[ToolResult | None]:
        with use_tool_context(approval=lambda _: "sure, go ahead"):
            return await _drive(registry, ["probe"])

    results = _run(main())

    assert ran == []
    assert results[0].is_error is True
    assert "TypeError" in results[0].output


# ---- progress: the channel that must *not* fail closed ------------------


def test_progress_reaches_a_bound_sink():
    seen: list[ProgressUpdate] = []

    async def slow() -> str:
        await report_progress("normalising", tool_name="slow", fraction=0.5)
        return "done"

    registry = ToolRegistry([FunctionTool("slow", "d", slow)])

    async def main() -> list[ToolResult | None]:
        with use_tool_context(progress=seen.append):
            return await _drive(registry, ["slow"])

    assert _run(main())[0].output == "done"
    assert seen == [
        ProgressUpdate(tool_name="slow", message="normalising", fraction=0.5)
    ]


def test_progress_with_no_sink_is_a_no_op_and_says_so():
    """The opposite of approval, because progress is not a permission.

    A background turn has no audience, and a tool that refused to run
    without one would be unusable outside a surface.
    """
    reported: list[bool] = []

    async def slow() -> str:
        reported.append(await report_progress("still going"))
        return "done"

    registry = ToolRegistry([FunctionTool("slow", "d", slow)])

    assert _run(_drive(registry, ["slow"]))[0].output == "done"
    assert reported == [False]


def test_a_sink_that_raises_does_not_fail_the_tool_that_reported_to_it():
    """"Never fails closed" has to mean *broken* as well as *absent*.

    It meant only "absent". A Desktop Surface whose websocket closed
    mid-run, or a Telegram edit that hit a rate limit, raised out of
    ``report_progress`` and through the tool, and the registry filed it as
    ``tool 'works' raised RuntimeError: the websocket closed`` — the
    tool's work already done and thrown away, and a Surface transport
    fault delivered to the model in the one shape that asks the model to
    fix the tool.

    Both halves are asserted: the tool's own answer survives, and
    ``report_progress`` tells the truth about delivery rather than
    claiming a success it did not have.
    """
    delivered: list[bool] = []

    def broken(update: ProgressUpdate) -> None:
        raise RuntimeError("the websocket closed")

    async def works() -> str:
        delivered.append(await report_progress("halfway", tool_name="works"))
        return "the work is done"

    registry = ToolRegistry([FunctionTool("works", "d", works)])

    async def main() -> list[ToolResult | None]:
        with use_tool_context(progress=broken):
            return await _drive(registry, ["works"])

    results = _run(main())

    assert results[0].is_error is False, results[0].output
    assert results[0].output == "the work is done"
    assert delivered == [False]


def test_an_async_sink_that_raises_is_caught_too():
    """The await is inside the guard, not merely the call.

    A ``try`` that wrapped only ``sink(update)`` would catch a synchronous
    sink and miss an async one, which is the shape a real surface has:
    the coroutine is built without touching the socket and fails when it
    is awaited.
    """
    delivered: list[bool] = []

    async def broken(update: ProgressUpdate) -> None:
        await asyncio.sleep(0)
        raise ConnectionResetError("peer went away")

    async def main() -> None:
        with use_tool_context(progress=broken):
            delivered.append(await report_progress("halfway"))

    _run(main())

    assert delivered == [False]


def test_a_cancelled_sink_is_not_swallowed_as_a_failed_report():
    """``except Exception``, never ``BaseException`` — traps 3 and 4.

    A turn being cancelled is not a sink declining to listen, and a
    ``report_progress`` that answered ``False`` to it would convert an
    abandoned run into one that keeps going.
    """

    async def cancelling(update: ProgressUpdate) -> None:
        raise asyncio.CancelledError

    async def main() -> None:
        with use_tool_context(progress=cancelling):
            await report_progress("halfway")

    with pytest.raises(asyncio.CancelledError):
        _run(main())


def test_an_async_progress_sink_is_awaited():
    seen: list[str] = []

    async def sink(update: ProgressUpdate) -> None:
        await asyncio.sleep(0)
        seen.append(update.message)

    async def main() -> None:
        with use_tool_context(progress=sink):
            await report_progress("pushed over a websocket")

    _run(main())

    assert seen == ["pushed over a websocket"]


# ---- trap 11: read inside the engine's own workers ----------------------


def test_the_context_reaches_tools_running_in_concurrent_engine_workers():
    """Plan 0028 trap 11, and the property the whole design rests on.

    The rendezvous is what makes this a concurrency test rather than a
    sequential one: no tool can return until all three have started, so
    all three are genuinely in flight in separate ``ensure_future``
    workers when they read the context. A same-coroutine read would prove
    nothing about that hop, which is the hop the engine performs and this
    package does not control.

    The three tools declare ``_PARALLEL`` because the scheduler now runs a
    tool that has not claimed ``concurrency_safe`` alone; without it this
    test would wait forever for a second worker that the engine was
    holding back on purpose.
    """
    started = asyncio.Semaphore(0)
    release = asyncio.Event()

    async def probe() -> str:
        started.release()
        await release.wait()
        return context_value("session_id", "<unset>")

    registry = ToolRegistry(
        [
            FunctionTool(name, "d", probe, policy=_PARALLEL)
            for name in ("a", "b", "c")
        ]
    )

    async def main() -> list[str]:
        with use_tool_context(values={"session_id": "s-outer"}):
            turn = asyncio.ensure_future(_drive(registry, ["a", "b", "c"]))
            for _ in range(3):
                await started.acquire()
            release.set()
            return _outputs(await turn)

    assert _run(main()) == ["s-outer"] * 3


def test_a_tool_that_suspends_still_sees_the_context_after_resuming():
    """``contextvars`` follow the task, not the stack frame that set them."""

    async def probe() -> str:
        before = context_value("session_id")
        await asyncio.sleep(0)
        return f"{before}/{context_value('session_id')}"

    registry = ToolRegistry([FunctionTool("probe", "d", probe)])

    async def main() -> list[str]:
        with use_tool_context(values={"session_id": "s1"}):
            return _outputs(await _drive(registry, ["probe"]))

    assert _run(main()) == ["s1/s1"]


def test_a_tool_cannot_leak_a_binding_into_the_turn_that_called_it():
    """A worker's context is a copy, so a sub-agent's bind is contained."""

    async def rebinder() -> str:
        set_tool_context(ToolContext(values={"session_id": "hijacked"}))
        return context_value("session_id", "<unset>")

    registry = ToolRegistry([FunctionTool("rebinder", "d", rebinder)])

    async def main() -> tuple[list[str], Any]:
        with use_tool_context(values={"session_id": "s1"}):
            outputs = _outputs(await _drive(registry, ["rebinder"]))
            return outputs, context_value("session_id")

    assert _run(main()) == (["hijacked"], "s1")


# ---- Q4.5: two sessions in one process ----------------------------------


def test_two_sessions_in_their_own_tasks_keep_their_own_channels():
    """Plan 0028 §4 Q4's fifth question, in the shape the Channel Surface has.

    Telegram and Feishu conversations interleave on one event loop, so
    isolation is not optional. The tools are forced to overlap — neither
    can finish before the other has started — so a leak would show up as
    one user's tool call being ruled on by the other user's channel, which
    is precisely the incident this convention exists to prevent.
    """
    both_started = asyncio.Semaphore(0)
    release = asyncio.Event()
    asked: list[tuple[str, str]] = []

    def channel_for(user: str):
        async def channel(request: ApprovalRequest) -> bool:
            asked.append((user, request.reason))
            return True

        return channel

    async def probe() -> str:
        both_started.release()
        await release.wait()
        await require_approval("probe", reason=context_value("session_id", "?"))
        return context_value("session_id", "<unset>")

    registry = ToolRegistry([FunctionTool("probe", "d", probe)])

    async def session(user: str) -> list[str]:
        with use_tool_context(approval=channel_for(user), values={"session_id": user}):
            return _outputs(await _drive(registry, ["probe"]))

    async def main() -> list[list[str]]:
        tasks = [
            asyncio.ensure_future(session("alice")),
            asyncio.ensure_future(session("bob")),
        ]
        for _ in range(2):
            await both_started.acquire()
        release.set()
        return list(await asyncio.gather(*tasks))

    results = _run(main())

    assert results == [["alice"], ["bob"]]
    assert sorted(asked) == [("alice", "alice"), ("bob", "bob")]


def test_two_sessions_sharing_one_task_do_collide():
    """The hazard the convention exists to avoid, pinned as a fact.

    ``contextvars`` isolate per asyncio Task, not per coroutine call, so
    two sessions binding inside one shared task are **not** isolated: the
    later ``set`` wins and the earlier session's tools read the later
    session's channel. Written as a passing test rather than a comment
    because the convention "each top-level session gets its own Task" has
    no other enforcement, and a mechanism whose failure mode is undocumented
    gets refactored into production by someone who assumed it was safe.
    """
    alice = set_tool_context(ToolContext(values={"session_id": "alice"}))
    set_tool_context(ToolContext(values={"session_id": "bob"}))

    assert context_value("session_id") == "bob", "the later bind won"

    reset_tool_context(alice)
    assert context_value("session_id") is None


# ---- a human's thinking time is not the tool's budget -------------------


def test_a_slow_human_is_not_charged_to_the_tool_timeout():
    """A person slower than ``tool_timeout`` no longer fails the tool.

    ``engine/executor.py::_execute`` wraps the whole of
    ``executor.execute(call)`` in ``asyncio.timeout(config.tool_timeout)``
    while plan 0028 §4 Q4.3 puts the approval ``await`` *inside* the
    tool's own ``execute``, so the two nest the wrong way round. What
    closes the gap is the engine offering that budget's pause down the
    dispatch path — ``DeadlineAwareExecutor`` → ``ToolRegistry`` →
    ``pause_tool_timeout`` — and ``require_approval`` entering it around
    the round trip.

    The numbers are a ratio and not a measurement: the human takes twice
    ``tool_timeout``, which under the old behaviour cancelled the tool and
    told the model ``tool 'gated' timed out after 1s`` — a sentence that
    was false, since nothing ran long and nobody had answered.
    """
    asked: list[ApprovalRequest] = []

    async def slow_human(request: ApprovalRequest) -> bool:
        asked.append(request)
        await asyncio.sleep(2.0)
        return True

    ran: list[str] = []

    async def gated() -> str:
        await require_approval("gated")
        # One await of real work after the decision, and it is why this
        # test can fail. ``asyncio.Timeout`` fires only at an await point
        # and its ``__aexit__`` cancels the handler, so a tool that
        # returned here would not notice a deadline restored into the
        # past — which is the bug being fixed, wearing a different name.
        await asyncio.sleep(0.05)
        ran.append("yes")
        return "the irreversible thing"

    registry = ToolRegistry([FunctionTool("gated", "d", gated)])
    calls = [ToolCall(id="c0", name="gated", arguments="{}")]
    config = EngineConfig(tool_timeout=1.0)

    async def main() -> tuple[list[ToolResult | None], float]:
        results: list[ToolResult | None] = []
        with use_tool_context(approval=slow_human):
            started = asyncio.get_running_loop().time()
            async for _ in execute_tool_calls(registry, calls, config, results):
                pass
            return results, asyncio.get_running_loop().time() - started

    results, elapsed = _run(main())

    assert len(asked) == 1, "the human really was asked"
    assert ran == ["yes"], "and the tool ran once they agreed"
    assert results[0].is_error is False
    assert results[0].output == "the irreversible thing"
    assert elapsed >= 2.0, "the human's two seconds really were spent"


def _gated_registry(channel_target: list[asyncio.Future]) -> ToolRegistry:
    """One ``ASK`` tool whose approval is answered out of band.

    The request is parked on ``channel_target`` and the tool waits for
    whoever is willing to resolve it, which is the arrangement every
    Surface has: the thing that shows a prompt is not the thing that ran
    the tool.

    **The yield before the ask is the realistic part, not a contrivance.**
    An ``ASK`` tool has to know what it is asking about before it can
    describe it — ``edit_file`` reads the file so the prompt can carry the
    diff, ``web_fetch`` has a URL to normalise — so the request reaches
    the channel one scheduling turn after the tool started, by which time
    the turn's consumer has already taken ``TOOL_START`` and gone back to
    waiting. A tool that asks without yielding first parks its request
    before the consumer's first wakeup, and the hazard below does not
    arise for it.
    """

    async def channel(request: ApprovalRequest) -> bool:
        reply: asyncio.Future = asyncio.get_running_loop().create_future()
        channel_target.append(reply)
        return await reply

    async def gated() -> str:
        await asyncio.sleep(0)  # the work done before the prompt can be written
        await require_approval("gated")
        return "ran"

    registry = ToolRegistry([FunctionTool("gated", "d", gated)])
    registry.approval_channel = channel  # type: ignore[attr-defined]
    return registry


def test_a_consumer_servicing_approvals_from_its_own_task_completes():
    """The supported shape, and the one a Surface has to implement.

    The human takes longer than ``tool_timeout``, so this also needs the
    pause — but the load-bearing half is *who* answers: a Task of its
    own, which can run while the turn's consumer is suspended waiting for
    the next event.
    """
    parked: list[asyncio.Future] = []
    registry = _gated_registry(parked)
    calls = [ToolCall(id="c0", name="gated", arguments="{}")]

    async def approver() -> None:
        while not parked:
            await asyncio.sleep(0)
        await asyncio.sleep(0.4)
        parked[0].set_result(True)

    async def main() -> list[ToolResult | None]:
        results: list[ToolResult | None] = []
        with use_tool_context(approval=registry.approval_channel):
            servicing = asyncio.ensure_future(approver())
            config = EngineConfig(tool_timeout=0.2)
            async for _ in execute_tool_calls(registry, calls, config, results):
                pass
            await servicing
        return results

    results = _run(main())

    assert results[0] is not None and results[0].output == "ran"


def test_a_consumer_that_only_polls_for_approvals_between_events_hangs():
    """The hazard, pinned, because a paused call has no engine-side bound.

    The request is issued *after* the consumer has gone back to waiting
    for the next event, so a consumer that checks a queue between events
    and never awaits it sees nothing, and the two wait for each other. A
    ``tool_timeout`` of 0.1s does not rescue it: that budget is exactly
    what the pause has lifted.

    **If this test ever fails, read it before deleting it.** A completed
    turn here means either the pause stopped being applied — in which case
    the model is being told a tool timed out when nobody answered, and
    ``test_a_slow_human_is_not_charged_to_the_tool_timeout`` should have
    gone red too — or something grew an engine-side bound on a paused
    call, which would be a real improvement and wants this test rewritten
    rather than removed. The reference harness documents the same hazard
    in its own shape at ``stream.go:51-58``.
    """
    parked: list[asyncio.Future] = []
    registry = _gated_registry(parked)
    calls = [ToolCall(id="c0", name="gated", arguments="{}")]

    async def main() -> None:
        results: list[ToolResult | None] = []
        with use_tool_context(approval=registry.approval_channel):
            config = EngineConfig(tool_timeout=0.1)
            async for _ in execute_tool_calls(registry, calls, config, results):
                for reply in parked:  # polled, never awaited
                    if not reply.done():
                        reply.set_result(True)

    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(asyncio.wait_for(main(), 0.6))


def test_the_budget_resumes_once_the_human_has_answered():
    """The pause gives the clock back; it does not switch it off.

    The tightening half of the pair. Implemented as "disable the timeout
    and forget to restore it", the test above would still pass and this
    one would not: a tool that overruns ``tool_timeout`` **after** an
    approval is still cancelled and still reported as having run long,
    which here is the true sentence.
    """

    async def prompt_human(request: ApprovalRequest) -> bool:
        await asyncio.sleep(0.2)
        return True

    async def gated() -> str:
        await require_approval("gated")
        await asyncio.sleep(2.0)
        return "never reached"

    registry = ToolRegistry([FunctionTool("gated", "d", gated)])
    calls = [ToolCall(id="c0", name="gated", arguments="{}")]
    config = EngineConfig(tool_timeout=0.5)

    async def main() -> list[ToolResult | None]:
        results: list[ToolResult | None] = []
        with use_tool_context(approval=prompt_human):
            async for _ in execute_tool_calls(registry, calls, config, results):
                pass
        return results

    results = _run(main())

    assert results[0].is_error is True
    assert "timed out after 0.5s" in results[0].output
