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
