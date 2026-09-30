"""The QQ adapter, over fake platform objects.

``qq-botpy`` is not installed here and there is no network. What this file
tests is what is *particular* to QQ: an attribution that is a callback name
rather than a list, a passive reply that has to name the message it answers,
a sequence number that must not change when an attempt is repeated, and a
client that renders no Markdown at all. The eight rules QQ shares with every
other adapter are in ``test_channel_cutover_conformance.py``, which drives it
through the fixture registered at the bottom.
"""

from __future__ import annotations

import asyncio
import itertools
from types import SimpleNamespace

import pytest

from omicsclaw.entry.channel import reply_target
from omicsclaw.entry.channel.delivery import (
    DeliveryAttemptOutcome,
    DeliveryAttemptRequest,
    deliver,
)
from omicsclaw.entry.channel.qq import QQChannel, QQConfig
from omicsclaw.entry.channel.qq_delivery import (
    MessageSequence,
    QQDeliveryAdapter,
    strip_markdown,
)
from omicsclaw.entry.ingress import VALUE_CHAT_TYPE, VALUE_MENTIONS
from tests.entry.channel_conformance import (  # type: ignore[import-not-found]
    ChannelFixture,
    DeliveryCase,
    register,
)
from tests.entry.test_channel_ingress import (  # type: ignore[import-not-found]
    OWNER,
)
from tests.entry.test_channel_slack import (  # type: ignore[import-not-found]
    CountingRuntime,
)

WAIT_S = 5.0
APP_ID = "102000001"
GROUP = "group-open-id"


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, WAIT_S))


# ---- platform doubles --------------------------------------------------


class ServerError(Exception):
    """Stands in for ``botpy.errors.ServerError``: a 5xx, so ambiguous."""

    status = 503


class ForbiddenError(Exception):
    """Stands in for ``botpy.errors.ForbiddenError``.

    The class name is load-bearing: with no botpy to import, it is the only
    thing that tells a refusal from a transport failure.
    """


class TooManyRequests(Exception):
    """A QQ rate limit, which arrives as HTTP 429 with a header."""

    status = 429

    def __init__(self, retry_after: str = "4") -> None:
        super().__init__("rate limited")
        self.headers = {"Retry-After": retry_after}


class FakeQQApi:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict] = []

    async def post_group_message(self, **kwargs):
        return self._record(kwargs)

    async def post_c2c_message(self, **kwargs):
        return self._record(kwargs)

    def _record(self, kwargs: dict):
        if self.error is not None:
            raise self.error
        self.calls.append(kwargs)
        return {"id": "qq-sent"}


class FakeQQClient:
    def __init__(self, error: Exception | None = None) -> None:
        self.api = FakeQQApi(error)


_MESSAGE_IDS = itertools.count(3000)


def qq_message(*, text: str = "analyse this", sender: str = OWNER, group: bool = False):
    author = (
        SimpleNamespace(member_openid=sender)
        if group
        else SimpleNamespace(user_openid=sender)
    )
    return SimpleNamespace(
        id=f"qq-{next(_MESSAGE_IDS)}",
        author=author,
        content=text,
        group_openid=GROUP if group else "",
    )


def qq_channel(client: FakeQQClient | None = None) -> QQChannel:
    channel = QQChannel(
        QQConfig(app_id=APP_ID, app_secret="secret", allowed_senders={OWNER})
    )
    channel._client = client or FakeQQClient()
    return channel


def bound(runtime, client: FakeQQClient | None = None) -> QQChannel:
    channel = qq_channel(client)
    channel.bot_identity = APP_ID
    channel._account_namespace = f"app-{APP_ID}"
    channel.bind_control_runtime(runtime)
    channel._running = True
    channel.activate_ingress()
    return channel


# ---- the binding -------------------------------------------------------


def test_the_qq_binding_names_the_app_a_proven_mention_resolves_to():
    async def scenario():
        return await qq_channel().prepare_control_binding()

    binding = run(scenario())

    assert binding.adapter == "qq"
    assert binding.account_namespace == f"app-{APP_ID}"
    assert binding.sender_policy.bot_identity == APP_ID
    assert binding.attachment_input_enabled is False


def test_the_qq_binding_refuses_to_start_with_no_owners():
    async def scenario():
        channel = QQChannel(QQConfig(app_id="a", app_secret="b"))
        channel._client = FakeQQClient()
        with pytest.raises(RuntimeError, match="QQ_ALLOWED_SENDERS"):
            await channel.prepare_control_binding()

    run(scenario())


# ---- trap 4: the callback name is the assertion ------------------------


def test_only_the_group_callback_names_this_bot_as_mentioned():
    """``on_group_at_message_create`` fires only for messages that @-ed us.

    A direct message carries no mention and needs none; naming the bot there
    too would make the mention list say something the platform did not.
    """

    async def scenario():
        runtime = CountingRuntime()
        channel = bound(runtime)
        await channel._on_message(qq_message(group=True), is_group=True)
        await channel._on_message(qq_message(), is_group=False)
        return runtime

    group_message, direct = run(scenario()).messages

    assert group_message.values[VALUE_CHAT_TYPE] == "group"
    assert group_message.values[VALUE_MENTIONS] == (APP_ID,)
    assert group_message.session_id == f"qq:{GROUP}"
    assert direct.values[VALUE_CHAT_TYPE] == "private"
    assert direct.values[VALUE_MENTIONS] == ()


def test_a_qq_message_carries_the_id_a_passive_reply_has_to_name():
    async def scenario():
        runtime = CountingRuntime()
        message = qq_message(group=True)
        await bound(runtime)._on_message(message, is_group=True)
        return runtime, message

    runtime, message = run(scenario())

    (inbound,) = runtime.messages
    assert inbound.source_request_id == message.id
    assert inbound.surface == "qq"
    target = inbound.values["reply_target"]
    assert target["msg_id"] == message.id
    assert target["msg_type"] == "group"
    assert target["destination_id"] == GROUP


def test_the_leading_mention_qq_injects_is_stripped():
    async def scenario():
        runtime = CountingRuntime()
        await bound(runtime)._on_message(
            qq_message(text="@OmicsClaw analyse this", group=True), is_group=True
        )
        return runtime

    (inbound,) = run(scenario()).messages

    assert inbound.text == "analyse this"


def test_a_refused_qq_message_can_still_land_when_it_is_redelivered():
    async def scenario():
        from omicsclaw.entry.channel.runtime import TurnAcceptanceStatus

        runtime = CountingRuntime(
            TurnAcceptanceStatus.REJECTED, TurnAcceptanceStatus.ACCEPTED
        )
        channel = bound(runtime)
        message = qq_message()
        await channel._on_message(message, is_group=False)
        await channel._on_message(message, is_group=False)
        return runtime

    assert len(run(scenario()).messages) == 2


def test_qq_refuses_the_legacy_standalone_entry_point():
    with pytest.raises(RuntimeError, match="ChannelRuntime"):
        qq_channel().run_bot()


# ---- trap 1: the sequence number belongs to the message ----------------


def test_the_same_delivery_item_always_gets_the_same_sequence_number():
    """QQ numbers replies under the message they answer.

    ``deliver`` may call this adapter three times for one chunk. A counter
    would hand each attempt a fresh number, QQ would read the resend as a
    new message, and the person would see the answer twice — which is the
    exact duplicate ``ACCEPTANCE_UNKNOWN`` exists to prevent, arrived at by
    going around it.
    """
    sequence = MessageSequence()

    first = sequence.of("m1", "turn-0-0")
    again = sequence.of("m1", "turn-0-0")
    second_chunk = sequence.of("m1", "turn-0-1")
    other_message = sequence.of("m2", "turn-1-0")

    assert first == again == 1
    assert second_chunk == 2
    assert other_message == 1


def test_a_retried_qq_send_reuses_its_sequence_number():
    """The same claim, through the real adapter and the real retry loop."""
    client = FakeQQClient()
    adapter = QQDeliveryAdapter(client)
    request = qq_request()

    run(adapter.attempt(request))
    run(adapter.attempt(request))

    assert [call["msg_seq"] for call in client.api.calls] == [1, 1]


def test_two_chunks_of_one_answer_are_numbered_in_order():
    """And the numbers advance, or QQ refuses the second chunk."""
    client = FakeQQClient()
    adapter = QQDeliveryAdapter(client)

    async def scenario():
        return await deliver(
            adapter,
            ["first", "second"],
            item_prefix="turn-0",
            reply_target=reply_target.build(
                "qq", f"app-{APP_ID}", GROUP, msg_id="m1", msg_type="group"
            ),
        )

    run(scenario())

    assert [call["msg_seq"] for call in client.api.calls] == [1, 2]


# ---- trap 13: QQ renders no Markdown ----------------------------------


def test_markdown_is_reduced_before_it_reaches_qq():
    """The regression an acceptance classification cannot see.

    QQ accepts asterisks as happily as words, so every outbound assertion
    stays green while the person reads ``**bold**``.
    """
    client = FakeQQClient()

    run(QQDeliveryAdapter(client).attempt(qq_request(text="**bold** and `code`")))

    assert client.api.calls[0]["content"] == "bold and code"


def test_strip_markdown_keeps_the_words_and_drops_the_punctuation():
    assert strip_markdown("# Title\n- item\n**bold**") == "Title\n• item\nbold"


# ---- delivery ----------------------------------------------------------


def qq_request(text: str = "hello", item_id: str = "t1-0", **target):
    built = reply_target.build(
        "qq",
        f"app-{APP_ID}",
        target.pop("destination", GROUP),
        **({"msg_id": "m1", "msg_type": "group"} | target),
    )
    return DeliveryAttemptRequest(item_id=item_id, text=text, reply_target=built)


def test_a_qq_rate_limit_is_the_one_refusal_worth_repeating():
    adapter = QQDeliveryAdapter(FakeQQClient(TooManyRequests("4")))

    result = run(adapter.attempt(qq_request()))

    assert result.outcome is DeliveryAttemptOutcome.NOT_ACCEPTED_RETRYABLE
    assert result.retry_after_ms == 4000


def test_a_named_qq_refusal_is_permanent():
    adapter = QQDeliveryAdapter(FakeQQClient(ForbiddenError()))

    result = run(adapter.attempt(qq_request()))

    assert result.outcome is DeliveryAttemptOutcome.REJECTED_PERMANENT


def test_a_qq_server_error_is_ambiguous_rather_than_retryable():
    adapter = QQDeliveryAdapter(FakeQQClient(ServerError()))

    result = run(adapter.attempt(qq_request()))

    assert result.outcome is DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN
    assert not result.retryable


def test_a_qq_target_that_names_no_inbound_message_is_refused():
    """QQ accepts a bot message only as a reply to one it can name."""
    client = FakeQQClient()
    built = reply_target.build("qq", f"app-{APP_ID}", GROUP, msg_type="group")

    result = run(
        QQDeliveryAdapter(client).attempt(
            DeliveryAttemptRequest(item_id="t1-0", text="hi", reply_target=built)
        )
    )

    assert result.outcome is DeliveryAttemptOutcome.REJECTED_PERMANENT
    assert result.error_code == "qq_invalid_delivery"
    assert client.api.calls == []


def test_a_direct_reply_uses_the_c2c_endpoint():
    client = FakeQQClient()

    run(
        QQDeliveryAdapter(client).attempt(
            qq_request(destination="user-open-id", msg_type="c2c")
        )
    )

    assert client.api.calls[0]["openid"] == "user-open-id"


# ---- the conformance fixture -------------------------------------------


async def _conformance_submit(
    channel: QQChannel,
    *,
    text: str,
    sender: str = OWNER,
    group: bool = False,
    mentions_bot: bool = False,
) -> None:
    # A group message reaches this adapter only through the callback QQ fires
    # for messages that mentioned the bot, so "a group message that did not"
    # is one that never arrives.
    if group and not mentions_bot:
        return
    await channel._on_message(
        qq_message(text=text, sender=sender, group=group), is_group=group
    )


def _conformance_accepting_delivery():
    client = FakeQQClient()
    texts: list[str] = []

    class _Recording(QQDeliveryAdapter):
        async def attempt(self, request):
            result = await super().attempt(request)
            if result.outcome is DeliveryAttemptOutcome.ACCEPTED:
                texts.append(client.api.calls[-1]["content"])
            return result

    return _Recording(client), texts


def _conformance_delivery_cases() -> tuple[DeliveryCase, ...]:
    return (
        DeliveryCase(
            "timeout",
            QQDeliveryAdapter(FakeQQClient(asyncio.TimeoutError())),
            DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
        ),
        DeliveryCase(
            "unknown",
            QQDeliveryAdapter(FakeQQClient(RuntimeError("?"))),
            DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
        ),
        DeliveryCase(
            "rate_limited",
            QQDeliveryAdapter(FakeQQClient(TooManyRequests())),
            DeliveryAttemptOutcome.NOT_ACCEPTED_RETRYABLE,
        ),
    )


register(
    ChannelFixture(
        name="qq",
        new_channel=qq_channel,
        reply_target=lambda channel: reply_target.build(
            "qq", f"app-{APP_ID}", GROUP, msg_id="m1", msg_type="group"
        ),
        accepting_delivery=_conformance_accepting_delivery,
        delivery_cases=_conformance_delivery_cases,
        submit=_conformance_submit,
        direct_replies=lambda _channel, transport: list(transport.sent),
        has_groups=True,
        strips_markdown=True,
        unregistered_commands_reach_the_agent=True,
    )
)
