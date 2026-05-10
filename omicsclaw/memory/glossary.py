# pyright: reportArgumentType=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportOperatorIssue=false

"""
Glossary Service for OmicsClaw Memory System.

Ported from nocturne_memory. Manages keyword-to-node bindings and provides
Aho-Corasick-based content scanning for keyword highlighting.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from sqlalchemy import select, delete, and_, func
from sqlalchemy.exc import IntegrityError

from .models import (
    Node,
    Edge,
    Path,
    Memory,
    GlossaryKeyword,
    SHARED_NAMESPACE,
    serialize_row,
)

if TYPE_CHECKING:
    from .database import DatabaseManager
    from .search import SearchIndexer


@dataclass(frozen=True)
class _KeywordUniverse:
    """Snapshot of the glossary keywords visible from a given namespace.

    ``fingerprint`` is a (count, max_id, max_created_at) triple used to
    detect that the cache is stale; ``keywords`` is the de-duplicated
    keyword list to feed Aho-Corasick.
    """

    keywords: List[str]
    fingerprint: tuple


class GlossaryService:
    """Glossary keyword management and content scanning.

    Maintains an Aho-Corasick automaton for efficient multi-pattern
    matching.  The automaton is rebuilt lazily when the DB fingerprint
    (row count + max id + max created_at) changes.
    """

    def __init__(self, db: "DatabaseManager", search_indexer: "SearchIndexer"):
        self._session = db.session
        self._search = search_indexer
        # Per-namespace automaton cache. Key is the namespace string or
        # the literal "__all__" for the legacy unscoped scan.
        self._automatons: Dict[str, Any] = {}
        self._fingerprints: Dict[str, tuple] = {}

    async def add_glossary_keyword(
        self, keyword: str, node_uuid: str, namespace: str = SHARED_NAMESPACE
    ) -> Dict[str, Any]:
        """Bind a glossary keyword to a node inside ``namespace``.

        ``namespace`` defaults to ``__shared__`` so legacy callers that
        haven't migrated keep writing into the global partition. Pass an
        explicit namespace to scope a keyword to one user/surface; or use
        ``add_glossary_shared`` for clarity.
        """
        keyword = keyword.strip()
        if not keyword:
            raise ValueError("Glossary keyword cannot be empty")

        async with self._session() as session:
            node = await session.get(Node, node_uuid)
            if not node:
                raise ValueError(f"Node '{node_uuid}' not found")

            entry = GlossaryKeyword(
                keyword=keyword, node_uuid=node_uuid, namespace=namespace
            )
            session.add(entry)

            try:
                await session.flush()
            except IntegrityError:
                raise ValueError(
                    f"Keyword '{keyword}' is already bound to this node "
                    f"in namespace '{namespace}'"
                )

            await self._search.refresh_search_documents_for_node(
                node_uuid, session=session
            )

            row_after = serialize_row(entry)

            return {
                "id": entry.id,
                "keyword": keyword,
                "node_uuid": node_uuid,
                "namespace": namespace,
                "rows_before": {"glossary_keywords": []},
                "rows_after": {"glossary_keywords": [row_after]},
            }

    async def add_glossary_shared(
        self, keyword: str, node_uuid: str
    ) -> Dict[str, Any]:
        """Bind a globally-visible glossary keyword (namespace=__shared__).

        Sugar for ``add_glossary_keyword(..., namespace=SHARED_NAMESPACE)``,
        intended for callers that want to be explicit about the global
        scope rather than relying on the default.
        """
        return await self.add_glossary_keyword(
            keyword, node_uuid, namespace=SHARED_NAMESPACE
        )

    async def remove_glossary_keyword(
        self, keyword: str, node_uuid: str, namespace: str = SHARED_NAMESPACE
    ) -> Dict[str, Any]:
        """Remove a glossary keyword binding within one namespace.

        Default ``__shared__`` matches the legacy callsite, which had no
        namespace concept. Removal is now namespace-scoped — pass an
        explicit namespace to remove a per-user binding without touching
        shared or other-user bindings of the same (keyword, node_uuid).
        """
        keyword = keyword.strip()
        async with self._session() as session:
            existing = await session.execute(
                select(GlossaryKeyword).where(
                    GlossaryKeyword.keyword == keyword,
                    GlossaryKeyword.node_uuid == node_uuid,
                    GlossaryKeyword.namespace == namespace,
                )
            )
            entry = existing.scalar_one_or_none()
            if not entry:
                return {
                    "success": False,
                    "rows_before": {"glossary_keywords": []},
                    "rows_after": {"glossary_keywords": []},
                }

            row_before = serialize_row(entry)

            await session.execute(
                delete(GlossaryKeyword).where(
                    GlossaryKeyword.id == entry.id
                )
            )

            await self._search.refresh_search_documents_for_node(
                node_uuid, session=session
            )

            return {
                "success": True,
                "rows_before": {"glossary_keywords": [row_before]},
                "rows_after": {"glossary_keywords": []},
            }

    async def get_glossary_for_node(self, node_uuid: str) -> List[str]:
        """Get all keywords bound to a node."""
        async with self._session() as session:
            result = await session.execute(
                select(GlossaryKeyword.keyword)
                .where(GlossaryKeyword.node_uuid == node_uuid)
                .order_by(GlossaryKeyword.keyword)
            )
            return [row[0] for row in result.all()]

    async def get_all_glossary(self) -> List[Dict[str, Any]]:
        """Get all glossary entries grouped by keyword, with node URIs."""
        async with self._session() as session:
            result = await session.execute(
                select(
                    GlossaryKeyword.keyword,
                    GlossaryKeyword.node_uuid,
                    Path.domain,
                    Path.path,
                    Memory.content,
                )
                .select_from(GlossaryKeyword)
                .join(Node, Node.uuid == GlossaryKeyword.node_uuid)
                .outerjoin(Edge, Edge.child_uuid == Node.uuid)
                .outerjoin(Path, Path.edge_id == Edge.id)
                .outerjoin(
                    Memory,
                    and_(
                        Memory.node_uuid == Node.uuid,
                        Memory.deprecated == False,
                    ),
                )
                .order_by(GlossaryKeyword.keyword, Path.domain, Path.path)
            )

            groups: Dict[str, Dict[str, Dict[str, str]]] = defaultdict(dict)

            for keyword, node_uuid, domain, path, content in result.all():
                if node_uuid not in groups[keyword]:
                    snippet = ""
                    if content:
                        snippet = content[:100].replace("\n", " ")
                        if len(content) > 100:
                            snippet += "..."
                    uri = f"{domain}://{path}" if domain is not None and path is not None else f"unlinked://{node_uuid}"
                    groups[keyword][node_uuid] = {
                        "node_uuid": node_uuid,
                        "uri": uri,
                        "content_snippet": snippet,
                    }

            return [
                {"keyword": kw, "nodes": list(node_map.values())}
                for kw, node_map in groups.items()
            ]

    async def find_glossary_in_content(
        self,
        content: str,
        namespace: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, str]]]:
        """Scan content for glossary keywords using Aho-Corasick.

        When ``namespace`` is provided, restricts the keyword universe to
        ``(namespace, __shared__)`` — that's how the search reindexer
        avoids cross-namespace keyword leaks. ``namespace=None`` preserves
        the legacy "match anything in the DB" behaviour.

        The Aho-Corasick automaton is built per namespace key and cached
        with a DB-level fingerprint so repeated scans don't repeatedly
        rebuild. ``namespace=None`` still uses the same cache slot.
        """
        try:
            import ahocorasick
        except ImportError:
            # ahocorasick not installed — fall back to simple substring matching
            return await self._find_glossary_simple(content, namespace=namespace)

        keyword_universe = await self._fetch_keyword_universe(namespace)

        # Cache the automaton keyed by namespace so different scopes don't
        # invalidate each other's caches every call.
        cache_key = namespace if namespace is not None else "__all__"
        cached_fp = self._fingerprints.get(cache_key)
        if keyword_universe.fingerprint != cached_fp:
            if not keyword_universe.keywords:
                self._automatons[cache_key] = None
            else:
                automaton = ahocorasick.Automaton()
                for kw in keyword_universe.keywords:
                    automaton.add_word(kw, kw)
                automaton.make_automaton()
                self._automatons[cache_key] = automaton
            self._fingerprints[cache_key] = keyword_universe.fingerprint

        automaton = self._automatons.get(cache_key)
        if automaton is None:
            return {}

        found_keywords: set = set()
        for _, kw in automaton.iter(content):
            found_keywords.add(kw)

        if not found_keywords:
            return {}

        return await self._resolve_keyword_nodes(found_keywords, namespace=namespace)

    async def _find_glossary_simple(
        self,
        content: str,
        namespace: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, str]]]:
        """Fallback: simple substring matching when ahocorasick is unavailable."""
        keyword_universe = await self._fetch_keyword_universe(namespace)
        found_keywords = {
            kw for kw in keyword_universe.keywords if kw in content
        }
        if not found_keywords:
            return {}
        return await self._resolve_keyword_nodes(found_keywords, namespace=namespace)

    async def _fetch_keyword_universe(
        self, namespace: Optional[str]
    ) -> "_KeywordUniverse":
        """Pull the keywords + fingerprint visible from ``namespace``.

        ``namespace=None`` returns every keyword (legacy behaviour).
        Otherwise restricts to ``(namespace, __shared__)``.
        """
        async with self._session() as session:
            stmt_count = select(
                func.count(GlossaryKeyword.id),
                func.coalesce(func.max(GlossaryKeyword.id), 0),
                func.max(GlossaryKeyword.created_at),
            )
            stmt_keys = select(GlossaryKeyword.keyword).distinct()
            if namespace is not None:
                ns_filter = GlossaryKeyword.namespace.in_(
                    [namespace, SHARED_NAMESPACE]
                )
                stmt_count = stmt_count.where(ns_filter)
                stmt_keys = stmt_keys.where(ns_filter)

            fp_row = await session.execute(stmt_count)
            fingerprint = tuple(fp_row.one())

            kw_result = await session.execute(stmt_keys)
            keywords = [row[0] for row in kw_result.all()]

        return _KeywordUniverse(keywords=keywords, fingerprint=fingerprint)

    async def _resolve_keyword_nodes(
        self, found_keywords: set, namespace: Optional[str] = None
    ) -> Dict[str, List[Dict[str, str]]]:
        """Resolve found keywords to their node UUIDs and URIs.

        If ``namespace`` is provided, only resolves keywords scoped to
        ``(namespace, __shared__)`` so a user-scoped scan can't leak the
        existence of a foreign-namespace keyword.
        """
        async with self._session() as session:
            stmt = (
                select(
                    GlossaryKeyword.keyword,
                    GlossaryKeyword.node_uuid,
                    Path.domain,
                    Path.path,
                )
                .select_from(GlossaryKeyword)
                .outerjoin(Edge, Edge.child_uuid == GlossaryKeyword.node_uuid)
                .outerjoin(Path, Path.edge_id == Edge.id)
                .where(GlossaryKeyword.keyword.in_(found_keywords))
                .order_by(GlossaryKeyword.keyword, Path.domain, Path.path)
            )
            if namespace is not None:
                stmt = stmt.where(
                    GlossaryKeyword.namespace.in_([namespace, SHARED_NAMESPACE])
                )
            result = await session.execute(stmt)

            matches: Dict[str, Dict[str, str]] = defaultdict(dict)
            for keyword, node_uuid, domain, path in result.all():
                if node_uuid not in matches[keyword]:
                    matches[keyword][node_uuid] = (
                        f"{domain}://{path}"
                        if domain is not None and path is not None
                        else f"unlinked://{node_uuid}"
                    )

            return {
                kw: [
                    {"node_uuid": nid, "uri": uri}
                    for nid, uri in node_map.items()
                ]
                for kw, node_map in matches.items()
            }
