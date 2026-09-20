"""``omicsclaw/schema`` — the standard types every component exchanges.

Per ADR 0077. This is the system's unified blood. The Main Loop, the
model adapter, the tool registry, and the memory layer all pass these
types to each other and nothing else.

It is defined before the Main Loop for the same reason the reference
harness defines it first: the loop body *is* the movement of these types,

    Message → ToolCall → ToolResult → Message

so there is no loop to write until they exist.

**Vendor-neutral by construction.** OpenAI, Anthropic, DeepSeek and
Ollama disagree about nearly everything — where a tool call's name lives,
whether a tool result is a role or a content block, what a cached token is
called. None of that appears here. Translating between a vendor payload
and these types is the model adapter layer's only job. A vendor field
name leaking into this package is a bug.

The two ReAct moves this package exists to carry:

=========  ==============================================================
Thought    ``Message.reasoning_content``
Action     ``Message.tool_calls`` → :class:`ToolCall` → :class:`ToolResult`
=========  ==============================================================

**Leaf package.** Standard library only: no ``omicsclaw`` imports, no
third-party dependency, no I/O, no logging. Every layer may depend on it;
it depends on none. That is what keeps the dependency graph acyclic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


class Role(StrEnum):
    """Author of a message in a multi-turn conversation.

    A :class:`~enum.StrEnum`, so ``Role.ASSISTANT == "assistant"`` holds
    and code comparing against bare strings keeps working.
    """

    SYSTEM = "system"
    """System prompt: the agent's identity, constraints, and boundaries."""

    USER = "user"
    """Human input, and loop-injected nudges written in the user's voice."""

    ASSISTANT = "assistant"
    """Model output: reasoning, tool-call requests, or both."""

    TOOL = "tool"
    """A tool result (Observation), correlated by ``tool_call_id``.

    The reference harness has only three roles and folds Observations
    into ``user`` with ``tool_call_id`` set. A fourth role is kept here
    because collapsing the two loses information the adapter would have
    to re-derive: with a distinct role, "is this turn a human or a
    machine speaking" is answered by the data rather than inferred from
    whether another field happens to be populated.
    """


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One Action: the model's request to run a registered tool."""

    id: str
    """Identifier correlating this call to its result. Supplied by the
    vendor where there is one, minted by the adapter where there is not."""

    name: str
    """The tool's identifier in the registry."""

    arguments: str = "{}"
    """Raw JSON argument payload, deliberately left unparsed.

    Deferred deserialization — what Go's ``json.RawMessage`` exists for —
    keeps the byte-exact payload the model produced, which prompt-prefix
    caching and replay evidence both depend on: a decode and re-encode
    can reorder keys and silently change the bytes. Parsing is the
    concrete tool's business, not the loop's.
    """

    def parsed_arguments(self) -> dict[str, Any]:
        """Decode :attr:`arguments`, returning ``{}`` for unusable payloads.

        Models emit truncated or empty argument strings often enough that
        raising here would turn a recoverable turn into a crashed run.
        The caller gets an empty dict and can hand the model a tool-level
        error it can correct from.
        """
        if not self.arguments:
            return {}
        try:
            decoded = json.loads(self.arguments)
        except (TypeError, ValueError):
            return {}
        return decoded if isinstance(decoded, dict) else {}


_EMPTY_METADATA: Mapping[str, Any] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class ToolResult:
    """One Observation: what came back from executing a :class:`ToolCall`."""

    tool_call_id: str
    """Mirrors the originating :attr:`ToolCall.id`."""

    name: str = ""
    """Tool that produced this result. Kept so telemetry survives the
    originating call being compacted out of history."""

    output: str = ""
    """Result text as the model will see it."""

    is_error: bool = False
    """The execution failed.

    The loop shows the model its errors rather than hiding them, so it
    can fix a bad argument and retry. Adapters with a native signal for
    this should use it instead of leaving the model to parse an error
    prefix out of the text.
    """

    metadata: Mapping[str, Any] = field(default_factory=lambda: _EMPTY_METADATA)
    """Execution facts no vendor has a field for — timings, timeouts,
    approval state. Never sent to a model; carried for the loop and for
    telemetry. Read-only by convention."""

    def to_message(self) -> Message:
        """Project into the Observation message appended to history."""
        return Message(
            role=Role.TOOL,
            content=self.output,
            tool_call_id=self.tool_call_id,
            name=self.name,
            is_error=self.is_error,
        )


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """What a model is told about one callable tool.

    The three fields every vendor needs, and none of the local execution
    policy — risk level, approval mode, concurrency safety — which the
    tool layer keeps and must never serialize into a prompt.
    """

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    """JSON Schema for the arguments. The one thing the vendors agree on,
    so it needs no neutral re-encoding."""


@dataclass(frozen=True, slots=True)
class Message:
    """One entry of conversation history — the unit the loop moves.

    Frozen: history is append-only between deliberate compactions, and a
    mutated message silently invalidates any prompt-prefix cache built
    over it. Use :meth:`replace` for the rare edit.
    """

    role: Role
    """Who authored this entry."""

    content: str = ""
    """The message body."""

    reasoning_content: str = ""
    """The Thought: model reasoning emitted alongside or instead of text.

    Persisted rather than treated as display-only. The reference harness
    streams thinking to its UI and then discards it, which is safe only
    for vendors that tolerate its absence — several thinking endpoints
    reject a conversation whose historical assistant turns have lost it.
    Carrying the Thought in the history is also what makes the Reasoning
    half of ReAct inspectable after the fact rather than merely watched
    as it scrolls past.
    """

    tool_calls: tuple[ToolCall, ...] = ()
    """The Action(s). Non-empty only on ``assistant`` messages; a tuple
    because one turn may request several tools in parallel."""

    tool_call_id: str = ""
    """Set only on ``role="tool"``, correlating the Observation to its request."""

    name: str = ""
    """Tool name on ``role="tool"`` messages; otherwise empty."""

    is_error: bool = False
    """This Observation reports a failed execution. Meaningful only when
    :attr:`tool_call_id` is set."""

    # ---- constructors ---------------------------------------------------

    @classmethod
    def system(cls, content: str) -> Message:
        return cls(role=Role.SYSTEM, content=content)

    @classmethod
    def user(cls, content: str) -> Message:
        return cls(role=Role.USER, content=content)

    @classmethod
    def assistant(
        cls,
        content: str = "",
        *,
        reasoning_content: str = "",
        tool_calls: tuple[ToolCall, ...] | list[ToolCall] = (),
    ) -> Message:
        return cls(
            role=Role.ASSISTANT,
            content=content,
            reasoning_content=reasoning_content,
            tool_calls=tuple(tool_calls),
        )

    @classmethod
    def tool(
        cls,
        *,
        tool_call_id: str,
        content: str = "",
        name: str = "",
        is_error: bool = False,
    ) -> Message:
        return cls(
            role=Role.TOOL,
            content=content,
            tool_call_id=tool_call_id,
            name=name,
            is_error=is_error,
        )

    # ---- derived state --------------------------------------------------

    @property
    def is_action(self) -> bool:
        """The model asked to act — the loop must execute and re-enter.

        The single branch the Main Loop turns on: an assistant message
        that requests tools continues the loop, one that does not ends it.
        """
        return bool(self.tool_calls)

    def replace(self, **changes: Any) -> Message:
        """Return a copy with ``changes`` applied (the frozen-dataclass edit)."""
        return Message(
            role=changes.get("role", self.role),
            content=changes.get("content", self.content),
            reasoning_content=changes.get("reasoning_content", self.reasoning_content),
            tool_calls=tuple(changes.get("tool_calls", self.tool_calls)),
            tool_call_id=changes.get("tool_call_id", self.tool_call_id),
            name=changes.get("name", self.name),
            is_error=changes.get("is_error", self.is_error),
        )


@dataclass(frozen=True, slots=True)
class Usage:
    """Token accounting for one model call, or a sum over several.

    Carries the cache split because prompt-prefix caching makes "input
    tokens" alone an unusable cost signal: a cached prefix and a fresh one
    differ by an order of magnitude in price at identical counts. Every
    vendor spells these differently; the adapter normalizes.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    """Input tokens served from a prefix cache (a hit)."""
    cache_write_tokens: int = 0
    """Input tokens written into the cache this call (billed as a miss)."""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def uncached_input_tokens(self) -> int:
        """Input tokens billed at full rate. Never negative."""
        return max(0, self.input_tokens - self.cache_read_tokens)

    def __add__(self, other: Usage) -> Usage:
        """Accumulate across the turns of one run."""
        if not isinstance(other, Usage):
            return NotImplemented
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
        )


__all__ = [
    "Message",
    "Role",
    "ToolCall",
    "ToolDefinition",
    "ToolResult",
    "Usage",
]
