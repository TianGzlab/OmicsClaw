from __future__ import annotations

import builtins

import httpx
import pytest
from openai import OpenAIError

import bot.core as core
from omicsclaw.agents.pipeline import ResearchPipeline
from omicsclaw.core.provider_registry import PROVIDER_PRESETS


def _clear_llm_env(monkeypatch):
    for key in (
        "LLM_PROVIDER",
        "LLM_API_KEY",
        "LLM_BASE_URL",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "OMICSCLAW_API_KEY",
        "OMICSCLAW_PROVIDER",
        "OMICSCLAW_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)


def test_build_llm_timeout_uses_defaults(monkeypatch):
    monkeypatch.delenv("OMICSCLAW_LLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("OMICSCLAW_LLM_CONNECT_TIMEOUT_SECONDS", raising=False)

    timeout = core._build_llm_timeout()

    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == core.DEFAULT_LLM_CONNECT_TIMEOUT_SECONDS
    assert timeout.read == core.DEFAULT_LLM_TIMEOUT_SECONDS
    assert timeout.write == core.DEFAULT_LLM_TIMEOUT_SECONDS
    assert timeout.pool == core.DEFAULT_LLM_TIMEOUT_SECONDS


def test_build_llm_timeout_respects_env(monkeypatch):
    monkeypatch.setenv("OMICSCLAW_LLM_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("OMICSCLAW_LLM_CONNECT_TIMEOUT_SECONDS", "3")

    timeout = core._build_llm_timeout()

    assert timeout.connect == 3.0
    assert timeout.read == 45.0
    assert timeout.write == 45.0
    assert timeout.pool == 45.0


def test_init_passes_timeout_to_async_openai(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(core, "AsyncOpenAI", _FakeAsyncOpenAI)
    monkeypatch.setenv("OMICSCLAW_MEMORY_ENABLED", "false")
    monkeypatch.setenv("OMICSCLAW_LLM_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("OMICSCLAW_LLM_CONNECT_TIMEOUT_SECONDS", "5")

    core.init(
        api_key="test-key",
        base_url="https://example.com/v1",
        model="test-model",
        provider="custom",
    )

    assert captured["api_key"] == "test-key"
    assert captured["base_url"] == "https://example.com/v1"
    assert isinstance(captured["timeout"], httpx.Timeout)
    assert captured["timeout"].connect == 5.0
    assert captured["timeout"].read == 30.0


def test_init_uses_generic_custom_env_without_explicit_args(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    _clear_llm_env(monkeypatch)
    monkeypatch.setattr(core, "AsyncOpenAI", _FakeAsyncOpenAI)
    monkeypatch.setenv("OMICSCLAW_MEMORY_ENABLED", "false")
    monkeypatch.setenv("LLM_PROVIDER", "custom")
    monkeypatch.setenv("LLM_BASE_URL", "https://custom.example.com/v1")
    monkeypatch.setenv("OMICSCLAW_MODEL", "custom-env-model")
    monkeypatch.setenv("LLM_API_KEY", "generic-key")

    core.init()

    assert core.LLM_PROVIDER_NAME == "custom"
    assert core.OMICSCLAW_MODEL == "custom-env-model"
    assert captured["api_key"] == "generic-key"
    assert captured["base_url"] == "https://custom.example.com/v1"


def test_init_disables_memory_when_graph_dependencies_missing(monkeypatch):
    captured: dict[str, object] = {}
    original_import = builtins.__import__

    class _FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    def _guarded_import(name, *args, **kwargs):
        if name == "sqlalchemy" or name.startswith("sqlalchemy."):
            raise ModuleNotFoundError("No module named 'sqlalchemy'")
        return original_import(name, *args, **kwargs)

    _clear_llm_env(monkeypatch)
    monkeypatch.setattr(core, "AsyncOpenAI", _FakeAsyncOpenAI)
    monkeypatch.setattr(core, "memory_store", object())
    monkeypatch.setattr(core, "session_manager", object())
    monkeypatch.setattr(builtins, "__import__", _guarded_import)
    monkeypatch.setenv("OMICSCLAW_MEMORY_ENABLED", "true")

    core.init(
        api_key="test-key",
        base_url="https://example.com/v1",
        model="test-model",
        provider="custom",
    )

    assert captured["api_key"] == "test-key"
    assert core.memory_store is None
    assert core.session_manager is None


def test_format_llm_api_error_mentions_custom_endpoint_base_url(monkeypatch):
    monkeypatch.setattr(core, "LLM_PROVIDER_NAME", "custom")
    monkeypatch.setattr(core, "OMICSCLAW_MODEL", "gpt-5.4")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.biom.autos")

    message = core._format_llm_api_error_message(Exception("Connection error."))

    assert "https://api.biom.autos" in message
    assert "/v1" in message
    assert "Connection error" in message


def test_init_allows_missing_credentials_when_requested(monkeypatch):
    class _UnexpectedAsyncOpenAI:
        def __init__(self, **kwargs):
            raise AssertionError("missing-key startup must not construct AsyncOpenAI")

    _clear_llm_env(monkeypatch)
    monkeypatch.setattr(core, "AsyncOpenAI", _UnexpectedAsyncOpenAI)
    monkeypatch.setattr(core, "llm", object())
    monkeypatch.setenv("OMICSCLAW_MEMORY_ENABLED", "false")

    core.init(
        provider="openai",
        api_key="",
        model="gpt-5.5",
        allow_missing_credentials=True,
    )

    assert core.llm is None
    assert core.LLM_PROVIDER_NAME == "openai"
    assert core.OMICSCLAW_MODEL == "gpt-5.5"


def test_init_allows_missing_credentials_error_when_requested(monkeypatch):
    class _MissingCredentialAsyncOpenAI:
        def __init__(self, **kwargs):
            raise OpenAIError("Missing credentials. Please pass an `api_key`.")

    _clear_llm_env(monkeypatch)
    monkeypatch.setattr(core, "AsyncOpenAI", _MissingCredentialAsyncOpenAI)
    monkeypatch.setenv("OMICSCLAW_MEMORY_ENABLED", "false")

    core.init(
        provider="ollama",
        base_url="http://127.0.0.1:11434/v1",
        model="qwen2.5:7b",
        allow_missing_credentials=True,
    )

    assert core.llm is None
    assert core.LLM_PROVIDER_NAME == "ollama"


def test_init_requires_credentials_by_default(monkeypatch):
    class _MissingCredentialAsyncOpenAI:
        def __init__(self, **kwargs):
            raise OpenAIError("Missing credentials. Please pass an `api_key`.")

    _clear_llm_env(monkeypatch)
    monkeypatch.setattr(core, "AsyncOpenAI", _MissingCredentialAsyncOpenAI)
    monkeypatch.setenv("OMICSCLAW_MEMORY_ENABLED", "false")

    with pytest.raises(OpenAIError, match="Missing credentials"):
        core.init(provider="openai", api_key="", model="gpt-5.5")


def test_pipeline_openai_path_receives_shared_timeout(monkeypatch):
    langchain_openai = pytest.importorskip("langchain_openai")
    captured: dict[str, object] = {}

    class _FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    pipeline = object.__new__(ResearchPipeline)
    pipeline.provider = "deepseek"
    pipeline.model = ""

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", _FakeChatOpenAI)
    monkeypatch.setenv("OMICSCLAW_LLM_TIMEOUT_SECONDS", "25")
    monkeypatch.setenv("OMICSCLAW_LLM_CONNECT_TIMEOUT_SECONDS", "4")

    llm = ResearchPipeline._get_llm(pipeline)

    assert isinstance(llm, _FakeChatOpenAI)
    assert isinstance(captured["timeout"], httpx.Timeout)
    assert captured["timeout"].connect == 4.0
    assert captured["timeout"].read == 25.0
    assert captured["openai_api_base"] == PROVIDER_PRESETS["deepseek"][0]


def test_pipeline_anthropic_path_receives_total_timeout(monkeypatch):
    langchain_anthropic = pytest.importorskip("langchain_anthropic")
    captured: dict[str, object] = {}

    class _FakeChatAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    pipeline = object.__new__(ResearchPipeline)
    pipeline.provider = "anthropic"
    pipeline.model = ""

    monkeypatch.setattr(langchain_anthropic, "ChatAnthropic", _FakeChatAnthropic)
    monkeypatch.setenv("OMICSCLAW_LLM_TIMEOUT_SECONDS", "40")
    monkeypatch.setenv("OMICSCLAW_LLM_CONNECT_TIMEOUT_SECONDS", "7")

    llm = ResearchPipeline._get_llm(pipeline)

    assert isinstance(llm, _FakeChatAnthropic)
    assert captured["timeout"] == 40.0
