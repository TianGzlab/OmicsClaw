"""Serialisation, safe names, and the two files a session leaves behind."""

from __future__ import annotations

import json
import os
import pathlib
import stat

import pytest

from omicsclaw.planning import (
    FilePlanArchive,
    PlanArchiveError,
    PlanItem,
    PlanStatus,
    dump_items,
    load_items,
    safe_name,
)

P, R, C, X = (
    PlanStatus.PENDING,
    PlanStatus.IN_PROGRESS,
    PlanStatus.COMPLETED,
    PlanStatus.CANCELLED,
)
_PLAN = (
    PlanItem("1", "load the matrix", R),
    PlanItem("2", "run QC", P),
    PlanItem("3", "done", C),
)


# ---- the text format ------------------------------------------------------


def test_a_plan_round_trips_unchanged():
    assert load_items(dump_items(_PLAN)) == _PLAN


def test_an_empty_plan_round_trips_as_an_empty_plan():
    assert load_items(dump_items(())) == ()


def test_non_ascii_content_is_stored_readably():
    """The file is partly written for a person; escaping it defeats that."""
    text = dump_items((PlanItem("1", "对空间域做去卷积", P),))

    assert "对空间域做去卷积" in text


def test_a_truncated_file_is_refused_rather_than_read_as_empty():
    with pytest.raises(PlanArchiveError) as caught:
        load_items('[{"id": "1", "conten')

    assert "valid JSON" in str(caught.value)


def test_a_json_object_is_refused_because_a_plan_is_a_list():
    with pytest.raises(PlanArchiveError):
        load_items('{"id": "1"}')


def test_a_missing_field_names_the_field_and_the_position():
    with pytest.raises(PlanArchiveError) as caught:
        load_items('[{"id": "1", "content": "a"}]')

    assert "item 0" in str(caught.value)
    assert "status" in str(caught.value)


def test_an_unknown_status_refuses_the_whole_file():
    """Skipping the item would leave history wrong in the unsafe direction.

    The anti-cheat rule decides by comparing a write against prior status,
    so an item silently missing from the restored plan is an item whose
    completion is never examined.
    """
    payload = json.dumps(
        [
            {"id": "1", "content": "a", "status": "pending"},
            {"id": "2", "content": "b", "status": "blocked"},
        ]
    )

    with pytest.raises(PlanArchiveError) as caught:
        load_items(payload)

    assert "blocked" in str(caught.value)


# ---- filenames ------------------------------------------------------------


@pytest.mark.parametrize(
    "session_id",
    ["../../etc/passwd", "a/b", "..", "", "   ", "sess:1?x"],
)
def test_a_name_never_leaves_its_directory(tmp_path, session_id: str):
    archive = FilePlanArchive(tmp_path)

    json_path, markdown_path = archive.paths(session_id)

    assert json_path.parent == tmp_path
    assert markdown_path.parent == tmp_path


def test_an_ordinary_id_is_left_alone_so_the_directory_stays_readable():
    assert safe_name("a1b2c3d4") == "a1b2c3d4"
    assert safe_name("chat-42_x.1") == "chat-42_x.1"


def test_an_id_that_empties_out_still_gets_a_name():
    assert safe_name("///") == "session"


# ---- the files ------------------------------------------------------------


def test_nothing_is_created_until_something_is_saved(tmp_path):
    """A deployment whose agent never plans leaves no trace of the feature."""
    directory = tmp_path / "plans"
    archive = FilePlanArchive(directory)

    assert archive.load("s") == ()
    assert not directory.exists()


def test_saving_creates_both_halves(tmp_path):
    archive = FilePlanArchive(tmp_path / "plans")

    archive.save("sess-1", _PLAN)

    json_path, markdown_path = archive.paths("sess-1")
    assert json_path.is_file()
    assert markdown_path.is_file()


def test_what_was_saved_is_what_is_loaded(tmp_path):
    archive = FilePlanArchive(tmp_path)
    archive.save("sess-1", _PLAN)

    assert archive.load("sess-1") == _PLAN


def test_only_the_json_half_is_ever_read_back(tmp_path):
    """The Markdown is a rendering; a torn one costs a glance, not state."""
    archive = FilePlanArchive(tmp_path)
    archive.save("sess-1", _PLAN)
    _, markdown_path = archive.paths("sess-1")
    markdown_path.write_text("corrupted by a person", encoding="utf-8")

    assert archive.load("sess-1") == _PLAN


def test_a_second_save_replaces_rather_than_appends(tmp_path):
    archive = FilePlanArchive(tmp_path)
    archive.save("s", _PLAN)

    archive.save("s", (PlanItem("9", "only this", P),))

    assert [item.id for item in archive.load("s")] == ["9"]


def test_two_sessions_do_not_share_a_plan(tmp_path):
    archive = FilePlanArchive(tmp_path)

    archive.save("a", (PlanItem("1", "a's plan", P),))
    archive.save("b", (PlanItem("2", "b's plan", P),))

    assert [i.content for i in archive.load("a")] == ["a's plan"]
    assert [i.content for i in archive.load("b")] == ["b's plan"]


def test_a_saved_plan_is_owner_only(tmp_path):
    archive = FilePlanArchive(tmp_path)
    archive.save("s", _PLAN)

    for path in archive.paths("s"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600, path


def test_an_unreadable_file_raises_rather_than_reading_as_no_plan(tmp_path):
    """Starting the session over silently is the worse failure."""
    archive = FilePlanArchive(tmp_path)
    archive.save("s", _PLAN)
    json_path, _ = archive.paths("s")
    json_path.chmod(0o000)

    try:
        if os.geteuid() == 0:  # pragma: no cover - root ignores the mode
            pytest.skip("running as root: file modes do not deny reads")
        with pytest.raises(PlanArchiveError):
            archive.load("s")
    finally:
        json_path.chmod(0o600)


def test_a_failed_write_leaves_the_previous_plan_intact(tmp_path, monkeypatch):
    """``O_TRUNC`` empties before the first byte lands; ``os.replace`` does not.

    A plan emptied by a failed write reads as "no plan", which is
    indistinguishable from a new session — plan 0029 finding #4.

    The failure is injected at :func:`os.replace` rather than by handing
    in an object that cannot be serialised: that would raise inside
    ``dump_items``, before any file is touched, and the test would pass
    against an implementation that truncates.
    """
    archive = FilePlanArchive(tmp_path)
    archive.save("s", _PLAN)
    json_path, _ = archive.paths("s")
    before = json_path.read_bytes()

    def refuse(src: object, dst: object) -> None:
        raise OSError("no space left on device")

    monkeypatch.setattr(os, "replace", refuse)

    with pytest.raises(PlanArchiveError):
        archive.save("s", (PlanItem("9", "replacement", P),))

    assert json_path.read_bytes() == before


def test_a_failed_write_leaves_no_temporary_file_behind(tmp_path, monkeypatch):
    archive = FilePlanArchive(tmp_path)
    archive.save("s", _PLAN)

    def refuse(src: object, dst: object) -> None:
        raise OSError("no space left on device")

    monkeypatch.setattr(os, "replace", refuse)

    with pytest.raises(PlanArchiveError):
        archive.save("s", (PlanItem("9", "replacement", P),))

    assert sorted(path.name for path in tmp_path.iterdir()) == ["s.json", "s.md"]


def test_the_injected_failure_really_reaches_the_replace(tmp_path, monkeypatch):
    """The guard above, checked: a no-op patch would make both tests vacuous."""
    archive = FilePlanArchive(tmp_path)
    calls: list[tuple[object, object]] = []
    real = os.replace

    def record(src: object, dst: object) -> None:
        calls.append((src, dst))
        real(src, dst)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "replace", record)
    archive.save("s", _PLAN)

    assert len(calls) == 1
    assert str(calls[0][1]).endswith("s.json")


def test_the_json_half_lands_before_the_markdown_half_is_touched(tmp_path):
    """The ordering :meth:`FilePlanArchive.save`'s docstring makes load-bearing.

    A crash between the two writes must leave the *record* stale rather
    than the *state* unrecoverable, and only this order gives that. The
    claim had no test: reversing the two writes left all 175 tests green,
    which is a docstring promising a property nothing checks.

    Observed by watching the filesystem rather than by reading the code:
    the markdown write is intercepted and asked what the JSON file says at
    that moment.
    """
    archive = FilePlanArchive(tmp_path)
    json_path, markdown_path = archive.paths("s")
    observed: list[str] = []

    real_write = type(markdown_path).write_text

    def spy(self, data, *args, **kwargs):
        if self == markdown_path:
            observed.append(json_path.read_text(encoding="utf-8"))
        return real_write(self, data, *args, **kwargs)

    original = pathlib.Path.write_text
    pathlib.Path.write_text = spy  # type: ignore[method-assign]
    try:
        archive.save("s", _PLAN)
    finally:
        pathlib.Path.write_text = original  # type: ignore[method-assign]

    assert observed, "the markdown half was never written"
    assert load_items(observed[0]) == _PLAN, (
        "the markdown half was written before the JSON half had landed"
    )


def test_a_markdown_failure_does_not_lose_the_state(tmp_path, monkeypatch):
    """The same ordering, stated as its consequence.

    The markdown half is a rendering and nothing reads it back, so its
    failure must cost a stale record — never the plan.
    """
    archive = FilePlanArchive(tmp_path)
    archive.save("s", (PlanItem("old", "previous plan", P),))

    original = pathlib.Path.write_text

    def refuse(self, data, *args, **kwargs):
        if self.suffix == ".md":
            raise OSError("no space left on device")
        return original(self, data, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "write_text", refuse)

    with pytest.raises(PlanArchiveError):
        archive.save("s", _PLAN)

    monkeypatch.undo()
    assert archive.load("s") == _PLAN
