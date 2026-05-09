"""Phase 1 (T1.7) RED tests for the per-tool predicate mapping.

Verifies that each lazy-load tool is exposed iff its expected predicate
fires for the given request. The 8 always-on tools must appear in every
scenario regardless of query.

Coverage map (mirrors plan section "Wire 33 lazy-load tools to predicates"):

| Predicate                          | Tools                                     |
|------------------------------------|-------------------------------------------|
| (none — always-on)                 | omicsclaw, resolve_capability,            |
|                                    | consult_knowledge, inspect_data,          |
|                                    | list_directory, glob_files, file_read,    |
|                                    | read_knowhow                              |
| anndata_or_file_path_in_query      | save_file, write_file, inspect_file,      |
|                                    | make_directory, move_file, remove_file,   |
|                                    | get_file_size, file_write, file_edit,     |
|                                    | grep_files, tool_search, create_json_file,|
|                                    | create_csv_file                           |
| pdf_or_paper_intent                | parse_literature, fetch_geo_metadata      |
| memory_in_use                      | remember, recall, forget                  |
| implementation_intent              | custom_analysis_execute                   |
| workspace_active                   | todo_write, task_create, task_get,        |
|                                    | task_list, task_update                    |
| non_trivial_no_capability          | list_skills_in_domain                     |
| plot_intent                        | replot_skill                              |
| web_or_url_intent                  | web_method_search, web_fetch, web_search, |
|                                    | download_file                             |
| skill_creation_intent              | create_omics_skill                        |
| (custom: "mcp" keyword)            | mcp_list                                  |
| (custom: audio keywords)           | generate_audio                            |
"""

from __future__ import annotations

import pytest

from omicsclaw.runtime.bot_tools import BotToolContext, build_bot_tool_specs
from omicsclaw.runtime.context_layers import ContextAssemblyRequest
from omicsclaw.runtime.tool_registry import select_tool_specs


def _all_specs():
    ctx = BotToolContext(skill_names=("sc-de",), domain_briefing="(test)")
    return build_bot_tool_specs(ctx)


def _selected_names(query: str = "", **kwargs) -> set[str]:
    req = ContextAssemblyRequest(surface="bot", query=query, **kwargs)
    return {s.name for s in select_tool_specs(_all_specs(), request=req)}


ALWAYS_ON = (
    "omicsclaw",
    "resolve_capability",
    "consult_knowledge",
    "inspect_data",
    "list_directory",
    "glob_files",
    "file_read",
    "read_knowhow",
)


# --- Always-on tools never get filtered out ----------------------------------


@pytest.mark.parametrize("tool", ALWAYS_ON)
def test_always_on_tool_visible_with_empty_query(tool: str) -> None:
    assert tool in _selected_names(query="")


@pytest.mark.parametrize("tool", ALWAYS_ON)
def test_always_on_tool_visible_with_unrelated_query(tool: str) -> None:
    assert tool in _selected_names(query="hello there")


# --- Lazy-load mapping: file/path triggers -----------------------------------


FILE_PATH_TOOLS = (
    "save_file",
    "write_file",
    "inspect_file",
    "make_directory",
    "move_file",
    "remove_file",
    "get_file_size",
    "file_write",
    "file_edit",
    "grep_files",
    "tool_search",
    "create_json_file",
    "create_csv_file",
)


@pytest.mark.parametrize("tool", FILE_PATH_TOOLS)
def test_file_path_tool_appears_when_h5ad_in_query(tool: str) -> None:
    assert tool in _selected_names(query="run sc-de on /tmp/x.h5ad")


@pytest.mark.parametrize("tool", FILE_PATH_TOOLS)
def test_file_path_tool_hidden_when_no_path(tool: str) -> None:
    assert tool not in _selected_names(query="explain UMAP")


# --- Lazy-load mapping: PDF / paper ------------------------------------------


@pytest.mark.parametrize("tool", ("parse_literature", "fetch_geo_metadata"))
def test_pdf_paper_tool_appears_on_pdf_query(tool: str) -> None:
    assert tool in _selected_names(query="extract from /tmp/paper.pdf")


@pytest.mark.parametrize("tool", ("parse_literature", "fetch_geo_metadata"))
def test_pdf_paper_tool_hidden_on_unrelated_query(tool: str) -> None:
    assert tool not in _selected_names(query="run sc-de")


# --- Lazy-load mapping: memory -----------------------------------------------


@pytest.mark.parametrize("tool", ("remember", "recall", "forget"))
def test_memory_tool_appears_on_memory_query(tool: str) -> None:
    assert tool in _selected_names(query="please remember I prefer DESeq2")


@pytest.mark.parametrize("tool", ("remember", "recall", "forget"))
def test_memory_tool_hidden_on_unrelated_query(tool: str) -> None:
    assert tool not in _selected_names(query="run sc-de")


# --- Lazy-load mapping: implementation intent --------------------------------


def test_custom_analysis_execute_appears_on_implement_query() -> None:
    assert "custom_analysis_execute" in _selected_names(
        query="implement a new sc-de variant"
    )


def test_custom_analysis_execute_hidden_on_plain_query() -> None:
    assert "custom_analysis_execute" not in _selected_names(query="explain UMAP")


# --- Lazy-load mapping: workspace_active -------------------------------------


WORKSPACE_TOOLS = ("todo_write", "task_create", "task_get", "task_list", "task_update")


@pytest.mark.parametrize("tool", WORKSPACE_TOOLS)
def test_workspace_tool_appears_when_workspace_set(tool: str) -> None:
    assert tool in _selected_names(query="show plan", workspace="/tmp/run42")


@pytest.mark.parametrize("tool", WORKSPACE_TOOLS)
def test_workspace_tool_hidden_when_no_workspace(tool: str) -> None:
    assert tool not in _selected_names(query="show plan")


# --- Lazy-load mapping: non_trivial_no_capability ----------------------------


def test_list_skills_in_domain_appears_on_substantive_no_capability() -> None:
    assert "list_skills_in_domain" in _selected_names(
        query="do differential expression on single-cell data",
        capability_context="",
    )


def test_list_skills_in_domain_hidden_when_capability_present() -> None:
    assert "list_skills_in_domain" not in _selected_names(
        query="do differential expression on single-cell data",
        capability_context="## Deterministic Capability Assessment\n- coverage: exact_skill",
    )


# --- Lazy-load mapping: plot_intent ------------------------------------------


def test_replot_skill_appears_on_plot_query() -> None:
    assert "replot_skill" in _selected_names(query="enhance the violin plot")


def test_replot_skill_hidden_on_non_plot_query() -> None:
    assert "replot_skill" not in _selected_names(query="run sc-de")


# --- Lazy-load mapping: web_or_url_intent ------------------------------------


WEB_TOOLS = ("web_method_search", "web_fetch", "web_search", "download_file")


@pytest.mark.parametrize("tool", WEB_TOOLS)
def test_web_tool_appears_on_url_query(tool: str) -> None:
    assert tool in _selected_names(query="search the web for spatial deconv methods")


@pytest.mark.parametrize("tool", WEB_TOOLS)
def test_web_tool_hidden_on_unrelated_query(tool: str) -> None:
    assert tool not in _selected_names(query="run sc-de on /tmp/x.h5ad")


# --- Lazy-load mapping: skill_creation_intent --------------------------------


def test_create_omics_skill_appears_on_create_query() -> None:
    assert "create_omics_skill" in _selected_names(
        query="create a new skill for batch correction"
    )


def test_create_omics_skill_hidden_on_run_query() -> None:
    assert "create_omics_skill" not in _selected_names(query="run sc-de")


# --- Lazy-load mapping: niche tools ------------------------------------------


def test_generate_audio_hidden_by_default() -> None:
    """``generate_audio`` is niche — gate it on explicit audio keywords."""
    assert "generate_audio" not in _selected_names(query="run sc-de")
    assert "generate_audio" not in _selected_names(query="explain UMAP")


def test_generate_audio_appears_on_audio_query() -> None:
    assert "generate_audio" in _selected_names(query="generate a podcast summary")
    assert "generate_audio" in _selected_names(query="generate audio for this report")


def test_mcp_list_hidden_by_default() -> None:
    assert "mcp_list" not in _selected_names(query="run sc-de")


def test_mcp_list_appears_on_mcp_query() -> None:
    assert "mcp_list" in _selected_names(query="what mcp servers are available")


# --- Aggregate count assertions ---------------------------------------------


def test_baseline_query_only_shows_always_on_set() -> None:
    """Baseline (empty query, no workspace, no capability) should show
    exactly the 8 always-on tools and nothing else."""
    selected = _selected_names(query="")
    extras = selected - set(ALWAYS_ON)
    assert extras == set(), f"unexpected non-always-on tools fired: {extras}"
    missing = set(ALWAYS_ON) - selected
    assert missing == set(), f"always-on tools missing: {missing}"


def test_realistic_scde_turn_count_well_under_full_set() -> None:
    """Realistic sc-de query exposes always-on + file-path tools, but
    keeps memory / pdf / web / plot tools hidden."""
    selected = _selected_names(query="run sc-de on /tmp/x.h5ad")
    assert len(selected) <= 25, (
        f"realistic sc-de turn exposed {len(selected)} tools; expected <= 25 "
        f"(always-on 8 + file-path ~13 + maybe non_trivial fallback): {sorted(selected)}"
    )
    assert len(selected) < 41, "ALL 41 tools shown — predicate gating not applied"
    assert "remember" not in selected
    assert "parse_literature" not in selected
    assert "web_search" not in selected
    assert "replot_skill" not in selected
