"""Snapshot tests for the assembled bot tool list.

Phase 1 (T1.1) of the tool-list-compression refactor. Freezes the OpenAI
tool-list payload for 10 representative request shapes so the upcoming
predicate-gated lazy-load produces visible, reviewable diffs against a
known reference.

Usage:
    pytest tests/test_tool_list_snapshots.py            # verify
    UPDATE_SNAPSHOTS=1 pytest tests/test_tool_list_snapshots.py  # regenerate

Each fixture lives at ``tests/fixtures/tool_list/<scenario>.json`` and
contains:
- ``request``: the scenario inputs (surface, skill, query, ...)
- ``total_chars``: total chars across all tool descriptions + parameter schemas
- ``tool_count``: number of ToolSpecs visible
- ``tool_names``: sorted list of visible tool names
- ``tools``: full openai-tool serialized list (the payload that goes to the LLM)

Phase 1 baseline: every scenario sees all 41 tools (no per-request
filtering yet). Subsequent commits in this branch flip to
predicate-gated selection and the fixtures shrink dramatically.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from omicsclaw.runtime.bot_tools import BotToolContext, build_bot_tool_specs

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "tool_list"
UPDATE = os.environ.get("UPDATE_SNAPSHOTS", "").strip() not in ("", "0", "false", "False")


@dataclass(frozen=True)
class Scenario:
    name: str
    surface: str = "bot"
    skill: str = ""
    query: str = ""
    workspace: str = ""
    pipeline_workspace: str = ""
    capability_context: str = ""


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(name="baseline_bot"),
    Scenario(name="baseline_interactive", surface="interactive"),
    Scenario(
        name="realistic_bot_scde",
        surface="bot",
        skill="sc-de",
        query="do differential expression on /tmp/sample.h5ad",
    ),
    Scenario(
        name="realistic_bot_bulkrna_de",
        surface="bot",
        skill="bulkrna-de",
        query="run differential expression on /tmp/counts.csv",
    ),
    Scenario(
        name="realistic_bot_pdf_paper",
        surface="bot",
        query="extract GEO accession from /tmp/paper.pdf",
    ),
    Scenario(
        name="realistic_bot_workspace",
        surface="bot",
        query="show me the latest plan",
        workspace="/tmp/run42",
        pipeline_workspace="/tmp/run42",
    ),
    Scenario(
        name="realistic_bot_save_intent",
        surface="bot",
        query="implement and save a sc-de variant under output/",
    ),
    Scenario(
        name="realistic_bot_plot_intent",
        surface="bot",
        query="enhance the umap plot with bigger fonts",
    ),
    Scenario(
        name="realistic_bot_code_edit_intent",
        surface="bot",
        query="refactor sc-de.py to extract the threshold helper",
    ),
    Scenario(
        name="realistic_bot_web_intent",
        surface="bot",
        query="search the web for spatial deconvolution method comparison",
    ),
)


def _build_specs(scenario: Scenario):
    skills = (scenario.skill,) if scenario.skill else ("sc-de",)
    ctx = BotToolContext(skill_names=skills, domain_briefing="(test)")
    return build_bot_tool_specs(ctx)


def _serialize(scenario: Scenario) -> dict[str, Any]:
    specs = _build_specs(scenario)
    tools = [spec.to_openai_tool() for spec in specs]
    total_chars = sum(
        len(spec.description) + len(json.dumps(spec.parameters)) for spec in specs
    )
    return {
        "request": {
            "surface": scenario.surface,
            "skill": scenario.skill,
            "query": scenario.query,
            "workspace": scenario.workspace,
            "pipeline_workspace": scenario.pipeline_workspace,
            "capability_context": scenario.capability_context,
        },
        "total_chars": total_chars,
        "tool_count": len(specs),
        "tool_names": sorted(spec.name for spec in specs),
        "tools": tools,
    }


def _fixture_path(scenario: Scenario) -> Path:
    return FIXTURE_DIR / f"{scenario.name}.json"


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_tool_list_matches_snapshot(scenario: Scenario) -> None:
    actual = _serialize(scenario)
    fixture = _fixture_path(scenario)
    if UPDATE or not fixture.exists():
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        fixture.write_text(
            json.dumps(actual, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        if not UPDATE:
            pytest.skip(f"Snapshot created at {fixture}; rerun without UPDATE_SNAPSHOTS")
        return
    expected = json.loads(fixture.read_text(encoding="utf-8"))
    assert actual == expected, (
        f"\nSnapshot drift: {scenario.name}\n"
        f"  fixture: {fixture}\n"
        f"  actual total_chars: {actual['total_chars']} vs expected {expected.get('total_chars')}\n"
        f"  actual tool_count:  {actual['tool_count']} vs expected {expected.get('tool_count')}\n"
        f"  fix: rerun with UPDATE_SNAPSHOTS=1 and review the diff before committing."
    )


def test_all_scenarios_have_unique_names() -> None:
    names = [s.name for s in SCENARIOS]
    assert len(names) == len(set(names))


def test_at_least_ten_scenarios_cover_intent_categories() -> None:
    """Coverage guard: 10 scenarios over baseline + 4 intent categories
    that gate predicate-injected tools (file/path, pdf, workspace, plot,
    code-edit, web). Subsequent phases rely on these triggers firing /
    not-firing per scenario."""
    assert len(SCENARIOS) >= 10
    surfaces = {s.surface for s in SCENARIOS}
    assert "bot" in surfaces
    assert "interactive" in surfaces
