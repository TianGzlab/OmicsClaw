"""Dataset registration & retrieval for the remote control plane.

Real implementation (not a placeholder):
- ``POST /datasets/upload``        — multipart upload, fingerprint, persist
- ``POST /datasets/import-remote`` — register a path that already exists on
                                     the server (for users who scp/rsync)
- ``GET  /datasets``               — list registered DatasetRefs
- ``DELETE /datasets/{id}``        — unregister (and for uploads, free disk)

Storage layout (see ``omicsclaw.remote.storage``)::

    <workspace>/.omicsclaw/remote/datasets/<dataset_id>/
        <original_filename>          (upload only)
        meta.json
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile

from omicsclaw.remote.schemas import (
    DatasetImportRemoteRequest,
    DatasetListResponse,
    DatasetRef,
)
from omicsclaw.remote.storage import (
    composite_checksum,
    datasets_root,
    path_modified_at_iso,
    resolve_workspace,
)

router = APIRouter(tags=["remote"])

_MAX_UPLOAD_BYTES = 1024 * 1024 * 1024  # 1 GiB — boring MVP cap


def _meta_path(dataset_dir: Path) -> Path:
    return dataset_dir / "meta.json"


def _read_meta(dataset_dir: Path) -> DatasetRef | None:
    meta = _meta_path(dataset_dir)
    if not meta.is_file():
        return None
    try:
        payload = json.loads(meta.read_text(encoding="utf-8"))
        return DatasetRef.model_validate(payload)
    except (OSError, ValueError):
        return None


def _write_meta(dataset_dir: Path, ref: DatasetRef) -> None:
    _meta_path(dataset_dir).write_text(
        json.dumps(ref.model_dump(), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _find_existing_by_checksum(
    root: Path,
    checksum: str,
    execution_target: str,
    *,
    exclude_dir: Path | None = None,
) -> DatasetRef | None:
    for entry in root.iterdir():
        if not entry.is_dir() or entry == exclude_dir:
            continue
        ref = _read_meta(entry)
        if ref is not None:
            ref = _refresh_dataset_ref(entry, ref)
        if (
            ref is not None
            and ref.checksum == checksum
            and ref.execution_target == execution_target
            and ref.status != "stale"
        ):
            return ref
    return None


def _normalize_execution_target(raw: str) -> str:
    value = str(raw or "").strip()
    if value == "local":
        return value
    if value.startswith("remote:") and value != "remote:":
        return value
    raise HTTPException(
        status_code=400,
        detail="execution_target must be 'local' or 'remote:<profile_id>'",
    )


def _storage_path_from_uri(storage_uri: str) -> Path | None:
    parsed = urlparse(storage_uri)
    if parsed.scheme in ("", "file"):
        return Path(unquote(parsed.path if parsed.scheme else storage_uri))
    return None


def _refresh_dataset_ref(dataset_dir: Path, ref: DatasetRef) -> DatasetRef:
    storage_path = _storage_path_from_uri(ref.storage_uri)
    storage_exists = storage_path is None or storage_path.exists()
    expected_status = ref.status
    if storage_exists and ref.status == "stale":
        expected_status = "synced"
    elif not storage_exists:
        expected_status = "stale"

    if expected_status == ref.status:
        return ref

    updated = ref.model_copy(update={"status": expected_status})
    _write_meta(dataset_dir, updated)
    return updated


def _resolve_or_400() -> Path:
    try:
        return resolve_workspace()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _validate_dataset_id(dataset_id: str) -> str:
    """Reject path-traversal / absolute / multi-segment ids.

    Same shape as ``artifacts._validate_job_id`` — dataset_id must be a
    single safe path component so ``datasets_root / id`` can never
    escape the workspace.
    """
    candidate = str(dataset_id or "").strip()
    path = Path(candidate)
    if (
        not candidate
        or path.is_absolute()
        or len(path.parts) != 1
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise HTTPException(
            status_code=400, detail="dataset_id contains an unsafe path"
        )
    return candidate


@router.get("/datasets", response_model=DatasetListResponse)
async def list_datasets() -> DatasetListResponse:
    workspace = _resolve_or_400()
    root = datasets_root(workspace)
    refs: list[DatasetRef] = []
    for entry in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not entry.is_dir():
            continue
        ref = _read_meta(entry)
        if ref is not None:
            refs.append(_refresh_dataset_ref(entry, ref))
    return DatasetListResponse(
        datasets=refs,
        total=len(refs),
        workspace=str(workspace),
    )


@router.post("/datasets/upload", response_model=DatasetRef)
async def upload_dataset(
    file: UploadFile = File(...),
    display_name: str = Form(""),
    execution_target: str = Form(...),
) -> DatasetRef:
    workspace = _resolve_or_400()
    root = datasets_root(workspace)
    normalized_execution_target = _normalize_execution_target(execution_target)
    dataset_id = uuid.uuid4().hex
    dataset_dir = root / dataset_id
    dataset_dir.mkdir(parents=True, exist_ok=False)

    safe_name = Path(file.filename or "dataset.bin").name
    target = dataset_dir / safe_name
    written = 0
    try:
        with target.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > _MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"upload exceeds {_MAX_UPLOAD_BYTES} bytes; use "
                            "POST /datasets/import-remote after scp/rsync"
                        ),
                    )
                out.write(chunk)
    except HTTPException:
        shutil.rmtree(dataset_dir, ignore_errors=True)
        raise
    except OSError as exc:
        shutil.rmtree(dataset_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"failed to persist upload: {exc}") from exc
    finally:
        await file.close()

    checksum = composite_checksum(target)
    existing = _find_existing_by_checksum(
        root,
        checksum,
        normalized_execution_target,
        exclude_dir=dataset_dir,
    )
    if existing is not None:
        shutil.rmtree(dataset_dir, ignore_errors=True)
        return _refresh_dataset_ref(root / existing.dataset_id, existing)

    ref = DatasetRef(
        dataset_id=dataset_id,
        display_name=(display_name or safe_name).strip(),
        storage_uri=target.as_uri(),
        execution_target=normalized_execution_target,
        checksum=checksum,
        size_bytes=target.stat().st_size,
        modified_at=path_modified_at_iso(target),
        status="synced",
    )
    _write_meta(dataset_dir, ref)
    return ref


@router.post("/datasets/import-remote", response_model=DatasetRef)
async def import_remote_dataset(req: DatasetImportRemoteRequest) -> DatasetRef:
    workspace = _resolve_or_400()
    normalized_execution_target = _normalize_execution_target(req.execution_target)
    src = Path(req.remote_path).expanduser()
    if not src.is_absolute():
        raise HTTPException(status_code=400, detail="remote_path must be absolute")
    if not src.is_file():
        raise HTTPException(status_code=404, detail=f"file not found on server: {src}")

    root = datasets_root(workspace)
    checksum = composite_checksum(src)
    existing = _find_existing_by_checksum(root, checksum, normalized_execution_target)
    if existing is not None:
        return _refresh_dataset_ref(root / existing.dataset_id, existing)

    dataset_id = uuid.uuid4().hex
    dataset_dir = root / dataset_id
    dataset_dir.mkdir(parents=True, exist_ok=False)

    ref = DatasetRef(
        dataset_id=dataset_id,
        display_name=(req.display_name or src.name).strip(),
        storage_uri=src.resolve().as_uri(),
        execution_target=normalized_execution_target,
        checksum=checksum,
        size_bytes=src.stat().st_size,
        modified_at=path_modified_at_iso(src),
        status="synced",
    )
    _write_meta(dataset_dir, ref)
    return ref


@router.delete("/datasets/{dataset_id}", status_code=204)
async def delete_dataset(dataset_id: str) -> Response:
    """Unregister a dataset.

    Upload-type datasets: removing the dataset dir frees the stored
    file plus ``meta.json``.

    Import-remote datasets: the dataset dir holds ONLY ``meta.json`` —
    the user's source file at ``storage_uri`` lives outside the
    workspace and is deliberately NOT touched. Rmtree on the workspace-
    local dataset dir is therefore safe for both shapes.
    """
    workspace = _resolve_or_400()
    safe_id = _validate_dataset_id(dataset_id)
    dataset_dir = datasets_root(workspace) / safe_id
    if not dataset_dir.is_dir():
        raise HTTPException(
            status_code=404, detail=f"dataset not found: {safe_id}"
        )
    shutil.rmtree(dataset_dir)
    return Response(status_code=204)
