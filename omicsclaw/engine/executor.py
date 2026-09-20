"""``omicsclaw/engine`` — the hands the loop acts through.

Plan 0027 §2, "the tool seam". The loop needs to be able to act, but it
must not know how the acting is arranged. So it declares the smallest
Protocol that lets it act and nothing more, and step 4's
``omicsclaw/tools/`` satisfies that Protocol **structurally, without
importing** :mod:`omicsclaw.engine` — the same argument plan 0026 made
for :class:`~omicsclaw.provider.base.LLMProvider`, and the reason a test
double here is a fifteen-line class with no import of this module at all.

Scheduling *policy* — concurrency, per-tool timeouts, the ordering of
Observations — stays on this side of the seam, because it is the loop's
business rather than any individual tool's. That is why the reference
harness keeps ``tools_exec.go`` inside its ``engine/`` package too.

**Leaf-adjacent.** ``omicsclaw.schema`` and the standard library.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from contextlib import AbstractContextManager, ExitStack, contextmanager, suppress
from typing import Protocol, TypeAlias, runtime_checkable

from omicsclaw.schema import Message, ToolCall, ToolDefinition, ToolResult

from .config import EngineConfig
from .types import EngineEvent

TimeoutPause: TypeAlias = Callable[[], AbstractContextManager[None]]
"""A factory for one "stop charging me for this" block.

Entering the context it returns suspends the per-call timeout; leaving it
restores whatever was left of the budget. Handed to the tool layer for the
duration of one call so a wait on something that is not the tool's own
work — a human's approval decision — is not reported as the tool running
long. Single-use, like every :func:`~contextlib.contextmanager` result:
call the factory again for a second block.
"""


@runtime_checkable
class ToolExecutor(Protocol):
    """What a tool layer must look like from the loop's side.

    Two methods, and **what they omit is the point**. Risk level,
    approval mode, concurrency safety and working directory are all
    absent, for exactly the reason
    :class:`~omicsclaw.schema.ToolDefinition` omits them: local execution
    policy is the tool layer's own business, and it must never be
    serialized into a prompt. There is nowhere here to put it, so it
    cannot leak.

    A :class:`~typing.Protocol`, not a base class, so satisfying it is a
    matter of shape. ``runtime_checkable`` makes ``isinstance`` work for
    the conformance test.
    """

    def available_tools(self) -> Sequence[ToolDefinition]:
        """The tools offered to the model for the turn about to start.

        A method rather than a fixed attribute because the loop must
        re-read it **every turn**: an executor's contents may change
        while a run is in flight, and answering this once at construction
        time would silently hide every tool registered after that moment.
        """
        ...

    async def execute(self, call: ToolCall) -> ToolResult:
        """Run one call and return its Observation.

        A failure is expected to come back as a
        :class:`~omicsclaw.schema.ToolResult` with ``is_error=True``
        rather than as an exception, which is what that flag exists for:
        the model is shown its errors so it can fix a bad argument and
        try again. The engine nevertheless wraps this call, because it
        cannot assume a third-party implementation honours the
        convention, and one raising executor must not be able to kill a
        whole run.
        """
        ...


@runtime_checkable
class ConcurrencyAwareExecutor(Protocol):
    """An executor that can say which of its tools may run in parallel.

    Deliberately a **second** Protocol rather than a third method on
    :class:`ToolExecutor`. The two-method seam is what a test double and a
    third-party adapter are written against, and widening it would break
    every one of them to add a capability they can live without: an
    executor that does not implement this is scheduled exactly as this
    layer scheduled everything before the barrier existed.

    It answers by tool *name* and not by
    :class:`~omicsclaw.schema.ToolCall`, so nothing here invites an
    executor to decide scheduling from a model's arguments.
    """

    def is_concurrency_safe(self, name: str) -> bool:
        """Whether ``name`` may run beside other tools in the same turn.

        ``False`` makes the call a barrier — see
        :attr:`~omicsclaw.engine.config.EngineConfig.serialize_unsafe_tools`.
        A name the executor does not recognise should answer ``False``,
        for the reason every permission default in this system is the
        guarded one.
        """
        ...


@runtime_checkable
class DeadlineAwareExecutor(Protocol):
    """An executor that can carry the per-call timeout pause to its tools.

    The engine owns the per-call budget, and a tool waiting on a human is
    the one case where charging wall-clock time to that budget reports
    something false: nothing ran long, nobody answered. The pause cannot
    be handed over as an argument — :meth:`ToolExecutor.execute` takes one
    — and the two layers may not import each other, so it is offered
    through a scope the executor opens and closes itself.

    Optional for the same reason :class:`ConcurrencyAwareExecutor` is: an
    executor that does not implement it keeps the budget covering the
    whole call.
    """

    def use_timeout_pause(
        self, pause: TimeoutPause
    ) -> AbstractContextManager[None]:
        """Publish ``pause`` to whatever runs inside the returned scope.

        Entered immediately before one call and exited after it, on the
        Task that call runs on, so the publication is task-local and one
        call's pause is unreachable from another.
        """
        ...


# ---- scheduling one turn's calls ----------------------------------------


async def execute_tool_calls(
    executor: ToolExecutor,
    calls: Sequence[ToolCall],
    config: EngineConfig,
    results: list[ToolResult | None],
    turn: int = 0,
) -> AsyncIterator[EngineEvent]:
    """Run one turn's tool calls, yielding progress events as they happen.

    ``results`` is appended to with **one slot per call, in call order,
    and a ``None`` wherever the worker produced nothing at all** — a tool
    that raised :exc:`asyncio.CancelledError` at us, which is not an
    Observation and must not be invented into one here. The list is
    therefore always ``len(calls)`` longer than it was, whatever happened
    inside, and ``results[i]`` answers ``calls[i]`` or answers nothing.
    The caller reads it only after the iterator is exhausted.

    **The ``None`` is the whole point of the slot.** A compacted list —
    survivors only — forces the caller to re-derive which call each
    result belongs to, and the obvious re-derivation is a lookup by
    ``ToolCall.id``. That is strictly worse than the ordering information
    this function already has: ids are not guaranteed unique (a vendor
    that omits one leaves ``ToolCall.id`` empty and two such calls
    collapse into a single dict entry) and not guaranteed preserved (a
    wrapping registry or an MCP proxy may re-issue the result under a
    different id, after which the genuine output matches nothing and a
    tool that already ran is reported as having produced no result).
    Position is the one correspondence nothing downstream can corrupt.

    **The out-parameter is deliberate, not sloppy.** PEP 525 forbids a
    non-empty ``return`` in an async generator, so a routine that both
    streams events *and* hands back a value cannot be spelled any other
    way. A mutable outcome holder is the seam plan 0027 §6 blesses for
    the loop kernel itself, and reusing it here leaves the layer with one
    shape to learn instead of two.

    **Order is bought with a slot per call, written by index.** The
    reference harness pre-allocates its result slice for exactly this
    reason: completion order stops being call order the moment two tools
    differ in speed, and a mispaired Observation files result B under
    call A's id, after which the model reasons from the wrong answer —
    silently, and for the rest of the run.

    **Events are queued by the workers and drained here**, rather than
    emitted as all-starts-then-all-finishes around a single ``gather``.
    A consumer watching a thirty-second tool has to see it start when it
    starts; batching would hold that news hostage to whichever sibling
    finishes last, which is precisely the moment a progress display is
    worth having.

    **Not every call is started at once.** A call the executor reports as
    not concurrency-safe runs as a barrier — alone, with nothing else of
    this turn's in flight — while its safe neighbours still run beside
    each other. The turn is therefore a sequence of batches, run in call
    order, and a batch is drained before the next one starts.
    :func:`_concurrency_groups` decides the split; ordering, event
    delivery and the slot-per-call contract above are unaffected by it,
    and an executor that cannot answer the question gets one batch holding
    every call.

    Cancellation is not a failure and is not caught: abandoning this
    generator cancels every tool still in flight and waits for them, so
    no orphaned task outlives the turn that started it.
    """
    slots: list[ToolResult | None] = [None] * len(calls)
    queue: asyncio.Queue[EngineEvent | None] = asyncio.Queue()
    limit = config.max_concurrent_tools
    semaphore = asyncio.Semaphore(limit) if limit > 0 else None
    started: list[asyncio.Task[None]] = []

    async def run_one(index: int, call: ToolCall) -> None:
        try:
            if semaphore is not None:
                await semaphore.acquire()
            try:
                queue.put_nowait(EngineEvent.tool_start(call, turn))
                began = time.perf_counter()
                result = await _execute(executor, call, config.tool_timeout)
                elapsed = time.perf_counter() - began
            finally:
                if semaphore is not None:
                    semaphore.release()
            slots[index] = result
            queue.put_nowait(EngineEvent.tool_finished(result, turn, elapsed))
        finally:
            # One sentinel per worker on every exit path, cancellation
            # included, so the drain below ends by counting workers that
            # have stopped rather than events it hopes to receive.
            queue.put_nowait(None)

    try:
        for group in _concurrency_groups(executor, calls, config):
            # One Task per call, so each worker runs on its own copy of
            # the context current here — ``Task.__init__`` calls
            # ``copy_context()``. The tool layer depends on that for
            # per-call approval isolation and says so in
            # ``omicsclaw/tools/context.py``. What would break it is
            # awaiting a call inline instead of in a Task, or handing
            # several Tasks one shared ``Context``.
            batch = [
                asyncio.ensure_future(run_one(index, calls[index]))
                for index in group
            ]
            started.extend(batch)
            live = len(batch)
            while live:
                event = await queue.get()
                if event is None:
                    live -= 1
                    continue
                yield event
        # Every slot, ``None`` ones included. A slot is still ``None``
        # when its worker produced no result at all — a tool that raised
        # ``CancelledError`` at us. Cancellation is not an Observation,
        # so nothing is invented here; the empty slot is handed up as
        # evidence, and the loop decides what to tell the model.
        results.extend(slots)
    finally:
        for task in started:
            task.cancel()
        await asyncio.gather(*started, return_exceptions=True)


def observations(
    results: Sequence[ToolResult],
    config: EngineConfig,
) -> tuple[Message, ...]:
    """Project tool results into the Observation messages appended to history.

    Takes *answered* results — one per call, no empty slots — and not the
    ``list[ToolResult | None]`` :func:`execute_tool_calls` fills. Deciding
    what an unanswered call is told is the loop's business (a call must
    still be answered, or Anthropic rejects the next request), so it
    happens before this function rather than inside it, and nothing here
    has to guess what a ``None`` meant.

    The projection itself already exists as
    :meth:`~omicsclaw.schema.ToolResult.to_message` — which is also what
    carries ``is_error`` through to the adapter, so a failed tool reaches
    the model as a failure rather than as prose it has to parse. This
    function only substitutes for an empty body.

    That substitution happens **here, inside the engine**, before any
    message reaches an adapter, for the two reasons the reference harness
    records: some backends reject a ``tool_result`` with empty content
    outright with a 400, and even where it is accepted an Observation
    carrying no information spends a whole turn saying nothing. The
    wording lives on :class:`~omicsclaw.engine.config.EngineConfig` so a
    deployment can phrase it in the language its models are prompted in.
    """
    projected: list[Message] = []
    for result in results:
        message = result.to_message()
        if not message.content:
            message = message.replace(content=config.empty_output_placeholder)
        projected.append(message)
    return tuple(projected)


# ---- internals ----------------------------------------------------------


def _concurrency_groups(
    executor: ToolExecutor,
    calls: Sequence[ToolCall],
    config: EngineConfig,
) -> list[tuple[int, ...]]:
    """Split one turn's calls into the batches that may run together.

    Each batch is a tuple of indices into ``calls``, and the batches are
    in call order. A call whose tool is not concurrency-safe is a batch of
    one; every other call joins the run of safe neighbours it sits in.

    Returns a single batch holding every call when the barrier is switched
    off, or when the executor cannot answer
    :meth:`ConcurrencyAwareExecutor.is_concurrency_safe` — so an executor
    that has not opted in is scheduled exactly as it was before the
    barrier existed.
    """
    if not calls:
        return []
    if not config.serialize_unsafe_tools or not isinstance(
        executor, ConcurrencyAwareExecutor
    ):
        return [tuple(range(len(calls)))]

    groups: list[tuple[int, ...]] = []
    parallel: list[int] = []
    for index, call in enumerate(calls):
        if _is_concurrency_safe(executor, call.name):
            parallel.append(index)
            continue
        if parallel:
            groups.append(tuple(parallel))
            parallel = []
        groups.append((index,))
    if parallel:
        groups.append(tuple(parallel))
    return groups


def _is_concurrency_safe(executor: ConcurrencyAwareExecutor, name: str) -> bool:
    """Whether ``name`` may run in parallel; an executor that raises means no.

    A wrong answer here changes scheduling silently for every call in the
    turn, so a broken implementation resolves to the guarded value rather
    than to an error the model would have to read.
    """
    try:
        return bool(executor.is_concurrency_safe(name))
    except Exception:
        return False


@contextmanager
def _bound_timeout_pause(
    executor: ToolExecutor,
    budget: asyncio.Timeout,
) -> Iterator[None]:
    """Offer ``budget``'s pause to the executor for one call's duration.

    Yields unchanged when the executor declares no way to receive one —
    and also when the one it declared does not open. An executor that
    opted into this seam and got it wrong loses the pause, which is the
    behaviour of an executor that never opted in; without the guard it
    would instead lose **every** tool call in the run to a ``TypeError``
    the model would be asked to fix, and only when a timeout was
    configured. Same guarded default as :func:`_is_concurrency_safe`, for
    the same reason.

    Only opening is guarded. An exception on the way out is left to
    propagate, because suppressing it would also discard whatever the
    tool was raising through this frame.
    """
    if not isinstance(executor, DeadlineAwareExecutor):
        yield
        return
    with ExitStack() as scope:
        with suppress(Exception):
            scope.enter_context(executor.use_timeout_pause(lambda: _paused(budget)))
        yield


@contextmanager
def _paused(budget: asyncio.Timeout) -> Iterator[None]:
    """Stop ``budget`` for the block, then give back what was left of it.

    Time spent inside is not charged to the per-call timeout: the deadline
    is lifted on the way in and re-set on the way out to the same number
    of seconds that remained on the way in.

    Does nothing when the budget carries no deadline — which is what a
    second pause sees while a first is open, so the first one owns the
    restore — and nothing when the budget has already fired, where
    rescheduling is both refused and pointless.

    That rule is written for **nesting**, where it is exactly right. Two
    pauses opened *side by side* inside one call — an ``asyncio.gather``
    over two sub-tasks that each wait on a person — are a shape it does
    not serve: whichever opened first restores the deadline when it
    closes, and the other is charged for the rest of its wait. Nothing
    here is asking a human twice in parallel today, and a tool that wants
    to should hold one pause around both.

    **A paused call is unbounded on this side.** Every later batch of the
    turn waits behind it too when it is a barrier — see
    :attr:`~omicsclaw.engine.config.EngineConfig.serialize_unsafe_tools`.

    **A paused call has no engine-side bound, and that hands a consumer
    contract to whoever asks the human.** Whatever answers an approval
    request must be able to make progress while the consumer of
    :func:`execute_tool_calls` is suspended between events — its own Task,
    or an ``await`` on the request queue from inside the ``async for``
    body. A consumer that merely *polls* for requests between events never
    sees one: the request is issued after the consumer has already gone
    back to waiting for the next event, and the two wait for each other.

    That consumer was already broken before this function existed; what it
    got instead of a hang was ``tool 'X' timed out``, which is the false
    sentence the pause was written to stop saying. So the pause did not
    create the deadlock — it removed the accident that was hiding it — and
    the honest bound is the one on the surface's own prompt.
    ``tests/engine/test_executor.py`` pins the supported shape.

    The reference harness carries the same hazard in a different shape and
    documents it at ``stream.go:51-58``: its event channel is unbuffered,
    so a second concurrent approval blocks until the TUI reads again, and
    a TUI that stops consuming while its dialog is open deadlocks.
    """
    loop = asyncio.get_running_loop()
    when = budget.when()
    if when is None:
        yield
        return
    remaining = when - loop.time()
    try:
        budget.reschedule(None)
    except RuntimeError:
        yield
        return
    try:
        yield
    finally:
        try:
            budget.reschedule(loop.time() + remaining)
        except RuntimeError:
            pass


async def _execute(
    executor: ToolExecutor,
    call: ToolCall,
    timeout: float,
) -> ToolResult:
    """Run one call so that nothing it does can end the run.

    A tool layer is *expected* to report its own failures as ``is_error``
    Observations, and step 4's registry will. But a Protocol is satisfied
    by shape, so a third-party executor that raises instead must not be
    able to kill a run that was otherwise going fine; the exception
    becomes the Observation, and the model gets to see what went wrong
    and correct it.

    The timeout is per *call*, applied here rather than around the turn,
    so a slow tool degrades into one failed Observation instead of
    cancelling the siblings running beside it.

    **The budget can be paused, and only from inside the call.** A tool
    waiting on a human's approval decision is not a tool running long, so
    the budget is offered to the executor as a
    :data:`TimeoutPause` for the duration of the call —
    :class:`DeadlineAwareExecutor`. An executor that does not take it, or
    a tool that never uses it, is timed exactly as before. What the pause
    costs is that a call blocked on a human who never answers has no
    engine-side deadline left, so a surface that asks for approval owns
    the deadline on its own prompt.

    ``except Exception`` and never ``BaseException``:
    :exc:`asyncio.CancelledError` is not an ``Exception``, so a cancelled
    scope leaves untouched. An expired budget's :exc:`TimeoutError` on
    3.11+ **is** one, and is caught here — it names a tool that overran,
    not a caller who walked away, and letting it escape would report the
    first as the second.

    **Only the budget that actually fired may claim the timeout.** On
    3.11+ ``socket.timeout`` **is** the builtin ``TimeoutError``, so a
    tool with a read budget of its own raises the very class an expired
    engine budget does — and this repository has one:
    ``tools/_websafety.py`` narrows the socket to what is left of its own
    deadline, so ``web_fetch`` against a slow host raises it from inside
    the call. Reported as ours, ``timed out`` against
    ``https://rest.ensembl.org/…`` would reach the model as ``tool
    'web_fetch' timed out after 60s`` — the host gone, the tool's real
    budget replaced by a number that never elapsed, and the model pointed
    at "make it fit in 60s" when the truth is "that service is
    unreachable". (Note which exceptions this is *not* about:
    ``requests.exceptions.ReadTimeout`` descends from ``OSError`` through
    ``RequestException`` and is **not** a ``TimeoutError``, so it never
    reaches this branch at all.) :func:`asyncio.timeout` is used rather than
    :func:`asyncio.wait_for` precisely because it can be *asked*:
    ``expired()`` answers whether this budget is what raised, and an
    unexpired one — including the ``timeout <= 0`` case, where the engine
    imposed no budget at all — falls through to the ordinary wording that
    keeps the exception's own text.
    """
    budget: asyncio.Timeout | None = None
    try:
        if timeout > 0:
            budget = asyncio.timeout(timeout)
            async with budget:
                with _bound_timeout_pause(executor, budget):
                    return await executor.execute(call)
        return await executor.execute(call)
    except TimeoutError as exc:
        if budget is not None and budget.expired():
            return _failed(call, f"tool {call.name!r} timed out after {timeout:g}s")
        return _raised(call, exc)
    except Exception as exc:
        return _raised(call, exc)


def _raised(call: ToolCall, exc: Exception) -> ToolResult:
    """The Observation an exception becomes, carrying its own text.

    The class name *and* the message, because the model is the one asked
    to fix this: ``ValueError: threshold must be positive`` says what to
    change, where a summary written by the engine would say only that
    something went wrong.
    """
    return _failed(call, f"tool {call.name!r} raised {type(exc).__name__}: {exc}")


def _failed(call: ToolCall, description: str) -> ToolResult:
    """The Observation an execution failure becomes.

    A result like any other, filed in its own call's slot: from the
    loop's side a failure *is* the turn's answer for that call, and an
    empty slot would mean something else entirely — that the call was
    never answered at all. It carries the call's
    :attr:`~omicsclaw.schema.ToolCall.id` because the wire needs one,
    though the loop pairs on position and not on that field.
    """
    return ToolResult(
        tool_call_id=call.id,
        name=call.name,
        output=description,
        is_error=True,
    )


__all__ = [
    "ConcurrencyAwareExecutor",
    "DeadlineAwareExecutor",
    "TimeoutPause",
    "ToolExecutor",
    "execute_tool_calls",
    "observations",
]
