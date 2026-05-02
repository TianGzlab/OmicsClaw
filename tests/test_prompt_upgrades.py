"""Substring-pin tests for the system-prompt discipline injections."""
from __future__ import annotations

import pytest


@pytest.fixture
def role_guardrails_text() -> str:
    from omicsclaw.runtime.context_layers import get_role_guardrails
    return get_role_guardrails()


class TestRoleGuardrailsToneInjection:
    def test_emoji_guideline_present(self, role_guardrails_text: str):
        assert "emojis unless the user explicitly requests them" in role_guardrails_text

    def test_concise_guideline_present(self, role_guardrails_text: str):
        assert "concise and direct" in role_guardrails_text
        assert "skip preamble" in role_guardrails_text

    def test_path_line_citation_present(self, role_guardrails_text: str):
        assert "`path:line`" in role_guardrails_text

    def test_no_let_me_preamble(self, role_guardrails_text: str):
        assert '"Let me X:" before a tool call' in role_guardrails_text


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
