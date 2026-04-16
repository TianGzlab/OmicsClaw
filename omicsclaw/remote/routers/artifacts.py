"""GET /artifacts?job_id=  +  GET /artifacts/{artifact_id}/download

Artifacts are looked up under ``<workspace>/.omicsclaw/remote/jobs/<job_id>/artifacts/``.
Until the Executor abstraction is wired in, ``GET /artifacts`` returns an
empty list and ``download`` returns 404. The shape stays stable so the App
side ArtifactsBrowser can render an empty state today and gain content
automatically once jobs start producing files.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from omicsclaw.remote.schemas import Artifact, ArtifactListResponse
from omicsclaw.remote.storage import jobs_root, path_modified_at_iso, resolve_workspace

router = APIRouter(tags=["remote"])


def _resolve_or_400() -> Path:
    try:
        return resolve_workspace()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _artifact_id(job_id: str, relative: Path) -> str:
    # Stable, URL-safe id: "<job_id>:<relative-posix-path>".
    return f"{job_id}:{relative.as_posix()}"


def _validate_job_id(job_id: str) -> str:
    candidate = str(job_id or "").strip()
    path = Path(candidate)
    if (
        not candidate
        or ":" in candidate
        or path.is_absolute()
        or len(path.parts) != 1
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise HTTPException(status_code=400, detail="job_id contains an unsafe path")
    return candidate


def _split_artifact_id(artifact_id: str) -> tuple[str, Path]:
    if ":" not in artifact_id:
        raise HTTPException(status_code=400, detail="artifact_id must be 'job_id:relative_path'")
    job_id, _, rel = artifact_id.partition(":")
    safe_job_id = _validate_job_id(job_id)
    rel_path = Path(rel)
    if rel_path.is_absolute() or any(part == ".." for part in rel_path.parts):
        raise HTTPException(status_code=400, detail="artifact_id contains an unsafe relative path")
    return safe_job_id, rel_path


def _artifacts_dir(workspace: Path, job_id: str) -> Path:
    root = jobs_root(workspace).resolve()
    target = (root / _validate_job_id(job_id) / "artifacts").resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="job_id contains an unsafe path") from exc
    return target


def _resolve_artifact_target(base: Path, rel: Path) -> Path:
    target = (base / rel).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="artifact_id escapes artifact root") from exc
    return target


@router.get("/artifacts", response_model=ArtifactListResponse)
async def list_artifacts(job_id: str = Query(...)) -> ArtifactListResponse:
    workspace = _resolve_or_400()
    base = _artifacts_dir(workspace, job_id)
    if not base.is_dir():
        return ArtifactListResponse(artifacts=[], total=0)
    rows: list[Artifact] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        resolved = _resolve_artifact_target(base, path.relative_to(base))
        rel = path.relative_to(base)
        mime, _ = mimetypes.guess_type(str(resolved))
        rows.append(Artifact(
            artifact_id=_artifact_id(job_id, rel),
            job_id=job_id,
            relative_path=rel.as_posix(),
            size_bytes=resolved.stat().st_size,
            mime_type=mime or "application/octet-stream",
            created_at=path_modified_at_iso(resolved),
        ))
    return ArtifactListResponse(artifacts=rows, total=len(rows))


@router.get("/artifacts/{artifact_id:path}/download")
async def download_artifact(artifact_id: str) -> FileResponse:
    workspace = _resolve_or_400()
    job_id, rel = _split_artifact_id(artifact_id)
    base = _artifacts_dir(workspace, job_id)
    target = _resolve_artifact_target(base, rel)
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"artifact not found: {artifact_id}")
    # FileResponse streams + supports Range requests automatically.
    return FileResponse(
        path=target,
        filename=rel.name,
        media_type=mimetypes.guess_type(str(target))[0] or "application/octet-stream",
    )
