"""``omicsclaw/context`` — deciding what to drop, and writing it down.

One compaction, as a function: :func:`compact` grades the conversation,
offloads, cuts head from tail, summarizes and reports, taking the
previous :class:`CompactionState` as a parameter and returning the next
one. It keeps no state and decides nothing about what happens to its
result.

Carrying that state from one model call to the next, and deciding
whether a result replaces the history, is
:class:`~omicsclaw.context.progressive.ProgressiveCompactor`'s — one
instance per run, so concurrent conversations never share it. Keeping
the state between exchanges, persisting records and writing offloaded
text are the caller's.

**Three tiers do three different things**, which is the seam worth
watching: an implementation that routed every pressure level to the same
treatment would pass any test that only checked which
:class:`~omicsclaw.context.budget.Pressure` came back.

=============  =============================================================
``NONE``       nothing, byte for byte
``WARN``       offload oversized tool results; without an offloader, nothing
``SOFT``       summarize the older half of the head, keep the rest verbatim
``FULL``       summarize the whole head, keep ``min_tail`` behind it
``EMERGENCY``  truncate greedily, **never** call the summarizer
=============  =============================================================

When an :class:`~omicsclaw.context.offload.Offloader` is supplied,
:func:`compact` first moves oversized tool results out of the compactible
head at every tier above ``NONE``, then grades the conversation again and
applies the tier it is now in — offloading alone may be enough.

**Only one pass.** The replaced layer compacted to a target ratio and
iterated up to three times to converge, so that one compaction cost one
cache re-warm. Its premise does not hold here — that design assumed the
system prompt and the summary moved together, and in this package
assembly and compaction are two separate functions. One pass, as the
harness does; the total may still sit above target afterwards and the
next turn compacts again.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import Protocol, Sequence, runtime_checkable

from omicsclaw.schema import Message, Role

from .budget import PRESSURE_ORDER, ContextBudget, Pressure
from .offload import (
    MAX_REFERENCES,
    OFFLOAD_MARKER,
    OffloadEntry,
    Offloader,
    offload_messages,
    parse_placeholder,
    parse_references,
)
from .summary import (
    Anchors,
    FIRST_TEMPLATE,
    INCREMENTAL_TEMPLATE,
    OFFLOAD_RULE,
    SUMMARY_SYSTEM_PROMPT,
    Summarizer,
    build_compaction_message,
    is_summary_message,
    parse_anchors_and_summary,
)
from .tokens import TokenCounter, estimate_messages_tokens
from .transcript import (
    _emergency_survivors,
    fit_to_budget,
    render_for_summary,
    repair_tool_pairs,
    split_head_tail,
)

__all__ = [
    "CompactionPlan",
    "CompactionRecord",
    "CompactionState",
    "DEFAULT_MIN_TAIL",
    "MemoryExtractor",
    "apply_compaction",
    "build_summary_prompt",
    "collect_references",
    "compact",
    "plan_compaction",
]

DEFAULT_MIN_TAIL = 6
"""Recent messages a tiered compaction never touches.

``compaction.go:87-92``. The same author used **8** in his own benchmark
(``cmd/swebench/runner.go:293-299``) — one number with two values in one
codebase, which is the whole argument for re-deriving borrowed literals
rather than pasting them. Neither figure has been calibrated against
this repository's traffic, where a single tool result can be an entire
analysis report.
"""

_EMERGENCY_REASON = "emergency fallback: forced truncation"
"""``progressive_compactor.go:341-352`` records an error on every
emergency compaction, whether or not anything went wrong, because
truncating without a model *is* the degraded outcome."""

_STILL_OVER_REASON = "the compacted conversation is still over usable_tokens"
"""The one thing a compaction must never do quietly.

Task C acceptance 3 is unconditional — "it fits afterwards" — and
:func:`compact` cannot always deliver it. Decision Q10 keeps the task
anchor whatever it costs, so an emergency truncation of a conversation
whose task message is itself larger than the budget comes back over the
line by construction. That is the right trade and it is not the same
statement as :data:`_EMERGENCY_REASON`: "I truncated" and "I truncated
and it still does not fit" are different things to read in an audit
record, and only the second one predicts the API refusal on the next
hop.
"""

_FALLBACK_TARGETS: dict[Pressure, str] = {
    Pressure.SOFT: "warn_at",
    Pressure.FULL: "soft_at",
}
"""Which declared threshold a degraded compaction has to get under.

**Not new numbers**: every value is the name of a field on the
:class:`~omicsclaw.context.budget.ContextBudget` the caller passed in,
and the mapping is "one tier down from the tier that triggered".

Two rows, because two tiers can degrade: ``SOFT`` and ``FULL`` are the
only ones that ask a summarizer and so the only ones with a
summarization to fall back from. ``EMERGENCY`` never reaches the
fallback — it has its own truncation and its own reasons — and
``NONE``/``WARN`` change nothing to begin with. A third row would be a
branch nobody can reach.

The harness has this property and this layer had lost it. There
``NewTokenBudgetCompactor`` trims to ``contextWindow * 80/100``
(``compaction.go:86-92``) while ``determineTier`` grades against the
undivided ``contextWindow`` (``progressive_compactor.go:209-227``), so
the fallback target is *stricter* than the trigger and
``compaction.go:117-131`` actually peels. Porting both onto
``usable_tokens`` made them the same number, and since every tier below
``EMERGENCY`` is by definition under ``emergency_at`` — that is, under
1.0 — the first line of :func:`~omicsclaw.context.transcript.
fit_to_budget` returned the input byte for byte on every degraded path
there is. A degradation that removes nothing is not a degradation; it
is the failure, unrecorded except as a string.
"""

_NO_ANCHORS = Anchors()
"""All five ``N/A`` — what an unusable summarizer response parses into."""


@runtime_checkable
class MemoryExtractor(Protocol):
    """Reads the messages a summary is about to replace.

    Called on SOFT and FULL compactions, concurrently with the summarizer,
    with the messages as they were before any offloading. Its return
    value is ignored and an exception it raises is recorded in
    :attr:`CompactionRecord.advisories`; it cannot change or fail the
    compaction.
    """

    async def extract(self, messages: Sequence[Message]) -> object:
        """Read *messages* and keep whatever outlives them."""
        ...


def _more_severe(measured: Pressure, floor: Pressure) -> Pressure:
    """The more severe of the two tiers."""
    return measured if PRESSURE_ORDER[measured] >= PRESSURE_ORDER[floor] else floor


def _emergency_target(budget: ContextBudget) -> int:
    """Tokens an emergency truncation keeps: the FULL threshold.

    Landing below the EMERGENCY threshold is not enough — a conversation
    packed to just under it is graded EMERGENCY again as soon as it grows,
    and is truncated again instead of summarized. At the FULL threshold
    the next compaction summarizes.
    """
    return int(budget.usable_tokens * budget.full_at)


async def _offload_span(
    messages: tuple[Message, ...],
    start: int,
    end: int,
    offloader: Offloader,
    counter: TokenCounter | None,
) -> tuple[tuple[Message, ...], tuple[OffloadEntry, ...], tuple[str, ...]]:
    """Offload the tool results in ``messages[start:end]``."""
    if start >= end:
        return messages, (), ()
    moved = await offload_messages(messages[start:end], offloader, counter=counter)
    if not moved.entries:
        return messages, (), moved.failures
    return (
        (*messages[:start], *moved.messages, *messages[end:]),
        moved.entries,
        moved.failures,
    )


@dataclass(frozen=True, slots=True)
class CompactionState:
    """What one compaction leaves behind for the next one.

    Carried by the caller between turns; step 6 decides where it lives
    (a session row, memory, nowhere). Losing it is not fatal and not
    free: every compaction then starts from
    :data:`~omicsclaw.context.summary.FIRST_TEMPLATE` and re-summarizes
    from a blank slate, so detail shed in the previous round is gone
    rather than carried by the incremental merge.
    """

    summary: str = ""
    anchors: Anchors = _NO_ANCHORS


@dataclass(frozen=True, slots=True)
class CompactionPlan:
    """What a compaction is about to do, decided without any I/O.

    ``pinned + tail`` is the conversation that survives verbatim;
    ``head`` is what a summary will stand in for. The invariant worth
    knowing is that ``needs_summary`` is exactly ``bool(head)``: there is
    no tier that summarizes nothing and no tier that drops the head
    silently — except :attr:`~omicsclaw.context.budget.Pressure.
    EMERGENCY`, which has already thrown away what it is going to throw
    away by the time this plan exists, and whose ``tail`` is therefore
    shorter than the input rather than a suffix boundary.
    """

    pressure: Pressure
    pinned: tuple[Message, ...]
    head: tuple[Message, ...]
    tail: tuple[Message, ...]
    needs_summary: bool


def plan_compaction(
    messages: Sequence[Message],
    budget: ContextBudget,
    *,
    pinned: int = 0,
    min_tail: int,
    counter: TokenCounter | None = None,
    floor: Pressure = Pressure.NONE,
) -> CompactionPlan:
    """Grade the conversation and decide the cut. Pure, synchronous.

    *floor* is the least severe tier the conversation is treated as,
    whatever it measures — ``Pressure.FULL`` forces a full summary.

    *pinned* is how many leading messages are protected. **It defaults
    to zero, which asserts nothing about the input** — the alternative
    default, ``1``, would assert that message zero is a system prompt,
    which is the harness's precondition and not this project's (its
    engine injects nothing). The price of the safe default is real: a
    caller who forgets ``pinned=1`` will find its system prompt in the
    compactible head. Two things soften it. The output of
    :func:`~omicsclaw.context.prompt.assemble` always begins with
    exactly one system message, so the correct call after assembling is::

        plan_compaction(assembled, budget, pinned=1, min_tail=6)

    and :attr:`CompactionRecord.advisories` says so out loud when it
    sees ``pinned=0`` in front of a system message — stating the fact
    without changing the behaviour, which is this layer's division of
    labour with its callers throughout. It is an advisory and not a
    :attr:`~CompactionRecord.degraded` reason because a compaction that
    did exactly what it was asked to is not a failed one; see that
    field for what conflating the two cost.
    """
    pressure = _more_severe(
        budget.pressure(estimate_messages_tokens(messages, counter=counter)), floor
    )
    kept, head, tail = split_head_tail(messages, pinned=pinned, min_tail=min_tail)
    rest = (*head, *tail)

    if not rest or pressure in (Pressure.NONE, Pressure.WARN):
        return CompactionPlan(pressure, kept, (), rest, False)

    if pressure is Pressure.EMERGENCY:
        survivors = _emergency_survivors(
            kept, rest, budget, counter, _emergency_target(budget)
        )
        return CompactionPlan(pressure, kept, (), survivors, False)

    if pressure is Pressure.SOFT:
        # Half the head goes, half stays in the model's own words: the
        # harness's compromise between compression and continuity
        # (``progressive_compactor.go:266-301``).
        middle = len(head) // 2
        oldest = head[:middle]
        tail_after = (*head[middle:], *tail)
        return CompactionPlan(pressure, kept, oldest, tail_after, bool(oldest))

    return CompactionPlan(pressure, kept, head, tail, bool(head))


def apply_compaction(
    plan: CompactionPlan,
    *,
    summary: str,
    anchors: Anchors,
    references: Sequence[OffloadEntry] = (),
) -> tuple[Message, ...]:
    """Turn a plan and a summary into the new conversation. Synchronous.

    Tool pairs are repaired on the paths that removed messages, and only
    there. A pass-through that ran the repair would not be a
    pass-through: it would rebuild a malformed history into a different
    one, and the low-pressure tiers have to be byte-identical to their
    input or every quiet turn costs a prompt-cache re-warm.
    """
    if plan.needs_summary:
        message = build_compaction_message(anchors, summary, references)
        held = _answers_owed_by(plan.pinned, plan.tail)
        return repair_tool_pairs(
            (*plan.pinned, *plan.tail[:held], message, *plan.tail[held:])
        )
    if plan.pressure is Pressure.EMERGENCY:
        return repair_tool_pairs((*plan.pinned, *plan.tail))
    return (*plan.pinned, *plan.tail)


def _answers_owed_by(
    pinned: tuple[Message, ...],
    tail: tuple[Message, ...],
) -> int:
    """How many leading *tail* messages must stay in front of the summary.

    The pinned prefix may end mid-exchange: its last assistant turn
    asked for tools and the results answering it are the first thing in
    the tail. Dropping the summary message between the two is a
    conversation :func:`~omicsclaw.context.transcript.repair_tool_pairs`
    will then have to repair by *deleting* those results and answering
    with placeholders — legal, and a needless loss of exactly the
    messages ``pinned`` was supposed to protect. Letting them past the
    summary first costs one slice and keeps them.

    The question is asked the same way
    :func:`~omicsclaw.context.transcript.repair_tool_pairs` asks it —
    walk back over the contiguous run of tool results at the end of the
    prefix, and the turn in front of that run is the only one that can
    still be owed anything. Asking instead whether an id appears
    *anywhere* in ``pinned`` gets a prefix whose tool result precedes
    its own call wrong, which is the same membership-versus-adjacency
    confusion, one function along.
    """
    run_start = len(pinned)
    while run_start and pinned[run_start - 1].role == Role.TOOL:
        run_start -= 1
    if run_start == 0:
        return 0
    caller = pinned[run_start - 1]
    if caller.role != Role.ASSISTANT or not caller.tool_calls:
        return 0
    owed = {call.id for call in caller.tool_calls}
    owed -= {message.tool_call_id for message in pinned[run_start:]}
    if not owed:
        return 0
    index = 0
    while (
        index < len(tail)
        and tail[index].role == Role.TOOL
        and tail[index].tool_call_id in owed
    ):
        index += 1
    return index


def build_summary_prompt(
    plan: CompactionPlan,
    state: CompactionState,
) -> tuple[str, str]:
    """``(system, user)`` for the summarizer. ``:386-415``.

    A non-empty ``state.summary`` switches to the incremental template,
    which hands the model the previous compaction and asks it to merge
    rather than to summarize a summary; an earlier compaction message in
    the head is then left out of the rendered conversation. The first
    template gains :data:`~omicsclaw.context.summary.OFFLOAD_RULE` when
    the conversation contains an offload placeholder.
    """
    head = plan.head
    if state.summary:
        # The previous compaction reaches the model as <previous-compaction>;
        # rendering its message again would hand the model the same text twice.
        head = tuple(m for m in head if not is_summary_message(m))
    conversation = render_for_summary(head)
    if not state.summary:
        template = FIRST_TEMPLATE
        if OFFLOAD_MARKER in conversation:
            template = template.replace(
                "\n\nConversation:\n", f"\n{OFFLOAD_RULE}\n\nConversation:\n", 1
            )
        return SUMMARY_SYSTEM_PROMPT, template.format(conversation=conversation)
    previous = state.summary
    if state.anchors != _NO_ANCHORS:
        previous = f"{state.anchors.render()}\n\n## Summary\n{state.summary}"
    return SUMMARY_SYSTEM_PROMPT, INCREMENTAL_TEMPLATE.format(
        previous=previous, conversation=conversation
    )


def collect_references(messages: Sequence[Message]) -> tuple[OffloadEntry, ...]:
    """Every offload reference *messages* carries, oldest first.

    Read from offload placeholders and from the reference block of any
    earlier compaction message, deduplicated by reference, and limited to
    the newest :data:`~omicsclaw.context.offload.MAX_REFERENCES`.
    """
    found: dict[str, OffloadEntry] = {}
    for message in messages:
        if is_summary_message(message):
            entries = parse_references(message.content)
        else:
            entry = parse_placeholder(message)
            entries = (entry,) if entry is not None else ()
        for entry in entries:
            found.pop(entry.reference, None)
            found[entry.reference] = entry
    return tuple(found.values())[-MAX_REFERENCES:]


@dataclass(frozen=True, slots=True)
class CompactionRecord:
    """What one compaction did, as a value somebody else may persist.

    Every field is JSON-able. Identity, session and time are not here:
    whoever persists a record adds them.

    Both token counts are carried because the pressure that *triggered*
    a compaction is the one from before it, and a record that reported
    only the flattened figure would explain nothing about why the
    compaction happened.
    """

    pressure: Pressure
    """The tier that was applied: measured after any offloading, and
    raised to the caller's floor."""

    tokens_before: int
    tokens_after: int
    msgs_before: int
    msgs_after: int
    summarized: int
    """Messages a summary stood in for. Zero on every degraded path."""

    preserved_tail: int
    """Original messages carried through verbatim after the pinned prefix.

    Counted by identity against the input, so the placeholders
    :func:`~omicsclaw.context.transcript.repair_tool_pairs` inserts and
    the compaction message itself are excluded — "carried through
    verbatim" is the claim, and a count that included messages this
    package invented would not be making it.
    """

    anchors: Anchors = _NO_ANCHORS
    summary_text: str = ""
    degraded: str = ""
    """Empty when the compaction took its intended path.

    Non-empty is the only trace a *failure* leaves, so it carries every
    failure reason, joined by ``"; "``.

    **It does not carry advisories** — see :attr:`advisories`, which
    used to share this field. That is what makes this one readable as a
    gate. Plan 0030 §11.A's seam table has step 6 porting
    ``internal/engine/history.go:120-122`` — *do not write a compaction
    back when it recorded an error, unless the tier was*
    ``EMERGENCY`` — and while a merely advisory note lived here, that
    port refused to write back compactions that had worked perfectly.
    The trigger was the everyday mistake ``plan_compaction`` itself
    warns about, a caller who forgot ``pinned=1``, and the symptom was
    issue #117's: re-compacting from scratch every turn and paying for
    one more summarization each time.

    **Still not a gate on its own**: :data:`_EMERGENCY_REASON` is
    written whenever the emergency tier ran, whether or not anything
    went wrong, exactly as ``progressive_compactor.go:341-352`` does.
    Any consumer reading this field has to carve ``EMERGENCY`` out the
    way the Go does.
    """

    advisories: tuple[str, ...] = ()
    """Facts about how this compaction was *called*. Never failures.

    ``pinned=0`` in front of a system prompt, or a plan with nothing to
    compact: true, worth saying, and not a reason to distrust the
    result. Kept as a tuple rather than joined because the one thing
    they must not become is another string somebody tests for emptiness.
    """

    duration_s: float = 0.0
    """Wall time this compaction took, from :func:`time.monotonic`.

    Almost all of it is the summarizer's ``await``, which is why it is
    the one number here worth watching: a compaction that starts costing
    seconds is a summarization model that is being asked for too much.
    """

    trigger: Pressure = Pressure.NONE
    """The tier measured on arrival, before offloading. Equals
    :attr:`pressure` unless offloading lowered it or a floor raised it."""

    offloaded: tuple[OffloadEntry, ...] = ()
    """Tool results this compaction moved out of the conversation."""

    forced: bool = False
    """The caller asked for a compaction regardless of pressure."""

    written_back: bool = False
    """Whether the caller kept the result as its history.

    :func:`compact` never sets it; a caller that decides, such as
    :class:`~omicsclaw.context.progressive.ProgressiveCompactor`, records
    its decision here.
    """

    @property
    def compression_ratio(self) -> float:
        """``tokens_after / tokens_before``; zero when there was nothing."""
        if self.tokens_before <= 0:
            return 0.0
        return self.tokens_after / self.tokens_before


def _advisories(
    messages: Sequence[Message],
    plan: CompactionPlan,
    pinned: int,
    min_tail: int,
) -> list[str]:
    """Facts about this call worth recording, none of them errors.

    The second note is computed from ``pinned`` and ``min_tail`` rather
    than from ``plan.head``, because those are not the same question.
    Under :attr:`~omicsclaw.context.budget.Pressure.SOFT` the plan's
    head is half of the compactible head, so a conversation with exactly
    one compactible message has ``plan.head == ()`` while the pinned
    prefix and ``min_tail`` plainly do **not** cover it. Reading
    emptiness off the plan wrote a false sentence into the record — and
    a test that only asks whether the sentence is present cannot tell.
    """
    notes: list[str] = []
    if pinned == 0 and messages and messages[0].role == Role.SYSTEM:
        notes.append(
            "pinned=0 while message 0 is a system prompt, so it was "
            "treated as compactible history"
        )
    if plan.pressure in (Pressure.SOFT, Pressure.FULL):
        if len(messages) - pinned <= min_tail:
            notes.append(
                "nothing to compact: the pinned prefix and min_tail cover "
                "the whole conversation"
            )
        elif not plan.head:
            notes.append(
                "nothing to summarize: the soft tier compacts the older "
                "half of the head, and the head is a single message"
            )
    return notes


def _fallback_target(budget: ContextBudget, pressure: Pressure) -> int:
    """Token ceiling a degraded compaction has to get under.

    One tier below the one that triggered, read off the budget the
    caller supplied — see :data:`_FALLBACK_TARGETS`. The ``usable_tokens``
    default is for a tier that cannot reach here today; it is the value
    that changes nothing, so a future caller who does route another tier
    through the fallback gets the old no-op rather than a number this
    function invented for it.
    """
    field = _FALLBACK_TARGETS.get(pressure)
    if field is None:
        return budget.usable_tokens
    return int(budget.usable_tokens * getattr(budget, field))


async def compact(
    messages: Sequence[Message],
    budget: ContextBudget,
    *,
    summarizer: Summarizer | None = None,
    state: CompactionState = CompactionState(),
    pinned: int = 0,
    min_tail: int = DEFAULT_MIN_TAIL,
    counter: TokenCounter | None = None,
    offloader: Offloader | None = None,
    extractor: MemoryExtractor | None = None,
    floor: Pressure = Pressure.NONE,
) -> tuple[tuple[Message, ...], CompactionRecord, CompactionState]:
    """Offload, grade, summarize if it is worth it, and report.

    Returns the compacted conversation, the record of what happened, and
    the state to hand to the next compaction.

    With an *offloader*, oversized tool results in the compactible head
    are moved out first at every tier above ``NONE``; the conversation is
    then graded again and the tier it is now in is applied. At EMERGENCY
    the recent tail is offloaded as well before anything is dropped, and
    the truncation keeps the FULL threshold's worth of tokens so the next
    compaction can summarize. *floor* is the
    least severe tier to apply whatever the measurement says —
    ``Pressure.FULL`` forces a summary of the whole head.

    **Summarization never raises out of here.** A summarizer that is
    absent, that fails, or that returns nothing usable falls back to
    :func:`~omicsclaw.context.transcript.fit_to_budget` trimmed to one
    declared tier below the applied one, and the reason goes into
    :attr:`CompactionRecord.degraded`. So does a result that came out
    larger than ``budget.usable_tokens``, whatever produced it. On SOFT
    and FULL the *extractor*, when given, reads the summarized messages
    as they were before offloading, concurrently with the summarizer; a
    failure there, or in the store, is recorded in
    :attr:`CompactionRecord.advisories` and changes nothing else.

    :exc:`asyncio.CancelledError` propagates untouched. No timeout is
    imposed on the summarizer or the store: a summarizer that never
    returns makes this never return, so bound it inside the summarizer.
    """
    started = monotonic()
    original = tuple(messages)
    tokens_before = estimate_messages_tokens(original, counter=counter)
    trigger = _more_severe(budget.pressure(tokens_before), floor)
    notes: list[str] = []
    working = original
    offloaded: tuple[OffloadEntry, ...] = ()
    if offloader is not None and trigger is not Pressure.NONE:
        _, head, _ = split_head_tail(original, pinned=pinned, min_tail=min_tail)
        working, offloaded, failures = await _offload_span(
            working, pinned, pinned + len(head), offloader, counter
        )
        notes.extend(failures)

    plan = plan_compaction(
        working, budget, pinned=pinned, min_tail=min_tail, counter=counter, floor=floor
    )
    if offloader is not None and plan.pressure is Pressure.EMERGENCY:
        # Truncation drops whole messages; a large recent tool result kept
        # as a placeholder survives it with its full text on disk.
        working, more, failures = await _offload_span(
            working, pinned, len(working), offloader, counter
        )
        notes.extend(failures)
        if more:
            offloaded = (*offloaded, *more)
            plan = plan_compaction(
                working,
                budget,
                pinned=pinned,
                min_tail=min_tail,
                counter=counter,
                floor=floor,
            )
    if plan.pressure is not trigger:
        notes.append(
            f"offloading lowered the pressure from {trigger} to {plan.pressure}"
        )
    notes.extend(_advisories(working, plan, pinned, min_tail))
    reasons: list[str] = []
    anchors = state.anchors
    summary_text = ""
    summarized = 0
    new_state = state

    def fall_back(reason: str) -> tuple[Message, ...]:
        reasons.append(reason)
        return fit_to_budget(
            working,
            budget,
            pinned=pinned,
            min_tail=min_tail,
            counter=counter,
            target_tokens=_fallback_target(budget, plan.pressure),
        )

    if plan.pressure is Pressure.EMERGENCY:
        # Never spends an LLM round trip: the tier exists because there
        # is no room left to spend one in.
        result = apply_compaction(plan, summary="", anchors=anchors)
        reasons.append(_EMERGENCY_REASON)
    elif not plan.needs_summary:
        result = apply_compaction(plan, summary="", anchors=anchors)
    elif summarizer is None:
        result = fall_back("no summarizer was supplied")
    else:
        system, user = build_summary_prompt(plan, state)
        # SOFT and FULL both cut their head from index ``pinned``, and
        # offloading replaced messages one for one, so this slice of the
        # input is the summarized head as it was before offloading.
        before_offload = original[pinned : pinned + len(plan.head)]
        written, failure, extraction_error = await _summarize_and_extract(
            summarizer, system, user, extractor, before_offload
        )
        if extraction_error is not None:
            notes.append(f"the memory extractor raised {extraction_error!r}")
        if failure is not None:
            result = fall_back(f"the summarizer raised {failure!r}")
        else:
            parsed, summary_text = parse_anchors_and_summary(written)
            if not summary_text and parsed == _NO_ANCHORS:
                # Structurally empty, which is this layer's equivalent of
                # the harness's ``resp == nil`` check — not a judgement
                # about the summary's quality, which nothing here makes.
                reason = "the summarizer returned neither anchors nor a summary"
                result = fall_back(reason)
            else:
                anchors = state.anchors.merge(parsed)
                summarized = len(plan.head)
                result = apply_compaction(
                    plan,
                    summary=summary_text,
                    anchors=anchors,
                    references=collect_references(plan.head),
                )
                new_state = CompactionState(summary=summary_text, anchors=anchors)

    usable = budget.usable_tokens
    tokens_after = estimate_messages_tokens(result, counter=counter)
    if tokens_after > usable:
        if plan.pressure is not Pressure.EMERGENCY:
            result = fall_back(
                f"the compacted conversation came out at {tokens_after} "
                f"tokens against a usable budget of {usable}"
            )
            anchors = state.anchors
            summary_text = ""
            summarized = 0
            new_state = state
            tokens_after = estimate_messages_tokens(result, counter=counter)
        if tokens_after > usable:
            reasons.append(_STILL_OVER_REASON)

    originals = {id(message) for message in original}
    record = CompactionRecord(
        pressure=plan.pressure,
        tokens_before=tokens_before,
        tokens_after=tokens_after,
        msgs_before=len(original),
        msgs_after=len(result),
        summarized=summarized,
        preserved_tail=sum(1 for m in result[pinned:] if id(m) in originals),
        anchors=anchors,
        summary_text=summary_text,
        degraded="; ".join(reasons),
        advisories=tuple(notes),
        duration_s=monotonic() - started,
        trigger=trigger,
        offloaded=offloaded,
        forced=floor is not Pressure.NONE,
    )
    return result, record, new_state


async def _summarize_and_extract(
    summarizer: Summarizer,
    system: str,
    user: str,
    extractor: MemoryExtractor | None,
    head: Sequence[Message],
) -> tuple[str, Exception | None, Exception | None]:
    """Run the summarizer and the extractor side by side.

    Returns ``(summary, summarizer_error, extractor_error)``; each error
    is ``None`` when that call succeeded. Anything that is not an
    :class:`Exception` — a cancellation — is re-raised.
    """
    calls = [summarizer.summarize(user, system=system)]
    if extractor is not None:
        calls.append(extractor.extract(tuple(head)))
    outcomes = await asyncio.gather(*calls, return_exceptions=True)
    for outcome in outcomes:
        if isinstance(outcome, BaseException) and not isinstance(outcome, Exception):
            raise outcome
    written = outcomes[0]
    failure = written if isinstance(written, Exception) else None
    extraction_error = None
    if len(outcomes) > 1 and isinstance(outcomes[1], Exception):
        extraction_error = outcomes[1]
    return ("" if failure is not None else written), failure, extraction_error
