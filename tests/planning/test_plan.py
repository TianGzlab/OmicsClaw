"""``PlanStore``: atomic replacement, immutable reads, and the write sink."""

from __future__ import annotations

import threading

import pytest

from omicsclaw.planning import PlanItem, PlanStatus, PlanStore


def _items(*specs: tuple[str, str, PlanStatus]) -> tuple[PlanItem, ...]:
    return tuple(PlanItem(i, c, s) for i, c, s in specs)


def test_a_new_store_is_empty():
    store = PlanStore()

    assert store.read() == ()
    assert store.is_empty
    assert store.active_count() == (0, 0)


def test_write_replaces_everything_rather_than_patching():
    store = PlanStore()
    store.write(_items(("1", "first", PlanStatus.PENDING)))

    store.write(_items(("2", "second", PlanStatus.PENDING)))

    assert [item.id for item in store.read()] == ["2"]


def test_write_returns_what_it_stored():
    """The caller reports the return value, never a second read.

    A read afterwards could observe a later write from another session's
    task, and the tool would report a plan its own call did not produce.
    """
    store = PlanStore()

    returned = store.write(_items(("1", "first", PlanStatus.PENDING)))

    assert returned == store.read()


def test_the_caller_s_list_is_not_the_store_s():
    """Mutating the sequence that was written must not reach the store."""
    store = PlanStore()
    written = [PlanItem("1", "first", PlanStatus.PENDING)]

    store.write(written)
    written.append(PlanItem("2", "second", PlanStatus.PENDING))

    assert len(store.read()) == 1


def test_a_read_cannot_be_mutated_into_the_store():
    """No defensive copy is made, so the type has to be the guarantee."""
    store = PlanStore()
    store.write(_items(("1", "first", PlanStatus.PENDING)))

    snapshot = store.read()

    assert isinstance(snapshot, tuple)
    with pytest.raises((AttributeError, TypeError)):
        # type: ignore[attr-defined]
        snapshot.append(PlanItem("2", "x", PlanStatus.PENDING))
    with pytest.raises(AttributeError):
        snapshot[0].status = PlanStatus.COMPLETED  # type: ignore[misc]


def test_active_count_separates_outstanding_from_total():
    store = PlanStore()
    store.write(
        _items(
            ("1", "a", PlanStatus.PENDING),
            ("2", "b", PlanStatus.IN_PROGRESS),
            ("3", "c", PlanStatus.COMPLETED),
            ("4", "d", PlanStatus.CANCELLED),
        )
    )

    assert store.active_count() == (2, 4)


def test_is_empty_is_about_items_not_about_activity():
    """A finished plan is not an absent one — the gate depends on this.

    If ``is_empty`` meant "nothing outstanding", a session that completed
    its plan would start being nudged to write one again.
    """
    store = PlanStore()
    store.write(_items(("1", "a", PlanStatus.COMPLETED)))

    assert not store.is_empty
    assert store.active_count() == (0, 1)


def test_the_sink_sees_every_write_with_what_was_written():
    seen: list[tuple[PlanItem, ...]] = []
    store = PlanStore(on_write=lambda items: seen.append(tuple(items)))

    store.write(_items(("1", "a", PlanStatus.PENDING)))
    store.write(_items(("1", "a", PlanStatus.COMPLETED)))

    assert [item[0].status for item in seen] == [
        PlanStatus.PENDING,
        PlanStatus.COMPLETED,
    ]


def test_restore_does_not_fire_the_sink():
    """Reading a plan back must not write it out again.

    Without this, every resumed session pays a needless disk write, and a
    hand-edited archive is silently normalised under the operator.
    """
    seen: list[object] = []
    store = PlanStore(on_write=seen.append)

    store.restore(_items(("1", "a", PlanStatus.PENDING)))

    assert store.read() != ()
    assert seen == []


def test_a_raising_sink_reaches_the_caller():
    """Stated contract: this package cannot log, so it cannot swallow.

    The layer that binds a sink is the one that can report the failure,
    which is why the exception is not caught here.
    """

    def boom(items: object) -> None:
        raise OSError("disk full")

    store = PlanStore(on_write=boom)

    with pytest.raises(OSError):
        store.write(_items(("1", "a", PlanStatus.PENDING)))

    assert store.read() != (), "the write itself must still have landed"


def test_concurrent_writes_leave_one_whole_plan_not_a_mixture():
    """The lock's job: a reader never sees half of one write.

    Threads rather than tasks because a tool may run under
    ``asyncio.to_thread``, which is the case an ``asyncio.Lock`` would
    not protect at all.
    """
    store = PlanStore()
    start = threading.Barrier(4)
    plans = [
        tuple(PlanItem(f"{n}-{i}", "x", PlanStatus.PENDING) for i in range(50))
        for n in range(4)
    ]
    observed: list[tuple[PlanItem, ...]] = []

    def writer(plan: tuple[PlanItem, ...]) -> None:
        start.wait()
        for _ in range(100):
            store.write(plan)
            observed.append(store.read())

    threads = [threading.Thread(target=writer, args=(plan,)) for plan in plans]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert observed
    for snapshot in observed:
        prefixes = {item.id.split("-")[0] for item in snapshot}
        assert len(prefixes) == 1, f"a read saw two writes mixed: {prefixes}"


def test_plan_status_values_are_the_wire_strings():
    """They are persisted and put in a tool schema; renaming one is a break."""
    assert [status.value for status in PlanStatus] == [
        "pending",
        "in_progress",
        "completed",
        "cancelled",
    ]


def test_is_active_is_exactly_pending_and_in_progress():
    assert PlanItem("1", "a", PlanStatus.PENDING).is_active
    assert PlanItem("1", "a", PlanStatus.IN_PROGRESS).is_active
    assert not PlanItem("1", "a", PlanStatus.COMPLETED).is_active
    assert not PlanItem("1", "a", PlanStatus.CANCELLED).is_active


def test_a_new_item_defaults_to_pending():
    assert PlanItem("1", "a").status is PlanStatus.PENDING
