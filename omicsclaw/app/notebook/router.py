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
    notebook_id: Optional[str] = Field(default=None, min_length=1)
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
) -> tuple[Optional[str], Optional[str]]:
    if not file_path:
        return None, None
    try:
        return nb_files.resolve_workspace_notebook_target(file_path, workspace)
    except Exception as exc:
        raise _notebook_error(exc)


def _resolve_kernel_request(
    notebook_id: Optional[str],
    file_path: Optional[str] = None,
    workspace: Optional[str] = None,
    cwd: Optional[str] = None,
) -> tuple[str, Optional[str], Optional[str]]:
    _, resolved_file_path = _resolve_notebook_target(file_path, workspace)
    if resolved_file_path is not None:
        if Path(resolved_file_path).suffix.lower() != ".ipynb":
            raise HTTPException(status_code=400, detail="file_path must end with .ipynb")
        return (
            nb_files.derive_notebook_id(resolved_file_path),
            resolved_file_path,
            str(Path(resolved_file_path).parent),
        )
    if notebook_id:
        return notebook_id, None, cwd
    raise HTTPException(status_code=400, detail="notebook_id or file_path is required")


@router.post("/kernel/start")
async def kernel_start(req: KernelStartRequest) -> dict:
    manager = get_kernel_manager()
    resolved_notebook_id, resolved_file_path, resolved_cwd = _resolve_kernel_request(
        req.notebook_id,
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
        req.notebook_id,
        req.file_path,
        req.workspace,
    )
    stopped = await manager.stop(resolved_notebook_id, file_path=resolved_file_path)
    return {"notebook_id": resolved_notebook_id, "stopped": stopped}


@router.post("/kernel/interrupt")
async def kernel_interrupt(req: KernelIdRequest) -> dict:
    manager = get_kernel_manager()
    resolved_notebook_id, resolved_file_path, _ = _resolve_kernel_request(
        req.notebook_id,
        req.file_path,
        req.workspace,
    )
    interrupted = await manager.interrupt(resolved_notebook_id, file_path=resolved_file_path)
    if not interrupted:
        raise HTTPException(status_code=404, detail="no kernel for that notebook_id")
    return {"notebook_id": resolved_notebook_id, "interrupted": True}


@router.get("/kernel/status")
async def kernel_status(
    notebook_id: Optional[str] = Query(default=None, min_length=1),
    workspace: Optional[str] = Query(default=None),
    file_path: Optional[str] = Query(default=None),
) -> dict:
    manager = get_kernel_manager()
    resolved_notebook_id, resolved_file_path, _ = _resolve_kernel_request(
        notebook_id,
        file_path,
        workspace,
    )
    return await manager.status(resolved_notebook_id, file_path=resolved_file_path)


@router.post("/complete")
async def complete(req: CompleteRequest) -> dict:
    manager = get_kernel_manager()
    resolved_notebook_id, resolved_file_path, _ = _resolve_kernel_request(
        req.notebook_id,
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
        req.notebook_id,
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

    async def event_stream() -> AsyncIterator[bytes]:
        resolved_notebook_id, resolved_file_path, resolved_cwd = _resolve_kernel_request(
            req.notebook_id,
            req.file_path,
            req.workspace,
            req.cwd,
        )
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


class VarDetailRequest(BaseModel):
    notebook_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    max_rows: int = Field(default=50, ge=1, le=500)
    max_cols: int = Field(default=50, ge=1, le=200)
    file_path: Optional[str] = None


class AdataSlotRequest(BaseModel):
    notebook_id: str = Field(..., min_length=1)
    var_name: str = Field(..., min_length=1)
    slot: str = Field(..., min_length=1)
    key: str = ""
    max_rows: int = Field(default=50, ge=1, le=500)
    max_cols: int = Field(default=50, ge=1, le=200)
    file_path: Optional[str] = None


@router.post("/var_detail")
async def var_detail(req: VarDetailRequest) -> dict:
    """Return a rich preview (DataFrame table / AnnData summary / scalar repr)."""
    try:
        script = var_inspector.build_var_detail_script(
            req.name,
            max_rows=req.max_rows,
            max_cols=req.max_cols,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    manager = get_kernel_manager()
    try:
        stdout, kernel_status = await manager.run_stdout_script(
            req.notebook_id,
            script,
            file_path=req.file_path,
        )
    except Exception as exc:
        log.exception("[notebook] var_detail failed")
        raise HTTPException(status_code=500, detail=f"var_detail failed: {exc}")

    payload = var_inspector.parse_var_detail_payload(stdout)
    return {"payload": payload, "kernel_status": kernel_status}


@router.post("/adata_slot")
async def adata_slot(req: AdataSlotRequest) -> dict:
    """Drill into ``adata.<slot>[<key>]`` and return a slice preview."""
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

    manager = get_kernel_manager()
    try:
        stdout, kernel_status = await manager.run_stdout_script(
            req.notebook_id,
            script,
            file_path=req.file_path,
        )
    except Exception as exc:
        log.exception("[notebook] adata_slot failed")
        raise HTTPException(status_code=500, detail=f"adata_slot failed: {exc}")

    payload = var_inspector.parse_var_detail_payload(stdout)
    return {"payload": payload, "kernel_status": kernel_status}


# ---------------------------------------------------------------------------
# Notebook file CRUD — both `/notebook/files/*` and flat `/notebook/*`
# ---------------------------------------------------------------------------


class NotebookTargetRequest(BaseModel):
    root: str = Field(..., min_length=1)
    filename: str = Field(..., min_length=1)


class NotebookSaveRequest(BaseModel):
    root: str = Field(..., min_length=1)
    filename: str = Field(..., min_length=1)
    cells: list[dict[str, Any]] = Field(default_factory=list)


def _list_impl(root: str) -> dict:
    return {"files": nb_files.list_ipynb_files(root), "root": root}


def _open_impl(req: NotebookTargetRequest) -> dict:
    try:
        path = nb_files.resolve_ipynb_path(req.root, req.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="notebook not found")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"read failed: {exc}")
    try:
        cells = nb_files.parse_ipynb_bytes(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"filename": req.filename, "root": req.root, "cells": cells}


async def _upload_impl(file: UploadFile) -> dict:
    filename = file.filename or ""
    if not filename.endswith(".ipynb"):
        raise HTTPException(status_code=400, detail="filename must end with .ipynb")
    raw = await file.read()
    try:
        cells = nb_files.parse_ipynb_bytes(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"filename": filename, "cells": cells}


def _notebook_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def _decode_json_body(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Request body must be JSON")
    return body


async def _read_json_body(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Request body must be JSON")
    return _decode_json_body(body)


# --- /notebook/files/* (low-level file helpers) ---------------------------


@router.get("/files/list")
async def files_list(root: str = Query(..., min_length=1)) -> dict:
    return _list_impl(root)


@router.post("/files/upload")
async def files_upload(file: UploadFile = File(...)) -> dict:
    return await _upload_impl(file)


@router.post("/files/open")
async def files_open(req: NotebookTargetRequest) -> dict:
    return _open_impl(req)


# --- /notebook/{list,open,create,save,delete} (flat CRUD) -----------------


@router.get("/list")
async def notebook_list(
    root: Optional[str] = Query(default=None),
    workspace: Optional[str] = Query(default=None),
) -> dict:
    if workspace:
        try:
            workspace_real = nb_files.resolve_workspace_root(workspace)
            notebooks = nb_files.list_workspace_notebooks(workspace)
        except Exception as exc:
            raise _notebook_error(exc)
        return {"root": workspace_real, "notebooks": notebooks}

    if root:
        return _list_impl(root)

    raise HTTPException(status_code=400, detail="workspace or root is required")


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


@router.post("/open")
async def notebook_open(req: NotebookTargetRequest) -> dict:
    return _open_impl(req)


@router.post("/create")
async def notebook_create(request: Request) -> dict:
    body = await _read_json_body(request)

    if body.get("workspace") and not body.get("root") and not body.get("filename"):
        try:
            path = nb_files.create_workspace_notebook(str(body.get("workspace")))
        except Exception as exc:
            raise _notebook_error(exc)
        return {"path": path}

    req = NotebookTargetRequest(**body)
    try:
        path = nb_files.create_empty_notebook(req.root, req.filename)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"filename": req.filename, "root": req.root, "path": path}


@router.post("/save")
async def notebook_save(request: Request) -> dict:
    body = await _read_json_body(request)

    if body.get("workspace") and body.get("path") and body.get("notebook") is not None:
        try:
            path = nb_files.save_workspace_notebook(
                str(body.get("workspace")),
                str(body.get("path")),
                body.get("notebook"),
            )
        except Exception as exc:
            raise _notebook_error(exc)
        return {"path": path, "savedAt": int(time.time() * 1000)}

    req = NotebookSaveRequest(**body)
    try:
        path = nb_files.save_notebook(req.root, req.filename, req.cells)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"save failed: {exc}")
    return {"filename": req.filename, "root": req.root, "path": path}


@router.post("/delete")
async def notebook_delete(request: Request) -> dict:
    body = await _read_json_body(request)

    if body.get("workspace") and body.get("path") and not body.get("root") and not body.get("filename"):
        try:
            manager = get_kernel_manager()
            target_path = str(body.get("path"))
            await manager.stop(nb_files.derive_notebook_id(target_path), file_path=target_path)
            path = nb_files.delete_workspace_notebook(
                str(body.get("workspace")),
                target_path,
            )
        except Exception as exc:
            raise _notebook_error(exc)
        return {"path": path}

    req = NotebookTargetRequest(**body)
    try:
        nb_files.delete_notebook(req.root, req.filename)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="notebook not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"filename": req.filename, "root": req.root, "deleted": True}
