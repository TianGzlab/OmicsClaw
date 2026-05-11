"""
Review API — Endpoints for reviewing AI changes and performing rollbacks.

Routes the desktop ``/api/review/*`` traffic through ``ReviewLog`` and
``MemoryEngine``. The legacy JSON contract is preserved so the
OmicsClaw-App frontend keeps working unchanged.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..snapshot import _rows_equal, get_changeset_store

router = APIRouter(prefix="/api/review", tags=["review"])


class RollbackRequest(BaseModel):
    """Request to rollback specific changes."""
    keys: List[str]


class IntegrateRequest(BaseModel):
    """Request to accept specific pending changes."""
    keys: List[str]


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get("/changes")
async def get_changes():
    """Get all pending AI changes grouped by affected node."""
    store = get_changeset_store()

    all_rows = store.get_all_rows_dict()
    changed_keys = set()
    for key, entry in all_rows.items():
        table = entry.get("table", "")
        before = entry.get("before")
        after = entry.get("after")
        if not _rows_equal(table, before, after):
            changed_keys.add(key)

    change_count = len(changed_keys)

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for key in changed_keys:
        entry = all_rows[key]
        table = entry.get("table", "unknown")
        before = entry.get("before")
        after = entry.get("after")
        ref = after or before

        node_uuid = None
        if ref:
            if table == "nodes":
                node_uuid = ref.get("uuid")
            elif table == "memories":
                node_uuid = ref.get("node_uuid")
            elif table == "edges":
                node_uuid = ref.get("child_uuid")
            elif table == "paths":
                node_uuid = ref.get("node_uuid")
                if not node_uuid:
                    edge_id = ref.get("edge_id")
                    if edge_id:
                        edge_key = f"edges:{edge_id}"
                        edge_entry = all_rows.get(edge_key)
                        if edge_entry:
                            edge_ref = edge_entry.get("after") or edge_entry.get("before")
                            if edge_ref:
                                node_uuid = edge_ref.get("child_uuid")
            elif table == "glossary_keywords":
                node_uuid = ref.get("node_uuid")

        if not node_uuid:
            node_uuid = "_unknown_"

        if node_uuid not in groups:
            groups[node_uuid] = []

        entry_with_key = {**entry, "key": key}
        groups[node_uuid].append(entry_with_key)

    return {
        "change_count": change_count,
        "groups": groups,
    }


@router.get("/change-count")
async def get_change_count():
    """Get the number of pending changes."""
    store = get_changeset_store()
    return {"count": store.get_change_count()}


@router.get("/diff")
async def get_diff(key: str = Query(..., description="Change key to diff")):
    """Get before/after diff for a specific change."""
    store = get_changeset_store()
    all_rows = store.get_all_rows_dict()

    entry = all_rows.get(key)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Change key '{key}' not found")

    table = entry.get("table", "unknown")
    before = entry.get("before")
    after = entry.get("after")

    # For memory rows the snapshot only carries the ref; resolve full
    # content from the live DB via ReviewLog so the UI can render diffs.
    if table == "memories":
        from .. import get_review_log
        review = get_review_log()

        if before and "id" in before:
            mem = await review.get_memory_by_id(before["id"])
            if mem:
                before = {**before, "content": mem.get("content", "")}

        if after and "id" in after:
            mem = await review.get_memory_by_id(after["id"])
            if mem:
                after = {**after, "content": mem.get("content", "")}

    return {
        "key": key,
        "table": table,
        "before": before,
        "after": after,
    }


@router.post("/rollback")
async def rollback_changes(req: RollbackRequest):
    """Rollback specific changes by their keys."""
    store = get_changeset_store()
    all_rows = store.get_all_rows_dict()

    from .. import get_memory_engine, get_review_log

    engine = get_memory_engine()
    review = get_review_log()

    errors: List[Dict[str, Any]] = []
    rolled_back: List[str] = []

    for key in req.keys:
        entry = all_rows.get(key)
        if not entry:
            errors.append({"key": key, "error": "Not found"})
            continue

        table = entry.get("table", "unknown")
        before = entry.get("before")
        after = entry.get("after")

        try:
            if table == "memories" and before and after:
                # Content was updated: rollback to the old memory version.
                old_id = before.get("id")
                if old_id:
                    # ReviewLog.rollback_to declares ``namespace`` as
                    # a required kwarg for signature symmetry with the
                    # rest of ReviewLog, but the chain rewrite itself
                    # never consults the value (it acts on memory_id
                    # → node_uuid, which is namespace-independent).
                    # Pass __shared__ as the canonical placeholder.
                    await review.rollback_to(old_id, namespace="__shared__")
                    rolled_back.append(key)
                else:
                    errors.append({"key": key, "error": "No old memory ID"})

            elif table == "memories" and before is None and after:
                errors.append(
                    {"key": key, "error": "Cannot rollback memory creation"}
                )

            elif table == "paths" and before is None and after:
                # Path was created by the AI: remove it via the engine.
                domain = after.get("domain", "core")
                path = after.get("path", "")
                namespace = after.get("namespace", "__shared__")
                if path:
                    try:
                        await engine.delete(
                            f"{domain}://{path}", namespace=namespace
                        )
                        rolled_back.append(key)
                    except (ValueError, RuntimeError) as e:
                        errors.append({"key": key, "error": str(e)})

            elif table == "paths" and before and after is None:
                # Path was deleted by the AI: restore it.
                domain = before.get("domain", "core")
                path = before.get("path", "")
                namespace = before.get("namespace", "__shared__")
                edge_id = before.get("edge_id")
                if path and edge_id:
                    # The original edge may have been GC'd along with the
                    # path; look it up to recover the original node_uuid
                    # before delegating to ReviewLog.restore_path.
                    from ..models import Edge
                    from sqlalchemy import select
                    from .. import get_db_manager

                    db = get_db_manager()
                    async with db.session() as session:
                        edge_result = await session.execute(
                            select(Edge).where(Edge.id == edge_id)
                        )
                        edge = edge_result.scalar_one_or_none()
                    if edge:
                        await review.restore_path(
                            path=path,
                            domain=domain,
                            namespace=namespace,
                            node_uuid=edge.child_uuid,
                        )
                        rolled_back.append(key)
                    else:
                        errors.append({"key": key, "error": "Edge not found"})
                else:
                    errors.append({"key": key, "error": "Missing path or edge_id"})

            else:
                errors.append(
                    {"key": key, "error": f"Unsupported rollback for table '{table}'"}
                )

        except Exception as e:
            errors.append({"key": key, "error": str(e)})

    if rolled_back:
        store.remove_keys(rolled_back)

    return {
        "rolled_back": rolled_back,
        "errors": errors,
        "remaining": store.get_change_count(),
    }


@router.post("/integrate")
async def integrate_changes(req: IntegrateRequest):
    """Accept specific pending changes by removing them from the changeset."""
    store = get_changeset_store()
    all_rows = store.get_all_rows_dict()

    errors: List[Dict[str, Any]] = []
    accepted: List[str] = []

    for key in req.keys:
        entry = all_rows.get(key)
        if not entry:
            errors.append({"key": key, "error": "Not found"})
            continue
        table = entry.get("table", "")
        before = entry.get("before")
        after = entry.get("after")
        if _rows_equal(table, before, after):
            errors.append({"key": key, "error": "No pending change"})
            continue
        accepted.append(key)

    if accepted:
        store.remove_keys(accepted)

    return {
        "integrated": accepted,
        "errors": errors,
        "remaining": store.get_change_count(),
    }


@router.post("/integrate-all")
async def integrate_all():
    """Accept all pending changes (clear the changeset)."""
    store = get_changeset_store()
    count = store.clear_all()
    return {"integrated": count}
