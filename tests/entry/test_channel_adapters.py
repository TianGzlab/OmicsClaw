"""The two production adapters, over fake platform objects.

Plan 0031 §5.3 accepts Telegram and Feishu and explicitly does not accept
the other seven, so these two are the ones with tests. Neither vendor SDK
is installed and there is no network, so every platform object here is a
stand-in — which is the whole point: the gates being asserted are in the
adapter, not in the SDK, and an adapter whose refusals only worked when
Telegram was reachable would be no gate at all.

The rules under test are ``CLAUDE.md``'s, word for word:
``FEISHU_ALLOWED_SENDERS`` is *required* and "authoritative Feishu ingress
admits nobody else and refuses to start without it"; without
``FEISHU_BOT_OPEN_ID`` "group chats fail closed". Telegram gets the same
group rule here, because the reason for it is the platform's rather than
Feishu's: an owner @-mentioning a colleague in a shared group must not make
this agent answer.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from omicsclaw.entry.channel.feishu import FeishuChannel, FeishuConfig
from omicsclaw.entry.channel.runtime import (
    CODE_OWNER_DENIED,
    VALUE_REPLY_TARGET,
    ChannelRuntime,
    TurnAcceptanceStatus,
    compose_channel_runtime,
)
from omicsclaw.entry.channel.telegram import (
    TelegramChannel,
    TelegramConfig,
    telegram_bot_identity,
    telegram_mentions,
)
from omicsclaw.entry.ingress import (
    VALUE_CHAT_TYPE,
    VALUE_MENTIONS,
    SenderPolicy,
)
from tests.entry.test_channel_ingress import (  # type: ignore[import-not-found]
    OWNER,
    Transport,
    deployment,
)

WAIT_S = 5.0
BOT_USERNAME = "@omicsclaw_bot"
BOT_OPEN_ID = "ou_bot"


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, WAIT_S))


# ---- Telegram ----------------------------------------------------------


class FakeTelegramMessage:
    def __init__(self, text: str = "analyse this", entities=(), message_id: int = 7):
        self.text = text
        self.entities = entities
        self.message_id = message_id
        self.caption = None
        self.document = None
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


def telegram_update(
    *,
    text: str = "analyse this",
    user_id: str = OWNER,
    chat_type: str = "private",
    entities=(),
    chat_id: int = 42,
):
    message = FakeTelegramMessage(text=text, entities=entities)
    return SimpleNamespace(
        message=message,
        effective_user=SimpleNamespace(id=user_id, first_name="Owner"),
        effective_chat=SimpleNamespace(id=chat_id, type=chat_type),
    )


def mention(offset: int, length: int):
    return SimpleNamespace(type="mention", offset=offset, length=length)


def telegram_channel(runtime=None) -> TelegramChannel:
    channel = TelegramChannel(
        TelegramConfig(
            bot_token="123:secret",
            allowed_senders={OWNER},
            account_namespace="bot-1",
        )
    )
    channel.bot_identity = BOT_USERNAME
    channel._running = True
    if runtime is not None:
        channel.bind_control_runtime(runtime, loop=asyncio.get_event_loop())
    channel.activate_ingress()
    return channel


def test_the_bot_identity_is_the_handle_a_mention_actually_carries():
    """Telegram writes a bot mention as ``@handle`` and reports no id for it.

    So the username is the identity when there is one. The numeric fallback
    covers bots without a public username, which can then only be addressed
    by a ``text_mention``.
    """
    assert telegram_bot_identity(SimpleNamespace(username="bot", id=9)) == "@bot"
    assert telegram_bot_identity(SimpleNamespace(username=None, id=9)) == "9"
    assert telegram_bot_identity(SimpleNamespace()) == ""


def test_mentions_are_read_in_both_spellings_telegram_uses():
    """``mention`` slices the text; ``text_mention`` carries a user object."""
    message = FakeTelegramMessage(
        text="@omicsclaw_bot please look",
        entities=(
            mention(0, len(BOT_USERNAME)),
            SimpleNamespace(type="text_mention", user=SimpleNamespace(id=1234)),
            SimpleNamespace(type="bold", offset=0, length=3),
        ),
    )

    assert telegram_mentions(message) == (BOT_USERNAME, "1234")


def test_a_message_mentioning_nobody_yields_no_mentions():
    """Which is what makes a group message fail closed."""
    assert telegram_mentions(FakeTelegramMessage(text="hello")) == ()


def test_a_telegram_group_message_without_a_mention_creates_no_exchange(tmp_path):
    """§9-9 (c) on the Telegram adapter, end to end through the runtime.

    The sender is the owner, so the allowlist gate passes. Nothing here was
    addressed to this bot, so nothing runs.
    """

    async def scenario():
        app, spy = deployment(tmp_path)
        policy = SenderPolicy(
            allowed_senders=frozenset({OWNER}), bot_identity=BOT_USERNAME
        )
        from tests.entry.test_channel_ingress import binding_for

        runtime = ChannelRuntime(
            app, [binding_for(Transport(), adapter="telegram", sender_policy=policy)]
        )
        await runtime.start()
        channel = telegram_channel(runtime)
        update = telegram_update(chat_type="supergroup", text="hi @someone_else")
        result = await channel._submit_control_inbound(update, update.message.text)
        await runtime.close(0.0)
        return result, spy, update

    result, spy, update = run(scenario())

    assert spy.delivered == []
    assert result.acceptance.code == CODE_OWNER_DENIED
    assert update.message.replies == [], "a stranger is told nothing at all"


def test_a_telegram_group_message_that_mentions_the_bot_runs(tmp_path):
    """The other direction, so the refusal above is not vacuous."""

    async def scenario():
        app, spy = deployment(tmp_path)
        policy = SenderPolicy(
            allowed_senders=frozenset({OWNER}), bot_identity=BOT_USERNAME
        )
        from tests.entry.test_channel_ingress import binding_for

        transport = Transport()
        runtime = ChannelRuntime(
            app,
            [binding_for(transport, adapter="telegram", sender_policy=policy)],
        )
        await runtime.start()
        channel = telegram_channel(runtime)
        text = f"{BOT_USERNAME} please look"
        update = telegram_update(
            chat_type="supergroup",
            text=text,
            entities=(mention(0, len(BOT_USERNAME)),),
        )
        result = await channel._submit_control_inbound(update, text)
        assert result.handle is not None
        await result.handle.wait()
        await runtime.close(WAIT_S)
        return result, spy, transport

    result, spy, transport = run(scenario())

    assert result.acceptance.status is TurnAcceptanceStatus.ACCEPTED
    assert len(spy.delivered) == 1
    assert transport.sent == ["ok"]


def test_a_telegram_message_carries_its_idempotency_key_and_target(tmp_path):
    """Chat and message id: stable across Telegram's own redelivery.

    The registry resolves a repeat of that key to the exchange it already
    started, which is what stops one retry becoming two answers.
    """

    async def scenario():
        app, spy = deployment(tmp_path)
        from tests.entry.test_channel_ingress import binding_for

        runtime = ChannelRuntime(
            app,
            [
                binding_for(
                    Transport(),
                    adapter="telegram",
                    sender_policy=SenderPolicy(
                        allowed_senders=frozenset({OWNER}),
                        bot_identity=BOT_USERNAME,
                    ),
                )
            ],
        )
        await runtime.start()
        channel = telegram_channel(runtime)
        update = telegram_update()
        result = await channel._submit_control_inbound(update, "analyse this")
        assert result.handle is not None
        await result.handle.wait()
        await runtime.close(WAIT_S)
        return spy

    spy = run(scenario())

    (inbound,) = spy.delivered
    assert inbound.source_request_id == "42:7"
    assert inbound.session_id == "telegram:42"
    assert inbound.sender == OWNER
    assert inbound.surface == "telegram"
    assert inbound.values[VALUE_CHAT_TYPE] == "private"
    assert inbound.values[VALUE_MENTIONS] == ()
    assert inbound.values[VALUE_REPLY_TARGET] == {
        "schema_version": 1,
        "kind": "channel",
        "adapter": "telegram",
        "account_namespace": "bot-1",
        "destination_id": "42",
    }


def test_a_telegram_refusal_that_is_safe_to_explain_is_explained(tmp_path):
    """Not every refusal is a secret. A full queue is a "try again".

    The one that stays silent is :data:`CODE_OWNER_DENIED`, asserted above:
    answering an unknown sender confirms the bot exists and that they were
    checked against a list.
    """

    async def scenario():
        app, _spy = deployment(tmp_path, max_queued_per_session=1)
        from tests.entry.test_channel_ingress import binding_for

        runtime = ChannelRuntime(
            app,
            [
                binding_for(
                    Transport(),
                    adapter="telegram",
                    sender_policy=SenderPolicy(
                        allowed_senders=frozenset({OWNER}),
                        bot_identity=BOT_USERNAME,
                    ),
                )
            ],
        )
        await runtime.start()
        channel = telegram_channel(runtime)
        updates = [telegram_update(chat_id=42) for _ in range(3)]
        for index, update in enumerate(updates):
            update.message.message_id = index
            await channel._submit_control_inbound(update, "analyse this")
        await runtime.close(WAIT_S)
        return updates

    updates = run(scenario())

    assert updates[0].message.replies == []
    assert updates[1].message.replies == []
    assert any("retry" in reply.lower() for reply in updates[2].message.replies)


def test_a_telegram_photo_is_refused_without_being_fetched(tmp_path):
    """Plan 0031 §5.3 discards the photo path rather than accepting it.

    ``Message`` carries ``content: str`` and no content parts
    (``omicsclaw/schema/message.py:178-179``), so an accepted photo
    would have been dropped between the adapter and the model. The handler
    answers in one sentence and touches no file API — the fake below would
    raise if it did.
    """

    async def scenario():
        channel = telegram_channel()
        message = FakeTelegramMessage(text="")
        message.photo = (SimpleNamespace(file_id="boom"),)
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=OWNER, first_name="Owner"),
            effective_chat=SimpleNamespace(id=42, type="private"),
        )

        class Exploding:
            async def get_file(self, *args, **kwargs):
                raise AssertionError("a discarded photo must never be downloaded")

        await channel._handle_photo(update, SimpleNamespace(bot=Exploding()))
        return message

    message = run(scenario())

    assert len(message.replies) == 1
    assert "cannot read images" in message.replies[0]


def test_an_unknown_telegram_sender_is_refused_before_anything_is_read(tmp_path):
    """The command handlers' own gate, which runs before any work."""

    async def scenario():
        channel = telegram_channel()
        update = telegram_update(user_id="stranger")
        return channel._owner_update_allowed(update)

    assert run(scenario()) is False


# ---- Telegram: the binding -------------------------------------------


class FakeTelegramApp:
    def __init__(self, username: str | None = "omicsclaw_bot", bot_id: int = 1):
        self.bot = SimpleNamespace(
            get_me=self._get_me, send_message=self._send_message
        )
        self._username = username
        self._bot_id = bot_id
        self.sent: list[dict] = []
        self.started = False

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        self.started = True

    async def _get_me(self):
        return SimpleNamespace(id=self._bot_id, username=self._username)

    async def _send_message(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(message_id=1)


def test_the_telegram_binding_carries_both_halves_of_the_gate():
    """Owners and this bot's own handle, read back from the platform.

    The account namespace is authenticated rather than configured, so one
    process serving two bots cannot deliver one bot's reply with the
    other's token.
    """

    async def scenario():
        channel = TelegramChannel(
            TelegramConfig(bot_token="t", allowed_senders={OWNER}, admin_chat_id=99)
        )
        channel._app = FakeTelegramApp()
        return await channel.prepare_control_binding()

    binding = run(scenario())

    assert binding.adapter == "telegram"
    assert binding.account_namespace == "bot-1"
    assert binding.sender_policy.allowed_senders == frozenset({OWNER, "99"})
    assert binding.sender_policy.bot_identity == "@omicsclaw_bot"
    assert binding.attachment_input_enabled is False
    assert binding.text_chunk_limit == 4096


def test_the_telegram_binding_refuses_to_start_with_no_owners():
    """``CLAUDE.md``'s "refuses to start without it", on this adapter."""

    async def scenario():
        channel = TelegramChannel(TelegramConfig(bot_token="t"))
        channel._app = FakeTelegramApp()
        with pytest.raises(RuntimeError, match="TELEGRAM_ALLOWED_SENDERS"):
            await channel.prepare_control_binding()

    run(scenario())


# ---- Feishu ------------------------------------------------------------


def feishu_channel(runtime=None, *, bot_open_id: str = BOT_OPEN_ID) -> FeishuChannel:
    channel = FeishuChannel(
        FeishuConfig(
            app_id="cli_app",
            app_secret="secret",
            bot_open_id=bot_open_id,
            allowed_senders={OWNER},
        )
    )
    channel._running = True
    if runtime is not None:
        channel.bind_control_runtime(runtime, loop=asyncio.get_event_loop())
    channel.activate_ingress()
    return channel


def feishu_event(
    *,
    text: str = "analyse this",
    sender: str = OWNER,
    chat_type: str = "p2p",
    message_type: str = "text",
    mentions=(),
    message_id: str = "om_1",
):
    message = SimpleNamespace(
        chat_id="oc_1",
        message_id=message_id,
        chat_type=chat_type,
        message_type=message_type,
        content=json.dumps({"text": text}),
        create_time=None,
        mentions=tuple(
            SimpleNamespace(id=SimpleNamespace(open_id=open_id))
            for open_id in mentions
        ),
    )
    return SimpleNamespace(
        event=SimpleNamespace(
            message=message,
            sender=SimpleNamespace(sender_id=SimpleNamespace(open_id=sender)),
        )
    )


async def feishu_runtime(app, transport):
    from tests.entry.test_channel_ingress import binding_for

    runtime = ChannelRuntime(
        app,
        [
            binding_for(
                transport,
                adapter="feishu",
                sender_policy=SenderPolicy(
                    allowed_senders=frozenset({OWNER}), bot_identity=BOT_OPEN_ID
                ),
            )
        ],
    )
    await runtime.start()
    return runtime


def test_a_feishu_direct_message_from_the_owner_runs_from_the_sdk_thread(tmp_path):
    """The real hand-off: the SDK's handler is synchronous and off-loop.

    ``_handle_event`` is called on a thread that is not running the loop,
    exactly as ``lark-oapi`` calls it, and reaches the agent through
    ``run_coroutine_threadsafe``. A test that called it from the loop would
    not be testing the arrangement that exists.
    """

    async def scenario():
        app, spy = deployment(tmp_path)
        transport = Transport()
        runtime = await feishu_runtime(app, transport)
        channel = feishu_channel(runtime)
        await asyncio.to_thread(channel._handle_event, feishu_event())
        for handle in app.sessions.running():
            await handle.wait()
        await runtime.close(WAIT_S)
        return spy, transport

    spy, transport = run(scenario())

    (inbound,) = spy.delivered
    assert inbound.source_request_id == "om_1"
    assert inbound.session_id == "feishu:oc_1"
    assert inbound.values[VALUE_CHAT_TYPE] == "p2p"
    assert inbound.values[VALUE_REPLY_TARGET]["destination_kind"] == "chat_id"
    assert transport.sent == ["ok"]


def test_a_feishu_message_from_a_non_owner_creates_no_exchange(tmp_path):
    """§9-9 (b) on the Feishu adapter. Nothing runs and nothing answers."""

    async def scenario():
        app, spy = deployment(tmp_path)
        transport = Transport()
        runtime = await feishu_runtime(app, transport)
        channel = feishu_channel(runtime)
        await asyncio.to_thread(
            channel._handle_event, feishu_event(sender="ou_stranger")
        )
        await runtime.close(0.0)
        return spy, transport

    spy, transport = run(scenario())

    assert spy.delivered == []
    assert transport.sent == []


def test_a_feishu_group_message_without_a_mention_creates_no_exchange(tmp_path):
    """§9-9 (c) on the Feishu adapter — the owner, in a group, to somebody."""

    async def scenario():
        app, spy = deployment(tmp_path)
        runtime = await feishu_runtime(app, Transport())
        channel = feishu_channel(runtime)
        await asyncio.to_thread(
            channel._handle_event,
            feishu_event(chat_type="group", mentions=("ou_colleague",)),
        )
        await runtime.close(0.0)
        return spy

    assert run(scenario()).delivered == []


def test_a_feishu_group_message_fails_closed_with_no_bot_open_id(tmp_path):
    """``FEISHU_BOT_OPEN_ID`` absent: refused even when it mentions us.

    There is nothing to match the mention against, so "it mentioned us" is
    not a fact the adapter has.
    """

    async def scenario():
        app, spy = deployment(tmp_path)
        runtime = await feishu_runtime(app, Transport())
        channel = feishu_channel(runtime, bot_open_id="")
        await asyncio.to_thread(
            channel._handle_event,
            feishu_event(chat_type="group", mentions=(BOT_OPEN_ID,)),
        )
        await runtime.close(0.0)
        return spy

    assert run(scenario()).delivered == []


def test_a_feishu_group_message_that_mentions_this_bot_runs(tmp_path):
    """And the mention markup is stripped before the model reads it."""

    async def scenario():
        app, spy = deployment(tmp_path)
        runtime = await feishu_runtime(app, Transport())
        channel = feishu_channel(runtime)
        await asyncio.to_thread(
            channel._handle_event,
            feishu_event(
                chat_type="group",
                mentions=(BOT_OPEN_ID,),
                text="@_user_1 analyse this",
            ),
        )
        for handle in app.sessions.running():
            await handle.wait()
        await runtime.close(WAIT_S)
        return spy

    spy = run(scenario())

    (inbound,) = spy.delivered
    assert inbound.text == "analyse this"
    assert inbound.values[VALUE_MENTIONS] == (BOT_OPEN_ID,)


def test_a_feishu_message_reports_the_mentions_it_actually_carried(tmp_path):
    """The adapter reports what the platform said, not what it hopes.

    Two gates apply the same rule here: the adapter's own, which stops the
    work early, and :class:`~omicsclaw.entry.ingress.SenderPolicy`'s at
    ingress, which holds for every adapter in the package. The second is
    only worth having if the facts it reads are true, and an adapter that
    always reported "this mentioned me" would pass every *other* test in
    this file — measured: it does.
    """

    async def scenario():
        app, spy = deployment(tmp_path)
        runtime = await feishu_runtime(app, Transport())
        channel = feishu_channel(runtime)
        await asyncio.to_thread(
            channel._handle_event,
            feishu_event(mentions=("ou_colleague",)),
        )
        for handle in app.sessions.running():
            await handle.wait()
        await runtime.close(WAIT_S)
        return spy

    spy = run(scenario())

    (inbound,) = spy.delivered
    assert inbound.values[VALUE_MENTIONS] == ("ou_colleague",)


def test_a_feishu_non_text_message_creates_no_exchange(tmp_path):
    """The text-only slice, unchanged by the port.

    Admitting an image would put a synthesized ``[image]`` placeholder in
    the transcript and answer a question the owner never asked.
    """

    async def scenario():
        app, spy = deployment(tmp_path)
        runtime = await feishu_runtime(app, Transport())
        channel = feishu_channel(runtime)
        await asyncio.to_thread(
            channel._handle_event, feishu_event(message_type="image")
        )
        await runtime.close(0.0)
        return spy

    assert run(scenario()).delivered == []


def test_a_redelivered_feishu_message_is_not_answered_twice(tmp_path):
    """Feishu redelivers events at least once; the message id is the key."""

    async def scenario():
        app, spy = deployment(tmp_path)
        transport = Transport()
        runtime = await feishu_runtime(app, transport)
        channel = feishu_channel(runtime)
        await asyncio.to_thread(channel._handle_event, feishu_event())
        for handle in app.sessions.running():
            await handle.wait()
        await asyncio.to_thread(channel._handle_event, feishu_event())
        await runtime.close(WAIT_S)
        return spy, transport

    spy, transport = run(scenario())

    assert len(spy.delivered) == 1, "the local cache stopped the repeat"
    assert transport.sent == ["ok"]


def test_the_feishu_binding_carries_both_halves_of_the_gate():
    async def scenario():
        channel = feishu_channel()
        channel._lark_client = object()
        return await channel.prepare_control_binding()

    binding = run(scenario())

    assert binding.adapter == "feishu"
    assert binding.account_namespace == "cli_app"
    assert binding.sender_policy.allowed_senders == frozenset({OWNER})
    assert binding.sender_policy.bot_identity == BOT_OPEN_ID
    assert binding.attachment_input_enabled is False


def test_the_feishu_binding_refuses_to_start_without_an_allowlist():
    """The sentence ``CLAUDE.md`` uses, enforced where starting happens."""

    async def scenario():
        channel = FeishuChannel(
            FeishuConfig(app_id="a", app_secret="s", bot_open_id=BOT_OPEN_ID)
        )
        with pytest.raises(RuntimeError, match="FEISHU_ALLOWED_SENDERS"):
            await channel.prepare_control_binding()

    run(scenario())


def test_the_feishu_binding_refuses_to_start_without_a_bot_open_id():
    """"Group chats fail closed without it" — and so does start-up."""

    async def scenario():
        channel = FeishuChannel(
            FeishuConfig(app_id="a", app_secret="s", allowed_senders={OWNER})
        )
        with pytest.raises(RuntimeError, match="FEISHU_BOT_OPEN_ID"):
            await channel.prepare_control_binding()

    run(scenario())


# ---- composition -------------------------------------------------------


def test_composition_collects_every_binding_before_building_anything(tmp_path):
    """One runtime for several channels, and all-or-nothing.

    A channel that cannot authenticate must fail the whole start rather
    than leave half a deployment answering messages.
    """

    async def scenario():
        app, _spy = deployment(tmp_path)
        telegram = TelegramChannel(
            TelegramConfig(bot_token="t", allowed_senders={OWNER})
        )
        telegram._app = FakeTelegramApp()
        feishu = FeishuChannel(
            FeishuConfig(
                app_id="cli_app",
                app_secret="secret",
                bot_open_id=BOT_OPEN_ID,
                allowed_senders={OWNER},
            )
        )
        feishu._lark_client = object()
        runtime = await compose_channel_runtime(app, [telegram, feishu])
        assert telegram._control_runtime is runtime
        assert feishu._control_runtime is runtime
        assert runtime.started
        assert runtime.binding("telegram") is not None
        assert runtime.binding("feishu") is not None
        # Ingress stays closed: opening it is the manager's barrier.
        assert telegram.ingress_active is False
        assert feishu.ingress_active is False
        await runtime.close(0.0)

    run(scenario())


def test_a_channel_that_cannot_authenticate_fails_the_whole_composition(tmp_path):
    """And every channel that got as far as authenticating is released."""

    async def scenario():
        app, _spy = deployment(tmp_path)
        telegram = TelegramChannel(
            TelegramConfig(bot_token="t", allowed_senders={OWNER})
        )
        telegram._app = FakeTelegramApp()
        broken = FeishuChannel(FeishuConfig(app_id="a", app_secret="s"))
        with pytest.raises(RuntimeError):
            await compose_channel_runtime(app, [telegram, broken])
        return telegram

    telegram = run(scenario())

    assert telegram._control_runtime is None
    assert telegram._running is False
