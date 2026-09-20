"""Plan 0030 pitfall 19: there are no gates left, so pin what replaced them.

The file keeps the name plan 0030 §7 gave it, and the name is now a
statement about an absence. The replaced layer had **six** checks on
what a summarizer returned — empty, too many tokens, too many
characters, too many bytes, looks like a tool call, and a content
fidelity check that re-read the source material for file paths and
``Error``/``Traceback``/``TODO`` markers and rejected a summary that had
dropped one. The harness has none: ``progressive_compactor.go:423-431``
checks that the call did not error and did not return nil, then parses
whatever came back. The owner's 2026-09-18 ruling takes the harness's
shape.

**The cost is not theoretical here.** A compaction of an omics session
can lose the path to the ``h5ad`` everything downstream refers to, and
gates two and six existed precisely for that. What is left in their
place is two defences, and because they are all that is left they are
tested harder than the thing they replaced:

* a degradation that always happens and always leaves a trace, and
* an emergency tier that never spends an LLM round trip at all.

And one prohibition, which is what the last test here enforces: **no
replacement gate may be invented.** "Reject a summary longer than the
template" needs a template to measure against, and the
deterministic-template path is exactly what was removed.
"""

from __future__ import annotations

import asyncio

import pytest

from omicsclaw.context.budget import ContextBudget, Pressure
from omicsclaw.context.compaction import compact
from omicsclaw.context.summary import is_summary_message
from omicsclaw.context.tokens import estimate_messages_tokens
from omicsclaw.context.transcript import fit_to_budget
from omicsclaw.schema import Message


class _Counting:
    """Records how often it was asked, and what it was asked."""

    def __init__(self, text: str = "") -> None:
        self.text = text
        self.calls = 0

    async def summarize(self, prompt: str, *, system: str) -> str:
        self.calls += 1
        return self.text


class _Raising:
    def __init__(self) -> None:
        self.calls = 0

    async def summarize(self, prompt: str, *, system: str) -> str:
        self.calls += 1
        raise RuntimeError("the summarization endpoint is down")


class _NeverReturns:
    """Waits forever, and remembers whether it was cancelled."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.cancelled = False

    async def summarize(self, prompt: str, *, system: str) -> str:
        self.entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return "unreachable"


def _history(turns: int = 24) -> list[Message]:
    messages = [Message.system("you are OmicsClaw")]
    for index in range(turns):
        messages.append(Message.user(f"q{index} " + "x" * 400))
    return messages


def _budget_at(messages, ratio: float) -> ContextBudget:
    usable = max(1, int(estimate_messages_tokens(messages) / ratio))
    return ContextBudget(
        context_tokens=usable,
        reserve_output_tokens=0,
        reserve_tool_tokens=0,
        safety_ratio=0.0,
    )


@pytest.mark.parametrize(
    ("label", "summarizer"),
    [
        ("absent", None),
        ("raises", _Raising()),
        ("empty string", _Counting("")),
        ("ignores the format", _Counting("Sure! Here is what happened.")),
    ],
)
def test_every_way_a_summarizer_can_fail_degrades_and_leaves_a_trace(
    label: str, summarizer
):
    """Defence one, all four doors (plan 0030 §9-10).

    The last two are one condition in the implementation, not two: a
    response that parses to no anchors and no summary is *structurally*
    empty, which is this layer's equivalent of the harness's ``resp ==
    nil`` check. It is deliberately not a judgement about quality —
    see the last test in this file.

    The result must be the fallback's, byte for byte, and the record
    must say why. A fallback that quietly produced something else would
    pass a test that only asked whether the call survived.
    """
    messages = _history()
    budget = _budget_at(messages, 0.85)

    result, record, state = asyncio.run(
        compact(messages, budget, summarizer=summarizer, pinned=1)
    )

    expected = fit_to_budget(
        messages,
        budget,
        pinned=1,
        min_tail=6,
        target_tokens=int(budget.usable_tokens * budget.soft_at),
    )
    assert result == expected
    assert record.degraded, "a degradation that leaves no trace is silent failure"
    assert record.summarized == 0
    assert record.summary_text == ""
    assert not any(is_summary_message(m) for m in result)
    assert state.summary == "", "a failed round must not advance the state"


def test_a_failed_summarization_pushes_the_history_down_a_tier():
    """Defence one has to *do* something, and for two rounds it did not.

    This test replaces one that asserted the opposite —
    ``assert tuple(messages) == result`` — and recorded in its own
    docstring that "the harness's fallback trims to 80% of the window
    while its tiers trigger from 60%, so its equivalent does push the
    history back down a tier. Ours does not." That is not a property, it
    is the bug: ``fit_to_budget`` returns the input untouched the moment
    it fits, every tier below ``EMERGENCY`` fits ``usable_tokens`` by
    definition, and ``EMERGENCY`` never reaches the fallback. So all
    four ways a summarizer can fail produced a byte-for-byte no-op and a
    string.

    The repair gives the fallback a stricter target than the trigger, as
    ``compaction.go:86-92`` against ``progressive_compactor.go:209-227``
    does, drawn from the tier thresholds already on
    :class:`ContextBudget` rather than from a new number. What this
    pins is that the result got *smaller* and landed under the tier
    below the one that fired — an implementation that re-aimed the
    fallback at ``usable_tokens`` again passes every other assertion in
    this file.
    """
    messages = _history()
    budget = _budget_at(messages, 0.85)

    result, record, _ = asyncio.run(
        compact(messages, budget, summarizer=_Raising(), pinned=1)
    )

    assert record.pressure is Pressure.FULL
    assert "summarizer raised" in record.degraded
    assert len(result) < len(messages), "a degradation that removes nothing is a no-op"
    assert record.tokens_after < record.tokens_before
    assert estimate_messages_tokens(result) <= int(
        budget.usable_tokens * budget.soft_at
    ), "the fallback target is one declared tier below the tier that fired"
    assert budget.pressure(record.tokens_after) is not Pressure.FULL


def test_the_fallback_still_keeps_the_pinned_prefix_and_the_tail():
    """The companion to the tightening: it trims, it does not truncate.

    A fallback aimed at a stricter target could satisfy the test above
    by throwing the conversation away. It peels the oldest compactible
    messages one at a time instead (``compaction.go:117-131``), so the
    pinned prefix is the same object it went in as and ``min_tail``
    recent messages survive verbatim.
    """
    messages = _history()
    budget = _budget_at(messages, 0.85)

    result, _, _ = asyncio.run(
        compact(messages, budget, summarizer=_Raising(), pinned=1, min_tail=6)
    )

    assert result[0] is messages[0]
    assert result[-6:] == tuple(messages[-6:])


def test_the_emergency_tier_never_asks_a_model():
    """Defence two: ``progressive_compactor.go:341-352``.

    The assertion is a **call count**, because an implementation that
    asked and then ignored the answer would satisfy every assertion
    about the resulting messages while still spending a round trip — in
    the one situation where there is no room to spend one, and where the
    summarizer's own prompt would have to fit in the window that just
    overflowed.
    """
    messages = _history(turns=40)
    summarizer = _Counting("## Summary\nwould have worked")

    _, record, _ = asyncio.run(
        compact(
            messages,
            _budget_at(messages, 1.8),
            summarizer=summarizer,
            pinned=1,
        )
    )

    assert record.pressure is Pressure.EMERGENCY
    assert summarizer.calls == 0
    assert record.degraded == "emergency fallback: forced truncation"


def test_an_emergency_degradation_is_recorded_even_though_nothing_failed():
    """``:348-351`` writes an error unconditionally, and it is right to.

    Truncating without a model *is* the degraded outcome, whether or not
    anything went wrong on the way there.
    """
    messages = _history(turns=40)

    _, record, _ = asyncio.run(
        compact(messages, _budget_at(messages, 1.8), summarizer=None, pinned=1)
    )

    assert record.degraded == "emergency fallback: forced truncation"


def test_a_cancelled_summarizer_propagates_instead_of_degrading():
    """Pitfall 12, and the discipline pitfall 4 asks for.

    ``CancelledError`` propagates untouched — the rule this rebuild set
    in step 0027. ``except Exception`` has not caught it since 3.8, so
    the way to break it is a bare ``except``, and that is the mutation
    this test exists to kill: under it the cancellation would be
    swallowed, the compaction would "succeed" by degrading, and the
    caller's timeout would return a result instead of raising.

    The deadline is exercised by a real suspension rather than by
    arriving after the window shut: the summarizer signals that it
    entered and then awaits something that never completes, so the
    cancellation has an ``await`` to arrive at. After the window closes
    the test awaits **once more** before asserting, which is what makes
    ``cancelled`` observable — a coroutine that returned the instant the
    window closed would have observed nothing at all.
    """
    messages = _history()
    budget = _budget_at(messages, 0.85)
    summarizer = _NeverReturns()

    async def scenario() -> None:
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(0.05):
                await compact(messages, budget, summarizer=summarizer, pinned=1)
        await asyncio.sleep(0)

    asyncio.run(scenario())

    assert summarizer.entered.is_set(), "the summarizer was never reached"
    assert summarizer.cancelled, "the cancellation never arrived at an await"


def test_a_summary_that_drops_the_file_path_is_accepted_anyway():
    """The prohibition: no gate may be invented to catch this.

    The replaced layer's sixth gate pulled file paths out of the source
    material and refused a summary that had lost one. It is gone, and
    this is what that means in practice — the ``h5ad`` every later step
    refers to is simply not in the compacted history any more, and
    nothing raises, warns or records. A test asserting the *absence* of
    a check is the only way this stays a decision instead of drifting
    back into a half-remembered one.
    """
    messages = [Message.system("sys"), Message.user("analyse /data/slide.h5ad")]
    messages += [Message.user(f"q{i} " + "x" * 400) for i in range(24)]
    budget = _budget_at(messages, 0.85)
    forgetful = _Counting(
        "## Anchors\n\n### User Intent\ndo some analysis\n\n"
        "## Summary\nthe user asked about a file"
    )

    result, record, _ = asyncio.run(
        compact(messages, budget, summarizer=forgetful, pinned=1)
    )

    assert record.degraded == "", "nothing rejected it, and nothing should have"
    assert record.summarized > 0
    assert not any("slide.h5ad" in m.content for m in result), (
        "the path is gone from the compacted history — plan 0030 §11.A-9 "
        "is the debt this leaves open"
    )
