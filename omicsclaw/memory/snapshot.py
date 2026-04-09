# pyright: reportArgumentType=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportOperatorIssue=false

"""
Changeset Store — Single-pool accumulation of row-level before/after states.

Ported from nocturne_memory for OmicsClaw Memory System.

Overwrite semantics:
  - First touch of a PK: record both `before` (pre-AI) and `after` (post-AI).
  - Subsequent touches of the same PK: overwrite `after` only; `before` is frozen.
  - Net-zero changes (before == after) are filtered from display automatically.

Storage: one JSON file at `~/.config/omicsclaw/memory_snapshots/changeset.json`.
"""

import os
import json
import stat
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)


def _default_snapshot_dir() -> str:
    env_dir = os.environ.get("OMICSCLAW_SNAPSHOT_DIR")
    if env_dir:
        return env_dir
    return str(Path.home() / ".config" / "omicsclaw" / "memory_snapshots")


DEFAULT_SNAPSHOT_DIR = _default_snapshot_dir()

_CHANGESET_FILENAME = "changeset.json"

TABLE_ORDER = ["nodes", "memories", "edges", "paths", "glossary_keywords"]
TABLE_PKS = {
    "nodes": "uuid",
    "memories": "id",
    "edges": "id",
    "paths": ("domain", "path"),
    "glossary_keywords": ("keyword", "node_uuid"),
}


def _make_row_key(table: str, row: Dict[str, Any]) -> str:
    pk_def = TABLE_PKS[table]
    if isinstance(pk_def, tuple):
        pk_val = "|".join(str(row[k]) for k in pk_def)
    else:
        pk_val = str(row[pk_def])
    return f"{table}:{pk_val}"


def _rows_equal(table: str, a: Optional[dict], b: Optional[dict]) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False

    if table == "glossary_keywords":
        a_copy = {k: v for k, v in a.items() if k not in ("id", "created_at")}
        b_copy = {k: v for k, v in b.items() if k not in ("id", "created_at")}
        return a_copy == b_copy

    return a == b


class ChangesetStore:
    """
    Accumulates row-level before/after states in a single pool.

    The review page reads the frozen `before` and queries live DB state
    to present the user with a clean delta and compute rollback paths.
    """

    def __init__(self, snapshot_dir: Optional[str] = None):
        self.snapshot_dir = snapshot_dir or DEFAULT_SNAPSHOT_DIR
        Path(self.snapshot_dir).mkdir(parents=True, exist_ok=True)

    @property
    def _changeset_path(self) -> str:
        return os.path.join(self.snapshot_dir, _CHANGESET_FILENAME)

    def _load(self) -> Dict[str, Any]:
        p = self._changeset_path
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "rows" not in data:
                return {"rows": {}}
            return data
        return {"rows": {}}

    def _save(self, data: Dict[str, Any]):
        p = self._changeset_path
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Core: record with overwrite semantics
    # ------------------------------------------------------------------

    def record(
        self,
        table: str,
        row_before: Optional[Dict[str, Any]],
        row_after: Optional[Dict[str, Any]],
    ):
        """
        Record one row change.

        First touch: store both `before` and `after`.
        Subsequent: overwrite `after` only.
        """
        ref_row = row_before if row_before is not None else row_after
        if ref_row is None:
            return
        key = _make_row_key(table, ref_row)

        data = self._load()
        existing = data["rows"].get(key)

        if existing is not None:
            existing["after"] = row_after
        else:
            data["rows"][key] = {
                "table": table,
                "before": row_before,
                "after": row_after,
            }

        self._gc_noop_creates(data)
        if data.get("rows"):
            self._save(data)
        else:
            self._remove_changeset()

    def record_many(
        self,
        before_state: Dict[str, List[Dict[str, Any]]],
        after_state: Dict[str, List[Dict[str, Any]]],
    ):
        """
        Batch-record changes across multiple tables.

        Both arguments map table name -> list of row dicts.
        Rows in `before_state` only = DELETE.
        Rows in `after_state` only = INSERT.
        Rows in both = UPDATE (matched by PK).
        """
        if not before_state and not after_state:
            logger.debug("record_many: called with empty before_state and after_state, skipping")
            return

        logger.debug(
            "record_many: before_tables=%s, after_tables=%s",
            list(before_state.keys()), list(after_state.keys())
        )

        data = self._load()

        all_tables = set(before_state.keys()) | set(after_state.keys())
        for table in all_tables:
            before_rows = {_make_row_key(table, r): r for r in before_state.get(table, [])}
            after_rows = {_make_row_key(table, r): r for r in after_state.get(table, [])}

            all_keys = set(before_rows.keys()) | set(after_rows.keys())
            for key in all_keys:
                b = before_rows.get(key)
                a = after_rows.get(key)

                existing = data["rows"].get(key)
                if existing is not None:
                    existing["after"] = a
                else:
                    data["rows"][key] = {
                        "table": table,
                        "before": b,
                        "after": a,
                    }

        rows_before_gc = len(data.get("rows", {}))
        self._gc_noop_creates(data)
        rows_after_gc = len(data.get("rows", {}))

        if rows_before_gc != rows_after_gc:
            logger.debug(
                "record_many: GC removed %d entries (%d -> %d)",
                rows_before_gc - rows_after_gc, rows_before_gc, rows_after_gc
            )

        if data.get("rows"):
            self._save(data)
            logger.info(
                "record_many: saved %d changeset entries to %s",
                len(data["rows"]), self._changeset_path
            )
        else:
            self._remove_changeset()
            logger.debug("record_many: no net changes, removed changeset file")

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_change_count(self) -> int:
        """Return the number of net-changed rows in the pool."""
        data = self._load()
        return len(self._changed_rows(data))

    def get_changed_rows(self) -> List[Dict[str, Any]]:
        """Return all rows where before != after (net changes only)."""
        data = self._load()
        return self._changed_rows(data)

    def get_all_rows_dict(self) -> Dict[str, Any]:
        """Return the full dictionary of rows (including unchanged) for resolving references."""
        data = self._load()
        return data.get("rows", {})

    def remove_keys(self, keys: List[str]) -> int:
        """Remove specific tracked rows by their keys."""
        if not keys:
            return 0

        data = self._load()
        removed = 0
        for k in keys:
            if k in data["rows"]:
                data["rows"].pop(k)
                removed += 1

        remaining = self._changed_rows(data)
        if not remaining:
            self._remove_changeset()
        elif removed > 0:
            self._save(data)

        return removed

    def clear_all(self) -> int:
        """Clear the entire changeset pool (integrate all)."""
        data = self._load()
        count = len(self._changed_rows(data))
        self._remove_changeset()
        return count

    def discard_all(self) -> int:
        """Drop the entire changeset pool after rollback/discard."""
        data = self._load()
        count = len(self._changed_rows(data))
        self._remove_changeset()
        return count

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _changed_rows(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        result = []
        for entry in data.get("rows", {}).values():
            if not _rows_equal(entry.get("table", ""), entry.get("before"), entry.get("after")):
                result.append(entry)
        return result

    @staticmethod
    def _gc_noop_creates(data: Dict[str, Any]) -> bool:
        """Remove create-then-delete no-ops and their orphaned dependents."""
        rows = data.get("rows", {})
        if not rows:
            return False

        net_zero = {
            k for k, e in rows.items()
            if e.get("before") is None and e.get("after") is None
        }
        if not net_zero:
            return False

        reachable = set()
        created_nodes = set()
        for key, entry in rows.items():
            if key.startswith("nodes:") and entry.get("before") is None:
                node_uuid = key.split(":", 1)[1]
                created_nodes.add(node_uuid)

            if key in net_zero or not key.startswith("paths:"):
                continue
            ref = entry.get("after") or entry.get("before")
            if not ref:
                continue
            edge_id = ref.get("edge_id")
            if edge_id is not None:
                ek = f"edges:{edge_id}"
                ee = rows.get(ek)
                if ee and ek not in net_zero:
                    er = ee.get("after") or ee.get("before")
                    if er and er.get("child_uuid"):
                        reachable.add(er["child_uuid"])
            if ref.get("node_uuid"):
                reachable.add(ref["node_uuid"])

        to_remove = set(net_zero)
        for key, entry in rows.items():
            if key in to_remove or entry.get("before") is not None:
                continue
            ref = entry.get("after")
            if not ref:
                continue

            if key.startswith("nodes:"):
                if ref.get("uuid") not in reachable:
                    to_remove.add(key)
            elif key.startswith("memories:"):
                node_uuid = ref.get("node_uuid")
                if node_uuid in created_nodes and node_uuid not in reachable:
                    to_remove.add(key)
            elif key.startswith("glossary_keywords:"):
                node_uuid = ref.get("node_uuid")
                if node_uuid in created_nodes and node_uuid not in reachable:
                    to_remove.add(key)
            elif key.startswith("edges:"):
                eid = ref.get("id")
                if not any(
                    k not in to_remove and k.startswith("paths:")
                    and ((rows[k].get("after") or rows[k].get("before") or {}).get("edge_id") == eid)
                    for k in rows
                ):
                    to_remove.add(key)

        for key in to_remove:
            rows.pop(key, None)
        return True

    def _remove_changeset(self):
        p = self._changeset_path
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
        except PermissionError:
            os.chmod(p, stat.S_IWRITE)
            os.remove(p)


def _parse_uri(uri: str):
    if "://" in uri:
        domain, path = uri.split("://", 1)
    else:
        domain, path = "core", uri
    return domain, path


# Global singleton
_store: Optional[ChangesetStore] = None


def get_changeset_store() -> ChangesetStore:
    global _store
    if _store is None:
        _store = ChangesetStore()
    return _store
