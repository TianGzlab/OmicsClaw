"""Job submission, listing, SSE event stream, cancel, retry.

Jobs are persisted as JSON sidecars on disk so they survive process
restarts. Each queued job is driven to a terminal state by the active
``Executor`` (``omicsclaw.execution.executors``); the default spawns
``python omicsclaw.py run <skill> ...``.

Critical constraints:
- ``GET /jobs/{id}/events`` is read-only — streaming must never rewrite
  terminal state such as ``canceled``.
- Running jobs orphaned by a server restart are reconciled to ``failed``
  on first workspace touch (``_reconcile_orphaned_jobs``).
- A cancel during executor run wins: the runner re-reads the job after
  ``executor.run()`` and skips the terminal write if status already moved.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from omicsclaw.execution.executors import (
    Executor,
    JobContext,
    JobOutcome,
    build_default_executor,
)
from omicsclaw.execution.executors.local import EXECUTOR_NOT_IMPLEMENTED_LINE
from omicsclaw.remote.schemas import (
    Job,
    JobListResponse,
    JobStatus,
    JobSubmitRequest,
    JobSubmitResponse,
)
from omicsclaw.remote.routers.env import build_env_doctor_report_payload
from omicsclaw.remote.storage import jobs_root, resolve_workspace, utc_now_iso

router = APIRouter(tags=["remote"])
logger = logging.getLogger(__name__)
_TERMINAL_STATUSES = frozenset({"succeeded", "failed", "canceled"})
_STUB_JOB_TASKS: dict[str, asyncio.Task[None]] = {}
_EXECUTOR_NOT_IMPLEMENTED_LINE = EXECUTOR_NOT_IMPLEMENTED_LINE
_DEFAULT_EXECUTOR: Executor = build_default_executor()
_ORPHANED_JOB_LINE = (
    "server_restart_orphaned_job: job was in 'running' state when the "
    "server restarted; no active task to drive it forward"
)
_RECONCILED_WORKSPACES: set[Path] = set()


def _job_dir(workspace: Path, job_id: str) -> Path:
    return jobs_root(workspace) / job_id


def _job_path(workspace: Path, job_id: str) -> Path:
    return _job_dir(workspace, job_id) / "job.json"


def _artifact_root(workspace: Path, job_id: str) -> Path:
    return _job_dir(workspace, job_id) / "artifacts"


def _is_chat_stream_job(job: Optional[Job]) -> bool:
    return bool(
        job
        and job.skill == "chat"
        and isinstance(job.params, dict)
        and job.params.get("job_kind") == "chat_stream"
    )


def _reconcile_orphaned_jobs(workspace: Path) -> bool:
    """Flip ``running`` jobs that have no active stub task to ``failed``.

    Invariants:
    - Never touches ``queued`` jobs — they recover through ``_ensure_stub_job``.
    - Never touches terminal jobs (succeeded / failed / canceled).
    - Skips jobs whose stub task is still alive on the current event loop.
    Returns ``True`` only when the workspace was scanned without unexpected
    reconcile errors. Callers should retry later when ``False`` is returned.
    """
    root = jobs_root(workspace)
    if not root.is_dir():
        return True
    reconciled_cleanly = True
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        job = _read_job(workspace, entry.name)
        if job is None or job.status != "running":
            continue
        task = _STUB_JOB_TASKS.get(entry.name)
        if task is not None and not task.done():
            continue
        try:
            artifact_root = _persist_failure_diagnostics(
                workspace,
                job.job_id,
                stdout_text=_ORPHANED_JOB_LINE,
            )
            orphaned = job.model_copy(update={
                "status": "failed",
                "finished_at": utc_now_iso(),
                "exit_code": 1,
                "error": "server_restart_orphaned_job",
                "artifact_root": artifact_root,
            })
            _write_job(workspace, orphaned)
        except Exception:
            reconciled_cleanly = False
            logger.exception(
                "Failed to reconcile orphaned remote job '%s' in workspace '%s'",
                job.job_id,
                workspace,
            )
    return reconciled_cleanly


def _resolve_or_400() -> Path:
    try:
        workspace = resolve_workspace()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if workspace not in _RECONCILED_WORKSPACES:
        if _reconcile_orphaned_jobs(workspace):
            _RECONCILED_WORKSPACES.add(workspace)
    return workspace


def _read_job(workspace: Path, job_id: str) -> Optional[Job]:
    path = _job_path(workspace, job_id)
    if not path.is_file():
        return None
    try:
        return Job.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_job(workspace: Path, job: Job) -> None:
    """Atomically persist ``job.json``.

    Writes to a sibling ``.tmp`` file then ``os.replace``-renames it
    into place. The rename is atomic on POSIX, so concurrent readers
    never observe a truncated file — they see either the pre-write
    content or the full post-write content. A crash / SIGKILL during
    the ``.tmp`` write leaves the target untouched; a crash between
    write and rename also leaves the target untouched plus a stray
    ``.tmp`` (benign — next write overwrites it).
    """
    path = _job_path(workspace, job.job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    serialized = json.dumps(job.model_dump(), indent=2, sort_keys=True)
    try:
        tmp.write_text(serialized, encoding="utf-8")
        tmp.replace(path)
    except Exception:
        # Best-effort cleanup so repeated failures don't leave stale
        # .tmp files. The target is intentionally NOT touched.
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _write_text(path: Path, content: str) -> None:
    """Atomically write ``content`` to ``path``.

    Mirrors ``_write_job``'s temp-file + ``os.replace`` pattern so a
    crash mid-write leaves the pre-existing target intact instead of a
    truncated / half-written file. Used for the diagnostic artifacts
    (``stdout.log``, ``diagnostics/stdout.log``, ``env_doctor.json``)
    that the App's failure-diagnostic view depends on.

    Not used for the live executor append path — ``SubprocessExecutor``
    writes bytes straight into ``stdout.log`` so SSE log-tailing can
    stream incrementally.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def append_job_stdout_line(workspace: Path, job_id: str, line: str) -> None:
    trimmed = line.rstrip()
    if not trimmed:
        return
    stdout_path = _job_dir(workspace, job_id) / "stdout.log"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    with stdout_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{trimmed}\n")


def _finalize_stdout(workspace: Path, job_id: str, stdout_text: str) -> None:
    """Ensure ``stdout.log`` has content for diagnostics.

    Preserve anything the executor streamed during run (so live-tailed
    SSE output isn't wiped). Only fall back to ``stdout_text`` when the
    executor left the file empty / missing — this is the instant-return
    stub-executor path, e.g. ``LocalExecutor``.
    """
    stdout_path = _job_dir(workspace, job_id) / "stdout.log"
    if stdout_path.is_file() and stdout_path.stat().st_size > 0:
        return
    if not stdout_text:
        return
    normalized = stdout_text if stdout_text.endswith("\n") else f"{stdout_text}\n"
    _write_text(stdout_path, normalized)


def _persist_failure_diagnostics(workspace: Path, job_id: str, *, stdout_text: str) -> str:
    _finalize_stdout(workspace, job_id, stdout_text)
    job_dir = _job_dir(workspace, job_id)
    artifact_root = _artifact_root(workspace, job_id)
    diagnostics_dir = artifact_root / "diagnostics"

    stdout_path = job_dir / "stdout.log"
    diagnostics_content = (
        stdout_path.read_text(encoding="utf-8")
        if stdout_path.is_file()
        else ""
    )
    _write_text(diagnostics_dir / "stdout.log", diagnostics_content)

    env_payload = build_env_doctor_report_payload(workspace_dir=str(workspace))
    _write_text(
        diagnostics_dir / "env_doctor.json",
        json.dumps(env_payload.model_dump(), indent=2, sort_keys=True),
    )
    return str(artifact_root.resolve())


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _tail_new_lines(
    log_path: Path,
    bytes_read: int,
    carry: str,
) -> tuple[list[str], int, str]:
    """Read new bytes from ``log_path`` since ``bytes_read`` offset.

    Returns ``(complete_new_lines, new_offset, carry)`` where ``carry``
    holds the trailing partial line (no newline yet) that must be
    prepended to the next read. Only ``\\n``-terminated lines are
    returned here; partial content is buffered until the executor flushes
    a newline or the stream drains at terminal state.

    File shrink / truncate is out of scope for MVP — executors only
    append.
    """
    if not log_path.is_file():
        return [], bytes_read, carry
    try:
        size = log_path.stat().st_size
    except OSError:
        return [], bytes_read, carry
    if size <= bytes_read:
        return [], bytes_read, carry
    try:
        with log_path.open("rb") as fh:
            fh.seek(bytes_read)
            chunk = fh.read(size - bytes_read)
    except OSError:
        return [], bytes_read, carry
    buffer = carry + chunk.decode("utf-8", errors="replace")
    pieces = buffer.split("\n")
    new_carry = pieces[-1]  # may be "" when buffer ends with \n
    return pieces[:-1], size, new_carry


def _log_event(job_id: str, line: str, *, event_id: int | None = None) -> str:
    """Render a ``job_log`` SSE frame, optionally with an ``id:`` line.

    The id carries the end-byte-offset of ``line`` inside ``stdout.log``
    so clients can round-trip it back as ``Last-Event-ID`` on reconnect.
    Each line gets a *distinct* id — a shared batch id would let a
    client crash mid-batch silently drop later lines with the same id.
    """
    payload = {"job_id": job_id, "stream": "stdout", "line": line}
    data = json.dumps(payload, ensure_ascii=False)
    if event_id is None:
        return f"event: job_log\ndata: {data}\n\n"
    return f"id: {event_id}\nevent: job_log\ndata: {data}\n\n"


def _status_event_name(status: JobStatus) -> str:
    return {
        "queued": "job_queued",
        "running": "job_started",
        "succeeded": "job_succeeded",
        "failed": "job_failed",
        "canceled": "job_canceled",
    }[status]


def _persist_success_stdout(workspace: Path, job_id: str, *, stdout_text: str) -> str:
    _finalize_stdout(workspace, job_id, stdout_text)
    artifact_root = _artifact_root(workspace, job_id)
    artifact_root.mkdir(parents=True, exist_ok=True)
    return str(artifact_root.resolve())


async def _run_job(workspace: Path, job_id: str) -> None:
    """Drive a queued job through the active Executor to a terminal state.

    Re-reads the job JSON between each transition so a ``cancel`` call
    wins over an in-flight executor run.
    """
    try:
        await asyncio.sleep(0.01)
        job = _read_job(workspace, job_id)
        if job is None or job.status != "queued":
            return

        running = job.model_copy(update={"status": "running", "started_at": utc_now_iso()})
        _write_job(workspace, running)

        # Yield so the SSE poll loop observes the 'running' transition
        # before an instant-return executor (e.g. LocalExecutor stub) flips
        # the job to its terminal state.
        await asyncio.sleep(0.02)

        ctx = JobContext(
            job_id=job_id,
            workspace=workspace,
            skill=running.skill,
            inputs=running.inputs,
            params=running.params,
            artifact_root=_artifact_root(workspace, job_id),
            stdout_log=_job_dir(workspace, job_id) / "stdout.log",
        )
        outcome: JobOutcome = await _DEFAULT_EXECUTOR.run(ctx)

        # Cancel may have landed while the executor was running. Don't
        # clobber a terminal state that the cancel handler already wrote.
        job = _read_job(workspace, job_id)
        if job is None or job.status != "running":
            return

        if outcome.exit_code == 0:
            artifact_root = _persist_success_stdout(
                workspace, job_id, stdout_text=outcome.stdout_text,
            )
            final = job.model_copy(update={
                "status": "succeeded",
                "finished_at": utc_now_iso(),
                "exit_code": outcome.exit_code,
                "error": None,
                "artifact_root": artifact_root,
            })
        else:
            artifact_root = _persist_failure_diagnostics(
                workspace,
                job_id,
                stdout_text=outcome.stdout_text or _EXECUTOR_NOT_IMPLEMENTED_LINE,
            )
            final = job.model_copy(update={
                "status": "failed",
                "finished_at": utc_now_iso(),
                "exit_code": outcome.exit_code,
                "error": outcome.error or "executor_not_implemented",
                "artifact_root": artifact_root,
            })
        _write_job(workspace, final)
    finally:
        _STUB_JOB_TASKS.pop(job_id, None)


def _ensure_stub_job(workspace: Path, job_id: str) -> None:
    job = _read_job(workspace, job_id)
    if _is_chat_stream_job(job):
        return
    task = _STUB_JOB_TASKS.get(job_id)
    if task is not None and not task.done():
        return
    _STUB_JOB_TASKS[job_id] = asyncio.create_task(_run_job(workspace, job_id))


def bind_chat_stream_job(workspace: Path, job_id: str, *, session_id: str = "") -> Job:
    job = _read_job(workspace, job_id)
    if job is None:
        raise LookupError(f"job not found: {job_id}")
    if not _is_chat_stream_job(job):
        raise ValueError(f"job is not a chat_stream display job: {job_id}")
    if session_id and job.session_id and job.session_id != session_id:
        raise ValueError(
            f"job session mismatch: expected {job.session_id!r}, got {session_id!r}"
        )
    if job.status == "queued":
        running = job.model_copy(update={
            "status": "running",
            "started_at": job.started_at or utc_now_iso(),
        })
        _write_job(workspace, running)
        return running
    if job.status == "running":
        return job
    if job.status == "canceled":
        return job
    raise ValueError(f"job is already terminal: {job.status}")


def finalize_chat_stream_job(
    workspace: Path,
    job_id: str,
    *,
    status: JobStatus,
    error: str | None = None,
) -> Job:
    if status not in _TERMINAL_STATUSES:
        raise ValueError(f"chat stream job must finalize to a terminal status, got {status}")

    job = _read_job(workspace, job_id)
    if job is None:
        raise LookupError(f"job not found: {job_id}")
    if not _is_chat_stream_job(job):
        raise ValueError(f"job is not a chat_stream display job: {job_id}")
    if job.status == "canceled" and status != "canceled":
        return job
    if job.status in _TERMINAL_STATUSES and job.status == status:
        return job
    if job.status in _TERMINAL_STATUSES and job.status != status:
        return job

    updates: dict[str, object | None] = {
        "status": status,
        "finished_at": utc_now_iso(),
        "started_at": job.started_at or utc_now_iso(),
    }
    if status == "succeeded":
        updates.update({
            "exit_code": 0,
            "error": None,
            "artifact_root": _persist_success_stdout(workspace, job_id, stdout_text=""),
        })
    elif status == "failed":
        message = error or "chat_stream_failed"
        updates.update({
            "exit_code": 1,
            "error": message,
            "artifact_root": _persist_failure_diagnostics(
                workspace,
                job_id,
                stdout_text=message,
            ),
        })
    else:
        updates.update({"error": error or job.error})

    final = job.model_copy(update=updates)
    _write_job(workspace, final)
    return final


@router.post("/jobs", response_model=JobSubmitResponse)
async def submit_job(req: JobSubmitRequest) -> JobSubmitResponse:
    workspace = _resolve_or_400()
    job = Job(
        job_id=uuid.uuid4().hex,
        session_id=req.session_id.strip(),
        skill=req.skill,
        status="queued",
        workspace=str(workspace),
        inputs=req.inputs,
        params=req.params,
        created_at=utc_now_iso(),
    )
    _write_job(workspace, job)
    _ensure_stub_job(workspace, job.job_id)
    return JobSubmitResponse(job_id=job.job_id, status=job.status)


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    status: Optional[JobStatus] = Query(None),
    limit: int = Query(50, ge=1, le=500),
) -> JobListResponse:
    workspace = _resolve_or_400()
    root = jobs_root(workspace)
    rows: list[Job] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        job = _read_job(workspace, entry.name)
        if job is None:
            continue
        if status and job.status != status:
            continue
        rows.append(job)
    rows.sort(key=lambda j: j.created_at, reverse=True)
    total = len(rows)
    rows = rows[:limit]
    return JobListResponse(jobs=rows, total=total)


@router.get("/jobs/{job_id}", response_model=Job)
async def get_job(job_id: str) -> Job:
    workspace = _resolve_or_400()
    job = _read_job(workspace, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    return job


@router.post("/jobs/{job_id}/cancel", response_model=Job)
async def cancel_job(job_id: str) -> Job:
    workspace = _resolve_or_400()
    job = _read_job(workspace, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    if job.status in ("succeeded", "failed", "canceled"):
        return job
    updated = job.model_copy(update={
        "status": "canceled",
        "finished_at": utc_now_iso(),
    })
    _write_job(workspace, updated)

    # Interrupt the in-flight executor task so cooperative cancel paths
    # run (``SubprocessExecutor`` → SIGTERM → SIGKILL). Without this, a
    # long-running skill would keep burning CPU despite the status flip.
    # ``task.cancel()`` on a completed task is a safe no-op.
    task = _STUB_JOB_TASKS.get(job_id)
    if task is not None:
        task.cancel()
    return updated


@router.post("/jobs/{job_id}/retry", response_model=JobSubmitResponse)
async def retry_job(job_id: str) -> JobSubmitResponse:
    workspace = _resolve_or_400()
    original = _read_job(workspace, job_id)
    if original is None:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    if original.status not in _TERMINAL_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"can only retry a finished job; this one is {original.status}",
        )
    clone = Job(
        job_id=uuid.uuid4().hex,
        session_id=original.session_id,
        skill=original.skill,
        status="queued",
        workspace=str(workspace),
        inputs=original.inputs,
        params=original.params,
        created_at=utc_now_iso(),
    )
    _write_job(workspace, clone)
    _ensure_stub_job(workspace, clone.job_id)
    return JobSubmitResponse(job_id=clone.job_id, status=clone.status)


def _parse_resume_cursor(last_event_id: Optional[str]) -> int:
    """Parse ``Last-Event-ID`` into a byte offset.

    Invalid / missing / negative values fall back to ``0`` (fresh stream)
    so the worst case is the pre-resume duplication behaviour, never a
    500.
    """
    if not last_event_id:
        return 0
    try:
        value = int(last_event_id)
    except ValueError:
        return 0
    return value if value > 0 else 0


async def _job_event_stream(
    workspace: Path, job_id: str, *, resume_bytes: int = 0
) -> AsyncIterator[str]:
    job = _read_job(workspace, job_id)
    if job is None:
        yield _sse_event("error", {"error": "job_not_found", "job_id": job_id})
        return

    if job.status == "queued":
        _ensure_stub_job(workspace, job_id)

    stdout_path = _job_dir(workspace, job_id) / "stdout.log"
    bytes_read = resume_bytes
    carry = ""
    last_status: JobStatus | None = None

    while True:
        current = _read_job(workspace, job_id)
        if current is None:
            yield _sse_event("error", {"error": "job_not_found", "job_id": job_id})
            return

        # Drain any new stdout lines *before* a status-change event so the
        # App gets context in the natural order (logs → final banner).
        new_lines, new_bytes, carry = _tail_new_lines(
            stdout_path, bytes_read, carry
        )
        cursor = bytes_read
        for line in new_lines:
            # +1 for the stripped trailing \n.
            cursor += len(line.encode("utf-8")) + 1
            yield _log_event(job_id, line, event_id=cursor)
        bytes_read = new_bytes

        if current.status != last_status:
            yield _sse_event(_status_event_name(current.status), current.model_dump())
            last_status = current.status

        if current.status in _TERMINAL_STATUSES:
            final_lines, new_bytes, carry = _tail_new_lines(
                stdout_path, bytes_read, carry
            )
            cursor = bytes_read
            for line in final_lines:
                cursor += len(line.encode("utf-8")) + 1
                yield _log_event(job_id, line, event_id=cursor)
            bytes_read = new_bytes
            # Flush an unterminated trailing line so the last executor
            # output never gets silently dropped.
            if carry:
                cursor += len(carry.encode("utf-8"))
                yield _log_event(job_id, carry, event_id=cursor)
            yield _sse_event("done", {"job_id": job_id})
            return

        await asyncio.sleep(0.01)


@router.get("/jobs/{job_id}/events")
async def job_events(
    job_id: str,
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    workspace = _resolve_or_400()
    resume_bytes = _parse_resume_cursor(last_event_id)
    return StreamingResponse(
        _job_event_stream(workspace, job_id, resume_bytes=resume_bytes),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
