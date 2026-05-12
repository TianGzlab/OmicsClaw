"""Snapshot tests for the assembled system prompt.

Phase 1 (Task 1.1) of the system-prompt-compression refactor. These tests
freeze the system prompt content for 10 representative request shapes so
that subsequent phases produce visible, reviewable diffs against a known
baseline rather than free-floating regression risk.

Usage:
    pytest tests/test_system_prompt_snapshots.py            # verify
    UPDATE_SNAPSHOTS=1 pytest tests/test_system_prompt_snapshots.py  # regenerate

Each fixture lives at ``tests/fixtures/system_prompt/<scenario>.txt`` and
contains the exact assembled system prompt bytes (LF-normalised). When a
phase intentionally changes prompt content, regenerate by running with
``UPDATE_SNAPSHOTS=1`` and review the diff before committing.

Determinism notes:
- Fixtures use absolute paths under ``/tmp/`` to avoid machine-specific
  workspace resolution differences.
- KH content is loaded from ``knowledge_base/knowhows/`` and is checked
  into the repo, so headlines + bodies are stable per commit.
- Skill registry is loaded from ``skills/<domain>/<skill>/SKILL.md`` —
  also checked in, so prefetched skill_context is stable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from omicsclaw.runtime.context_assembler import assemble_prompt_context
from omicsclaw.runtime.context_layers import ContextAssemblyRequest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "system_prompt"
UPDATE = os.environ.get("UPDATE_SNAPSHOTS", "").strip() not in ("", "0", "false", "False")


@dataclass(frozen=True)
class Scenario:
    name: str
    surface: str = "bot"
    skill: str = ""
    query: str = ""
    domain: str = ""
    capability_context: str = ""
    memory_context: str = ""
    plan_context: str = ""
    workspace: str = ""
    pipeline_workspace: str = ""
    mcp_servers: tuple[Any, ...] = field(default_factory=tuple)


_REALISTIC_CAPABILITY = (
    "## Deterministic Capability Assessment\n"
    "- coverage: exact_skill\n"
    "- chosen_skill: {skill}\n"
    "- domain: {domain}"
)


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(name="baseline_bot"),
    Scenario(name="baseline_interactive", surface="interactive"),
    Scenario(name="baseline_pipeline", surface="pipeline"),
    Scenario(
        name="realistic_bot_scde",
        surface="bot",
        skill="sc-de",
        query="do differential expression on my single-cell h5ad file",
        domain="singlecell",
        capability_context=_REALISTIC_CAPABILITY.format(
            skill="sc-de", domain="singlecell"
        ),
        memory_context="User prefers DESeq2-style outputs.",
        plan_context="## Active Plan\n- Step 1: load data\n- Step 2: run sc-de",
        workspace="/tmp/run42",
        pipeline_workspace="/tmp/run42",
    ),
    Scenario(
        name="realistic_bot_bulkrna_de",
        surface="bot",
        skill="bulkrna-de",
        query="run differential expression on bulk RNA-seq counts",
        domain="bulkrna",
        capability_context=_REALISTIC_CAPABILITY.format(
            skill="bulkrna-de", domain="bulkrna"
        ),
        memory_context="",
        plan_context="",
        workspace="",
        pipeline_workspace="",
    ),
    Scenario(
        name="realistic_bot_pdf",
        surface="bot",
        skill="",
        query="extract the GEO accession from /tmp/paper.pdf",
        domain="",
        capability_context="",
        memory_context="",
        plan_context="",
        workspace="",
        pipeline_workspace="",
    ),
    Scenario(
        name="realistic_interactive_workspace",
        surface="interactive",
        skill="",
        query="show me the latest plan",
        domain="",
        capability_context="",
        memory_context="",
        plan_context="## Active Plan\n- Step 1: review files\n- Step 2: run sc-de",
        workspace="/tmp/run42",
        pipeline_workspace="/tmp/run42",
    ),
    Scenario(
        name="realistic_interactive_mcp",
        surface="interactive",
        skill="",
        query="check my repo on github",
        domain="",
        capability_context="",
        memory_context="",
        plan_context="",
        workspace="/tmp/run42",
        pipeline_workspace="",
        mcp_servers=({"name": "github", "transport": "stdio", "active": True},),
    ),
    Scenario(
        name="realistic_bot_capability_present",
        surface="bot",
        skill="sc-de",
        query="run sc-de on my data",
        domain="singlecell",
        capability_context=_REALISTIC_CAPABILITY.format(
            skill="sc-de", domain="singlecell"
        ),
        memory_context="",
        plan_context="",
        workspace="",
        pipeline_workspace="",
    ),
    Scenario(
        name="realistic_bot_genomics_vc",
        surface="bot",
        skill="genomics-variant-calling",
        query="call variants on my BAM file at /tmp/sample.bam",
        domain="genomics",
        capability_context=_REALISTIC_CAPABILITY.format(
            skill="genomics-variant-calling", domain="genomics"
        ),
        memory_context="",
        plan_context="",
        workspace="",
        pipeline_workspace="",
    ),
)


def _request(scenario: Scenario) -> ContextAssemblyRequest:
    return ContextAssemblyRequest(
        surface=scenario.surface,
        skill=scenario.skill,
        query=scenario.query,
        domain=scenario.domain,
        capability_context=scenario.capability_context,
        memory_context=scenario.memory_context,
        plan_context=scenario.plan_context,
        workspace=scenario.workspace,
        pipeline_workspace=scenario.pipeline_workspace,
        mcp_servers=scenario.mcp_servers,
    )


def _fixture_path(scenario: Scenario) -> Path:
    return FIXTURE_DIR / f"{scenario.name}.txt"


def _assemble(scenario: Scenario) -> str:
    asm = assemble_prompt_context(request=_request(scenario))
    # Normalise to LF and strip trailing whitespace per line for cross-platform stability.
    return asm.system_prompt.replace("\r\n", "\n")


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_system_prompt_matches_snapshot(scenario: Scenario) -> None:
    actual = _assemble(scenario)
    fixture = _fixture_path(scenario)
    if UPDATE or not fixture.exists():
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        fixture.write_text(actual, encoding="utf-8")
        if not UPDATE:
            pytest.skip(f"Snapshot created at {fixture}; rerun without UPDATE_SNAPSHOTS")
        return
    expected = fixture.read_text(encoding="utf-8")
    assert actual == expected, (
        f"\nSnapshot drift: {scenario.name}\n"
        f"  fixture: {fixture}\n"
        f"  fix: rerun with UPDATE_SNAPSHOTS=1 and review the diff before committing."
    )


def test_all_scenarios_have_unique_names() -> None:
    names = [s.name for s in SCENARIOS]
    assert len(names) == len(set(names))


def test_at_least_ten_scenarios_cover_baseline_and_realistic() -> None:
    assert len(SCENARIOS) >= 10
    surfaces = {s.surface for s in SCENARIOS}
    assert surfaces >= {"bot", "interactive", "pipeline"}
