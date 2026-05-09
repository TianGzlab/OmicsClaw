"""Substring-pin tests for the system-prompt discipline injections.

Phase 3 retired the ``role_guardrails`` injector. The tone rules that
used to live there now split between two homes:
- The persistent always-on rules (concise, ``path:line``, ``Let me X``
  ban) live in SOUL.md.
- The surface-conditional emoji / markdown / plain-text rules live in
  the ``surface_voice_rules`` layer.

This file pins the contract at both new locations so a future regression
that drops one of these rules from the prompt is caught immediately.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOUL_PATH = ROOT / "SOUL.md"


@pytest.fixture
def soul_md_text() -> str:
    return SOUL_PATH.read_text(encoding="utf-8")


@pytest.fixture
def bot_voice_rules_text() -> str:
    from omicsclaw.runtime.context_assembler import assemble_prompt_context
    from omicsclaw.runtime.context_layers import ContextAssemblyRequest

    asm = assemble_prompt_context(request=ContextAssemblyRequest(surface="bot"))
    for layer in asm.layers:
        if layer.name == "surface_voice_rules":
            return layer.content
    raise AssertionError("surface_voice_rules layer missing for bot surface")


@pytest.fixture
def cli_voice_rules_text() -> str:
    from omicsclaw.runtime.context_assembler import assemble_prompt_context
    from omicsclaw.runtime.context_layers import ContextAssemblyRequest

    asm = assemble_prompt_context(request=ContextAssemblyRequest(surface="interactive"))
    for layer in asm.layers:
        if layer.name == "surface_voice_rules":
            return layer.content
    raise AssertionError("surface_voice_rules layer missing for interactive surface")


class TestPersonaToneRulesInSoulMd:
    """Always-on tone rules that survive Phase 3 in SOUL.md."""

    def test_path_line_citation_present(self, soul_md_text: str):
        assert "`path:line`" in soul_md_text

    def test_no_let_me_preamble(self, soul_md_text: str):
        assert '"Let me X:"' in soul_md_text

    def test_concise_and_direct_guidance_present(self, soul_md_text: str):
        """Pin both halves of the original 'concise and direct' rule plus
        the 'skip preamble' sibling phrase."""
        lower = soul_md_text.lower()
        assert "concise" in lower
        assert "direct" in lower
        assert "preamble" in lower


class TestSurfaceConditionalVoiceRules:
    """Per-surface emoji / markdown rules moved here from role_guardrails."""

    def test_bot_allows_emoji_sparingly(self, bot_voice_rules_text: str):
        lower = bot_voice_rules_text.lower()
        assert "emoji" in lower
        assert "no emoji" not in lower

    def test_cli_forbids_emoji(self, cli_voice_rules_text: str):
        lower = cli_voice_rules_text.lower()
        assert "no emoji" in lower or "plain text" in lower


@pytest.fixture
def execution_discipline_text() -> str:
    from omicsclaw.runtime.context_layers import get_execution_discipline
    return get_execution_discipline()


class TestExecutionDisciplineActionsInjection:
    def test_reversibility_guideline_present(self, execution_discipline_text: str):
        assert "reversibility and blast radius" in execution_discipline_text

    def test_no_destructive_shortcut_guideline_present(self, execution_discipline_text: str):
        assert "destructive shortcut" in execution_discipline_text
        assert "force-push" in execution_discipline_text or "force push" in execution_discipline_text

    def test_no_blind_retry_guideline_present(self, execution_discipline_text: str):
        assert "fails twice the same way" in execution_discipline_text


@pytest.fixture
def skill_contract_text() -> str:
    from omicsclaw.runtime.context_layers import get_skill_contract
    return get_skill_contract()


class TestSkillContractDoingTasksInjection:
    def test_read_before_change_present(self, skill_contract_text: str):
        assert "Read code before proposing changes" in skill_contract_text

    def test_prefer_existing_file_present(self, skill_contract_text: str):
        assert "editing an existing file" in skill_contract_text

    def test_stay_within_scope_present(self, skill_contract_text: str):
        assert "Stay within scope" in skill_contract_text
        assert "bug fix doesn't need surrounding cleanup" in skill_contract_text

    def test_no_unsolicited_comments_present(self, skill_contract_text: str):
        assert "comments or docstrings to code you didn't change" in skill_contract_text

    def test_no_speculative_validation_present(self, skill_contract_text: str):
        assert (
            "error handling, fallbacks, or validation for scenarios that can't happen"
            in skill_contract_text
        )

    def test_no_compat_shims_present(self, skill_contract_text: str):
        assert "backwards-compat shims" in skill_contract_text

    def test_owasp_present(self, skill_contract_text: str):
        assert "OWASP-class vulnerabilities" in skill_contract_text


@pytest.fixture
def output_format_text_default_bot() -> str:
    from omicsclaw.runtime.output_styles import render_output_style_layer
    return render_output_style_layer(style_name="default", surface="bot")


class TestOutputFormatEfficiencyInjection:
    def test_lead_with_answer_present(self, output_format_text_default_bot: str):
        assert "Lead with the answer" in output_format_text_default_bot

    def test_one_sentence_rule_present(self, output_format_text_default_bot: str):
        assert "one sentence, don't use three" in output_format_text_default_bot

    def test_milestones_rule_present(self, output_format_text_default_bot: str):
        assert "natural milestones" in output_format_text_default_bot

    def test_prose_only_caveat_present(self, output_format_text_default_bot: str):
        assert "applies to your prose only" in output_format_text_default_bot

    def test_efficiency_section_present_for_other_profiles(self):
        from omicsclaw.runtime.output_styles import render_output_style_layer
        for style in ("scientific-brief", "teaching", "pipeline-operator"):
            text = render_output_style_layer(style_name=style, surface="bot")
            assert "Lead with the answer" in text, f"style={style} missing efficiency section"


class TestHarnessLoopSystemPrompt:
    def test_smallest_patch_directive_present(self):
        import inspect
        from omicsclaw.autoagent.harness_loop import HarnessLoop
        source = inspect.getsource(HarnessLoop._call_llm)
        assert "smallest patch" in source

    def test_owasp_present(self):
        import inspect
        from omicsclaw.autoagent.harness_loop import HarnessLoop
        source = inspect.getsource(HarnessLoop._call_llm)
        assert "OWASP-class vulnerabilities" in source

    def test_json_only_contract_preserved(self):
        import inspect
        from omicsclaw.autoagent.harness_loop import HarnessLoop
        source = inspect.getsource(HarnessLoop._call_llm)
        # The strict JSON-output contract is what the parser depends on.
        assert "Respond ONLY with valid JSON" in source
        assert "No prose" in source
