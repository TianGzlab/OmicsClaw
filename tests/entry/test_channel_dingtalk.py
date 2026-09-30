"""The DingTalk adapter, over fake platform objects.

There is no ``httpx`` call and no socket here. What this file tests is what
is *particular* to DingTalk: an attribution that arrives as a boolean rather
than as a list, a reply that goes to a person even when the question was
asked in a group, a robot code the outbound call cannot do without, and a
send whose response used not to be read at all. The eight rules DingTalk
shares with every other adapter are in
``test_channel_cutover_conformance.py``, which drives it through the fixture
registered at the bottom.
"""

from __future__ import annotations

import asyncio
import itertools
import json

import pytest

from omicsclaw.entry.channel import reply_target
from omicsclaw.entry.channel.delivery import (
    DeliveryAttemptOutcome,
    DeliveryAttemptRequest,
)
from omicsclaw.entry.channel.dingtalk import DingTalkChannel, DingTalkConfig
from omicsclaw.entry.channel.dingtalk_delivery import DingTalkDeliveryAdapter
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
CLIENT_ID = "dingoabc"


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, WAIT_S))


# ---- platform doubles --------------------------------------------------


class FakeHttpResponse:
    def __init__(self, payload: dict, *, status_code: int = 200, headers=None) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self) -> dict:
        return self._payload


class FakeHttpClient:
    """The two calls this adapter makes, and a way to make either fail."""

    def __init__(
        self,
        *,
        send_response: FakeHttpResponse | None = None,
        send_error: Exception | None = None,
        token: str = "tok",
    ) -> None:
        self.send_response = send_response or FakeHttpResponse({})
        self.send_error = send_error
        self.token = token
        self.posts: list[tuple[str, dict]] = []
        self.closed = False

    async def post(self, url: str, json=None, headers=None):
        self.posts.append((url, json or {}))
        if "accessToken" in url:
            return FakeHttpResponse({"accessToken": self.token, "expireIn": 7200})
        if "gateway" in url:
            return FakeHttpResponse({"endpoint": "wss://x", "ticket": "t"})
        if self.send_error is not None:
            raise self.send_error
        return self.send_response

    async def aclose(self) -> None:
        self.closed = True


_MESSAGE_IDS = itertools.count(9000)


def dingtalk_frame(
    *,
    text: str = "analyse this",
    sender: str = OWNER,
    group: bool = False,
    at_list: bool = False,
) -> dict:
    payload = {
        "text": {"content": text},
        "senderStaffId": sender,
        "conversationType": "2" if group else "1",
    }
    if at_list:
        payload["isInAtList"] = True
    return {
        "type": "CALLBACK",
        "headers": {"messageId": f"dt-{next(_MESSAGE_IDS)}"},
        "data": json.dumps(payload, ensure_ascii=False),
    }


def dingtalk_channel(http_client: FakeHttpClient | None = None) -> DingTalkChannel:
    channel = DingTalkChannel(
        DingTalkConfig(
            client_id=CLIENT_ID,
            client_secret="secret",
            allowed_senders={OWNER},
        )
    )
    channel._http_client = http_client or FakeHttpClient()
    return channel


def bound(runtime, http_client: FakeHttpClient | None = None) -> DingTalkChannel:
    channel = dingtalk_channel(http_client)
    channel.bot_identity = CLIENT_ID
    channel._account_namespace = f"robot-{CLIENT_ID}"
    channel.bind_control_runtime(runtime)
    channel._running = True
    channel.activate_ingress()
    return channel


# ---- the binding -------------------------------------------------------


def test_the_dingtalk_binding_carries_the_robot_identity_a_mention_resolves_to():
    async def scenario():
        return await dingtalk_channel().prepare_control_binding()

    binding = run(scenario())

    assert binding.adapter == "dingtalk"
    assert binding.account_namespace == f"robot-{CLIENT_ID}"
    assert binding.sender_policy.bot_identity == CLIENT_ID
    assert binding.sender_policy.allowed_senders == frozenset({OWNER})
    assert binding.attachment_input_enabled is False


def test_the_dingtalk_binding_refuses_to_start_with_no_owners():
    async def scenario():
        channel = DingTalkChannel(DingTalkConfig(client_id="a", client_secret="b"))
        channel._http_client = FakeHttpClient()
        with pytest.raises(RuntimeError, match="DINGTALK_ALLOWED_SENDERS"):
            await channel.prepare_control_binding()

    run(scenario())


# ---- trap 4: an assertion, translated rather than assumed --------------


def test_a_group_message_dingtalk_says_mentioned_us_names_this_robot():
    """``isInAtList`` is the whole of DingTalk's attribution, so it is read."""

    async def scenario():
        runtime = CountingRuntime()
        await bound(runtime)._on_ws_message(
            dingtalk_frame(group=True, at_list=True)
        )
        return runtime

    (inbound,) = run(scenario()).messages

    assert inbound.values[VALUE_CHAT_TYPE] == "group"
    assert inbound.values[VALUE_MENTIONS] == (CLIENT_ID,)


def test_a_group_message_dingtalk_did_not_flag_creates_no_exchange():
    """The mutation this test exists to kill is one line long.

    Putting the robot identity into the mention list unconditionally makes
    ``SenderPolicy.admits`` return true for every group message — a gate
    that is always open, which reads in a diff exactly like a gate.
    """

    async def scenario():
        runtime = CountingRuntime()
        await bound(runtime)._on_ws_message(
            dingtalk_frame(group=True, at_list=False)
        )
        return runtime

    assert run(scenario()).messages == []


def test_a_one_to_one_dingtalk_message_needs_no_mention_at_all():
    async def scenario():
        runtime = CountingRuntime()
        await bound(runtime)._on_ws_message(dingtalk_frame())
        return runtime

    (inbound,) = run(scenario()).messages

    assert inbound.values[VALUE_CHAT_TYPE] == "private"
    assert inbound.values[VALUE_MENTIONS] == ()
    assert inbound.surface == "dingtalk"
    assert inbound.values["reply_target"]["robot_code"] == CLIENT_ID


def test_a_dingtalk_ping_is_answered_and_creates_nothing():
    """The stream's keepalive, which is not a message."""

    async def scenario():
        runtime = CountingRuntime()
        http = FakeHttpClient()
        channel = bound(runtime, http)
        sent: list[dict] = []

        async def _record(payload):
            sent.append(payload)

        channel._ws_send_json = _record
        await channel._on_ws_message(
            {"type": "SYSTEM", "headers": {"topic": "ping"}, "data": ""}
        )
        return runtime, sent

    runtime, sent = run(scenario())

    assert runtime.messages == []
    assert len(sent) == 1


def test_a_refused_dingtalk_message_can_still_land_when_it_is_resent():
    """The local cache is an optimisation and never the authority."""

    async def scenario():
        from omicsclaw.entry.channel.runtime import TurnAcceptanceStatus

        runtime = CountingRuntime(
            TurnAcceptanceStatus.REJECTED, TurnAcceptanceStatus.ACCEPTED
        )
        channel = bound(runtime)
        frame = dingtalk_frame()
        await channel._on_ws_message(frame)
        await channel._on_ws_message(dict(frame))
        return runtime

    assert len(run(scenario()).messages) == 2


def test_dingtalk_refuses_the_legacy_standalone_entry_point():
    with pytest.raises(RuntimeError, match="ChannelRuntime"):
        dingtalk_channel().run_stream()


# ---- delivery ----------------------------------------------------------


def dingtalk_request(text: str = "hello", **target) -> DeliveryAttemptRequest:
    built = reply_target.build(
        "dingtalk",
        f"robot-{CLIENT_ID}",
        target.pop("destination", OWNER),
        **({"robot_code": CLIENT_ID} | target),
    )
    return DeliveryAttemptRequest(item_id="t1-0", text=text, reply_target=built)


async def _token() -> str:
    return "tok"


def adapter(http: FakeHttpClient) -> DingTalkDeliveryAdapter:
    return DingTalkDeliveryAdapter(http, _token)


def test_the_dingtalk_adapter_reads_the_response_it_used_to_ignore():
    """A send nobody looks at is not a send that succeeded."""
    http = FakeHttpClient(
        send_response=FakeHttpResponse(
            {"code": "Forbidden.AccessDenied"}, status_code=403
        )
    )

    result = run(adapter(http).attempt(dingtalk_request()))

    assert result.outcome is DeliveryAttemptOutcome.REJECTED_PERMANENT
    assert result.error_code == "dingtalk_rejected"


def test_a_dingtalk_rate_limit_is_the_one_refusal_worth_repeating():
    http = FakeHttpClient(
        send_response=FakeHttpResponse(
            {"code": "requestLimit"}, status_code=429, headers={"Retry-After": "5"}
        )
    )

    result = run(adapter(http).attempt(dingtalk_request()))

    assert result.outcome is DeliveryAttemptOutcome.NOT_ACCEPTED_RETRYABLE
    assert result.retry_after_ms == 5000


def test_a_dingtalk_server_error_is_ambiguous_rather_than_retryable():
    """A 5xx may have crossed the acceptance seam; a resend can duplicate."""
    http = FakeHttpClient(send_response=FakeHttpResponse({}, status_code=503))

    result = run(adapter(http).attempt(dingtalk_request()))

    assert result.outcome is DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN
    assert not result.retryable


def test_a_dingtalk_send_that_raised_is_ambiguous():
    http = FakeHttpClient(send_error=asyncio.TimeoutError())

    result = run(adapter(http).attempt(dingtalk_request()))

    assert result.outcome is DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN


def test_a_dingtalk_target_without_a_robot_code_never_reaches_dingtalk():
    """``batchSend`` names the robot that speaks; nothing else can supply it."""
    http = FakeHttpClient()
    built = reply_target.build("dingtalk", f"robot-{CLIENT_ID}", OWNER)

    result = run(
        adapter(http).attempt(
            DeliveryAttemptRequest(item_id="t1-0", text="hi", reply_target=built)
        )
    )

    assert result.outcome is DeliveryAttemptOutcome.REJECTED_PERMANENT
    assert result.error_code == "dingtalk_invalid_delivery"
    assert http.posts == []


def test_a_delivered_dingtalk_message_carries_the_markdown_payload():
    http = FakeHttpClient(send_response=FakeHttpResponse({}, status_code=200))

    result = run(adapter(http).attempt(dingtalk_request("**bold**")))

    assert result.outcome is DeliveryAttemptOutcome.ACCEPTED
    (_url, body), = http.posts
    assert body["robotCode"] == CLIENT_ID
    assert body["userIds"] == [OWNER]
    assert json.loads(body["msgParam"])["text"] == "**bold**"


# ---- the conformance fixture -------------------------------------------


async def _conformance_submit(
    channel: DingTalkChannel,
    *,
    text: str,
    sender: str = OWNER,
    group: bool = False,
    mentions_bot: bool = False,
) -> None:
    await channel._on_ws_message(
        dingtalk_frame(text=text, sender=sender, group=group, at_list=mentions_bot)
    )


def _conformance_accepting_delivery():
    http = FakeHttpClient(send_response=FakeHttpResponse({}, status_code=200))
    texts: list[str] = []

    class _Recording(DingTalkDeliveryAdapter):
        async def attempt(self, request):
            result = await super().attempt(request)
            if result.outcome is DeliveryAttemptOutcome.ACCEPTED:
                texts.append(json.loads(http.posts[-1][1]["msgParam"])["text"])
            return result

    return _Recording(http, _token), texts


def _conformance_delivery_cases() -> tuple[DeliveryCase, ...]:
    limited = FakeHttpClient(
        send_response=FakeHttpResponse(
            {"code": "requestLimit"}, status_code=429, headers={"Retry-After": "2"}
        )
    )
    return (
        DeliveryCase(
            "timeout",
            adapter(FakeHttpClient(send_error=asyncio.TimeoutError())),
            DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
        ),
        DeliveryCase(
            "unknown",
            adapter(FakeHttpClient(send_error=RuntimeError("?"))),
            DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
        ),
        DeliveryCase(
            "rate_limited",
            adapter(limited),
            DeliveryAttemptOutcome.NOT_ACCEPTED_RETRYABLE,
        ),
    )


register(
    ChannelFixture(
        name="dingtalk",
        new_channel=dingtalk_channel,
        reply_target=lambda channel: reply_target.build(
            "dingtalk", f"robot-{CLIENT_ID}", OWNER, robot_code=CLIENT_ID
        ),
        accepting_delivery=_conformance_accepting_delivery,
        delivery_cases=_conformance_delivery_cases,
        submit=_conformance_submit,
        direct_replies=lambda _channel, transport: list(transport.sent),
        has_groups=True,
        strips_markdown=False,
        unregistered_commands_reach_the_agent=True,
    )
)
