"""``omicsclaw/engine`` — the ReAct loop itself.

Plan 0027 §2 and §6, the third step of the staged rebuild. Step 1 gave
the system a vocabulary and step 2 gave it a way to speak; this is the
loop that keeps

    Message → ToolCall → ToolResult → Message

moving until the model stops asking to act::

    engine = AgentEngine(provider, tools, EngineConfig(max_turns=50))

    result = await engine.run(messages)               # blocking
    async for event in engine.run_stream(messages):   # streaming
        ...

**One kernel, two mouths.** :meth:`AgentEngine.run` and
:meth:`AgentEngine.run_stream` share a single copy of the turn / tool /
Observation logic, because a second copy is how a blocking path and a
streaming path start disagreeing about when a run is finished — and the
disagreement surfaces as a bug report about one of them. What differs is
one injected turn strategy: ``run`` calls ``generate`` and
``run_stream`` calls ``generate_stream``, so a blocking caller never pays
for streaming and never reassembles a message out of deltas it did not
want.

Python cannot spell that seam the way the reference harness does. PEP 525
forbids a non-empty ``return`` in an async generator, so a strategy
cannot both yield events and hand back a :class:`Completion`; it fills a
mutable outcome holder instead — the shape plan 0027 §6 blesses, and the
one :func:`~omicsclaw.engine.executor.execute_tool_calls` already uses
for its results.

**What this layer is not.** No prompt assembly, no session persistence,
no tool implementations. The conversation arrives assembled and leaves
as a trajectory; history belongs to the caller. Compaction is not
decided here either: a :class:`~omicsclaw.engine.compactor.
HistoryCompactor` handed to :meth:`AgentEngine.run` is consulted before
every model call and may rewrite what is sent, or the history itself.
Nor is what a call is *reminded* of: a
:class:`~omicsclaw.engine.augmentor.TurnAugmentor` is consulted after the
compactor and may append to that call — and only to that call. The loop
knows neither what a plan is nor that one exists.

**Leaf-adjacent.** ``omicsclaw.schema``, ``omicsclaw.provider`` and the
standard library. No logging, no I/O, no vendor SDK.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import aclosing
from dataclasses import dataclass, replace

from omicsclaw.provider import Completion, LLMProvider, ProviderError
from omicsclaw.schema import (
    Message,
    StreamChunkType,
    ToolCall,
    ToolDefinition,
    ToolResult,
    Usage,
)

from .augmentor import TurnAugmentor
from .compactor import HistoryCompactor
from .config import EngineConfig
from .executor import ToolExecutor, execute_tool_calls, observations
from .retry import generate_with_retry
from .types import EngineError, EngineEvent, RunResult, StopReason

_TRUNCATING_FINISH_REASONS = frozenset({"length", "max_tokens"})
"""The two spellings of "the output ceiling cut this turn off".

``length`` is the OpenAI family's, ``max_tokens`` is Anthropic's.
Compared case-insensitively and by exact match: a vendor token nobody
recognises means *not truncated*, because guessing that an unfamiliar
reason implies truncation would abandon runs that had in fact finished.
"""


@dataclass(slots=True)
class _TurnOutcome:
    """Where a turn strategy leaves what its model call produced.

    PEP 525 forbids a non-empty ``return`` in an async generator, so a
    strategy that yields events cannot also return its ``Completion``.
    Plan 0027 §6 blesses this holder as the seam; task C's
    ``execute_tool_calls`` uses the same shape for its results, which
    leaves the package with one idiom to learn instead of two.
    """

    completion: Completion | None = None
    """What the model said. Still ``None`` after a strategy has finished
    means the model call produced nothing usable — a stream that died
    before its DONE chunk, or a provider that returned ``None`` where the
    Protocol says ``Completion``. Trap 11, and the one thing that must
    never be read as an empty turn.

    Reset to ``None`` before every *attempt*, not merely every turn: see
    :meth:`AgentEngine._attempt`, where the reason is that this field
    outliving the attempt that wrote it is how a retried turn reports a
    stale answer as a fresh one."""

    usage: Usage | None = None
    """What the backend reported, where the path this turn took can tell.

    Carried beside the completion rather than taken from it because
    ``Completion.usage`` defaults to zeros and so cannot express the
    difference between "this turn was free" and "this backend does not
    say".

    **Only the streaming path can express that difference, and that is a
    limit rather than a policy.** ``StreamChunk.usage`` is
    ``Usage | None``, so :meth:`AgentEngine._streaming_turn` passes the
    ``None`` through untouched. ``Completion.usage`` is not optional, so
    :meth:`AgentEngine._blocking_turn` has nothing but zeros to copy: a
    blocking turn against a backend that reported nothing is indistinguishable
    here from a blocking turn that genuinely cost nothing, and both arrive
    as ``Usage()``. Fixing that means giving ``Completion`` a way to say
    "not reported", which belongs to :mod:`omicsclaw.provider` and not to
    this layer — so this docstring states the limit rather than promising
    past it.
    """


_TurnStrategy = Callable[
    [tuple[Message, ...], tuple[ToolDefinition, ...], int, _TurnOutcome],
    AsyncIterator[EngineEvent],
]
"""One model call: yield whatever the caller should see, fill the holder."""


class AgentEngine:
    """Drives one conversation to convergence, and stops on its own terms.

    Holds the provider ("the brain"), the tool executor ("the hands") and
    one frozen budget for its lifetime. It holds no conversation: a run's
    history arrives as an argument and leaves inside its
    :class:`~omicsclaw.engine.types.RunResult`, so two runs of the same
    engine cannot contaminate each other and nothing needs resetting
    between them.
    """

    def __init__(
        self,
        provider: LLMProvider,
        tools: ToolExecutor,
        config: EngineConfig | None = None,
    ) -> None:
        self._provider = provider
        self._tools = tools
        self._config = config if config is not None else EngineConfig()

    # ---- the two entry points -------------------------------------------

    async def run(
        self,
        messages: Sequence[Message],
        *,
        compactor: HistoryCompactor | None = None,
        augmentor: TurnAugmentor | None = None,
    ) -> RunResult:
        """Run to completion and hand back the whole trajectory.

        *compactor*, when given, is consulted before every model call;
        see :class:`~omicsclaw.engine.compactor.HistoryCompactor`.
        *augmentor* is consulted after it and may append to what that
        call is sent; see
        :class:`~omicsclaw.engine.augmentor.TurnAugmentor`.

        The events the kernel produces are dropped here rather than
        summarised: a caller who wants to watch a run asked for
        :meth:`run_stream`, and inventing a second, quieter event
        vocabulary for the blocking path would be the second copy this
        design exists to avoid.

        Raises :class:`~omicsclaw.provider.ProviderError` for a backend
        failure and propagates :exc:`asyncio.CancelledError` untouched.
        Neither is a ``stop_reason``: a ``RunResult`` exists only when the
        loop stopped on its own terms.
        """
        async for event in self._kernel(
            messages, self._blocking_turn, compactor, augmentor
        ):
            # DONE is the only event that carries one, and it is last.
            if event.result is not None:
                return event.result
        raise EngineError(
            "the loop kernel ended without a DONE event — the engine's own "
            "invariant, not the provider's"
        )

    def run_stream(
        self,
        messages: Sequence[Message],
        *,
        compactor: HistoryCompactor | None = None,
        augmentor: TurnAugmentor | None = None,
    ) -> AsyncIterator[EngineEvent]:
        """Run to completion, yielding each increment as it happens.

        *compactor* and *augmentor* are consulted before every model
        call, as for :meth:`run`.

        Deliberately not ``async def``, following
        :meth:`~omicsclaw.provider.LLMProvider.generate_stream`: it
        returns the iterator directly, so callers write ``async for event
        in engine.run_stream(…)`` with no intervening ``await``.

        The final event is ``DONE`` and carries the same
        :class:`~omicsclaw.engine.types.RunResult` :meth:`run` would have
        returned. Failures are raised at the iteration point rather than
        delivered as an error event, because an ``async for`` already
        re-raises there and a consumer should not have to hand-write a
        branch the language gives away (plan 0027 §4 Q3).
        """
        return self._kernel(messages, self._streaming_turn, compactor, augmentor)

    # ---- the kernel ------------------------------------------------------

    async def _kernel(
        self,
        messages: Sequence[Message],
        turn_strategy: _TurnStrategy,
        compactor: HistoryCompactor | None = None,
        augmentor: TurnAugmentor | None = None,
    ) -> AsyncIterator[EngineEvent]:
        """The ReAct cycle — the only copy of it.

        Per turn: re-read the available tools, let the compactor rewrite
        the conversation, let the augmentor add to it, call the model,
        append what it said, and if it asked to act, execute the calls
        and append the Observations. Repeat.

        ``MAX_TURNS`` is the standing verdict. Every other way out is a
        ``break`` the body takes deliberately, so a run that leaves
        through the ``while`` condition is by construction one that still
        had something to say and no room left to say it.
        """
        config = self._config
        history: list[Message] = list(messages)
        usage = Usage()
        turns = 0
        stop = StopReason.MAX_TURNS

        while not (0 < config.max_turns <= turns):
            turns += 1
            # Trap 7. A registry's contents change while a run is in
            # flight — MCP servers connect asynchronously — so reading
            # this once at construction would silently hide every tool
            # registered after that moment.
            tools = tuple(self._tools.available_tools())
            sent = tuple(history)
            if compactor is not None:
                rewrite = await compactor.compact(sent, tools)
                if rewrite is not None and rewrite[0]:
                    sent = tuple(rewrite[0])
                    if rewrite[1]:
                        history = list(sent)
            if augmentor is not None:
                # After the compactor, and onto ``sent`` alone. An
                # augmentor's whole purpose is to be read, so adding
                # before compaction would let compaction remove it; and
                # ``history`` is what the run carries forward, so writing
                # there would make one turn's reminder permanent and let
                # a per-call block accumulate a copy per turn.
                extra = await augmentor.augment(sent, tools)
                if extra:
                    sent = (*sent, *extra)
            outcome = _TurnOutcome()
            async with aclosing(
                generate_with_retry(
                    lambda: self._attempt(turn_strategy, sent, tools, turns, outcome),
                    config,
                )
            ) as turn_events:
                async for event in turn_events:
                    yield event

            completion = outcome.completion
            if completion is None:  # pragma: no cover — _attempt raises first
                # Unreachable, and deliberately still written: "the
                # holder is full by now" is a property of _attempt rather
                # than of this line, and stating it here narrows the type
                # without an ``assert`` that vanishes under ``-O``.
                raise EngineError(
                    f"turn {turns}: the retry loop returned without a completion "
                    "and without raising — this engine's own invariant, since "
                    "_attempt refuses to finish an attempt that filled nothing"
                )
            usage = usage + completion.usage
            # Trap 8: the *whole* assistant message, never a display or
            # truncated view of it. A history that grows anything less
            # loses the turn on the next call, and with it Anthropic's
            # user/assistant alternation.
            history.append(completion.message)

            verdict = _stop_reason_for(completion)
            if verdict is None:
                calls = completion.message.tool_calls
                results: list[ToolResult | None] = []
                async with aclosing(
                    execute_tool_calls(self._tools, calls, config, results, turns)
                ) as tool_events:
                    async for event in tool_events:
                        yield event
                answered = _answer_every_call(calls, results)
                history.extend(observations(answered, config))
            yield EngineEvent.turn_end(turns, outcome.usage)
            if verdict is not None:
                stop = verdict
                break

        yield EngineEvent.done(
            RunResult(
                messages=tuple(history),
                stop_reason=stop,
                usage=usage,
                turns=turns,
            )
        )

    # ---- one attempt at a turn -------------------------------------------

    async def _attempt(
        self,
        turn_strategy: _TurnStrategy,
        history: tuple[Message, ...],
        tools: tuple[ToolDefinition, ...],
        turn: int,
        outcome: _TurnOutcome,
    ) -> AsyncIterator[EngineEvent]:
        """One *attempt* at a turn: empty holder in, filled holder or raise.

        Sits between the retry budget and the turn strategy so that the
        two invariants a retried turn depends on hold for every attempt
        rather than for the turn as a whole.

        **The holder is cleared first, and that is not housekeeping.** The
        kernel builds one :class:`_TurnOutcome` per turn and every attempt
        writes into it, so attempt 1's completion outlives attempt 1.
        Leave it there and a turn where attempt 1 delivered ``DONE`` and
        then failed, and attempt 2 stopped without delivering one, ends
        with the check below reading attempt 1's answer, finding it
        perfectly well-formed, and reporting a converged run built on a
        reply the provider already took back.

        **An attempt that filled nothing raises rather than returns**, and
        this is the *only* place that decides so — which is why both
        strategies hand an empty holder up rather than each inventing its
        own verdict. Trap 11, in the two shapes it actually arrives in:

        - a stream that ended without a usable ``DONE`` chunk, the dropped
          half-stream;
        - a ``generate`` that returned ``None``, or a ``generate_stream``
          that returned something that is not an iterator. The type
          annotations do not prevent this: ``LLMProvider`` is a
          structural Protocol and ``runtime_checkable`` compares method
          names, never return types, so "``Completion.message`` is
          non-optional" stops nothing. Dereferenced, it is an
          ``AttributeError`` (or a ``TypeError``) that no budget catches
          and no strategy expects.

        Reading either as an empty turn would report success on a model
        call that did not happen. Both are raised as a
        :class:`~omicsclaw.provider.ProviderError` — the provider's
        contract is the one that broke, and "a model call failed,
        expressed in this layer's own vocabulary" is what that type is
        for. The attribution is what puts it *inside*
        :func:`~omicsclaw.engine.retry.generate_with_retry` rather than
        beside it: a dropped half-stream is the very scenario the retry
        budget exists for, and the reference harness returns an ordinary
        error for both cases (``retry.go:64-68``, ``stream.go:244-246``),
        buying each three attempts. Raising an ``EngineError`` would have
        made these the failures the budget could not absorb, killing a
        run on first occurrence.
        """
        outcome.completion = None
        outcome.usage = None
        async with aclosing(turn_strategy(history, tools, turn, outcome)) as events:
            async for event in events:
                yield event
        if outcome.completion is None:
            raise ProviderError(
                f"turn {turn}: the provider produced no completion — a stream "
                "that ended without a usable DONE chunk, or a call that "
                "returned nothing at all. A model call that did not happen, "
                "not an empty turn",
                provider=self._provider.name,
            )

    # ---- the two turn strategies -----------------------------------------

    async def _blocking_turn(
        self,
        history: tuple[Message, ...],
        tools: tuple[ToolDefinition, ...],
        turn: int,
        outcome: _TurnOutcome,
    ) -> AsyncIterator[EngineEvent]:
        """One turn over :meth:`~omicsclaw.provider.LLMProvider.generate`.

        A blocking caller must not pay for streaming: there is nothing to
        reassemble here, and ``generate`` is the path on which
        ``finish_reason`` has never been in doubt.

        It yields nothing at all. The unreachable ``yield`` below is what
        makes this function an async generator, which is what lets the
        kernel drive both strategies — and the retry around them — with
        one ``async for``.

        **A ``None`` is left in the holder rather than dereferenced.** The
        annotation says ``generate`` returns a ``Completion``, and the
        annotation is not a check: ``LLMProvider`` is a structural
        Protocol and ``runtime_checkable`` compares *method names*, never
        return types, so a third-party provider returning ``None``
        satisfies ``isinstance`` and arrives here. Reading ``.usage`` off
        it raises an ``AttributeError`` that is neither a
        ``ProviderError`` nor an ``EngineError`` — outside every retry
        budget, so ``generate_retries=5`` buys nothing and the run dies on
        the first occurrence. Returning quietly hands the empty holder to
        :meth:`_attempt`, which is the one place that decides what an
        unproductive attempt means. It is the same standard this layer
        already applies to a tool executor that raises (trap 5) and to an
        ``ERROR`` chunk from an adapter neither shipped adapter emits
        (trap 10): a third-party implementer's mistake must not be able
        to kill a run.
        """
        completion = await self._provider.generate(history, tools)
        if completion is not None:
            outcome.completion = completion
            outcome.usage = completion.usage
        return
        yield  # pragma: no cover — makes this an async generator

    async def _streaming_turn(
        self,
        history: tuple[Message, ...],
        tools: tuple[ToolDefinition, ...],
        turn: int,
        outcome: _TurnOutcome,
    ) -> AsyncIterator[EngineEvent]:
        """One turn over ``generate_stream``, chunk by chunk.

        Two of the branches defend a contract rather than serve a happy
        path:

        ``ERROR`` becomes a raised ``ProviderError``. Neither shipped
        adapter emits that chunk, but a third-party adapter satisfying
        the Protocol structurally may, and silently ignoring it would
        turn a failed stream into a turn that merely said nothing.

        ``DONE`` without a message leaves the holder unset, which
        :meth:`_attempt` reports as a
        :class:`~omicsclaw.provider.ProviderError` — the same treatment
        as a stream that stops before ``DONE`` at all, because both are a
        connection that died rather than a model that had nothing to say,
        and both are worth another attempt.

        A ``generate_stream`` that handed back something that is not an
        async iterator is the streaming twin of the blocking path's
        ``None`` completion, and is treated the same way: return, and let
        :meth:`_attempt` turn the empty holder into a retryable failure.
        Iterating it instead raises ``TypeError: … is not async
        iterable``, which no budget catches.

        The test is ``__aiter__``, not ``is None``, and that *is* the
        structural check this layer argues for rather than a betrayal of
        it: having ``__aiter__`` is the definition of an async iterable,
        so every legitimate implementation passes — an async generator, a
        hand-written class, an SDK's own stream object — and what it
        rejects is the shape that was never one. Returning a plain list
        of chunks is the easy misreading of "returns the iterator
        directly", and it should cost a retry, not the run.

        The provider's stream is *closed* rather than merely abandoned.
        Both shipped adapters release their HTTP connection in a
        ``finally`` that only runs when a ``GeneratorExit`` reaches their
        yield, so a consumer who walks away mid-turn leaks a socket
        unless the closure is propagated the whole way down.
        """
        stream = self._provider.generate_stream(history, tools)
        if not hasattr(stream, "__aiter__"):
            return
        async with aclosing(stream) as chunks:
            async for chunk in chunks:
                if chunk.type is StreamChunkType.TEXT_DELTA:
                    yield EngineEvent.text(chunk.delta, turn)
                elif chunk.type is StreamChunkType.REASONING_DELTA:
                    yield EngineEvent.reasoning(chunk.delta, turn)
                elif chunk.type is StreamChunkType.ERROR:
                    raise ProviderError(chunk.error, provider=self._provider.name)
                elif chunk.type is StreamChunkType.DONE and chunk.message is not None:
                    outcome.completion = Completion(
                        message=chunk.message,
                        usage=chunk.usage if chunk.usage is not None else Usage(),
                        finish_reason=chunk.finish_reason,
                    )
                    outcome.usage = chunk.usage


# ---- internals -----------------------------------------------------------


def _stop_reason_for(completion: Completion) -> StopReason | None:
    """Why this turn ends the run, or ``None`` to keep going.

    Truncation is tested **first**, and that ordering is trap 3. A turn
    the output ceiling severed may carry tool calls accumulated from a
    stream that stopped mid-argument, so the calls can be half-parsed
    while looking perfectly well-formed. Acting on one is strictly worse
    than stopping: the model never finished asking, and the loop would be
    executing a request nobody completed.

    The severed turn is still appended to history — it is what the model
    said — which leaves that trajectory ending on unanswered tool calls.
    A caller resuming from it must answer or drop them itself; the loop
    will not invent Observations for calls it deliberately refused to
    run, because an invented one is indistinguishable from a tool that
    really did report that.
    """
    if completion.finish_reason.lower() in _TRUNCATING_FINISH_REASONS:
        return StopReason.TRUNCATED
    if not completion.message.is_action:
        return StopReason.CONVERGED
    return None


def _answer_every_call(
    calls: Sequence[ToolCall],
    results: Sequence[ToolResult | None],
) -> tuple[ToolResult, ...]:
    """Guarantee one Observation per :class:`ToolCall`, paired by position.

    Anthropic requires every ``tool_use`` block to be answered by a
    ``tool_result`` in the very next message. A missing one is not a
    degraded turn, it is a 400 — raised on the *following* request, far
    from the tool that caused it.

    ``execute_tool_calls`` files each result in its call's own slot and
    hands up one slot per call, so the pairing is already decided by the
    time this function sees it: ``results[i]`` answers ``calls[i]``, and a
    ``None`` there means that worker produced nothing.

    **Re-deriving the pairing from ``tool_call_id`` is what this used to
    do, and it was trap 1 coming back in through the side door.** It
    throws away ordering the scheduler established and rebuilds it from a
    field nothing guarantees:

    - *Ids are not unique.* ``openai_provider.decode_tool_call`` mints
      nothing when the vendor omits the field, so two calls can both
      carry ``""`` — a shipped preset (``ollama``) reaches exactly that.
      A ``{result.tool_call_id: result}`` dict collapses them, and the
      model is told ``read_file`` returned what ``delete_file`` did.
    - *Ids are not preserved.* A retrying or wrapping registry, or an MCP
      proxy, may answer under a different id. The genuine output then
      matches no call and is dropped, while the call it belonged to is
      told the tool "produced no result" — inviting the model to re-run
      something that already ran, side effects and all.

    Position survives both. It is also cheaper, and it is the information
    the scheduler already had.

    A call with no result becomes a failed Observation rather than an
    empty or a successful one. It genuinely produced no answer, and
    ``is_error`` is how the model is told so — reporting silence as
    success invites it to build on an answer that does not exist. A
    scheduler that returned fewer slots than calls would be breaking its
    own contract; the missing tail is answered the same way rather than
    raising, because an unanswered ``tool_use`` is a 400 on the next
    request and that is a worse way to learn about it.

    **An answer that came back under the wrong id is re-stamped with the
    right one — a deliberate, silent correction.** Position decides
    *which* call a result answers, but the id is what the wire is
    validated against: Anthropic matches every ``tool_result`` to a
    ``tool_use`` by id, so letting a registry's mislabelled answer
    through turns somebody else's bug into a hard 400 on the following
    request — the very failure the one-Observation-per-call rule exists
    to prevent. A rule that guarantees the count but not the ids is half
    a rule. The engine appended the assistant message that carries the
    authoritative :attr:`ToolCall.id`, so at this point it holds the
    correct value and the executor's is the one in doubt.

    The evidence is not discarded with it. The reported id is kept in the
    answered result's ``metadata`` under ``reported_tool_call_id`` —
    :attr:`~omicsclaw.schema.ToolResult.metadata` is documented as
    execution facts no vendor has a field for, never sent to a model — so
    a registry that is mislabelling its answers stays diagnosable while
    the wire stays valid. Note where that fact can currently be *read*:
    ``observations`` drops metadata by design, so within this package the
    surviving live witness is the ``TOOL_RESULT`` event, which carries
    the executor's original result untouched. The metadata entry is where
    the fact belongs once step 6 starts persisting these records.
    """
    answered: list[ToolResult] = []
    for index, call in enumerate(calls):
        result = results[index] if index < len(results) else None
        if result is None:
            result = ToolResult(
                tool_call_id=call.id,
                name=call.name,
                output=f"tool {call.name!r} produced no result",
                is_error=True,
            )
        elif result.tool_call_id != call.id:
            result = replace(
                result,
                tool_call_id=call.id,
                metadata={
                    **result.metadata,
                    "reported_tool_call_id": result.tool_call_id,
                },
            )
        answered.append(result)
    return tuple(answered)


__all__ = ["AgentEngine"]
