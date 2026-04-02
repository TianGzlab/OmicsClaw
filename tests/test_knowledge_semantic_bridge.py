import asyncio

from omicsclaw.knowledge import KnowledgeAdvisor
from omicsclaw.knowledge.semantic_bridge import (
    generate_query_rewrites,
    rerank_candidates_with_llm,
)


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, responses: list[str]):
        self._responses = list(responses)

    async def create(self, **kwargs):
        return _FakeResponse(self._responses.pop(0))


class _FakeLLM:
    def __init__(self, responses: list[str]):
        self.chat = self
        self.completions = _FakeCompletions(responses)


def test_generate_query_rewrites_and_bridge_cross_language_search(tmp_path):
    kb_root = tmp_path / "knowledge_base"
    doc_dir = kb_root / "03_best_practices"
    doc_dir.mkdir(parents=True)
    (doc_dir / "spatial-svg-guide.md").write_text(
        """---
title: Spatially Variable Genes Guide
category: spatial
---

# Spatially Variable Genes Guide

## Method selection
Spatially variable gene analysis commonly uses Moran's I, SPARK-X, and SpatialDE.
""",
        encoding="utf-8",
    )

    advisor = KnowledgeAdvisor(db_path=tmp_path / "knowledge.db")
    advisor.kb_root = kb_root

    base_results = advisor.search(
        query="帮我推荐适合这个数据的空间变异基因方法",
        domain="spatial",
        doc_type="best-practices",
        limit=2,
        auto_build=True,
    )
    assert base_results == []

    fake_llm = _FakeLLM(
        ['{"queries":["spatially variable genes","moran spatialde spark-x"]}']
    )
    rewrites = asyncio.run(
        generate_query_rewrites(
            query="帮我推荐适合这个数据的空间变异基因方法",
            domain="spatial",
            doc_type="best-practices",
            llm_client=fake_llm,
            model="fake-model",
        )
    )

    assert rewrites == ["spatially variable genes", "moran spatialde spark-x"]

    bridged_results = advisor.search(
        query="帮我推荐适合这个数据的空间变异基因方法",
        domain="spatial",
        doc_type="best-practices",
        limit=2,
        auto_build=True,
        extra_queries=rewrites,
    )
    assert bridged_results
    assert bridged_results[0]["title"] == "Spatially Variable Genes Guide"


def test_rerank_candidates_with_llm_reorders_results():
    fake_llm = _FakeLLM(['{"ordered_ids":["r2","r1"]}'])
    candidates = [
        {
            "title": "Generic Workflow",
            "section_title": "Overview",
            "content": "General workflow.",
            "domain": "spatial",
            "doc_type": "workflow",
        },
        {
            "title": "Spatially Variable Genes Guide",
            "section_title": "Method selection",
            "content": "Use Moran's I, SPARK-X, and SpatialDE.",
            "domain": "spatial",
            "doc_type": "best-practices",
        },
    ]

    reranked = asyncio.run(
        rerank_candidates_with_llm(
            query="Which spatially variable gene method should I use?",
            candidates=candidates,
            llm_client=fake_llm,
            model="fake-model",
            limit=2,
        )
    )

    assert reranked[0]["title"] == "Spatially Variable Genes Guide"
