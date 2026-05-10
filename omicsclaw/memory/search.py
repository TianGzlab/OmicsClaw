# pyright: reportArgumentType=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportOperatorIssue=false

"""
FTS Search Indexer and Query Engine for OmicsClaw Memory System.

Ported from nocturne_memory. Maintains derived search rows and provides
full-text search across the memory graph.
"""

from typing import Optional, Dict, Any, List, TYPE_CHECKING

from sqlalchemy import select, delete, text, or_
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    Memory,
    Edge,
    Path,
    GlossaryKeyword,
    SearchDocument,
    escape_like_literal,
)
from .search_terms import build_document_search_terms, expand_query_terms
from .uri import MemoryURI

if TYPE_CHECKING:
    from .database import DatabaseManager

SHARED_NAMESPACE = "__shared__"


class SearchIndexer:
    """FTS index maintenance and query engine.

    Manages the derived search_documents table, keeping it in sync with
    the live graph state.  Supports both SQLite FTS5 and PostgreSQL
    tsvector backends.
    """

    def __init__(self, db: "DatabaseManager"):
        self._session = db.session
        self._optional_session = db._optional_session
        self.db_type = db.db_type

    # -----------------------------------------------------------------
    # Query helpers (stateless)
    # -----------------------------------------------------------------

    @staticmethod
    def _to_sqlite_match_query(query: str) -> str:
        """Convert free text into a conservative FTS5 MATCH expression."""
        normalized = expand_query_terms(query)
        tokens = [token.replace('"', '""') for token in normalized.split() if token]
        if not tokens:
            raw = query.strip().replace('"', '""')
            return f'"{raw}"' if raw else ""
        return " AND ".join(f'"{token}"' for token in tokens)

    @staticmethod
    def _format_search_snippet(content: str, query: str) -> str:
        """Build a short content snippet around the first literal hit or token hit."""
        if not content:
            return ""

        content_lower = content.lower()
        query_lower = query.lower()

        pos = content_lower.find(query_lower)
        match_len = len(query)

        if pos < 0:
            tokens = expand_query_terms(query).split()
            for token in tokens:
                if not token:
                    continue
                pos = content_lower.find(token.lower())
                if pos >= 0:
                    match_len = len(token)
                    break

        if pos < 0:
            fallback = content[:80]
            return fallback + ("..." if len(content) > 80 else "")

        start = max(0, pos - 30)
        end = min(len(content), pos + match_len + 30)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(content) else ""
        return prefix + content[start:end] + suffix

    # -----------------------------------------------------------------
    # Index maintenance
    # -----------------------------------------------------------------

    async def _build_search_documents_for_node(
        self, session: AsyncSession, node_uuid: str
    ) -> List[Dict[str, Any]]:
        """Materialize search rows for every reachable path of a node."""
        memory = (
            await session.execute(
                select(Memory)
                .where(Memory.node_uuid == node_uuid, Memory.deprecated == False)
                .limit(1)
            )
        ).scalar_one_or_none()
        if not memory:
            return []

        path_rows = (
            await session.execute(
                select(
                    Path.namespace, Path.domain, Path.path, Edge.priority, Edge.disclosure
                )
                .select_from(Path)
                .join(Edge, Path.edge_id == Edge.id)
                .where(Edge.child_uuid == node_uuid)
                .order_by(Path.namespace, Path.domain, Path.path)
            )
        ).all()
        if not path_rows:
            return []

        # Glossary keywords are partitioned by namespace; for each search
        # row we include only keywords visible from its namespace, i.e. the
        # row's own namespace plus the global ``__shared__`` namespace.
        keyword_rows = (
            await session.execute(
                select(GlossaryKeyword.keyword, GlossaryKeyword.namespace)
                .where(GlossaryKeyword.node_uuid == node_uuid)
                .order_by(GlossaryKeyword.namespace, GlossaryKeyword.keyword)
            )
        ).all()
        keyword_by_ns: Dict[str, List[str]] = {}
        for kw, ns in keyword_rows:
            if not kw:
                continue
            keyword_by_ns.setdefault(ns, []).append(kw)

        documents = []
        shared_keywords = keyword_by_ns.get(SHARED_NAMESPACE, [])
        for row in path_rows:
            visible = list(keyword_by_ns.get(row.namespace, []))
            if row.namespace != SHARED_NAMESPACE:
                visible.extend(shared_keywords)
            glossary_text = " ".join(visible)
            uri = f"{row.domain}://{row.path}"
            documents.append(
                {
                    "namespace": row.namespace,
                    "domain": row.domain,
                    "path": row.path,
                    "node_uuid": node_uuid,
                    "memory_id": memory.id,
                    "uri": uri,
                    "content": memory.content,
                    "disclosure": row.disclosure,
                    "search_terms": build_document_search_terms(
                        row.path,
                        uri,
                        memory.content,
                        row.disclosure,
                        glossary_text,
                    ),
                    "priority": row.priority,
                }
            )
        return documents

    async def _delete_search_documents_for_node(
        self, session: AsyncSession, node_uuid: str
    ) -> None:
        """Remove all derived search rows for a node."""
        if self.db_type == "sqlite":
            try:
                await session.execute(
                    text("DELETE FROM search_documents_fts WHERE node_uuid = :node_uuid"),
                    {"node_uuid": node_uuid},
                )
            except Exception:
                pass  # FTS table may not exist

        await session.execute(
            delete(SearchDocument).where(SearchDocument.node_uuid == node_uuid)
        )

    async def _insert_search_documents(
        self, session: AsyncSession, documents: List[Dict[str, Any]]
    ) -> None:
        """Insert fresh derived search rows for one node."""
        if not documents:
            return

        session.add_all(SearchDocument(**doc) for doc in documents)
        await session.flush()

        if self.db_type != "sqlite":
            return

        for doc in documents:
            try:
                await session.execute(
                    text(
                        """
                        INSERT INTO search_documents_fts (
                            namespace, domain, path, node_uuid, uri, content, disclosure, search_terms
                        ) VALUES (
                            :namespace, :domain, :path, :node_uuid, :uri, :content, coalesce(:disclosure, ''), :search_terms
                        )
                        """
                    ),
                    doc,
                )
            except Exception:
                pass  # FTS table may not exist

    async def refresh_search_documents_for_node(
        self, node_uuid: str, session: Optional[AsyncSession] = None
    ) -> None:
        """Rebuild derived search rows for one node (all namespaces).

        Used when a node's content or structural metadata changed and every
        path pointing at it needs to be reindexed.
        """
        async with self._optional_session(session) as session:
            documents = await self._build_search_documents_for_node(session, node_uuid)
            await self._delete_search_documents_for_node(session, node_uuid)
            await self._insert_search_documents(session, documents)

    async def refresh_search_documents_for(
        self,
        namespace: str,
        uri: str | MemoryURI,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """Surgically rebuild ONE search row at (namespace, domain, path).

        Useful when a write touches only a single (namespace, uri) and we
        don't want to disturb sibling rows for the same node in other
        namespaces. No-op if the path doesn't exist or has no active memory.
        """
        parsed = uri if isinstance(uri, MemoryURI) else MemoryURI.parse(uri)

        async with self._optional_session(session) as s:
            path_row = (
                await s.execute(
                    select(Path).where(
                        Path.namespace == namespace,
                        Path.domain == parsed.domain,
                        Path.path == parsed.path,
                    )
                )
            ).scalar_one_or_none()
            if path_row is None:
                return

            edge = await s.get(Edge, path_row.edge_id)
            if edge is None:
                return

            memory = (
                await s.execute(
                    select(Memory)
                    .where(
                        Memory.node_uuid == edge.child_uuid,
                        Memory.deprecated == False,  # noqa: E712
                    )
                    .order_by(Memory.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if memory is None:
                return

            keyword_rows = (
                await s.execute(
                    select(GlossaryKeyword.keyword)
                    .where(
                        GlossaryKeyword.node_uuid == edge.child_uuid,
                        GlossaryKeyword.namespace.in_(
                            [namespace, SHARED_NAMESPACE]
                        ),
                    )
                    .order_by(GlossaryKeyword.keyword)
                )
            ).all()
            glossary_text = " ".join(row[0] for row in keyword_rows if row[0])

            uri_str = f"{parsed.domain}://{parsed.path}"
            doc = {
                "namespace": namespace,
                "domain": parsed.domain,
                "path": parsed.path,
                "node_uuid": edge.child_uuid,
                "memory_id": memory.id,
                "uri": uri_str,
                "content": memory.content,
                "disclosure": edge.disclosure,
                "search_terms": build_document_search_terms(
                    parsed.path,
                    uri_str,
                    memory.content,
                    edge.disclosure,
                    glossary_text,
                ),
                "priority": edge.priority,
            }

            if self.db_type == "sqlite":
                try:
                    await s.execute(
                        text(
                            "DELETE FROM search_documents_fts "
                            "WHERE namespace = :ns AND domain = :d AND path = :p"
                        ),
                        {"ns": namespace, "d": parsed.domain, "p": parsed.path},
                    )
                except Exception:
                    pass
            await s.execute(
                delete(SearchDocument).where(
                    SearchDocument.namespace == namespace,
                    SearchDocument.domain == parsed.domain,
                    SearchDocument.path == parsed.path,
                )
            )
            await self._insert_search_documents(s, [doc])

    async def get_node_uuids_for_prefix(
        self, session: AsyncSession, domain: str, base_path: str
    ) -> List[str]:
        """Collect unique node UUIDs for a path and all descendants."""
        safe = escape_like_literal(base_path)
        result = await session.execute(
            select(Edge.child_uuid)
            .select_from(Path)
            .join(Edge, Path.edge_id == Edge.id)
            .where(Path.domain == domain)
            .where(
                or_(
                    Path.path == base_path,
                    Path.path.like(f"{safe}/%", escape="\\"),
                )
            )
            .distinct()
        )
        return [row[0] for row in result.all()]

    async def rebuild_all_search_documents(
        self, session: Optional[AsyncSession] = None
    ) -> None:
        """Fully rebuild the derived search index from live graph state."""
        async with self._optional_session(session) as session:
            if self.db_type == "sqlite":
                try:
                    await session.execute(text("DELETE FROM search_documents_fts"))
                except Exception:
                    pass

            await session.execute(delete(SearchDocument))

            result = await session.execute(
                select(Edge.child_uuid)
                .select_from(Path)
                .join(Edge, Path.edge_id == Edge.id)
                .distinct()
            )
            for (node_uuid,) in result.all():
                documents = await self._build_search_documents_for_node(session, node_uuid)
                await self._insert_search_documents(session, documents)

    # -----------------------------------------------------------------
    # Public search API
    # -----------------------------------------------------------------

    async def search(
        self,
        query: str,
        limit: int = 10,
        domain: Optional[str] = None,
        namespace: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search memories by path and content using the derived FTS index.

        When ``namespace`` is provided, results are restricted to that
        namespace plus the shared partition; per-namespace hits are sorted
        ahead of shared ones. ``namespace=None`` preserves legacy
        unfiltered behavior for callers that haven't migrated.
        """
        async with self._session() as session:
            candidate_limit = max(limit * 5, 50)
            params: Dict[str, Any] = {"candidate_limit": candidate_limit}

            domain_clause = ""
            if domain is not None:
                params["domain"] = domain
                domain_clause = "AND sd.domain = :domain"

            namespace_clause, namespace_order = "", ""
            if namespace is not None:
                params["current_ns"] = namespace
                params["shared_ns"] = SHARED_NAMESPACE
                namespace_clause = (
                    "AND sd.namespace IN (:current_ns, :shared_ns)"
                )
                namespace_order = (
                    "CASE WHEN sd.namespace = :current_ns THEN 0 ELSE 1 END ASC,"
                )

            if self.db_type == "sqlite":
                # Try FTS5 first, fall back to LIKE search
                try:
                    return await self._search_sqlite_fts(
                        session,
                        query,
                        params,
                        domain_clause,
                        namespace_clause,
                        namespace_order,
                        limit,
                    )
                except Exception:
                    return await self._search_sqlite_like(
                        session, query, limit, domain, namespace
                    )
            else:
                normalized = expand_query_terms(query)
                if not normalized:
                    return []

                params["ts_query"] = normalized
                result = await session.execute(
                    text(
                        f"""
                        SELECT
                            sd.domain,
                            sd.path,
                            sd.node_uuid,
                            sd.uri,
                            sd.priority,
                            sd.content,
                            sd.disclosure,
                            sd.namespace AS namespace,
                            ts_rank_cd(
                                to_tsvector(
                                    'simple',
                                    coalesce(sd.path, '') || ' ' ||
                                    coalesce(sd.uri, '') || ' ' ||
                                    coalesce(sd.content, '') || ' ' ||
                                    coalesce(sd.disclosure, '') || ' ' ||
                                    coalesce(sd.search_terms, '')
                                ),
                                websearch_to_tsquery('simple', :ts_query)
                            ) AS score
                        FROM search_documents AS sd
                        WHERE to_tsvector(
                                'simple',
                                coalesce(sd.path, '') || ' ' ||
                                coalesce(sd.uri, '') || ' ' ||
                                coalesce(sd.content, '') || ' ' ||
                                coalesce(sd.disclosure, '') || ' ' ||
                                coalesce(sd.search_terms, '')
                              ) @@ websearch_to_tsquery('simple', :ts_query)
                          {domain_clause}
                          {namespace_clause}
                        ORDER BY {namespace_order} score DESC, sd.priority ASC, char_length(sd.path) ASC
                        LIMIT :candidate_limit
                        """
                    ),
                    params,
                )

                return self._format_results(result, query, limit)

    async def _search_sqlite_fts(
        self,
        session: AsyncSession,
        query: str,
        params: Dict[str, Any],
        domain_clause: str,
        namespace_clause: str,
        namespace_order: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Search using SQLite FTS5."""
        match_query = self._to_sqlite_match_query(query)
        if not match_query:
            return []

        params["match_query"] = match_query
        result = await session.execute(
            text(
                f"""
                SELECT
                    sd.domain,
                    sd.path,
                    sd.node_uuid,
                    sd.uri,
                    sd.priority,
                    sd.content,
                    sd.disclosure,
                    sd.namespace AS namespace,
                    -- 8 bm25 weights, one per FTS column in declaration order:
                    -- namespace, domain, path, node_uuid, uri, content,
                    -- disclosure, search_terms. namespace gets 0.0 because
                    -- the JOIN already filters it; domain/node_uuid stay 0.0
                    -- so they don't influence ranking.
                    bm25(search_documents_fts, 0.0, 0.0, 2.5, 0.0, 2.0, 1.0, 1.0, 0.75) AS score
                FROM search_documents AS sd
                JOIN search_documents_fts
                  ON search_documents_fts.namespace = sd.namespace
                 AND search_documents_fts.domain    = sd.domain
                 AND search_documents_fts.path      = sd.path
                WHERE search_documents_fts MATCH :match_query
                  {domain_clause}
                  {namespace_clause}
                ORDER BY {namespace_order} score ASC, sd.priority ASC, length(sd.path) ASC
                LIMIT :candidate_limit
                """
            ),
            params,
        )
        return self._format_results(result, query, limit)

    async def _search_sqlite_like(
        self,
        session: AsyncSession,
        query: str,
        limit: int,
        domain: Optional[str],
        namespace: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Fallback search using LIKE when FTS5 is unavailable."""
        safe_query = f"%{escape_like_literal(query)}%"
        params: Dict[str, Any] = {"query": safe_query, "limit": limit * 3}

        domain_clause = ""
        if domain:
            params["domain"] = domain
            domain_clause = "AND sd.domain = :domain"

        namespace_clause, namespace_order = "", ""
        if namespace is not None:
            params["current_ns"] = namespace
            params["shared_ns"] = SHARED_NAMESPACE
            namespace_clause = (
                "AND sd.namespace IN (:current_ns, :shared_ns)"
            )
            namespace_order = (
                "CASE WHEN sd.namespace = :current_ns THEN 0 ELSE 1 END ASC,"
            )

        result = await session.execute(
            text(
                f"""
                SELECT
                    sd.domain,
                    sd.path,
                    sd.node_uuid,
                    sd.uri,
                    sd.priority,
                    sd.content,
                    sd.disclosure,
                    sd.namespace AS namespace,
                    0 AS score
                FROM search_documents AS sd
                WHERE (sd.content LIKE :query ESCAPE '\\' OR sd.path LIKE :query ESCAPE '\\')
                  {domain_clause}
                  {namespace_clause}
                ORDER BY {namespace_order} sd.priority ASC, length(sd.path) ASC
                LIMIT :limit
                """
            ),
            params,
        )
        return self._format_results(result, query, limit)

    def _format_results(self, result, query: str, limit: int) -> List[Dict[str, Any]]:
        """Format raw SQL results into search result dicts."""
        matches = []
        seen_nodes = set()

        for row in result.mappings():
            if row["node_uuid"] in seen_nodes:
                continue
            seen_nodes.add(row["node_uuid"])
            matches.append(
                {
                    "namespace": row.get("namespace"),
                    "domain": row["domain"],
                    "path": row["path"],
                    "uri": row["uri"],
                    "name": row["path"].rsplit("/", 1)[-1],
                    "snippet": self._format_search_snippet(row["content"], query),
                    "priority": row["priority"],
                    "disclosure": row["disclosure"],
                }
            )
            if len(matches) >= limit:
                break

        return matches
