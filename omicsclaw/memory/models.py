# pyright: reportArgumentType=false, reportAttributeAccessIssue=false

"""
ORM Models for OmicsClaw Graph Memory System.

Ported from nocturne_memory with OmicsClaw adaptations.

Graph-based memory storage with:
- Node: a conceptual entity (UUID), version-independent
- Memory: a content version of a node
- Edge: parent→child relationship between nodes, carrying metadata
- Path: materialized URI cache (domain://path → edge)
"""

from datetime import datetime
from typing import Dict, Any, List

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# Sentinel root node — parent_uuid of all top-level edges.
# Using a fixed UUID instead of NULL avoids SQLite's NULL != NULL uniqueness quirk.
ROOT_NODE_UUID = "00000000-0000-0000-0000-000000000000"


# =============================================================================
# Shared Utilities
# =============================================================================


def escape_like_literal(value: str) -> str:
    """Escape special chars in SQL LIKE patterns for literal matching."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def serialize_row(obj) -> Dict[str, Any]:
    """Convert an ORM model instance to a plain dict for snapshot storage."""
    d = {}
    for col in obj.__table__.columns:
        val = getattr(obj, col.name)
        if isinstance(val, datetime):
            val = val.isoformat()
        d[col.name] = val
    return d


def serialize_memory_ref(obj) -> Dict[str, Any]:
    """Serialize a Memory row as a pointer (no content).

    The actual content stays in the DB and is resolved at review time.
    """
    d = serialize_row(obj)
    d.pop("content", None)
    return d


# =============================================================================
# ORM Models
# =============================================================================


class Node(Base):
    """A conceptual entity whose UUID persists across content versions.

    Edges reference nodes by UUID, so updating a memory's content (which
    creates a new Memory row) never requires touching the graph structure.
    """

    __tablename__ = "nodes"

    uuid = Column(String(36), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    memories = relationship("Memory", back_populates="node")
    child_edges = relationship(
        "Edge", foreign_keys="Edge.child_uuid", back_populates="child_node"
    )
    parent_edges = relationship(
        "Edge", foreign_keys="Edge.parent_uuid", back_populates="parent_node"
    )


class Memory(Base):
    """A single content version of a node.

    Version chain: old.migrated_to → new.id.  All versions of the same
    conceptual entity share the same node_uuid.
    """

    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    node_uuid = Column(String(36), ForeignKey("nodes.uuid"), nullable=True)
    content = Column(Text, nullable=False)
    deprecated = Column(Boolean, default=False)
    migrated_to = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    node = relationship("Node", back_populates="memories")


class Edge(Base):
    """Directed parent→child relationship between two nodes.

    Carries display name, priority, and disclosure.  The (parent_uuid,
    child_uuid) pair is unique — one edge per structural relationship.
    Multiple Path rows can reference the same edge (aliases).
    """

    __tablename__ = "edges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    parent_uuid = Column(String(36), ForeignKey("nodes.uuid"), nullable=False)
    child_uuid = Column(String(36), ForeignKey("nodes.uuid"), nullable=False)
    name = Column(String(256), nullable=False)
    priority = Column(Integer, default=0)
    disclosure = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("parent_uuid", "child_uuid", name="uq_edge_parent_child"),
    )

    parent_node = relationship(
        "Node", foreign_keys=[parent_uuid], back_populates="parent_edges"
    )
    child_node = relationship(
        "Node", foreign_keys=[child_uuid], back_populates="child_edges"
    )
    paths = relationship("Path", back_populates="edge")


class Path(Base):
    """Materialized URI cache: (namespace, domain, path_string) → edge.

    The source of truth for tree structure is the edges table.
    Paths are a routing convenience for URI resolution. ``namespace``
    partitions identical (domain, path) URIs across surfaces/users.
    Default ``__shared__`` keeps legacy callers (GraphService) writing into
    the same partition they always have.
    """

    __tablename__ = "paths"

    namespace = Column(
        String(128), primary_key=True, nullable=False, default="__shared__"
    )
    domain = Column(String(64), primary_key=True, default="core")
    path = Column(String(512), primary_key=True)
    edge_id = Column(Integer, ForeignKey("edges.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    edge = relationship("Edge", back_populates="paths")


class GlossaryKeyword(Base):
    """Glossary keyword-to-node binding, partitioned by namespace.

    When a keyword appears in a memory's content, the frontend highlights
    the keyword and links it to the associated node. Each namespace owns
    its own keyword set; ``__shared__`` keywords are visible to all.
    """

    __tablename__ = "glossary_keywords"

    id = Column(Integer, primary_key=True, autoincrement=True)
    keyword = Column(Text, nullable=False)
    node_uuid = Column(
        String(36),
        ForeignKey("nodes.uuid", ondelete="CASCADE"),
        nullable=False,
    )
    namespace = Column(
        String(128), nullable=False, default="__shared__"
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "namespace", "keyword", "node_uuid", name="uq_glossary_keyword_node"
        ),
    )

    node = relationship("Node")


class SearchDocument(Base):
    """Derived search row for one reachable path of an active node.

    Composite PK ``(namespace, domain, path)`` matches Path's so the indexer
    can refresh exactly one row per write target.
    """

    __tablename__ = "search_documents"

    namespace = Column(
        String(128), primary_key=True, nullable=False, default="__shared__"
    )
    domain = Column(String(64), primary_key=True, default="core")
    path = Column(String(512), primary_key=True)
    node_uuid = Column(
        String(36),
        ForeignKey("nodes.uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    memory_id = Column(
        Integer,
        ForeignKey("memories.id", ondelete="CASCADE"),
        nullable=False,
    )
    uri = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    disclosure = Column(Text, nullable=True)
    search_terms = Column(Text, nullable=False, default="")
    priority = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow)


# =============================================================================
# Change Collector
# =============================================================================


class ChangeCollector:
    """Accumulates serialized row data before mutations for changeset recording.

    Passed optionally through the operation layers so that each delete
    primitive can record pre-deletion state without coupling the "what to
    record" concern into the "what to delete" logic.
    """

    def __init__(self):
        self.nodes: List[Dict[str, Any]] = []
        self.memories: List[Dict[str, Any]] = []
        self.edges: List[Dict[str, Any]] = []
        self.paths: List[Dict[str, Any]] = []
        self.glossary_keywords: List[Dict[str, Any]] = []

    def record(self, table: str, row_data: Dict[str, Any]):
        if table == "memories":
            row_data = {k: v for k, v in row_data.items() if k != "content"}
        getattr(self, table).append(row_data)

    def to_dict(self) -> Dict[str, list]:
        return {
            "nodes": self.nodes,
            "memories": self.memories,
            "edges": self.edges,
            "paths": self.paths,
            "glossary_keywords": self.glossary_keywords,
        }
