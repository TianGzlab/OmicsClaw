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


class TestExecutionRulesNowGated:
    """Phase 4 retired the always-on ``execution_discipline`` and
    ``skill_contract`` text blocks. Their content split into two homes:
    predicate-gated layers (covered in ``test_predicate_gated_injectors.py``)
    and pre-call tool preambles (covered in ``test_tool_preambles.py``).

    The most-load-bearing rules are pinned here as a backstop so a future
    regression that drops one of these pre-call mechanisms surfaces in
    this file's history."""

    def test_action_risk_rule_lives_in_soul_md(self, soul_md_text: str):
        # SOUL.md rule 5 ("destructive or shared-state actions") is the
        # always-on home for what used to be Action Risk Discipline.
        lower = soul_md_text.lower()
        assert "destructive" in lower
        assert "confirm" in lower

    def test_engineering_preamble_carries_owasp_and_no_shell_rules(self):
        from omicsclaw.runtime.tool_execution_hooks import (
            DEFAULT_PRE_CALL_RULE_INJECTORS,
            build_pre_call_rule_text,
        )

        text = build_pre_call_rule_text(
            tool_name="file_edit",
            tool_args={"path": "src/foo.py"},
            injectors=DEFAULT_PRE_CALL_RULE_INJECTORS,
        ).lower()
        assert "owasp" in text or "injection" in text
        assert ".sh" in text or "shell" in text

    def test_skill_execution_preamble_carries_method_and_output_rules(self):
        from omicsclaw.runtime.tool_execution_hooks import (
            DEFAULT_PRE_CALL_RULE_INJECTORS,
            build_pre_call_rule_text,
        )

        text = build_pre_call_rule_text(
            tool_name="omicsclaw",
            tool_args={"skill": "sc-de"},
            injectors=DEFAULT_PRE_CALL_RULE_INJECTORS,
        ).lower()
        assert "lowercase" in text
        assert "output/" in text


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
