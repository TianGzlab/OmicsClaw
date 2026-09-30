"""A provider that replays a fixed script of model replies.

:class:`ScriptedProvider` satisfies :class:`~omicsclaw.provider.LLMProvider`
by shape. Each main-line call takes the next :class:`ScriptedTurn`; a call
made with ``tools=None`` (the summarizer and memory extraction) takes the
next side reply instead, so a compaction that does or does not run cannot
shift the main script. Every call is recorded with the messages and tools
it was sent.
"""

from __future__ import annotations

import dataclasses
import json
import threading
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from omicsclaw.provider import Completion, ProviderError
from omicsclaw.schema import (
    Message,
    Role,
    StreamChunk,
    StreamChunkType,
    ToolCall,
    ToolDefinition,
    Usage,
)

__all__ = [
    "DEFAULT_USAGE",
    "RecordedCall",
    "ScriptedProvider",
    "ScriptedTurn",
    "tool_call",
]

DEFAULT_USAGE = Usage(input_tokens=100, output_tokens=50)
"""The usage every main-line call reports unless its turn overrides it."""


@dataclass(frozen=True)
class ScriptedTurn:
    """One scripted model reply.

    :param text: The assistant text.
    :param tool_calls: Tool calls the reply requests. Build them with
        :func:`tool_call`.
    :param err: When set, the call raises this instead of replying.
    :param usage: Token usage for this call. ``None`` uses the provider's
        fixed usage.
    """

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    err: BaseException | None = None
    usage: Usage | None = None


@dataclass(frozen=True)
class RecordedCall:
    """What one call to the provider was sent.

    :param messages: The conversation, as sent.
    :param tools: The names of the tools offered, in order. Empty for a
        call made with ``tools=None``.
    :param full_tools: The tool definitions offered.
    :param bound: The overrides of the :meth:`ScriptedProvider.bind` view
        the call went through. Empty for the provider itself.
    """

    messages: tuple[Message, ...]
    tools: tuple[str, ...]
    full_tools: tuple[ToolDefinition, ...]
    bound: Mapping[str, Any] = field(default_factory=dict)


def tool_call(name: str, args: Mapping[str, Any] | str, id: str | None = None) -> ToolCall:
    """Build a :class:`~omicsclaw.schema.ToolCall` for a script.

    :param name: The tool name.
    :param args: The arguments, as a mapping (JSON-encoded here) or as a
        raw string passed through unchanged.
    :param id: The call id. ``None`` leaves it empty, and the
        :class:`ScriptedProvider` the call is scripted into numbers it
        ``call_<n>`` in script order, so a fresh provider always
        produces the same ids.
    :returns: The tool call.
    """
    arguments = args if isinstance(args, str) else json.dumps(dict(args))
    return ToolCall(id=id if id is not None else "", name=name, arguments=arguments)


def _numbered(turns: Sequence[ScriptedTurn]) -> tuple[ScriptedTurn, ...]:
    """*turns* with every empty tool-call id replaced by ``call_<n>``."""
    counter = 0
    out: list[ScriptedTurn] = []
    for turn in turns:
        calls: list[ToolCall] = []
        for call in turn.tool_calls:
            if not call.id:
                counter += 1
                call = dataclasses.replace(call, id=f"call_{counter}")
            calls.append(call)
        out.append(dataclasses.replace(turn, tool_calls=tuple(calls)))
    return tuple(out)


class _State:
    """The script, the cursors and the records, shared by every view."""

    def __init__(
        self,
        turns: Sequence[ScriptedTurn],
        side_replies: Sequence[str],
    ) -> None:
        self.lock = threading.Lock()
        self.turns = _numbered(turns)
        self.side_replies = tuple(side_replies)
        self.index = 0
        self.side_index = 0
        self.calls: list[RecordedCall] = []
        self.side_calls: list[RecordedCall] = []
        self.exhausted = 0


class ScriptedProvider:
    """An :class:`~omicsclaw.provider.LLMProvider` that replays a script.

    :param turns: The main-line replies, in order.
    :param name: The provider name, reported to telemetry as
        ``gen_ai.system``.
    :param usage: The usage every main-line call reports unless its turn
        sets one.
    :param on_exhausted: What a main-line call does once the script has
        run out. ``"converge"`` replies with *exhausted_text* and no tool
        calls, which lets the loop stop; ``"raise"`` raises
        ``ProviderError("script exhausted", status_code=400)``.
    :param exhausted_text: The reply used by ``"converge"``.
    :param side_replies: Replies for calls made with ``tools=None``, in
        order.
    :param side_default: The side reply once *side_replies* has run out.
    :raises ValueError: *on_exhausted* is neither ``"converge"`` nor
        ``"raise"``.
    """

    def __init__(
        self,
        *turns: ScriptedTurn,
        name: str = "scripted",
        usage: Usage = DEFAULT_USAGE,
        on_exhausted: str = "converge",
        exhausted_text: str = "done.",
        side_replies: Sequence[str] = (),
        side_default: str = "",
    ) -> None:
        if on_exhausted not in ("converge", "raise"):
            raise ValueError(
                f"on_exhausted must be 'converge' or 'raise', not {on_exhausted!r}"
            )
        self._name = name
        self._usage = usage
        self._on_exhausted = on_exhausted
        self._exhausted_text = exhausted_text
        self._side_default = side_default
        self._state = _State(turns, side_replies)
        self._bound: Mapping[str, Any] = {}

    # ---- LLMProvider -------------------------------------------------------

    @property
    def name(self) -> str:
        """The provider name."""
        return self._name

    async def generate(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None = None,
    ) -> Completion:
        """Record the call and return the next scripted reply.

        :raises BaseException: the turn's ``err``, when it has one.
        :raises ProviderError: the script is used up and
            ``on_exhausted="raise"``.
        """
        return self._next(messages, tools)

    def generate_stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Return an iterator that yields the next reply as one ``DONE`` chunk.

        The call is taken from the script when the iterator is first
        advanced, and a scripted error is raised from there.
        """
        return self._stream(messages, tools)

    def bind(self, **overrides: Any) -> ScriptedProvider:
        """Return a view that shares this provider's script and records.

        The overrides are stored on each :class:`RecordedCall` the view
        makes; they change nothing else.
        """
        view = object.__new__(ScriptedProvider)
        view._name = self._name
        view._usage = self._usage
        view._on_exhausted = self._on_exhausted
        view._exhausted_text = self._exhausted_text
        view._side_default = self._side_default
        view._state = self._state
        view._bound = {**self._bound, **overrides}
        return view

    # ---- inspection --------------------------------------------------------

    @property
    def calls(self) -> tuple[RecordedCall, ...]:
        """Every main-line call, oldest first."""
        with self._state.lock:
            return tuple(self._state.calls)

    @property
    def side_calls(self) -> tuple[RecordedCall, ...]:
        """Every call made with ``tools=None``, oldest first."""
        with self._state.lock:
            return tuple(self._state.side_calls)

    @property
    def exhausted(self) -> int:
        """How many main-line calls found the script already used up."""
        with self._state.lock:
            return self._state.exhausted

    @property
    def turn_index(self) -> int:
        """How many main-line calls have been made."""
        with self._state.lock:
            return self._state.index

    def reset(self) -> None:
        """Rewind both cursors and clear both records."""
        with self._state.lock:
            self._state.index = 0
            self._state.side_index = 0
            self._state.calls.clear()
            self._state.side_calls.clear()
            self._state.exhausted = 0

    # ---- internals ---------------------------------------------------------

    async def _stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None,
    ) -> AsyncIterator[StreamChunk]:
        completion = self._next(messages, tools)
        yield StreamChunk(
            type=StreamChunkType.DONE,
            message=completion.message,
            usage=completion.usage,
            finish_reason=completion.finish_reason,
        )

    def _next(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None,
    ) -> Completion:
        offered = tuple(tools) if tools is not None else ()
        record = RecordedCall(
            messages=tuple(messages),
            tools=tuple(tool.name for tool in offered),
            full_tools=offered,
            bound=dict(self._bound),
        )
        state = self._state
        with state.lock:
            if tools is None:
                state.side_calls.append(record)
                if state.side_index < len(state.side_replies):
                    text = state.side_replies[state.side_index]
                    state.side_index += 1
                else:
                    text = self._side_default
                return Completion(
                    message=Message(role=Role.ASSISTANT, content=text),
                    usage=self._usage,
                    finish_reason="end_turn",
                )
            state.calls.append(record)
            if state.index < len(state.turns):
                turn: ScriptedTurn | None = state.turns[state.index]
            else:
                turn = None
                state.exhausted += 1
            state.index += 1
        if turn is None:
            if self._on_exhausted == "raise":
                raise ProviderError(
                    "script exhausted", provider=self._name, status_code=400
                )
            turn = ScriptedTurn(text=self._exhausted_text)
        if turn.err is not None:
            raise turn.err
        return Completion(
            message=Message(
                role=Role.ASSISTANT,
                content=turn.text,
                tool_calls=turn.tool_calls,
            ),
            usage=turn.usage if turn.usage is not None else self._usage,
            finish_reason="tool_use" if turn.tool_calls else "end_turn",
        )
