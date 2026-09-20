"""``omicsclaw.engine`` — the ReAct main loop.

Plan 0027, step 3 of the staged rebuild. Steps 1 and 2 delivered the
vocabulary (:mod:`omicsclaw.schema`) and the interpreter that speaks it
(:mod:`omicsclaw.provider`); this package is the loop that moves those
types until the model has nothing left to ask for::

    from omicsclaw.engine import AgentEngine, EngineConfig

    engine = AgentEngine(provider, tools, EngineConfig(max_turns=50))
    result = await engine.run(messages)

The loop owns turn orchestration, tool scheduling, Observation injection
and the decision to stop — and owns nothing else. Prompt assembly,
session persistence and the tools themselves live elsewhere; compaction
reaches the loop through :class:`~omicsclaw.engine.compactor.
HistoryCompactor`, an optional per-run argument, and
:class:`~omicsclaw.engine.augmentor.TurnAugmentor` is its sibling — also
optional, also per run, consulted after it, and able only to *append* to
the call being made. :class:`~omicsclaw.engine.executor.ToolExecutor`
is exported as the seam those tools will satisfy **structurally**,
without importing this package, exactly as an adapter satisfies
``LLMProvider``.

``execute_tool_calls`` and ``observations`` are exported beside it
because scheduling policy — concurrency, per-tool timeouts, the ordering
of Observations — is the loop's business rather than any tool's, and a
caller assembling its own turn should reach for the same scheduler the
engine uses instead of writing a second one.

:class:`~omicsclaw.engine.executor.ConcurrencyAwareExecutor` and
:class:`~omicsclaw.engine.executor.DeadlineAwareExecutor` are the two
**optional** halves of that seam: the first lets an executor mark a tool
as a barrier so it runs alone, the second lets it carry the per-call
timeout pause down to a tool waiting on a human. An executor that
implements neither is driven exactly as the two-method seam always was.

This package imports ``omicsclaw.schema``, ``omicsclaw.provider`` and the
standard library, and nothing else. No vendor SDK, no logging, no I/O:
importing the loop never requires an optional extra to be installed.
"""

from .augmentor import TurnAugmentor
from .compactor import HistoryCompactor
from .config import EngineConfig
from .executor import (
    ConcurrencyAwareExecutor,
    DeadlineAwareExecutor,
    TimeoutPause,
    ToolExecutor,
    execute_tool_calls,
    observations,
)
from .loop import AgentEngine
from .types import EngineError, EngineEvent, EngineEventType, RunResult, StopReason

__all__ = [
    "AgentEngine",
    "ConcurrencyAwareExecutor",
    "DeadlineAwareExecutor",
    "EngineConfig",
    "EngineError",
    "EngineEvent",
    "EngineEventType",
    "HistoryCompactor",
    "RunResult",
    "StopReason",
    "TimeoutPause",
    "ToolExecutor",
    "TurnAugmentor",
    "execute_tool_calls",
    "observations",
]
