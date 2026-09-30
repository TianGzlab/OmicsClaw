"""Conversations, queues, one Task each — and what survives a cancel.

Plan 0031 Q4, Q6, Q7, Q17 and traps 3, 3b, 4b, 9, 11. The doubles come
from ``test_turn_runner.py`` so that the app under test here is the same
real app: registry, engine and context assembly are never stubbed, only
the backend is.
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
import pathlib

import pytest

from omicsclaw.context import ContextBudget
from omicsclaw.entry.events import TurnEventType
from omicsclaw.entry.session import (
    DEFAULT_ABANDON_GRACE_S,
    InMemorySessionStore,
    QueueFull,
    RegistryClosed,
    Session,
    SessionRegistry,
    attach_sessions,
)
from omicsclaw.entry.turn import TurnHandle
from omicsclaw.provider import Completion
from omicsclaw.schema import Message, Role
from omicsclaw.tools.context import ApprovalDecision
from tests.entry.test_turn_runner import (  # type: ignore[import-not-found]
    Asking,
    Exploding,
    Scripted,
    Sleeping,
    calling,
    make_app,
)

WAIT_S = 5.0


class RecordingStore(InMemorySessionStore):
    """An in-memory store that counts saves and suspends on each one.

    The suspension is inherited and it is the point: a ``save`` awaited
    from inside a cancelled Task never completes, and a store that never
    yields would let that defect pass (plan 0031 trap 3b, and plan 0029's
    finding #6 before it).
    """

    def __init__(self) -> None:
        super().__init__()
        self.saved: list[tuple[str, int]] = []

    async def save(self, session: Session) -> None:
        await super().save(session)
        self.saved.append((session.session_id, len(session.history)))


class Canned:
    """A summarizer that answers in the shape compaction can parse.

    Records the prompt it was given, which is how "did the second
    compaction extend the first" is asked without reaching into
    :mod:`omicsclaw.context`'s internals.
    """

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def summarize(self, prompt: str, *, system: str) -> str:
        self.prompts.append(prompt)
        return (
            "## Anchors\n\n### User Intent\nship it\n\n"
            "## Summary\nthey discussed it at length"
        )


def registry_for(tmp_path: pathlib.Path, provider, *, store=None, **kwargs):
    """An app with a registry attached, and the registry itself."""
    tools = kwargs.pop("tools", None)
    overrides = {
        key: kwargs.pop(key)
        for key in tuple(kwargs)
        if key not in {"abandon_grace_s"}
    }
    app = make_app(tmp_path, provider, tools=tools, **overrides)
    attached = attach_sessions(app, store=store, **kwargs)
    assert attached.sessions is not None
    return attached, attached.sessions


async def drain(handle, *, timeout: float = WAIT_S):
    """Wait for one exchange to settle, bounded."""
    return await asyncio.wait_for(handle.wait(), timeout)


# ---- layering: session.py may import turn.py, never the reverse ---------


def test_the_turn_kernel_does_not_import_the_session_layer():
    """Plan 0031's file split, pinned where it can actually drift.

    ``turn.py`` owns one exchange and ``session.py`` owns the
    conversations that submit them, so the arrow points one way. A cycle
    would not fail at import time — Python tolerates plenty of them — it
    would fail later, as the moment somebody moves a constant.
    """
    source = pathlib.Path("omicsclaw/entry/turn.py").read_text(encoding="utf-8")
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
        elif isinstance(node, ast.ImportFrom):
            names.append("." * node.level)
        elif isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)

    assert not [name for name in names if "session" in name], names


# ---- Q7: queueing is a semantic, not a lock ----------------------------


def test_submit_hands_back_a_handle_before_anything_runs(tmp_path):
    _app, sessions = registry_for(
        tmp_path, Scripted(Message(role=Role.ASSISTANT, content="done"))
    )

    async def drive():
        handle = await asyncio.wait_for(sessions.submit("s1", "hi"), WAIT_S)
        state_at_submit = handle.state
        await drain(handle)
        return state_at_submit, handle

    state_at_submit, handle = asyncio.run(drive())

    assert state_at_submit == "queued"
    assert handle.state == "terminal"
    assert handle.terminal == "converged"
    assert handle.outcome is not None


def test_a_second_message_is_queued_and_says_how_many_are_ahead(tmp_path):
    _app, sessions = registry_for(
        tmp_path, Scripted(Message(role=Role.ASSISTANT, content="done"))
    )

    async def drive():
        first = await sessions.submit("s1", "one")
        second = await sessions.submit("s1", "two")
        queued = [
            frame
            for frame in second.stream.retained()
            if frame.type is TurnEventType.QUEUED
        ]
        await drain(first)
        await drain(second)
        return queued, first, second

    queued, first, second = asyncio.run(drive())

    assert len(queued) == 1
    assert queued[0].queued_ahead == 1
    assert first.terminal == "converged"
    assert second.terminal == "converged"


def test_a_full_queue_refuses_rather_than_accumulating(tmp_path):
    _app, sessions = registry_for(
        tmp_path,
        Scripted(Message(role=Role.ASSISTANT, content="done")),
        max_queued_per_session=1,
    )

    async def drive():
        first = await sessions.submit("s1", "one")
        await sessions.submit("s1", "two")
        with pytest.raises(QueueFull):
            await sessions.submit("s1", "three")
        await drain(first)

    asyncio.run(drive())


def test_a_queued_exchange_can_be_cancelled_before_it_starts(tmp_path):
    """Q7's last clause: a user who typed twice can take the second back."""
    sleeping = Sleeping()
    provider = Scripted(
        calling("sleep"), Message(role=Role.ASSISTANT, content="done")
    )
    _app, sessions = registry_for(tmp_path, provider, tools=[sleeping])

    async def drive():
        first = await sessions.submit("s1", "one")
        second = await sessions.submit("s1", "two")
        await asyncio.wait_for(sleeping.entered.wait(), WAIT_S)

        second.cancel()
        first.cancel()
        await drain(first)
        await drain(second)
        return second, provider.calls

    second, calls = asyncio.run(drive())

    assert second.terminal == "cancelled"
    last = second.stream.retained()[-1]
    assert last.type is TurnEventType.EXCHANGE_END
    assert last.terminal == "cancelled"
    assert calls == 1, "the cancelled exchange must never have reached the model"


# ---- Q6: serial within a session, concurrent across sessions -----------


def test_two_sessions_overlap_while_one_session_serializes(tmp_path):
    first_tool, second_tool = Sleeping(), Sleeping()
    app_one, sessions = registry_for(
        tmp_path,
        Scripted(calling("sleep"), Message(role=Role.ASSISTANT, content="done")),
        tools=[first_tool],
    )
    _app_two, other = registry_for(
        tmp_path,
        Scripted(calling("sleep"), Message(role=Role.ASSISTANT, content="done")),
        tools=[second_tool],
    )
    assert app_one.sessions is sessions

    async def drive():
        one = await sessions.submit("s1", "first")
        queued = await sessions.submit("s1", "second")
        two = await other.submit("s2", "elsewhere")

        await asyncio.wait_for(first_tool.entered.wait(), WAIT_S)
        await asyncio.wait_for(second_tool.entered.wait(), WAIT_S)
        overlapping = (one.state, two.state, queued.state)

        for handle in (one, queued, two):
            handle.cancel()
        for handle in (one, queued, two):
            await drain(handle)
        return overlapping

    one_state, two_state, queued_state = asyncio.run(drive())

    assert one_state == "running"
    assert two_state == "running", "a second session must not wait on the first"
    assert queued_state == "queued", "a second message must wait on the first"


# ---- trap 3 / 3b: cancellation, history and persistence ----------------


def test_a_cancelled_exchange_leaves_the_history_byte_identical(tmp_path):
    sleeping = Sleeping()
    store = RecordingStore()
    _app, sessions = registry_for(
        tmp_path,
        Scripted(calling("sleep"), Message(role=Role.ASSISTANT, content="done")),
        store=store,
        tools=[sleeping],
    )

    async def drive():
        seed = Session(
            session_id="s1", history=(Message.user("earlier"),)
        )
        await store.save(seed)
        before = seed.history

        handle = await sessions.submit("s1", "cancel me")
        await asyncio.wait_for(sleeping.entered.wait(), WAIT_S)
        handle.cancel()
        await drain(handle)
        return before, sessions.session("s1"), handle

    before, session, handle = asyncio.run(drive())

    assert handle.terminal == "cancelled"
    assert session is not None
    assert session.history is before, "a cancelled exchange must not rewrite history"
    assert [message.content for message in session.history] == ["earlier"]


def test_persistence_happens_after_the_cancelled_task_is_reaped(tmp_path):
    """Trap 3b: ``finally: await store.save`` inside the Task never runs.

    The store here suspends on every save, so an implementation that put
    the save in the exchange's own ``finally`` would be interrupted at
    that ``await`` and this assertion would find nothing written.
    """
    sleeping = Sleeping()
    store = RecordingStore()
    _app, sessions = registry_for(
        tmp_path,
        Scripted(calling("sleep"), Message(role=Role.ASSISTANT, content="done")),
        store=store,
        tools=[sleeping],
    )

    async def drive():
        handle = await sessions.submit("s1", "cancel me")
        await asyncio.wait_for(sleeping.entered.wait(), WAIT_S)
        handle.cancel()
        await drain(handle)

    asyncio.run(drive())

    assert store.saved == [("s1", 0)], "the registry did not persist after the reap"


def test_a_converged_exchange_stores_its_history(tmp_path):
    store = RecordingStore()
    _app, sessions = registry_for(
        tmp_path,
        Scripted(Message(role=Role.ASSISTANT, content="done")),
        store=store,
    )

    async def drive():
        await drain(await sessions.submit("s1", "one"))
        return sessions.session("s1")

    session = asyncio.run(drive())

    assert session is not None
    assert [m.role for m in session.history] == [Role.USER, Role.ASSISTANT]
    assert not any(m.role is Role.SYSTEM for m in session.history)
    assert store.saved == [("s1", 2)]


def test_a_failed_exchange_leaves_the_history_alone(tmp_path):
    store = RecordingStore()
    _app, sessions = registry_for(tmp_path, Exploding(), store=store)

    async def drive():
        handle = await sessions.submit("s1", "one")
        await drain(handle)
        return handle, sessions.session("s1")

    handle, session = asyncio.run(drive())

    assert handle.terminal == "failed"
    assert session is not None and session.history == ()
    assert store.saved == [("s1", 0)]


# ---- trap 1b, where trap 3b moved it: a store that raises ---------------


class Breaking(InMemorySessionStore):
    """A store that fails where the :class:`SessionStore` Protocol lets it.

    The Protocol exists so a later persistence layer satisfies it
    structurally, and the one implementation this step ships cannot fail
    — so every green test ran against a store with no failure mode, and
    the two ``await``\\ s the registry makes into it were unguarded.

    ``load`` and ``save`` break separately because they break at opposite
    ends of an exchange: ``load`` before a single frame exists, ``save``
    after the stream has already sealed.
    """

    def __init__(self, *, on_load: bool = False, on_save: bool = False) -> None:
        super().__init__()
        self.on_load = on_load
        self.on_save = on_save

    async def load(self, session_id: str) -> Session | None:
        if self.on_load:
            raise RuntimeError("the store is unreachable")
        return await super().load(session_id)

    async def save(self, session: Session) -> None:
        if self.on_save:
            raise RuntimeError("the store is read-only")
        await super().save(session)


async def frames_until_sealed(handle, *, timeout: float = WAIT_S):
    """Every frame of one exchange, bounded — the assertion is the bound.

    An unsealed stream leaves ``__anext__`` waiting on a queue nobody
    will ever put to, which is a REPL that has stopped responding and an
    SSE response that never ends. :func:`asyncio.wait_for` is how that
    hang becomes a failure instead of a suite that never finishes.
    """

    async def consume():
        collected = []
        async with handle.observe() as observation:
            async for frame in observation:
                collected.append(frame)
        return collected

    return await asyncio.wait_for(consume(), timeout)


def test_a_store_that_cannot_load_ends_the_exchange_rather_than_hanging(tmp_path):
    """Trap 1b: the terminal frame is owed however the exchange ended.

    ``load`` raises before the exchange has a Task, so nothing downstream
    would ever seal the stream or settle the handle — not a failed turn
    but a permanently open one. Persistence moved out of the exchange's
    Task under trap 3b; this is the obligation that had to move with it.
    """
    provider = Scripted(Message(role=Role.ASSISTANT, content="done"))
    _app, sessions = registry_for(
        tmp_path, provider, store=Breaking(on_load=True)
    )

    async def drive():
        handle = await sessions.submit("s1", "one")
        frames = await frames_until_sealed(handle)
        await drain(handle)
        return handle, frames

    handle, frames = asyncio.run(drive())

    assert handle.terminal == "failed"
    assert isinstance(handle.error, RuntimeError)
    assert frames[-1].type is TurnEventType.EXCHANGE_END
    assert frames[-1].terminal == "failed"
    assert provider.calls == 0


def test_a_store_that_cannot_save_still_settles_the_exchange(tmp_path):
    """The other end, where the frame has already gone out.

    ``save`` raises after the exchange's own ``finally`` sealed the
    stream on ``converged``, so the frame cannot be retracted and this
    checks the half that can still be got right: ``wait()`` returns. It
    used to be the line *after* the save, which meant a channel pump and
    a REPL both blocked on it forever.

    The verdict is ``failed`` and the sealed frame says ``converged``.
    They disagree on purpose — the answer was delivered, the history was
    not kept — and a surface that treats the handle as authoritative is
    the one that will not silently lose a conversation.
    """
    _app, sessions = registry_for(
        tmp_path,
        Scripted(Message(role=Role.ASSISTANT, content="done")),
        store=Breaking(on_save=True),
    )

    async def drive():
        handle = await sessions.submit("s1", "one")
        frames = await frames_until_sealed(handle)
        await drain(handle)
        return handle, frames

    handle, frames = asyncio.run(drive())

    assert handle.terminal == "failed"
    assert isinstance(handle.error, RuntimeError)
    assert frames[-1].type is TurnEventType.EXCHANGE_END
    assert frames[-1].terminal == "converged"


def test_a_lane_keeps_serving_after_a_store_failure(tmp_path):
    """One broken exchange must not strand the conversation behind it.

    A pump that dies with work still in :attr:`_Lane.waiting` leaves
    every queued exchange with no runner and no terminal frame, and
    ``lane.pump`` at ``None`` means nothing will ever pick them up. That
    is not one failed turn, it is a session that has stopped answering.
    """
    store = Breaking(on_save=True)
    _app, sessions = registry_for(
        tmp_path,
        Scripted(Message(role=Role.ASSISTANT, content="done")),
        store=store,
    )

    async def drive():
        first = await sessions.submit("s1", "one")
        second = await sessions.submit("s1", "two")
        await drain(first)
        store.on_save = False
        await drain(second)
        return first, second

    first, second = asyncio.run(drive())

    assert first.terminal == "failed"
    assert second.terminal == "converged", "the lane stopped after one failure"


# ---- R3: a cancel that arrives while the registry is loading -----------


class Wedging(InMemorySessionStore):
    """A store whose ``load`` waits to be let go.

    Holds the registry inside the one window where an exchange has been
    accepted, has no Task yet, and is therefore cancellable only through
    :attr:`TurnHandle.terminal`.
    """

    def __init__(self) -> None:
        super().__init__()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def load(self, session_id: str) -> Session | None:
        self.entered.set()
        await self.release.wait()
        return await super().load(session_id)


def test_a_cancel_arriving_during_the_load_is_not_discarded(tmp_path):
    """Three ordinary paths reach this window; all three used to lose.

    A ``Ctrl-C`` typed straight after a submission, trap 9's grace timer
    firing, and ``shutdown`` cancelling a queued exchange all call
    :meth:`TurnHandle.cancel` on a handle whose ``_task`` is still
    ``None``. That call can only set ``terminal``, and the registry read
    it once — before the ``await`` — so the exchange ran anyway, called
    the model, rewrote the history and replaced ``cancelled`` with
    ``converged``.
    """
    store = Wedging()
    provider = Scripted(Message(role=Role.ASSISTANT, content="done"))
    _app, sessions = registry_for(tmp_path, provider, store=store)

    async def drive():
        handle = await sessions.submit("s1", "take it back")
        await asyncio.wait_for(store.entered.wait(), WAIT_S)
        handle.cancel()
        store.release.set()
        frames = await frames_until_sealed(handle)
        await drain(handle)
        return handle, frames

    handle, frames = asyncio.run(drive())

    assert handle.terminal == "cancelled"
    assert provider.calls == 0, "a cancelled exchange must never reach the model"
    assert frames[-1].type is TurnEventType.EXCHANGE_END
    assert frames[-1].terminal == "cancelled"
    assert sessions.session("s1") is not None
    assert sessions.session("s1").history == ()


# ---- trap 4b: the compaction state is carried between exchanges --------


def test_a_second_compaction_extends_the_first_instead_of_restarting(tmp_path):
    """The whole cost of not storing :attr:`Session.compaction`.

    Without it the second compaction starts from ``FIRST_TEMPLATE`` with
    a blank page: it pays for a summary of material already summarized
    and loses whatever the first pass chose to keep.
    """
    canned = Canned()
    # ``memory=False`` and ``subagents=False`` keep the tier reachable:
    # ``measure`` reserves what the tool declarations cost, so the two
    # memory tools or the ``task`` tool would tip this history into
    # ``emergency``, where no summarizer is called at all.
    app = make_app(
        tmp_path,
        Scripted(Message(role=Role.ASSISTANT, content="done")),
        memory=False,
        subagents=False,
    )
    app = dataclasses.replace(
        app,
        summarizer=canned,
        budget=ContextBudget(
            context_tokens=9_000,
            reserve_output_tokens=200,
            reserve_tool_tokens=200,
        ),
    )
    attached = attach_sessions(app)
    sessions = attached.sessions
    assert sessions is not None

    def bulk() -> tuple[Message, ...]:
        """Enough conversation to reach ``full`` — not ``emergency``.

        At ``emergency`` compaction never calls a summarizer at all (the
        tier exists because there is no room left to spend a round trip
        in), so this is the only tier at which the question can be asked.
        """
        messages: list[Message] = []
        for index in range(30):
            messages.append(Message.user(f"question {index} " + "q" * 300))
            messages.append(Message.assistant("answer " + "a" * 300))
        return tuple(messages)

    async def drive():
        session = Session(session_id="s1", history=bulk())
        await sessions._store.save(session)

        first = await sessions.submit("s1", "next")
        await drain(first)

        # Re-inflate the conversation so the second exchange reaches the
        # same tier. Compaction is what shrank it, which is the point —
        # what has to survive between the two is the *state*, not the
        # size.
        live = sessions.session("s1")
        assert live is not None
        live.history = bulk()

        second = await sessions.submit("s1", "next again")
        await drain(second)
        return first, second, sessions.session("s1")

    first, second, session = asyncio.run(drive())

    assert first.outcome is not None and first.outcome.compaction is not None
    assert second.outcome is not None and second.outcome.compaction is not None
    assert len(canned.prompts) == 2
    assert "<previous-compaction>" not in canned.prompts[0]
    assert "<previous-compaction>" in canned.prompts[1], (
        "the second compaction started from a blank page"
    )
    assert session is not None and session.compaction.summary


# ---- trap 9: the last observer leaving, not any iterator breaking -------


def test_one_observer_leaving_does_not_kill_the_exchange(tmp_path):
    sleeping = Sleeping()
    _app, sessions = registry_for(
        tmp_path,
        Scripted(calling("sleep"), Message(role=Role.ASSISTANT, content="done")),
        tools=[sleeping],
        abandon_grace_s=0.02,
    )

    async def drive():
        handle = await sessions.submit("s1", "watch me")
        staying = handle.observe()
        leaving = handle.observe()
        await asyncio.wait_for(sleeping.entered.wait(), WAIT_S)

        await leaving.aclose()
        await asyncio.sleep(0.1)  # longer than the grace period
        still_running = handle.state

        await staying.aclose()
        await drain(handle)
        return still_running, handle

    still_running, handle = asyncio.run(drive())

    assert still_running == "running", "a browser refresh must not kill an exchange"
    assert handle.terminal == "cancelled"


def test_an_exchange_nobody_ever_watched_is_not_abandoned(tmp_path):
    """Submit-and-await is a legitimate shape; it never observes at all."""
    _app, sessions = registry_for(
        tmp_path,
        Scripted(Message(role=Role.ASSISTANT, content="done")),
        abandon_grace_s=0.01,
    )

    async def drive():
        handle = await sessions.submit("s1", "hi")
        await asyncio.sleep(0.05)
        await drain(handle)
        return handle

    assert asyncio.run(drive()).terminal == "converged"


@pytest.mark.parametrize("grace", [600.0, 0.02, None])
def test_the_registry_reports_the_grace_it_was_built_with(tmp_path, grace):
    """``/health`` publishes this, so it must be the value in force,
    ``None`` included: that registry never cancels an unwatched exchange."""
    _app, sessions = registry_for(
        tmp_path,
        Scripted(Message(role=Role.ASSISTANT, content="done")),
        abandon_grace_s=grace,
    )

    assert sessions.abandon_grace_s == grace


def test_the_registry_reports_the_default_grace_when_none_was_named(tmp_path):
    _app, sessions = registry_for(
        tmp_path, Scripted(Message(role=Role.ASSISTANT, content="done"))
    )

    assert sessions.abandon_grace_s == DEFAULT_ABANDON_GRACE_S


def test_the_cancelled_task_is_reaped_rather_than_left_unretrieved(tmp_path):
    """Trap 9's second half, and Y14d.

    An un-awaited cancelled Task prints "Task exception was never
    retrieved" from the garbage collector, into a log nobody is reading.
    The handle reaching a terminal state at all is the observable proof
    the registry waited for the Task instead of walking away from it.
    """
    sleeping = Sleeping()
    _app, sessions = registry_for(
        tmp_path,
        Scripted(calling("sleep"), Message(role=Role.ASSISTANT, content="done")),
        tools=[sleeping],
    )

    async def drive():
        handle = await sessions.submit("s1", "hi")
        await asyncio.wait_for(sleeping.entered.wait(), WAIT_S)
        handle.cancel()
        await drain(handle)
        assert handle._task is not None
        return handle._task

    task = asyncio.run(drive())

    assert task.done()
    assert task.cancelled()


# ---- Q18 / trap 11: approving is idempotent and forgiving --------------


def test_approving_a_finished_exchange_does_not_raise(tmp_path):
    _app, sessions = registry_for(
        tmp_path, Scripted(Message(role=Role.ASSISTANT, content="done"))
    )

    async def drive():
        handle = await sessions.submit("s1", "hi")
        await drain(handle)
        await handle.approve("whatever", ApprovalDecision(approved=True))

    asyncio.run(drive())


def test_approving_reaches_the_tool_through_the_handle(tmp_path):
    """The path a surface actually uses: a frame in, a decision back."""
    _app, sessions = registry_for(
        tmp_path,
        Scripted(calling("ask"), Message(role=Role.ASSISTANT, content="done")),
        tools=[Asking("ask")],
    )

    async def answer(handle):
        async with handle.observe() as observation:
            async for frame in observation:
                if frame.type is TurnEventType.APPROVAL_REQUIRED:
                    await handle.approve(
                        frame.request_id, ApprovalDecision(approved=True)
                    )

    async def drive():
        handle = await sessions.submit("s1", "go")
        watcher = asyncio.create_task(answer(handle))
        await drain(handle)
        await asyncio.wait_for(watcher, WAIT_S)
        return handle

    handle = asyncio.run(drive())

    assert handle.outcome is not None
    observations = [
        m for m in handle.outcome.result.messages if m.role is Role.TOOL
    ]
    assert len(observations) == 1
    assert not observations[0].is_error


# ---- Q24: the same source_request_id is the same exchange --------------


def test_a_redelivered_message_resolves_to_the_same_exchange(tmp_path):
    _app, sessions = registry_for(
        tmp_path, Scripted(Message(role=Role.ASSISTANT, content="done"))
    )

    async def drive():
        first = await sessions.submit("s1", "hi", source_request_id="req-1")
        again = await sessions.submit("s1", "hi", source_request_id="req-1")
        await drain(first)
        return first, again

    first, again = asyncio.run(drive())

    assert again is first


def test_the_same_key_in_two_conversations_is_two_exchanges(tmp_path):
    """The idempotency key is scoped to a session, not to the process.

    A surface is free to number its requests per conversation — a message
    sequence number, a per-chat counter — so one id landing in two
    sessions is ordinary rather than exotic. A global index answers the
    second one with the *first* session's handle, and the caller then
    observes a conversation it never submitted to: its deltas, its tool
    arguments and its tool outputs, which is what ``/chat/stream``
    returns to whoever asked.
    """
    _app, sessions = registry_for(
        tmp_path, Scripted(Message(role=Role.ASSISTANT, content="done"))
    )

    async def drive():
        first = await sessions.submit("s1", "mine", source_request_id="seq-1")
        second = await sessions.submit("s2", "theirs", source_request_id="seq-1")
        await drain(first)
        await drain(second)
        return first, second

    first, second = asyncio.run(drive())

    assert first is not second
    assert first.session_id == "s1"
    assert second.session_id == "s2"
    assert second.text == "theirs", "the caller was handed another session's turn"


def test_two_messages_without_an_idempotency_key_are_two_exchanges(tmp_path):
    _app, sessions = registry_for(
        tmp_path, Scripted(Message(role=Role.ASSISTANT, content="done"))
    )

    async def drive():
        first = await sessions.submit("s1", "hi")
        second = await sessions.submit("s1", "hi")
        await drain(first)
        await drain(second)
        return first, second

    first, second = asyncio.run(drive())

    assert first.turn_id != second.turn_id


# ---- reconnecting by id -------------------------------------------------


def test_an_exchange_can_be_reopened_by_id_from_a_cursor(tmp_path):
    """The desktop reconnect: a new request, an old turn id, a cursor."""
    _app, sessions = registry_for(
        tmp_path, Scripted(Message(role=Role.ASSISTANT, content="done"))
    )

    async def drive():
        handle = await sessions.submit("s1", "hi")
        await drain(handle)
        replay = sessions.observe(handle.turn_id, after_seq=1)
        frames = [frame async for frame in replay]
        return handle, frames

    handle, frames = asyncio.run(drive())

    assert frames[0].seq == 2
    assert frames[-1].type is TurnEventType.EXCHANGE_END
    with pytest.raises(KeyError):
        sessions.observe("never-issued")


# ---- Q17: shutdown ------------------------------------------------------


def test_shutdown_stops_admitting_and_drains_what_is_running(tmp_path):
    app, sessions = registry_for(
        tmp_path, Scripted(Message(role=Role.ASSISTANT, content="done"))
    )

    async def drive():
        handle = await sessions.submit("s1", "hi")
        await asyncio.wait_for(app.aclose(), WAIT_S)
        with pytest.raises(RegistryClosed):
            await sessions.submit("s1", "after")
        return handle

    handle = asyncio.run(drive())

    assert handle.terminal == "converged", "a running exchange gets its grace"


def test_shutdown_cancels_what_outlives_the_grace_and_reaps_it(tmp_path):
    sleeping = Sleeping()
    _app, sessions = registry_for(
        tmp_path,
        Scripted(calling("sleep"), Message(role=Role.ASSISTANT, content="done")),
        tools=[sleeping],
    )

    async def drive():
        handle = await sessions.submit("s1", "hi")
        await asyncio.wait_for(sleeping.entered.wait(), WAIT_S)
        await asyncio.wait_for(sessions.shutdown(0.05), WAIT_S)
        return handle

    handle = asyncio.run(drive())

    assert handle.terminal == "cancelled"
    assert handle.stream.sealed, "the terminal frame is owed even at shutdown"


def test_shutdown_cancels_what_was_still_queued(tmp_path):
    sleeping = Sleeping()
    _app, sessions = registry_for(
        tmp_path,
        Scripted(calling("sleep"), Message(role=Role.ASSISTANT, content="done")),
        tools=[sleeping],
    )

    async def drive():
        running = await sessions.submit("s1", "one")
        queued = await sessions.submit("s1", "two")
        await asyncio.wait_for(sleeping.entered.wait(), WAIT_S)
        await asyncio.wait_for(sessions.shutdown(0.05), WAIT_S)
        return running, queued

    running, queued = asyncio.run(drive())

    assert running.terminal == "cancelled"
    assert queued.terminal == "cancelled"
    assert queued.stream.sealed


def test_shutdown_settles_an_exchange_whose_pump_it_had_to_cancel(tmp_path):
    """Even the store can be what shutdown runs out of patience with.

    A pump cancelled inside its own ``await store.save`` never reaches
    the line that settles the handle, which would leave an SSE stream
    without an ending and a ``wait()`` that never returns.
    """

    class Hanging(InMemorySessionStore):
        async def save(self, session: Session) -> None:
            await asyncio.sleep(30)

    sleeping = Sleeping()
    _app, sessions = registry_for(
        tmp_path,
        Scripted(calling("sleep"), Message(role=Role.ASSISTANT, content="done")),
        store=Hanging(),
        tools=[sleeping],
    )

    async def drive():
        handle = await sessions.submit("s1", "hi")
        await asyncio.wait_for(sleeping.entered.wait(), WAIT_S)
        await asyncio.wait_for(sessions.shutdown(0.02), WAIT_S)
        await drain(handle, timeout=1.0)
        return handle

    handle = asyncio.run(drive())

    assert handle.terminal == "cancelled"
    assert handle.stream.sealed


def test_shutdown_leaves_no_exchange_running_behind_a_cancelled_pump(tmp_path):
    """Cancelling an :func:`asyncio.wait` does not cancel what it waits on.

    The registry waits on the exchange's Task rather than awaiting it, so
    that a cancelled exchange cannot cancel the pump that still has to
    persist. The cost is this: a pump cancelled *inside* that wait walks
    away and the Task keeps running — against a registry that is closing,
    with tools that may still write files. The exchange's Task has to be
    cancelled from the pump's own ``finally``.

    ``Reluctant`` takes two cancellations because one is what the ordinary
    path already delivers; a tool that stops at the first would leave this
    test green either way.
    """

    class Reluctant(Sleeping):
        """Absorbs its first cancellation and sleeps again."""

        def __init__(self) -> None:
            super().__init__()
            self.absorbed = asyncio.Event()

        async def execute(self, arguments: str) -> str:
            self.entered.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                self.absorbed.set()
                await asyncio.sleep(30)
            return "slept"

    reluctant = Reluctant()
    _app, sessions = registry_for(
        tmp_path,
        Scripted(calling("sleep"), Message(role=Role.ASSISTANT, content="done")),
        tools=[reluctant],
    )

    async def drive():
        handle = await sessions.submit("s1", "hi")
        await asyncio.wait_for(reluctant.entered.wait(), WAIT_S)
        await asyncio.wait_for(sessions.shutdown(0.02), WAIT_S)
        # Read inside the loop: :func:`asyncio.run` cancels whatever is
        # left when the coroutine returns, so a leak asserted afterwards
        # has already been cleaned up by the thing under test's caller.
        return handle, handle._task is not None and handle._task.done()

    handle, settled = asyncio.run(drive())

    assert reluctant.absorbed.is_set(), "the tool never saw a first cancellation"
    assert settled, "the exchange outlived the pump that started it"
    assert handle.terminal == "cancelled"


def test_shutdown_settles_a_stranded_handle_on_the_quiet_path_too(tmp_path):
    """The backstop has to run where nothing needed cancelling.

    ``_close_out`` was the last statement of the branch that cancels a
    lane, so both early returns above it skipped it — and the case it
    exists for, a pump that stopped without settling what it was
    carrying, is a case where no pump is pending and the *first* early
    return is taken. A handle nobody settles is a ``wait()`` that never
    returns and a stream with no ending.

    The handle is planted in the retention index directly because every
    path that would strand one is now guarded; the backstop is still
    owed, and a guard is not a reason to delete the thing behind it.
    """
    _app, sessions = registry_for(
        tmp_path, Scripted(Message(role=Role.ASSISTANT, content="done"))
    )
    stranded = TurnHandle(session_id="s1", turn_id="t1", text="hi")
    sessions._handles["t1"] = stranded

    asyncio.run(asyncio.wait_for(sessions.shutdown(0.01), WAIT_S))

    assert stranded.done
    assert stranded.terminal == "cancelled"
    assert stranded.stream.sealed


def test_shutting_down_an_idle_registry_is_a_no_op(tmp_path):
    app, _sessions = registry_for(
        tmp_path, Scripted(Message(role=Role.ASSISTANT, content="done"))
    )

    asyncio.run(asyncio.wait_for(app.aclose(), WAIT_S))


# ---- the store Protocol -------------------------------------------------


def test_the_in_memory_store_round_trips_a_session():
    store = InMemorySessionStore()

    async def drive():
        assert await store.load("s1") is None
        await store.save(Session(session_id="s1", history=(Message.user("hi"),)))
        loaded = await store.load("s1")
        listed = await store.list()
        return loaded, listed

    loaded, listed = asyncio.run(drive())

    assert loaded is not None and len(loaded.history) == 1
    assert [session.session_id for session in listed] == ["s1"]


def test_the_in_memory_store_lists_by_updated_at_not_by_save_order():
    """The protocol's order is the field's, which the SQLite store also reads."""
    store = InMemorySessionStore()

    async def drive():
        await store.save(Session(session_id="late", updated_at=900.0))
        await store.save(Session(session_id="early", updated_at=100.0))
        await store.save(Session(session_id="middle", updated_at=500.0))
        return await store.list()

    listed = asyncio.run(drive())

    assert [s.session_id for s in listed] == ["late", "middle", "early"]


def test_the_registry_stamps_each_save_so_the_last_conversation_used_leads(
    tmp_path,
):
    """A conversation spoken in again moves back to the top of the list.

    ``s1`` is created first, ``s2`` second, and then ``s1`` is used again:
    ordered by creation the list would still put ``s2`` first.
    """
    _app, sessions = registry_for(tmp_path, Scripted(), store=InMemorySessionStore())

    async def drive():
        await drain(await sessions.submit("s1", "one"))
        stamped = sessions.session("s1").updated_at
        await drain(await sessions.submit("s2", "two"))
        await drain(await sessions.submit("s1", "three"))
        listed = await sessions.list_sessions()
        return stamped, [s.session_id for s in listed], listed[0].updated_at

    stamped, order, latest = asyncio.run(drive())

    assert order == ["s1", "s2"]
    assert latest > stamped


def test_a_registry_takes_a_store_that_only_satisfies_the_protocol(tmp_path):
    """Structural conformance: the later memory layer will not subclass."""

    class Elsewhere:
        def __init__(self) -> None:
            self.sessions: dict[str, Session] = {}

        async def load(self, session_id: str):
            await asyncio.sleep(0)
            return self.sessions.get(session_id)

        async def save(self, session: Session) -> None:
            await asyncio.sleep(0)
            self.sessions[session.session_id] = session

        async def list(self, limit: int = 50):
            await asyncio.sleep(0)
            return tuple(self.sessions.values())[:limit]

    store = Elsewhere()
    _app, sessions = registry_for(
        tmp_path,
        Scripted(Message(role=Role.ASSISTANT, content="done")),
        store=store,
    )

    async def drive():
        await drain(await sessions.submit("s1", "hi"))

    asyncio.run(drive())

    assert "s1" in store.sessions
    assert len(store.sessions["s1"].history) == 2


def test_the_cap_evicts_an_idle_session_and_never_a_busy_one(tmp_path):
    """Q6: eviction is a cache policy, and history is not a cache.

    A session with an exchange running or queued is never the victim
    however old it is — dropping it would throw away the history the
    exchange in flight is about to be written into.
    """
    class Routing(Scripted):
        """Answers from the message rather than from a call counter.

        Three sessions share one backend here, so a scripted list would
        hand session two the reply written for session one.
        """

        async def generate(self, messages, tools=None):
            self.seen.append(tuple(messages))
            self.calls += 1
            last = messages[-1]
            if last.role is Role.USER and "sleep" in (last.content or ""):
                return Completion(message=calling("sleep"))
            return Completion(message=Message(role=Role.ASSISTANT, content="done"))

    sleeping = Sleeping()
    _app, sessions = registry_for(
        tmp_path, Routing(), tools=[sleeping], max_sessions=1
    )

    async def drive():
        await drain(await sessions.submit("idle", "hello"))
        assert sessions.session("idle") is not None

        busy = await sessions.submit("busy", "sleep on it")
        await asyncio.wait_for(sleeping.entered.wait(), WAIT_S)
        await drain(await sessions.submit("newcomer", "hello"))
        survived = sessions.session("busy") is not None

        busy.cancel()
        await drain(busy)
        return survived, sessions.session("idle"), sessions.session("newcomer")

    survived, idle, newcomer = asyncio.run(drive())

    assert survived, "a session with an exchange in flight is never evicted"
    assert idle is None, "the least recently used idle session was not evicted"
    assert newcomer is not None


def test_the_registry_is_the_one_mutable_thing_on_an_app(tmp_path):
    app, sessions = registry_for(
        tmp_path, Scripted(Message(role=Role.ASSISTANT, content="done"))
    )

    assert isinstance(sessions, SessionRegistry)
    assert app.sessions is sessions
    assert sessions._app is app, "the registry holds the attached app"
