import os

from omicsclaw.knowledge import KnowledgeAdvisor
from omicsclaw.knowledge.retriever import clear_runtime_notices, consume_runtime_notice


def test_knowledge_advisor_search_formatted_auto_builds_index(tmp_path):
    clear_runtime_notices()
    kb_root = tmp_path / "knowledge_base"
    doc_dir = kb_root / "03_best_practices"
    doc_dir.mkdir(parents=True)
    (doc_dir / "singlecell-marker-guide.md").write_text(
        """---
title: Single-Cell Marker Genes
category: singlecell
---

# Single-Cell Marker Genes

## Recommended markers
Marker genes such as CD3D and EPCAM help annotate single-cell clusters.
""",
        encoding="utf-8",
    )

    advisor = KnowledgeAdvisor(db_path=tmp_path / "knowledge.db")
    advisor.kb_root = kb_root

    assert advisor.ensure_available(auto_build=False) is False

    result = advisor.search_formatted(
        query="marker genes",
        domain="singlecell",
        doc_type="best-practices",
        limit=2,
        auto_build=True,
    )

    assert 'Knowledge base results for: "marker genes"' in result
    assert "Single-Cell Marker Genes" in result
    assert "singlecell-marker-guide.md" in result
    assert advisor.ensure_available(auto_build=False) is True
    assert consume_runtime_notice() == "Knowledge base indexed automatically (1 file(s))."
    assert consume_runtime_notice() == ""


def test_knowledge_advisor_uses_semantic_fallback_for_paraphrased_queries(tmp_path):
    clear_runtime_notices()
    kb_root = tmp_path / "knowledge_base"
    doc_dir = kb_root / "03_best_practices"
    doc_dir.mkdir(parents=True)
    (doc_dir / "batch-integration-guide.md").write_text(
        """---
title: Batch Integration Guide
category: singlecell
---

# Batch Integration Guide

## Method selection
Harmony corrects batch effects in single-cell data and is a strong baseline
for integration before downstream clustering.
""",
        encoding="utf-8",
    )

    advisor = KnowledgeAdvisor(db_path=tmp_path / "knowledge.db")
    advisor.kb_root = kb_root

    result = advisor.search_formatted(
        query="harmonization for batches",
        domain="singlecell",
        doc_type="best-practices",
        limit=2,
        auto_build=True,
    )

    assert "Batch Integration Guide" in result
    assert "batch-integration-guide.md" in result


def test_knowledge_advisor_auto_rebuilds_when_new_documents_are_added(tmp_path):
    clear_runtime_notices()
    kb_root = tmp_path / "knowledge_base"
    doc_dir = kb_root / "03_best_practices"
    doc_dir.mkdir(parents=True)
    (doc_dir / "initial-guide.md").write_text(
        """---
title: Initial Guide
category: singlecell
---

# Initial Guide

## Notes
Initial marker guidance.
""",
        encoding="utf-8",
    )

    advisor = KnowledgeAdvisor(db_path=tmp_path / "knowledge.db")
    advisor.kb_root = kb_root
    assert advisor.search("initial marker", domain="singlecell", doc_type="best-practices")

    new_doc = doc_dir / "new-guide.md"
    new_doc.write_text(
        """---
title: New Guide
category: singlecell
---

# New Guide

## Notes
Novel integration recipe with keyword xenobridge.
""",
        encoding="utf-8",
    )
    os.utime(new_doc, None)

    result = advisor.search_formatted(
        query="xenobridge",
        domain="singlecell",
        doc_type="best-practices",
        limit=2,
        auto_build=True,
    )

    assert "New Guide" in result
    assert "new-guide.md" in result
    assert consume_runtime_notice() == "Knowledge base indexed automatically (1 file(s))."
    assert consume_runtime_notice() == "Knowledge base updated; index refreshed automatically (2 file(s))."
    assert consume_runtime_notice() == ""


def test_knowledge_advisor_auto_rebuilds_when_documents_change_or_are_deleted(tmp_path):
    clear_runtime_notices()
    kb_root = tmp_path / "knowledge_base"
    doc_dir = kb_root / "03_best_practices"
    doc_dir.mkdir(parents=True)
    guide = doc_dir / "mutable-guide.md"
    guide.write_text(
        """---
title: Mutable Guide
category: spatial
---

# Mutable Guide

## Notes
Original keyword alpha-signal.
""",
        encoding="utf-8",
    )

    advisor = KnowledgeAdvisor(db_path=tmp_path / "knowledge.db")
    advisor.kb_root = kb_root
    assert advisor.search("alpha-signal", domain="spatial", doc_type="best-practices")

    guide.write_text(
        """---
title: Mutable Guide
category: spatial
---

# Mutable Guide

## Notes
Updated keyword beta-refresh with more content.
""",
        encoding="utf-8",
    )
    os.utime(guide, None)

    refreshed = advisor.search_formatted(
        query="beta-refresh",
        domain="spatial",
        doc_type="best-practices",
        limit=2,
        auto_build=True,
    )
    assert "Mutable Guide" in refreshed
    assert "beta-refresh" in refreshed

    guide.unlink()

    missing = advisor.search_formatted(
        query="beta-refresh",
        domain="spatial",
        doc_type="best-practices",
        limit=2,
        auto_build=True,
    )
    assert missing == "No knowledge base results found for: beta-refresh"
    assert consume_runtime_notice() == "Knowledge base indexed automatically (1 file(s))."
    assert consume_runtime_notice() == "Knowledge base updated; index refreshed automatically (1 file(s))."
    assert consume_runtime_notice() == "Knowledge base updated; index refreshed automatically (0 file(s))."
    assert consume_runtime_notice() == ""
