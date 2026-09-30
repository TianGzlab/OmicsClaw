"""``skills/_sdk/result.py``: the result.json envelope a skill writes (plan 0062 §3.3, case 19).

The writer is a deliberately small copy of the framework's owned-output
writer. Kept: no symbolic link in the target or in any ancestor, nothing
outside the output root, an atomic ``mkstemp`` + ``fsync`` + ``os.replace``
that leaves no temporary file behind on failure, and a reader that returns
``None`` for a symbolic link. Dropped (plan 0062 Q1): the hard-link count
check, the ``.omicsclaw-run-claim.json`` claim marker, and the Windows
reparse-point probe. ``mark_result_status`` accepts only run outcomes;
``scaffold`` is valid in an envelope but is not a run outcome, as in
``omicsclaw/common/report.py``.
"""

from __future__ import annotations

import json
import os

import pytest

from skills._sdk import result as result_module
from skills._sdk.result import (
    RESULT_SCHEMA,
    load_result_json,
    mark_result_status,
    validate_result_envelope,
    write_owned_text,
    write_result_json,
)


def _write(out, **kwargs):
    return write_result_json(out, "demo-skill", "1.0", {"n": 1}, {"params": {}}, input_checksum="abc", **kwargs)


def test_the_envelope_has_exactly_the_required_keys(tmp_path):
    payload = json.loads(_write(tmp_path).read_text())
    assert set(payload) == set(RESULT_SCHEMA["required"])
    assert payload["input_checksum"] == "sha256:abc"
    assert validate_result_envelope(payload) == []


def test_lineage_is_written_when_given(tmp_path):
    payload = json.loads(_write(tmp_path, lineage=[{"skill": "up"}]).read_text())
    assert set(payload) == set(RESULT_SCHEMA["required"]) | {"lineage"}


def test_a_failed_replace_leaves_the_target_and_no_temporary(tmp_path, monkeypatch):
    target = _write(tmp_path)
    before = target.read_text()

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(result_module.os, "replace", boom)
    with pytest.raises(OSError):
        write_owned_text(target, output_root=tmp_path, text="new")
    assert target.read_text() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["result.json"]


def test_a_symlinked_target_is_refused(tmp_path):
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_text("{}")
    out = tmp_path / "out"
    out.mkdir()
    (out / "result.json").symlink_to(elsewhere)
    with pytest.raises(RuntimeError):
        _write(out)
    assert elsewhere.read_text() == "{}"


def test_a_symlinked_ancestor_inside_the_root_is_refused(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    (out / "link").symlink_to(real, target_is_directory=True)
    with pytest.raises(RuntimeError):
        write_owned_text(out / "link" / "x.json", output_root=out, text="{}")
    assert not (real / "x.json").exists()


def test_a_symlinked_output_root_is_refused(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "out").symlink_to(real, target_is_directory=True)
    with pytest.raises(RuntimeError):
        _write(tmp_path / "out")
    assert list(real.iterdir()) == []


def test_a_path_outside_the_root_is_refused(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(RuntimeError):
        write_owned_text(tmp_path / "escape.json", output_root=out, text="{}")
    assert not (tmp_path / "escape.json").exists()


def test_load_returns_none_for_links_and_bad_json(tmp_path):
    assert load_result_json(tmp_path) is None
    (tmp_path / "result.json").write_text("{not json")
    assert load_result_json(tmp_path) is None
    good = tmp_path / "good.json"
    good.write_text('{"skill": "x"}')
    (tmp_path / "result.json").unlink()
    (tmp_path / "result.json").symlink_to(good)
    assert load_result_json(tmp_path) is None
    (tmp_path / "result.json").unlink()
    _write(tmp_path)
    assert load_result_json(tmp_path)["skill"] == "demo-skill"


@pytest.mark.parametrize("status", ["ok", "partial", "failed"])
def test_mark_result_status_writes_run_outcomes(tmp_path, status):
    _write(tmp_path)
    assert mark_result_status(tmp_path, status) is True
    assert json.loads((tmp_path / "result.json").read_text())["status"] == status


@pytest.mark.parametrize("status", ["scaffold", "done", ""])
def test_mark_result_status_rejects_anything_else(tmp_path, status):
    before = _write(tmp_path).read_text()
    assert mark_result_status(tmp_path, status) is False
    assert (tmp_path / "result.json").read_text() == before


def test_mark_result_status_without_an_envelope_is_false(tmp_path):
    assert mark_result_status(tmp_path, "ok") is False


def test_scaffold_is_a_valid_envelope_status(tmp_path):
    payload = json.loads(_write(tmp_path).read_text())
    payload["status"] = "scaffold"
    assert validate_result_envelope(payload) == []
    payload["status"] = "done"
    assert validate_result_envelope(payload) != []


def test_the_writer_never_follows_the_old_file(tmp_path):
    """Replacement goes through a new inode; a reader holding the old file keeps the old bytes."""
    target = _write(tmp_path)
    old_inode = os.stat(target).st_ino
    write_owned_text(target, output_root=tmp_path, text='{"x": 1}')
    assert os.stat(target).st_ino != old_inode
