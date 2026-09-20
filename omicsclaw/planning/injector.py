"""Putting the plan back in front of the model, before every call.

Plan 0039 §2.2. This is the half of the planning system that makes the
other half worth having: a plan the model wrote four compactions ago is
only authoritative if it is still *present*, and the conversation is
exactly the place it will not be.

Two things are appended, in this order, and both only to the copy that is
sent:

1. the **planning gate** — one nudge, at most once per exchange, when the
   model has been reading for a long time without writing a plan or
   touching anything;
2. the **plan block** — every outstanding item, verbatim, with a header
   saying it outranks whatever the history now says.

The order is the reference harness's (``loop_phases.go:201-216``) and it
is the useful one: the nudge only ever fires when there is no plan, so
the two never appear together, and if that ever changes the instruction
to make a plan should come before the plan it is asking for.

**Nothing here is persisted and nothing accumulates.** The engine appends
these to the conversation it sends and then discards them; the next call
recomputes from the store. That is what makes a plan edited by
``plan_write`` visible on the very next call with no invalidation
anywhere.

:class:`PlanInjector` satisfies
:class:`omicsclaw.engine.TurnAugmentor` **structurally**. It does not
import it, and a layering test pins that.
"""

from __future__ import annotations

from typing import Sequence

from omicsclaw.schema import Message, Role, ToolDefinition

from .plan import PlanStore
from .render import format_plan
from .tool import PLAN_WRITE_TOOL_NAME

__all__ = [
    "DEFAULT_GATE_TURNS",
    "PLANNING_GATE_TEXT",
    "PROGRESS_TOOL_NAMES",
    "PlanInjector",
]


DEFAULT_GATE_TURNS = 8
"""Consecutive read-only model turns before the planning gate fires.

**Re-derived, not ported.** The reference harness uses 12, and says why
(``cmd/swebench/runner.go:52-55``): 12 is offset from its stall window of
10 and sits well below its SWE-bench median of 28 turns, so the nudge
lands while an exploration is drifting rather than after half the budget
is gone. Both of those numbers are properties of *its* run — an 80-turn
unattended coding budget.

The budget here is :attr:`~omicsclaw.engine.EngineConfig.max_turns` = 50,
derived in that module against this repository's own benchmark evidence.
The same fraction of the budget is 7.5, and 8 is the round number above
it. It is also comfortably longer than an ordinary omics question, which
converges in a handful of turns — a gate that fired inside those would be
teaching the model to plan a one-step task.

``0`` or less turns the gate off entirely and leaves the plan block,
which is the right setting for a surface that has its own idea of when to
interrupt.
"""

PLANNING_GATE_TEXT = (
    "You have spent several turns reading without changing anything and "
    f"without writing a plan. Stop and call `{PLAN_WRITE_TOOL_NAME}` once "
    "to record a short plan — locate, act, verify — then work through it, "
    "updating each item as you go."
)
"""What the gate says. ``runner.go:58``'s shape, in this prompt's language.

Three properties are load-bearing and survive the translation: it states
the observation ("you have been reading and not doing"), it names the
tool, and it gives a three-part skeleton so that "make a plan" is a
concrete next action rather than an exhortation. The tool name is
interpolated rather than spelled, because a nudge naming a tool that is
not mounted is worse than no nudge.

English for the reason :data:`~omicsclaw.planning.render.
INJECTION_HEADER` records.
"""

PROGRESS_TOOL_NAMES = frozenset({"write_file", "edit_file"})
"""Tools whose use means the model is doing the work rather than reading.

The reference harness's set exactly (``nudge.go:16-19``), and the names
match this repository's foundation tools. ``bash`` is deliberately absent
from both: it is how you run a script *and* how you grep, so counting it
as progress would disarm the gate for a model that is only exploring —
which is the behaviour the gate exists to catch.

Stated as a name set rather than read off :class:`ToolPolicy`'s
``writes_workspace`` claim, even though that would look more principled.
It would be wrong: ``writes_workspace`` is an advisory claim that
defaults to ``False`` (plan 0028), so an undeclared tool would read as
read-only, and ``bash`` declares it — which would make every ``grep``
progress.
"""


class PlanInjector:
    """One exchange's view of the plan, rendered before every model call.

    :param store: The session's plan. Read, never written.
    :param gate_turns: See :data:`DEFAULT_GATE_TURNS`.
    :param gate_text: See :data:`PLANNING_GATE_TEXT`.

    Built per exchange rather than per app, like the compactor
    (:func:`~omicsclaw.entry.compaction.build_compactor`), because the
    "at most once" in the gate's contract has to be scoped to something,
    and an exchange is the unit a person would recognise as "this
    request".
    """

    __slots__ = ("_gate_text", "_gate_turns", "_nudged", "_store")

    def __init__(
        self,
        store: PlanStore,
        *,
        gate_turns: int = DEFAULT_GATE_TURNS,
        gate_text: str = PLANNING_GATE_TEXT,
    ) -> None:
        self._store = store
        self._gate_turns = gate_turns
        self._gate_text = gate_text
        self._nudged = False

    async def augment(
        self,
        history: Sequence[Message],
        tools: Sequence[ToolDefinition] = (),
    ) -> tuple[Message, ...]:
        """What to append to *history* for this model call.

        :param history: The conversation this call will be sent, after
            compaction. The post-compaction view is the right input and
            not merely the available one: the gate asks what the model
            can currently see, and the block has to land after whatever
            a summary replaced.
        :param tools: This call's tool definitions. Unused — the gate
            reads what the model *did*, not what it could have done — and
            accepted so that the signature matches
            :class:`~omicsclaw.engine.compactor.HistoryCompactor`'s and a
            future augmentor that does care needs no seam change.

        ``async`` with nothing to await, deliberately: the seam is
        ``async`` (plan 0039 §2.2) so that an implementation reading a
        plan out of a database is possible without widening it, and a
        synchronous body is what that costs when the plan is in memory.

        Both messages are :attr:`~omicsclaw.schema.Role.USER`. An
        assistant-role injection would be the model reading its own words
        with no memory of saying them, and a system-role one would land
        mid-conversation, which several backends reject outright.
        """
        appended: list[Message] = []
        if self._gate_fires(history):
            self._nudged = True
            appended.append(Message(role=Role.USER, content=self._gate_text))
        block = format_plan(self._store.read())
        if block:
            appended.append(Message(role=Role.USER, content=block))
        return tuple(appended)

    # ---- internals -------------------------------------------------------

    def _gate_fires(self, history: Sequence[Message]) -> bool:
        """Whether this call should carry the nudge.

        Four conditions, and the first three are all ways of saying "this
        would be noise":

        - the gate is off, or has already fired this exchange;
        - a plan exists — a session with a plan is already being told
          about it every turn, so nudging it to make one is both wrong
          and confusing. This is the reference harness's *disarmed* flag
          (``loop_phases.go:255``) expressed as a fact about the store
          instead of as a flag, which means it also covers a plan
          restored from a previous session;
        - fewer than :attr:`_gate_turns` model turns are visible — either
          the exchange has just started, or a compaction just replaced
          the ones that were. **The consequence is stated in plan 0039
          §4.4 rather than fixed**: the reference harness counts in the
          engine, so its counter survives a compaction and can fire
          where this cannot. Accepted, because a compaction has just
          handed the model a fresh summary, and that is the one turn on
          which an extra instruction is least likely to help.

        The fourth is the actual test: none of the last :attr:`_gate_turns`
        assistant turns called ``plan_write`` or a
        :data:`PROGRESS_TOOL_NAMES` tool.

        That fourth condition is a **window**, where the reference
        harness's counter is permanent — a model that edited a file
        twenty turns ago and has read ever since is disarmed there and
        nudged here. The window is the better answer for this repository
        and it is a judgement, not an accident: an exploration that
        drifted after doing some work is the same drift, and the once
        per exchange guard is what stops the difference becoming
        repetition.
        """
        if self._nudged or self._gate_turns <= 0 or not self._store.is_empty:
            return False
        seen = 0
        for message in reversed(history):
            if message.role is not Role.ASSISTANT:
                continue
            for call in message.tool_calls:
                if call.name == PLAN_WRITE_TOOL_NAME:
                    return False
                if call.name in PROGRESS_TOOL_NAMES:
                    return False
            seen += 1
            if seen >= self._gate_turns:
                return True
        return False
