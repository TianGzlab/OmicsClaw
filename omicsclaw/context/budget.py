"""``omicsclaw/context`` — how much room is left, and how worried to be.

Plan 0030 task A, decisions Q9, Q9-a and Q9-b. One question this module
answers before the model is called rather than after: *does this fit, and
if not, how badly?*

**The denominator is a subtraction, not a percentage.** The reference
harness compares against a flat fraction of the context window — 80% in
``internal/memory/compaction.go:87-92``, 60/70/80/95% of the window in
``progressive_compactor.go:124-134``. It uses a fraction because it has
no better number to hand. We do::

    usable = context_tokens
           - reserve_output_tokens      # ModelLimits.output_tokens
           - reserve_tool_tokens        # estimate_tool_tokens(tools)
           - context_tokens * safety_ratio

That this is the harness's own intent rather than a local invention is
something the harness says out loud. Its real benchmark does not use the
80% default: ``cmd/swebench/runner.go:293-299`` sets the budget to
**55%** of the window, and the comment on ``:294`` spends the missing
45% on "tool definitions (~25K) + output reserve + chars/4 estimation
error" — the three subtrahends above, folded into one fraction because
Go had nowhere to put them separately.

**Neither reserve has a default, and that is the point.** A default of
zero is the convenient value, not the guarded one: a caller who forgets
``reserve_tool_tokens`` gets a budget 20-30K tokens larger than the
space that actually exists (``token.go:32``), and nothing in this
package can notice, because :func:`~omicsclaw.context.compaction.
plan_compaction` is never shown the tools. Both numbers are *known* to
the caller — one from ``get_model_limits(model)``, one from
:func:`~omicsclaw.context.tokens.estimate_tool_tokens` — so demanding
them costs a line and buys the whole argument above. Forgetting one is a
``TypeError`` at construction.

A warning that travels with ``reserve_output_tokens``: an output ceiling
of 8192 out of ``omicsclaw/provider/_model_limits.py`` means *not
known*, not *known to be 8192*. Where the real ceiling is higher, this
budget is optimistic by the difference.

**"No budget configured" is not a budget of zero.** ``context_tokens
<= 0`` raises rather than modelling anything; a caller who does not know
the window holds ``ContextBudget | None`` and does not construct one.
The opposite case — a window so small, or reserves so large, that
``usable_tokens`` is zero or negative — is real and is
:attr:`Pressure.EMERGENCY`, because not one message of history fits and
"do nothing" means posting the whole conversation into a refusal. The
harness's ``ContextWindow <= 0 → TierNone`` (``progressive_compactor.go:
211-213``) is deliberately **not** ported: after the denominator
changed, that line answers a different question than it used to.

**The four ratios are the harness's, uncalibrated here.** 0.60 / 0.70 /
0.80 / 0.95 come from ``progressive_compactor.go:124-134``. They have
never been measured against this repository's traffic, and the number
they are compared to now has a different denominator than the one they
were chosen for (plan 0030 §11.A-7). Saying so is worth more than
inventing four fresh numbers with the same amount of evidence behind
them.

**Where ``local_budget_status`` went.** The replaced layer had a second
grading function, because grading against a 1M-token window says "fine"
forever and only a local budget says anything useful. ``usable_tokens``
*is* that local budget, so the capability is not missing — it is the
only mode this class has.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Sequence

from omicsclaw.schema import Message, ToolDefinition

from .tokens import TokenCounter, estimate_messages_tokens, estimate_tool_tokens

__all__ = [
    "BudgetReport",
    "ContextBudget",
    "PRESSURE_ORDER",
    "Pressure",
    "at_least",
    "measure",
]


class Pressure(StrEnum):
    """How close the conversation is to the edge of what fits.

    Five tiers, named after the reference harness's
    (``progressive_compactor.go:1-12``) rather than after the replaced
    layer's ``OK/WARNING/COMPRESS/CRITICAL/BLOCK``, so that a reader
    holding the Go source beside this one is reading about the same
    thing. Each tier is a different *kind* of answer, not a different
    shade of the same one — see
    :func:`~omicsclaw.context.compaction.plan_compaction`, which turns
    each into a different treatment of the history.
    """

    NONE = "none"
    """Nothing to do. The history is passed through untouched."""

    WARN = "warn"
    """Offload oversized tool results; summarize nothing.

    Without an :class:`~omicsclaw.context.offload.Offloader` no message
    is altered and the tier is only a signal.
    """

    SOFT = "soft"
    """Summarize the older half of the compactible head, keep the rest."""

    FULL = "full"
    """Summarize the whole compactible head."""

    EMERGENCY = "emergency"
    """Truncate without asking a model. Never spends an LLM round trip."""


PRESSURE_ORDER: dict[Pressure, int] = {
    Pressure.NONE: 0,
    Pressure.WARN: 1,
    Pressure.SOFT: 2,
    Pressure.FULL: 3,
    Pressure.EMERGENCY: 4,
}
"""Severity rank per tier.

:class:`Pressure` is a :class:`~enum.StrEnum`, so ``>=`` between two
members compares their *values* alphabetically: ``Pressure.EMERGENCY >=
Pressure.FULL`` is ``False``. Compare tiers through :func:`at_least`.
"""


def at_least(measured: Pressure, threshold: Pressure) -> bool:
    """Whether *measured* is as severe as *threshold*, or worse."""
    return PRESSURE_ORDER[measured] >= PRESSURE_ORDER[threshold]


@dataclass(frozen=True, slots=True)
class ContextBudget:
    """One model call's room, decomposed into what is spoken for.

    Construct per model, from the caller's side of the fence::

        limits = get_model_limits(model)
        budget = ContextBudget(
            context_tokens=limits.context_tokens,
            reserve_output_tokens=limits.output_tokens,
            reserve_tool_tokens=estimate_tool_tokens(registry_tools),
        )

    This package does not perform that lookup itself: importing
    ``omicsclaw.provider`` for one table read would cost the layer its
    leaf status, and the caller already holds the model name.
    """

    context_tokens: int
    """The model's whole context window."""

    reserve_output_tokens: int
    """Room kept for the answer. No default — see the module docstring."""

    reserve_tool_tokens: int
    """Room kept for tool schemas. No default — see the module docstring.

    A declaration, which :func:`measure` will overrule with the measured
    figure whenever the measurement is larger.
    """

    safety_ratio: float = 0.10
    """Fraction of the window held back against estimation error.

    A tenth. The estimator it covers for is uncalibrated (see
    :mod:`omicsclaw.context.tokens`), so this is a round number and not
    a measurement: the harness's own benchmark leaves a larger residual
    after naming the same two reserves (``runner.go:293-299``), while
    this package's per-field rounding already errs high. Both directions
    are guesses, which is exactly why it is a parameter.
    """

    warn_at: float = 0.60
    soft_at: float = 0.70
    full_at: float = 0.80
    emergency_at: float = 0.95

    def __post_init__(self) -> None:
        """Refuse a budget that is looser than its own parts claim.

        Every check below is a *shape* check, not a calibration: none of
        them introduces a threshold, they only say that a reserve cannot
        be negative and that the four tiers have to be in tier order.
        Pitfall 2 is the reason they exist at all — a budget is the one
        kind of arithmetic where a wrong answer still looks like an
        answer. ``ContextBudget(context_tokens=1_000,
        reserve_output_tokens=-5_000, safety_ratio=-1.0)`` used to
        report 7,000 usable tokens out of a 1,000-token window, and
        ``warn_at=0.9, soft_at=0.2`` used to grade a tenth of the budget
        as ``EMERGENCY``. Both are unreachable now, and neither was
        caught by anything that measured the subtraction.
        """
        if self.context_tokens <= 0:
            raise ValueError(
                "context_tokens must be positive: a caller that does not "
                "know the window holds ContextBudget | None and does not "
                "construct one, because zero would be graded as full"
            )
        for field, value in (
            ("reserve_output_tokens", self.reserve_output_tokens),
            ("reserve_tool_tokens", self.reserve_tool_tokens),
            ("safety_ratio", self.safety_ratio),
        ):
            if value < 0:
                raise ValueError(
                    f"{field} must not be negative: usable_tokens "
                    f"subtracts it, so a negative reserve hands back more "
                    f"room than the window has"
                )
        tiers = (
            ("warn_at", self.warn_at),
            ("soft_at", self.soft_at),
            ("full_at", self.full_at),
            ("emergency_at", self.emergency_at),
        )
        for (lower_name, lower), (upper_name, upper) in zip(tiers, tiers[1:]):
            if lower > upper:
                raise ValueError(
                    f"{lower_name}={lower} is above {upper_name}={upper}: "
                    f"pressure() walks the tiers from the top down, so "
                    f"out-of-order thresholds grade a quiet conversation "
                    f"into a tier that discards messages"
                )
        if self.warn_at < 0:
            raise ValueError(
                "warn_at must not be negative: a negative floor grades an "
                "empty conversation as already under pressure"
            )

    @property
    def usable_tokens(self) -> int:
        """What history may occupy. May be zero or negative."""
        safety = int(self.context_tokens * self.safety_ratio)
        return (
            self.context_tokens
            - self.reserve_output_tokens
            - self.reserve_tool_tokens
            - safety
        )

    def ratio(self, used_tokens: int) -> float:
        """*used_tokens* as a fraction of :attr:`usable_tokens`.

        Infinite when nothing is usable, which is honest — no finite
        multiple of zero holds a message — and lands on
        :attr:`Pressure.EMERGENCY` through the ordinary comparison
        below rather than through a special case.
        """
        usable = self.usable_tokens
        if usable <= 0:
            return float("inf")
        return used_tokens / usable

    def pressure(self, used_tokens: int) -> Pressure:
        """Which tier *used_tokens* falls in. Boundaries belong upward."""
        ratio = self.ratio(used_tokens)
        if ratio >= self.emergency_at:
            return Pressure.EMERGENCY
        if ratio >= self.full_at:
            return Pressure.FULL
        if ratio >= self.soft_at:
            return Pressure.SOFT
        if ratio >= self.warn_at:
            return Pressure.WARN
        return Pressure.NONE


@dataclass(frozen=True, slots=True)
class BudgetReport:
    """A preflight reading: what this call will cost, and where it sits."""

    budget: ContextBudget
    """The budget the grade was computed against — **after** the measured
    tool cost was folded in, so ``report.budget.usable_tokens`` is the
    number :attr:`ratio` divided by and not a looser one."""

    message_tokens: int
    tool_tokens: int
    """Measured cost of the tool definitions on this call."""

    tool_reserve_shortfall: int
    """How far the declared tool reserve fell below the measured cost.

    Zero when the declaration was honest. Non-zero is how a caller
    discovers it under-declared, which is the only way to find out: this
    package cannot correct the caller's own budget object.
    """

    pressure: Pressure
    ratio: float


def measure(
    messages: Sequence[Message],
    tools: Sequence[ToolDefinition],
    budget: ContextBudget,
    *,
    counter: TokenCounter | None = None,
) -> BudgetReport:
    """Grade one prospective call against its budget.

    The tool cost reaches this function twice: declared, on
    ``budget.reserve_tool_tokens``, and measured, from *tools*. They are
    the same quantity from two sources, and the tighter of the two wins
    — ``max(declared, measured)``. Trusting the declaration instead
    would hand back a budget 20-30K tokens larger than the room that
    exists every time a caller under-declared (``token.go:32``), which
    is the failure this whole module is arranged to prevent. The
    difference is not swallowed: it is returned as
    :attr:`BudgetReport.tool_reserve_shortfall`.
    """
    tool_tokens = estimate_tool_tokens(tools, counter=counter)
    message_tokens = estimate_messages_tokens(messages, counter=counter)
    shortfall = max(0, tool_tokens - budget.reserve_tool_tokens)
    effective = replace(
        budget,
        reserve_tool_tokens=max(budget.reserve_tool_tokens, tool_tokens),
    )
    return BudgetReport(
        budget=effective,
        message_tokens=message_tokens,
        tool_tokens=tool_tokens,
        tool_reserve_shortfall=shortfall,
        pressure=effective.pressure(message_tokens),
        ratio=effective.ratio(message_tokens),
    )
