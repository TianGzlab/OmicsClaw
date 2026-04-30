"""Tests for DeepSeek passback wiring inside autoagent.llm_client."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from omicsclaw.autoagent import llm_client


def _stub_runtime(provider: str, model: str = "deepseek-v4-flash"):
    """Build a fake ResolvedProviderRuntime."""
    runtime = MagicMock()
    runtime.provider = provider
    runtime.base_url = "https://api.deepseek.com" if provider == "deepseek" else ""
    runtime.model = model
    runtime.api_key = "sk-test"
    runtime.source = "test"
    return runtime


@pytest.fixture
def fake_openai_client(monkeypatch):
    captured = {"create_kwargs": None}
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="ok"))]

    fake_client = MagicMock()

    def fake_create(**kwargs):
        captured["create_kwargs"] = kwargs
        return fake_response

    fake_client.chat.completions.create.side_effect = fake_create

    monkeypatch.setattr(
        "omicsclaw.autoagent.llm_client.OpenAI",
        lambda **_: fake_client,
        raising=False,
    )
    return captured


def test_deepseek_provider_applies_passback(monkeypatch, fake_openai_client):
    runtime = _stub_runtime("deepseek")

    monkeypatch.setattr(
        "omicsclaw.core.provider_runtime.resolve_provider_runtime",
        lambda **_: runtime,
    )
    monkeypatch.setattr(
        "omicsclaw.core.provider_runtime.provider_requires_api_key",
        lambda *_: True,
    )

    llm_client.call_llm("hi", system_prompt="be brief")

    sent_messages = fake_openai_client["create_kwargs"]["messages"]
    # In the single-shot directive case there is no historical assistant
    # message, so passback is a no-op — but it still must NOT raise.
    assert sent_messages[0]["role"] == "system"
    assert sent_messages[1]["role"] == "user"


def test_non_deepseek_provider_skips_passback(monkeypatch, fake_openai_client):
    runtime = _stub_runtime("openai", model="gpt-5.5")

    monkeypatch.setattr(
        "omicsclaw.core.provider_runtime.resolve_provider_runtime",
        lambda **_: runtime,
    )
    monkeypatch.setattr(
        "omicsclaw.core.provider_runtime.provider_requires_api_key",
        lambda *_: True,
    )

    # Spy on the patches function — should NOT be called for non-deepseek
    with patch(
        "omicsclaw.autoagent.llm_client.apply_deepseek_reasoning_passback",
        wraps=lambda x: x,
    ) as spy:
        llm_client.call_llm("hi", system_prompt="be brief")

    spy.assert_not_called()


def test_deepseek_extra_body_forwarded_from_catalog(monkeypatch, fake_openai_client):
    runtime = _stub_runtime("deepseek", model="deepseek-v4-pro")

    monkeypatch.setattr(
        "omicsclaw.core.provider_runtime.resolve_provider_runtime",
        lambda **_: runtime,
    )
    monkeypatch.setattr(
        "omicsclaw.core.provider_runtime.provider_requires_api_key",
        lambda *_: True,
    )

    llm_client.call_llm("hi", system_prompt="be brief")

    sent_kwargs = fake_openai_client["create_kwargs"]
    # DeepSeek has no catalog default features today, so extra_body should
    # not be set (or be empty). This test pins that contract: catalog is
    # consulted but does not synthesize provider-specific keys we never
    # asked for.
    extra_body = sent_kwargs.get("extra_body")
    assert extra_body is None or extra_body == {}
