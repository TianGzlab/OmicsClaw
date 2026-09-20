"""One plan per session in a process that serves many of them."""

from __future__ import annotations

from typing import Sequence

import pytest

from omicsclaw.planning import (
    FilePlanArchive,
    PlanArchiveError,
    PlanBook,
    PlanItem,
    PlanStatus,
)

P, R, C = PlanStatus.PENDING, PlanStatus.IN_PROGRESS, PlanStatus.COMPLETED


class _Recording:
    """An in-memory :class:`PlanArchive` that counts what it was asked."""

    def __init__(self) -> None:
        self.saves: list[tuple[str, tuple[PlanItem, ...]]] = []
        self.loads: list[str] = []
        self.stored: dict[str, tuple[PlanItem, ...]] = {}

    def load(self, session_id: str) -> tuple[PlanItem, ...]:
        self.loads.append(session_id)
        return self.stored.get(session_id, ())

    def save(self, session_id: str, items: Sequence[PlanItem]) -> None:
        self.saves.append((session_id, tuple(items)))
        self.stored[session_id] = tuple(items)


class _Broken:
    def load(self, session_id: str) -> tuple[PlanItem, ...]:
        raise PlanArchiveError("cannot read")

    def save(self, session_id: str, items: Sequence[PlanItem]) -> None:
        raise PlanArchiveError("cannot write")


def test_two_sessions_get_two_stores():
    book = PlanBook()

    book.for_session("a").write((PlanItem("1", "a's step", P),))

    assert book.for_session("b").read() == ()


def test_the_same_session_gets_the_same_store():
    book = PlanBook()

    assert book.for_session("a") is book.for_session("a")


def test_a_write_reaches_the_archive_at_once():
    """Write-through: the crash window is one file write, not one turn."""
    archive = _Recording()
    book = PlanBook(archive)

    book.for_session("a").write((PlanItem("1", "step", R),))

    assert [session for session, _ in archive.saves] == ["a"]


def test_a_second_process_reads_the_plan_back():
    archive = _Recording()
    PlanBook(archive).for_session("a").write((PlanItem("1", "step", R),))

    restored = PlanBook(archive).for_session("a").read()

    assert [(i.id, i.status) for i in restored] == [("1", R)]


def test_a_restore_does_not_write_the_archive_back_out():
    archive = _Recording()
    PlanBook(archive).for_session("a").write((PlanItem("1", "step", R),))
    before = len(archive.saves)

    PlanBook(archive).for_session("a")

    assert len(archive.saves) == before


def test_the_archive_is_read_once_per_session_not_per_call():
    archive = _Recording()
    book = PlanBook(archive)

    book.for_session("a")
    book.for_session("a")
    book.for_session("a")

    assert archive.loads == ["a"]


def test_an_anonymous_session_is_never_persisted():
    """Two unrelated anonymous runs would otherwise share one file.

    ``run_turn`` without a session has no identity to resume under, so
    each read would be the other run's plan.
    """
    archive = _Recording()
    book = PlanBook(archive)

    book.for_session("").write((PlanItem("1", "step", P),))

    assert archive.saves == []
    assert archive.loads == []


def test_an_anonymous_session_still_gets_a_working_store():
    book = PlanBook(_Recording())

    store = book.for_session("")
    store.write((PlanItem("1", "step", P),))

    assert [i.id for i in store.read()] == ["1"]


def test_without_a_sink_a_storage_failure_reaches_the_caller():
    book = PlanBook(_Broken())

    with pytest.raises(PlanArchiveError):
        book.for_session("a")


def test_a_bound_sink_turns_a_load_failure_into_a_report():
    """Fail-open: refusing to start an exchange over a stale file is worse."""
    seen: list[tuple[str, PlanArchiveError]] = []
    book = PlanBook(_Broken(), on_archive_error=lambda s, e: seen.append((s, e)))

    store = book.for_session("a")

    assert [session for session, _ in seen] == ["a"]
    assert store.read() == ()


def test_a_bound_sink_turns_a_save_failure_into_a_report():
    """The plan is in memory and correct; losing the turn would not help."""
    seen: list[tuple[str, PlanArchiveError]] = []
    book = PlanBook(_Broken(), on_archive_error=lambda s, e: seen.append((s, e)))
    store = book.for_session("a")
    seen.clear()

    store.write((PlanItem("1", "step", P),))

    assert len(seen) == 1
    assert [i.id for i in store.read()] == ["1"]


def test_forget_drops_the_store_and_keeps_the_archive():
    """Eviction is a memory decision; a resumed session still has its plan."""
    archive = _Recording()
    book = PlanBook(archive)
    book.for_session("a").write((PlanItem("1", "step", R),))

    book.forget("a")

    assert "a" not in book.sessions()
    assert [i.id for i in book.for_session("a").read()] == ["1"]


def test_forgetting_a_session_that_was_never_seen_is_not_an_error():
    PlanBook().forget("never")


def test_sessions_lists_what_has_been_asked_for():
    book = PlanBook()
    book.for_session("a")
    book.for_session("b")

    assert book.sessions() == ("a", "b")


def test_a_book_without_an_archive_keeps_plans_only_in_memory():
    book = PlanBook()
    book.for_session("a").write((PlanItem("1", "step", P),))

    assert [i.id for i in PlanBook().for_session("a").read()] == []


def test_the_whole_path_works_over_real_files(tmp_path):
    """The in-memory double proves the wiring; this proves the archive."""
    directory = tmp_path / "plans"
    PlanBook(FilePlanArchive(directory)).for_session("sess-1").write(
        (PlanItem("1", "load the matrix", R), PlanItem("2", "run QC", P))
    )

    restored = PlanBook(FilePlanArchive(directory)).for_session("sess-1").read()

    assert [(i.id, i.status) for i in restored] == [("1", R), ("2", P)]
    assert (directory / "sess-1.md").is_file()
