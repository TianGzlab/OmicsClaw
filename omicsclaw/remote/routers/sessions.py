"""POST /sessions/{session_id}/resume — reattach to running jobs.

When the App's tunnel drops or the window reopens, the session is asked
"are any of your jobs still alive?". MVP-1 returns the list of active jobs
owned by that session; deeper transcript replay belongs to the chat layer.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from omicsclaw.remote.schemas import Job, SessionResumeResponse
from omicsclaw.remote.storage import jobs_root, resolve_workspace

router = APIRouter(tags=["remote"])


def _resolve_or_400() -> Path:
    try:
        return resolve_workspace()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _read_job(job_file: Path) -> Job | None:
    if not job_file.is_file():
        return None
    try:
        return Job.model_validate_json(job_file.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


@router.post("/sessions/{session_id}/resume", response_model=SessionResumeResponse)
async def resume_session(session_id: str) -> SessionResumeResponse:
    workspace = _resolve_or_400()
    root = jobs_root(workspace)
    active: list[str] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        job = _read_job(entry / "job.json")
        if job is None:
            continue
        if job.session_id != session_id:
            continue
        if job.status in ("queued", "running"):
            active.append(entry.name)
    return SessionResumeResponse(
        session_id=session_id,
        resumed=True,
        reason="" if active else "no_active_jobs",
        active_job_ids=active,
    )
