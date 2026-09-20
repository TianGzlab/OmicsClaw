"""Contract tests for ``omicsclaw.engine.loop`` (plan 0027 §6, task B).

The blocking half of the kernel: does the ReAct cycle converge, does it
terminate, and does every Observation it injects belong to the call it
claims to answer. Traps 3, 4, 7, 8 and 9 of plan 0027 §7 each have a
named test here, and the two that do damage *silently* — a truncated turn
whose half-parsed calls get executed anyway, and an Observation shifted
into a neighbour's slot — are tested for the damage rather than for the
symptom.

No network and no vendor SDK: both seams are Protocols, so a scripted
provider and a recording executor drive every case. Neither imports the
Protocol it satisfies, which is how we know the structural typing is
real.
"""

from __future__ import annotations

import asyncio
from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
    Coroutine,
    Sequence,
)
from typing import Any, TypeVar

import pytest

from omicsclaw.engine import AgentEngine, EngineConfig
from omicsclaw.engine.loop import _answer_every_call
from omicsclaw.engine.types import (
    EngineError,
    EngineEventType,
    RunResult,
    StopReason,
)
from omicsclaw.provider import Completion, LLMProvider, ProviderError
from omicsclaw.schema import (
    Message,
    Role,
    StreamChunk,
    ToolCall,
    ToolDefinition,
    ToolResult,
    Usage,
)

_T = TypeVar("_T")

_DEADLINE = 5.0
"""Seconds any one scenario may take. A hang guard, not a measurement.

A loop that fails to terminate does not fail, it spins — and a spin
wedges the whole suite instead of naming the test that caught it.
"""


class ScriptedProvider:
    """A model that says what it was told to say, one turn at a time.

    The last line of the script repeats forever, so "keeps asking for
    tools until something stops it" needs no special case. Every call is
    recorded, because what the loop *hands* the provider is half of what
    is under test here: the tools of that turn, and the history as it
    stood when the turn began.

    The history is recorded **as given and never copied**. Taking a
    ``tuple()`` of it here would be the double quietly making its own
    snapshot, and the test that asks whether the engine passed one would
    then pass whether it did or not.
    """

    def __init__(self, *turns: Completion | BaseException) -> None:
        self._turns = list(turns)
        self.seen: list[tuple[Sequence[Message], tuple[ToolDefinition, ...]]]
        self.seen = []

    @property
    def name(self) -> str:
        return "scripted"

    async def generate(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None = None,
    ) -> Completion:
        self.seen.append((messages, tuple(tools or ())))
        turn = self._turns[min(len(self.seen) - 1, len(self._turns) - 1)]
        if isinstance(turn, BaseException):
            raise turn
        return turn

    def generate_stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolDefinition] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        raise AssertionError("run() must never reach the streaming path")

    def bind(self, **overrides: Any) -> ScriptedProvider:
        return self


class RecordingExecutor:
    """A tool layer whose list of tools can change while a run is running.

    ``tools`` is a plain list on purpose: a test that appends to it
    between turns is reproducing what an MCP server does when it finishes
    connecting.
    """

    def __init__(
        self,
        tools: Sequence[ToolDefinition] = (),
        behaviour: Callable[[ToolCall], Awaitable[ToolResult]] | None = None,
    ) -> None:
        self.tools = list(tools)
        self._behaviour = behaviour
        self.executed: list[ToolCall] = []
        self.reads = 0

    def available_tools(self) -> Sequence[ToolDefinition]:
        self.reads += 1
        return tuple(self.tools)

    async def execute(self, call: ToolCall) -> ToolResult:
        self.executed.append(call)
        if self._behaviour is not None:
            return await self._behaviour(call)
        return ToolResult(
            tool_call_id=call.id, name=call.name, output=f"{call.name} ran"
        )


def _run(main: Coroutine[Any, Any, _T]) -> _T:
    """``pytest-asyncio`` is not installed; ``tests/provider/`` drives
    async tests with :func:`asyncio.run` and so does this."""

    async def guarded() -> _T:
        return await asyncio.wait_for(main, _DEADLINE)

    return asyncio.run(guarded())


def _tool(name: str) -> ToolDefinition:
    return ToolDefinition(name=name, description=f"the {name} skill")


def _call(index: int, name: str = "spatial_de") -> ToolCall:
    return ToolCall(id=f"c{index}", name=name, arguments="{}")


def _acts(
    *calls: ToolCall,
    finish_reason: str = "tool_calls",
    usage: Usage | None = None,
    text: str = "",
) -> Completion:
    return Completion(
        message=Message.assistant(text, tool_calls=calls),
        usage=usage if usage is not None else Usage(),
        finish_reason=finish_reason,
    )


def _answers(
    text: str = "three markers stood out",
    finish_reason: str = "stop",
    usage: Usage | None = None,
) -> Completion:
    return Completion(
        message=Message.assistant(text),
        usage=usage if usage is not None else Usage(),
        finish_reason=finish_reason,
    )


def _engine(
    provider: ScriptedProvider,
    tools: RecordingExecutor | None = None,
    config: EngineConfig | None = None,
) -> tuple[AgentEngine, RecordingExecutor]:
    executor = tools if tools is not None else RecordingExecutor()
    return AgentEngine(provider, executor, config), executor


# --- the cycle ------------------------------------------------------------


def test_a_model_that_asks_for_nothing_converges_on_its_first_turn():
    provider = ScriptedProvider(_answers("done"))
    engine, executor = _engine(provider)

    result = _run(engine.run([Message.user("what changed?")]))

    assert result.stop_reason is StopReason.CONVERGED
    assert result.turns == 1
    assert executor.executed == []
    assert result.final_message == Message.assistant("done")


def test_a_requested_tool_is_executed_and_its_observation_fed_back():
    provider = ScriptedProvider(_acts(_call(1)), _answers("done"))
    engine, executor = _engine(provider)

    result = _run(engine.run([Message.user("run the DE")]))

    assert [call.id for call in executor.executed] == ["c1"]
    assert [m.role for m in result.messages] == [
        Role.USER,
        Role.ASSISTANT,
        Role.TOOL,
        Role.ASSISTANT,
    ]
    assert result.messages[2].content == "spatial_de ran"
    assert result.messages[2].tool_call_id == "c1"
    assert result.turns == 2
    assert result.stop_reason is StopReason.CONVERGED


def test_the_observation_is_visible_to_the_turn_that_follows_it():
    """The whole point of injecting it: the loop is a loop because turn
    ``n + 1`` reasons over what turn ``n`` learned."""
    provider = ScriptedProvider(_acts(_call(1)), _answers())
    engine, _ = _engine(provider)

    _run(engine.run([Message.user("run the DE")]))

    second_turn = provider.seen[1][0]
    assert [m.role for m in second_turn] == [Role.USER, Role.ASSISTANT, Role.TOOL]
    assert second_turn[2].content == "spatial_de ran"


def test_the_trajectory_returned_starts_with_the_conversation_passed_in():
    """So the result can be fed straight back into the next run instead
    of every caller re-splicing history by hand."""
    conversation = [Message.system("you are OmicsClaw"), Message.user("hello")]
    provider = ScriptedProvider(_answers("hi"))
    engine, _ = _engine(provider)

    result = _run(engine.run(conversation))

    assert result.messages[:2] == tuple(conversation)
    assert len(result.messages) == 3


def test_the_provider_is_handed_a_snapshot_and_not_a_live_history():
    """An adapter that keeps what it was sent must not find the record
    rewritten by the turns that came after it.

    Only meaningful because ``ScriptedProvider`` stores the sequence it
    was handed rather than a copy of it: a double that snapshots on the
    way in would report one message here no matter what the engine did.
    """
    provider = ScriptedProvider(_acts(_call(1)), _answers())
    engine, _ = _engine(provider)

    result = _run(engine.run([Message.user("go")]))

    assert len(provider.seen[0][0]) == 1
    assert len(provider.seen[1][0]) == 3
    assert len(result.messages) == 4


def test_usage_is_summed_across_every_turn_of_the_run():
    provider = ScriptedProvider(
        _acts(_call(1), usage=Usage(input_tokens=10, output_tokens=5)),
        _answers(usage=Usage(input_tokens=3, output_tokens=1)),
    )
    engine, _ = _engine(provider)

    result = _run(engine.run([Message.user("go")]))

    assert result.usage == Usage(input_tokens=13, output_tokens=6)


def test_turns_counts_model_calls_rather_than_messages():
    provider = ScriptedProvider(_acts(_call(1), _call(2)), _answers())
    engine, _ = _engine(provider)

    result = _run(engine.run([Message.user("go")]))

    assert result.turns == 2
    assert len(result.messages) == 5


def test_an_engine_keeps_no_conversation_between_two_runs():
    """A run's history arrives as an argument and leaves in its result,
    so nothing needs resetting between runs."""
    provider = ScriptedProvider(_answers("first"), _answers("second"))
    engine, _ = _engine(provider)

    first = _run(engine.run([Message.user("one")]))
    second = _run(engine.run([Message.user("two")]))

    assert len(first.messages) == 2
    assert len(second.messages) == 2
    assert provider.seen[1][0] == (Message.user("two"),)


def test_an_engine_given_no_configuration_uses_the_default_budget():
    engine, _ = _engine(ScriptedProvider(_answers()), config=None)

    result = _run(engine.run([Message.user("go")]))

    assert result.stop_reason is StopReason.CONVERGED
    assert isinstance(result, RunResult)


# --- trap 9: the turn ceiling is checked before the call ------------------


def test_a_ceiling_of_one_permits_exactly_one_model_call():
    provider = ScriptedProvider(_acts(_call(1)))
    engine, _ = _engine(provider, config=EngineConfig(max_turns=1))

    result = _run(engine.run([Message.user("go")]))

    assert len(provider.seen) == 1
    assert result.turns == 1
    assert result.stop_reason is StopReason.MAX_TURNS


def test_a_ceiling_of_two_permits_a_second_model_call():
    """The other side of the boundary. Without it, an off-by-one that
    allows zero calls would pass the test above just as happily."""
    provider = ScriptedProvider(_acts(_call(1)))
    engine, _ = _engine(provider, config=EngineConfig(max_turns=2))

    result = _run(engine.run([Message.user("go")]))

    assert len(provider.seen) == 2
    assert result.turns == 2
    assert result.stop_reason is StopReason.MAX_TURNS


def test_a_run_stopped_by_the_ceiling_keeps_the_work_it_did():
    """The reference harness discards the whole trajectory here, which is
    what makes its budget exhaustion indistinguishable from a crash."""
    provider = ScriptedProvider(_acts(_call(1)))
    engine, _ = _engine(provider, config=EngineConfig(max_turns=1))

    result = _run(engine.run([Message.user("go")]))

    assert [m.role for m in result.messages] == [
        Role.USER,
        Role.ASSISTANT,
        Role.TOOL,
    ]
    assert result.messages[2].content == "spatial_de ran"


@pytest.mark.parametrize("ceiling", [0, -1])
def test_a_ceiling_of_zero_or_less_means_there_is_no_ceiling(ceiling: int):
    """``EngineConfig.max_turns`` promises this in as many words, so an
    implementation that stopped anyway would make that docstring a lie."""
    provider = ScriptedProvider(
        _acts(_call(1)), _acts(_call(2)), _acts(_call(3)), _answers()
    )
    engine, _ = _engine(provider, config=EngineConfig(max_turns=ceiling))

    result = _run(engine.run([Message.user("go")]))

    assert result.turns == 4
    assert result.stop_reason is StopReason.CONVERGED


# --- trap 3: a truncated turn is not a converged one ----------------------


@pytest.mark.parametrize("reason", ["length", "max_tokens"])
def test_the_output_ceiling_ends_a_run_as_truncated(reason: str):
    """``length`` is the OpenAI family's spelling, ``max_tokens`` is
    Anthropic's. Both mean the answer was severed mid-sentence, and
    without this the loop would report one as a completed task."""
    provider = ScriptedProvider(_answers("half a sen", finish_reason=reason))
    engine, _ = _engine(provider)

    result = _run(engine.run([Message.user("go")]))

    assert result.stop_reason is StopReason.TRUNCATED
    assert result.turns == 1
    assert result.final_message == Message.assistant("half a sen")


@pytest.mark.parametrize("reason", ["LENGTH", "Max_Tokens"])
def test_a_finish_reason_is_read_without_regard_to_its_case(reason: str):
    provider = ScriptedProvider(_answers(finish_reason=reason))
    engine, _ = _engine(provider)

    assert _run(engine.run([])).stop_reason is StopReason.TRUNCATED


@pytest.mark.parametrize(
    "reason", ["stop", "end_turn", "tool_calls", "tool_use", "", "lengthy"]
)
def test_any_other_finish_reason_leaves_the_run_converged(reason: str):
    """A vendor token nobody recognises means *not* truncated: guessing
    the other way would abandon runs that had in fact finished."""
    provider = ScriptedProvider(_answers(finish_reason=reason))
    engine, _ = _engine(provider)

    assert _run(engine.run([])).stop_reason is StopReason.CONVERGED


def test_a_truncated_turn_does_not_execute_the_tool_calls_it_carried():
    """The case that does damage silently.

    A call accumulated from a stream that stopped mid-argument can be
    half-parsed while still looking well-formed, so acting on it is
    strictly worse than stopping — the model never finished asking. The
    severed turn is still recorded, because it is what the model said.
    """
    provider = ScriptedProvider(
        _acts(_call(1, "delete_everything"), finish_reason="length")
    )
    engine, executor = _engine(provider)

    result = _run(engine.run([Message.user("go")]))

    assert executor.executed == []
    assert result.stop_reason is StopReason.TRUNCATED
    assert len(provider.seen) == 1
    assert [m.role for m in result.messages] == [Role.USER, Role.ASSISTANT]


def test_truncation_outranks_a_turn_that_also_asked_for_tools():
    """``is_action`` and ``finish_reason`` disagree here, and the order
    the two are tested in is the whole of trap 3."""
    provider = ScriptedProvider(_acts(_call(1), finish_reason="max_tokens"))
    engine, executor = _engine(provider)

    result = _run(engine.run([]))

    assert result.stop_reason is StopReason.TRUNCATED
    assert executor.executed == []


# --- trap 7: the tool list is re-read every turn --------------------------


def test_a_tool_registered_mid_run_is_offered_on_the_very_next_turn():
    """MCP servers connect asynchronously, so a registry's contents
    change while a run is in flight. Reading the list once at
    construction would hide every tool registered after that moment —
    silently, because the model simply never asks for what it was never
    offered.
    """
    executor = RecordingExecutor(tools=[_tool("spatial_de")])

    async def behaviour(call: ToolCall) -> ToolResult:
        executor.tools.append(_tool("spatial_domains"))
        return ToolResult(tool_call_id=call.id, name=call.name, output="ok")

    executor._behaviour = behaviour
    provider = ScriptedProvider(_acts(_call(1)), _answers())
    engine, _ = _engine(provider, executor)

    _run(engine.run([Message.user("go")]))

    assert [t.name for t in provider.seen[0][1]] == ["spatial_de"]
    assert [t.name for t in provider.seen[1][1]] == [
        "spatial_de",
        "spatial_domains",
    ]
    assert executor.reads == 2


def test_an_executor_offering_nothing_offers_nothing_rather_than_a_default():
    """Empty means empty. An adapter substituting a default tool list is
    what plan 0026 forbids, and the loop must not do it either."""
    provider = ScriptedProvider(_answers())
    engine, _ = _engine(provider)

    _run(engine.run([]))

    assert provider.seen[0][1] == ()


# --- trap 8: the whole assistant message goes into history ----------------


def test_the_assistant_message_is_appended_whole_and_not_as_a_view():
    """A display copy loses the turn on the next call, and Anthropic's
    user/assistant alternation breaks with it."""
    said = Message.assistant(
        "I will look",
        reasoning_content="the user wants markers",
        tool_calls=(_call(1),),
    )
    provider = ScriptedProvider(
        Completion(message=said, finish_reason="tool_calls"), _answers()
    )
    engine, _ = _engine(provider)

    result = _run(engine.run([Message.user("go")]))

    assert result.messages[1] == said
    assert result.messages[1].reasoning_content == "the user wants markers"
    assert provider.seen[1][0][1] == said


# --- one Observation per tool call, paired by position --------------------


def test_a_call_whose_execution_vanished_still_gets_an_observation():
    """Anthropic requires every ``tool_use`` to be answered in the very
    next message; a missing ``tool_result`` is a 400 raised on the
    *following* turn, far from the tool that caused it.

    The gap is real: ``execute_tool_calls`` leaves an empty slot for a
    call whose execution raised a bare ``CancelledError``, deliberately,
    because a cancellation is not an Observation.
    """

    async def behaviour(call: ToolCall) -> ToolResult:
        if call.id == "c2":
            raise asyncio.CancelledError
        return ToolResult(tool_call_id=call.id, name=call.name, output=call.id)

    executor = RecordingExecutor(behaviour=behaviour)
    provider = ScriptedProvider(_acts(_call(1), _call(2), _call(3)), _answers())
    engine, _ = _engine(provider, executor)

    result = _run(engine.run([Message.user("go")]))

    observations = [m for m in result.messages if m.role is Role.TOOL]
    assert [m.tool_call_id for m in observations] == ["c1", "c2", "c3"]


def test_the_survivors_keep_their_own_answers_when_one_goes_missing():
    """Trap 1 end to end, with the missing slot in the middle and the
    slowest tool first.

    Zipping a *compacted* result list onto the calls would shift every
    survivor up into a neighbour's slot and hand the model one tool's
    answer under another tool's name. So would filing results in
    completion order, which is why ``c3`` here finishes before ``c1``
    even starts to return: both mistakes put ``output of c3`` under
    ``c1``, and only a scheduler that writes each result into its own
    slot survives.
    """
    third_finished = asyncio.Event()

    async def behaviour(call: ToolCall) -> ToolResult:
        if call.id == "c2":
            raise asyncio.CancelledError
        if call.id == "c1":
            await third_finished.wait()
        else:
            third_finished.set()
        return ToolResult(
            tool_call_id=call.id, name=call.name, output=f"output of {call.id}"
        )

    executor = RecordingExecutor(behaviour=behaviour)
    provider = ScriptedProvider(_acts(_call(1), _call(2), _call(3)), _answers())
    engine, _ = _engine(provider, executor)

    result = _run(engine.run([Message.user("go")]))

    observations = [m for m in result.messages if m.role is Role.TOOL]
    assert [m.tool_call_id for m in observations] == ["c1", "c2", "c3"]
    assert [m.content for m in observations][0] == "output of c1"
    assert [m.content for m in observations][2] == "output of c3"
    assert [m.is_error for m in observations] == [False, True, False]


def test_two_calls_the_vendor_left_unidentified_keep_their_own_answers():
    """R2, and the reason the pairing moved off ``tool_call_id``.

    ``openai_provider.decode_tool_call`` reads ``id`` straight off the
    payload and mints nothing when the field is absent, so a backend that
    omits it — ``ollama`` is a shipped preset — produces two calls that
    both carry ``""``. A ``{result.tool_call_id: result}`` dict collapses
    them into one entry, and the model is told ``read_file`` returned
    what ``delete_file`` did: a destructive answer filed under a harmless
    question, silently, with nothing in the trajectory to show for it.
    """
    anonymous = (
        ToolCall(id="", name="read_file", arguments="{}"),
        ToolCall(id="", name="delete_file", arguments="{}"),
    )

    async def behaviour(call: ToolCall) -> ToolResult:
        return ToolResult(
            tool_call_id=call.id, name=call.name, output=f"{call.name} ran"
        )

    executor = RecordingExecutor(behaviour=behaviour)
    provider = ScriptedProvider(_acts(*anonymous), _answers())
    engine, _ = _engine(provider, executor)

    result = _run(engine.run([Message.user("go")]))

    observations = [m for m in result.messages if m.role is Role.TOOL]
    assert [m.name for m in observations] == ["read_file", "delete_file"]
    assert [m.content for m in observations] == ["read_file ran", "delete_file ran"]


def test_a_result_re_issued_under_another_id_is_still_that_calls_answer():
    """R3. A ``tool_call_id`` is not an identity the loop controls.

    A retrying or wrapping registry, or an MCP proxy, can answer under a
    derived id. Looked up by id, that genuine output matches nothing: it
    is dropped, the call is told the tool "produced no result", and the
    model's cheapest repair is to run it again — which for a mutating
    tool means doing the work twice. Position is what makes the answer
    findable.
    """

    async def behaviour(call: ToolCall) -> ToolResult:
        return ToolResult(
            tool_call_id=f"{call.id}-attempt-2",
            name=call.name,
            output="42 spots removed",
        )

    executor = RecordingExecutor(behaviour=behaviour)
    provider = ScriptedProvider(_acts(_call(1, "spatial_filter")), _answers())
    engine, _ = _engine(provider, executor)

    result = _run(engine.run([Message.user("go")]))

    observation = [m for m in result.messages if m.role is Role.TOOL][0]
    assert observation.content == "42 spots removed"
    assert observation.is_error is False
    assert len(executor.executed) == 1


def test_an_observation_reaching_history_carries_the_id_its_call_was_issued_under():
    """Position decides *which* call an answer belongs to; the id is what
    the wire is validated against, and both have to be right.

    Anthropic matches every ``tool_result`` to its ``tool_use`` by id, so
    a mislabelled answer let through as-is converts somebody else's
    labelling bug into a hard 400 on the following request — the exact
    failure one-Observation-per-call exists to prevent. The engine
    appended the assistant message that carries the authoritative id, so
    it is the executor's that is in doubt here, not the call's.
    """

    async def behaviour(call: ToolCall) -> ToolResult:
        return ToolResult(
            tool_call_id="whatever-the-proxy-felt-like",
            name=call.name,
            output="42 spots removed",
        )

    executor = RecordingExecutor(behaviour=behaviour)
    provider = ScriptedProvider(_acts(_call(1, "spatial_filter")), _answers())
    engine, _ = _engine(provider, executor)

    result = _run(engine.run([Message.user("go")]))

    observation = [m for m in result.messages if m.role is Role.TOOL][0]
    assert observation.tool_call_id == "c1"
    assert observation.content == "42 spots removed"


def test_the_id_the_executor_reported_is_kept_as_evidence_not_discarded():
    """The correction is silent, so the evidence must not be.

    Rewriting an id hides a registry that is mislabelling its answers,
    which is a real objection to doing it. ``ToolResult.metadata`` is
    where that is answered: execution facts no vendor has a field for,
    documented as never reaching a model, so the diagnostic survives on
    the record while the wire stays valid.
    """
    call = _call(1, "spatial_filter")
    reported = ToolResult(
        tool_call_id="c1-attempt-2", name="spatial_filter", output="42 spots removed"
    )

    answered = _answer_every_call((call,), [reported])

    assert answered[0].tool_call_id == "c1"
    assert answered[0].metadata["reported_tool_call_id"] == "c1-attempt-2"
    assert answered[0].output == "42 spots removed"
    assert answered[0].name == "spatial_filter"


def test_a_result_already_wearing_its_own_calls_id_is_passed_through_untouched():
    """The correction fires only on a mismatch.

    Rebuilding every result would put a ``reported_tool_call_id`` on
    every Observation of every run, which would make the entry useless as
    a signal — the thing it is there to be.
    """
    result = ToolResult(tool_call_id="c1", name="spatial_de", output="3 markers")

    answered = _answer_every_call((_call(1),), [result])

    assert answered[0] is result
    assert "reported_tool_call_id" not in answered[0].metadata


def test_a_missing_observation_reports_a_failure_rather_than_silence():
    """It genuinely produced no answer, and ``is_error`` is how the model
    is told so. Reporting silence as success invites it to build on an
    answer that does not exist."""

    async def behaviour(call: ToolCall) -> ToolResult:
        raise asyncio.CancelledError

    executor = RecordingExecutor(behaviour=behaviour)
    provider = ScriptedProvider(_acts(_call(1, "spatial_cnv")), _answers())
    engine, _ = _engine(provider, executor)

    result = _run(engine.run([Message.user("go")]))

    observation = [m for m in result.messages if m.role is Role.TOOL][0]
    assert observation.is_error
    assert "spatial_cnv" in observation.content
    assert observation.tool_call_id == "c1"


def test_a_failed_tool_reaches_the_model_as_a_failure():
    """``ToolResult.is_error`` survives the projection into history, so
    the model can fix a bad argument instead of parsing prose."""

    async def behaviour(call: ToolCall) -> ToolResult:
        raise ValueError("threshold must be positive")

    executor = RecordingExecutor(behaviour=behaviour)
    provider = ScriptedProvider(_acts(_call(1)), _answers())
    engine, _ = _engine(provider, executor)

    result = _run(engine.run([Message.user("go")]))

    observation = [m for m in result.messages if m.role is Role.TOOL][0]
    assert observation.is_error
    assert "threshold must be positive" in observation.content


def test_an_empty_tool_output_becomes_the_configured_placeholder():
    """Substituted before any message reaches an adapter, because some
    backends reject an empty ``tool_result`` outright."""

    async def behaviour(call: ToolCall) -> ToolResult:
        return ToolResult(tool_call_id=call.id, name=call.name, output="")

    executor = RecordingExecutor(behaviour=behaviour)
    provider = ScriptedProvider(_acts(_call(1)), _answers())
    engine, _ = _engine(provider, executor)

    result = _run(engine.run([Message.user("go")]))

    observation = [m for m in result.messages if m.role is Role.TOOL][0]
    assert observation.content == EngineConfig().empty_output_placeholder


# --- failures and cancellation --------------------------------------------


def test_a_provider_failure_is_raised_rather_than_returned():
    """There is no ``StopReason.ERROR``: a ``RunResult`` exists only when
    the loop stopped on its own terms."""
    provider = ScriptedProvider(ProviderError("502 bad gateway", status_code=400))
    engine, _ = _engine(provider)

    with pytest.raises(ProviderError):
        _run(engine.run([Message.user("go")]))


def test_a_transient_provider_failure_does_not_kill_the_run():
    """The budget exists so one bad minute does not cost an agent its
    trajectory. The base delay is a millisecond here so the backoff is
    real without being paid for."""
    provider = ScriptedProvider(
        ProviderError("503", status_code=503), _answers("recovered")
    )
    config = EngineConfig(generate_retries=2, generate_retry_base=0.001)
    engine, _ = _engine(provider, config=config)

    result = _run(engine.run([Message.user("go")]))

    assert len(provider.seen) == 2
    assert result.turns == 1
    assert result.final_message == Message.assistant("recovered")


class EmptyProvider(ScriptedProvider):
    """A provider that answers with ``None``, which the Protocol permits.

    Not a contrived double: ``LLMProvider`` is structural and
    ``runtime_checkable`` compares method *names*, so this class is an
    ``LLMProvider`` by every check the engine can make. An adapter that
    forgets a ``return`` on one branch, or hands back its SDK's "no
    choices" case, is this.
    """

    def __init__(self, empty_turns: int = 1_000) -> None:
        super().__init__(_answers("recovered"))
        self._empty_turns = empty_turns

    async def generate(self, messages, tools=None):
        if len(self.seen) < self._empty_turns:
            self.seen.append((messages, tuple(tools or ())))
            return None
        return await super().generate(messages, tools)


def test_a_provider_that_answers_with_nothing_is_retried_rather_than_crashing():
    """R8, the blocking twin of a stream that never sent its DONE.

    Dereferenced, this is ``AttributeError: 'NoneType' object has no
    attribute 'usage'`` — neither a ``ProviderError`` nor an
    ``EngineError``, so it sits outside every budget and
    ``generate_retries=5`` buys nothing while the run dies on the first
    occurrence. The type annotation does not prevent it: nothing checks
    return types at runtime, which the assertion below states rather than
    assumes.
    """
    provider = EmptyProvider()
    config = EngineConfig(generate_retries=3, generate_retry_base=0.001)
    engine, _ = _engine(provider, config=config)

    assert isinstance(provider, LLMProvider)
    with pytest.raises(ProviderError) as raised:
        _run(engine.run([Message.user("go")]))

    assert len(provider.seen) == 3
    assert "no completion" in str(raised.value)
    assert raised.value.provider == "scripted"


def test_a_provider_that_answers_with_nothing_once_can_still_finish_the_run():
    """Retryable means recoverable, not merely renamed.

    The reference harness treats an empty response as transient for this
    reason (``retry.go:64-68``): the alternative is a whole trajectory
    thrown away because one call came back blank.
    """
    provider = EmptyProvider(empty_turns=1)
    config = EngineConfig(generate_retries=3, generate_retry_base=0.001)
    engine, _ = _engine(provider, config=config)

    result = _run(engine.run([Message.user("go")]))

    assert len(provider.seen) == 2
    assert result.turns == 1
    assert result.stop_reason is StopReason.CONVERGED
    assert result.final_message == Message.assistant("recovered")


def test_a_cancelled_run_stays_cancelled():
    """Trap 4. Cancellation is not a failure and it is not a result —
    turning it into either would tell a caller who cancelled a run that
    the run had an opinion about it."""

    class HangingProvider(ScriptedProvider):
        def __init__(self) -> None:
            super().__init__()
            self.reached = asyncio.Event()

        async def generate(self, messages, tools=None):
            self.reached.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")  # pragma: no cover

    async def scenario() -> tuple[bool, BaseException]:
        provider = HangingProvider()
        engine, _ = _engine(provider)
        task = asyncio.ensure_future(engine.run([Message.user("go")]))
        await provider.reached.wait()
        task.cancel()
        outcome = (await asyncio.gather(task, return_exceptions=True))[0]
        return task.cancelled(), outcome

    cancelled, outcome = _run(scenario())

    assert cancelled
    assert isinstance(outcome, asyncio.CancelledError)


def test_run_never_reaches_the_streaming_entry_point():
    """A blocking caller must not pay for streaming, and ``generate`` is
    the path on which ``finish_reason`` has never been in doubt."""
    provider = ScriptedProvider(_acts(_call(1)), _answers())
    engine, _ = _engine(provider)

    result = _run(engine.run([Message.user("go")]))

    assert result.stop_reason is StopReason.CONVERGED
    # The double's streaming half is a landmine, so "never reached it" is
    # the run above having finished at all rather than an absence nobody
    # can see.
    with pytest.raises(AssertionError):
        provider.generate_stream(())


def test_the_blocking_strategy_reports_what_the_turn_cost_like_the_other_one():
    """Reaching past ``run`` on purpose.

    ``run`` discards the kernel's events, so the blocking strategy's half
    of the outcome holder has no public observer — and an unobserved
    field is one that quietly stops being filled. Driving the kernel
    directly is the only way to hold both strategies to the same seam.
    """
    provider = ScriptedProvider(_answers(usage=Usage(input_tokens=9)))
    engine, _ = _engine(provider)

    async def scenario() -> list[Any]:
        return [event async for event in engine._kernel([], engine._blocking_turn)]

    events = _run(scenario())
    turn_end = [e for e in events if e.usage is not None]

    assert len(turn_end) == 1
    assert turn_end[0].usage == Usage(input_tokens=9)


def test_the_blocking_path_cannot_say_that_the_backend_reported_nothing():
    """The one asymmetry between the two strategies, pinned as a limit.

    ``EngineEvent.usage`` is ``None`` when a backend reported nothing —
    but only a *streamed* turn can say so, because ``StreamChunk.usage``
    is optional and ``Completion.usage`` is not. ``_blocking_turn`` has
    nothing but zeros to copy, so a silent backend is indistinguishable
    here from a turn that genuinely cost nothing, and both arrive as
    ``Usage()``.

    Closing that gap means teaching ``Completion`` to express "not
    reported", which belongs to ``omicsclaw.provider``. Until it does,
    this is what the blocking path *does*, and the docstrings on
    ``_TurnOutcome.usage`` and ``EngineEvent.usage`` say so rather than
    promising past it.
    """
    provider = ScriptedProvider(_answers())
    engine, _ = _engine(provider)

    async def scenario() -> list[Any]:
        return [event async for event in engine._kernel([], engine._blocking_turn)]

    events = _run(scenario())
    turn_end = [e for e in events if e.type is EngineEventType.TURN_END]

    assert len(turn_end) == 1
    assert turn_end[0].usage == Usage()
    assert turn_end[0].usage is not None


def test_run_refuses_to_invent_a_result_when_the_kernel_produces_none():
    """``run`` reads its answer off the kernel's ``DONE`` event. If that
    event never arrives, the honest report is a broken invariant — never
    an empty, successful-looking run.

    This is also ``EngineError``'s one reachable case now that a dead
    provider stream raises ``ProviderError`` instead (R6): the kernel is
    code this package wrote, so no backend can be blamed for it going
    quiet, and that is exactly the distinction the two types keep.
    """
    engine, _ = _engine(ScriptedProvider(_answers()))

    async def kernel_that_says_nothing(*args: Any) -> AsyncIterator[Any]:
        return
        yield

    engine._kernel = kernel_that_says_nothing

    with pytest.raises(EngineError):
        _run(engine.run([Message.user("go")]))
