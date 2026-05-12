"""
Maintenance API — Endpoints for cleaning up deprecated/orphan memories.

Routes desktop ``/api/maintenance/*`` traffic through ``ReviewLog``. The
legacy dict shape produced by ``GraphService`` is preserved so the
existing OmicsClaw-App frontend keeps working unchanged.
"""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"])


@router.get("/orphans")
async def list_orphan_memories():
    """List all orphan and deprecated memories."""
    from .. import get_review_log

    review = get_review_log()
    return await review.list_orphans_with_chain()


@router.get("/orphan/{memory_id}")
async def get_orphan_detail(memory_id: int):
    """Get full detail of an orphan memory (for content viewing and diff)."""
    from .. import get_review_log

    review = get_review_log()
    detail = await review.get_orphan_detail(memory_id)
    if detail is None:
        raise HTTPException(
            status_code=404, detail=f"Memory {memory_id} not found"
        )
    return detail


@router.delete("/orphan/{memory_id}")
async def delete_orphan(memory_id: int):
    """Permanently delete an orphan/deprecated memory."""
    from .. import get_review_log
    from ..snapshot import get_changeset_store

    review = get_review_log()
    store = get_changeset_store()

    try:
        result = await review.permanently_delete_orphan(memory_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    store.record_many(
        before_state=result.get("rows_before", {}),
        after_state=result.get("rows_after", {}),
    )

    return result


@router.post("/rebuild-search-index")
async def rebuild_search_index():
    """Fully rebuild the search index from live graph state."""
    from .. import get_search_indexer

    search = get_search_indexer()

    await search.rebuild_all_search_documents()
    return {"status": "ok", "message": "Search index rebuilt successfully"}
