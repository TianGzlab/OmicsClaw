"""SSE ``Last-Event-ID`` resume cursor.

Plan §关键风险2: "SSE 断链自动重订阅；``/jobs/:id/events?resume=1`` 从最后
cursor 续流". When the tunnel hiccups or the App tab is backgrounded, the
browser's EventSource automatically reconnects with the ``Last-Event-ID``
header set to the last seen event id. The server must resume the log
tail at that byte offset so the user doesn't see duplicate output.

Invariants tested:
- ``job_log`` events carry an ``id:`` line equal to the end-byte-offset
  of the line in ``stdout.log``.
- Each line has a DIFFERENT id — otherwise a client crash between two
  lines in the same poll batch would lose one.
- Reconnecting with ``Last-Event-ID: N`` skips log bytes <= N.
- Invalid / non-numeric headers fall back to a fresh subscribe
  (byte 0) so the worst case is the existing duplication behaviour.
- Status events stay id-less — the SSE spec says the client keeps its
  previous Last-Event-ID, which is the correct cursor for log resume.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import List, Tuple

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from omicsclaw.execution.executors import JobContext, JobOutcome
from omicsclaw.remote.app_integration import register_remote_routers
from omicsclaw.remote.routers import jobs as jobs_module


@pytest.fixture()
def client(monkeypatch, tmp_path: Path) -> TestClient:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("OMICSCLAW_WORKSPACE", str(workspace))
    monkeypatch.delenv("OMICSCLAW_REMOTE_AUTH_TOKEN", raising=False)
    app = FastAPI()
    register_remote_routers(app)
    return TestClient(app)


def _parse_sse(body: str) -> List[dict]:
    events: list[dict] = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        ev = re.search(r"^event:\s*(\S+)", block, re.MULTILINE)
        dm = re.search(r"^data:\s*(.*)$", block, re.MULTILINE)
        idm = re.search(r"^id:\s*(\S+)", block, re.MULTILINE)
        if not ev or not dm:
            continue
        try:
            data = json.loads(dm.group(1))
        except json.JSONDecodeError:
            data = dm.group(1)
        event_id = idm.group(1) if idm else None
        events.append({"event": ev.group(1), "data": data, "id": event_id})
    return events


def _log_events(events: List[dict]) -> List[Tuple[str, str]]:
    return [
        (e["id"], e["data"]["line"])
        for e in events
        if e["event"] == "job_log" and isinstance(e["data"], dict)
    ]


def _seed_completed_job_with_log(
    workspace: Path,
    job_id: str,
    log_text: str,
    status: str = "succeeded",
) -> None:
    """Plant a terminal job whose stdout.log already contains ``log_text``.

    This lets resume tests exercise the cursor purely from the SSE side
    — no racing against a live executor.
    """
    job_dir = workspace / ".omicsclaw" / "remote" / "jobs" / job_id
    job_dir.mkdir(parents=True)
    (job_dir / "stdout.log").write_text(log_text, encoding="utf-8")
    (job_dir / "job.json").write_text(
        json.dumps({
            "job_id": job_id,
            "session_id": "",
            "skill": "noop",
            "status": status,
            "workspace": str(workspace),
            "inputs": {},
            "params": {},
            "created_at": "2025-01-01T00:00:00+00:00",
            "started_at": "2025-01-01T00:00:01+00:00",
            "finished_at": "2025-01-01T00:00:02+00:00",
            "exit_code": 0 if status == "succeeded" else 1,
            "error": None,
            "artifact_root": str(job_dir / "artifacts"),
        }),
        encoding="utf-8",
    )


def test_log_events_carry_monotonic_ids_at_line_boundaries(
    client: TestClient, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    _seed_completed_job_with_log(
        workspace, "id-check", "alpha\nbeta\ngamma\n"
    )

    with client.stream("GET", "/jobs/id-check/events") as stream:
        body = "".join(stream.iter_text())

    log_rows = _log_events(_parse_sse(body))
    assert [line for _id, line in log_rows] == ["alpha", "beta", "gamma"]
    ids = [int(event_id) for event_id, _ in log_rows]
    assert ids == sorted(set(ids)), "ids must be strictly monotonic"
    # "alpha\n" is 6 bytes → first id = 6; "beta\n" is 5 → 11; "gamma\n" 6 → 17
    assert ids == [6, 11, 17]


def test_resume_with_last_event_id_skips_seen_log_lines(
    client: TestClient, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    _seed_completed_job_with_log(
        workspace, "resume-mid", "alpha\nbeta\ngamma\n"
    )

    # Simulate the client having already received through "beta" (id=11).
    with client.stream(
        "GET",
        "/jobs/resume-mid/events",
        headers={"Last-Event-ID": "11"},
    ) as stream:
        body = "".join(stream.iter_text())

    log_rows = _log_events(_parse_sse(body))
    lines = [line for _id, line in log_rows]
    assert "alpha" not in lines
    assert "beta" not in lines
    assert "gamma" in lines


def test_resume_past_end_of_log_emits_no_log_events(
    client: TestClient, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    _seed_completed_job_with_log(
        workspace, "resume-end", "one\ntwo\n"
    )

    # Cursor beyond EOF: nothing left to stream.
    with client.stream(
        "GET",
        "/jobs/resume-end/events",
        headers={"Last-Event-ID": "9999"},
    ) as stream:
        body = "".join(stream.iter_text())

    events = _parse_sse(body)
    assert _log_events(events) == []
    # Status + done must still fire so the App can reconcile state.
    assert any(e["event"] == "job_succeeded" for e in events)
    assert any(e["event"] == "done" for e in events)


def test_resume_with_invalid_header_falls_back_to_fresh(
    client: TestClient, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    _seed_completed_job_with_log(
        workspace, "resume-bad", "hello\nworld\n"
    )

    for bad in ("not-a-number", "", "-5", "1.5"):
        with client.stream(
            "GET",
            "/jobs/resume-bad/events",
            headers={"Last-Event-ID": bad},
        ) as stream:
            body = "".join(stream.iter_text())
        lines = [line for _id, line in _log_events(_parse_sse(body))]
        assert "hello" in lines, f"invalid header {bad!r} must yield fresh stream"
        assert "world" in lines


def test_status_events_do_not_carry_id(
    client: TestClient, tmp_path: Path
) -> None:
    """SSE spec: absent ``id:`` lets the client keep its previous id —
    we want log-line cursors, not status cursors, to drive resume."""
    workspace = tmp_path / "workspace"
    _seed_completed_job_with_log(
        workspace, "status-ids", "just-one-line\n"
    )

    with client.stream("GET", "/jobs/status-ids/events") as stream:
        body = "".join(stream.iter_text())

    for e in _parse_sse(body):
        if e["event"] in ("job_queued", "job_started", "job_succeeded",
                          "job_failed", "job_canceled", "done"):
            assert e["id"] is None, (
                f"status event {e['event']} must not carry id"
            )


def test_resume_preserves_status_event_for_current_state(
    client: TestClient, tmp_path: Path
) -> None:
    """Reconnecting clients still need to see the current status so
    their UI updates — don't suppress status events just because the
    cursor is already past all logs."""
    workspace = tmp_path / "workspace"
    _seed_completed_job_with_log(
        workspace, "resume-status", "line\n", status="failed"
    )

    with client.stream(
        "GET",
        "/jobs/resume-status/events",
        headers={"Last-Event-ID": "9999"},
    ) as stream:
        body = "".join(stream.iter_text())

    names = [e["event"] for e in _parse_sse(body)]
    assert "job_failed" in names


def test_live_run_ids_roundtrip_and_resume_mid_stream(
    monkeypatch, client: TestClient, tmp_path: Path
) -> None:
    """Full live scenario: run an executor that writes known lines,
    capture the ids on the first subscribe, then reconnect with the
    second line's id as Last-Event-ID and verify the third line comes
    through without the first two."""

    class LinesExecutor:
        async def run(self, ctx: JobContext) -> JobOutcome:
            ctx.stdout_log.parent.mkdir(parents=True, exist_ok=True)
            for line in ("aaa\n", "bbb\n", "ccc\n"):
                await asyncio.sleep(0.05)
                with ctx.stdout_log.open("ab") as fh:
                    fh.write(line.encode("utf-8"))
            return JobOutcome(exit_code=0, stdout_text="")

    monkeypatch.setattr(jobs_module, "_DEFAULT_EXECUTOR", LinesExecutor())
    response = client.post("/jobs", json={"skill": "noop"})
    job_id = response.json()["job_id"]

    with client.stream("GET", f"/jobs/{job_id}/events") as stream:
        body = "".join(stream.iter_text())

    log_rows = _log_events(_parse_sse(body))
    assert [line for _id, line in log_rows] == ["aaa", "bbb", "ccc"]
    _bbb_id, _ = log_rows[1]

    # Second subscribe with the second line's id as the cursor.
    with client.stream(
        "GET",
        f"/jobs/{job_id}/events",
        headers={"Last-Event-ID": _bbb_id},
    ) as stream:
        body2 = "".join(stream.iter_text())
    resumed = [line for _id, line in _log_events(_parse_sse(body2))]
    assert resumed == ["ccc"]
