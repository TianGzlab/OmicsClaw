"""
SQLite FTS5 storage engine for the OmicsClaw knowledge base.

Stores document chunks in a regular table with a companion FTS5 virtual
table for full-text search.  Uses plain sqlite3 (no ORM) — the knowledge
base is a static, read-heavy store that doesn't need async or migrations.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Optional

from .indexer import Chunk, ParseResult, iter_documents

logger = logging.getLogger(__name__)

# Default database location
_DEFAULT_DB_DIR = Path(os.getenv(
    "OMICSCLAW_DATA_DIR",
    os.path.expanduser("~/.config/omicsclaw"),
))
_DEFAULT_DB_PATH = _DEFAULT_DB_DIR / "knowledge.db"


class KnowledgeStore:
    """SQLite FTS5 backed knowledge store."""

    _INDEXABLE_SUFFIXES = {".md", ".py", ".r"}

    _QUERY_NOISE_PHRASES: tuple[str, ...] = (
        "can you",
        "could you",
        "would you",
        "please",
        "help me",
        "recommend",
        "recommended",
        "suggest",
        "suitable",
        "appropriate",
        "which",
        "what",
        "should i",
        "how do i",
        "how to",
        "best way",
        "workflow",
        "pipeline",
        "method",
        "methods",
        "parameter",
        "parameters",
        "compare",
        "comparison",
        "difference",
        "versus",
        " vs ",
        "帮我",
        "请问",
        "推荐",
        "建议",
        "适合",
        "这个数据",
        "该数据",
        "如何选择",
        "怎么选",
        "选择",
        "什么方法",
        "哪个方法",
        "哪种方法",
        "方法",
        "流程",
        "工作流",
        "参数",
        "调参",
        "区别",
        "对比",
        "比较",
        "如何",
        "怎么做",
        "这两种",
        "这种",
        "那个",
        "这个",
        "该",
        "的",
        "吗",
        "呢",
    )
    _QUERY_STOPWORDS: set[str] = {
        "a", "an", "and", "the", "for", "with", "into", "from", "this", "that",
        "these", "those", "use", "using", "should", "would", "could", "please",
        "help", "recommend", "recommended", "suggest", "suitable", "appropriate",
        "which", "what", "how", "best", "way", "workflow", "pipeline", "method",
        "methods", "parameter", "parameters", "compare", "comparison", "difference",
        "versus", "vs", "choose", "selection", "analysis",
    }

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or _DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_schema(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source_path TEXT NOT NULL,
                title       TEXT NOT NULL,
                domain      TEXT NOT NULL,
                doc_type    TEXT NOT NULL,
                section_title TEXT NOT NULL,
                content     TEXT NOT NULL,
                search_terms TEXT NOT NULL DEFAULT '',
                content_hash TEXT NOT NULL DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_kc_domain
                ON knowledge_chunks(domain);
            CREATE INDEX IF NOT EXISTS idx_kc_doc_type
                ON knowledge_chunks(doc_type);
            CREATE INDEX IF NOT EXISTS idx_kc_source
                ON knowledge_chunks(source_path);

            CREATE TABLE IF NOT EXISTS knowledge_meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)

        # FTS5 virtual table — tokenize with unicode61 for broad language support
        # Check if FTS table already exists
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_fts'"
        ).fetchone()
        if not row:
            conn.execute("""
                CREATE VIRTUAL TABLE knowledge_fts USING fts5(
                    title,
                    section_title,
                    content,
                    search_terms,
                    content='knowledge_chunks',
                    content_rowid='id',
                    tokenize='unicode61 remove_diacritics 2'
                )
            """)
            # Triggers to keep FTS in sync with content table
            conn.executescript("""
                CREATE TRIGGER IF NOT EXISTS kc_ai AFTER INSERT ON knowledge_chunks BEGIN
                    INSERT INTO knowledge_fts(rowid, title, section_title, content, search_terms)
                    VALUES (new.id, new.title, new.section_title, new.content, new.search_terms);
                END;

                CREATE TRIGGER IF NOT EXISTS kc_ad AFTER DELETE ON knowledge_chunks BEGIN
                    INSERT INTO knowledge_fts(knowledge_fts, rowid, title, section_title, content, search_terms)
                    VALUES ('delete', old.id, old.title, old.section_title, old.content, old.search_terms);
                END;

                CREATE TRIGGER IF NOT EXISTS kc_au AFTER UPDATE ON knowledge_chunks BEGIN
                    INSERT INTO knowledge_fts(knowledge_fts, rowid, title, section_title, content, search_terms)
                    VALUES ('delete', old.id, old.title, old.section_title, old.content, old.search_terms);
                    INSERT INTO knowledge_fts(rowid, title, section_title, content, search_terms)
                    VALUES (new.id, new.title, new.section_title, new.content, new.search_terms);
                END;
            """)
        conn.commit()

    # ------------------------------------------------------------------
    # Build / rebuild index
    # ------------------------------------------------------------------

    def _iter_indexable_sources(self, kb_root: Path):
        if not kb_root.is_dir():
            return
        for root, dirs, files in os.walk(kb_root):
            dirs[:] = [name for name in dirs if not name.startswith(".")]
            root_path = Path(root)
            for fname in sorted(files):
                if fname.startswith("."):
                    continue
                path = root_path / fname
                if path.suffix.lower() not in self._INDEXABLE_SUFFIXES:
                    continue
                yield path

    def compute_source_manifest(self, kb_root: Path) -> dict[str, str]:
        """Build a lightweight fingerprint of the current knowledge source tree."""
        normalized_root = str(kb_root.expanduser().resolve())
        digest = hashlib.sha256()
        file_count = 0

        for path in self._iter_indexable_sources(kb_root) or ():
            try:
                stat = path.stat()
            except OSError:
                continue
            rel_path = str(path.relative_to(kb_root)).replace(os.sep, "/")
            digest.update(rel_path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(stat.st_size).encode("ascii"))
            digest.update(b"\0")
            digest.update(str(stat.st_mtime_ns).encode("ascii"))
            digest.update(b"\0")
            file_count += 1

        return {
            "source_root": normalized_root,
            "source_fingerprint": digest.hexdigest(),
            "source_file_count": str(file_count),
        }

    def _set_meta(self, key: str, value: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO knowledge_meta (key, value) VALUES (?, ?)",
            (key, value),
        )

    def _get_meta(self, key: str) -> str:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value FROM knowledge_meta WHERE key = ?",
            (key,),
        ).fetchone()
        return str(row["value"]) if row else ""

    def get_build_manifest(self) -> dict[str, str]:
        if not self.db_path.exists():
            return {}
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM sqlite_master WHERE type='table' AND name='knowledge_meta'"
            ).fetchone()
            if not row or row["cnt"] == 0:
                return {}
            rows = conn.execute("SELECT key, value FROM knowledge_meta").fetchall()
        except Exception:
            return {}
        return {str(item["key"]): str(item["value"]) for item in rows}

    def is_up_to_date(self, kb_root: Path) -> bool:
        if not self.is_built() or not kb_root.is_dir():
            return False
        current = self.compute_source_manifest(kb_root)
        stored = self.get_build_manifest()
        return (
            stored.get("source_root", "") == current["source_root"]
            and stored.get("source_fingerprint", "") == current["source_fingerprint"]
        )

    def build(self, kb_root: Path) -> dict:
        """Index all documents under *kb_root*.  Returns stats dict."""
        self._ensure_schema()
        conn = self._get_conn()
        manifest = self.compute_source_manifest(kb_root)

        # Clear existing data for a clean rebuild
        conn.execute("DELETE FROM knowledge_chunks")
        conn.execute("DELETE FROM knowledge_meta")
        conn.commit()

        doc_count = 0
        chunk_count = 0
        domain_counts: dict[str, int] = {}
        type_counts: dict[str, int] = {}

        for result in iter_documents(kb_root):
            doc_count += 1
            for chunk in result.chunks:
                conn.execute(
                    """INSERT INTO knowledge_chunks
                       (source_path, title, domain, doc_type,
                        section_title, content, search_terms, content_hash)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        chunk.source_path,
                        chunk.title,
                        chunk.domain,
                        chunk.doc_type,
                        chunk.section_title,
                        chunk.content,
                        chunk.search_terms,
                        chunk.content_hash,
                    ),
                )
                chunk_count += 1
                domain_counts[chunk.domain] = domain_counts.get(chunk.domain, 0) + 1
                type_counts[chunk.doc_type] = type_counts.get(chunk.doc_type, 0) + 1

        for key, value in manifest.items():
            self._set_meta(key, value)
        self._set_meta("built_at", str(int(time.time())))
        conn.commit()
        logger.info("Indexed %d documents → %d chunks", doc_count, chunk_count)

        return {
            "documents": doc_count,
            "chunks": chunk_count,
            "domains": domain_counts,
            "types": type_counts,
            "db_path": str(self.db_path),
            **manifest,
        }

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    # Synonym table for runtime query expansion (Stage 7)
    _SYNONYMS: dict[str, list[str]] = {
        # Batch correction methods
        "batch correction": ["combat", "harmony", "scanorama", "mnn", "bbknn"],
        "combat": ["batch correction"],
        "harmony": ["batch correction", "integration"],
        # Clustering
        "clustering": ["leiden", "louvain", "cluster"],
        "leiden": ["clustering"],
        "louvain": ["clustering"],
        # Normalization
        "normalization": ["normalize", "scaling", "scran", "sctransform"],
        "sctransform": ["normalization", "variance stabilization"],
        # DE analysis
        "differential expression": ["deg", "de analysis", "deseq2", "edger"],
        "deg": ["differential expression", "differentially expressed genes"],
        "deseq2": ["differential expression", "de analysis"],
        # Enrichment
        "enrichment": ["ora", "gsea", "pathway analysis"],
        "gsea": ["enrichment", "gene set enrichment"],
        "ora": ["enrichment", "over-representation"],
        "pathway": ["enrichment", "kegg", "reactome", "go"],
        # QC
        "qc": ["quality control", "filtering", "doublet"],
        "quality control": ["qc", "filtering"],
        "doublet": ["scrublet", "doubletfinder"],
        # Dimension reduction
        "pca": ["dimension reduction", "dimensionality reduction", "embedding"],
        "umap": ["dimension reduction", "visualization"],
        "tsne": ["dimension reduction", "visualization"],
        # Cell annotation
        "annotation": ["cell type", "celltypist", "marker"],
        "cell type": ["annotation", "marker genes"],
        # Trajectory
        "trajectory": ["pseudotime", "rna velocity", "diffusion map"],
        "pseudotime": ["trajectory"],
    }

    @classmethod
    def _expand_synonyms(cls, query: str) -> str:
        """Expand query with synonym terms for better recall."""
        query_lower = query.lower()
        additions: list[str] = []

        for term, synonyms in cls._SYNONYMS.items():
            if term in query_lower:
                additions.extend(synonyms)

        if additions:
            # Deduplicate and remove terms already in the query
            unique = set()
            for a in additions:
                if a.lower() not in query_lower:
                    unique.add(a)
            if unique:
                expanded = query + " " + " ".join(unique)
                return expanded

        return query

    @classmethod
    def _strip_query_noise(cls, query: str) -> str:
        cleaned = str(query or "").lower()
        for phrase in cls._QUERY_NOISE_PHRASES:
            cleaned = cleaned.replace(phrase, " ")
        cleaned = re.sub(r"[^\w\u4e00-\u9fff+\-\.]+", " ", cleaned)
        return " ".join(cleaned.split())

    @classmethod
    def _extract_keyword_terms(cls, query: str) -> list[str]:
        terms: list[str] = []
        for word in re.findall(r"[a-z0-9][a-z0-9_\-+.]+", query.lower()):
            if len(word) < 3 or word in cls._QUERY_STOPWORDS:
                continue
            terms.append(word)

        for span in re.findall(r"[\u4e00-\u9fff]{2,}", query):
            trimmed = span
            for phrase in cls._QUERY_NOISE_PHRASES:
                if any("\u4e00" <= ch <= "\u9fff" for ch in phrase):
                    trimmed = trimmed.replace(phrase, "")
            trimmed = trimmed.strip()
            if len(trimmed) >= 2:
                terms.append(trimmed)

        return list(dict.fromkeys(term for term in terms if term))

    @classmethod
    def _build_search_candidates(cls, query: str) -> list[str]:
        candidates: list[str] = []

        def add(candidate: str) -> None:
            value = " ".join(str(candidate or "").split()).strip()
            if value and value not in candidates:
                candidates.append(value)

        normalized = " ".join(str(query or "").split()).strip()
        add(normalized)

        cleaned = cls._strip_query_noise(normalized)
        add(cleaned)

        keyword_terms = cls._extract_keyword_terms(cleaned or normalized)
        if keyword_terms:
            add(" ".join(keyword_terms[:6]))
            for term in keyword_terms[:4]:
                add(term)

        return candidates

    @staticmethod
    def _to_fts5_query(query: str) -> tuple[str, str]:
        """Convert free-text into FTS5 MATCH expressions.

        Returns (strict_query, relaxed_query) where strict uses AND
        and relaxed uses OR.  Caller should try strict first, fall back
        to relaxed if no results.
        """
        tokens = []
        for word in query.split():
            word = word.strip()
            if not word:
                continue
            word = word.replace('"', '""')
            tokens.append(f'"{word}"')
        if not tokens:
            raw = query.strip().replace('"', '""')
            expr = f'"{raw}"' if raw else ""
            return expr, expr
        strict = " AND ".join(tokens)
        relaxed = " OR ".join(tokens)
        return strict, relaxed

    def search(
        self,
        query: str,
        domain: Optional[str] = None,
        doc_type: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict]:
        """Full-text search returning ranked chunks.

        Applies synonym expansion (Stage 7) before FTS5 matching.
        Falls back to LIKE search if FTS5 MATCH returns no results.
        """
        self._ensure_schema()
        conn = self._get_conn()

        # Stage 7: Synonym expansion for relaxed query
        expanded_query = self._expand_synonyms(query)
        query_candidates = self._build_search_candidates(expanded_query)

        # Build WHERE filters
        filters = []
        params: list = []
        if domain and domain != "all":
            filters.append("kc.domain = ?")
            params.append(domain)
        if doc_type and doc_type != "all":
            filters.append("kc.doc_type = ?")
            params.append(doc_type)
        where_clause = (" AND " + " AND ".join(filters)) if filters else ""

        # 1. Try FTS5 MATCH — strict (AND) first, then relaxed (OR)
        fts_sql = f"""
            SELECT kc.*, bm25(knowledge_fts, 2.0, 1.5, 1.0, 0.5) AS rank
            FROM knowledge_fts fts
            JOIN knowledge_chunks kc ON kc.id = fts.rowid
            WHERE fts.knowledge_fts MATCH ?
            {where_clause}
            ORDER BY rank
            LIMIT ?
        """
        for candidate in query_candidates:
            strict_q, relaxed_q = self._to_fts5_query(candidate)
            for fts_expr in (strict_q, relaxed_q):
                if not fts_expr:
                    continue
                try:
                    rows = conn.execute(fts_sql, [fts_expr] + params + [limit]).fetchall()
                    if rows:
                        return [dict(r) for r in rows]
                except sqlite3.OperationalError:
                    pass  # Fall through

        # 2. Fallback: LIKE search on content + title
        like_sql = f"""
            SELECT kc.*, 0 AS rank
            FROM knowledge_chunks kc
            WHERE (kc.content LIKE ? OR kc.title LIKE ?
                   OR kc.section_title LIKE ? OR kc.search_terms LIKE ?)
            {where_clause}
            LIMIT ?
        """
        for candidate in query_candidates:
            like_pat = f"%{candidate}%"
            rows = conn.execute(
                like_sql,
                [like_pat, like_pat, like_pat, like_pat] + params + [limit],
            ).fetchall()
            if rows:
                return [dict(r) for r in rows]
        return []

    # ------------------------------------------------------------------
    # Utility queries
    # ------------------------------------------------------------------

    def get_document(self, source_path: str) -> list[dict]:
        """Return all chunks for a given source document."""
        self._ensure_schema()
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM knowledge_chunks WHERE source_path = ? ORDER BY id",
            (source_path,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_chunks(
        self,
        domain: Optional[str] = None,
        doc_type: Optional[str] = None,
    ) -> list[dict]:
        """Return indexed chunks, optionally filtered by domain and doc_type."""
        self._ensure_schema()
        conn = self._get_conn()

        filters = []
        params: list[str] = []
        if domain and domain != "all":
            filters.append("domain = ?")
            params.append(domain)
        if doc_type and doc_type != "all":
            filters.append("doc_type = ?")
            params.append(doc_type)
        where_clause = f" WHERE {' AND '.join(filters)}" if filters else ""

        rows = conn.execute(
            f"SELECT * FROM knowledge_chunks{where_clause} ORDER BY id",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def list_topics(self, domain: Optional[str] = None) -> list[dict]:
        """List distinct documents with their titles and domains."""
        self._ensure_schema()
        conn = self._get_conn()
        if domain and domain != "all":
            rows = conn.execute(
                """SELECT DISTINCT source_path, title, domain, doc_type
                   FROM knowledge_chunks WHERE domain = ?
                   ORDER BY doc_type, title""",
                (domain,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT DISTINCT source_path, title, domain, doc_type
                   FROM knowledge_chunks
                   ORDER BY domain, doc_type, title""",
            ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        """Return index statistics."""
        self._ensure_schema()
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0]
        docs = conn.execute(
            "SELECT COUNT(DISTINCT source_path) FROM knowledge_chunks"
        ).fetchone()[0]

        domain_rows = conn.execute(
            "SELECT domain, COUNT(*) AS cnt FROM knowledge_chunks GROUP BY domain ORDER BY cnt DESC"
        ).fetchall()
        type_rows = conn.execute(
            "SELECT doc_type, COUNT(*) AS cnt FROM knowledge_chunks GROUP BY doc_type ORDER BY cnt DESC"
        ).fetchall()

        return {
            "total_chunks": total,
            "total_documents": docs,
            "db_path": str(self.db_path),
            "by_domain": {r["domain"]: r["cnt"] for r in domain_rows},
            "by_type": {r["doc_type"]: r["cnt"] for r in type_rows},
            "build_manifest": self.get_build_manifest(),
        }

    def is_built(self) -> bool:
        """Check if the knowledge index has been built."""
        if not self.db_path.exists():
            return False
        try:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='knowledge_chunks'"
            ).fetchone()
            if not row or row[0] == 0:
                return False
            count = conn.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()
            if count[0] > 0:
                return True
            return bool(self._get_meta("source_fingerprint"))
        except Exception:
            return False
