"""``omicsclaw/provider`` — the one contract the Main Loop programs against.

Plan 0026, step 2 of the staged framework rebuild. ADR 0077 gave the
system a vendor-neutral vocabulary; nothing could yet turn those types
into a request. This layer can::

    Engine ──▶ LLMProvider ──▶ vendor SDK
                 (here)         (OpenAI / Anthropic / DeepSeek / Ollama …)

A provider is a *simultaneous interpreter*: :mod:`omicsclaw.schema` types
go in, :mod:`omicsclaw.schema` types come out, and every vendor-shaped
field name lives and dies inside one adapter module. Adding a backend is
then a new file, not an edit to the loop.

**What is absent from the interface is the point.** ``generate`` takes the
conversation and the tools available for this turn, and nothing else — no
model, no temperature, no ``max_tokens``, no thinking budget. Those live
on the instance, in a :class:`~omicsclaw.provider.config.ProviderConfig`
fixed at construction, so the Engine cannot acquire model configuration:
there is nowhere to put it. Per-request variation goes through
:meth:`LLMProvider.bind`, which hands back a *different provider* rather
than widening the hot-path signature.

**Leaf-adjacent.** This package imports ``omicsclaw.schema`` and the
standard library, nothing else. No vendor SDK is imported here — that is
each adapter's private business, so importing the contract never requires
an optional extra to be installed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from omicsclaw.schema import Message, StreamChunk, ToolDefinition, Usage


class ProviderError(RuntimeError):
    """A model call failed, expressed in this layer's own vocabulary.

    Adapters catch whatever their vendor SDK raises and re-raise this, so
    no caller ever writes ``except openai.APIError`` and thereby acquires
    a hard dependency on one backend. The exception type is part of the
    interface just as much as the return type is.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str = "",
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        """Which backend failed. Carried separately from the message so a
        log or a retry policy can branch on it without parsing text."""

        self.status_code = status_code
        """HTTP status where the vendor reported one. ``None`` for
        failures that never reached the wire (bad config, malformed tool
        arguments), which is itself the distinction a retry policy needs."""

    def __str__(self) -> str:
        text = super().__str__()
        return f"[{self.provider}] {text}" if self.provider else text


class ProviderDeadlineExceeded(ProviderError):
    """The configured request budget is exhausted; do not retry it."""


@dataclass(frozen=True, slots=True)
class Completion:
    """The result of one non-streaming model call.

    The Python equivalent of the reference harness's
    ``(*Message, *Usage, error)`` multi-return: Go spells that as three
    values, Python spells it as one frozen record plus an exception. It
    also gives ``finish_reason`` a home, which the current code reads and
    then drops on the floor for want of a field to put it in.
    """

    message: Message
    """The assistant turn. ``message.is_action`` is the branch the loop
    turns on — tools requested means continue, no tools means stop."""

    usage: Usage = field(default_factory=Usage)
    """Token accounting for this call. Defaults to zeros rather than to
    ``None`` so accumulating over a run is a plain ``sum`` and never has
    to special-case a backend that reports nothing."""

    finish_reason: str = ""
    """Why the model stopped, as the vendor spelled it.

    Left as the raw token ("stop" / "end_turn" / "tool_calls" /
    "tool_use" / "length" / "max_tokens") because the only consumer that
    needs more than telemetry is the one case ``message.is_action``
    cannot express: a reply truncated by the output ceiling. Promoting it
    to a neutral enum is deferred until something branches on the rest.
    """


@runtime_checkable
class LLMProvider(Protocol):
    """What every model backend must look like from the Engine's side.

    A :class:`~typing.Protocol`, not a base class: an adapter satisfies it
    by shape, so a test double is a twenty-line class with no import of
    this module at all. ``runtime_checkable`` makes ``isinstance`` work
    for the conformance test.
    """

    @property
    def name(self) -> str:
        """Stable identifier for logs, telemetry, and error attribution."""
        ...

    async def generate(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None = None,
    ) -> Completion:
        """Run one blocking turn.

        ``tools=None`` (or empty) **strips every tool** rather than
        meaning "use the default set". That is load-bearing: it is how the
        reference harness implements a separated Thinking phase — pass no
        tools and the model must reason, pass tools and it may act — so a
        two-phase loop needs no new interface. An adapter that quietly
        substitutes a default tool list breaks that phase switch.

        Raises :class:`ProviderError` for any backend failure.
        """
        ...

    def generate_stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Run one streaming turn.

        Deliberately *not* ``async def``: it returns the iterator
        directly, so callers write ``async for chunk in p.generate_stream(…)``
        without an intervening ``await``. The final chunk is
        ``StreamChunkType.DONE`` carrying the assembled message and usage;
        consumers must drain to it so the underlying HTTP connection is
        released.

        ``tools`` follows :meth:`generate` exactly.
        """
        ...

    def bind(self, **overrides: Any) -> LLMProvider:
        """Return a cheap copy of this provider with a different configuration.

        For per-request variation — ``model_override``, ``max_tokens_override``,
        a pinned title-generation profile — without letting model
        configuration back into the hot-path signature. The receiver is
        **never** mutated: two turns holding two binds of the same
        provider must not be able to observe each other's settings.

        The intended implementation is one line over the config's own
        copy-on-write::

            return type(self)(self._config.with_overrides(**overrides))
        """
        ...


__all__ = ["Completion", "LLMProvider", "ProviderDeadlineExceeded", "ProviderError"]
