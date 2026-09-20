"""Three acceptance states, and the one that must never be retried.

Plan 0031 §5.3. ``telegram_delivery.py`` has carried the sentence "The Pump
must not retry blindly" since before this rebuild, and it is the whole
reason that file was ported rather than rewritten: a send that timed out
may already be in front of the person, so resending it produces a second
visible reply that nothing upstream can see, count or take back.

Everything here runs against a fake transport. There is no network and no
token on this machine, and a delivery test that needed one would be a test
nobody runs.
"""

from __future__ import annotations

import asyncio

from omicsclaw.entry.channel.delivery import (
    ATTEMPT_TIMEOUT_S,
    MAX_DELIVERY_ATTEMPTS,
    RETRY_BASE_S,
    RETRY_MAX_S,
    DeliveryAdapterResult,
    DeliveryAttemptOutcome,
    DeliveryAttemptRequest,
    deliver,
)
from omicsclaw.entry.ingress import Acceptance

WAIT_S = 5.0

TARGET = {"kind": "channel", "adapter": "telegram", "destination_id": "42"}


class Recorder:
    """A transport that answers from a script and remembers every call."""

    def __init__(self, *outcomes: DeliveryAdapterResult) -> None:
        self.script = list(outcomes)
        self.calls: list[DeliveryAttemptRequest] = []

    async def __call__(self, request: DeliveryAttemptRequest) -> DeliveryAdapterResult:
        self.calls.append(request)
        index = min(len(self.calls) - 1, len(self.script) - 1)
        return self.script[index]


class Clock:
    """A sleep that records instead of waiting."""

    def __init__(self) -> None:
        self.slept: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.slept.append(seconds)


def accepted() -> DeliveryAdapterResult:
    return DeliveryAdapterResult(outcome=DeliveryAttemptOutcome.ACCEPTED)


def unknown() -> DeliveryAdapterResult:
    return DeliveryAdapterResult(
        outcome=DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN,
        error_code="telegram_acceptance_unknown",
    )


def retryable(after_ms: int | None = None) -> DeliveryAdapterResult:
    return DeliveryAdapterResult(
        outcome=DeliveryAttemptOutcome.NOT_ACCEPTED_RETRYABLE,
        error_code="telegram_retry_after",
        retry_after_ms=after_ms,
    )


def permanent() -> DeliveryAdapterResult:
    return DeliveryAdapterResult(
        outcome=DeliveryAttemptOutcome.REJECTED_PERMANENT,
        error_code="telegram_forbidden",
    )


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, WAIT_S))


# ---- the projection ----------------------------------------------------


def test_four_adapter_outcomes_project_onto_three_acceptances():
    """The narrowing is spelled once, here and in one method.

    Both refusals become ``REJECTED``: the wire vocabulary has three
    members and a ``retry_after``, so "refused, try later" is carried by
    the hint rather than by a fourth name.
    """
    assert accepted().as_delivery_result().acceptance is Acceptance.ACCEPTED
    assert unknown().as_delivery_result().acceptance is Acceptance.UNKNOWN
    assert permanent().as_delivery_result().acceptance is Acceptance.REJECTED
    assert retryable(3000).as_delivery_result().acceptance is Acceptance.REJECTED


def test_a_retry_hint_crosses_in_seconds_and_a_missing_one_stays_missing():
    """``None`` means *the platform did not say*, which is not zero.

    A caller that read a missing hint as "retry now" would turn one rate
    limit into a tighter loop against the thing that just rate-limited it.
    """
    assert retryable(2500).as_delivery_result().retry_after == 2.5
    assert retryable(None).as_delivery_result().retry_after is None
    assert permanent().as_delivery_result().retry_after is None


def test_only_one_outcome_is_retryable():
    """``ACCEPTANCE_UNKNOWN`` is deliberately not among them.

    It is the state that *might* have been delivered, so it is the state a
    retry can duplicate. Keeping this readable on the result is why the
    four-member enum survived the projection onto three.
    """
    assert retryable().retryable is True
    assert accepted().retryable is False
    assert permanent().retryable is False
    assert unknown().retryable is False


# ---- the pump ----------------------------------------------------------


def test_an_accepted_message_is_sent_exactly_once():
    transport = Recorder(accepted())
    clock = Clock()

    result = run(
        deliver(
            transport,
            ["hello"],
            item_prefix="t1",
            reply_target=TARGET,
            sleep=clock,
        )
    )

    assert result.acceptance is Acceptance.ACCEPTED
    assert len(transport.calls) == 1
    assert clock.slept == []


def test_an_unknown_acceptance_is_never_retried():
    """The sentence this file exists for, as an assertion.

    One call, no sleep, and an ``UNKNOWN`` handed back so the caller knows
    it does not know.
    """
    transport = Recorder(unknown())
    clock = Clock()

    result = run(
        deliver(
            transport,
            ["hello"],
            item_prefix="t1",
            reply_target=TARGET,
            sleep=clock,
        )
    )

    assert result.acceptance is Acceptance.UNKNOWN
    assert len(transport.calls) == 1, "an unknown acceptance may already have landed"
    assert clock.slept == []


def test_a_permanent_rejection_is_not_retried():
    """The platform answered and refused; the answer is proof, not noise."""
    transport = Recorder(permanent())
    clock = Clock()

    result = run(
        deliver(
            transport, ["hi"], item_prefix="t1", reply_target=TARGET, sleep=clock
        )
    )

    assert result.acceptance is Acceptance.REJECTED
    assert len(transport.calls) == 1
    assert clock.slept == []


def test_a_rate_limit_is_retried_up_to_the_bound_and_then_given_up():
    """Bounded, because an unbounded retry is an outage that never ends."""
    transport = Recorder(retryable(2000))
    clock = Clock()

    result = run(
        deliver(
            transport, ["hi"], item_prefix="t1", reply_target=TARGET, sleep=clock
        )
    )

    assert result.acceptance is Acceptance.REJECTED
    assert len(transport.calls) == MAX_DELIVERY_ATTEMPTS
    assert clock.slept == [2.0, 2.0], "the platform's own hint, not our backoff"


def test_a_rate_limit_with_no_hint_backs_off_exponentially():
    """A platform that refuses without saying when still gets a wait."""
    transport = Recorder(retryable(None))
    clock = Clock()

    run(deliver(transport, ["hi"], item_prefix="t1", reply_target=TARGET, sleep=clock))

    assert clock.slept == [RETRY_BASE_S, RETRY_BASE_S * 2]


def test_an_absurd_retry_hint_is_capped():
    """A platform may ask for a week; the adapters bound it at a week.

    Honouring that inside one exchange would pin a Task open for a week,
    so the wait is clamped and the attempt budget runs out instead.
    """
    transport = Recorder(retryable(7 * 24 * 60 * 60 * 1000))
    clock = Clock()

    run(deliver(transport, ["hi"], item_prefix="t1", reply_target=TARGET, sleep=clock))

    assert clock.slept == [RETRY_MAX_S, RETRY_MAX_S]


def test_a_retried_message_keeps_one_item_id():
    """Feishu deduplicates by it for an hour, which only holds if it is stable.

    A fresh id per attempt would defeat the single mechanism that makes a
    retry safe on that platform.
    """
    transport = Recorder(retryable(0))
    clock = Clock()

    run(deliver(transport, ["hi"], item_prefix="t9", reply_target=TARGET, sleep=clock))

    assert {call.item_id for call in transport.calls} == {"t9-0"}
    assert [call.attempt_no for call in transport.calls] == [1, 2, 3]


def test_the_chunks_of_one_reply_get_distinct_ids_and_go_in_order():
    transport = Recorder(accepted())

    run(
        deliver(
            transport,
            ["first", "second", "third"],
            item_prefix="t1",
            reply_target=TARGET,
            sleep=Clock(),
        )
    )

    assert [call.text for call in transport.calls] == ["first", "second", "third"]
    assert [call.item_id for call in transport.calls] == ["t1-0", "t1-1", "t1-2"]


def test_a_failed_chunk_stops_the_rest_of_the_reply():
    """Paragraph three without paragraph two is a different answer."""
    transport = Recorder(accepted(), permanent())
    clock = Clock()

    result = run(
        deliver(
            transport,
            ["first", "second", "third"],
            item_prefix="t1",
            reply_target=TARGET,
            sleep=clock,
        )
    )

    assert result.acceptance is Acceptance.REJECTED
    assert [call.text for call in transport.calls] == ["first", "second"]


def test_an_adapter_that_raises_is_an_unknown_acceptance():
    """It told us nothing about whether the message arrived.

    Letting the exception out instead would abort the reply of an exchange
    that has already run and already cost a model call.
    """

    async def explode(request):
        raise RuntimeError("the socket went away")

    result = run(
        deliver(
            explode, ["hi"], item_prefix="t1", reply_target=TARGET, sleep=Clock()
        )
    )

    assert result.acceptance is Acceptance.UNKNOWN


def test_an_adapter_that_returns_nonsense_is_an_unknown_acceptance():
    """A result this pump cannot read is not evidence of anything."""

    async def confused(request):
        return "sent!"

    result = run(
        deliver(
            confused, ["hi"], item_prefix="t1", reply_target=TARGET, sleep=Clock()
        )
    )

    assert result.acceptance is Acceptance.UNKNOWN


def test_an_adapter_that_hangs_is_abandoned_as_unknown():
    """Bounded at :data:`ATTEMPT_TIMEOUT_S`, and the timeout is not a retry.

    Driven with a patched constant rather than by waiting thirty seconds,
    because a test that waits out a production timeout is a test that gets
    deleted.
    """

    async def hang(request):
        await asyncio.sleep(WAIT_S * 10)
        raise AssertionError("unreachable")

    async def scenario():
        from omicsclaw.entry.channel import delivery as module

        original = module.ATTEMPT_TIMEOUT_S
        module.ATTEMPT_TIMEOUT_S = 0.01
        try:
            return await deliver(
                hang, ["hi"], item_prefix="t1", reply_target=TARGET, sleep=Clock()
            )
        finally:
            module.ATTEMPT_TIMEOUT_S = original

    result = run(scenario())

    assert result.acceptance is Acceptance.UNKNOWN
    assert ATTEMPT_TIMEOUT_S == 30.0, "the production bound is back"


def test_an_empty_chunk_costs_no_provider_call():
    transport = Recorder(accepted())

    result = run(
        deliver(
            transport,
            ["", "text", ""],
            item_prefix="t1",
            reply_target=TARGET,
            sleep=Clock(),
        )
    )

    assert result.acceptance is Acceptance.ACCEPTED
    assert [call.text for call in transport.calls] == ["text"]


# ---- the ported adapters, over fake platform objects -------------------


class RetryAfter(Exception):
    """Stands in for ``telegram.error.RetryAfter``, which is not installed.

    ``telegram_delivery._is_error`` falls back to comparing the exception's
    class name **exactly** so that the classification survives without the
    SDK, which is the situation on this machine and in any deployment that
    installed only the Feishu extra. The name below is therefore
    load-bearing: rename it and this stops being a rate limit.
    """

    def __init__(self, retry_after: float) -> None:
        super().__init__("flood control")
        self.retry_after = retry_after


class Forbidden(Exception):
    pass


class FakeBot:
    """The two methods ``TelegramDeliveryAdapter`` touches."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.sent: list[dict] = []

    async def send_message(self, **kwargs):
        if self.error is not None:
            raise self.error
        self.sent.append(kwargs)
        return type("Sent", (), {"message_id": 17})()


def telegram_request(text: str = "hello", **target) -> DeliveryAttemptRequest:
    reply_target = {"kind": "channel", "adapter": "telegram", "destination_id": "42"}
    reply_target.update(target)
    return DeliveryAttemptRequest(
        item_id="t1-0", text=text, reply_target=reply_target
    )


def test_the_ported_telegram_adapter_still_classifies_three_ways():
    """The port changed its imports; this is the behaviour underneath them."""
    from omicsclaw.entry.channel.telegram_delivery import TelegramDeliveryAdapter

    ok = run(TelegramDeliveryAdapter(FakeBot()).attempt(telegram_request()))
    assert ok.outcome is DeliveryAttemptOutcome.ACCEPTED
    assert ok.provider_evidence == {"message_id": 17}

    limited = run(
        TelegramDeliveryAdapter(FakeBot(RetryAfter(4))).attempt(telegram_request())
    )
    assert limited.outcome is DeliveryAttemptOutcome.NOT_ACCEPTED_RETRYABLE
    assert limited.retry_after_ms == 4000

    refused = run(
        TelegramDeliveryAdapter(FakeBot(Forbidden())).attempt(telegram_request())
    )
    assert refused.outcome is DeliveryAttemptOutcome.REJECTED_PERMANENT

    lost = run(
        TelegramDeliveryAdapter(FakeBot(OSError("timed out"))).attempt(
            telegram_request()
        )
    )
    assert lost.outcome is DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN
    assert lost.error_code == "telegram_acceptance_unknown"


def test_the_ported_telegram_adapter_refuses_a_target_it_cannot_address():
    """A malformed target never reached Telegram, so it is not ambiguous."""
    from omicsclaw.entry.channel.telegram_delivery import TelegramDeliveryAdapter

    bot = FakeBot()
    result = run(
        TelegramDeliveryAdapter(bot).attempt(telegram_request(destination_id=None))
    )

    assert result.outcome is DeliveryAttemptOutcome.REJECTED_PERMANENT
    assert result.error_code == "telegram_invalid_delivery"
    assert bot.sent == []


def test_the_ported_telegram_adapter_passes_a_thread_id_through():
    from omicsclaw.entry.channel.telegram_delivery import TelegramDeliveryAdapter

    bot = FakeBot()
    run(TelegramDeliveryAdapter(bot).attempt(telegram_request(thread_id="7")))

    assert bot.sent == [{"chat_id": 42, "text": "hello", "message_thread_id": 7}]


class _FeishuResponse:
    def __init__(self, ok: bool, code: int = 0, message_id: str = "om_x") -> None:
        self._ok = ok
        self.code = code
        self.data = type("Data", (), {"message_id": message_id})()

    def success(self) -> bool:
        return self._ok


class FakeLarkClient:
    """``client.im.v1.message.create``, and nothing else."""

    def __init__(self, response) -> None:
        self.requests: list[object] = []
        create = self._create
        self.im = type(
            "Im",
            (),
            {
                "v1": type(
                    "V1",
                    (),
                    {"message": type("Message", (), {"create": create})()},
                )()
            },
        )()
        self.response = response

    def _create(self, request):
        self.requests.append(request)
        return self.response


def feishu_request(**target) -> DeliveryAttemptRequest:
    reply_target = {
        "kind": "channel",
        "adapter": "feishu",
        "destination_id": "oc_1",
        "destination_kind": "chat_id",
    }
    reply_target.update(target)
    return DeliveryAttemptRequest(
        item_id="t1-0", text="hello", reply_target=reply_target
    )


def test_the_ported_feishu_adapter_still_classifies_three_ways():
    """``request_builder`` is injected because ``lark-oapi`` is not installed."""
    from omicsclaw.entry.channel.feishu_delivery import FeishuDeliveryAdapter

    def builder(arguments):
        return arguments

    ok = run(
        FeishuDeliveryAdapter(
            FakeLarkClient(_FeishuResponse(True)), request_builder=builder
        ).attempt(feishu_request())
    )
    assert ok.outcome is DeliveryAttemptOutcome.ACCEPTED

    limited = run(
        FeishuDeliveryAdapter(
            FakeLarkClient(_FeishuResponse(False, code=230020)),
            request_builder=builder,
        ).attempt(feishu_request())
    )
    assert limited.outcome is DeliveryAttemptOutcome.NOT_ACCEPTED_RETRYABLE

    refused = run(
        FeishuDeliveryAdapter(
            FakeLarkClient(_FeishuResponse(False, code=230001)),
            request_builder=builder,
        ).attempt(feishu_request())
    )
    assert refused.outcome is DeliveryAttemptOutcome.REJECTED_PERMANENT

    confused = run(
        FeishuDeliveryAdapter(
            FakeLarkClient(_FeishuResponse(False, code=0)), request_builder=builder
        ).attempt(feishu_request())
    )
    assert confused.outcome is DeliveryAttemptOutcome.ACCEPTANCE_UNKNOWN


def test_the_ported_feishu_adapter_sends_the_item_id_as_its_dedup_key():
    """The port must not have dropped the one field that makes a retry safe."""
    from omicsclaw.entry.channel.feishu_delivery import FeishuDeliveryAdapter

    captured: list[dict] = []

    def builder(arguments):
        captured.append(dict(arguments))
        return arguments

    run(
        FeishuDeliveryAdapter(
            FakeLarkClient(_FeishuResponse(True)), request_builder=builder
        ).attempt(feishu_request())
    )

    assert captured[0]["uuid"] == "t1-0"
    assert captured[0]["receive_id"] == "oc_1"
    assert captured[0]["receive_id_type"] == "chat_id"


def test_the_ported_feishu_adapter_refuses_an_unaddressable_target():
    from omicsclaw.entry.channel.feishu_delivery import FeishuDeliveryAdapter

    result = run(
        FeishuDeliveryAdapter(
            FakeLarkClient(_FeishuResponse(True)), request_builder=dict
        ).attempt(feishu_request(destination_kind="carrier_pigeon"))
    )

    assert result.outcome is DeliveryAttemptOutcome.REJECTED_PERMANENT
    assert result.error_code == "feishu_invalid_delivery"


def test_neither_delivery_adapter_imports_its_sdk_to_be_used():
    """Both are usable on a machine with neither vendor SDK installed.

    Which is this machine, and is the reason the tests above can exist at
    all: the classification lives in the adapter, not in the SDK.
    """
    import sys

    assert "telegram" not in sys.modules
    assert "lark_oapi" not in sys.modules
