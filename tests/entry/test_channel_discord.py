"""The Discord adapter, over fake platform objects.

``discord.py`` is not installed here and there is no network, so every
platform object below is a stand-in — which is the point: the gates being
asserted live in the adapter, and one that only held when Discord was
reachable would be no gate at all.

What this file tests is what is *particular* to Discord: an identity that is
only readable after ``login`` and before ``connect``, a mention list the
library hands over as user objects, two spellings of the same mention in a
message body, and a rate limit that arrives as an attribute on the
exception. The eight rules Discord shares with every other adapter are in
``test_channel_cutover_conformance.py``, which drives it through the fixture
registered at the bottom.
"""

from __future__ import annotations

import asyncio
import itertools
import sys
import types
from types import SimpleNamespace

import pytest

from omicsclaw.entry.channel import reply_target
from omicsclaw.entry.channel.delivery import (
    DeliveryAttemptOutcome,
    DeliveryAttemptRequest,
)
from omicsclaw.entry.channel.discord import DiscordChannel, DiscordConfig
from omicsclaw.entry.channel.discord_delivery import DiscordDeliveryAdapter
from omicsclaw.entry.ingress import VALUE_CHAT_TYPE, VALUE_MENTIONS
from tests.entry.channel_conformance import (  # type: ignore[import-not-found]
    MENTION_PROBE,
    ChannelFixture,
    DeliveryCase,
    MentionGuard,
    SentCall,
    register,
)
from tests.entry.test_channel_ingress import (  # type: ignore[import-not-found]
    OWNER,
)
from tests.entry.test_channel_slack import (  # type: ignore[import-not-found]
    CountingRuntime,
)

WAIT_S = 5.0
BOT_ID = 77
GUILD_CHANNEL = "456"
DM_CHANNEL = "123"


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, WAIT_S))


# ---- platform doubles --------------------------------------------------
#
# Two of the class names below are load-bearing. With no ``discord.py`` to
# import, both the adapter and its delivery module fall back to comparing a
# class name **exactly** — ``DMChannel`` is how a direct message is
# recognised and ``HTTPException`` is how a rate limit is. Rename either and
# the behaviour under test quietly stops happening.


class DMChannel:
    """A Discord direct-message channel, identified by its class name."""

    def __init__(self, channel_id: str = DM_CHANNEL) -> None:
        self.id = channel_id


class TextChannel:
    """A guild channel: anything that is not a DM, for this adapter."""

    def __init__(self, channel_id: str = GUILD_CHANNEL) -> None:
        self.id = channel_id


class HTTPException(Exception):
    """Stands in for ``discord.errors.HTTPException``."""

    def __init__(self, status: int = 429, retry_after: float | None = None) -> None:
        super().__init__("discord http error")
        self.status = status
        self.retry_after = retry_after


class Forbidden(HTTPException):
    """Stands in for ``discord.errors.Forbidden``."""

    def __init__(self) -> None:
        super().__init__(status=403)


class AllowedMentions:
    """Stands in for ``discord.AllowedMentions``: whom one message may notify.

    Compared by value, so a test can say "this send notifies nobody" without
    the SDK that defines the real one.
    """

    def __init__(
        self,
        *,
        everyone: bool = True,
        users: bool = True,
        roles: bool = True,
        replied_user: bool = True,
    ) -> None:
        self.everyone = everyone
        self.users = users
        self.roles = roles
        self.replied_user = replied_user

    @classmethod
    def none(cls) -> "AllowedMentions":
        return cls(everyone=False, users=False, roles=False, replied_user=False)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, AllowedMentions) and vars(self) == vars(other)

    def __repr__(self) -> str:
        return f"AllowedMentions({vars(self)})"


NO_MENTIONS = AllowedMentions.none()


def fake_discord_module() -> types.ModuleType:
    """A ``discord`` package holding only :class:`AllowedMentions`."""
    module = types.ModuleType("discord")
    module.AllowedMentions = AllowedMentions  # type: ignore[attr-defined]
    return module


class SendingChannel:
    """The one method the delivery adapter calls on a resolved channel."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.texts: list[str] = []
        self.calls: list[dict] = []

    async def send(self, text: str, **kwargs):
        if self.error is not None:
            raise self.error
        self.texts.append(text)
        self.calls.append({"content": text, **kwargs})
        return SimpleNamespace(id=999)


class FakeDiscordClient:
    """``login``, ``connect``, ``close`` and ``get_channel`` — no more."""

    def __init__(
        self,
        *,
        user_id: int | None = BOT_ID,
        channel: SendingChannel | None = None,
    ) -> None:
        self.user = SimpleNamespace(id=user_id) if user_id is not None else None
        self.logged_in_with = ""
        self.closed = False
        self._channel = channel

    async def login(self, token: str) -> None:
        self.logged_in_with = token

    async def connect(self, reconnect: bool = True) -> None:
        await asyncio.sleep(3600)

    async def close(self) -> None:
        self.closed = True

    def get_channel(self, channel_id: int):
        return self._channel


_MESSAGE_IDS = itertools.count(5000)


def discord_message(
    *,
    text: str = "analyse this",
    sender: str = OWNER,
    group: bool = False,
    mentions_bot: bool = False,
):
    mentions = (SimpleNamespace(id=BOT_ID),) if mentions_bot else ()
    return SimpleNamespace(
        id=next(_MESSAGE_IDS),
        author=SimpleNamespace(id=sender),
        channel=TextChannel() if group else DMChannel(),
        content=text,
        mentions=mentions,
    )


def discord_channel(client: FakeDiscordClient | None = None) -> DiscordChannel:
    channel = DiscordChannel(
        DiscordConfig(bot_token="token", allowed_senders={OWNER})
    )
    channel._client = client or FakeDiscordClient()
    return channel


def bound(runtime, client: FakeDiscordClient | None = None) -> DiscordChannel:
    channel = discord_channel(client)
    channel.bot_identity = str(BOT_ID)
    channel._account_namespace = f"bot-{BOT_ID}"
    channel.bind_control_runtime(runtime)
    channel._running = True
    channel.activate_ingress()
    return channel


# ---- the binding -------------------------------------------------------


def test_the_discord_binding_reads_its_identity_at_login_not_at_ready():
    """``on_ready`` fires after ``connect``, which is after the binding.

    Building the binding from an identity that is not there yet leaves
    ``bot_identity`` empty — and an empty identity makes every guild message
    fail closed, on a deployment that otherwise looks healthy.
    """

    async def scenario():
        client = FakeDiscordClient()
        channel = discord_channel(client)
        return client, await channel.prepare_control_binding()

    client, binding = run(scenario())

    assert client.logged_in_with == "token"
    assert binding.adapter == "discord"
    assert binding.account_namespace == f"bot-{BOT_ID}"
    assert binding.sender_policy.bot_identity == str(BOT_ID)
    assert binding.sender_policy.allowed_senders == frozenset({OWNER})
    assert binding.attachment_input_enabled is False


def test_the_discord_binding_refuses_a_login_that_names_nobody():
    """Without an identity there is nothing to attribute a mention to."""

    async def scenario():
        channel = discord_channel(FakeDiscordClient(user_id=None))
        with pytest.raises(RuntimeError, match="identity"):
            await channel.prepare_control_binding()

    run(scenario())


def test_the_discord_binding_refuses_to_start_with_no_owners():
    async def scenario():
        channel = DiscordChannel(DiscordConfig(bot_token="t"))
        channel._client = FakeDiscordClient()
        with pytest.raises(RuntimeError, match="DISCORD_ALLOWED_SENDERS"):
            await channel.prepare_control_binding()

    run(scenario())


# ---- inbound -----------------------------------------------------------


def test_a_discord_guild_message_that_mentions_the_bot_is_normalised():
    """Both mention spellings come off, or the model reads a snowflake."""

    async def scenario():
        runtime = CountingRuntime()
        channel = bound(runtime)
        message = discord_message(
            text=f"<@{BOT_ID}> <@!{BOT_ID}> analyse this",
            group=True,
            mentions_bot=True,
        )
        await channel._on_message(message)
        return runtime, message

    runtime, message = run(scenario())

    (inbound,) = runtime.messages
    assert inbound.text == "analyse this"
    assert inbound.session_id == f"discord:{GUILD_CHANNEL}"
    assert inbound.source_request_id == str(message.id)
    assert inbound.surface == "discord"
    assert inbound.values[VALUE_CHAT_TYPE] == "group"
    assert inbound.values[VALUE_MENTIONS] == (str(BOT_ID),)
    assert inbound.values["reply_target"]["destination_id"] == GUILD_CHANNEL


def test_a_discord_direct_message_is_private_and_needs_no_mention():
    async def scenario():
        runtime = CountingRuntime()
        await bound(runtime)._on_message(discord_message())
        return runtime

    (inbound,) = run(scenario()).messages

    assert inbound.values[VALUE_CHAT_TYPE] == "private"
    assert inbound.values[VALUE_MENTIONS] == ()


def test_a_discord_guild_message_without_a_mention_is_not_even_submitted():
    async def scenario():
        runtime = CountingRuntime()
        await bound(runtime)._on_message(discord_message(group=True))
        return runtime

    assert run(scenario()).messages == []


def test_a_discord_message_from_the_bot_itself_is_ignored():
    """A bot that answers itself is a loop with a rate limit at the end."""

    async def scenario():
        runtime = CountingRuntime()
        await bound(runtime)._on_message(discord_message(sender=str(BOT_ID)))
        return runtime

    assert run(scenario()).messages == []


def test_a_refused_discord_message_can_still_land_when_it_is_redelivered():
    """The local cache is an optimisation and never the authority.

    Marking a message as seen on arrival loses it silently whenever the
    submission that follows fails and the gateway resends inside the TTL.
    """

    async def scenario():
        from omicsclaw.entry.channel.runtime import TurnAcceptanceStatus

        runtime = CountingRuntime(
            TurnAcceptanceStatus.REJECTED, TurnAcceptanceStatus.ACCEPTED
        )
        channel = bound(runtime)
        message = discord_message()
        await channel._on_message(message)
        await channel._on_message(message)
        return runtime

    assert len(run(scenario()).messages) == 2


def test_a_discord_message_that_was_accepted_is_not_submitted_twice():
    async def scenario():
        runtime = CountingRuntime()
        channel = bound(runtime)
        message = discord_message()
        await channel._on_message(message)
        await channel._on_message(message)
        return runtime

    assert len(run(scenario()).messages) == 1


def test_discord_refuses_the_legacy_standalone_entry_point():
    with pytest.raises(RuntimeError, match="ChannelRuntime"):
        discord_channel().run_bot()


# ---- delivery ----------------------------------------------------------


def discord_adapter(client: FakeDiscordClient) -> DiscordDeliveryAdapter:
    """The delivery adapter over *client*, told to notify nobody.

    ``discord.py`` is not installed here, so the value it would load is
    supplied instead; what the adapter does with it is the same.
    """
    return DiscordDeliveryAdapter(client, allowed_mentions=NO_MENTIONS)


def discord_request(text: str = "hello", **target) -> DeliveryAttemptRequest:
    built = reply_target.build(
        "discord", f"bot-{BOT_ID}", target.pop("destination", GUILD_CHANNEL), **target
    )
    return DeliveryAttemptRequest(item_id="t1-0", text=text, reply_target=built)


def test_the_discord_adapter_classifies_a_rate_limit_from_the_exception():
    channel = SendingChannel(HTTPException(status=429, retry_after=2.5))
    adapter = discord_adapter(FakeDiscordClient(channel=channel))

    result = run(adapter.attempt(discord_request()))

    assert result.outcome is DeliveryAttemptOutcome.NOT_ACCEPTED_RETRYABLE
    assert result.retry_after_ms == 2500


def test_a_discord_refusal_is_permanent_even_though_it_is_an_http_error():
    """``Forbidden`` subclasses ``HTTPException``, so order decides this.

    Checked after the 429 branch instead, a permanent refusal with no status
    would be read as a rate limit and retried three times against a channel
    this bot will never be allowed to post in.
    """
    channel = SendingChannel(Forbidden())
    adapter = discord_adapter(FakeDiscordClient(channel=channel))

    result = run(adapter.attempt(discord_request()))

    assert result.outcome is DeliveryAttemptOutcome.REJECTED_PERMANENT
    assert result.error_code == "discord_forbidden"


def test_a_channel_discord_cannot_resolve_never_reached_discord():
    """So it is a refusal, not an ambiguity: no socket work happened."""
    adapter = discord_adapter(FakeDiscordClient(channel=None))

    result = run(adapter.attempt(discord_request()))

    assert result.outcome is DeliveryAttemptOutcome.REJECTED_PERMANENT
    assert result.error_code == "discord_channel_not_found"


def test_a_destination_that_is_not_a_snowflake_is_refused():
    channel = SendingChannel()
    adapter = discord_adapter(FakeDiscordClient(channel=channel))

    result = run(adapter.attempt(discord_request(destination="not-a-number")))

    assert result.outcome is DeliveryAttemptOutcome.REJECTED_PERMANENT
    assert result.error_code == "discord_invalid_delivery"
    assert channel.texts == []


def test_every_discord_send_tells_discord_to_notify_nobody(monkeypatch):
    """Discord notifies from ``@everyone``, ``@here``, ``<@id>`` and ``<@&role>``.

    Unless the send says otherwise, which is what ``allowed_mentions`` is
    for. Setting it to ``AllowedMentions.none()`` on every send, rather than
    escaping the text, leaves the text exactly as the model wrote it — the
    person sees ``@everyone`` and nobody is pinged.
    """
    monkeypatch.setitem(sys.modules, "discord", fake_discord_module())
    channel = SendingChannel()
    adapter = DiscordDeliveryAdapter(FakeDiscordClient(channel=channel))

    result = run(adapter.attempt(discord_request(MENTION_PROBE)))

    assert result.outcome is DeliveryAttemptOutcome.ACCEPTED
    assert channel.calls == [
        {"content": MENTION_PROBE, "allowed_mentions": AllowedMentions.none()}
    ]


def test_without_discord_py_nothing_is_sent_unguarded(monkeypatch):
    """No SDK means no ``AllowedMentions`` to send with, so no send at all.

    Without ``discord.py`` there is no real client to send through, so this
    only matters to a double — and a double that sent anyway would hide an
    adapter that had stopped setting the guard.
    """
    monkeypatch.setitem(sys.modules, "discord", None)
    channel = SendingChannel()
    adapter = DiscordDeliveryAdapter(FakeDiscordClient(channel=channel))

    result = run(adapter.attempt(discord_request(MENTION_PROBE)))

    assert result.outcome is DeliveryAttemptOutcome.REJECTED_PERMANENT
    assert result.error_code == "discord_client_unavailable"
    assert channel.calls == []


class FlakySendingChannel(SendingChannel):
    """Refuses its first send as rate-limited, then accepts."""

    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0

    async def send(self, text: str, **kwargs):
        self.attempts += 1
        if self.attempts == 1:
            raise HTTPException(status=429, retry_after=0)
        return await super().send(text, **kwargs)


def test_every_chunk_and_every_retry_is_sent_notifying_nobody(monkeypatch):
    """The guard is per send, so it has to be on every one of them.

    A reply leaves as several chunks and a rate-limited chunk is sent again;
    a guard set on the first call only, or dropped on a retry, is a mention
    that reaches the room on exactly the sends nobody looks at.
    """
    from omicsclaw.entry.channel.delivery import deliver
    from omicsclaw.entry.ingress import Acceptance

    monkeypatch.setitem(sys.modules, "discord", fake_discord_module())
    channel = FlakySendingChannel()

    async def no_wait(_seconds: float) -> None:
        return None

    result = run(
        deliver(
            DiscordDeliveryAdapter(FakeDiscordClient(channel=channel)),
            ["@everyone one", "@here two", "<@&42> three"],
            item_prefix="t1",
            reply_target=discord_request().reply_target,
            sleep=no_wait,
        )
    )

    assert result.acceptance is Acceptance.ACCEPTED
    assert channel.attempts == 4, "the first chunk was meant to be retried once"
    assert [call["content"] for call in channel.calls] == [
        "@everyone one",
        "@here two",
        "<@&42> three",
    ]
    assert all(
        call["allowed_mentions"] == AllowedMentions.none() for call in channel.calls
    )


# ---- the conformance fixture -------------------------------------------


async def _conformance_submit(
    channel: DiscordChannel,
    *,
    text: str,
    sender: str = OWNER,
    group: bool = False,
    mentions_bot: bool = False,
) -> None:
    await channel._on_message(
        discord_message(
            text=text, sender=sender, group=group, mentions_bot=mentions_bot
        )
    )


def _conformance_accepting_delivery():
    channel = SendingChannel()
    return discord_adapter(FakeDiscordClient(channel=channel)), channel.texts


class _MentionRecordingChannel(SendingChannel):
    """Records each ``channel.send`` as a :class:`SentCall`."""

    def __init__(self) -> None:
        super().__init__()
        self.sent_calls: list[SentCall] = []

    async def send(self, text: str, **kwargs):
        notifies = kwargs.get("allowed_mentions") != AllowedMentions.none()
        self.sent_calls.append(SentCall(text=text, notifies=notifies))
        return await super().send(text, **kwargs)


def _conformance_mention_delivery():
    channel = _MentionRecordingChannel()
    return discord_adapter(FakeDiscordClient(channel=channel)), channel.sent_calls


def _conformance_delivery_cases() -> tuple[DeliveryCase, ...]:
    def adapter(error: Exception):
        return discord_adapter(FakeDiscordClient(channel=SendingChannel(error)))

    return (
        DeliveryCase(
            "timeout",
            adapter(asyncio.TimeoutError()),
            DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
        ),
        DeliveryCase(
            "unknown",
            adapter(RuntimeError("?")),
            DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
        ),
        DeliveryCase(
            "rate_limited",
            adapter(HTTPException(status=429, retry_after=1)),
            DeliveryAttemptOutcome.NOT_ACCEPTED_RETRYABLE,
        ),
    )


register(
    ChannelFixture(
        name="discord",
        new_channel=discord_channel,
        reply_target=lambda channel: reply_target.build(
            "discord", f"bot-{BOT_ID}", GUILD_CHANNEL
        ),
        accepting_delivery=_conformance_accepting_delivery,
        delivery_cases=_conformance_delivery_cases,
        submit=_conformance_submit,
        direct_replies=lambda _channel, transport: list(transport.sent),
        has_groups=True,
        strips_markdown=False,
        unregistered_commands_reach_the_agent=True,
        mention_guard=MentionGuard(
            live_spellings=("@everyone",),
            accepting_delivery=_conformance_mention_delivery,
        ),
    )
)
