"""Real-time SSE log tailing from ``<job>/stdout.log``.

Contract: whenever the active Executor writes a ``\\n``-terminated line to
``ctx.stdout_log``, the SSE stream must emit a corresponding ``job_log``
event (stream=``stdout``) *before* the eventual terminal status event.

Key invariants:
- Lines written in separate flushes must surface as separate events
  (no batching across the whole run).
- No line is emitted twice, even if the SSE loop polls the file many times.
- A pre-existing ``stdout.log`` (e.g. session resume) is drained on the
  first subscription.
- Unterminated trailing content is flushed only at terminal state.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import List

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
    """Return [{event, data}] in stream order."""
    events: list[dict] = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        match = re.search(r"^event:\s*(\S+)", block, re.MULTILINE)
        data_match = re.search(r"^data:\s*(.*)$", block, re.MULTILINE)
        if not match or not data_match:
            continue
        try:
            data = json.loads(data_match.group(1))
        except json.JSONDecodeError:
            data = data_match.group(1)
        events.append({"event": match.group(1), "data": data})
    return events


def test_sse_tails_progressive_lines_as_separate_events(
    monkeypatch, client: TestClient, tmp_path: Path
) -> None:
    """Executor writes 3 newline-terminated lines with pauses in between →
    SSE emits 3 distinct ``job_log`` events, not one batched event."""

    class ProgressiveExecutor:
        async def run(self, ctx: JobContext) -> JobOutcome:
            ctx.stdout_log.parent.mkdir(parents=True, exist_ok=True)
            for line in ("step-1-done\n", "step-2-done\n", "step-3-done\n"):
                await asyncio.sleep(0.05)
                with ctx.stdout_log.open("ab") as fh:
                    fh.write(line.encode("utf-8"))
            return JobOutcome(exit_code=0, error=None, stdout_text="")

    monkeypatch.setattr(jobs_module, "_DEFAULT_EXECUTOR", ProgressiveExecutor())

    response = client.post("/jobs", json={"skill": "noop"})
    assert response.status_code == 200, response.text
    job_id = response.json()["job_id"]

    with client.stream("GET", f"/jobs/{job_id}/events") as stream:
        body = "".join(stream.iter_text())

    events = _parse_sse(body)
    log_lines = [
        e["data"]["line"]
        for e in events
        if e["event"] == "job_log" and isinstance(e["data"], dict)
    ]
    assert "step-1-done" in log_lines
    assert "step-2-done" in log_lines
    assert "step-3-done" in log_lines


def test_sse_log_events_use_stdout_stream(
    monkeypatch, client: TestClient
) -> None:
    class OneLineExecutor:
        async def run(self, ctx: JobContext) -> JobOutcome:
            ctx.stdout_log.parent.mkdir(parents=True, exist_ok=True)
            ctx.stdout_log.write_text("single-line\n", encoding="utf-8")
            return JobOutcome(exit_code=0, error=None, stdout_text="")

    monkeypatch.setattr(jobs_module, "_DEFAULT_EXECUTOR", OneLineExecutor())

    response = client.post("/jobs", json={"skill": "noop"})
    job_id = response.json()["job_id"]

    with client.stream("GET", f"/jobs/{job_id}/events") as stream:
        body = "".join(stream.iter_text())

    log_events = [e for e in _parse_sse(body) if e["event"] == "job_log"]
    assert log_events, "expected at least one job_log event"
    assert log_events[0]["data"]["stream"] == "stdout"


def test_sse_does_not_duplicate_log_lines_across_polls(
    monkeypatch, client: TestClient
) -> None:
    """File tailing must track position; a line written once must never
    appear in two separate job_log events."""

    class SlowExecutor:
        async def run(self, ctx: JobContext) -> JobOutcome:
            ctx.stdout_log.parent.mkdir(parents=True, exist_ok=True)
            with ctx.stdout_log.open("ab") as fh:
                fh.write(b"only-once\n")
            # Sleep long enough that the SSE poll loop runs many times
            # after the write, giving duplicate emissions a chance to happen.
            await asyncio.sleep(0.2)
            return JobOutcome(exit_code=0, error=None, stdout_text="")

    monkeypatch.setattr(jobs_module, "_DEFAULT_EXECUTOR", SlowExecutor())
    response = client.post("/jobs", json={"skill": "noop"})
    job_id = response.json()["job_id"]

    with client.stream("GET", f"/jobs/{job_id}/events") as stream:
        body = "".join(stream.iter_text())

    only_once_events = [
        e
        for e in _parse_sse(body)
        if e["event"] == "job_log"
        and isinstance(e["data"], dict)
        and e["data"].get("line") == "only-once"
    ]
    assert len(only_once_events) == 1, (
        f"expected exactly one emission; got {len(only_once_events)}"
    )


def test_sse_resumes_pre_existing_stdout_log(
    client: TestClient, tmp_path: Path
) -> None:
    """Subscribing to a job whose stdout.log already has content drains
    that content as job_log events — the session-resume guarantee."""
    workspace = tmp_path / "workspace"
    job_id = "resumed-job"
    job_dir = workspace / ".omicsclaw" / "remote" / "jobs" / job_id
    job_dir.mkdir(parents=True)
    (job_dir / "stdout.log").write_text(
        "pre-existing-line-1\npre-existing-line-2\n", encoding="utf-8"
    )
    (job_dir / "job.json").write_text(
        json.dumps({
            "job_id": job_id,
            "session_id": "",
            "skill": "noop",
            "status": "succeeded",
            "workspace": str(workspace),
            "inputs": {},
            "params": {},
            "created_at": "2025-01-01T00:00:00+00:00",
            "started_at": "2025-01-01T00:00:01+00:00",
            "finished_at": "2025-01-01T00:00:02+00:00",
            "exit_code": 0,
            "error": None,
            "artifact_root": str(job_dir / "artifacts"),
        }),
        encoding="utf-8",
    )

    with client.stream("GET", f"/jobs/{job_id}/events") as stream:
        body = "".join(stream.iter_text())

    log_lines = [
        e["data"]["line"]
        for e in _parse_sse(body)
        if e["event"] == "job_log" and isinstance(e["data"], dict)
    ]
    assert "pre-existing-line-1" in log_lines
    assert "pre-existing-line-2" in log_lines


def test_sse_flushes_unterminated_trailing_line_at_done(
    monkeypatch, client: TestClient
) -> None:
    """A final ``\\n``-less chunk must be flushed as a job_log event when
    the job reaches terminal state — otherwise the last executor output
    gets silently dropped."""

    class NoTrailingNewlineExecutor:
        async def run(self, ctx: JobContext) -> JobOutcome:
            ctx.stdout_log.parent.mkdir(parents=True, exist_ok=True)
            ctx.stdout_log.write_text("trailing-no-newline", encoding="utf-8")
            return JobOutcome(exit_code=0, error=None, stdout_text="")

    monkeypatch.setattr(
        jobs_module, "_DEFAULT_EXECUTOR", NoTrailingNewlineExecutor()
    )
    response = client.post("/jobs", json={"skill": "noop"})
    job_id = response.json()["job_id"]

    with client.stream("GET", f"/jobs/{job_id}/events") as stream:
        body = "".join(stream.iter_text())

    log_lines = [
        e["data"]["line"]
        for e in _parse_sse(body)
        if e["event"] == "job_log" and isinstance(e["data"], dict)
    ]
    assert "trailing-no-newline" in log_lines


def test_sse_log_events_appear_before_terminal_status(
    monkeypatch, client: TestClient
) -> None:
    """User expects log context first, then the final status — reversing
    the order makes the UI awkward (banner arrives before logs)."""

    class LoggedExecutor:
        async def run(self, ctx: JobContext) -> JobOutcome:
            ctx.stdout_log.parent.mkdir(parents=True, exist_ok=True)
            ctx.stdout_log.write_text(
                "context-line-a\ncontext-line-b\n", encoding="utf-8"
            )
            return JobOutcome(exit_code=0, error=None, stdout_text="")

    monkeypatch.setattr(jobs_module, "_DEFAULT_EXECUTOR", LoggedExecutor())
    response = client.post("/jobs", json={"skill": "noop"})
    job_id = response.json()["job_id"]

    with client.stream("GET", f"/jobs/{job_id}/events") as stream:
        body = "".join(stream.iter_text())

    events = _parse_sse(body)
    names = [e["event"] for e in events]
    terminal_index = names.index("job_succeeded")
    log_positions = [
        i
        for i, e in enumerate(events)
        if e["event"] == "job_log"
        and isinstance(e["data"], dict)
        and e["data"].get("line", "").startswith("context-line")
    ]
    assert log_positions, "expected log events"
    assert max(log_positions) < terminal_index, (
        "all context log events should be emitted before job_succeeded"
    )
