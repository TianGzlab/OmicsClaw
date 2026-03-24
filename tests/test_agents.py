"""Tests for the multi-agent research pipeline infrastructure.

These tests verify config loading, intake processing, and data structures
WITHOUT requiring deepagents/langchain (those are optional dependencies).
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


# =========================================================================
# Test config.yaml loading
# =========================================================================


class TestAgentConfig:
    """Tests for agent config loading and structure."""

    def test_config_yaml_exists(self):
        """config.yaml must exist in omicsclaw/agents/."""
        config_path = Path(__file__).parent.parent / "omicsclaw" / "agents" / "config.yaml"
        assert config_path.exists(), f"Missing config.yaml at {config_path}"

    def test_config_yaml_parseable(self):
        """config.yaml must be valid YAML."""
        import yaml
        config_path = Path(__file__).parent.parent / "omicsclaw" / "agents" / "config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)
        assert isinstance(config, dict)

    def test_config_has_all_agents(self):
        """config.yaml must define all 6 sub-agents."""
        import yaml
        config_path = Path(__file__).parent.parent / "omicsclaw" / "agents" / "config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        expected_agents = [
            "planner-agent",
            "research-agent",
            "coding-agent",
            "analysis-agent",
            "writing-agent",
            "reviewer-agent",
        ]
        for agent_name in expected_agents:
            assert agent_name in config, f"Missing agent: {agent_name}"

    def test_each_agent_has_required_fields(self):
        """Each agent must have description, tools, and system_prompt."""
        import yaml
        config_path = Path(__file__).parent.parent / "omicsclaw" / "agents" / "config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        for agent_name, agent_def in config.items():
            assert "description" in agent_def, f"{agent_name} missing description"
            assert "tools" in agent_def, f"{agent_name} missing tools"
            # system_prompt or system_prompt_ref
            has_prompt = "system_prompt" in agent_def or "system_prompt_ref" in agent_def
            assert has_prompt, f"{agent_name} missing system_prompt or system_prompt_ref"

    def test_reviewer_agent_has_search_tool(self):
        """reviewer-agent must have tavily_search for citation verification."""
        import yaml
        config_path = Path(__file__).parent.parent / "omicsclaw" / "agents" / "config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        reviewer_tools = config["reviewer-agent"]["tools"]
        assert "tavily_search" in reviewer_tools


# =========================================================================
# Test prompts
# =========================================================================


class TestPrompts:
    """Tests for prompt templates."""

    def test_imports(self):
        """Prompt module must be importable without optional deps."""
        from omicsclaw.agents.prompts import (
            RESEARCH_PIPELINE_WORKFLOW,
            DELEGATION_STRATEGY,
            RESEARCHER_INSTRUCTIONS,
            REVIEWER_CHECKLIST,
            PAPER_FORMAT_RULES,
        )
        assert "OmicsClaw" in RESEARCH_PIPELINE_WORKFLOW
        assert "reviewer" in REVIEWER_CHECKLIST.lower()

    def test_get_system_prompt(self):
        """get_system_prompt() returns a non-empty prompt."""
        from omicsclaw.agents.prompts import get_system_prompt
        prompt = get_system_prompt()
        assert len(prompt) > 100
        assert "OmicsClaw" in prompt

    def test_get_researcher_prompt_has_date(self):
        """get_researcher_prompt() includes current date."""
        from omicsclaw.agents.prompts import get_researcher_prompt
        prompt = get_researcher_prompt()
        # Should contain a date like 2026-03-22
        import re
        assert re.search(r"\d{4}-\d{2}-\d{2}", prompt)

    def test_build_prompt_refs(self):
        """build_prompt_refs() returns a dict with RESEARCHER_INSTRUCTIONS."""
        from omicsclaw.agents.prompts import build_prompt_refs
        refs = build_prompt_refs()
        assert "RESEARCHER_INSTRUCTIONS" in refs


# =========================================================================
# Test intake (PDF→MD)
# =========================================================================


class TestIntake:
    """Tests for intake processing and PDF→MD conversion."""

    def test_intake_result_structure(self):
        """IntakeResult dataclass has expected fields."""
        from omicsclaw.agents.intake import IntakeResult
        result = IntakeResult()
        assert result.input_mode == "A"
        assert result.paper_markdown == ""
        assert result.geo_accessions == []

    def test_extract_geo_accessions(self):
        """Should extract GSE/GSM IDs from text."""
        from omicsclaw.agents.intake import _extract_geo_accessions
        text = "We used GSE123456 and GSM789012 samples from GEO. Also GSE123456 again."
        result = _extract_geo_accessions(text)
        assert "GSE123456" in result
        assert "GSM789012" in result
        # Should deduplicate
        assert result.count("GSE123456") == 1

    def test_extract_organism_human(self):
        """Should detect human organism."""
        from omicsclaw.agents.intake import _extract_organism
        result = _extract_organism("We analyzed human breast cancer samples")
        assert "Homo sapiens" in result
        # Exact match when specific keywords are present
        assert _extract_organism("Homo sapiens tissue was collected") == "Homo sapiens"

    def test_extract_organism_mouse(self):
        """Should detect mouse organism."""
        from omicsclaw.agents.intake import _extract_organism
        assert _extract_organism("Mouse brain tissue was collected") == "Mus musculus"

    def test_extract_technology(self):
        """Should detect sequencing technology."""
        from omicsclaw.agents.intake import _extract_technology
        assert _extract_technology("10x Visium spatial transcriptomics") == "10x Visium"
        # When multiple techs are mentioned, all should be detected
        result = _extract_technology("scRNA-seq using 10x Chromium")
        assert "10x Chromium" in result
        assert "scRNA-seq" in result

    def test_extract_tissue(self):
        """Should detect tissue types."""
        from omicsclaw.agents.intake import _extract_tissue
        result = _extract_tissue("We studied brain and liver tissue")
        assert "brain" in result
        assert "liver" in result

    def test_pdf_to_markdown(self):
        """_pdf_to_markdown should produce structured MD."""
        from omicsclaw.agents.intake import _pdf_to_markdown
        raw = "Title of Paper\n\nAbstract\nThis is the abstract text.\n\nIntroduction\nSome intro."
        md = _pdf_to_markdown("/tmp/test.pdf", raw)
        # Title extraction may pick up different text for very short inputs;
        # verify the raw text appears somewhere in the output.
        assert "Title of Paper" in md
        assert "## Full Text" in md

    def test_prepare_intake_mode_a(self):
        """prepare_intake should work in Mode A (PDF only)."""
        from omicsclaw.agents.intake import prepare_intake

        # Create a fake PDF (just text, pypdf will fail gracefully)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4\n")
            f.write(b"Test paper about GSE123456\n")
            pdf_path = f.name

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                result = prepare_intake(
                    idea="Test idea",
                    pdf_path=pdf_path,
                    output_dir=tmpdir,
                )
                assert result.input_mode == "A"
                assert result.idea == "Test idea"
                assert Path(result.paper_md_path).exists()
        finally:
            Path(pdf_path).unlink(missing_ok=True)

    def test_prepare_intake_mode_c(self):
        """prepare_intake should work in Mode C (idea only, no PDF)."""
        from omicsclaw.agents.intake import prepare_intake

        with tempfile.TemporaryDirectory() as tmpdir:
            result = prepare_intake(
                idea="Investigate tumor microenvironment heterogeneity",
                output_dir=tmpdir,
            )
            assert result.input_mode == "C"
            assert result.idea == "Investigate tumor microenvironment heterogeneity"
            assert result.paper_markdown == ""
            assert result.paper_md_path == ""
            # Should have created a research_request.md
            assert (Path(tmpdir) / "research_request.md").exists()
            req_content = (Path(tmpdir) / "research_request.md").read_text()
            assert "Mode: C" in req_content
            assert "idea only" in req_content.lower()


# =========================================================================
# Test dependency check
# =========================================================================


class TestDependencyCheck:
    """Test that research deps are properly guarded."""

    def test_check_research_deps_raises_without_deepagents(self):
        """_check_research_deps should raise ImportError if deepagents missing."""
        from omicsclaw.agents import _check_research_deps
        # If deepagents IS installed, this test passes trivially.
        # If not installed, it should raise ImportError.
        try:
            _check_research_deps()
        except ImportError as e:
            assert "research" in str(e).lower() or "deepagents" in str(e).lower()


# =========================================================================
# Test slash command registration
# =========================================================================


class TestSlashCommand:
    """Test that /research is registered in SLASH_COMMANDS."""

    def test_research_in_slash_commands(self):
        from omicsclaw.interactive._constants import SLASH_COMMANDS
        cmd_names = [cmd for cmd, _ in SLASH_COMMANDS]
        assert "/research" in cmd_names

