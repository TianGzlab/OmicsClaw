"""Who gets in, and what a refusal costs — the channel surface's front door.

Plan 0031 §9-9, which is written the way it is because of plan 0028's
lesson: *having a test is not the same as being connected*. So every
assertion here is about the **tightening** direction, and the two that
matter most assert that the session registry was **not called** rather than
that a polite refusal came back. A bot that answers "you are not allowed"
has already told an unknown sender that it exists, that their identity was
checked, and that somebody is listening.

The rules: ``FEISHU_ALLOWED_SENDERS`` is *required*, authoritative Feishu
ingress admits nobody else and refuses to start without it, and without
``FEISHU_BOT_OPEN_ID`` group chats fail closed.
"""

from __future__ import annotations

import asyncio
import dataclasses
import pathlib

import pytest

from omicsclaw.entry.channel.binding import (
    DEFAULT_TEXT_CHUNK_LIMIT,
    ChannelSurfaceBinding,
)
from omicsclaw.entry.channel.delivery import (
    DeliveryAdapterResult,
    DeliveryAttemptOutcome,
)
from omicsclaw.entry.channel.runtime import (
    CODE_NOT_STARTED,
    CODE_OWNER_DENIED,
    CODE_QUEUE_FULL,
    CODE_UNKNOWN_ADAPTER,
    VALUE_REPLY_TARGET,
    ChannelRuntime,
    TurnAcceptanceStatus,
)
from omicsclaw.entry.ingress import (
    VALUE_CHAT_TYPE,
    VALUE_MENTIONS,
    InboundMessage,
    SenderPolicy,
)
from omicsclaw.entry.session import attach_sessions
from tests.entry.test_turn_runner import (  # type: ignore[import-not-found]
    Scripted,
    make_app,
)

WAIT_S = 5.0
"""Every await in this file is bounded by it: a surface defect is a hang,
and there is no timeout plugin on this machine."""

OWNER = "ou_owner"
BOT = "ou_bot"


class Transport:
    """A delivery adapter that records instead of reaching a platform.

    There is no network and no token on this machine, so "the reply left"
    is only ever observable as *this object was called with that text*.
    """

    def __init__(self, outcome: DeliveryAttemptOutcome | None = None) -> None:
        self.outcome = outcome or DeliveryAttemptOutcome.ACCEPTED
        self.sent: list[str] = []
        self.requests: list[object] = []

    async def __call__(self, request) -> DeliveryAdapterResult:
        self.requests.append(request)
        self.sent.append(request.text)
        return DeliveryAdapterResult(outcome=self.outcome)


class SpyRegistry:
    """The real registry, wrapped so "was it called" is answerable.

    Wrapping rather than faking: the tests that assert an exchange *did*
    run need the real thing, and two objects with different behaviour would
    make the refusal tests prove nothing about the accepting path.
    """

    def __init__(self, inner) -> None:
        self.inner = inner
        self.delivered: list[InboundMessage] = []
        self.submitted: list[tuple[str, str]] = []

    async def deliver(self, message: InboundMessage):
        self.delivered.append(message)
        return await self.inner.deliver(message)

    async def submit(self, session_id: str, text: str, **kwargs):
        self.submitted.append((session_id, text))
        return await self.inner.submit(session_id, text, **kwargs)

    def handle(self, turn_id: str):
        return self.inner.handle(turn_id)

    def session(self, session_id: str):
        return self.inner.session(session_id)

    def running(self):
        return self.inner.running()

    async def shutdown(self, grace_s: float) -> None:
        await self.inner.shutdown(grace_s)


def binding_for(transport: Transport, **kwargs) -> ChannelSurfaceBinding:
    policy = kwargs.pop(
        "sender_policy",
        SenderPolicy(allowed_senders=frozenset({OWNER}), bot_identity=BOT),
    )
    return ChannelSurfaceBinding(
        adapter=kwargs.pop("adapter", "feishu"),
        account_namespace=kwargs.pop("account_namespace", "cli_test"),
        sender_policy=policy,
        delivery_adapter=transport,
        **kwargs,
    )


def deployment(tmp_path: pathlib.Path, provider=None, **overrides):
    """A real app with a spied registry, plus a transport and a binding."""
    overrides.setdefault("approval_timeout_s", WAIT_S)
    app = make_app(tmp_path, provider or Scripted(), tools=(), **overrides)
    attached = attach_sessions(app)
    spy = SpyRegistry(attached.sessions)
    return dataclasses.replace(attached, sessions=spy), spy


def message(text: str = "analyse this", **kwargs) -> InboundMessage:
    values = {VALUE_REPLY_TARGET: {"adapter": "feishu", "destination_id": "c1"}}
    values.update(kwargs.pop("values", {}))
    return InboundMessage(
        text=text,
        session_id=kwargs.pop("session_id", "feishu:c1"),
        source_request_id=kwargs.pop("source_request_id", "om_1"),
        sender=kwargs.pop("sender", OWNER),
        surface=kwargs.pop("surface", "feishu"),
        values=values,
    )


async def runtime_for(app, binding, **kwargs) -> ChannelRuntime:
    runtime = ChannelRuntime(app, [binding], **kwargs)
    await runtime.start()
    return runtime


# ---- §9-9 (a): no policy, no surface -----------------------------------


def test_a_binding_without_a_sender_policy_cannot_be_built():
    """Plan 0031 §9-9 (a): ingress refuses to start without an allowlist.

    The allowlist is a **positional** field with no default, so omitting it
    is a :exc:`TypeError` before any message exists. A keyword with a
    default is a keyword somebody leaves out, and the deployment that
    leaves it out does not look broken — it looks popular.
    """
    with pytest.raises(TypeError):
        ChannelSurfaceBinding(  # type: ignore[call-arg]
            adapter="feishu",
            account_namespace="cli_test",
            delivery_adapter=Transport(),
        )


def test_an_empty_allowlist_is_refused_rather_than_admitting_nobody():
    """An allowlist of nobody is indistinguishable from an unused bot."""
    with pytest.raises(ValueError):
        SenderPolicy(allowed_senders=frozenset())


def test_a_binding_refuses_a_policy_shaped_object_that_is_not_one():
    """The type is the contract: a dict of owners is not a fail-closed gate."""
    with pytest.raises(TypeError):
        ChannelSurfaceBinding(
            adapter="feishu",
            account_namespace="cli_test",
            sender_policy={"owners": [OWNER]},  # type: ignore[arg-type]
            delivery_adapter=Transport(),
        )


def test_a_binding_refuses_to_advertise_attachment_input(tmp_path):
    """Plan 0031 §5.3 discards the photo path; the flag must say so.

    Kept rather than deleted because a binding is where a future
    attachment cutover would announce itself, and a silently ignored
    ``True`` would read as support for something that is dropped.
    """
    with pytest.raises(ValueError):
        binding_for(Transport(), attachment_input_enabled=True)


# ---- §9-9 (b): a stranger creates no exchange --------------------------


def test_a_sender_outside_the_allowlist_creates_no_exchange(tmp_path):
    """Plan 0031 §9-9 (b). The assertion is about what did **not** happen.

    ``SessionRegistry.deliver`` is not called, so there is no history, no
    model call, no queue slot and nothing to cancel. Asserting on a refusal
    sentence instead would pass just as happily against an implementation
    that ran the exchange and then apologised.
    """

    async def scenario():
        app, spy = deployment(tmp_path)
        runtime = await runtime_for(app, binding_for(Transport()))
        result = await runtime.submit(message(sender="ou_stranger"))
        await runtime.close(0.0)
        return result, spy

    result, spy = asyncio.run(asyncio.wait_for(scenario(), WAIT_S))

    assert spy.delivered == []
    assert spy.submitted == []
    assert result.handle is None
    assert result.acceptance.status is TurnAcceptanceStatus.REJECTED
    assert result.acceptance.code == CODE_OWNER_DENIED


def test_an_unidentified_sender_creates_no_exchange(tmp_path):
    """An empty sender is never on an allowlist, whatever the allowlist is.

    The case a platform produces when it cannot attribute a message, which
    is precisely when guessing is worst.
    """

    async def scenario():
        app, spy = deployment(tmp_path)
        runtime = await runtime_for(app, binding_for(Transport()))
        result = await runtime.submit(message(sender=""))
        await runtime.close(0.0)
        return result, spy

    result, spy = asyncio.run(asyncio.wait_for(scenario(), WAIT_S))

    assert spy.delivered == []
    assert result.acceptance.code == CODE_OWNER_DENIED


# ---- §9-9 (c): an unproven group mention creates no exchange -----------


def test_a_group_message_that_mentions_nobody_creates_no_exchange(tmp_path):
    """Plan 0031 §9-9 (c). The sender is an owner; the message is not ours.

    This is the case that makes the rule worth having: the person is on the
    allowlist, so gate one passes, and the message was simply not addressed
    to this agent.
    """

    async def scenario():
        app, spy = deployment(tmp_path)
        runtime = await runtime_for(app, binding_for(Transport()))
        result = await runtime.submit(
            message(values={VALUE_CHAT_TYPE: "group", VALUE_MENTIONS: ()})
        )
        await runtime.close(0.0)
        return result, spy

    result, spy = asyncio.run(asyncio.wait_for(scenario(), WAIT_S))

    assert spy.delivered == []
    assert result.acceptance.code == CODE_OWNER_DENIED


def test_a_group_message_mentioning_another_human_creates_no_exchange(tmp_path):
    """A non-empty mention list is not proof; the bot must be *in* it."""

    async def scenario():
        app, spy = deployment(tmp_path)
        runtime = await runtime_for(app, binding_for(Transport()))
        result = await runtime.submit(
            message(
                values={
                    VALUE_CHAT_TYPE: "group",
                    VALUE_MENTIONS: ("ou_colleague",),
                }
            )
        )
        await runtime.close(0.0)
        return result, spy

    result, spy = asyncio.run(asyncio.wait_for(scenario(), WAIT_S))

    assert spy.delivered == []
    assert result.acceptance.code == CODE_OWNER_DENIED


def test_a_group_message_fails_closed_without_a_bot_identity(tmp_path):
    """``FEISHU_BOT_OPEN_ID`` absent: every group message is refused.

    Not "mentions are ignored in groups" — refused. Without an identity to
    match, a mention of anyone would otherwise be read as a mention of us.
    """

    async def scenario():
        app, spy = deployment(tmp_path)
        policy = SenderPolicy(allowed_senders=frozenset({OWNER}))
        runtime = await runtime_for(app, binding_for(Transport(), sender_policy=policy))
        result = await runtime.submit(
            message(values={VALUE_CHAT_TYPE: "group", VALUE_MENTIONS: (BOT,)})
        )
        await runtime.close(0.0)
        return result, spy

    result, spy = asyncio.run(asyncio.wait_for(scenario(), WAIT_S))

    assert spy.delivered == []
    assert result.acceptance.code == CODE_OWNER_DENIED


def test_a_group_message_that_mentions_this_bot_does_run(tmp_path):
    """The other direction, so the gate above is not passing vacuously.

    A rule that refuses everything satisfies every refusal test in this
    file and is useless; this is the test that makes those mean something.
    """

    async def scenario():
        app, spy = deployment(tmp_path)
        runtime = await runtime_for(app, binding_for(Transport()))
        result = await runtime.submit(
            message(values={VALUE_CHAT_TYPE: "group", VALUE_MENTIONS: [BOT]})
        )
        if result.handle is not None:
            await result.handle.wait()
        await runtime.close(WAIT_S)
        return result, spy

    result, spy = asyncio.run(asyncio.wait_for(scenario(), WAIT_S))

    assert len(spy.delivered) == 1
    assert result.acceptance.status is TurnAcceptanceStatus.ACCEPTED


def test_a_direct_message_from_an_owner_does_run(tmp_path):
    """The ordinary case, and the baseline the refusals are measured from."""

    async def scenario():
        app, spy = deployment(tmp_path)
        transport = Transport()
        runtime = await runtime_for(app, binding_for(transport))
        result = await runtime.submit(message())
        assert result.handle is not None
        await result.handle.wait()
        await runtime.close(WAIT_S)
        return result, spy, transport

    result, spy, transport = asyncio.run(asyncio.wait_for(scenario(), WAIT_S))

    assert result.acceptance.status is TurnAcceptanceStatus.ACCEPTED
    assert len(spy.delivered) == 1
    assert transport.sent == ["ok"]


# ---- the other refusals ------------------------------------------------


def test_a_runtime_that_has_not_started_refuses_without_touching_sessions(tmp_path):
    """An unstarted runtime has no loop to run a reply pump on."""

    async def scenario():
        app, spy = deployment(tmp_path)
        runtime = ChannelRuntime(app, [binding_for(Transport())])
        result = await runtime.submit(message())
        return result, spy

    result, spy = asyncio.run(asyncio.wait_for(scenario(), WAIT_S))

    assert result.acceptance.code == CODE_NOT_STARTED
    assert spy.delivered == []


def test_a_message_for_an_unknown_adapter_is_refused(tmp_path):
    """Routing is by name and is never guessed.

    Guessing would send one account's reply through another's token, which
    on a shared platform means one customer's answer in another's chat.
    """

    async def scenario():
        app, spy = deployment(tmp_path)
        runtime = await runtime_for(app, binding_for(Transport()))
        result = await runtime.submit(message(surface="telegram"))
        await runtime.close(0.0)
        return result, spy

    result, spy = asyncio.run(asyncio.wait_for(scenario(), WAIT_S))

    assert result.acceptance.code == CODE_UNKNOWN_ADAPTER
    assert spy.delivered == []


def test_two_bindings_for_one_adapter_are_refused(tmp_path):
    """One name, one account: an inbound message names only the adapter."""

    async def scenario():
        app, _spy = deployment(tmp_path)
        with pytest.raises(ValueError):
            ChannelRuntime(
                app,
                [
                    binding_for(Transport(), account_namespace="one"),
                    binding_for(Transport(), account_namespace="two"),
                ],
            )

    asyncio.run(asyncio.wait_for(scenario(), WAIT_S))


def test_a_channel_runtime_requires_an_approval_deadline(tmp_path):
    """Plan 0031 Q12: ``approval_timeout_s`` may not be ``None`` here.

    A CLI can wait for a person who is sitting in front of it. A channel
    cannot: the person may have closed the app, and a tool waiting forever
    for consent holds that conversation's queue behind it.
    """

    async def scenario():
        app, _spy = deployment(tmp_path, approval_timeout_s=None)
        with pytest.raises(ValueError, match="approval_timeout_s"):
            ChannelRuntime(app, [binding_for(Transport())])

    asyncio.run(asyncio.wait_for(scenario(), WAIT_S))


def test_a_channel_runtime_requires_a_session_registry(tmp_path):
    """``build_app`` leaves ``sessions=None``; a channel cannot run on that."""

    async def scenario():
        app = make_app(tmp_path, Scripted(), tools=(), approval_timeout_s=WAIT_S)
        with pytest.raises(ValueError, match="session registry"):
            ChannelRuntime(app, [binding_for(Transport())])

    asyncio.run(asyncio.wait_for(scenario(), WAIT_S))


def test_an_empty_message_creates_no_exchange(tmp_path):
    """Whitespace is not a question, and asking it costs a model call."""

    async def scenario():
        app, spy = deployment(tmp_path)
        runtime = await runtime_for(app, binding_for(Transport()))
        result = await runtime.submit(message(text="   \n "))
        await runtime.close(0.0)
        return result, spy

    result, spy = asyncio.run(asyncio.wait_for(scenario(), WAIT_S))

    assert result.acceptance.code == "empty_text"
    assert spy.delivered == []


# ---- Q7: queueing is a semantic ---------------------------------------


def test_a_second_message_is_queued_and_a_third_is_refused(tmp_path):
    """Plan 0031 Q7, seen from a channel.

    ``submit`` returns before the exchange runs, so a person who sent three
    messages gets three answers to "what happened to it" — running, queued,
    and *refused*, which is the one an unbounded queue cannot give.
    """

    async def scenario():
        app, spy = deployment(tmp_path, max_queued_per_session=1)
        runtime = await runtime_for(app, binding_for(Transport()))
        first = await runtime.submit(message(source_request_id="a"))
        second = await runtime.submit(message(source_request_id="b"))
        third = await runtime.submit(message(source_request_id="c"))
        for result in (first, second):
            if result.handle is not None:
                await result.handle.wait()
        await runtime.close(WAIT_S)
        return first, second, third, spy

    first, second, third, spy = asyncio.run(asyncio.wait_for(scenario(), WAIT_S))

    assert first.acceptance.status is TurnAcceptanceStatus.ACCEPTED
    assert second.acceptance.status is TurnAcceptanceStatus.ACCEPTED
    assert third.acceptance.code == CODE_QUEUE_FULL
    assert len(spy.delivered) == 3  # the third reached the registry and was refused


def test_a_redelivery_resolves_to_the_same_exchange(tmp_path):
    """Plan 0031 Q24's ``durable_ingress_idempotency``, on an IM surface.

    Every platform here redelivers. A second submission of one message id
    must resolve to the exchange already running, and must not start a
    second reply pump over it — two pumps would answer the person twice.
    """

    async def scenario():
        app, _spy = deployment(tmp_path)
        transport = Transport()
        runtime = await runtime_for(app, binding_for(transport))
        first = await runtime.submit(message(source_request_id="same"))
        second = await runtime.submit(message(source_request_id="same"))
        assert first.handle is not None
        await first.handle.wait()
        await runtime.close(WAIT_S)
        return first, second, transport

    first, second, transport = asyncio.run(asyncio.wait_for(scenario(), WAIT_S))

    assert second.acceptance.status is TurnAcceptanceStatus.DUPLICATE
    assert second.acceptance.turn_id == first.acceptance.turn_id
    assert second.handle is first.handle
    assert transport.sent == ["ok"]


def test_one_message_id_in_two_chats_is_not_a_redelivery(tmp_path):
    """Message ids are per-conversation on several of these platforms.

    A key space shared across chats makes the second chat's *first*
    message a duplicate of the first chat's: no reply pump is started, so
    the person in that chat is answered by silence. Worse, the handle
    handed back belongs to a conversation they cannot see.
    """

    async def scenario():
        app, _spy = deployment(tmp_path)
        transport = Transport()
        runtime = await runtime_for(app, binding_for(transport))
        first = await runtime.submit(
            message(session_id="feishu:c1", source_request_id="om_1")
        )
        second = await runtime.submit(
            message(session_id="feishu:c2", source_request_id="om_1")
        )
        assert first.handle is not None and second.handle is not None
        await first.handle.wait()
        await second.handle.wait()
        await runtime.close(WAIT_S)
        return first, second

    first, second = asyncio.run(asyncio.wait_for(scenario(), WAIT_S))

    assert second.acceptance.status is TurnAcceptanceStatus.ACCEPTED
    assert second.acceptance.turn_id != first.acceptance.turn_id
    assert second.handle is not first.handle


def test_the_default_chunk_limit_matches_the_ported_channel_config():
    """One number, two homes; a test rather than a comment.

    ``BaseChannelConfig.text_chunk_limit`` is what every adapter overrides
    from and what a binding falls back to. They cannot be allowed to drift.
    """
    from omicsclaw.entry.channel.config import BaseChannelConfig

    assert DEFAULT_TEXT_CHUNK_LIMIT == BaseChannelConfig().text_chunk_limit
