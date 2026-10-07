"""``omicsclaw/provider`` — the Anthropic Messages adapter.

Plan 0026 §8, task C. This is where the "simultaneous interpreter" claim
is tested, because Anthropic disagrees with :mod:`omicsclaw.schema` about
almost every structural choice:

===============  ==============================  ==========================
Concern          schema                          Anthropic
===============  ==============================  ==========================
System prompt    a ``Role.SYSTEM`` message       a top-level ``system``
                                                 parameter, lifted out of
                                                 the message list
Tool call        ``Message.tool_calls``          a ``tool_use`` block
Tool result      a ``Role.TOOL`` message         a ``tool_result`` block
                                                 inside a **user** turn
Arguments        raw JSON text                   a decoded object
Reasoning        ``Message.reasoning_content``   a ``thinking`` block
Stop signal      —                               ``stop_reason``
===============  ==============================  ==========================

Every one of those translations lives in this file and nowhere else. The
conversions are module-level functions over plain data rather than
methods, so the whole outbound and inbound mapping is testable without a
client, a key, or a socket.

**The SDK is loaded lazily, through one seam.** ``anthropic`` is an
optional extra and is *not* installed in this repo's environment. Binding
it at import time would make the module unimportable here and would drag
a vendor package into every test that only wants to check a conversion.
:func:`_build_async_client` is therefore the single function that needs
it; everything else in this module runs on the standard library.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import AsyncIterator, Mapping, Sequence
from enum import StrEnum
from typing import Any

from omicsclaw.schema import (
    Message,
    Role,
    StreamChunk,
    ToolCall,
    ToolDefinition,
    Usage,
)

from ._accumulator import ToolCallAccumulators
from ._deadline import RequestDeadline
from ._model_limits import bare_model_name
from .base import Completion, ProviderError
from .config import ProviderConfig

_PROVIDER_NAME = "anthropic"

MIN_THINKING_BUDGET_TOKENS = 1024
"""Anthropic rejects a smaller extended-thinking budget outright."""


# --------------------------------------------------------------------------
# reading vendor payloads
# --------------------------------------------------------------------------


def _field(source: Any, name: str, default: Any = None) -> Any:
    """Read ``name`` off an SDK model *or* the plain dict it serializes to.

    Plan 0026 §6 asks that the inbound direction be tested against
    recorded vendor responses, which are dicts. Every decoder below reads
    through here so one implementation serves both the pydantic objects
    the SDK really returns and the recorded fixtures the tests replay.
    """
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def decode_usage(raw: Any) -> Usage:
    """Translate an Anthropic usage block into the schema's accounting.

    Trap 7. Anthropic's ``input_tokens`` counts only the tokens it had to
    read for real — a cache hit is reported *separately* and excluded
    from it. :attr:`omicsclaw.schema.Usage.input_tokens` means total
    input, so the cache read is added back; the vendor's own figure is
    then recoverable as :attr:`Usage.uncached_input_tokens`. Summing the
    raw field instead under-reports input by the whole cached prefix,
    which on an agent run is most of it.
    """
    if raw is None:
        return Usage()
    cache_read = int(_field(raw, "cache_read_input_tokens", 0) or 0)
    cache_write = int(_field(raw, "cache_creation_input_tokens", 0) or 0)
    return Usage(
        input_tokens=int(_field(raw, "input_tokens", 0) or 0) + cache_read,
        output_tokens=int(_field(raw, "output_tokens", 0) or 0),
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
    )


def _merge_usage(current: Usage, update: Usage) -> Usage:
    """Fold one streamed usage report into the running total.

    A stream reports usage twice and each report is partial:
    ``message_start`` carries the input side with ``output_tokens`` still
    0, and ``message_delta`` carries the final output count with the
    input side zeroed. Overwriting wholesale therefore loses whichever
    half arrived first, so a field is replaced only when the newer event
    actually has a number for it.
    """
    return Usage(
        input_tokens=update.input_tokens or current.input_tokens,
        output_tokens=update.output_tokens or current.output_tokens,
        cache_read_tokens=update.cache_read_tokens or current.cache_read_tokens,
        cache_write_tokens=update.cache_write_tokens or current.cache_write_tokens,
    )


def decode_content(blocks: Any) -> Message:
    """Fold Anthropic's content blocks back into one assistant message.

    ``thinking`` becomes ``reasoning_content``, ``text`` becomes
    ``content``, ``tool_use`` becomes ``tool_calls``. ``redacted_thinking``
    is dropped: its ``data`` is ciphertext the model can replay but no
    human or log can read, and putting it in ``reasoning_content`` would
    make a field documented as the Thought hold something unreadable.
    """
    text: list[str] = []
    thinking: list[str] = []
    calls: list[ToolCall] = []

    for block in blocks or ():
        kind = _field(block, "type", "")
        if kind == "text":
            text.append(str(_field(block, "text", "") or ""))
        elif kind == "thinking":
            thinking.append(str(_field(block, "thinking", "") or ""))
        elif kind == "tool_use":
            calls.append(
                ToolCall(
                    id=str(_field(block, "id", "") or ""),
                    name=str(_field(block, "name", "") or ""),
                    arguments=_encode_tool_input(_field(block, "input", {})),
                )
            )

    return Message.assistant(
        content="".join(text),
        reasoning_content="".join(thinking),
        tool_calls=tuple(calls),
    )


def _encode_tool_input(value: Any) -> str:
    """Re-encode a decoded ``tool_use.input`` as the schema's JSON text."""
    try:
        return json.dumps(value if value is not None else {})
    except (TypeError, ValueError) as exc:
        raise ProviderError(
            f"tool_use input is not JSON-serializable: {value!r}",
            provider=_PROVIDER_NAME,
        ) from exc


# --------------------------------------------------------------------------
# writing vendor payloads
# --------------------------------------------------------------------------


def decode_arguments(call: ToolCall) -> dict[str, Any]:
    """Decode a tool call's arguments for ``tool_use.input``.

    Trap 6. The schema keeps ``arguments`` as raw JSON *text* on purpose;
    Anthropic wants the object. Deliberately **not**
    :meth:`ToolCall.parsed_arguments`, which returns ``{}`` for an
    unusable payload: that is the right answer for the tool layer, where
    an empty dict becomes an error the model can correct from, and the
    wrong one here, where it would replay history as a call the model
    never made and quietly change what the conversation says happened.
    """
    raw = call.arguments or "{}"
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ProviderError(
            f"tool call {call.name!r} (id {call.id!r}) has unparseable "
            f"arguments: {raw!r}",
            provider=_PROVIDER_NAME,
        ) from exc
    if not isinstance(decoded, dict):
        raise ProviderError(
            f"tool call {call.name!r} (id {call.id!r}) arguments decoded to "
            f"{type(decoded).__name__}, but tool_use.input must be an object",
            provider=_PROVIDER_NAME,
        )
    return decoded


def _tool_result_block(message: Message) -> dict[str, Any]:
    """One Observation as a ``tool_result`` block.

    Trap 8. ``is_error`` is passed through as the structured flag rather
    than left for the model to infer from an error prefix in the text —
    the reference harness notes explicitly that the flag is what
    strengthens self-correction on the next turn.
    """
    return {
        "type": "tool_result",
        "tool_use_id": message.tool_call_id,
        "content": message.content,
        "is_error": bool(message.is_error),
    }


def _assistant_blocks(message: Message) -> list[dict[str, Any]]:
    """Text and tool calls of one assistant turn, as content blocks.

    ``reasoning_content`` is **not** replayed as a ``thinking`` block.
    Anthropic verifies a returned thinking block against the
    ``signature`` it issued with it, and the schema has nowhere to keep
    that signature — so emitting the block would turn every follow-up
    turn into a 400. Dropping it is lossy and is recorded as such; it is
    the only option this schema leaves.
    """
    blocks: list[dict[str, Any]] = []
    if message.content:
        blocks.append({"type": "text", "text": message.content})
    for call in message.tool_calls:
        blocks.append(
            {
                "type": "tool_use",
                "id": call.id,
                "name": call.name,
                "input": decode_arguments(call),
            }
        )
    return blocks


def encode_conversation(
    messages: Sequence[Message],
) -> tuple[str, list[dict[str, Any]]]:
    """Split history into Anthropic's ``(system, messages)`` pair.

    Two structural moves, both required rather than tidy:

    *System prompts are lifted out.* Anthropic has no system role in the
    message list. Several are joined, so a caller that layers a persona
    onto a base prompt keeps both.

    *Consecutive tool results are batched into one user turn.* Trap 5.
    Anthropic has no ``tool`` role either: an Observation is a
    ``tool_result`` block inside a user message, and a turn that
    requested three tools in parallel must answer with all three blocks
    in a **single** user turn. Emitting one user turn per result is
    rejected by the API, and — where it is not — it teaches the model to
    stop asking for parallel calls. Batching is correctness, not
    optimization.
    """
    system_parts: list[str] = []
    turns: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []

    def flush_tool_results() -> None:
        if pending:
            turns.append({"role": "user", "content": list(pending)})
            pending.clear()

    for message in messages:
        if message.role == Role.SYSTEM:
            if message.content:
                system_parts.append(message.content)
            continue
        if message.role == Role.TOOL:
            pending.append(_tool_result_block(message))
            continue

        flush_tool_results()
        if message.role == Role.USER:
            turns.append(
                {"role": "user", "content": [{"type": "text", "text": message.content}]}
            )
        else:
            blocks = _assistant_blocks(message)
            if blocks:
                turns.append({"role": "assistant", "content": blocks})

    flush_tool_results()
    return "\n\n".join(system_parts), turns


def encode_tools(
    tools: Sequence[ToolDefinition] | None,
) -> list[dict[str, Any]]:
    """Translate tool definitions, passing the JSON Schema through whole.

    The reference harness picks ``properties`` and ``required`` out of
    the schema because Go's typed parameter has fields for exactly those
    two. Python's SDK takes the schema as-is, so it is forwarded intact
    and ``$defs``, ``additionalProperties`` and nested constraints
    survive instead of being silently flattened away.

    An empty or missing ``tools`` yields ``[]``, and the caller then omits
    the parameter entirely — never a default tool set. That is the
    Thinking/Action phase switch described in
    :meth:`omicsclaw.provider.base.LLMProvider.generate`.
    """
    payload: list[dict[str, Any]] = []
    for tool in tools or ():
        input_schema = dict(tool.input_schema or {})
        input_schema.setdefault("type", "object")
        input_schema.setdefault("properties", {})
        payload.append(
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": input_schema,
            }
        )
    return payload


def clamp_thinking_budget(budget: int, max_tokens: int) -> int:
    """Fit a requested thinking budget into what the API will accept.

    ``ProviderConfig`` stores what was *asked for*; making it legal is
    this adapter's job, because the ceiling it has to fit under
    (``max_tokens``) is resolved here too. Anthropic requires a budget of
    at least :data:`MIN_THINKING_BUDGET_TOKENS` and strictly below
    ``max_tokens``, so:

    * ``budget <= 0`` disables extended thinking and returns 0;
    * anything below the floor is raised to it, as the reference harness
      does — a request that asks to think a little means to think;
    * anything at or above the ceiling is lowered to ``max_tokens - 1``,
      the largest budget the API accepts. The adapter makes the request
      legal and does not second-guess the ratio: how much of the output
      allowance should go to reasoning is the caller's call, not a
      number this layer can invent.

    When no legal budget exists at all — ``max_tokens`` at or below the
    floor — this raises rather than silently dropping the thinking
    parameter. The two settings contradict each other, and a silently
    non-thinking model is the failure that is hardest to notice.
    """
    if budget <= 0:
        return 0
    if max_tokens <= MIN_THINKING_BUDGET_TOKENS:
        raise ProviderError(
            f"thinking_budget_tokens={budget} cannot be satisfied: Anthropic "
            f"requires a budget of at least {MIN_THINKING_BUDGET_TOKENS} and "
            f"strictly below max_tokens, which is {max_tokens}",
            provider=_PROVIDER_NAME,
        )
    return max(MIN_THINKING_BUDGET_TOKENS, min(budget, max_tokens - 1))


class ThinkingSupport(StrEnum):
    """How a given Claude model wants extended thinking to be asked for.

    Not a preference — the wrong shape is an HTTP 400 on the newest models
    and, in the other direction, silence on the oldest. The generation a
    model belongs to is therefore part of the request, and this enum is
    what :func:`thinking_support_for_model` reads off the model name.
    """

    ADAPTIVE_ONLY = "adaptive_only"
    """``budget_tokens`` has been **removed** and returns 400. Depth is
    asked for as ``output_config.effort`` instead."""

    ADAPTIVE_PREFERRED = "adaptive_preferred"
    """``budget_tokens`` is deprecated but still functional; adaptive is
    the vendor's recommendation. See :func:`encode_thinking` for which one
    this adapter actually sends and why."""

    BUDGET_ONLY = "budget_only"
    """``{"type": "enabled", "budget_tokens": N}`` is the *only* way to get
    thinking at all — these models predate adaptive."""


_ADAPTIVE_ONLY_MARKERS: tuple[str, ...] = (
    "fable-5",
    "opus-5",
    "opus-4-8",
    "opus-4-7",
    "sonnet-5",
)
"""Model families that reject ``budget_tokens`` outright (Fable 5 and 5.1,
Opus 5, Opus 4.8, Opus 4.7, Sonnet 5).

Substrings, matched against the normalized name, so that a dated release
(``claude-opus-4-7-20260115``) and a point revision (``claude-fable-5-1``)
are covered by their family's entry instead of needing one line each — a
table of exact ids would classify every model the day it ships as
"unknown", and unknown here means the shape that 400s."""

_ADAPTIVE_PREFERRED_MARKERS: tuple[str, ...] = ("opus-4-6", "sonnet-4-6")
"""Opus 4.6 and Sonnet 4.6: the generation where both shapes work."""

_EFFORT_LADDER: tuple[tuple[int, str], ...] = (
    (4_096, "low"),
    (16_384, "medium"),
    (32_768, "high"),
    (65_536, "xhigh"),
)
"""Budget ceilings mapped to ``output_config.effort`` levels, exclusive.

**This ladder is this adapter's own convention, not a vendor-published
equivalence** — no such equivalence exists, because an adaptive model has
no budget knob to be equivalent to. What it preserves is the only thing a
caller's number reliably means: monotonicity. Asking for more tokens of
thinking asks for more thinking, on every model, and the request never
silently evaporates because the model happened to be a new one.
"""

_MAX_EFFORT = "max"


def _normalized_model(model: str) -> str:
    """Bare, lowercased, with ``.`` folded to ``-``.

    The same model arrives spelled both ways — ``claude-opus-4-7`` from
    Anthropic itself, ``anthropic/claude-opus-4.7`` from a gateway — and
    classifying the two differently would mean sending the 400-shape to
    exactly one of them, which is the hardest version of this bug to find.
    """
    return bare_model_name(model).replace(".", "-")


def thinking_support_for_model(model: str) -> ThinkingSupport:
    """Which thinking shape ``model`` accepts.

    Unknown names fall to :attr:`ThinkingSupport.BUDGET_ONLY`, matching
    what ``providers/models.get_default_features`` has always done. It is
    the conservative answer for the population it actually catches — local
    proxies and Anthropic-compatible third parties, which implement the
    long-standing shape — even though a brand-new Anthropic model would be
    misfiled by it. A new Anthropic model needs a line in
    :data:`_ADAPTIVE_ONLY_MARKERS`; there is no way to infer a release
    date from a model string.
    """
    name = _normalized_model(model)
    if any(marker in name for marker in _ADAPTIVE_ONLY_MARKERS):
        return ThinkingSupport.ADAPTIVE_ONLY
    if any(marker in name for marker in _ADAPTIVE_PREFERRED_MARKERS):
        return ThinkingSupport.ADAPTIVE_PREFERRED
    return ThinkingSupport.BUDGET_ONLY


def effort_for_budget(budget: int) -> str:
    """Translate a requested token budget into an ``effort`` level.

    See :data:`_EFFORT_LADDER` for what this translation is and is not.
    """
    for ceiling, effort in _EFFORT_LADDER:
        if budget < ceiling:
            return effort
    return _MAX_EFFORT


def encode_thinking(model: str, budget: int, max_tokens: int) -> dict[str, Any]:
    """The request fragment that asks ``model`` to think, or ``{}``.

    Three outcomes, one per :class:`ThinkingSupport`:

    ``ADAPTIVE_ONLY``
        ``{"type": "adaptive"}`` plus ``output_config.effort``. The
        budget is *not* clamped on this path: ``clamp_thinking_budget``
        enforces a relationship to ``max_tokens`` that no longer exists
        here, and would refuse a perfectly legal request.

    ``BUDGET_ONLY``
        the legacy ``{"type": "enabled", "budget_tokens": N}``, clamped.

    ``ADAPTIVE_PREFERRED``
        ``{"type": "adaptive"}`` as well. Both shapes work on this
        generation, so the choice is about which way the deprecation runs:
        ``budget_tokens`` is already removed on every later model, and
        pinning the *default* model to a shape on its way out would ship a
        latent 400. It is also what this repository already does — the
        pre-rebuild ``providers/models.get_default_features`` returns
        adaptive for any ``4-6`` or ``4-7`` match — so sending the legacy
        shape here would be a regression against live behaviour, not a
        conservative choice. A caller who needs the exact token number
        honoured on this generation can still ask for the legacy shape
        through ``ProviderConfig.extra``.

    **What ``thinking_budget_tokens`` means on an adaptive model**: it is
    a depth *request*, read through :func:`effort_for_budget`, not a token
    allowance — the parameter it used to name no longer exists. It is
    neither ignored nor passed through: a caller that asked to think a
    little still gets ``"low"``, one that asked for 100k still gets
    ``"max"``, and ``0`` still means no thinking at all. A caller who
    wants a specific effort level names it directly in
    ``ProviderConfig.extra`` as ``{"output_config": {"effort": ...}}``.
    """
    if budget <= 0:
        return {}
    if thinking_support_for_model(model) is not ThinkingSupport.BUDGET_ONLY:
        return {
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort_for_budget(budget)},
        }
    return {
        "thinking": {
            "type": "enabled",
            "budget_tokens": clamp_thinking_budget(budget, max_tokens),
        }
    }


# --------------------------------------------------------------------------
# the SDK seam
# --------------------------------------------------------------------------


def _load_sdk() -> Any:
    """Import ``anthropic`` on first use, or explain that it is missing.

    A plain ``import`` statement rather than ``importlib``, deliberately:
    both defer the cost equally, but only this form leaves the dependency
    visible to grep, to dependency and licence scanners, and to the
    layering test. Laziness comes from *where* the import sits — inside
    this factory, never at module scope — not from making it dynamic.
    """
    try:
        import anthropic

        return anthropic
    except ImportError as exc:
        raise ProviderError(
            "the anthropic SDK is not installed; run "
            "`pip install anthropic` to use this provider",
            provider=_PROVIDER_NAME,
        ) from exc


def _sdk_timeout(sdk: Any, config: ProviderConfig) -> Any:
    """Build the SDK's timeout object from the config's plain seconds.

    ``ProviderConfig`` carries seconds rather than a transport object
    because it may not import one. The class is taken *off the SDK
    module* rather than by importing the HTTP library directly, which is
    both a layering rule and a correctness one: ``anthropic`` re-exports
    whichever library that release is built on (``httpx`` in 0.x,
    ``httpx2`` in 1.x) and 1.x rejects an object built from the other.
    Reading it back from the SDK is version-correct by construction.

    A release that stops re-exporting it falls back to the total as a
    plain float, which the SDK also accepts — losing the separate connect
    deadline, but never the request one.
    """
    timeout_cls = getattr(sdk, "Timeout", None)
    if timeout_cls is None:
        return float(config.timeout_seconds)
    return timeout_cls(
        float(config.timeout_seconds),
        connect=float(config.connect_timeout_seconds),
    )


def _build_async_client(config: ProviderConfig) -> Any:
    """Construct the async Anthropic client for ``config``.

    The one function in this module that needs the vendor package, and
    therefore the seam tests replace. Async because the whole project is:
    a blocking client here would block the Surface's event loop for the
    length of a generation.

    An empty ``base_url`` or ``api_key`` means *omit the argument*, never
    pass ``None`` — the SDK's own default endpoint and its credential
    resolution (env var, then auth profile) are both worth keeping, and
    an explicit ``None`` overrides them with nothing.
    """
    sdk = _load_sdk()
    kwargs: dict[str, Any] = {
        "max_retries": int(config.max_retries),
        "timeout": _sdk_timeout(sdk, config),
    }
    if config.api_key:
        kwargs["api_key"] = config.api_key
    if config.base_url:
        kwargs["base_url"] = config.base_url
    return sdk.AsyncAnthropic(**kwargs)


async def _close_stream(stream: Any, timeout: float = 1.0) -> None:
    """Release the SDK stream, tolerating a client that has no ``close``.

    Failures are swallowed on purpose: this runs from a ``finally``, and
    an exception raised while closing would replace whatever caused the
    close — including a cancellation — with a much less informative one.
    """
    closer = getattr(stream, "close", None)
    if closer is None:
        return
    try:
        result = closer()
        if inspect.isawaitable(result):
            async with asyncio.timeout(min(timeout, 1.0)):
                await result
    except Exception:
        # Deliberately broad and deliberately silent; see the docstring.
        pass


class AnthropicProvider:
    """:class:`~omicsclaw.provider.base.LLMProvider` over Anthropic Messages.

    Also serves any Anthropic-compatible endpoint, since the shape of the
    request rather than the hostname is what this adapter knows; point
    :attr:`ProviderConfig.base_url` at it.

    The client is built on first use rather than in ``__init__`` so that
    a provider can be constructed, inspected and ``bind()``-ed — and its
    conversions exercised — in an environment where the optional
    ``anthropic`` package is not installed at all.
    """

    __slots__ = ("_config", "_cached_client")

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        self._cached_client: Any = None

    @property
    def name(self) -> str:
        return self._config.provider or _PROVIDER_NAME

    @property
    def config(self) -> ProviderConfig:
        """The frozen configuration this provider was built from."""
        return self._config

    def bind(self, **overrides: Any) -> AnthropicProvider:
        """Copy-on-write. The receiver is never mutated — see ``base.py``."""
        return type(self)(self._config.with_overrides(**overrides))

    # ---- request assembly ------------------------------------------------

    def _request_params(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None,
    ) -> dict[str, Any]:
        config = self._config
        system, encoded = encode_conversation(messages)

        params: dict[str, Any] = {
            "model": config.model,
            # Anthropic requires max_tokens on every request, unlike the
            # OpenAI-compatible endpoints, so the model's known ceiling
            # stands in whenever the caller named no number.
            "max_tokens": config.max_output_tokens,
            "messages": encoded,
        }
        if system:
            params["system"] = system

        encoded_tools = encode_tools(tools)
        if encoded_tools:
            params["tools"] = encoded_tools

        thinking = encode_thinking(
            config.model, config.thinking_budget_tokens, config.max_output_tokens
        )
        # Extended thinking and a sampling temperature are mutually
        # exclusive — the API rejects any temperature but 1 while thinking
        # is enabled — so the request carries one or the other, never both.
        # Models that accept only adaptive thinking reject ``temperature``
        # outright, so they get neither.
        if thinking:
            params.update(thinking)
        elif thinking_support_for_model(config.model) is not ThinkingSupport.ADAPTIVE_ONLY:
            params["temperature"] = config.temperature

        # Last, and therefore winning, exactly as the OpenAI adapter
        # applies it: ``extra`` is the escape hatch for knobs this layer
        # has no neutral word for (``top_p``, ``stop_sequences``,
        # ``metadata``, a beta feature shipped after this file was
        # written), and an escape hatch that could not override a computed
        # default would be no escape at all.
        params.update(config.extra)
        if config.extra.get("thinking") and "temperature" not in config.extra:
            # Turning thinking on through ``extra`` would otherwise leave
            # the temperature this adapter had already set, and the pair is
            # a 400. Only the value *this* method chose is withdrawn: a
            # caller who put both keys in ``extra`` is taken at their word.
            params.pop("temperature", None)

        return params

    def _client(self) -> Any:
        if self._cached_client is None:
            self._cached_client = _build_async_client(self._config)
        return self._cached_client

    def _wrap(self, exc: Exception) -> ProviderError:
        """Re-express a vendor failure in this layer's vocabulary.

        So no caller ever writes ``except anthropic.APIError`` and
        thereby acquires a hard dependency on one backend.
        """
        if isinstance(exc, ProviderError):
            return exc
        status = getattr(exc, "status_code", None)
        return ProviderError(
            f"Anthropic Messages request failed: {exc}",
            provider=self.name,
            status_code=status if isinstance(status, int) else None,
        )

    # ---- the interface ---------------------------------------------------

    async def generate(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None = None,
    ) -> Completion:
        """Run one blocking turn. See ``base.LLMProvider.generate``."""
        params = self._request_params(messages, tools)
        try:
            async with RequestDeadline(self._config.timeout_seconds, self.name).wait():
                response = await self._client().messages.create(**params)
        except Exception as exc:
            raise self._wrap(exc) from exc

        return Completion(
            message=decode_content(_field(response, "content", ())),
            usage=decode_usage(_field(response, "usage")),
            finish_reason=str(_field(response, "stop_reason", "") or ""),
        )

    def generate_stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Run one streaming turn. See ``base.LLMProvider.generate_stream``.

        Not ``async def``: the iterator is returned directly. Conversion
        happens here, before the generator is created, so a malformed
        tool call in the history raises at the call site rather than on
        the first ``__anext__`` — the payload was never going to reach
        the wire, and the traceback is far more useful pointing at the
        caller than at a half-started stream.
        """
        return self._stream(self._request_params(messages, tools))

    async def _stream(self, params: dict[str, Any]) -> AsyncIterator[StreamChunk]:
        deadline = RequestDeadline(self._config.timeout_seconds, self.name)
        try:
            async with deadline.wait():
                stream = await self._client().messages.create(**params, stream=True)
        except Exception as exc:
            raise self._wrap(exc) from exc

        text: list[str] = []
        reasoning: list[str] = []
        accumulators = ToolCallAccumulators()
        usage = Usage()
        finish_reason = ""

        try:
            async for event in deadline.iterate(stream):
                kind = _field(event, "type", "")

                if kind == "content_block_delta":
                    delta = _field(event, "delta")
                    delta_kind = _field(delta, "type", "")
                    if delta_kind == "text_delta":
                        piece = str(_field(delta, "text", "") or "")
                        text.append(piece)
                        yield StreamChunk.text(piece)
                    elif delta_kind == "thinking_delta":
                        piece = str(_field(delta, "thinking", "") or "")
                        reasoning.append(piece)
                        yield StreamChunk.reasoning(piece)
                    elif delta_kind == "input_json_delta":
                        accumulators.append_arguments(
                            int(_field(event, "index", 0) or 0),
                            str(_field(delta, "partial_json", "") or ""),
                        )

                elif kind == "content_block_start":
                    block = _field(event, "content_block")
                    if _field(block, "type", "") == "tool_use":
                        accumulators.start(
                            int(_field(event, "index", 0) or 0),
                            str(_field(block, "id", "") or ""),
                            str(_field(block, "name", "") or ""),
                        )

                elif kind == "message_start":
                    raw = _field(_field(event, "message"), "usage")
                    usage = _merge_usage(usage, decode_usage(raw))

                elif kind == "message_delta":
                    usage = _merge_usage(
                        usage, decode_usage(_field(event, "usage"))
                    )
                    # ``message_delta`` is the only event carrying the
                    # stop signal, and it sits on the event's ``delta``
                    # (a message-level delta), not on a content block.
                    # "max_tokens" here is the truncation the Main Loop
                    # must not mistake for the model having finished.
                    stop = _field(_field(event, "delta"), "stop_reason", "")
                    if stop:
                        finish_reason = str(stop)

            message = Message.assistant(
                content="".join(text),
                reasoning_content="".join(reasoning),
                # Never range(len(...)): with thinking or leading text the
                # tool_use blocks start at index 1. See ToolCallAccumulators.
                tool_calls=accumulators.finalize(),
            )
            yield StreamChunk.done(message, usage, finish_reason)
        except Exception as exc:
            # ``Exception``, not ``BaseException``: cancellation arrives as
            # ``CancelledError`` / ``GeneratorExit``, and a cancelled turn
            # is not a provider failure — dressing it up as one would hide
            # the cancellation from the caller that asked for it.
            raise self._wrap(exc) from exc
        finally:
            # Trap 9. A consumer that stops early — a cancelled turn, a
            # `break`, a timeout — must not leave the HTTP connection
            # held open for the lifetime of the process.
            await _close_stream(stream, self._config.timeout_seconds)


__all__ = [
    "MIN_THINKING_BUDGET_TOKENS",
    "AnthropicProvider",
    "ThinkingSupport",
    "clamp_thinking_budget",
    "decode_arguments",
    "decode_content",
    "decode_usage",
    "effort_for_budget",
    "encode_conversation",
    "encode_thinking",
    "encode_tools",
    "thinking_support_for_model",
]
