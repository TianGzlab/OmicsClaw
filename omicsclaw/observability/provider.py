"""One span per model call, by wrapping the contract the loop programs against.

The counterpart of ``observability/provider.go``, and the seam that needs
the least argument: :class:`~omicsclaw.provider.LLMProvider` is a
structural :class:`~typing.Protocol`, so a decorator satisfying it is
invisible to the engine. Nothing in :mod:`omicsclaw.engine` or
:mod:`omicsclaw.provider` changes, and a deployment that does not observe
never constructs one —
:meth:`~omicsclaw.observability.telemetry.Telemetry.trace_provider` hands
the inner provider straight back.

**Decorating a provider is safe in a way that decorating the registry was
not.** ``entry/assembly.py`` refuses to let anything wrap
:class:`~omicsclaw.tools.ToolRegistry` because the engine probes it with
:func:`isinstance` for two optional Protocols and a wrapper that forgets
one fails silently (defect R3). ``LLMProvider`` has no optional
Protocols: four members, all of them required, all forwarded here — and
``tests/observability/test_provider.py`` asserts the member list against
the Protocol so that a fifth one added upstream fails a test rather than
disappearing.

Imports :mod:`omicsclaw.provider`, :mod:`omicsclaw.schema` and this
package.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Sequence
from contextlib import aclosing
from typing import Any

from omicsclaw.provider import Completion, LLMProvider
from omicsclaw.schema import Message, StreamChunk, StreamChunkType, ToolDefinition, Usage

from .attributes import (
    ATTR_ERROR_MESSAGE,
    ATTR_ERROR_STATUS,
    ATTR_ERROR_TYPE,
    ATTR_GENAI_INPUT_TOKENS,
    ATTR_GENAI_OUTPUT_TOKENS,
    ATTR_GENAI_REQUEST_MODEL,
    ATTR_GENAI_SYSTEM,
    ATTR_CACHE_READ_TOKENS,
    ATTR_INPUT_TOKENS,
    ATTR_LANGFUSE_OBSERVATION_INPUT,
    ATTR_LANGFUSE_OBSERVATION_OUTPUT,
    ATTR_MODEL,
    ATTR_OUTPUT_TOKENS,
    METRIC_LLM_DURATION,
    METRIC_TOKENS_INPUT,
    METRIC_TOKENS_OUTPUT,
    SPAN_LLM_REQUEST,
)
from .contract import NOOP_SPAN, AttributeValue, Meter, Span, Tracer
from .scope import current_parent
from .serialize import serialize_messages, serialize_output

_log = logging.getLogger(__name__)

__all__ = ["TracedProvider"]


class TracedProvider:
    """An :class:`~omicsclaw.provider.LLMProvider` that spans its own calls.

    One :data:`~omicsclaw.observability.attributes.SPAN_LLM_REQUEST` per
    call, parented to whatever
    :func:`~omicsclaw.observability.scope.current_parent` says is open —
    the turn, normally; the interaction on the blocking path; nothing at
    all for a provider driven from a script, which produces a standalone
    trace rather than an error.
    """

    __slots__ = ("_capture", "_inner", "_meter", "_model", "_tracer")

    def __init__(
        self,
        inner: LLMProvider,
        tracer: Tracer,
        meter: Meter,
        *,
        model: str = "",
        capture_content: bool = False,
    ) -> None:
        self._inner = inner
        self._tracer = tracer
        self._meter = meter
        self._model = model
        self._capture = capture_content

    @property
    def inner(self) -> LLMProvider:
        """What this wraps. Exposed so a composition root can unwrap one
        for a test, and so ``tests/entry`` can assert what is mounted."""
        return self._inner

    @property
    def name(self) -> str:
        """The inner provider's name, unchanged.

        **Not** ``"traced:openai"``. The name reaches a person through
        :class:`~omicsclaw.provider.ProviderError`'s message and a
        surface's status line, and telling somebody their backend is
        called ``traced:openai`` would make telemetry look like a
        component that can fail on its own.
        """
        return self._inner.name

    async def generate(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None = None,
    ) -> Completion:
        """One blocking call, timed and recorded, and otherwise untouched."""
        span = self._start(messages)
        started = time.perf_counter()
        try:
            completion = await self._inner.generate(messages, tools)
        except BaseException as error:
            self._fail(span, error, time.perf_counter() - started)
            raise
        self._succeed(
            span,
            usage=completion.usage if completion is not None else None,
            output=completion.message if completion is not None else None,
            elapsed=time.perf_counter() - started,
        )
        return completion

    def generate_stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """One streaming call. Deliberately not ``async def``, as upstream.

        Returning the generator rather than awaiting it keeps the
        Protocol's shape — ``async for chunk in provider.generate_stream(…)``
        with no intervening ``await`` — which the engine relies on and
        which its ``hasattr(stream, "__aiter__")`` check would otherwise
        reject.
        """
        return self._stream(messages, tools)

    async def _stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None,
    ) -> AsyncIterator[StreamChunk]:
        """The generator behind :meth:`generate_stream`.

        The span opens on the first ``__anext__`` rather than when
        ``generate_stream`` was called, because that is when a generator's
        body starts. This is the honest timing — nothing has been sent
        before then — and it is also what puts the span under the right
        turn, since the lazy :class:`~omicsclaw.observability.scope.TurnScope`
        materialises at the same moment.

        ``finally`` closes the span on **every** exit including
        ``GeneratorExit``: the engine abandons a stream when a run is
        cancelled, and a span left open is a span never exported.
        ``aclosing`` propagates that closure to the inner provider, which
        is where the HTTP connection is released.
        """
        span = self._start(messages)
        started = time.perf_counter()
        usage: Usage | None = None
        final: Message | None = None
        failure: BaseException | None = None
        try:
            async with aclosing(self._inner.generate_stream(messages, tools)) as chunks:
                async for chunk in chunks:
                    if chunk.type is StreamChunkType.DONE:
                        final = chunk.message
                        if chunk.usage is not None:
                            usage = chunk.usage
                    yield chunk
        except BaseException as error:
            failure = error
            raise
        finally:
            elapsed = time.perf_counter() - started
            if failure is not None:
                self._fail(span, failure, elapsed)
            else:
                self._succeed(span, usage=usage, output=final, elapsed=elapsed)

    def bind(self, **overrides: Any) -> LLMProvider:
        """Bind the inner provider and keep the wrapper around the result.

        **Returning ``self._inner.bind(...)`` would be the obvious
        one-liner and would silently stop tracing.** Every bound provider
        in this tree is a real call path —
        ``entry/assembly.py:722`` binds a summarization model — so a bind
        that unwrapped telemetry would leave compaction as the one model
        call that never appears in a trace, which is also the call most
        likely to be the expensive surprise.

        ``overrides["model"]`` is adopted as the recorded model name when
        present, because that is the keyword this repository's one caller
        uses and a span labelled with the *unbound* model would be worse
        than one labelled with nothing.
        """
        return TracedProvider(
            self._inner.bind(**overrides),
            self._tracer,
            self._meter,
            model=str(overrides.get("model") or self._model),
            capture_content=self._capture,
        )

    # ---- internals -------------------------------------------------------

    def _start(self, messages: Sequence[Message]) -> Span:
        """Open the call's span, or hand back the no-op and carry on.

        This is the **hot path of an actual model call**, so nothing here
        may raise: a backend that went away mid-run must cost a missing
        span, not the exchange. Serialization is inside the guard too,
        because it is the step that touches a conversation of unknown
        shape.
        """
        try:
            attributes: dict[str, AttributeValue] = {
                ATTR_GENAI_SYSTEM: self._inner.name
            }
            if self._model:
                attributes[ATTR_MODEL] = self._model
                attributes[ATTR_GENAI_REQUEST_MODEL] = self._model
            if self._capture:
                attributes[ATTR_LANGFUSE_OBSERVATION_INPUT] = serialize_messages(
                    messages
                )
            return self._tracer.start_span(
                SPAN_LLM_REQUEST, parent=current_parent(), attributes=attributes
            )
        except Exception:
            _log.exception("telemetry could not open a span for a model call")
            return NOOP_SPAN

    def _succeed(
        self,
        span: Span,
        *,
        usage: Usage | None,
        output: Message | None,
        elapsed: float,
    ) -> None:
        attributes: dict[str, AttributeValue] = {}
        if usage is not None:
            attributes[ATTR_INPUT_TOKENS] = usage.input_tokens
            attributes[ATTR_OUTPUT_TOKENS] = usage.output_tokens
            attributes[ATTR_GENAI_INPUT_TOKENS] = usage.input_tokens
            attributes[ATTR_GENAI_OUTPUT_TOKENS] = usage.output_tokens
            if usage.cache_read_tokens:
                attributes[ATTR_CACHE_READ_TOKENS] = usage.cache_read_tokens
        if self._capture and output is not None:
            attributes[ATTR_LANGFUSE_OBSERVATION_OUTPUT] = serialize_output(output)
        if attributes:
            span.set_attributes(attributes)
        span.end()
        self._record(usage, elapsed)

    def _fail(self, span: Span, error: BaseException, elapsed: float) -> None:
        """Close a failed call: always the shape of it, the words only if asked.

        :data:`~omicsclaw.observability.attributes.ATTR_ERROR_TYPE` and
        :data:`~omicsclaw.observability.attributes.ATTR_ERROR_STATUS` are
        always recorded; the vendor's **message** is recorded only when
        content capture is on.

        **That gate is a repair, and the argument it replaces is worth
        keeping visible.** This used to record ``str(error)`` ungated,
        reasoning that a provider failure is raised by an SDK about an
        HTTP exchange and so describes the backend rather than the
        payload. True of ``429 rate limited`` and ``connection error``;
        not true of a content-policy refusal, which quotes the text it
        refused, or of a validation error, which quotes the field it could
        not parse. With capture off this layer promises that no payload
        leaves the process, and a promise with an exception that depends
        on which error a vendor happened to return is not one. Nothing
        diagnosable is lost: the class, the status and
        :data:`~omicsclaw.observability.attributes.ATTR_MODEL` — already
        on this span — survive.

        **An abandoned stream arrives here too**, as a
        :exc:`GeneratorExit`: the engine closes the provider's stream when
        a run is cancelled. That is an incomplete call and is marked as
        one.

        The duration is still recorded. A failing backend that takes
        thirty seconds to fail is the thing a latency histogram exists to
        show, and excluding failures would hide it.
        """
        span.record_error(error)
        attributes: dict[str, AttributeValue] = {
            ATTR_ERROR_TYPE: type(error).__name__
        }
        status = getattr(error, "status_code", None)
        if isinstance(status, int):
            attributes[ATTR_ERROR_STATUS] = status
        if self._capture:
            message = str(error)
            if message:
                attributes[ATTR_ERROR_MESSAGE] = message
        span.set_attributes(attributes)
        span.end()
        self._record(None, elapsed)

    def _record(self, usage: Usage | None, elapsed: float) -> None:
        """The three instruments this seam owns.

        Token counters live here rather than on the turn because this is
        the only place that sees **every** model call: a turn retried
        three times spends three calls' worth of prompt tokens and its
        ``TURN_END`` reports the last attempt alone.
        """
        dimensions = {ATTR_GENAI_SYSTEM: self._inner.name}
        if self._model:
            dimensions[ATTR_MODEL] = self._model
        self._meter.record(METRIC_LLM_DURATION, elapsed, dimensions)
        if usage is not None:
            self._meter.count(METRIC_TOKENS_INPUT, usage.input_tokens, dimensions)
            self._meter.count(METRIC_TOKENS_OUTPUT, usage.output_tokens, dimensions)
