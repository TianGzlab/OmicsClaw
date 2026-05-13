"""Predicate function tests for the lazy-injection context layer machinery.

Phase 4 of the system-prompt-compression refactor adds
``omicsclaw/runtime/predicates.py`` with 7 predicate functions that gate
conditional context layers (file-path discipline, AnnData preflight, PDF/paper
handling, workspace continuity, chat-mode, memory hygiene, capability
non-trivial gate). These tests are written here in Phase 1 (Task 1.4) so the
red bar is established before Phase 4 starts; each test is currently skipped.

Phase 4 will:
  1. Implement the 7 functions in ``omicsclaw/runtime/predicates.py``.
  2. Remove the ``@pytest.mark.skip`` markers (one per test).
  3. The tests should turn green without further edits.

Predicate signatures (target):

    def implementation_intent(req: ContextAssemblyRequest) -> bool: ...
    def anndata_or_file_path_in_query(req: ContextAssemblyRequest) -> bool: ...
    def pdf_or_paper_intent(req: ContextAssemblyRequest) -> bool: ...
    def workspace_active(req: ContextAssemblyRequest) -> bool: ...
    def chat_surface(req: ContextAssemblyRequest) -> bool: ...
    def memory_in_use(req: ContextAssemblyRequest) -> bool: ...
    def non_trivial_no_capability(req: ContextAssemblyRequest) -> bool: ...
"""

from __future__ import annotations

import pytest

from omicsclaw.runtime.context_layers import ContextAssemblyRequest

_PHASE_4_REASON = "Phase 4: implement runtime/predicates.py and unskip"


def _req(**kwargs) -> ContextAssemblyRequest:
    return ContextAssemblyRequest(**kwargs)


# --- implementation_intent ----------------------------------------------------

def test_implementation_intent_fires_on_implement_keyword() -> None:
    from omicsclaw.runtime.predicates import implementation_intent

    assert implementation_intent(_req(query="implement a new feature for sc-de")) is True


def test_implementation_intent_fires_on_chinese_keywords() -> None:
    from omicsclaw.runtime.predicates import implementation_intent

    assert implementation_intent(_req(query="帮我重构 cluster 模块")) is True
    assert implementation_intent(_req(query="添加一个新的 skill")) is True


def test_implementation_intent_quiet_on_plain_question() -> None:
    from omicsclaw.runtime.predicates import implementation_intent

    assert implementation_intent(_req(query="what is the structure of an h5ad file")) is False


def test_implementation_intent_quiet_on_empty_query() -> None:
    from omicsclaw.runtime.predicates import implementation_intent

    assert implementation_intent(_req(query="")) is False


# --- anndata_or_file_path_in_query --------------------------------------------

def test_anndata_or_file_path_fires_on_h5ad_extension() -> None:
    from omicsclaw.runtime.predicates import anndata_or_file_path_in_query

    assert anndata_or_file_path_in_query(_req(query="run sc-de on /data/sample.h5ad")) is True


def test_anndata_or_file_path_fires_on_known_extensions() -> None:
    from omicsclaw.runtime.predicates import anndata_or_file_path_in_query

    for ext in ("csv", "tsv", "fastq", "fq", "bam", "vcf", "mzML"):
        assert anndata_or_file_path_in_query(_req(query=f"file.{ext} please")) is True


def test_anndata_or_file_path_fires_on_absolute_path() -> None:
    from omicsclaw.runtime.predicates import anndata_or_file_path_in_query

    assert anndata_or_file_path_in_query(_req(query="data at /home/me/run42/output")) is True


def test_anndata_or_file_path_quiet_on_no_path_or_ext() -> None:
    from omicsclaw.runtime.predicates import anndata_or_file_path_in_query

    assert anndata_or_file_path_in_query(_req(query="explain UMAP")) is False


# --- pdf_or_paper_intent ------------------------------------------------------

def test_pdf_or_paper_intent_fires_on_pdf_extension() -> None:
    from omicsclaw.runtime.predicates import pdf_or_paper_intent

    assert pdf_or_paper_intent(_req(query="extract dataset from /tmp/paper.pdf")) is True


def test_pdf_or_paper_intent_fires_on_paper_keyword() -> None:
    from omicsclaw.runtime.predicates import pdf_or_paper_intent

    assert pdf_or_paper_intent(_req(query="summarize this paper for me")) is True
    assert pdf_or_paper_intent(_req(query="文献里提到的 GEO accession")) is True


def test_pdf_or_paper_intent_fires_on_geo_accession_pattern() -> None:
    from omicsclaw.runtime.predicates import pdf_or_paper_intent

    assert pdf_or_paper_intent(_req(query="get the GEO accession metadata")) is True


def test_pdf_or_paper_intent_quiet_on_unrelated_query() -> None:
    from omicsclaw.runtime.predicates import pdf_or_paper_intent

    assert pdf_or_paper_intent(_req(query="run sc-de on my data")) is False


# --- workspace_active ---------------------------------------------------------

def test_workspace_active_fires_when_workspace_set() -> None:
    from omicsclaw.runtime.predicates import workspace_active

    assert workspace_active(_req(workspace="/some/path")) is True


def test_workspace_active_fires_when_pipeline_workspace_set() -> None:
    from omicsclaw.runtime.predicates import workspace_active

    assert workspace_active(_req(pipeline_workspace="/some/path")) is True


def test_workspace_active_quiet_when_both_empty() -> None:
    from omicsclaw.runtime.predicates import workspace_active

    assert workspace_active(_req(workspace="", pipeline_workspace="")) is False


def test_workspace_active_quiet_when_whitespace_only() -> None:
    from omicsclaw.runtime.predicates import workspace_active

    assert workspace_active(_req(workspace="   ", pipeline_workspace="\t")) is False


# --- chat_surface -------------------------------------------------------------

def test_chat_surface_fires_on_bot() -> None:
    from omicsclaw.runtime.predicates import chat_surface

    assert chat_surface(_req(surface="bot")) is True


def test_chat_surface_quiet_on_interactive() -> None:
    from omicsclaw.runtime.predicates import chat_surface

    assert chat_surface(_req(surface="interactive")) is False


def test_chat_surface_quiet_on_pipeline() -> None:
    from omicsclaw.runtime.predicates import chat_surface

    assert chat_surface(_req(surface="pipeline")) is False


# --- memory_in_use ------------------------------------------------------------

def test_memory_in_use_fires_on_remember_keyword() -> None:
    from omicsclaw.runtime.predicates import memory_in_use

    assert memory_in_use(_req(query="please remember that I prefer DESeq2")) is True
    assert memory_in_use(_req(query="记住我用 Ubuntu 22.04")) is True


def test_memory_in_use_fires_on_forget_keyword() -> None:
    from omicsclaw.runtime.predicates import memory_in_use

    assert memory_in_use(_req(query="forget that I asked about velocity")) is True


def test_memory_in_use_quiet_on_unrelated_query() -> None:
    from omicsclaw.runtime.predicates import memory_in_use

    assert memory_in_use(_req(query="run sc-de")) is False


def test_memory_in_use_quiet_on_empty_query() -> None:
    from omicsclaw.runtime.predicates import memory_in_use

    assert memory_in_use(_req(query="")) is False


# --- preference_statement_intent ---------------------------------------------
# Gates the ``remember`` tool when the user states a persistent preference
# without uttering an explicit "记住 / remember" trigger. Co-exists with
# ``memory_in_use`` — ``remember`` fires on either predicate.

def test_preference_statement_fires_on_chinese_persistent_preference() -> None:
    from omicsclaw.runtime.predicates import preference_statement_intent

    # Real symptom from the desktop-app bug: user states a language preference
    # in Chinese without saying 记住.
    assert preference_statement_intent(_req(query="以后请用中文回答")) is True
    assert preference_statement_intent(_req(query="今后都用 DESeq2 跑 DE")) is True
    assert preference_statement_intent(_req(query="总是用 harmony 做整合")) is True
    assert preference_statement_intent(_req(query="默认用 leiden 聚类")) is True
    assert preference_statement_intent(_req(query="我习惯把 DPI 设成 300")) is True


def test_preference_statement_fires_on_english_persistent_preference() -> None:
    from omicsclaw.runtime.predicates import preference_statement_intent

    assert preference_statement_intent(
        _req(query="from now on use DESeq2 for DE")
    ) is True
    assert preference_statement_intent(
        _req(query="going forward, please reply in English")
    ) is True
    assert preference_statement_intent(
        _req(query="always use harmony for batch correction")
    ) is True
    assert preference_statement_intent(
        _req(query="I prefer to skip the doublet step")
    ) is True
    assert preference_statement_intent(
        _req(query="default to leiden clustering")
    ) is True


def test_preference_statement_quiet_on_non_preference_query() -> None:
    """Probes for false-positive triggers — common scientific phrasings
    that contain ``以后``/``默认``/``always`` as time/state adverbs rather
    than expressed preferences. These must NOT fire."""
    from omicsclaw.runtime.predicates import preference_statement_intent

    assert preference_statement_intent(_req(query="run sc-de")) is False
    assert preference_statement_intent(_req(query="explain UMAP")) is False
    # "以后" + 时间名词（不是动词）
    assert preference_statement_intent(_req(query="以后再说")) is False
    # "默认" 作形容词修饰参数名
    assert preference_statement_intent(
        _req(query="show me the default parameters")
    ) is False
    # bare "always" without a preference verb
    assert preference_statement_intent(
        _req(query="cells are always changing during differentiation")
    ) is False


def test_preference_statement_quiet_on_empty_query() -> None:
    from omicsclaw.runtime.predicates import preference_statement_intent

    assert preference_statement_intent(_req(query="")) is False


def test_preference_statement_acceptable_overfire_on_casual_taste() -> None:
    """Documents an intentional, low-cost over-fire boundary.

    Casual personal-taste statements ("我喜欢 X", "我习惯 X", momentary
    "请用 X" / "帮我把 X") fire this predicate even though they are not
    workflow preferences. The cost of an over-fire is one tool's schema
    (~600 tokens) briefly visible to the LLM, which still has to decide
    whether to actually call ``remember`` with a valid ``memory_type``
    (preference / insight / project_context). Keeping the regex
    permissive here trades a small context cost for not missing real
    declarative preferences — narrowing this would risk regressing the
    fix for the desktop-app silent-preference-loss bug.

    Future contributors: do not tighten without checking the regression
    suite in ``test_tool_list_lazy_exposure.py`` still passes.
    """
    from omicsclaw.runtime.predicates import preference_statement_intent

    assert preference_statement_intent(_req(query="我喜欢这首歌")) is True
    assert preference_statement_intent(_req(query="我习惯早起")) is True
    assert preference_statement_intent(_req(query="请用 git 提交这条")) is True


# --- non_trivial_no_capability ------------------------------------------------

def test_non_trivial_no_capability_fires_on_substantive_query_without_capability_block() -> None:
    from omicsclaw.runtime.predicates import non_trivial_no_capability

    req = _req(query="do differential expression analysis on my single-cell data", capability_context="")
    assert non_trivial_no_capability(req) is True


def test_non_trivial_no_capability_quiet_when_capability_block_present() -> None:
    from omicsclaw.runtime.predicates import non_trivial_no_capability

    req = _req(
        query="do differential expression analysis on my single-cell data",
        capability_context="## Deterministic Capability Assessment\n- coverage: exact_skill",
    )
    assert non_trivial_no_capability(req) is False


def test_non_trivial_no_capability_quiet_on_trivial_query() -> None:
    from omicsclaw.runtime.predicates import non_trivial_no_capability

    assert non_trivial_no_capability(_req(query="hi", capability_context="")) is False


def test_non_trivial_no_capability_quiet_on_empty_query() -> None:
    from omicsclaw.runtime.predicates import non_trivial_no_capability

    assert non_trivial_no_capability(_req(query="", capability_context="")) is False


# --- plot_intent (added in tool-list-compression Phase 1) --------------------


def test_plot_intent_fires_on_plot_keywords() -> None:
    from omicsclaw.runtime.predicates import plot_intent

    for query in (
        "enhance the umap plot",
        "show me a violin plot",
        "make the heatmap nicer",
        "visualize cluster boundaries",
        "make the figure prettier",
    ):
        assert plot_intent(_req(query=query)) is True, query


def test_plot_intent_fires_on_chinese_keywords() -> None:
    from omicsclaw.runtime.predicates import plot_intent

    assert plot_intent(_req(query="把图调整得更清楚")) is True
    assert plot_intent(_req(query="可视化聚类结果")) is True


def test_plot_intent_quiet_on_unrelated_query() -> None:
    from omicsclaw.runtime.predicates import plot_intent

    assert plot_intent(_req(query="run sc-de differential expression")) is False
    assert plot_intent(_req(query="explain UMAP to me")) is False


def test_plot_intent_quiet_on_empty_query() -> None:
    from omicsclaw.runtime.predicates import plot_intent

    assert plot_intent(_req(query="")) is False


# --- web_or_url_intent --------------------------------------------------------


def test_web_or_url_intent_fires_on_https_url() -> None:
    from omicsclaw.runtime.predicates import web_or_url_intent

    assert web_or_url_intent(_req(query="fetch https://example.com/page")) is True
    assert web_or_url_intent(_req(query="grab http://api.x.io/data")) is True


def test_web_or_url_intent_fires_on_web_keywords() -> None:
    from omicsclaw.runtime.predicates import web_or_url_intent

    for query in (
        "search the web for spatial deconvolution methods",
        "look up the website for scanpy",
        "scrape that page",
        "find the latest scvi tutorial online",
    ):
        assert web_or_url_intent(_req(query=query)) is True, query


def test_web_or_url_intent_fires_on_chinese_keywords() -> None:
    from omicsclaw.runtime.predicates import web_or_url_intent

    assert web_or_url_intent(_req(query="搜一下这个方法的论文网页")) is True


def test_web_or_url_intent_quiet_on_unrelated_query() -> None:
    from omicsclaw.runtime.predicates import web_or_url_intent

    assert web_or_url_intent(_req(query="run sc-de on /tmp/x.h5ad")) is False
    assert web_or_url_intent(_req(query="explain UMAP")) is False


# --- skill_creation_intent ----------------------------------------------------


def test_skill_creation_intent_fires_on_create_skill_keywords() -> None:
    from omicsclaw.runtime.predicates import skill_creation_intent

    for query in (
        "create a new skill for batch correction",
        "scaffold a skill that wraps deeptools",
        "I want to add a new skill for ATAC-seq",
        "package this analysis into a reusable skill",
    ):
        assert skill_creation_intent(_req(query=query)) is True, query


def test_skill_creation_intent_fires_on_chinese_keywords() -> None:
    from omicsclaw.runtime.predicates import skill_creation_intent

    assert skill_creation_intent(_req(query="封装成一个 skill")) is True
    assert skill_creation_intent(_req(query="新建 skill 模板")) is True


def test_skill_creation_intent_quiet_on_run_skill_query() -> None:
    """Running a skill is NOT creating one — the predicate must not
    over-fire on plain skill invocations."""
    from omicsclaw.runtime.predicates import skill_creation_intent

    assert skill_creation_intent(_req(query="run sc-de")) is False
    assert skill_creation_intent(_req(query="execute the spatial-preprocess skill")) is False


def test_skill_creation_intent_quiet_on_empty_query() -> None:
    from omicsclaw.runtime.predicates import skill_creation_intent

    assert skill_creation_intent(_req(query="")) is False
