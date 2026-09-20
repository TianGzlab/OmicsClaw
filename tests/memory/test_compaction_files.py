"""Plan 0035: the two files compaction leaves behind.

Offloaded tool results must be readable back through the workspace
sandbox and must not be rewritten on every turn that offloads them
again; the compaction log must round-trip every field, including the ones
the context layer added for offloading, and must survive a damaged line.
"""

from __future__ import annotations

import asyncio
import json
import os
import stat

import pytest

from omicsclaw.context import (
    Anchors,
    CompactionRecord,
    OffloadEntry,
    Pressure,
)
from omicsclaw.memory import FileOffloadStore, JsonlCompactionLog, safe_name


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, 5.0))


# --- the offload store -----------------------------------------------------


def test_a_result_is_written_where_its_relative_reference_points(tmp_path):
    store = FileOffloadStore(
        tmp_path / ".omicsclaw" / "tool_results", "s1", reference_base=tmp_path
    )

    reference = _run(store.put("c1-abc", "full output\n" * 100))

    assert reference == ".omicsclaw/tool_results/s1/c1-abc.txt"
    assert (tmp_path / reference).read_text() == "full output\n" * 100


def test_files_are_private_to_the_user(tmp_path):
    store = FileOffloadStore(tmp_path / "results", "s1")

    reference = _run(store.put("k", "secret"))

    assert stat.S_IMODE((tmp_path / "results" / "s1").stat().st_mode) == 0o700
    assert stat.S_IMODE(os.stat(reference).st_mode) == 0o600


def test_a_key_already_written_is_not_written_again(tmp_path):
    """Offloading the same result on a later turn costs no write — and does
    not clobber a file somebody edited in between."""
    store = FileOffloadStore(tmp_path, "s1")
    first = _run(store.put("k", "original"))
    (tmp_path / "s1" / "k.txt").write_text("edited")

    second = _run(store.put("k", "original"))
    again = FileOffloadStore(tmp_path, "s1")
    third = _run(again.put("k", "original"))

    assert first == second == third
    assert (tmp_path / "s1" / "k.txt").read_text() == "edited"


@pytest.mark.parametrize("key", ["../escape", "a/b", "", ".hidden", "x" * 200])
def test_a_key_that_is_not_a_plain_name_is_refused(tmp_path, key):
    with pytest.raises(ValueError):
        _run(FileOffloadStore(tmp_path, "s1").put(key, "x"))


def test_every_key_the_context_layer_derives_is_accepted(tmp_path):
    """The two layers each have a key rule; they must agree."""
    from omicsclaw.context import offload_key

    store = FileOffloadStore(tmp_path, "s1")
    for call_id in ("-x", "--", "..", "call_0", "", "é/ü", "a" * 200):
        _run(store.put(offload_key(call_id, "content"), "content"))


def test_a_reference_outside_the_base_is_absolute(tmp_path):
    store = FileOffloadStore(tmp_path / "a", "s1", reference_base=tmp_path / "b")

    reference = _run(store.put("k", "x"))

    assert reference == str((tmp_path / "a" / "s1" / "k.txt").resolve())


def test_purge_removes_the_session_directory(tmp_path):
    store = FileOffloadStore(tmp_path, "s1")
    _run(store.put("k", "x"))

    _run(store.purge())

    assert not (tmp_path / "s1").exists()
    _run(store.put("k", "x"))
    assert (tmp_path / "s1" / "k.txt").exists(), "a purged key is written again"


@pytest.mark.parametrize("raw", ["../../etc", "..", ".", "", "a/b", "feishu:ou_1"])
def test_session_ids_become_one_safe_component(raw):
    name = safe_name(raw)

    assert "/" not in name
    assert name not in ("", ".", "..")


def test_different_session_ids_never_share_a_directory():
    assert safe_name("a:b") != safe_name("a_b")
    assert safe_name("plain-id") == "plain-id"


# --- the compaction log ----------------------------------------------------


def _record() -> CompactionRecord:
    return CompactionRecord(
        pressure=Pressure.FULL,
        tokens_before=1000,
        tokens_after=300,
        msgs_before=40,
        msgs_after=8,
        summarized=32,
        preserved_tail=6,
        anchors=Anchors(user_intent="annotate", next_steps="- run DE"),
        summary_text="three steps in",
        degraded="",
        advisories=("offloading lowered the pressure from full to soft",),
        duration_s=1.5,
        trigger=Pressure.EMERGENCY,
        offloaded=(
            OffloadEntry(
                reference="r.txt",
                lines=5,
                chars=900,
                tool_call_id="c1",
                tool_name="bash",
            ),
        ),
        forced=True,
        written_back=True,
    )


def test_a_record_round_trips_through_the_log(tmp_path):
    log = JsonlCompactionLog(tmp_path)

    logged = _run(log.append("s1", _record(), timestamp=123.0))
    (read,) = _run(log.list("s1"))

    assert read == logged
    assert read.record == _record()
    assert read.timestamp == 123.0


def test_each_line_carries_identity_and_the_ratio(tmp_path):
    log = JsonlCompactionLog(tmp_path)
    _run(log.append("s1", _record()))
    _run(log.append("s1", _record()))

    lines = log.path_for("s1").read_text().splitlines()

    assert len(lines) == 2
    first, second = (json.loads(line) for line in lines)
    assert first["id"] != second["id"]
    assert first["session_id"] == "s1"
    assert first["compression_ratio"] == pytest.approx(0.3)
    assert first["pressure"] == "full"
    assert stat.S_IMODE(log.path_for("s1").stat().st_mode) == 0o600


def test_a_damaged_line_is_skipped_not_fatal(tmp_path):
    log = JsonlCompactionLog(tmp_path)
    _run(log.append("s1", _record()))
    with log.path_for("s1").open("a") as stream:
        stream.write("{not json\n")
        stream.write('{"id": "x", "session_id": "s1", "timestamp": 1}\n')
    _run(log.append("s1", _record()))

    assert len(_run(log.list("s1"))) == 2


def test_an_unknown_session_has_an_empty_log_and_purge_is_idempotent(tmp_path):
    log = JsonlCompactionLog(tmp_path)

    assert _run(log.list("nobody")) == ()
    _run(log.purge("nobody"))
    _run(log.append("s1", _record()))
    _run(log.purge("s1"))
    assert _run(log.list("s1")) == ()


def test_sessions_are_kept_apart(tmp_path):
    log = JsonlCompactionLog(tmp_path)
    _run(log.append("a", _record()))

    assert _run(log.list("b")) == ()
