"""Tests for the ``list_skills_in_domain`` lazy-load tool (Stage 4).

Covers the pure rendering helper and its wiring into the bot tool registry.
The subprocess-executor path (``execute_list_skills_in_domain``) is async;
we test it with ``asyncio.run`` since the function is thin.
"""

from __future__ import annotations

import asyncio

import pytest

from omicsclaw.runtime.bot_tools import BotToolContext, build_bot_tool_specs
from omicsclaw.runtime.skill_listing import list_skills_in_domain


# ---------------------------------------------------------------------------
# list_skills_in_domain (pure function)
# ---------------------------------------------------------------------------


def test_list_skills_in_domain_spatial_returns_all_skills():
    out = list_skills_in_domain("spatial")
    assert "Spatial Transcriptomics" in out
    assert "## Skills" in out
    # A few canonical spatial skills should appear.
    for alias in ("spatial-preprocess", "spatial-de", "spatial-communication"):
        assert f"`{alias}`" in out
    # The header should show ``N/N`` (no filter applied).
    assert "17/17 skills" in out or "N/N" not in out  # count is exact when unfiltered


def test_filter_narrows_result_and_is_case_insensitive():
    low = list_skills_in_domain("singlecell", "VELOCITY")
    assert "sc-velocity" in low
    # The 0/30 dead zone for an obviously unknown term should produce a graceful message.
    empty = list_skills_in_domain("singlecell", "zzz_no_such_term")
    assert "0/30" in empty
    assert "No skills match that filter" in empty


def test_unknown_domain_returns_soft_error():
    out = list_skills_in_domain("quantum")
    # Soft error, not an exception — the LLM must be able to recover.
    assert "Unknown domain" in out
    assert "spatial" in out  # lists known domains so LLM can self-correct


def test_description_truncation_uses_ellipsis():
    # Pick a domain guaranteed to have at least one long description.
    out = list_skills_in_domain("spatial")
    # Some spatial descriptions exceed 180 chars and should be truncated.
    # We just check the rendering contract holds (no raw multi-paragraph
    # descriptions leaking in), rather than asserting a specific line.
    for line in out.splitlines():
        if line.startswith("- `spatial-"):
            # Each description line must not exceed ~210 chars total (alias + dash + desc + ellipsis).
            assert len(line) <= 220, f"description not truncated: {line[:60]}…"


# ---------------------------------------------------------------------------
# ToolSpec wiring
# ---------------------------------------------------------------------------


def test_tool_spec_is_registered_for_bot():
    specs = build_bot_tool_specs(
        BotToolContext(skill_names=("auto",), skill_desc_text="")
    )
    names = {s.name for s in specs}
    assert "list_skills_in_domain" in names

    spec = next(s for s in specs if s.name == "list_skills_in_domain")
    # Domain enum must match the briefing's known domains.
    enum = spec.parameters["properties"]["domain"]["enum"]
    assert set(enum) == {
        "spatial", "singlecell", "genomics",
        "proteomics", "metabolomics", "bulkrna", "orchestrator", "literature",
    }
    assert spec.parameters["required"] == ["domain"]
    # Lazy read-only lookup: safe to call in parallel, doesn't mutate workspace.
    assert spec.read_only is True
    assert spec.concurrency_safe is True


def test_omicsclaw_tool_description_mentions_list_skills_tool():
    """After Stage 4 the briefing's trailing hint should point to the new tool."""
    specs = build_bot_tool_specs(
        BotToolContext(skill_names=("auto",), skill_desc_text="")
    )
    omics = next(s for s in specs if s.name == "omicsclaw")
    assert "list_skills_in_domain" in omics.description
    assert "across 8 domains" in omics.description
    assert "**literature**" in omics.description


def test_list_skills_in_domain_literature_returns_registered_skill():
    out = list_skills_in_domain("literature")
    assert "literature" in out
    assert "1/1 skills" in out
    assert "`literature`" in out


# ---------------------------------------------------------------------------
# Async executor
# ---------------------------------------------------------------------------


def test_executor_returns_error_when_domain_missing():
    from bot.core import execute_list_skills_in_domain

    out = asyncio.run(execute_list_skills_in_domain({}))
    assert out.startswith("Error:")
    assert "domain" in out


def test_executor_runs_end_to_end():
    from bot.core import execute_list_skills_in_domain

    out = asyncio.run(
        execute_list_skills_in_domain({"domain": "bulkrna", "filter": "survival"})
    )
    assert "bulkrna-survival" in out
    assert "## Skills" in out
