"""Plan 0027 §12.4.4: ``exchange`` is a lifecycle shell, not a second loop.

Two things are checked here and they pull in opposite directions. The
behavioural tests say the shells really do drive a run — collaborators
overridden per call, events forwarded, the degenerate case identical to
``run``. The structural test says they do nothing *else*: plan 0027 §6
spent a section arguing that one kernel with two mouths is what stops a
blocking path and a streaming path from disagreeing about when a run is
finished, and a shell that started counting turns or scheduling tools
would be the third opinion that argument exists to prevent.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import pathlib
from typing import Any, AsyncIterator, Sequence

import pytest

from omicsclaw.engine import AgentEngine, EngineConfig, EngineEventType
from omicsclaw.engine import loop as loop_module
from omicsclaw.provider import Completion
from omicsclaw.schema import (
    Message,
    Role,
    StreamChunk,
    StreamChunkType,
    ToolCall,
    ToolDefinition,
    ToolResult,
)


class Provider:
    def __init__(self, *replies: Message) -> None:
        self.replies = list(replies)
        self.seen: list[tuple[Message, ...]] = []

    @property
    def name(self) -> str:
        return "scripted"

    async def generate(self, messages, tools=None) -> Completion:
        self.seen.append(tuple(messages))
        reply = self.replies[min(len(self.seen) - 1, len(self.replies) - 1)]
        return Completion(message=reply, finish_reason="stop")

    async def _stream(self, messages, tools) -> AsyncIterator[StreamChunk]:
        completion = await self.generate(messages, tools)
        yield StreamChunk(type=StreamChunkType.TEXT_DELTA, delta="hi")
        yield StreamChunk(type=StreamChunkType.DONE, message=completion.message)

    def generate_stream(self, messages, tools=None):
        return self._stream(messages, tools)

    def bind(self, **overrides: Any) -> "Provider":
        return self


class Tools:
    def available_tools(self) -> Sequence[ToolDefinition]:
        return (ToolDefinition(name="bash", description="run"),)

    async def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult(tool_call_id=call.id, name=call.name, output="ran")


class Chat:
    def __init__(self, *history: Message) -> None:
        self.history = tuple(history)
        self.commits: list[tuple[Message, ...]] = []

    def messages(self) -> tuple[Message, ...]:
        return self.history

    async def commit(self, messages: Sequence[Message]) -> None:
        self.commits.append(tuple(messages))


class Prompt:
    def render(self) -> "Prompt":
        return self

    @property
    def system_prompt(self) -> str:
        return "persona"


class Compactor:
    def __init__(self) -> None:
        self.calls = 0

    async def compact(self, history, tools):
        self.calls += 1
        return None


class Augmentor:
    def __init__(self) -> None:
        self.calls = 0

    async def augment(self, history, tools):
        self.calls += 1
        return (Message.user("remember the plan"),)


def _acting() -> Message:
    return Message.assistant("", tool_calls=[ToolCall(id="c1", name="bash")])


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, 5.0))


# ---- the lifecycle -------------------------------------------------------


def test_with_no_collaborators_an_exchange_is_exactly_a_run():
    """The backward-compatible degenerate case, byte for byte."""
    bare = Provider(Message.assistant("done"))
    plain = Provider(Message.assistant("done"))

    shelled = _run(AgentEngine(bare, Tools()).exchange("go"))
    ran = _run(AgentEngine(plain, Tools()).run([Message.user("go")]))

    assert bare.seen == plain.seen == [(Message.user("go"),)]
    assert shelled.messages == ran.messages
    assert shelled.stop_reason == ran.stop_reason
    assert shelled.turns == ran.turns
    assert shelled.prompt is None


def test_an_empty_user_text_appends_nothing():
    """A conversation already ending on the user's turn is the ordinary
    case for a caller re-running after a compaction."""
    provider = Provider(Message.assistant("done"))
    engine = AgentEngine(provider, Tools(), conversation=Chat(Message.user("earlier")))

    _run(engine.exchange(""))

    assert provider.seen[0] == (Message.user("earlier"),)


def test_the_compactor_and_augmentor_pass_straight_through():
    provider = Provider(_acting(), Message.assistant("done"))
    compactor, augmentor = Compactor(), Augmentor()
    engine = AgentEngine(provider, Tools(), conversation=Chat())

    result = _run(
        engine.exchange("go", compactor=compactor, augmentor=augmentor)
    )

    assert result.turns == 2
    assert compactor.calls == 2
    assert augmentor.calls == 2
    assert provider.seen[0][-1] == Message.user("remember the plan")


def test_the_streaming_shell_forwards_every_event_the_kernel_emits():
    provider = Provider(_acting(), Message.assistant("done"))
    engine = AgentEngine(provider, Tools(), prompt=Prompt(), conversation=Chat())

    async def drive():
        return [event async for event in engine.exchange_stream("go")]

    events = _run(drive())
    kinds = [event.type for event in events]

    assert kinds.count(EngineEventType.DONE) == 1
    assert kinds[-1] is EngineEventType.DONE
    assert EngineEventType.TOOL_START in kinds
    assert EngineEventType.TOOL_RESULT in kinds
    assert EngineEventType.TEXT_DELTA in kinds
    assert kinds.count(EngineEventType.TURN_END) == 2


def test_both_shells_produce_the_same_trajectory():
    """The point of §6: the two mouths do not disagree about the run."""
    blocking = Provider(_acting(), Message.assistant("done"))
    streaming = Provider(_acting(), Message.assistant("done"))
    chats = Chat(Message.user("earlier")), Chat(Message.user("earlier"))

    blocked = _run(
        AgentEngine(blocking, Tools(), prompt=Prompt(), conversation=chats[0])
        .exchange("go")
    )

    async def drive():
        engine = AgentEngine(
            streaming, Tools(), prompt=Prompt(), conversation=chats[1]
        )
        return [event async for event in engine.exchange_stream("go")][-1].result

    streamed = _run(drive())

    assert blocked.messages == streamed.messages
    assert blocked.stop_reason == streamed.stop_reason
    assert chats[0].commits == chats[1].commits


def test_a_max_turns_exchange_still_commits_what_it_produced():
    """A run that stopped on a ceiling is still a run that happened."""
    provider = Provider(_acting())
    chat = Chat()
    engine = AgentEngine(
        provider, Tools(), EngineConfig(max_turns=2), conversation=chat
    )

    result = _run(engine.exchange("go"))

    assert result.stop_reason.name == "MAX_TURNS"
    assert chat.commits[0] == result.messages


def test_the_shells_hold_no_state_between_exchanges():
    """Two exchanges of one engine, and the second is not the first plus
    the first's history: the engine still owns no conversation."""
    provider = Provider(Message.assistant("a"), Message.assistant("b"))
    engine = AgentEngine(provider, Tools())

    _run(engine.exchange("one"))
    _run(engine.exchange("two"))

    assert provider.seen[0] == (Message.user("one"),)
    assert provider.seen[1] == (Message.user("two"),)


def test_the_user_message_is_the_text_byte_for_byte():
    provider = Provider(Message.assistant("done"))
    engine = AgentEngine(provider, Tools())

    _run(engine.exchange("## User Request"))

    assert provider.seen[0][0] == Message(role=Role.USER, content="## User Request")


# ---- the structure -------------------------------------------------------

_SOURCE = ast.parse(
    pathlib.Path(inspect.getsourcefile(loop_module)).read_text(encoding="utf-8")
)

_SHELL_ROOTS = ("exchange", "exchange_stream")
"""Where the walk below starts. The set it *checks* is derived, not
listed: a name written down here by hand is a name the next helper does
not have to be added to, and logic moved one call down into an unlisted
function would pass a guard that only knew about four names."""

_KERNEL_ENTRIES = frozenset({"run", "run_stream"})
"""The two calls a shell is allowed to make into the loop. The walk stops
at them rather than refusing them — everything the kernel does is the
kernel's to do."""

_LOOP_ONLY = {
    # turn orchestration
    "_kernel",
    "_attempt",
    "_blocking_turn",
    "_streaming_turn",
    "generate_with_retry",
    "_stop_reason_for",
    "_TurnOutcome",
    "turn_end",
    # tool scheduling and Observations
    "execute_tool_calls",
    "observations",
    "_answer_every_call",
    "available_tools",
    "ToolResult",
    "ToolCall",
    "tool_calls",
}


def _defined_functions() -> dict[str, ast.AST]:
    """Every function and method defined in ``engine/loop.py``, by name."""
    return {
        node.name: node
        for node in ast.walk(_SOURCE)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _function(name: str) -> ast.AST:
    node = _defined_functions().get(name)
    if node is None:
        raise AssertionError(f"{name} is not defined in engine/loop.py")
    return node


def _calls_out_of(node: ast.AST) -> set[str]:
    """Names this function calls: bare ``f()`` and ``self.f()`` alike.

    Both spellings, because a shell that grew a helper could reach it
    either way and only one of them looks like a method.
    """
    called: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Name):
            called.add(child.func.id)
        elif isinstance(child.func, ast.Attribute):
            called.add(child.func.attr)
    return called


def _shell_closure(source_functions: dict[str, ast.AST] | None = None) -> set[str]:
    """The shells plus everything they can reach inside ``loop.py``.

    Stops at :data:`_KERNEL_ENTRIES` without descending into them, and
    ignores calls to anything defined elsewhere — a shell is allowed to
    call ``replace`` or ``conversation.commit``; it is not allowed to
    have loop logic of its own, wherever it chose to put it.
    """
    functions = _defined_functions() if source_functions is None else source_functions
    reached: set[str] = set()
    pending = list(_SHELL_ROOTS)
    while pending:
        name = pending.pop()
        if name in reached or name in _KERNEL_ENTRIES:
            continue
        node = functions.get(name)
        if node is None:
            continue  # defined elsewhere — not ours to police
        reached.add(name)
        pending.extend(_calls_out_of(node))
    return reached


def _identifiers(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id)
        elif isinstance(child, ast.Attribute):
            names.add(child.attr)
    return names


@pytest.mark.parametrize("name", sorted(_shell_closure()))
def test_a_shell_contains_no_turn_tool_or_observation_logic(name: str):
    """§12.9's structural criterion, read off the source.

    A behavioural test cannot catch this: a shell that grew its own turn
    counter would still return the right answer for a while, and would
    only be discovered when the two paths' answers drifted apart.
    """
    offenders = sorted(_identifiers(_function(name)) & _LOOP_ONLY)

    assert not offenders, (
        f"{name} names {offenders} — the shells render, splice and "
        "delegate; turns, tools and Observations belong to the kernel"
    )


def test_the_closure_still_reaches_the_helpers_the_shells_delegate_to():
    """The derivation, checked. An empty or shrunken closure passes every
    test above it while policing nothing."""
    assert {"exchange", "exchange_stream", "_opening", "_settle"} <= _shell_closure()
    assert not _KERNEL_ENTRIES & _shell_closure()


def test_the_guard_follows_logic_hidden_one_call_down():
    """The guard itself, against the evasion it exists to stop.

    Listing the four shell names by hand used to be the whole rule, and
    a helper that was not on the list was a helper nobody read. This
    plants exactly that: ``exchange`` delegating to a private function
    whose body schedules tools.
    """
    planted = _defined_functions_of(
        "async def exchange(self):\n"
        "    return _hidden()\n"
        "def _hidden():\n"
        "    return execute_tool_calls()\n"
        "def exchange_stream(self):\n"
        "    return None\n"
    )
    closure = _shell_closure(planted)

    assert "_hidden" in closure, "the walk stopped at the front door"
    offenders = _identifiers(planted["_hidden"]) & _LOOP_ONLY
    assert offenders == {"execute_tool_calls"}


def _defined_functions_of(source: str) -> dict[str, ast.AST]:
    """``_defined_functions`` over a literal snippet, for the test above."""
    return {
        node.name: node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


@pytest.mark.parametrize("name", ("exchange", "exchange_stream"))
def test_a_shell_reaches_the_kernel_only_through_run_or_run_stream(name: str):
    """There is no third entry point into the loop, by construction."""
    engine_calls = {
        node.func.attr
        for node in ast.walk(_function(name))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
    }

    assert engine_calls <= {"run", "run_stream"}, engine_calls


@pytest.mark.parametrize("name", ("exchange", "exchange_stream"))
def test_a_shell_keeps_no_counter_and_runs_no_loop_of_its_own(name: str):
    """``turns += 1`` and ``while`` are the kernel's, and only its."""
    body = _function(name)
    assert not [n for n in ast.walk(body) if isinstance(n, ast.AugAssign)]
    assert not [n for n in ast.walk(body) if isinstance(n, ast.While)]
