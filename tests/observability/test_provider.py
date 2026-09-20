"""The model-call seam: a decorator the engine cannot tell apart."""

from __future__ import annotations

import pytest

from omicsclaw.observability import TracedProvider
from omicsclaw.observability.contract import NOOP_SPAN
from omicsclaw.provider import LLMProvider, ProviderError
from omicsclaw.schema import Message, Role, StreamChunkType, Usage

from ._support import (
    Exploding,
    RecordingMeter,
    RecordingTracer,
    Scripted,
    assistant,
    run,
    tool_turn,
)


def _traced(inner=None, **kwargs):
    tracer, meter = RecordingTracer(), RecordingMeter()
    inner = Scripted(assistant("hi", input_tokens=11, output_tokens=3)) if inner is None else inner
    return TracedProvider(inner, tracer, meter, **kwargs), tracer, meter


def test_it_satisfies_the_provider_protocol():
    traced, _, _ = _traced()

    assert isinstance(traced, LLMProvider)


def test_every_protocol_member_is_forwarded():
    """A fifth member added upstream must fail here, not vanish silently.

    The list is read off the Protocol rather than written down, which is
    the difference between a test that notices a widened contract and a
    comment that does not.
    """
    import typing

    required = set(typing._get_protocol_attrs(LLMProvider))

    assert required == {"name", "generate", "generate_stream", "bind"}
    for member in required:
        assert hasattr(TracedProvider, member), member


def test_the_name_is_the_inner_providers():
    """It reaches a person through ProviderError and a surface status line."""
    traced, _, _ = _traced()

    assert traced.name == "scripted"


def test_a_blocking_call_returns_exactly_what_the_inner_returned():
    inner = Scripted(assistant("answer", input_tokens=2))
    traced, _, _ = _traced(inner)

    completion = run(traced.generate([Message(role=Role.USER, content="q")]))

    assert completion.message.content == "answer"
    assert inner.calls == 1


def test_a_blocking_call_records_a_span_with_model_and_tokens():
    traced, tracer, meter = _traced(model="gpt-test")

    run(traced.generate([Message(role=Role.USER, content="q")]))

    span = tracer.named("omicsclaw.llm_request")[0]
    assert span.attributes["gen_ai.request.model"] == "gpt-test"
    assert span.attributes["llm.model"] == "gpt-test"
    assert span.attributes["gen_ai.system"] == "scripted"
    assert span.attributes["gen_ai.usage.input_tokens"] == 11
    assert span.attributes["llm.tokens.output"] == 3
    assert span.ended == 1
    assert meter.totals("omicsclaw.llm.tokens.input") == 11
    assert len(meter.records) == 1


def test_no_model_name_means_no_model_attribute_rather_than_an_empty_one():
    traced, tracer, _ = _traced()

    run(traced.generate([]))

    assert "llm.model" not in tracer.named("omicsclaw.llm_request")[0].attributes


def test_a_stream_is_passed_through_chunk_for_chunk():
    inner = Scripted(assistant("streamed", input_tokens=5, output_tokens=1))
    traced, _, _ = _traced(inner)

    async def drain():
        return [c async for c in traced.generate_stream([])]

    chunks = run(drain())

    assert [c.type for c in chunks] == [
        StreamChunkType.TEXT_DELTA,
        StreamChunkType.DONE,
    ]


def test_generate_stream_is_not_a_coroutine():
    """The engine checks ``hasattr(stream, "__aiter__")`` without awaiting."""
    traced, _, _ = _traced()

    stream = traced.generate_stream([])

    assert hasattr(stream, "__aiter__")
    run(_close(stream))


def test_a_streamed_call_records_its_usage_from_the_done_chunk():
    traced, tracer, meter = _traced(
        Scripted(assistant("s", input_tokens=8, output_tokens=2))
    )

    async def drain():
        async for _ in traced.generate_stream([]):
            pass

    run(drain())

    span = tracer.named("omicsclaw.llm_request")[0]
    assert span.attributes["llm.tokens.input"] == 8
    assert span.ended == 1
    assert meter.totals("omicsclaw.llm.tokens.output") == 2


def test_the_span_opens_on_the_first_chunk_not_at_the_call():
    """A generator's body starts at ``__anext__``; the timing must be honest."""
    traced, tracer, _ = _traced()

    stream = traced.generate_stream([])
    assert tracer.spans == []

    run(_drain(stream))
    assert len(tracer.named("omicsclaw.llm_request")) == 1


def test_abandoning_a_stream_still_closes_the_span():
    """The engine abandons a stream on cancellation; an open span never exports."""
    traced, tracer, _ = _traced()

    async def take_one():
        stream = traced.generate_stream([])
        async for _ in stream:
            break
        await stream.aclose()

    run(take_one())

    assert tracer.named("omicsclaw.llm_request")[0].ended == 1


def test_a_failed_call_records_the_shape_of_the_failure_but_not_its_words():
    """The repair of a claim that only held for *most* provider errors.

    This test used to assert the opposite — that the vendor's message is
    always recorded, because "a provider error describes an HTTP exchange,
    never the payload". That is true of ``429 rate limited`` and untrue of
    a content-policy refusal, which quotes the text it refused. With
    capture off, nothing that could carry a payload is written.
    """
    traced, tracer, meter = _traced(Exploding("429 rate limited"))

    with pytest.raises(ProviderError):
        run(traced.generate([]))

    span = tracer.named("omicsclaw.llm_request")[0]
    assert span.error == "ProviderError"
    assert span.attributes["error.type"] == "ProviderError"
    assert "error.message" not in span.attributes
    assert span.ended == 1


def test_a_failed_call_records_the_message_when_capture_is_on():
    """The companion, pinning that the words are available when asked for."""
    traced, tracer, _ = _traced(Exploding("429 rate limited"), capture_content=True)

    with pytest.raises(ProviderError):
        run(traced.generate([]))

    span = tracer.named("omicsclaw.llm_request")[0]
    assert "429 rate limited" in span.attributes["error.message"]


def test_a_status_code_survives_without_the_message():
    """"Was this a 429?" must stay answerable with capture off."""
    from omicsclaw.provider import ProviderError as PE

    class Rejecting:
        @property
        def name(self):
            return "rejecting"

        async def generate(self, messages, tools=None):
            raise PE("policy refused: <the user's prompt>", provider="x", status_code=400)

        def generate_stream(self, messages, tools=None):
            raise NotImplementedError

        def bind(self, **kw):
            return self

    traced, tracer, _ = _traced(Rejecting())

    with pytest.raises(ProviderError):
        run(traced.generate([]))

    span = tracer.named("omicsclaw.llm_request")[0]
    assert span.attributes["error.status_code"] == 400
    assert "the user's prompt" not in str(span.attributes)


def test_no_payload_reaches_an_llm_span_with_capture_off():
    """The security invariant over every attribute, not over known keys."""
    from omicsclaw.schema import Message as M, Role as R

    secret = "GSM12345 patient_07"
    traced, tracer, _ = _traced(model="gpt-test")

    run(traced.generate([M(role=R.USER, content=secret)]))

    written = " ".join(f"{k}={v}" for k, v in tracer.spans[0].attributes.items())
    for token in secret.split():
        assert token not in written
    assert not any("langfuse" in key for key in tracer.spans[0].attributes)


def test_a_failed_call_is_still_timed():
    """A backend that takes thirty seconds to fail is what a histogram is for."""
    traced, _, meter = _traced(Exploding())

    with pytest.raises(ProviderError):
        run(traced.generate([]))

    assert len(meter.records) == 1
    assert meter.records[0][0] == "omicsclaw.llm.request.duration"


def test_a_failed_stream_closes_its_span_too():
    traced, tracer, _ = _traced(Exploding())

    with pytest.raises(ProviderError):
        run(_drain(traced.generate_stream([])))

    assert tracer.named("omicsclaw.llm_request")[0].ended == 1


def test_bind_keeps_the_wrapper():
    """Otherwise compaction becomes the one model call that is never traced."""
    traced, _, _ = _traced()

    bound = traced.bind(model="summary-model")

    assert isinstance(bound, TracedProvider)


def test_bind_adopts_the_overridden_model_name():
    traced, tracer, _ = _traced(model="big")

    bound = traced.bind(model="small")
    run(bound.generate([]))

    assert tracer.named("omicsclaw.llm_request")[0].attributes["llm.model"] == "small"


def test_bind_without_a_model_keeps_the_one_it_had():
    traced, tracer, _ = _traced(model="big")

    run(traced.bind(temperature=0.1).generate([]))

    assert tracer.named("omicsclaw.llm_request")[0].attributes["llm.model"] == "big"


def test_the_conversation_is_not_recorded_by_default():
    traced, tracer, _ = _traced()

    run(traced.generate([Message(role=Role.USER, content="GSM12345 cohort")]))

    span = tracer.named("omicsclaw.llm_request")[0]
    assert "langfuse.observation.input" not in span.attributes
    assert "langfuse.observation.output" not in span.attributes


def test_the_conversation_is_recorded_when_capture_is_on():
    traced, tracer, _ = _traced(capture_content=True)

    run(traced.generate([Message(role=Role.USER, content="hello")]))

    span = tracer.named("omicsclaw.llm_request")[0]
    assert "hello" in span.attributes["langfuse.observation.input"]
    assert span.attributes["langfuse.observation.output"] == "hi"


def test_an_action_turn_records_the_calls_as_its_output():
    traced, tracer, _ = _traced(
        Scripted(tool_turn("bash", "read_file")), capture_content=True
    )

    run(traced.generate([]))

    output = tracer.named("omicsclaw.llm_request")[0].attributes[
        "langfuse.observation.output"
    ]
    assert "bash" in output and "read_file" in output


def test_a_tracer_that_is_down_does_not_take_the_model_call_with_it():
    """The hot path of a real exchange: telemetry may cost a span, never a run."""

    class Broken:
        def start_span(self, *a, **k):
            raise RuntimeError("backend down")

    traced = TracedProvider(
        Scripted(assistant("survived")), Broken(), RecordingMeter()
    )

    completion = run(traced.generate([]))

    assert completion.message.content == "survived"


def test_a_broken_tracer_leaves_the_call_recorded_against_the_noop_span():
    class Broken:
        def start_span(self, *a, **k):
            raise RuntimeError("down")

    meter = RecordingMeter()
    traced = TracedProvider(Scripted(assistant()), Broken(), meter)

    run(traced.generate([]))

    assert len(meter.records) == 1, "the meter still works when the tracer does not"


async def _drain(stream) -> None:
    async for _ in stream:
        pass


async def _close(stream) -> None:
    await stream.aclose()
