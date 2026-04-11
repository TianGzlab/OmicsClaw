"""FastAPI router exposing the notebook kernel manager.

Mounted under the `/notebook` prefix by `omicsclaw.app.server`. The Next.js
layer proxies requests here from `src/app/api/notebook/*/route.ts`.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import nb_files, var_inspector
from .kernel_manager import get_kernel_manager

log = logging.getLogger(__name__)

router = APIRouter(tags=["notebook"])


class NotebookLocatorRequest(BaseModel):
    """Every kernel-aware route takes the same locator shape: a trusted
    ``workspace`` plus the absolute ``file_path`` of the ``.ipynb``. The
    router derives the stable kernel id from ``realpath(file_path)``, so
    the client never needs (and can no longer send) a ``notebook_id``.
    """

    workspace: Optional[str] = None
    file_path: Optional[str] = None


class KernelStartRequest(NotebookLocatorRequest):
    cwd: Optional[str] = None


class KernelIdRequest(NotebookLocatorRequest):
    pass


class ExecuteRequest(NotebookLocatorRequest):
    cell_id: str = Field(..., min_length=1)
    code: str
    cwd: Optional[str] = None


class CompleteRequest(NotebookLocatorRequest):
    code: str
    cursor_pos: int = Field(..., ge=0)


class InspectRequest(NotebookLocatorRequest):
    pass


def _resolve_notebook_target(
    file_path: Optional[str],
    workspace: Optional[str] = None,
) -> tuple[str, str]:
    if not file_path:
        raise HTTPException(
            status_code=400,
            detail="file_path is required",
        )
    try:
        return nb_files.resolve_workspace_notebook_target(file_path, workspace)
    except Exception as exc:
        raise _notebook_error(exc)


def _resolve_kernel_request(
    file_path: Optional[str],
    workspace: Optional[str] = None,
    cwd: Optional[str] = None,
) -> tuple[str, str, str]:
    """Single entry point for every kernel-aware route.

    Returns ``(notebook_id, resolved_file_path, resolved_cwd)``. The
    ``notebook_id`` is derived internally from ``realpath(file_path)`` —
    the client never supplies it. This is what prevents the "same
    notebook, two kernels" race the legacy dual-track contract used to
    allow (a ``notebook_id``-only request would bypass live-session
    binding and silently spawn a local kernel next to a running live
    one).
    """
    _, resolved_file_path = _resolve_notebook_target(file_path, workspace)
    if Path(resolved_file_path).suffix.lower() != ".ipynb":
        raise HTTPException(status_code=400, detail="file_path must end with .ipynb")
    return (
        nb_files.derive_notebook_id(resolved_file_path),
        resolved_file_path,
        cwd if cwd is not None else str(Path(resolved_file_path).parent),
    )


@router.post("/kernel/start")
async def kernel_start(req: KernelStartRequest) -> dict:
    manager = get_kernel_manager()
    resolved_notebook_id, resolved_file_path, resolved_cwd = _resolve_kernel_request(
        req.file_path,
        req.workspace,
        req.cwd,
    )
    try:
        started = await manager.start(
            resolved_notebook_id,
            cwd=resolved_cwd,
            file_path=resolved_file_path,
        )
    except Exception as exc:
        log.exception("[notebook] kernel start failed")
        raise HTTPException(status_code=500, detail=f"kernel start failed: {exc}")
    return started


@router.post("/kernel/stop")
async def kernel_stop(req: KernelIdRequest) -> dict:
    manager = get_kernel_manager()
    resolved_notebook_id, resolved_file_path, _ = _resolve_kernel_request(
        req.file_path,
        req.workspace,
    )
    stopped = await manager.stop(resolved_notebook_id, file_path=resolved_file_path)
    return {"notebook_id": resolved_notebook_id, "stopped": stopped}


@router.post("/kernel/interrupt")
async def kernel_interrupt(req: KernelIdRequest) -> dict:
    manager = get_kernel_manager()
    resolved_notebook_id, resolved_file_path, _ = _resolve_kernel_request(
        req.file_path,
        req.workspace,
    )
    interrupted = await manager.interrupt(resolved_notebook_id, file_path=resolved_file_path)
    if not interrupted:
        raise HTTPException(status_code=404, detail="no kernel for that notebook")
    return {"notebook_id": resolved_notebook_id, "interrupted": True}


@router.get("/kernel/status")
async def kernel_status(
    workspace: Optional[str] = Query(default=None),
    file_path: Optional[str] = Query(default=None),
) -> dict:
    manager = get_kernel_manager()
    resolved_notebook_id, resolved_file_path, _ = _resolve_kernel_request(
        file_path,
        workspace,
    )
    return await manager.status(resolved_notebook_id, file_path=resolved_file_path)


@router.post("/complete")
async def complete(req: CompleteRequest) -> dict:
    manager = get_kernel_manager()
    resolved_notebook_id, resolved_file_path, _ = _resolve_kernel_request(
        req.file_path,
        req.workspace,
    )
    try:
        result = await manager.complete(
            notebook_id=resolved_notebook_id,
            code=req.code,
            cursor_pos=req.cursor_pos,
            file_path=resolved_file_path,
        )
    except Exception as exc:
        log.exception("[notebook] complete failed")
        raise HTTPException(status_code=500, detail=f"complete failed: {exc}")
    return result


@router.post("/inspect")
async def inspect(req: InspectRequest) -> dict:
    manager = get_kernel_manager()
    resolved_notebook_id, resolved_file_path, _ = _resolve_kernel_request(
        req.file_path,
        req.workspace,
    )
    try:
        return await manager.inspect(resolved_notebook_id, file_path=resolved_file_path)
    except Exception as exc:
        log.exception("[notebook] inspect failed")
        raise HTTPException(status_code=500, detail=f"inspect failed: {exc}")


def _format_sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/execute")
async def execute(req: ExecuteRequest) -> StreamingResponse:
    manager = get_kernel_manager()

    # Resolve the notebook target BEFORE returning the streaming response.
    # Previously this happened inside the generator, so any
    # workspace/file_path validation error (e.g. "outside the trusted
    # scope", "file_path must end with .ipynb") would be swallowed into
    # a generic SSE error + stream truncation on the frontend. Lifting
    # the resolution up means ValueError / HTTPException surface as real
    # HTTP 4xx with their actual message, which is what the UI (and any
    # debugging user) actually needs.
    resolved_notebook_id, resolved_file_path, resolved_cwd = _resolve_kernel_request(
        req.file_path,
        req.workspace,
        req.cwd,
    )

    async def event_stream() -> AsyncIterator[bytes]:
        try:
            async for event in manager.execute_stream(
                notebook_id=resolved_notebook_id,
                cell_id=req.cell_id,
                code=req.code,
                cwd=resolved_cwd,
                file_path=resolved_file_path,
            ):
                yield _format_sse(event).encode("utf-8")
        except Exception as exc:  # pragma: no cover
            log.exception("[notebook] execute_stream failed")
            yield _format_sse(
                {
                    "type": "error",
                    "data": {
                        "cell_id": req.cell_id,
                        "ename": type(exc).__name__,
                        "evalue": str(exc),
                        "traceback": [],
                    },
                }
            ).encode("utf-8")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Variable inspection (var_detail, adata_slot)
# ---------------------------------------------------------------------------


class VarDetailRequest(NotebookLocatorRequest):
    name: str = Field(..., min_length=1)
    max_rows: int = Field(default=50, ge=1, le=500)
    max_cols: int = Field(default=50, ge=1, le=200)


class AdataSlotRequest(NotebookLocatorRequest):
    var_name: str = Field(..., min_length=1)
    slot: str = Field(..., min_length=1)
    key: str = ""
    max_rows: int = Field(default=50, ge=1, le=500)
    max_cols: int = Field(default=50, ge=1, le=200)


@router.post("/var_detail")
async def var_detail(req: VarDetailRequest) -> dict:
    """Return a rich preview (DataFrame table / AnnData summary / scalar repr).

    Takes the same ``workspace + file_path`` locator as every other
    kernel-aware route — the client no longer supplies a ``notebook_id``.
    """
    try:
        script = var_inspector.build_var_detail_script(
            req.name,
            max_rows=req.max_rows,
            max_cols=req.max_cols,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    resolved_notebook_id, resolved_file_path, _ = _resolve_kernel_request(
        req.file_path,
        req.workspace,
    )

    manager = get_kernel_manager()
    try:
        stdout, kernel_status = await manager.run_stdout_script(
            resolved_notebook_id,
            script,
            file_path=resolved_file_path,
        )
    except Exception as exc:
        log.exception("[notebook] var_detail failed")
        raise HTTPException(status_code=500, detail=f"var_detail failed: {exc}")

    payload = var_inspector.parse_var_detail_payload(stdout)
    return {"payload": payload, "kernel_status": kernel_status}


@router.post("/adata_slot")
async def adata_slot(req: AdataSlotRequest) -> dict:
    """Drill into ``adata.<slot>[<key>]`` and return a slice preview.

    Takes the same ``workspace + file_path`` locator as every other
    kernel-aware route — the client no longer supplies a ``notebook_id``.
    """
    try:
        script = var_inspector.build_adata_slot_script(
            req.var_name,
            req.slot,
            req.key,
            max_rows=req.max_rows,
            max_cols=req.max_cols,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    resolved_notebook_id, resolved_file_path, _ = _resolve_kernel_request(
        req.file_path,
        req.workspace,
    )

    manager = get_kernel_manager()
    try:
        stdout, kernel_status = await manager.run_stdout_script(
            resolved_notebook_id,
            script,
            file_path=resolved_file_path,
        )
    except Exception as exc:
        log.exception("[notebook] adata_slot failed")
        raise HTTPException(status_code=500, detail=f"adata_slot failed: {exc}")

    payload = var_inspector.parse_var_detail_payload(stdout)
    return {"payload": payload, "kernel_status": kernel_status}


# ---------------------------------------------------------------------------
# Notebook file CRUD — both `/notebook/files/*` and flat `/notebook/*`
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Notebook file CRUD — single-track workspace + path contract.
#
# Every route below takes the same shape: a trusted ``workspace`` and an
# absolute ``path`` (or ``file_path`` for kernel routes) of the target
# ``.ipynb``. The legacy ``root + filename`` payload used to exist as a
# parallel track; it has been removed to close the "same notebook, two
# kernels" race — a legacy-shape save path rebuilt notebook metadata
# from scratch, throwing away kernelspec/language_info and leaving the
# frontend and a live kernel looking at different snapshots of state.
# ---------------------------------------------------------------------------


class NotebookUploadResponse(BaseModel):
    filename: str
    cells: list[dict[str, Any]]


class NotebookWorkspaceRequest(BaseModel):
    """Body used by ``/create`` when no path is specified — picks an
    ``Untitled-N.ipynb`` name inside ``workspace/notebooks/``."""

    workspace: str = Field(..., min_length=1)


class NotebookPathRequest(BaseModel):
    """Body used by ``/create`` (with explicit target), ``/save``, and
    ``/delete``. ``path`` is an absolute ``.ipynb`` path inside the
    workspace."""

    workspace: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)


class NotebookSavePayload(NotebookPathRequest):
    notebook: dict[str, Any]


class NotebookRenameRequest(NotebookPathRequest):
    """Rename a notebook inside its current directory. ``new_name`` is
    the target basename (with or without the ``.ipynb`` suffix — the
    filesystem layer auto-appends it). Cross-directory moves are not
    supported by this route on purpose."""

    new_name: str = Field(..., min_length=1)


def _notebook_error(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


async def _delete_workspace_path(workspace: str, target: str) -> tuple[str, str]:
    workspace_real, target_real = nb_files.resolve_workspace_notebook_target(target, workspace)
    manager = get_kernel_manager()
    notebook_id = nb_files.derive_notebook_id(target_real)
    status = await manager.status(notebook_id, file_path=target_real)
    if status.get("source") == "live" and status.get("running"):
        raise HTTPException(status_code=409, detail="cannot delete a live pipeline notebook")
    await manager.stop(notebook_id, file_path=target_real)
    deleted = nb_files.delete_workspace_notebook(workspace_real, target_real)
    return workspace_real, deleted


async def _rename_workspace_path(
    workspace: str,
    target: str,
    new_name: str,
) -> tuple[str, str]:
    """Stop the local kernel (if any), then rename on disk.

    Mirrors the delete flow because the kernel identity for a notebook
    is ``sha256(realpath(file_path))[:24]`` — after the file moves, the
    old kernel would be orphaned under its old id, and a fresh one
    would start under the new id on the next execute. Stopping the old
    kernel up front keeps the registry clean and prevents the "two
    kernels for the same notebook" confusion. Live-pipeline notebooks
    are refused entirely — their state is owned by the upstream
    session, not something we should move under it.
    """
    workspace_real, src_real = nb_files.resolve_workspace_notebook_target(
        target, workspace
    )
    manager = get_kernel_manager()
    notebook_id = nb_files.derive_notebook_id(src_real)
    status = await manager.status(notebook_id, file_path=src_real)
    if status.get("source") == "live" and status.get("running"):
        raise HTTPException(
            status_code=409,
            detail="cannot rename a live pipeline notebook",
        )
    await manager.stop(notebook_id, file_path=src_real)
    renamed = nb_files.rename_workspace_notebook(workspace_real, src_real, new_name)
    return workspace_real, renamed


@router.post("/files/upload")
async def files_upload(file: UploadFile = File(...)) -> dict:
    """Parse an uploaded ``.ipynb`` byte blob into JSON cells.

    This is the only remaining ``/files/*`` route — it is pure bytes-in,
    JSON-out and never touches the trusted-workspace model, so it can
    coexist with the workspace-scoped CRUD below without re-introducing a
    dual track.
    """
    filename = file.filename or ""
    if not filename.endswith(".ipynb"):
        raise HTTPException(status_code=400, detail="filename must end with .ipynb")
    raw = await file.read()
    try:
        cells = nb_files.parse_ipynb_bytes(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"filename": filename, "cells": cells}


@router.get("/list")
async def notebook_list(workspace: str = Query(..., min_length=1)) -> dict:
    try:
        workspace_real = nb_files.resolve_workspace_root(workspace)
        listing = nb_files.list_workspace_notebooks(workspace)
    except Exception as exc:
        raise _notebook_error(exc)
    return {"root": workspace_real, **listing}


@router.get("/open")
async def notebook_open_get(
    path: str = Query(..., min_length=1),
    workspace: Optional[str] = Query(default=None),
) -> dict:
    try:
        workspace_real, target_real, notebook = nb_files.open_workspace_notebook(path, workspace)
    except Exception as exc:
        raise _notebook_error(exc)
    return {"path": target_real, "workspace": workspace_real, "notebook": notebook}


@router.post("/create")
async def notebook_create(request: Request) -> dict:
    """Create an empty notebook inside a trusted workspace.

    Accepts two body shapes — both workspace-scoped:
    * ``{workspace}`` — auto-picks ``notebooks/Untitled-N.ipynb``
    * ``{workspace, path}`` — creates exactly ``path`` (must be absolute
      and inside ``workspace``)
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Request body must be JSON")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Request body must be JSON")

    if "path" in body and body["path"]:
        req = NotebookPathRequest(**body)
        try:
            workspace_real = nb_files.resolve_workspace_root(req.workspace)
            created = nb_files.create_workspace_notebook_at(workspace_real, req.path)
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except Exception as exc:
            raise _notebook_error(exc)
        return {"workspace": workspace_real, "path": created}

    req_ws = NotebookWorkspaceRequest(**body)
    try:
        created = nb_files.create_workspace_notebook(req_ws.workspace)
    except Exception as exc:
        raise _notebook_error(exc)
    return {"path": created}


@router.post("/save")
async def notebook_save(req: NotebookSavePayload) -> dict:
    try:
        path = nb_files.save_workspace_notebook(req.workspace, req.path, req.notebook)
    except Exception as exc:
        raise _notebook_error(exc)
    return {"path": path, "savedAt": int(time.time() * 1000)}


@router.post("/delete")
async def notebook_delete(req: NotebookPathRequest) -> dict:
    try:
        workspace_real, path = await _delete_workspace_path(req.workspace, req.path)
    except Exception as exc:
        raise _notebook_error(exc)
    return {"path": path, "workspace": workspace_real}


@router.post("/rename")
async def notebook_rename(req: NotebookRenameRequest) -> dict:
    try:
        workspace_real, path = await _rename_workspace_path(
            req.workspace,
            req.path,
            req.new_name,
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise _notebook_error(exc)
    return {"path": path, "workspace": workspace_real}
