"""
OmicsClaw Knowledge Advisor — searchable reference knowledge base.

Indexes markdown documents and reference scripts from the knowledge_base/
directory into a SQLite FTS5 store, enabling fast full-text search for
decision guides, best practices, troubleshooting, and workflow references.

Extended with:
- KnowledgeTelemetry: observability and audit logging (Plan Stage 0)
- KnowHowInjector: mandatory scientific constraint injection (Plan Stage 1)
- AdvisoryEvent / KnowledgeResolver: deterministic routing (Plan Stages 2+4)
- KnowledgeRegistry: metadata parsing/validation utilities for knowledge docs
"""

from .retriever import KnowledgeAdvisor
from .knowhow import KnowHowInjector, get_knowhow_injector
from .resolver import AdvisoryEvent, KnowledgeResolver, get_resolver
from .telemetry import KnowledgeTelemetry, get_telemetry
from .registry import KnowledgeRegistry

__all__ = [
    "KnowledgeAdvisor",
    "KnowHowInjector",
    "get_knowhow_injector",
    "AdvisoryEvent",
    "KnowledgeResolver",
    "get_resolver",
    "KnowledgeTelemetry",
    "get_telemetry",
    "KnowledgeRegistry",
]
