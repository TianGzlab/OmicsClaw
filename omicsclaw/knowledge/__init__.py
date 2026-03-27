"""
OmicsClaw Knowledge Advisor — searchable reference knowledge base.

Indexes markdown documents and reference scripts from the knowledge_base/
directory into a SQLite FTS5 store, enabling fast full-text search for
decision guides, best practices, troubleshooting, and workflow references.
"""

from .retriever import KnowledgeAdvisor

__all__ = ["KnowledgeAdvisor"]
