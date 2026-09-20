"""``omicsclaw/provider`` — the adapter for everything that speaks OpenAI.

Plan 0026 §8, task B. One file covers OpenAI itself, DeepSeek, Ollama and
every gateway that resells other vendors behind the Chat Completions
dialect (OpenRouter, SiliconFlow, DashScope, Volcengine, Moonshot, Zhipu,
NVIDIA). They disagree about field names and about what has to be
injected into the request body; they do not disagree about the shape. One
adapter plus a few named gates therefore serves twelve of the thirteen
presets in :mod:`omicsclaw.provider.config`.

Everything vendor-shaped stops here. The conversion is written as
module-level pure functions over plain dicts rather than as private
methods, because that is what makes both halves of the interpreter —
:func:`encode_messages` and :func:`decode_message` — assertable against
literal payloads with no client, no socket, and no SDK.

**The SDK is imported lazily**, inside :meth:`OpenAIProvider._create_client`.
``openai`` is an optional extra in this repo, and the conversion half of
this module has to stay importable and testable on an installation that
lacks it. A missing SDK then surfaces as a :class:`ProviderError` at call
time, which is the same failure mode this layer already promises for
every other backend problem, instead of as an ``ImportError`` raised
somewhere far from the call that caused it.
"""

from __future__ import annotations

import inspect
import json
import os
from collections.abc import AsyncIterator, Mapping, Sequence
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
from .base import Completion, ProviderError
from .config import ProviderConfig

_REASONING_FIELDS: tuple[str, ...] = ("reasoning_content", "reasoning")
"""Trap 2. DeepSeek-R1 spells the Thought ``reasoning_content``;
OpenRouter proxying a GPT model spells it ``reasoning``. Neither is in
OpenAI's published schema, so both have to be looked for by name and the
first non-empty one wins."""

_INCLUDE_REASONING_GATEWAYS: tuple[str, ...] = ("openrouter", "requesty")
"""Trap 3. These two return no reasoning at all unless the request body
carries ``include_reasoning=true``. Matched on the base URL, exactly as
the reference harness does, because the gateway is the thing that needs
the flag and the model name does not identify it."""

_EPHEMERAL = {"type": "ephemeral"}


# --- defensive field access ------------------------------------------------


def _field(source: Any, name: str, default: Any = None) -> Any:
    """Read ``name`` off a mapping *or* an SDK object.

    Not a plain ``getattr``, and that is trap 2's doing: the reasoning
    fields are outside OpenAI's schema, so a typed SDK model may park
    them in its extras rather than promote them to attributes — while
    other OpenAI-compatible servers are consumed as raw dicts to begin
    with. Mapping, attribute, pydantic extras, ``__dict__``: the first
    that holds a non-``None`` value wins.
    """
    if source is None:
        return default
    if isinstance(source, Mapping):
        value = source.get(name)
    else:
        value = getattr(source, name, None)
        if value is None:
            extra = getattr(source, "model_extra", None)
            if isinstance(extra, Mapping):
                value = extra.get(name)
        if value is None:
            holder = getattr(source, "__dict__", None)
            if isinstance(holder, Mapping):
                value = holder.get(name)
    return default if value is None else value


def _int(value: Any) -> int:
    """Token counts arrive as ``None``, ``"12"`` and ``12.0``; all mean a count."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


# --- schema → OpenAI -------------------------------------------------------


def encode_tool_call(call: ToolCall) -> dict[str, Any]:
    """Render one Action into the wire shape.

    ``arguments`` is passed through as the raw JSON *string* the model
    produced and is never decoded and re-encoded. A round trip through
    ``json`` can reorder keys and respace separators, which changes the
    bytes of the conversation prefix and costs a prompt-cache hit on
    every subsequent turn.
    """
    return {
        "id": call.id,
        "type": "function",
        "function": {"name": call.name, "arguments": call.arguments},
    }


def encode_message(message: Message) -> dict[str, Any]:
    """Render one history entry.

    Optional keys are *omitted* rather than emitted empty. A spurious
    ``"tool_calls": []`` on an ordinary assistant turn is not harmless: it
    changes the prefix bytes and so silently disables prompt caching for
    the whole conversation.

    The one key that is emitted whenever it has a value is
    ``reasoning_content``. DeepSeek's thinking endpoints reject a
    multi-turn request whose historical assistant messages have lost the
    Thought ("The reasoning_content in the thinking mode must be passed
    back"); today ``providers/patches.py`` papers over that by injecting
    ``""`` because the old message shape could not carry the real value.
    :class:`~omicsclaw.schema.Message` carries it, so the real value goes
    back and the patch has nothing left to do.
    """
    role = str(message.role)
    if role == Role.TOOL:
        payload: dict[str, Any] = {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": message.content,
        }
        if message.name:
            payload["name"] = message.name
        # ``is_error`` has no home in this dialect — unlike Anthropic's
        # tool_result, an OpenAI tool message is text only.
        return payload

    if role != Role.ASSISTANT:
        return {"role": role, "content": message.content}

    payload = {"role": "assistant"}
    if message.content or not message.tool_calls:
        # Content is omitted only when tool calls carry the turn, so an
        # otherwise empty assistant message still has a content key.
        payload["content"] = message.content
    if message.reasoning_content:
        payload["reasoning_content"] = message.reasoning_content
    if message.tool_calls:
        payload["tool_calls"] = [encode_tool_call(c) for c in message.tool_calls]
    return payload


def encode_messages(messages: Sequence[Message]) -> list[dict[str, Any]]:
    return [encode_message(message) for message in messages]


def encode_tool(tool: ToolDefinition) -> dict[str, Any]:
    function: dict[str, Any] = {"name": tool.name}
    if tool.description:
        function["description"] = tool.description
    function["parameters"] = dict(tool.input_schema) or {
        "type": "object",
        "properties": {},
    }
    return {"type": "function", "function": function}


def encode_tools(
    tools: Sequence[ToolDefinition] | None,
) -> list[dict[str, Any]] | None:
    """``None`` for no tools, which is the Thinking/Action phase switch.

    Returning a default tool set here would re-arm a phase that was meant
    to reason only, so an empty sequence and ``None`` mean the same thing
    and both strip the ``tools`` key from the request entirely.
    """
    if not tools:
        return None
    return [encode_tool(tool) for tool in tools]


# --- Anthropic-style prompt-cache breakpoints (ADR 0024) -------------------


def is_anthropic_family(provider: str, model: str) -> bool:
    """True for Claude reached natively or through an OpenAI-shaped gateway."""
    key = str(provider or "").strip().lower()
    name = str(model or "").strip().lower()
    return key == "anthropic" or "claude" in name or name.startswith("anthropic/")


def _is_localhost(base_url: str) -> bool:
    lowered = str(base_url or "").lower()
    return "127.0.0.1" in lowered or "localhost" in lowered


def _mark_last_system_message(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    index = next(
        (
            i
            for i in reversed(range(len(messages)))
            if messages[i].get("role") == "system"
        ),
        None,
    )
    if index is None:
        return messages
    out = list(messages)
    message = dict(out[index])
    content = message.get("content")
    if isinstance(content, str):
        message["content"] = [
            {"type": "text", "text": content, "cache_control": dict(_EPHEMERAL)}
        ]
    elif isinstance(content, list) and content and isinstance(content[-1], Mapping):
        blocks = list(content)
        blocks[-1] = {**blocks[-1], "cache_control": dict(_EPHEMERAL)}
        message["content"] = blocks
    else:
        return messages
    out[index] = message
    return out


def _mark_last_tool(
    tools: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    if not tools:
        return tools
    out = list(tools)
    out[-1] = {**out[-1], "cache_control": dict(_EPHEMERAL)}
    return out


def apply_cache_breakpoints(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    *,
    provider: str,
    model: str,
    base_url: str,
    enabled: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    """Mark the system prompt and the last tool with ``cache_control``.

    Ported from ``providers/models.apply_prompt_cache_breakpoints``. This
    is vendor-shaped output, so it belongs in an adapter rather than in a
    shared helper. OmicsClaw engineers a byte-stable system+tools prefix
    (ADR 0024) for the backends that cache automatically (OpenAI,
    DeepSeek); Anthropic caches nothing without an explicit breakpoint, so
    Claude reached through an OpenAI-compatible gateway got roughly zero
    cache hits off that same stable prefix until these two marks were
    added.

    Identity — the inputs are returned unchanged — for every other
    backend, for ccproxy/localhost endpoints that reject the block shape,
    and when ``enabled`` is false. Deterministic every turn, so the
    breakpoint itself never churns the prefix it exists to cache.
    """
    if not enabled or not is_anthropic_family(provider, model):
        return messages, tools
    if _is_localhost(base_url):
        return messages, tools
    return _mark_last_system_message(messages), _mark_last_tool(tools)


def breakpoints_enabled(env: Mapping[str, str] | None = None) -> bool:
    """``OMICSCLAW_PROMPT_CACHE_BREAKPOINTS=0`` turns the breakpoints off.

    The same lever the query engine reads today, kept spelled identically
    so an operator whose gateway rejects the block shape does not have to
    learn a new variable when this adapter takes over.
    """
    source = os.environ if env is None else env
    return (source.get("OMICSCLAW_PROMPT_CACHE_BREAKPOINTS") or "").strip() != "0"


def wants_include_reasoning(base_url: str) -> bool:
    """Trap 3. Harmless everywhere else; the parameter is simply ignored."""
    lowered = str(base_url or "").lower()
    return any(gateway in lowered for gateway in _INCLUDE_REASONING_GATEWAYS)


# --- OpenAI → schema -------------------------------------------------------


def decode_arguments(value: Any) -> str:
    """Normalize a tool call's arguments to JSON *text*.

    A string is kept byte-for-byte. Some OpenAI-compatible servers hand
    back an already-decoded object instead, and the schema's contract is
    that ``arguments`` is always parseable JSON text, so those are
    re-encoded — compactly, and without ASCII-escaping, so a Chinese
    skill parameter survives the trip legibly.
    """
    if isinstance(value, str):
        return value or "{}"
    if value is None:
        return "{}"
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return "{}"


def decode_tool_call(payload: Any) -> ToolCall | None:
    """One wire tool call, or ``None`` if it is not a function call.

    An explicitly non-function type (a built-in web search, say) is not
    something the local registry can run, so it is dropped. A *missing*
    type is accepted: several compatible servers omit the field, and
    refusing those would silently lose real calls.
    """
    kind = _text(_field(payload, "type", ""))
    if kind and kind != "function":
        return None
    function = _field(payload, "function")
    return ToolCall(
        id=_text(_field(payload, "id", "")),
        name=_text(_field(function, "name", "")),
        arguments=decode_arguments(_field(function, "arguments")),
    )


def decode_reasoning(delta: Any) -> str:
    """Trap 2. First non-empty of the known spellings of the Thought."""
    for name in _REASONING_FIELDS:
        value = _text(_field(delta, name, ""))
        if value:
            return value
    return ""


def decode_message(payload: Any) -> Message:
    """A response message back into the schema.

    ``content: null`` is how this dialect says "no text" on a pure tool
    call, and it becomes ``""`` rather than propagating a ``None`` into a
    field the schema types as ``str``.
    """
    calls = tuple(
        call
        for call in (
            decode_tool_call(raw) for raw in _field(payload, "tool_calls") or ()
        )
        if call is not None
    )
    return Message.assistant(
        _text(_field(payload, "content", "")),
        reasoning_content=decode_reasoning(payload),
        tool_calls=calls,
    )


def decode_usage(payload: Any) -> Usage:
    """Token accounting, across the dialects that report it differently.

    ``prompt_tokens`` already *includes* cached tokens here, so unlike
    Anthropic's ``input_tokens`` it needs no repair — the cache figure is
    a breakdown of the input, not an addition to it.

    ``cache_write_tokens`` stays zero: no OpenAI-compatible dialect
    reports cache creation. DeepSeek's ``prompt_cache_miss_tokens`` is
    "not a hit", which is not the same claim, and
    :attr:`Usage.uncached_input_tokens` already derives it.
    """
    if payload is None:
        return Usage()
    cached = _int(_field(_field(payload, "prompt_tokens_details"), "cached_tokens", 0))
    if not cached:
        cached = _int(_field(payload, "prompt_cache_hit_tokens", 0))
    return Usage(
        input_tokens=_int(_field(payload, "prompt_tokens", 0)),
        output_tokens=_int(_field(payload, "completion_tokens", 0)),
        cache_read_tokens=cached,
    )


def _accumulate_tool_call(calls: ToolCallAccumulators, fragment: Any) -> None:
    index = _int(_field(fragment, "index", 0))
    function = _field(fragment, "function")
    calls.start(
        index,
        _text(_field(fragment, "id", "")),
        _text(_field(function, "name", "")),
    )
    calls.append_arguments(index, _text(_field(function, "arguments", "")))


async def _close_stream(stream: Any) -> None:
    """Trap 9. Release the HTTP connection whatever ended the turn.

    A failure to close is swallowed: the stream is already gone, and
    turning that into an exception would replace a completed answer with
    an error. ``CancelledError`` is a ``BaseException`` and so passes
    through untouched, which is what makes this safe to run from a
    ``finally`` reached by cancellation.
    """
    close = getattr(stream, "close", None)
    if close is None:
        return
    try:
        result = close()
        if inspect.isawaitable(result):
            await result
    except Exception:
        pass


class OpenAIProvider:
    """An :class:`~omicsclaw.provider.base.LLMProvider` over Chat Completions.

    Satisfies the Protocol structurally; it deliberately does not inherit
    from it. Configuration is fixed at construction, so the Engine has
    nowhere to put a model name, and per-request variation goes through
    :meth:`bind`.
    """

    __slots__ = ("_client", "_config")

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        # Built on first use and cached. An instance attribute rather than
        # a local so a test can substitute a fake client and exercise the
        # whole request path with no SDK installed and no socket opened.
        self._client: Any | None = None

    @property
    def name(self) -> str:
        return self._config.provider or "openai"

    def bind(self, **overrides: Any) -> OpenAIProvider:
        """A new provider with a different configuration; never a mutation."""
        return type(self)(self._config.with_overrides(**overrides))

    # ---- SDK plumbing ----------------------------------------------------

    def _create_client(self) -> Any:
        try:
            import openai
        except ImportError as exc:
            raise ProviderError(
                "the 'openai' package is required for OpenAI-compatible "
                "backends but is not installed",
                provider=self.name,
            ) from exc

        kwargs: dict[str, Any] = {
            # Ollama and other local endpoints authenticate nothing, but
            # the SDK refuses to construct without a key, so a placeholder
            # stands in for the empty one.
            "api_key": self._config.api_key or "not-needed",
            "max_retries": self._config.max_retries,
            # ProviderConfig carries plain seconds because it may not
            # import a transport library; the SDK's timeout object is
            # assembled here, where httpx is already a dependency.
            "timeout": openai.Timeout(
                self._config.timeout_seconds,
                connect=self._config.connect_timeout_seconds,
            ),
        }
        if self._config.base_url:
            # An empty base URL means "the SDK's own default". Passing
            # None instead would override that default with nothing.
            kwargs["base_url"] = self._config.base_url
        return openai.AsyncOpenAI(**kwargs)

    def _client_or_create(self) -> Any:
        if self._client is None:
            self._client = self._create_client()
        return self._client

    def _wrap(self, exc: Exception, what: str) -> ProviderError:
        """Every SDK failure becomes this layer's own exception type.

        The HTTP status is lifted out where the SDK reported one, because
        that is how a retry policy tells a 429 from a malformed request
        without importing ``openai`` to inspect the class.
        """
        status = getattr(exc, "status_code", None)
        return ProviderError(
            f"{what}: {type(exc).__name__}: {exc}",
            provider=self.name,
            status_code=status if isinstance(status, int) else None,
        )

    def _request_payload(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None,
        *,
        stream: bool,
    ) -> dict[str, Any]:
        config = self._config
        encoded, encoded_tools = apply_cache_breakpoints(
            encode_messages(messages),
            encode_tools(tools),
            provider=config.provider,
            model=config.model,
            base_url=config.base_url,
            enabled=breakpoints_enabled(),
        )
        payload: dict[str, Any] = {
            "model": config.model,
            "messages": encoded,
            "temperature": config.temperature,
        }
        if config.max_tokens > 0:
            # Omitted when unset: this dialect treats the parameter as
            # optional and defaults to the model's own ceiling, which is
            # larger than the conservative figure a table miss would
            # supply. Naming a number here can only truncate.
            payload["max_tokens"] = config.max_output_tokens
        if encoded_tools:
            payload["tools"] = encoded_tools
        if stream:
            # Trap 4. Without this the usage block never arrives at all.
            payload["stream_options"] = {"include_usage": True}
        if wants_include_reasoning(config.base_url):
            payload["include_reasoning"] = True
        # Last, so an operator can override any of the above — including
        # turning include_reasoning back off for a gateway that rejects it.
        payload.update(config.extra)
        return payload

    # ---- the interface ---------------------------------------------------

    async def generate(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None = None,
    ) -> Completion:
        payload = self._request_payload(messages, tools, stream=False)
        client = self._client_or_create()
        try:
            response = await client.chat.completions.create(**payload)
        except Exception as exc:
            raise self._wrap(exc, "chat completion failed") from exc

        choices = _field(response, "choices") or ()
        if not choices:
            raise ProviderError(
                "the backend returned a completion with no choices",
                provider=self.name,
            )
        return Completion(
            message=decode_message(_field(choices[0], "message")),
            usage=decode_usage(_field(response, "usage")),
            finish_reason=_text(_field(choices[0], "finish_reason", "")),
        )

    def generate_stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Not ``async def``: the iterator is returned, not awaited."""
        return self._stream(messages, tools)

    async def _stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None,
    ) -> AsyncIterator[StreamChunk]:
        payload = self._request_payload(messages, tools, stream=True)
        client = self._client_or_create()
        try:
            stream = await client.chat.completions.create(stream=True, **payload)
        except Exception as exc:
            raise self._wrap(exc, "streaming chat completion failed") from exc

        text: list[str] = []
        reasoning: list[str] = []
        calls = ToolCallAccumulators()
        usage = Usage()
        finish_reason = ""
        try:
            async for raw in stream:
                # Trap 4, the other half: the usage-bearing chunk has an
                # EMPTY choices array. Reading usage after the skip below
                # loses all token accounting for every streamed turn.
                chunk_usage = decode_usage(_field(raw, "usage"))
                if chunk_usage != Usage():
                    usage = chunk_usage

                choices = _field(raw, "choices") or ()
                if not choices:
                    continue

                # The stop signal rides the LAST content-bearing chunk,
                # whose ``delta`` is typically empty — so it must be read
                # before the delta handling below, not folded into it.
                # Keep the last non-empty value: the field is null on
                # every chunk until the model actually stops.
                reason = _text(_field(choices[0], "finish_reason", ""))
                if reason:
                    finish_reason = reason

                delta = _field(choices[0], "delta")

                thought = decode_reasoning(delta)
                if thought:
                    reasoning.append(thought)
                    yield StreamChunk.reasoning(thought)

                content = _text(_field(delta, "content", ""))
                if content:
                    text.append(content)
                    yield StreamChunk.text(content)

                for fragment in _field(delta, "tool_calls") or ():
                    _accumulate_tool_call(calls, fragment)
        except Exception as exc:
            raise self._wrap(exc, "streaming chat completion failed") from exc
        finally:
            # Trap 9. Reached by a normal end, by an error, and by the
            # GeneratorExit that a cancelled turn throws in at the yield
            # above — the case that otherwise leaks the connection.
            await _close_stream(stream)

        yield StreamChunk.done(
            Message.assistant(
                "".join(text),
                reasoning_content="".join(reasoning),
                tool_calls=calls.finalize(),
            ),
            usage,
            finish_reason,
        )


__all__ = [
    "OpenAIProvider",
    "apply_cache_breakpoints",
    "breakpoints_enabled",
    "decode_message",
    "decode_reasoning",
    "decode_usage",
    "encode_message",
    "encode_messages",
    "encode_tools",
    "is_anthropic_family",
    "wants_include_reasoning",
]
