"""The Slack adapter, over fake platform objects.

``slack-sdk`` is not installed here and there is no network, so every
platform object below is a stand-in — which is the point: the gates being
asserted live in the adapter, and one that only held when Slack was
reachable would be no gate at all.

What this file tests is what is *particular* to Slack: a mention written into
the message body rather than reported as an entity, a channel type that says
whether a room is a DM, a ``thread_ts`` that has to survive as far as the
delivery call, and a rate limit that arrives as an HTTP header. The eight
rules Slack shares with every other adapter are in
``test_channel_cutover_conformance.py``, which drives it through the fixture
registered at the bottom.
"""

from __future__ import annotations

import asyncio
import dataclasses
import itertools

import pytest

from omicsclaw.entry.channel import reply_target
from omicsclaw.entry.channel.delivery import (
    DeliveryAttemptOutcome,
    DeliveryAttemptRequest,
)
from omicsclaw.entry.channel.runtime import (
    ChannelSubmission,
    TurnAcceptanceResult,
    TurnAcceptanceStatus,
)
from omicsclaw.entry.channel.slack import SlackChannel, SlackConfig, slack_mentions
from omicsclaw.entry.channel.slack_delivery import SlackDeliveryAdapter
from omicsclaw.entry.ingress import VALUE_CHAT_TYPE, VALUE_MENTIONS
from tests.entry.channel_conformance import (  # type: ignore[import-not-found]
    ChannelFixture,
    DeliveryCase,
    MentionGuard,
    SentCall,
    register,
)
from tests.entry.test_channel_ingress import (  # type: ignore[import-not-found]
    OWNER,
)

WAIT_S = 5.0
BOT_USER = "UBOT"
BOT_HANDLE = f"<@{BOT_USER}>"
TEAM = "T1"
CHANNEL = "C1"


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, WAIT_S))


# ---- platform doubles --------------------------------------------------


class SlackApiError(Exception):
    """Stands in for ``slack_sdk.errors.SlackApiError``, which is not installed.

    ``slack_delivery`` falls back to comparing the exception's class name
    **exactly** so that the classification survives without the SDK — which is
    the situation here and in any deployment that installed only another
    platform's extra. The name below is therefore load-bearing: rename it and
    a rate limit stops being one.
    """

    def __init__(self, response) -> None:
        super().__init__("slack api error")
        self.response = response


class SlackResponse(dict):
    """A Slack response: a mapping that also carries status and headers."""

    def __init__(self, payload, *, status_code: int = 200, headers=None) -> None:
        super().__init__(payload)
        self.status_code = status_code
        self.headers = headers or {}


class FakeSlackWebClient:
    """The three Web API methods this adapter touches."""

    def __init__(
        self,
        *,
        error: Exception | None = None,
        team_id: str = TEAM,
        user_id: str = BOT_USER,
    ) -> None:
        self.error = error
        self.team_id = team_id
        self.user_id = user_id
        self.texts: list[str] = []
        self.calls: list[dict] = []
        self.deleted: list[dict] = []

    async def auth_test(self):
        return {"team_id": self.team_id, "user_id": self.user_id, "user": "omicsclaw"}

    async def chat_postMessage(self, **kwargs):
        if self.error is not None:
            raise self.error
        self.calls.append(kwargs)
        self.texts.append(kwargs["text"])
        return SlackResponse({"ok": True, "ts": "111.222"})

    async def chat_delete(self, **kwargs):
        self.deleted.append(kwargs)
        return SlackResponse({"ok": True})


_TS = itertools.count(1)


def slack_event(
    *,
    text: str = "analyse this",
    sender: str = OWNER,
    group: bool = False,
) -> dict:
    return {
        "type": "message",
        "user": sender,
        "channel": CHANNEL,
        "text": text,
        "ts": f"{next(_TS)}.000100",
        "channel_type": "channel" if group else "im",
    }


def slack_channel(web_client: FakeSlackWebClient | None = None) -> SlackChannel:
    channel = SlackChannel(
        SlackConfig(
            bot_token="xoxb-test",
            app_token="xapp-test",
            allowed_senders={OWNER},
        )
    )
    channel._web_client = web_client or FakeSlackWebClient()
    return channel


# ---- mentions ----------------------------------------------------------


def test_a_mention_is_read_out_of_the_body_because_that_is_where_slack_puts_it():
    """Slack reports no entity list; the ``<@U…>`` in the text is the fact."""
    assert slack_mentions("hi <@UBOT> and <@U9> please") == ("<@UBOT>", "<@U9>")


def test_a_message_mentioning_nobody_yields_no_mentions():
    """Which is what makes a channel message fail closed."""
    assert slack_mentions("just talking") == ()


# ---- the binding -------------------------------------------------------


def test_the_slack_binding_is_authenticated_rather_than_configured():
    """``auth_test`` names the account and the handle, so a second app's
    token cannot deliver this one's reply."""

    async def scenario():
        return await slack_channel().prepare_control_binding()

    binding = run(scenario())

    assert binding.adapter == "slack"
    assert binding.account_namespace == "team-T1"
    assert binding.sender_policy.allowed_senders == frozenset({OWNER})
    assert binding.sender_policy.bot_identity == BOT_HANDLE
    assert binding.attachment_input_enabled is False


def test_the_slack_binding_refuses_to_start_with_no_owners():
    """"Admits nobody else and refuses to start without it", on this adapter."""

    async def scenario():
        channel = SlackChannel(SlackConfig(bot_token="x", app_token="y"))
        channel._web_client = FakeSlackWebClient()
        with pytest.raises(RuntimeError, match="SLACK_ALLOWED_SENDERS"):
            await channel.prepare_control_binding()

    run(scenario())


# ---- inbound -----------------------------------------------------------


class CountingRuntime:
    """A runtime that records submissions and answers as it is told to."""

    def __init__(self, *outcomes: TurnAcceptanceStatus) -> None:
        self.messages: list = []
        self._outcomes = list(outcomes)

    @property
    def app(self):  # pragma: no cover - the commands are not exercised here
        return None

    def binding(self, _name):  # pragma: no cover - same
        return None

    async def submit(self, message):
        self.messages.append(message)
        status = (
            self._outcomes.pop(0)
            if self._outcomes
            else TurnAcceptanceStatus.ACCEPTED
        )
        return ChannelSubmission(
            acceptance=TurnAcceptanceResult(
                status=status,
                turn_id="t1",
                code="queue_full" if status is TurnAcceptanceStatus.REJECTED else "",
            )
        )


def bound(runtime, web_client=None) -> SlackChannel:
    channel = slack_channel(web_client)
    channel.bot_identity = BOT_HANDLE
    channel._account_namespace = f"team-{TEAM}"
    channel.bind_control_runtime(runtime)
    channel._running = True
    channel.activate_ingress()
    return channel


def test_a_slack_message_carries_its_thread_its_key_and_its_mentions():
    """The thread is an extra on the reply target, so an answer stays in it.

    A busy channel with three questions in three threads is otherwise three
    answers at top level, in an order nobody can match to the questions.
    """

    async def scenario():
        runtime = CountingRuntime()
        channel = bound(runtime)
        event = slack_event(text=f"{BOT_HANDLE} analyse this", group=True)
        event["thread_ts"] = "900.000100"
        await channel._on_message(event, is_group=True)
        return runtime, event

    runtime, event = run(scenario())

    (inbound,) = runtime.messages
    assert inbound.text == "analyse this"
    assert inbound.session_id == f"slack:{CHANNEL}"
    assert inbound.source_request_id == f"{CHANNEL}:{event['ts']}"
    assert inbound.surface == "slack"
    assert inbound.values[VALUE_CHAT_TYPE] == "group"
    assert inbound.values[VALUE_MENTIONS] == (BOT_HANDLE,)
    target = inbound.values["reply_target"]
    assert target["adapter"] == "slack"
    assert target["destination_id"] == CHANNEL
    assert target["thread_ts"] == "900.000100"


def test_a_slack_direct_message_is_private_and_needs_no_mention():
    async def scenario():
        runtime = CountingRuntime()
        await bound(runtime)._on_message(slack_event(), is_group=False)
        return runtime

    (inbound,) = run(scenario()).messages

    assert inbound.values[VALUE_CHAT_TYPE] == "private"
    assert inbound.values[VALUE_MENTIONS] == ()


def test_a_slack_channel_message_without_a_mention_is_not_even_submitted():
    """The early gate. ``SenderPolicy`` would refuse it anyway; this stops
    the work before the runtime is asked."""

    async def scenario():
        runtime = CountingRuntime()
        await bound(runtime)._on_message(slack_event(group=True), is_group=True)
        return runtime

    assert run(scenario()).messages == []


def test_slacks_own_messages_are_ignored():
    """A bot that answers itself is a loop with a rate limit at the end."""

    async def scenario():
        runtime = CountingRuntime()
        channel = bound(runtime)
        await channel._on_message(slack_event(sender=BOT_USER), is_group=False)
        event = slack_event()
        event["bot_id"] = "B1"
        await channel._on_message(event, is_group=False)
        return runtime

    assert run(scenario()).messages == []


# ---- trap 12: the dedup cache must not mark before acceptance ----------


def test_a_refused_slack_message_can_still_land_when_slack_resends_it():
    """The local cache is an optimisation and must never be the authority.

    Slack resends an event it has not heard back about. If the cache marked
    the message on arrival, a submission that failed — a full queue, a
    runtime still starting — plus that resend would lose the person's
    message entirely: no exchange, no answer, and one warning in a log.
    """

    async def scenario():
        runtime = CountingRuntime(
            TurnAcceptanceStatus.REJECTED, TurnAcceptanceStatus.ACCEPTED
        )
        channel = bound(runtime)
        event = slack_event()
        await channel._on_message(event, is_group=False)
        await channel._on_message(dict(event), is_group=False)
        return runtime

    runtime = run(scenario())

    assert len(runtime.messages) == 2, "the resend of a refused message must land"


def test_a_slack_message_that_was_accepted_is_not_submitted_twice():
    """And the other direction, so the cache is not simply switched off."""

    async def scenario():
        runtime = CountingRuntime()
        channel = bound(runtime)
        event = slack_event()
        await channel._on_message(event, is_group=False)
        await channel._on_message(dict(event), is_group=False)
        return runtime

    assert len(run(scenario()).messages) == 1


# ---- the closed second path --------------------------------------------


def test_slack_refuses_the_legacy_standalone_entry_point():
    """A bot cannot own the agent it speaks for: the runtime is shared."""
    with pytest.raises(RuntimeError, match="ChannelRuntime"):
        slack_channel().run_bot()


# ---- delivery ----------------------------------------------------------


def slack_request(text: str = "hello", **target) -> DeliveryAttemptRequest:
    built = reply_target.build("slack", f"team-{TEAM}", CHANNEL, **target)
    return DeliveryAttemptRequest(item_id="t1-0", text=text, reply_target=built)


def test_the_slack_adapter_classifies_a_rate_limit_from_the_header():
    """The one refusal with evidence that nothing was delivered."""
    response = SlackResponse(
        {"ok": False, "error": "ratelimited"},
        status_code=429,
        headers={"Retry-After": "7"},
    )
    adapter = SlackDeliveryAdapter(FakeSlackWebClient(error=SlackApiError(response)))

    result = run(adapter.attempt(slack_request()))

    assert result.outcome is DeliveryAttemptOutcome.NOT_ACCEPTED_RETRYABLE
    assert result.retry_after_ms == 7000


def test_a_slack_refusal_slack_named_is_permanent():
    """The platform answered, and its answer is proof of non-delivery."""
    response = SlackResponse(
        {"ok": False, "error": "channel_not_found"}, status_code=404
    )
    adapter = SlackDeliveryAdapter(FakeSlackWebClient(error=SlackApiError(response)))

    result = run(adapter.attempt(slack_request()))

    assert result.outcome is DeliveryAttemptOutcome.REJECTED_PERMANENT


def test_an_unrecognised_slack_error_is_ambiguous_rather_than_retryable():
    """A 4xx this adapter does not know is reported as unknown.

    An omission then costs one reply the pump declines to retry, which is
    safe; guessing "retryable" would put a second copy of an answer in front
    of somebody who may already have read the first.
    """
    response = SlackResponse({"ok": False, "error": "something_new"}, status_code=400)
    adapter = SlackDeliveryAdapter(FakeSlackWebClient(error=SlackApiError(response)))

    result = run(adapter.attempt(slack_request()))

    assert result.outcome is DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN
    assert not result.retryable


def test_the_slack_adapter_sends_into_the_thread_the_target_names():
    client = FakeSlackWebClient()

    run(SlackDeliveryAdapter(client).attempt(slack_request(thread_ts="900.1")))

    assert client.calls == [
        {"channel": CHANNEL, "text": "hello", "thread_ts": "900.1"}
    ]


def slack_escaped(text: str) -> str:
    """*text* as Slack's documented rule says to send it: ``&``, ``<``, ``>``."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


SLACK_MENTIONS = (
    "<!channel> <!here> <!everyone> <@U0123> <#C0456> <!subteam^S0789> "
    "<https://example.com|a link> a & b < c > d"
)


def test_slack_is_handed_text_in_which_no_mention_syntax_survives():
    """Every Slack mention is written between ``<`` and ``>``.

    ``<!channel>``, ``<!here>`` and ``<!everyone>`` notify a whole room,
    ``<@U…>`` a person, ``<!subteam^…>`` a user group, and ``<#C…>`` and
    ``<url|text>`` are links. Escaping the three characters Slack's own rule
    names makes each of them display as the characters the model wrote, and
    nothing else about the text changes.
    """
    client = FakeSlackWebClient()

    result = run(SlackDeliveryAdapter(client).attempt(slack_request(SLACK_MENTIONS)))

    assert result.outcome is DeliveryAttemptOutcome.ACCEPTED
    assert client.texts == [slack_escaped(SLACK_MENTIONS)]
    assert "<" not in client.texts[0] and ">" not in client.texts[0]


def test_slack_escapes_the_text_as_written_so_an_entity_is_shown_not_decoded():
    """The escape is applied to the model's text, not to a guess at its intent.

    A model that writes ``&lt;!channel&gt;`` means those characters. Leaving
    them alone would let Slack decode them into ``<!channel>`` on screen, and
    an escape that skipped entities would be one a model could step around.
    """
    client = FakeSlackWebClient()

    run(SlackDeliveryAdapter(client).attempt(slack_request("AT&amp;T &lt;!here&gt;")))

    assert client.texts == ["AT&amp;amp;T &amp;lt;!here&amp;gt;"]


def test_a_threaded_slack_reply_is_escaped_like_any_other():
    """The thread is an argument beside the text, not a second way to send it."""
    client = FakeSlackWebClient()

    run(
        SlackDeliveryAdapter(client).attempt(
            slack_request("<!here> a & b", thread_ts="900.1")
        )
    )

    assert client.calls == [
        {"channel": CHANNEL, "text": "&lt;!here&gt; a &amp; b", "thread_ts": "900.1"}
    ]


class FlakySlackWebClient(FakeSlackWebClient):
    """Refuses the first ``chat.postMessage`` with a rate limit, then accepts."""

    def __init__(self) -> None:
        super().__init__()
        self.attempted: list[str] = []

    async def chat_postMessage(self, **kwargs):
        self.attempted.append(kwargs["text"])
        if len(self.attempted) == 1:
            raise SlackApiError(
                SlackResponse(
                    {"ok": False, "error": "ratelimited"},
                    status_code=429,
                    headers={"Retry-After": "0"},
                )
            )
        return await super().chat_postMessage(**kwargs)


def test_a_retried_slack_send_is_escaped_once_not_once_per_attempt():
    """Each attempt escapes the pump's original text, never the last payload.

    An adapter that kept its escaped text and escaped it again on the retry
    would put ``&amp;amp;`` in front of the person — only on the sends that
    happened to be rate-limited, which is how nobody would notice.
    """
    from omicsclaw.entry.channel.delivery import deliver
    from omicsclaw.entry.ingress import Acceptance

    client = FlakySlackWebClient()

    async def no_wait(_seconds: float) -> None:
        return None

    result = run(
        deliver(
            SlackDeliveryAdapter(client),
            ["a & b <!channel>"],
            item_prefix="t1",
            reply_target=slack_request().reply_target,
            sleep=no_wait,
        )
    )

    assert result.acceptance is Acceptance.ACCEPTED
    assert client.attempted == ["a &amp; b &lt;!channel&gt;"] * 2


def test_every_chunk_of_a_slack_reply_is_escaped_exactly_once(tmp_path):
    """Chunking happens on the model's text; escaping happens per provider call.

    Escaping first would let the chunker cut ``&amp;`` in half and would
    count five characters for every ``&``; escaping twice would show the
    person the entities themselves. Each payload is therefore exactly its
    chunk, escaped once.
    """
    from omicsclaw.entry.channel.base import chunk_text
    from omicsclaw.entry.channel.runtime import ChannelRuntime
    from omicsclaw.schema import Message, Role
    from tests.entry.test_channel_runtime import (  # type: ignore[import-not-found]
        deployment,
    )
    from tests.entry.test_turn_runner import (  # type: ignore[import-not-found]
        Scripted,
    )

    answer = "\n\n".join(["<!channel> a & b < c > d, see <@U0123>"] * 6)
    limit = 60
    client = FakeSlackWebClient()

    async def scenario():
        app = deployment(
            tmp_path, Scripted(Message(role=Role.ASSISTANT, content=answer))
        )
        channel = slack_channel(client)
        binding = await channel.prepare_control_binding()
        runtime = ChannelRuntime(
            app, [dataclasses.replace(binding, text_chunk_limit=limit)]
        )
        await runtime.start()
        channel.bind_control_runtime(runtime, loop=asyncio.get_running_loop())
        channel._running = True
        channel.activate_ingress()
        await channel._on_message(slack_event(text="analyse this"), is_group=False)
        for handle in app.sessions.running():
            await handle.wait()
        await runtime.close(WAIT_S)

    run(scenario())

    chunks = chunk_text(answer, limit)
    assert len(chunks) > 1
    assert client.texts == [slack_escaped(chunk) for chunk in chunks]


def test_slack_command_output_is_escaped_on_every_chunk(tmp_path):
    """A slash command answers through the same adapter, one chunk per call."""
    from omicsclaw.entry.channel.base import chunk_text
    from omicsclaw.entry.channel.binding import ChannelSurfaceBinding
    from omicsclaw.entry.ingress import SenderPolicy

    client = FakeSlackWebClient()
    listing = "\n".join(f"<!channel> file & {index}.h5ad" for index in range(20))
    limit = 80

    class OneBinding:
        app = None

        def binding(self, _name):
            return ChannelSurfaceBinding(
                adapter="slack",
                account_namespace=f"team-{TEAM}",
                sender_policy=SenderPolicy(
                    allowed_senders=frozenset({OWNER}), bot_identity=BOT_HANDLE
                ),
                delivery_adapter=SlackDeliveryAdapter(client),
                text_chunk_limit=limit,
            )

    async def scenario():
        channel = slack_channel(client)
        channel.bind_control_runtime(OneBinding())
        await channel.send_command_output(
            reply_target.build("slack", f"team-{TEAM}", CHANNEL), listing
        )

    run(scenario())

    chunks = chunk_text(listing, limit)
    assert len(chunks) > 1
    assert client.texts == [slack_escaped(chunk) for chunk in chunks]


def test_the_slack_typing_hint_is_a_fixed_ellipsis():
    """The one direct post that is not model text, so it needs no escape."""
    client = FakeSlackWebClient()

    run(slack_channel(client)._send_typing(CHANNEL))

    assert client.calls == [{"channel": CHANNEL, "text": "…"}]


def test_a_target_for_another_platform_never_reaches_slack():
    client = FakeSlackWebClient()
    other = reply_target.build("discord", "bot-1", "42")

    result = run(
        SlackDeliveryAdapter(client).attempt(
            DeliveryAttemptRequest(item_id="t1-0", text="hi", reply_target=other)
        )
    )

    assert result.outcome is DeliveryAttemptOutcome.REJECTED_PERMANENT
    assert result.error_code == "slack_invalid_delivery"
    assert client.calls == []


# ---- the conformance fixture -------------------------------------------


async def _conformance_submit(
    channel: SlackChannel,
    *,
    text: str,
    sender: str = OWNER,
    group: bool = False,
    mentions_bot: bool = False,
) -> None:
    body = f"{BOT_HANDLE} {text}" if (group and mentions_bot) else text
    await channel._on_message(
        slack_event(text=body, sender=sender, group=group), is_group=group
    )


def _conformance_accepting_delivery():
    client = FakeSlackWebClient()
    return SlackDeliveryAdapter(client), client.texts


class _MentionRecordingSlackWebClient(FakeSlackWebClient):
    """Records each ``chat.postMessage`` as a :class:`SentCall`."""

    def __init__(self) -> None:
        super().__init__()
        self.sent_calls: list[SentCall] = []

    async def chat_postMessage(self, **kwargs):
        # Slack has no per-message switch that turns mentions off, so every
        # call is one whose text must itself be inert.
        self.sent_calls.append(SentCall(text=kwargs["text"], notifies=True))
        return await super().chat_postMessage(**kwargs)


def _conformance_mention_delivery():
    client = _MentionRecordingSlackWebClient()
    return SlackDeliveryAdapter(client), client.sent_calls


def _conformance_delivery_cases() -> tuple[DeliveryCase, ...]:
    limited = SlackApiError(
        SlackResponse(
            {"ok": False, "error": "ratelimited"},
            status_code=429,
            headers={"Retry-After": "3"},
        )
    )
    return (
        DeliveryCase(
            "timeout",
            SlackDeliveryAdapter(FakeSlackWebClient(error=asyncio.TimeoutError())),
            DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
        ),
        DeliveryCase(
            "unknown",
            SlackDeliveryAdapter(FakeSlackWebClient(error=RuntimeError("?"))),
            DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
        ),
        DeliveryCase(
            "rate_limited",
            SlackDeliveryAdapter(FakeSlackWebClient(error=limited)),
            DeliveryAttemptOutcome.NOT_ACCEPTED_RETRYABLE,
        ),
    )


register(
    ChannelFixture(
        name="slack",
        new_channel=slack_channel,
        reply_target=lambda channel: reply_target.build(
            "slack", f"team-{TEAM}", CHANNEL, thread_ts="900.000100"
        ),
        accepting_delivery=_conformance_accepting_delivery,
        delivery_cases=_conformance_delivery_cases,
        submit=_conformance_submit,
        direct_replies=lambda _channel, transport: list(transport.sent),
        has_groups=True,
        strips_markdown=False,
        unregistered_commands_reach_the_agent=True,
        mention_guard=MentionGuard(
            live_spellings=("<!channel>", "<!here>"),
            accepting_delivery=_conformance_mention_delivery,
        ),
    )
)
