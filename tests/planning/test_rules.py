"""The two rules: what a write may claim, and what it may quietly drop."""

from __future__ import annotations

import pytest

from omicsclaw.planning import (
    MAX_DIRECT_COMPLETIONS,
    PlanItem,
    PlanRefused,
    PlanStatus,
    apply,
    merge,
    validate,
)

P, R, C, X = (
    PlanStatus.PENDING,
    PlanStatus.IN_PROGRESS,
    PlanStatus.COMPLETED,
    PlanStatus.CANCELLED,
)


def item(identifier: str, status: PlanStatus, content: str = "step") -> PlanItem:
    return PlanItem(identifier, content, status)


# ---- validate: the anti-cheat rule ---------------------------------------


def test_one_direct_completion_is_the_honest_case_and_is_allowed():
    """A model that really did finish a step in one turn is not lying."""
    validate((), (item("1", C),))


def test_two_direct_completions_in_one_call_are_refused():
    """The quantity is the signal — nine at once is what this exists for."""
    with pytest.raises(PlanRefused) as caught:
        validate((), (item("1", C), item("2", C)))

    assert "2 plan items" in str(caught.value)


def test_the_threshold_is_one_and_the_test_reads_it_from_the_constant():
    """Raising the constant without raising the rule would be a silent hole."""
    proposed = tuple(item(str(n), C) for n in range(MAX_DIRECT_COMPLETIONS + 1))

    with pytest.raises(PlanRefused):
        validate((), proposed)

    validate((), proposed[:MAX_DIRECT_COMPLETIONS])


def test_completing_work_that_was_claimed_first_is_never_counted():
    """``in_progress → completed`` is the path the rule wants to encourage."""
    previous = tuple(item(str(n), R) for n in range(5))
    proposed = tuple(item(str(n), C) for n in range(5))

    validate(previous, proposed)


def test_re_stating_a_completed_item_is_not_a_new_completion():
    previous = (item("1", C), item("2", C), item("3", C))

    validate(previous, previous)


def test_a_cancelled_item_cannot_be_completed_however_few_there_are():
    """No count governs this path: reviving an abandoned step is a decision."""
    with pytest.raises(PlanRefused) as caught:
        validate((item("1", X),), (item("1", C),))

    assert "cancelled" in str(caught.value)
    assert "pending or in_progress" in str(caught.value)


def test_a_cancelled_item_may_be_restored_and_then_completed():
    """The refusal names a path, and the path has to exist."""
    validate((item("1", X),), (item("1", R),))
    validate((item("1", R),), (item("1", C),))


def test_non_completed_statuses_are_never_examined():
    """Only a claim of progress is checked; the rest is the model's business."""
    validate((), tuple(item(str(n), P) for n in range(20)))
    validate((), tuple(item(str(n), R) for n in range(20)))
    validate((), tuple(item(str(n), X) for n in range(20)))


# ---- merge: preserving started work --------------------------------------


def test_an_omitted_completed_item_is_kept():
    """Losing it loses the history of what was done."""
    previous = (item("1", C), item("2", P))

    merged = merge(previous, (item("2", R),))

    assert [(i.id, i.status) for i in merged] == [("1", C), ("2", R)]


def test_an_omitted_in_progress_item_is_kept():
    """Losing it loses the task currently being worked on."""
    merged = merge((item("1", R),), (item("2", P),))

    assert [i.id for i in merged] == ["1", "2"]


def test_an_omitted_pending_item_is_dropped():
    """Trimming steps that never began is editing a model should be able to do."""
    merged = merge((item("1", P), item("2", P)), (item("2", R),))

    assert [i.id for i in merged] == ["2"]


def test_an_omitted_cancelled_item_is_dropped():
    merged = merge((item("1", X),), (item("2", P),))

    assert [i.id for i in merged] == ["2"]


def test_a_named_item_is_replaced_wherever_it_moved_to():
    merged = merge((item("1", R, "old"),), (item("1", C, "new"),))

    assert merged == (item("1", C, "new"),)


def test_order_is_first_written_order_with_new_items_appended():
    """A list that reshuffles between turns reads to the model as a new plan."""
    previous = (item("a", R), item("b", R), item("c", R))

    merged = merge(previous, (item("c", C), item("d", P), item("a", C)))

    assert [i.id for i in merged] == ["a", "b", "c", "d"]


def test_a_duplicate_id_inside_one_write_keeps_the_first():
    merged = merge((), (item("1", P, "first"), item("1", C, "second")))

    assert merged == (item("1", P, "first"),)


def test_merge_never_drops_a_submitted_item():
    submitted = (item("1", P), item("2", R), item("3", C), item("4", X))

    merged = merge((), submitted)

    assert merged == submitted


# ---- apply: the order of the two -----------------------------------------


def test_apply_validates_before_merging():
    """Merging first would hand validate carried items it never examined."""
    with pytest.raises(PlanRefused):
        apply((item("1", X),), (item("1", C),))


def test_apply_returns_the_merged_plan_when_the_write_is_accepted():
    result = apply((item("1", C),), (item("2", R),))

    assert [i.id for i in result] == ["1", "2"]


def test_a_refused_write_is_refused_whole():
    """Partial acceptance would record some of a batch of false completions."""
    previous = (item("keep", R),)

    with pytest.raises(PlanRefused):
        apply(previous, (item("a", C), item("b", C), item("keep", C)))


def test_carried_items_do_not_re_enter_validation():
    """A completed item kept by merge must not count as a new completion.

    Otherwise a plan would accumulate a debt of re-validation it can never
    pay: every later write would be refused because of history.
    """
    previous = tuple(item(str(n), C) for n in range(10))

    apply(previous, (item("new", C),))


# ---- the two rules read the same view of a write --------------------------


def test_one_item_sent_twice_is_one_completion_not_two():
    """A resend is not a second claim.

    ``validate`` counted the raw sequence while ``merge`` deduplicated, so
    the same finished item sent twice was refused for completing "2 plan
    items" that ``merge`` would have collapsed into one — a rule
    penalising a no-op resend.
    """
    duplicated = (item("a", C), item("a", C))

    validate((), duplicated)

    assert apply((), duplicated) == (item("a", C),)


def test_a_duplicate_does_not_buy_a_second_completion_either():
    """Deduplicating must not become a way to smuggle one through.

    Two *distinct* ids are still two direct completions, and sending one
    of them twice does not change that.
    """
    with pytest.raises(PlanRefused):
        validate((), (item("a", C), item("a", C), item("b", C)))


def test_validate_and_merge_agree_on_which_item_a_duplicate_id_means():
    """``merge`` keeps the first; ``validate`` must judge the first too.

    Otherwise ``[(a, pending), (a, completed)]`` is validated as a
    completion and stored as a pending item, or the reverse.
    """
    proposed = (item("a", P), item("a", C))

    validate((item("a", X),), proposed)

    assert apply((item("a", X),), proposed) == (item("a", P),)


def test_the_cancelled_refusal_survives_deduplication():
    with pytest.raises(PlanRefused):
        validate((item("a", X),), (item("a", C), item("a", C)))
