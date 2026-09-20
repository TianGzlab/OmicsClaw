"""Plan 0030 task A: the budget, pinned in the tightening direction.

Pitfall 2 is the organising principle of this file. A budget is the one
kind of arithmetic where a test that passes proves very little: "a large
history gets compacted" is green under an implementation that compacts
everything, and "the subtraction is right" is green under ``0 - 0``. So
every assertion here is chosen for what it rules *out* — a looser
budget, a lower tier, a trusted under-declaration.
"""

from __future__ import annotations

import pytest

from omicsclaw.context.budget import BudgetReport, ContextBudget, Pressure, measure
from omicsclaw.context.tokens import estimate_messages_tokens, estimate_tool_tokens
from omicsclaw.schema import Message, ToolDefinition


def _budget(**overrides) -> ContextBudget:
    """A budget whose ``usable_tokens`` is exactly 1,000.

    The reserves and the safety ratio are pinned to zero so that a tier
    boundary can be hit *exactly*; every other test in this file that
    cares about the subtraction sets them back.
    """
    return ContextBudget(
        **{
            "context_tokens": 1_000,
            "reserve_output_tokens": 0,
            "reserve_tool_tokens": 0,
            "safety_ratio": 0.0,
            **overrides,
        }
    )


def test_both_reserves_are_required():
    """Decision Q9-a: a default of zero is the convenient value.

    A caller who forgets the tool reserve gets a budget 20-30K tokens
    larger than the room that exists, and nothing downstream can notice
    — ``plan_compaction`` is never shown the tools. So forgetting is a
    ``TypeError`` at construction rather than a surprise at runtime.
    """
    with pytest.raises(TypeError):
        ContextBudget(context_tokens=200_000)

    with pytest.raises(TypeError):
        ContextBudget(context_tokens=200_000, reserve_output_tokens=8_192)

    with pytest.raises(TypeError):
        ContextBudget(context_tokens=200_000, reserve_tool_tokens=25_000)


def test_a_window_of_zero_is_refused_rather_than_modelled():
    """Decision Q9-b, row one: "no budget" is not a budget of zero.

    A caller who does not know the window holds ``ContextBudget | None``.
    Constructing one with zero would be graded as permanently full,
    which is a different statement than "unknown" and the wrong one.
    """
    with pytest.raises(ValueError):
        ContextBudget(context_tokens=0, reserve_output_tokens=0, reserve_tool_tokens=0)

    with pytest.raises(ValueError):
        ContextBudget(context_tokens=-1, reserve_output_tokens=0, reserve_tool_tokens=0)


def test_a_reserve_cannot_be_negative():
    """Pitfall 2 again, and it was only being applied to one field.

    ``usable_tokens`` *subtracts* three quantities, so a negative one is
    an addition wearing a reserve's name.
    ``ContextBudget(context_tokens=1_000, reserve_output_tokens=-5_000,
    safety_ratio=-1.0)`` reported **7,000** usable tokens out of a
    1,000-token window, graded every conversation ``NONE``, and nothing
    downstream could tell: every tier, every cut and every record was
    internally consistent with a window that does not exist.

    None of these checks is a calibrated threshold — they say a reserve
    is a reserve, nothing more.
    """
    with pytest.raises(ValueError):
        _budget(reserve_output_tokens=-5_000)

    with pytest.raises(ValueError):
        _budget(reserve_tool_tokens=-1)

    with pytest.raises(ValueError):
        _budget(safety_ratio=-1.0)

    absurd = ContextBudget(
        context_tokens=1_000,
        reserve_output_tokens=0,
        reserve_tool_tokens=0,
        safety_ratio=0.0,
    )
    assert absurd.usable_tokens <= absurd.context_tokens


def test_the_tiers_have_to_be_in_tier_order():
    """``pressure`` walks them from the top down, so order is arithmetic.

    ``warn_at=0.9, soft_at=0.2, full_at=0.5, emergency_at=0.1`` used to
    be accepted, and under it a conversation at 30% of the budget graded
    ``EMERGENCY`` — the tier that throws messages away without asking a
    model. The four ratios themselves stay the harness's and stay
    uncalibrated (see :class:`ContextBudget`); what is refused is a set
    that cannot be walked.
    """
    with pytest.raises(ValueError):
        _budget(warn_at=0.9, soft_at=0.2, full_at=0.5, emergency_at=0.1)

    with pytest.raises(ValueError):
        _budget(full_at=0.99)

    with pytest.raises(ValueError):
        _budget(warn_at=-0.5)

    equal = _budget(warn_at=0.8, soft_at=0.8, full_at=0.8, emergency_at=0.8)
    assert equal.pressure(799) is Pressure.NONE
    assert equal.pressure(800) is Pressure.EMERGENCY


def test_measure_honours_an_injected_counter():
    """Task A acceptance 3 on the preflight, numerator and denominator.

    ``measure`` is handed the caller's tokenizer and is supposed to
    grade with it. Dropping ``counter=`` produces a report that looks
    entirely normal while describing a different call: here the same
    message and the same tool are quiet under the injected counter and
    an emergency under the built-in estimate.
    """

    class _Fixed:
        def count_text(self, text: str) -> int:
            return 1

    messages = [Message.user("x" * 4_000)]
    tools = [ToolDefinition("t", "d" * 4_000, {"type": "object"})]
    budget = _budget()

    report = measure(messages, tools, budget, counter=_Fixed())

    assert report.message_tokens == 4, "content + reasoning + tool_call_id + name"
    assert report.tool_tokens == 3, "name + description + schema"
    assert report.pressure is Pressure.NONE
    assert report.budget.usable_tokens == 1_000 - 3
    assert measure(messages, tools, budget).pressure is Pressure.EMERGENCY


def test_the_reserves_are_subtracted_and_never_added():
    """Pitfall 2: a sign error is invisible to every other test here.

    ``usable_tokens`` computed as an addition still grades tiers, still
    compacts large histories, and still produces a plausible-looking
    number. Only a comparison against the window catches it.
    """
    budget = ContextBudget(
        context_tokens=200_000,
        reserve_output_tokens=8_192,
        reserve_tool_tokens=25_000,
    )

    assert budget.usable_tokens < budget.context_tokens
    assert budget.usable_tokens == 200_000 - 8_192 - 25_000 - 20_000


def test_every_subtrahend_tightens_the_budget():
    """Each of the three, on its own, so none can be silently ignored."""
    base = _budget()

    assert _budget(reserve_output_tokens=100).usable_tokens < base.usable_tokens
    assert _budget(reserve_tool_tokens=100).usable_tokens < base.usable_tokens
    assert _budget(safety_ratio=0.10).usable_tokens < base.usable_tokens


@pytest.mark.parametrize(
    ("used", "expected"),
    [
        (0, Pressure.NONE),
        (599, Pressure.NONE),
        (600, Pressure.WARN),
        (699, Pressure.WARN),
        (700, Pressure.SOFT),
        (799, Pressure.SOFT),
        (800, Pressure.FULL),
        (949, Pressure.FULL),
        (950, Pressure.EMERGENCY),
        (10_000, Pressure.EMERGENCY),
    ],
)
def test_each_tier_boundary_belongs_to_the_tier_above(used: int, expected: Pressure):
    """Pitfall 2: ``>=`` written as ``>`` moves no mid-range value.

    Every threshold is checked on both sides and *exactly on* the
    threshold, which is the only place the comparison operator is
    visible. The four ratios themselves (0.60/0.70/0.80/0.95) are the
    harness's, over a denominator we changed, and have never been
    calibrated here — see :class:`ContextBudget`.
    """
    assert _budget().pressure(used) is expected


def test_reserves_that_eat_the_window_are_an_emergency_not_a_shrug():
    """Decision Q9-b, row two — and the direction is the whole point.

    The harness returns its *lowest* tier when it has no room
    (``progressive_compactor.go:211-213``), which is safe there because
    the number it tests is the raw window. Here the same condition means
    the reserves have consumed everything, so not one message of history
    fits; grading that as "nothing to do" would post the whole
    conversation into a refusal.
    """
    starved = ContextBudget(
        context_tokens=1_000,
        reserve_output_tokens=900,
        reserve_tool_tokens=200,
        safety_ratio=0.0,
    )

    assert starved.usable_tokens < 0
    assert starved.pressure(0) is Pressure.EMERGENCY
    assert starved.pressure(10) is Pressure.EMERGENCY
    assert starved.ratio(10) == float("inf")


def test_the_numerator_and_the_denominator_come_from_the_same_ruler():
    """Task A's seam: one counting rule under the whole tier system.

    A grade is a numerator over a denominator, and they are produced by
    different modules. If ``measure`` counted messages its own way —
    another ``ceil(len/4)``, as the replaced layer had in three separate
    files — every tier boundary would sit somewhere other than where
    :class:`ContextBudget` says it does, and nothing would look wrong.
    """
    messages = [
        Message.user("你好"),
        Message.assistant("hello", reasoning_content="thinking about it"),
    ]
    tools = [ToolDefinition("t", "d", {"type": "object"})]
    budget = ContextBudget(
        context_tokens=1_000,
        reserve_output_tokens=0,
        reserve_tool_tokens=0,
        safety_ratio=0.0,
    )

    report = measure(messages, tools, budget)

    assert report.message_tokens == estimate_messages_tokens(messages)
    assert report.tool_tokens == estimate_tool_tokens(tools)
    assert report.ratio == report.message_tokens / report.budget.usable_tokens
    assert report.pressure is report.budget.pressure(report.message_tokens)


def test_measure_charges_the_tools_it_can_see_not_the_ones_declared():
    """The two-source seam of §3.2, pinned in the tightening direction.

    ``reserve_tool_tokens`` is a declaration and ``tools`` is a
    measurement of the same quantity. Believing the declaration when it
    is lower is how a budget ends up 20-30K tokens too large
    (``token.go:32``); the shortfall is handed back so the caller can
    find out it under-declared.
    """
    tools = [
        ToolDefinition("spatial_de", "d" * 400, {"type": "object"}),
        ToolDefinition("spatial_deconv", "d" * 400, {"type": "object"}),
    ]
    understated = ContextBudget(
        context_tokens=1_000,
        reserve_output_tokens=0,
        reserve_tool_tokens=1,
        safety_ratio=0.0,
    )

    report = measure([Message.user("hi")], tools, understated)

    assert report.tool_tokens > 1
    assert report.tool_reserve_shortfall == report.tool_tokens - 1
    assert report.budget.usable_tokens == 1_000 - report.tool_tokens, (
        "the measured cost must be what was subtracted, not the declaration"
    )
    assert report.budget.usable_tokens < understated.usable_tokens


def test_measure_leaves_an_honest_declaration_alone():
    """The other side of the same ``max``: over-declaring is not corrected.

    A caller that reserved generously keeps its margin, and the
    shortfall is zero because there is none. Without this half, an
    implementation that always used the measured figure would pass the
    test above.
    """
    tools = [ToolDefinition("t", "d", {"type": "object"})]
    generous = ContextBudget(
        context_tokens=1_000,
        reserve_output_tokens=0,
        reserve_tool_tokens=400,
        safety_ratio=0.0,
    )

    report = measure([Message.user("hi")], tools, generous)

    assert report.tool_tokens < 400
    assert report.tool_reserve_shortfall == 0
    assert report.budget.usable_tokens == 600


def test_measure_grades_against_the_budget_it_reports():
    """``report.budget`` is the tightened one, so the numbers agree.

    Reporting the caller's original budget alongside a pressure computed
    from a different one would leave a consumer dividing
    ``message_tokens`` by ``budget.usable_tokens`` and getting a ratio
    the report disagrees with.
    """
    tools = [ToolDefinition("t", "d" * 4_000, {"type": "object"})]
    budget = ContextBudget(
        context_tokens=1_000,
        reserve_output_tokens=0,
        reserve_tool_tokens=0,
        safety_ratio=0.0,
    )

    report = measure([Message.user("x" * 400)], tools, budget)

    assert isinstance(report, BudgetReport)
    assert report.pressure is report.budget.pressure(report.message_tokens)
    assert report.ratio == report.budget.ratio(report.message_tokens)
    assert report.pressure is Pressure.EMERGENCY, (
        "tool definitions alone can exhaust a window, which is why they "
        "are measured rather than assumed"
    )
