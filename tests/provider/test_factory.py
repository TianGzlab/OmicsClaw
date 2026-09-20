"""The package names its own adapter, so the Main Loop never has to.

Plan 0026 §1. Without a factory the loop would import an adapter module by
path and carry its own copy of "which preset speaks Messages" — the exact
coupling this layer exists to absorb. These tests pin the three things the
loop then depends on: the mapping is complete, it is right, and asking for
a provider still costs no vendor SDK.
"""

from __future__ import annotations

import pytest

import omicsclaw.provider as provider_package
from omicsclaw.provider import (
    PRESETS,
    AnthropicProvider,
    LLMProvider,
    OpenAIProvider,
    ProviderDialect,
    ProviderError,
    dialect_for,
    provider_for,
    provider_from_env,
    resolve_config,
)
from omicsclaw.provider import anthropic_provider as ap
from omicsclaw.provider import openai_provider as op
from omicsclaw.provider.factory import ADAPTERS

_OPENAI_SPEAKING_PRESETS = sorted(set(PRESETS) - {"anthropic"})


def refuse(*_args, **_kwargs):
    raise AssertionError("building a provider reached for a vendor SDK")


# --- the dialect mapping ---------------------------------------------------


def test_exactly_one_preset_speaks_the_anthropic_messages_dialect():
    """Twelve of thirteen presets are Chat Completions; miscounting sends a
    request in a grammar the endpoint does not parse."""
    messages = {
        name
        for name, preset in PRESETS.items()
        if preset.dialect is ProviderDialect.ANTHROPIC_MESSAGES
    }

    assert messages == {"anthropic"}
    assert len(PRESETS) == 13


@pytest.mark.parametrize("name", _OPENAI_SPEAKING_PRESETS)
def test_every_other_preset_speaks_chat_completions(name: str):
    assert dialect_for(name) is ProviderDialect.OPENAI_CHAT


def test_an_unknown_provider_name_is_assumed_to_speak_chat_completions():
    """A self-hosted gateway has no preset, and refusing to answer would
    make it unreachable through the factory for want of a table entry."""
    assert dialect_for("some-inhouse-gateway") is ProviderDialect.OPENAI_CHAT
    assert dialect_for("") is ProviderDialect.OPENAI_CHAT


def test_a_gateway_reselling_claude_still_speaks_chat_completions():
    """OpenRouter's default model is a Claude. The dialect follows the
    endpoint, never the model name — deriving it from the model would send
    a Messages payload to a Chat Completions URL."""
    assert "claude" in PRESETS["openrouter"].default_model
    assert dialect_for("openrouter") is ProviderDialect.OPENAI_CHAT


def test_every_dialect_has_an_adapter_that_speaks_it():
    """A dialect with no adapter is a ProviderError at call time for
    whichever preset was pointed at it."""
    assert set(ADAPTERS) == set(ProviderDialect)


# --- provider_for ----------------------------------------------------------


def test_the_anthropic_preset_builds_the_messages_adapter():
    built = provider_for(resolve_config("anthropic", env={}))

    assert isinstance(built, AnthropicProvider)
    assert isinstance(built, LLMProvider)
    assert built.name == "anthropic"


@pytest.mark.parametrize("name", _OPENAI_SPEAKING_PRESETS)
def test_every_other_preset_builds_the_chat_completions_adapter(name: str):
    built = provider_for(resolve_config(name, env={}))

    assert isinstance(built, OpenAIProvider)
    assert isinstance(built, LLMProvider)


def test_the_configuration_reaches_the_adapter_it_was_built_for():
    config = resolve_config("anthropic", "claude-haiku-4-5", env={}, max_tokens=64)

    assert provider_for(config).config is config


def test_an_explicit_dialect_overrides_the_one_the_preset_implies():
    """The case the preset table cannot express: an operator pointing an
    unlisted name at an Anthropic-compatible endpoint."""
    config = resolve_config(
        "custom", "claude-sonnet-4-6", base_url="http://localhost:8080", env={}
    )

    assert isinstance(provider_for(config), OpenAIProvider)
    assert isinstance(
        provider_for(config, dialect=ProviderDialect.ANTHROPIC_MESSAGES),
        AnthropicProvider,
    )


def test_a_dialect_nothing_implements_is_refused_in_this_layers_vocabulary():
    """Never a KeyError: the caller should not have to know this is a dict."""
    with pytest.raises(ProviderError, match="no adapter speaks dialect"):
        provider_for(
            resolve_config("openai", env={}),
            dialect="klingon",  # type: ignore[arg-type]
        )


def test_building_a_provider_opens_no_client_and_needs_no_vendor_sdk(monkeypatch):
    """The factory must stay callable where the optional extras are absent.

    Neither SDK is installed here, so a factory that constructed its client
    eagerly would not merely be slow — it would raise, and the Main Loop
    could not so much as ask what it is configured to talk to.
    """
    monkeypatch.setattr(ap, "_build_async_client", refuse)
    monkeypatch.setattr(op.OpenAIProvider, "_create_client", refuse)

    assert provider_for(resolve_config("anthropic", env={})).name == "anthropic"
    assert provider_for(resolve_config("deepseek", env={})).name == "deepseek"


# --- provider_from_env -----------------------------------------------------


def test_the_environments_own_api_key_picks_the_adapter():
    """The one call the Main Loop makes: no preset name, no dialect, no
    adapter class — just whatever the machine is configured for."""
    built = provider_from_env(env={"ANTHROPIC_API_KEY": "sk-ant-test"})

    assert isinstance(built, AnthropicProvider)
    assert built.config.api_key == "sk-ant-test"
    assert built.config.model == PRESETS["anthropic"].default_model


def test_a_different_key_in_the_environment_picks_a_different_adapter():
    built = provider_from_env(env={"DEEPSEEK_API_KEY": "sk-deep-test"})

    assert isinstance(built, OpenAIProvider)
    assert built.name == "deepseek"


def test_an_unconfigured_environment_still_yields_a_usable_provider():
    """Nothing detected is not an error here — the backend's own auth
    failure says more than a guess made at assembly time could."""
    built = provider_from_env(env={})

    assert isinstance(built, OpenAIProvider)
    assert isinstance(built, LLMProvider)


def test_an_explicit_provider_argument_outranks_the_environment():
    built = provider_from_env("anthropic", env={"DEEPSEEK_API_KEY": "sk-deep-test"})

    assert isinstance(built, AnthropicProvider)


def test_configuration_overrides_pass_straight_through_to_the_config():
    """The signature mirrors resolve_config so the two are interchangeable
    at a call site; an override silently dropped here would surface much
    later as an unexplained cost or truncation."""
    built = provider_from_env(
        "anthropic",
        "claude-haiku-4-5",
        env={},
        max_tokens=64,
        temperature=0.0,
    )

    assert built.config.model == "claude-haiku-4-5"
    assert built.config.max_tokens == 64
    assert built.config.temperature == 0.0


# --- the public surface ----------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "AnthropicProvider",
        "LLMProvider",
        "OpenAIProvider",
        "ProviderConfig",
        "ProviderDialect",
        "ProviderError",
        "dialect_for",
        "provider_for",
        "provider_from_env",
        "resolve_config",
    ],
)
def test_the_main_loop_can_reach_everything_it_needs_from_the_package(name: str):
    """Exported by name, so no caller has to import an adapter module by
    path — which would hard-code the preset-to-dialect mapping upstream."""
    assert name in provider_package.__all__
    assert getattr(provider_package, name) is not None
