"""
Browse API — Read/write endpoints for the memory graph (admin pane).

Serves ``/api/browse/*`` for the standalone admin UI shipped by
``oc memory-server``. The path-based read/write logic lives in the
private ``_browse_helpers.BrowseHelpers`` class; this module is just
the FastAPI thin wrapper that translates request params and records
changeset entries.
"""

import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..snapshot import get_changeset_store

router = APIRouter(prefix="/api/browse", tags=["browse"])

# Valid domains from environment or defaults
_DEFAULT_DOMAINS = "core,project,dataset,analysis,preference,insight,notes,session"


def _get_valid_domains():
    raw = os.getenv("OMICSCLAW_MEMORY_VALID_DOMAINS", _DEFAULT_DOMAINS)
    return [d.strip() for d in raw.split(",") if d.strip()]


def _browse_helpers():
    """Build a fresh BrowseHelpers bound to the singleton db + indexer.

    The helper is a thin DB-backed object (no per-process state), so
    re-creating it per request is fine and keeps imports lazy.
    """
    from .. import get_db_manager, get_search_indexer
    from ._browse_helpers import BrowseHelpers

    return BrowseHelpers(get_db_manager(), get_search_indexer())


# ------------------------------------------------------------------
# Pydantic models
# ------------------------------------------------------------------

class CreateMemoryRequest(BaseModel):
    parent_path: str = ""
    content: str
    priority: int = 0
    title: Optional[str] = None
    disclosure: Optional[str] = None
    domain: str = "core"


class UpdateMemoryRequest(BaseModel):
    content: Optional[str] = None
    priority: Optional[int] = None
    disclosure: Optional[str] = None


class AddPathRequest(BaseModel):
    new_path: str
    target_path: str
    new_domain: str = "core"
    target_domain: str = "core"
    priority: int = 0
    disclosure: Optional[str] = None


class AddGlossaryRequest(BaseModel):
    keyword: str
    node_uuid: str


class RemoveGlossaryRequest(BaseModel):
    keyword: str
    node_uuid: str


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get("/domains")
async def list_domains():
    """List configured valid domains with node counts."""
    helpers = _browse_helpers()

    valid = _get_valid_domains()
    result = []
    for d in valid:
        try:
            children = await helpers.get_children(
                node_uuid="00000000-0000-0000-0000-000000000000",
                context_domain=d,
            )
            count = len(children) if children else 0
        except Exception:
            count = 0
        result.append({"domain": d, "root_count": count})
    return result


@router.get("/node")
async def get_node(
    path: str = Query("", description="Node path"),
    domain: str = Query("core", description="Domain"),
):
    """Get a node's current memory content along with children and breadcrumbs."""
    helpers = _browse_helpers()

    result = await helpers.get_memory_by_path(path, domain)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Path '{domain}://{path}' not found")

    children = await helpers.get_children(
        node_uuid=result["node_uuid"],
        context_domain=domain,
        context_path=path,
    )

    breadcrumbs = []
    breadcrumbs.append({"path": "", "name": domain, "domain": domain})

    if path:
        parts = path.split("/")
        current_path = ""
        for p in parts:
            current_path = f"{current_path}/{p}" if current_path else p
            breadcrumbs.append({"path": current_path, "name": p, "domain": domain})

    return {
        "node": result,
        "children": children,
        "breadcrumbs": breadcrumbs
    }


@router.get("/children")
async def get_children(
    node_uuid: str = Query("00000000-0000-0000-0000-000000000000"),
    domain: Optional[str] = Query(None),
    path: Optional[str] = Query(None),
):
    """Get direct children of a node."""
    helpers = _browse_helpers()

    children = await helpers.get_children(
        node_uuid=node_uuid,
        context_domain=domain,
        context_path=path,
    )
    return {"children": children}


@router.get("/paths")
async def get_all_paths(domain: Optional[str] = Query(None)):
    """Get all paths (optionally filtered by domain)."""
    helpers = _browse_helpers()

    paths = await helpers.get_all_paths(domain=domain)
    return {"paths": paths}


@router.get("/search")
async def search_memories(
    q: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=100),
    domain: Optional[str] = Query(None),
):
    """Search memories by content and path."""
    from .. import get_search_indexer
    search = get_search_indexer()

    results = await search.search(q, limit=limit, domain=domain)
    return {"results": results}


@router.get("/recent")
async def get_recent(limit: int = Query(10, ge=1, le=50)):
    """Get recently created/updated memories."""
    helpers = _browse_helpers()

    memories = await helpers.get_recent_memories(limit=limit)
    return {"memories": memories}


@router.post("/create")
async def create_memory(req: CreateMemoryRequest):
    """Create a new memory node."""
    helpers = _browse_helpers()
    store = get_changeset_store()

    valid_domains = _get_valid_domains()
    if req.domain not in valid_domains:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid domain '{req.domain}'. Valid: {valid_domains}",
        )

    try:
        result = await helpers.create_memory(
            parent_path=req.parent_path,
            content=req.content,
            priority=req.priority,
            title=req.title,
            disclosure=req.disclosure,
            domain=req.domain,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    store.record_many(
        before_state={},
        after_state=result.get("rows_after", {}),
    )

    return result


@router.put("/node")
async def update_node(
    path: str = Query(...),
    domain: str = Query("core"),
    req: UpdateMemoryRequest = ...,
):
    """Update a memory's content, priority, or disclosure."""
    import logging
    log = logging.getLogger(__name__)

    helpers = _browse_helpers()
    store = get_changeset_store()

    try:
        result = await helpers.update_memory(
            path=path,
            content=req.content,
            priority=req.priority,
            disclosure=req.disclosure,
            domain=domain,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    rows_before = result.get("rows_before", {})
    rows_after = result.get("rows_after", {})

    log.info(
        "update_node: path=%s domain=%s rows_before_tables=%s rows_after_tables=%s",
        path, domain, list(rows_before.keys()), list(rows_after.keys()),
    )

    store.record_many(
        before_state=rows_before,
        after_state=rows_after,
    )

    return result


@router.post("/add-path")
async def add_path(req: AddPathRequest):
    """Create an alias path for an existing node."""
    helpers = _browse_helpers()
    store = get_changeset_store()

    try:
        result = await helpers.add_path(
            new_path=req.new_path,
            target_path=req.target_path,
            new_domain=req.new_domain,
            target_domain=req.target_domain,
            priority=req.priority,
            disclosure=req.disclosure,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    store.record_many(
        before_state={},
        after_state=result.get("rows_after", {}),
    )

    return result


@router.delete("/path")
async def remove_path(
    path: str = Query(...),
    domain: str = Query("core"),
):
    """Remove a path (with orphan prevention)."""
    helpers = _browse_helpers()
    store = get_changeset_store()

    try:
        result = await helpers.remove_path(path=path, domain=domain)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    store.record_many(
        before_state=result.get("rows_before", {}),
        after_state=result.get("rows_after", {}),
    )

    return result


# ------------------------------------------------------------------
# Glossary endpoints
# ------------------------------------------------------------------


@router.get("/glossary")
async def get_all_glossary():
    """Get all glossary entries."""
    from .. import get_glossary_service
    glossary = get_glossary_service()
    entries = await glossary.get_all_glossary()
    return {"glossary": entries}


@router.get("/glossary/{node_uuid}")
async def get_node_glossary(node_uuid: str):
    """Get glossary keywords for a specific node."""
    from .. import get_glossary_service
    glossary = get_glossary_service()
    keywords = await glossary.get_glossary_for_node(node_uuid)
    return {"keywords": keywords}


@router.post("/glossary")
async def add_glossary(req: AddGlossaryRequest):
    """Add a glossary keyword binding."""
    from .. import get_glossary_service
    glossary = get_glossary_service()
    store = get_changeset_store()

    try:
        result = await glossary.add_glossary_keyword(req.keyword, req.node_uuid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    store.record_many(
        before_state=result.get("rows_before", {}),
        after_state=result.get("rows_after", {}),
    )

    return result


@router.delete("/glossary")
async def remove_glossary(req: RemoveGlossaryRequest):
    """Remove a glossary keyword binding."""
    from .. import get_glossary_service
    glossary = get_glossary_service()
    store = get_changeset_store()

    result = await glossary.remove_glossary_keyword(req.keyword, req.node_uuid)

    store.record_many(
        before_state=result.get("rows_before", {}),
        after_state=result.get("rows_after", {}),
    )

    return result
