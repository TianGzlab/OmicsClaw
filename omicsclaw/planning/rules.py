"""What a plan write is allowed to claim, and what it may quietly drop.

Plan 0039 §2.5. The reference harness keeps both of these inside its
``plan_write`` tool and says outright that its store does not validate
(``plan.go:14``, ``plan_write.go:8-13``). They are here instead,
because they are rules about *plan state transitions* rather than about
tool plumbing: a second write path — a slash command, a Desktop plan
panel — must not be able to reach the store without them, and a rule
that can only be tested through a JSON payload is a rule tested at one
remove from what it says.

Two rules, and they guard opposite failures:

:func:`validate` stops a model claiming work it did not do.
:func:`merge` stops a model losing work it *did* do by omitting it.
"""

from __future__ import annotations

from typing import Sequence

from .plan import PlanItem, PlanStatus

__all__ = ["MAX_DIRECT_COMPLETIONS", "PlanRefused", "apply", "merge", "validate"]


MAX_DIRECT_COMPLETIONS = 1
"""How many items one write may mark ``completed`` without having first
marked them ``in_progress``.

**One, and not zero, and the difference is the whole design.** Zero would
refuse the ordinary case: a model that really did finish a step in the
same turn it wrote it down has nothing to lie about, and forcing it
through a wasted round trip to say ``in_progress`` first teaches it that
the plan tool is an obstacle. One refuses what the reference harness
built this check for: a single call that marked nine of eleven items
completed, with no work behind any of them (``plan_write.go:12-13``).

The quantity is the signal. Finishing one thing per turn is what doing
the work looks like; finishing nine is what describing the work looks
like.
"""


class PlanRefused(ValueError):
    """A write that would have recorded progress that did not happen.

    A :exc:`ValueError` rather than a bespoke hierarchy, because the one
    caller that matters —
    :func:`~omicsclaw.planning.tool.plan_write_tool` — re-raises it as a
    :exc:`~omicsclaw.tools.function_tool.ToolArgumentError`, and the
    model reads the message and corrects the call. The refusal is
    self-healing by design: it costs a turn, never the run.
    """


def _first_by_id(proposed: Sequence[PlanItem]) -> dict[str, PlanItem]:
    """The items a write really consists of, keyed by id, first one winning.

    **Both rules read this rather than the raw sequence**, and that is a
    repair rather than a tidy-up. They used to disagree: :func:`merge`
    deduplicated while :func:`validate` counted, so a model that sent one
    finished item *twice* — the same id, the same status, a resend rather
    than two claims — was refused for completing "2 plan items" that
    :func:`merge` would have collapsed into one. A rule that penalises a
    no-op resend teaches the model to avoid the tool.

    The first occurrence wins because the model contradicted itself
    inside one call and there is no evidence for preferring either; the
    first at least makes the outcome a function of what was sent rather
    than of dictionary insertion order. Insertion order is preserved, so
    a caller iterating the values sees the submission order.
    """
    incoming: dict[str, PlanItem] = {}
    for item in proposed:
        incoming.setdefault(item.id, item)
    return incoming


def validate(
    previous: Sequence[PlanItem],
    proposed: Sequence[PlanItem],
) -> None:
    """Check *proposed* against the history in *previous*.

    :raises PlanRefused: a ``cancelled`` item was marked ``completed``,
        or more than :data:`MAX_DIRECT_COMPLETIONS` items were marked
        ``completed`` without having been ``in_progress`` first.

    Only items *this* write names are checked, and each id is counted
    **once** however many times it was sent — the same view of the write
    :func:`merge` takes, through :func:`_first_by_id`. Items :func:`merge`
    carries forward untouched are not re-examined either, which is what
    stops a plan accumulating a debt of re-validation it can never pay —
    and is safe precisely because they are carried forward *unchanged*.

    The two refusals are asymmetric on purpose. A count governs the
    pending path because finishing one real thing per call is legitimate;
    no count governs the cancelled path, because reviving an abandoned
    step is a decision, and a decision that is worth making is worth
    writing down as ``pending`` first.
    """
    before = {item.id: item.status for item in previous}
    direct = 0
    for item in _first_by_id(proposed).values():
        if item.status is not PlanStatus.COMPLETED:
            continue
        prior = before.get(item.id)
        if prior is PlanStatus.CANCELLED:
            raise PlanRefused(
                f"plan item {item.id!r} was cancelled and cannot be marked "
                "completed directly — restore it to pending or in_progress "
                "first, so that reviving it is a step you took rather than "
                "one that happened"
            )
        if prior is None or prior is PlanStatus.PENDING:
            direct += 1
    if direct > MAX_DIRECT_COMPLETIONS:
        raise PlanRefused(
            f"{direct} plan items were marked completed in one call without "
            "having been in_progress. Mark one item in_progress, do that "
            "work, then mark it completed — one item per call. If these "
            "really are finished, report them one call at a time."
        )


def merge(
    previous: Sequence[PlanItem],
    proposed: Sequence[PlanItem],
) -> tuple[PlanItem, ...]:
    """Fold *proposed* into *previous*, keeping what was already started.

    The model is free to send only the items it is still thinking about.
    Treating that as a literal replacement is what the reference harness
    found costs real state (``plan_write.go:187-198``): an omitted
    ``completed`` item loses the history, and an omitted ``in_progress``
    item loses *the task currently being worked on*, taking the progress
    count down with it.

    So the rule is by prior status, not by presence:

    - named in *proposed* → the new version wins, wherever it moved to;
    - absent and ``in_progress`` or ``completed`` → carried forward,
      because started work is a fact and facts do not disappear by being
      left out;
    - absent and ``pending`` or ``cancelled`` → dropped, because trimming
      steps that were never begun is exactly the editing a model should
      be able to do in one write.

    **Order is the order items were first written**, with genuinely new
    ones appended. Stability is not cosmetic: the injected block is read
    by the model every turn, and a list that reshuffles itself between
    turns reads as a different plan.

    A duplicate id within *proposed* keeps the first occurrence — see
    :func:`_first_by_id`.
    """
    incoming = _first_by_id(proposed)

    merged: list[PlanItem] = []
    taken: set[str] = set()
    for item in previous:
        replacement = incoming.get(item.id)
        if replacement is not None:
            merged.append(replacement)
            taken.add(item.id)
        elif item.status in (PlanStatus.IN_PROGRESS, PlanStatus.COMPLETED):
            merged.append(item)
    for identifier, item in incoming.items():
        if identifier not in taken:
            merged.append(item)
    return tuple(merged)


def apply(
    previous: Sequence[PlanItem],
    proposed: Sequence[PlanItem],
) -> tuple[PlanItem, ...]:
    """Validate, then merge. What a write path should call.

    :raises PlanRefused: as :func:`validate`.

    Offered as one function so that no caller can accidentally do the
    second without the first — the order is the whole point, since
    merging first would hand :func:`validate` a list containing carried
    items it never examined and would invent violations out of history.
    """
    validate(previous, proposed)
    return merge(previous, proposed)
