"""Atomic writes for diagnostic artifacts.

Stage 7 made ``_write_job`` atomic for ``job.json``. This file extends
the same guarantee to the diagnostic artifacts written through
``_write_text``:

- ``stdout.log`` (when the executor didn't stream — e.g. LocalExecutor
  stub — and ``_finalize_stdout`` seeds it)
- ``diagnostics/stdout.log`` (failure diagnostic snapshot)
- ``diagnostics/env_doctor.json`` (env probe snapshot attached to
  failed jobs)

A crash mid-write leaves a truncated file — the App's failure-diagnostic
flow then shows an empty stdout or a JSON parse error. The fix is the
same temp-file + rename pattern used for ``job.json``.

Non-goal: making executor-driven ``stdout.log`` writes atomic.
``SubprocessExecutor`` appends byte-by-byte by design so the SSE tail
can stream live. Atomicity at append-time would defeat that.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omicsclaw.remote.routers import jobs as jobs_module


def test_write_text_failure_preserves_existing_target(
    monkeypatch, tmp_path: Path
) -> None:
    """RED: naive ``write_text`` on target = truncate-then-crash →
    empty target. GREEN: atomic writer writes to ``.tmp`` then
    ``replace``; sabotaging the replace keeps the target at its
    pre-write content."""
    target = tmp_path / "dir" / "file.log"
    target.parent.mkdir()
    target.write_text("previous-content\n", encoding="utf-8")

    real_write_text = Path.write_text
    real_replace = Path.replace

    def crash_on_direct_target(self: Path, *args, **kwargs):
        if self == target:
            with open(self, "wb"):
                pass
            raise RuntimeError("crash after truncate")
        return real_write_text(self, *args, **kwargs)

    def crash_on_target_rename(self: Path, target_path):
        if Path(target_path) == target:
            raise OSError("simulated crash mid-rename")
        return real_replace(self, target_path)

    monkeypatch.setattr(Path, "write_text", crash_on_direct_target)
    monkeypatch.setattr(Path, "replace", crash_on_target_rename)
    try:
        jobs_module._write_text(target, "new-content\n")
    except Exception:
        pass
    monkeypatch.setattr(Path, "write_text", real_write_text)
    monkeypatch.setattr(Path, "replace", real_replace)

    assert target.is_file()
    assert target.read_text(encoding="utf-8") == "previous-content\n", (
        "target was truncated — _write_text is not atomic"
    )


def test_write_text_crash_in_tmp_leaves_target_untouched(
    monkeypatch, tmp_path: Path
) -> None:
    target = tmp_path / "diagnostics" / "env_doctor.json"
    target.parent.mkdir(parents=True)
    target.write_text('{"prior":true}', encoding="utf-8")
    pre = target.read_text(encoding="utf-8")

    real_write_text = Path.write_text

    def crash_in_tmp(self: Path, *args, **kwargs):
        if self.name.endswith(".tmp"):
            # Partially write the tmp, then fail — simulates disk-full.
            real_write_text(self, "{partial", *args[1:], **kwargs)
            raise OSError("simulated disk full")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", crash_in_tmp)
    try:
        jobs_module._write_text(target, '{"now":true}')
    except OSError:
        pass
    monkeypatch.setattr(Path, "write_text", real_write_text)

    assert target.read_text(encoding="utf-8") == pre


def test_write_text_success_leaves_no_stray_tmp(tmp_path: Path) -> None:
    target = tmp_path / "report.log"
    jobs_module._write_text(target, "done\n")
    assert target.read_text(encoding="utf-8") == "done\n"
    stray = list(target.parent.glob("*.tmp"))
    assert stray == [], f"stray tmp files remain: {stray}"


def test_write_text_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "nested" / "place" / "x.log"
    jobs_module._write_text(target, "ok\n")
    assert target.is_file()
    assert target.read_text(encoding="utf-8") == "ok\n"


def test_write_text_roundtrip_unchanged(tmp_path: Path) -> None:
    target = tmp_path / "plain.txt"
    payload = "line1\nline2\n中文\n"
    jobs_module._write_text(target, payload)
    assert target.read_text(encoding="utf-8") == payload


def test_failure_diagnostics_env_doctor_json_is_atomic(
    monkeypatch, tmp_path: Path
) -> None:
    """End-to-end sanity: ``_persist_failure_diagnostics`` writes
    ``env_doctor.json`` through ``_write_text``; a crash during that
    write must not leave a corrupted JSON artifact for the App to
    render as ``parse error``."""
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("OMICSCLAW_WORKSPACE", str(workspace))

    job_id = "diag-atomic"
    # First-run: seed good diagnostics by running the real call.
    jobs_module._persist_failure_diagnostics(
        workspace, job_id, stdout_text="first run\n"
    )
    env_path = (
        workspace / ".omicsclaw" / "remote" / "jobs" / job_id
        / "artifacts" / "diagnostics" / "env_doctor.json"
    )
    assert env_path.is_file()
    first_bytes = env_path.read_bytes()
    assert first_bytes, "first diagnostics write should produce content"

    # Second-run with a simulated crash during the env_doctor.json
    # write. Under a non-atomic writer the target gets truncated; under
    # the atomic writer, failing the ``replace`` preserves the prior
    # content verbatim.
    real_write_text = Path.write_text
    real_replace = Path.replace

    def crash_on_env_doctor(self: Path, *args, **kwargs):
        if self == env_path:
            with open(self, "wb"):
                pass
            raise RuntimeError("crash during env_doctor write")
        return real_write_text(self, *args, **kwargs)

    def crash_env_doctor_rename(self: Path, target_path):
        if Path(target_path) == env_path:
            raise OSError("simulated crash during env_doctor rename")
        return real_replace(self, target_path)

    monkeypatch.setattr(Path, "write_text", crash_on_env_doctor)
    monkeypatch.setattr(Path, "replace", crash_env_doctor_rename)
    try:
        jobs_module._persist_failure_diagnostics(
            workspace, job_id, stdout_text="second run\n"
        )
    except Exception:
        pass
    monkeypatch.setattr(Path, "write_text", real_write_text)
    monkeypatch.setattr(Path, "replace", real_replace)

    assert env_path.read_bytes() == first_bytes, (
        "env_doctor.json was corrupted by mid-write crash"
    )
