"""Shared LLM provider registry and resolution helpers.

This module is intentionally dependency-light so it can be reused by bot,
interactive, routing, onboarding, and diagnostics surfaces without importing
heavier runtime modules.
"""

from __future__ import annotations

import json
import os
from typing import Any, Literal, Mapping, TypedDict

ProviderPreset = tuple[str, str, str]
ProviderTier = Literal["primary", "aggregator", "local"]


class ModelMetadata(TypedDict):
    id: str
    context_window: int | None


class ProviderDisplayMetadata(TypedDict):
    display_name: str
    description: str
    description_zh: str
    tier: ProviderTier
    models: tuple[str, ...]


class ProviderRegistryEntry(TypedDict):
    name: str
    base_url: str
    default_model: str
    env_key: str
    display_name: str
    description: str
    description_zh: str
    tier: ProviderTier
    models: list[str]
    model_metadata: list[ModelMetadata]


PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    # --- Tier 1: Primary providers ---
    "deepseek": ("https://api.deepseek.com", "deepseek-v4-flash", "DEEPSEEK_API_KEY"),
    "openai": ("", "gpt-5.5", "OPENAI_API_KEY"),
    "anthropic": (
        "https://api.anthropic.com/v1/",
        "claude-sonnet-4-6",
        "ANTHROPIC_API_KEY",
    ),
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini-3-flash-preview",
        "GOOGLE_API_KEY",
    ),
    "nvidia": (
        "https://integrate.api.nvidia.com/v1",
        "nvidia/nemotron-3-super-120b-a12b",
        "NVIDIA_API_KEY",
    ),
    # --- Tier 2: Third-party aggregators ---
    "siliconflow": (
        "https://api.siliconflow.cn/v1",
        "Pro/zai-org/GLM-5",
        "SILICONFLOW_API_KEY",
    ),
    "openrouter": (
        "https://openrouter.ai/api/v1",
        "anthropic/claude-sonnet-4.6",
        "OPENROUTER_API_KEY",
    ),
    "volcengine": (
        "https://ark.cn-beijing.volces.com/api/v3",
        "doubao-seed-2-0-pro-260215",
        "VOLCENGINE_API_KEY",
    ),
    "dashscope": (
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "qwen3.6-plus",
        "DASHSCOPE_API_KEY",
    ),
    "moonshot": (
        "https://api.moonshot.cn/v1",
        "kimi-k2.6",
        "MOONSHOT_API_KEY",
    ),
    "zhipu": (
        "https://open.bigmodel.cn/api/paas/v4",
        "glm-5.1",
        "ZHIPU_API_KEY",
    ),
    # --- Tier 3: Local & custom ---
    "ollama": ("http://localhost:11434/v1", "qwen2.5:7b", ""),
    "custom": ("", "", ""),
}

PROVIDER_DISPLAY_METADATA: dict[str, ProviderDisplayMetadata] = {
    "deepseek": {
        "display_name": "DeepSeek",
        "description": "DeepSeek V4 series — cost-effective reasoning",
        "description_zh": "DeepSeek V4 系列 — 高性价比推理",
        "tier": "primary",
        "models": ("deepseek-v4-flash", "deepseek-v4-pro"),
    },
    "openai": {
        "display_name": "OpenAI",
        "description": "GPT-5.5 and Codex series models",
        "description_zh": "GPT-5.5 及 Codex 系列模型",
        "tier": "primary",
        "models": ("gpt-5.5-pro", "gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.3-codex", "gpt-5", "gpt-5-mini"),
    },
    "anthropic": {
        "display_name": "Anthropic",
        "description": "Claude Opus 4.7, Sonnet 4.6 and Haiku 4.5",
        "description_zh": "Claude Opus 4.7、Sonnet 4.6 和 Haiku 4.5",
        "tier": "primary",
        "models": ("claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6", "claude-sonnet-4-5", "claude-haiku-4-5"),
    },
    "gemini": {
        "display_name": "Google Gemini",
        "description": "Gemini 3.1 / 3 / 2.5 series",
        "description_zh": "Gemini 3.1 / 3 / 2.5 系列",
        "tier": "primary",
        "models": ("gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-2.5-pro", "gemini-2.5-flash"),
    },
    "nvidia": {
        "display_name": "NVIDIA NIM",
        "description": "Hosted inference on NVIDIA infrastructure",
        "description_zh": "NVIDIA 基础设施托管推理",
        "tier": "primary",
        "models": (
            "nvidia/nemotron-3-super-120b-a12b",
            "deepseek-ai/deepseek-v3.2",
            "moonshotai/kimi-k2.5",
            "qwen/qwen3.5-397b-a17b",
        ),
    },
    "siliconflow": {
        "display_name": "SiliconFlow",
        "description": "China-optimized multi-model hosting",
        "description_zh": "国内优化的多模型托管平台",
        "tier": "aggregator",
        "models": ("Pro/zai-org/GLM-5", "Pro/MiniMaxAI/MiniMax-M2.5", "Pro/moonshotai/Kimi-K2.5", "Pro/zai-org/GLM-4.7"),
    },
    "openrouter": {
        "display_name": "OpenRouter",
        "description": "Multi-model gateway",
        "description_zh": "多模型网关",
        "tier": "aggregator",
        "models": (
            "anthropic/claude-sonnet-4.6",
            "anthropic/claude-opus-4.7",
            "openai/gpt-5.5",
            "openai/gpt-5.4",
            "google/gemini-3.1-pro-preview",
            "moonshotai/kimi-k2.6",
            "minimax/minimax-m2.7",
            "deepseek/deepseek-v4-pro",
        ),
    },
    "volcengine": {
        "display_name": "Volcengine",
        "description": "ByteDance Doubao Seed models",
        "description_zh": "字节跳动豆包 Seed 模型",
        "tier": "aggregator",
        "models": ("doubao-seed-2-0-pro-260215", "doubao-seed-2-0-lite-260215", "doubao-1.5-pro-256k", "doubao-1.5-thinking-pro"),
    },
    "dashscope": {
        "display_name": "DashScope",
        "description": "Alibaba Qwen3.6 / Qwen3 models (Plus, Max, Coder, QwQ)",
        "description_zh": "阿里巴巴通义千问 Qwen3.6 / Qwen3 系列（Plus、Max、Coder、QwQ）",
        "tier": "aggregator",
        "models": (
            "qwen3.6-plus",
            "qwen3-max",
            "qwen3-coder-plus",
            "qwen3-235b-a22b",
            "qwq-plus",
            "qwen3.5-flash",
            "qwen-turbo-latest",
        ),
    },
    "moonshot": {
        "display_name": "Moonshot",
        "description": "Kimi K2.6 / K2.5 series models",
        "description_zh": "月之暗面 Kimi K2.6 / K2.5 系列模型",
        "tier": "aggregator",
        "models": ("kimi-k2.6", "kimi-k2.5", "kimi-k2-thinking"),
    },
    "zhipu": {
        "display_name": "Zhipu AI",
        "description": "GLM-5.1 / GLM-5 series models",
        "description_zh": "智谱 GLM-5.1 / GLM-5 系列模型",
        "tier": "aggregator",
        "models": ("glm-5.1", "glm-5", "glm-5-turbo", "glm-4.7"),
    },
    "ollama": {
        "display_name": "Ollama",
        "description": "Local models — no API key needed",
        "description_zh": "本地模型，无需 API Key",
        "tier": "local",
        "models": (
            "qwen2.5:7b",
            "qwen2.5:14b",
            "qwen2.5:32b",
            "llama3.3:70b",
            "deepseek-r1:7b",
            "deepseek-r1:14b",
            "deepseek-r1:32b",
            "gemma3:12b",
        ),
    },
    "custom": {
        "display_name": "Custom Endpoint",
        "description": "Any OpenAI-compatible API",
        "description_zh": "任意 OpenAI 兼容接口",
        "tier": "local",
        "models": tuple(),
    },
}

PROVIDER_DETECT_ORDER: tuple[str, ...] = (
    "deepseek",
    "openai",
    "anthropic",
    "gemini",
    "nvidia",
    "siliconflow",
    "openrouter",
    "volcengine",
    "dashscope",
    "moonshot",
    "zhipu",
)

PROVIDER_CHOICES: tuple[str, ...] = tuple(PROVIDER_PRESETS.keys())

# Providers that intentionally allow wide/open model identifier spaces.
# For these, OmicsClaw must not auto-rewrite model names just because they
# resemble another provider's default model.
MODEL_NORMALIZATION_EXEMPT_PROVIDERS: frozenset[str] = frozenset({
    "custom",
    "ollama",
    "openrouter",
    "siliconflow",
    "nvidia",
})

DEPRECATED_PROVIDER_DEFAULT_MODELS: dict[str, frozenset[str]] = {
    "deepseek": frozenset({"deepseek-chat", "deepseek-reasoner"}),
}


# --------------------------------------------------------------------------- #
# OAuth support was previously declared here. It now lives entirely in
# ``omicsclaw.core.ccproxy_manager`` (the only module that actually runs
# ccproxy) — see the ``OAUTH_PROVIDERS`` table there. This module stays
# dependency-light and OAuth-agnostic per its original design.


def get_provider_display_metadata(provider_name: str) -> ProviderDisplayMetadata:
    metadata = PROVIDER_DISPLAY_METADATA.get(provider_name)
    if metadata is not None:
        return metadata

    label = str(provider_name or "").strip()
    return {
        "display_name": label or provider_name,
        "description": "",
        "description_zh": "",
        "tier": "local",
        "models": tuple(),
    }


def build_provider_registry_entries(
    provider_presets: Mapping[str, ProviderPreset] = PROVIDER_PRESETS,
) -> list[ProviderRegistryEntry]:
    from omicsclaw.core.llm_models import get_context_window

    entries: list[ProviderRegistryEntry] = []
    for name, (base_url, default_model, env_key) in provider_presets.items():
        metadata = get_provider_display_metadata(name)
        models = list(dict.fromkeys([
            *metadata["models"],
            *((default_model,) if default_model else tuple()),
        ]))
        model_metadata: list[ModelMetadata] = [
            {"id": model, "context_window": get_context_window(model)}
            for model in models
        ]
        entries.append({
            "name": name,
            "base_url": base_url,
            "default_model": default_model,
            "env_key": env_key,
            "display_name": metadata["display_name"],
            "description": metadata["description"],
            "description_zh": metadata["description_zh"],
            "tier": metadata["tier"],
            "models": models,
            "model_metadata": model_metadata,
        })
    return entries


def detect_provider_from_env(
    *,
    env: Mapping[str, str] | None = None,
    provider_presets: Mapping[str, ProviderPreset] = PROVIDER_PRESETS,
    detect_order: tuple[str, ...] = PROVIDER_DETECT_ORDER,
) -> str:
    """Detect the effective provider from environment variables."""
    source = os.environ if env is None else env
    requested = str(source.get("LLM_PROVIDER", "") or "").strip().lower()
    if requested:
        return requested

    for name in detect_order:
        preset = provider_presets.get(name)
        if preset is None:
            continue
        api_env = str(preset[2] or "")
        if api_env and source.get(api_env):
            return name
    return ""


def normalize_model_for_provider(
    provider: str = "",
    model: str = "",
    *,
    base_url: str = "",
    provider_presets: Mapping[str, ProviderPreset] = PROVIDER_PRESETS,
    exempt_providers: frozenset[str] = MODEL_NORMALIZATION_EXEMPT_PROVIDERS,
) -> tuple[str, str]:
    """Normalize obviously stale cross-provider default-model leftovers.

    This is intentionally conservative:

    - only runs when a concrete provider is selected
    - never rewrites models for custom/local/gateway-style providers
    - never rewrites when the user supplied a custom base URL
    - only rewrites when the model exactly matches another provider's default

    Returns ``(normalized_model, matched_foreign_provider)`` where the second
    value is empty when no normalization was needed.
    """
    provider_key = str(provider or "").strip().lower()
    candidate_model = str(model or "").strip()
    explicit_base_url = str(base_url or "").strip()

    if not provider_key or not candidate_model:
        return candidate_model, ""
    if explicit_base_url or provider_key in exempt_providers:
        return candidate_model, ""

    current = provider_presets.get(provider_key)
    if current is None:
        return candidate_model, ""

    current_default_model = str(current[1] or "").strip()
    if not current_default_model or candidate_model == current_default_model:
        return candidate_model, ""

    if candidate_model in DEPRECATED_PROVIDER_DEFAULT_MODELS.get(provider_key, frozenset()):
        return current_default_model, provider_key

    for other_name, (_, other_default_model, _) in provider_presets.items():
        if other_name == provider_key:
            continue
        if candidate_model == str(other_default_model or "").strip():
            return current_default_model, other_name

    return candidate_model, ""


def resolve_provider(
    provider: str = "",
    base_url: str = "",
    model: str = "",
    api_key: str = "",
    *,
    env: Mapping[str, str] | None = None,
    provider_presets: Mapping[str, ProviderPreset] = PROVIDER_PRESETS,
    detect_order: tuple[str, ...] = PROVIDER_DETECT_ORDER,
) -> tuple[str | None, str, str]:
    """Resolve effective provider endpoint, model, and API key.

    Priority:
    1. Explicit args
    2. Provider-specific env defaults
    3. Auto-detect from provider-specific API key env vars
    4. Generic LLM_API_KEY / OPENAI_API_KEY fallback
    """
    source = os.environ if env is None else env
    provider_key = str(provider or "").strip().lower()
    requested_provider_key = provider_key
    env_provider_key = str(
        source.get("LLM_PROVIDER", "") or source.get("OMICSCLAW_PROVIDER", "") or ""
    ).strip().lower()
    resolved_key = str(api_key or "")

    if not provider_key and not resolved_key:
        provider_key = detect_provider_from_env(
            env=source,
            provider_presets=provider_presets,
            detect_order=detect_order,
        )
        if provider_key:
            api_env = str(provider_presets.get(provider_key, ("", "", ""))[2] or "")
            if api_env:
                resolved_key = str(source.get(api_env, "") or "")

    preset_url, preset_model, preset_key_env = provider_presets.get(
        provider_key,
        ("", "", ""),
    )
    provider_env_base_url = (
        str(source.get(f"{provider_key.upper()}_BASE_URL", "") or "")
        if provider_key
        else ""
    )
    generic_env_applies = (
        bool(env_provider_key and env_provider_key == provider_key)
        or (not provider_key and not requested_provider_key)
        or (requested_provider_key == "custom" and not env_provider_key)
    )
    generic_env_base_url = (
        str(
            source.get("LLM_BASE_URL", "")
            or source.get("OMICSCLAW_BASE_URL", "")
            or ""
        )
        if generic_env_applies
        else ""
    )
    env_model = (
        str(
            source.get("OMICSCLAW_MODEL", "")
            or source.get("LLM_MODEL", "")
            or source.get("SPATIALCLAW_MODEL", "")
            or ""
        )
        if generic_env_applies
        else ""
    )
    env_base_url = provider_env_base_url or generic_env_base_url
    resolved_url = str(base_url or env_base_url or preset_url or "") or None
    resolved_model = str(model or env_model or preset_model or "deepseek-v4-flash")
    resolved_model, _normalized_from = normalize_model_for_provider(
        provider_key,
        resolved_model,
        base_url=base_url or env_base_url,
        provider_presets=provider_presets,
    )

    if not resolved_key and preset_key_env:
        resolved_key = str(source.get(preset_key_env, "") or "")
    if not resolved_key:
        generic_key = (
            str(
                source.get("LLM_API_KEY", "")
                or source.get("OMICSCLAW_API_KEY", "")
                or ""
            )
            if generic_env_applies
            else ""
        )
        openai_fallback = (
            str(source.get("OPENAI_API_KEY", "") or "")
            if provider_key in {"", "openai"}
            else ""
        )
        resolved_key = str(generic_key or openai_fallback or "")

    return resolved_url, resolved_model, resolved_key


def _build_sanitized_chat_openai_class(base_cls: type[Any]) -> type[Any]:
    from langchain_core.messages import BaseMessage

    class SanitizedChatOpenAI(base_cls):
        """Ensure message content is a plain string for OpenAI-compatible APIs."""

        def _sanitize(self, messages: list[BaseMessage]) -> list[BaseMessage]:
            for message in messages:
                if isinstance(message.content, list):
                    try:
                        text_parts: list[str] = []
                        for block in message.content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text_parts.append(block.get("text", ""))
                            else:
                                text_parts.append(json.dumps(block, ensure_ascii=False))
                        message.content = "\n".join(text_parts)
                    except Exception:
                        message.content = json.dumps(message.content, ensure_ascii=False)
                elif message.content is None:
                    message.content = ""
            return messages

        async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
            return super()._astream(
                self._sanitize(messages),
                stop=stop,
                run_manager=run_manager,
                **kwargs,
            )

        async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
            return await super()._agenerate(
                self._sanitize(messages),
                stop=stop,
                run_manager=run_manager,
                **kwargs,
            )

    return SanitizedChatOpenAI


def get_langchain_llm(
    provider: str = "",
    model: str = "",
    *,
    base_url: str = "",
    api_key: str = "",
    temperature: float = 0.3,
    timeout: Any = None,
    anthropic_timeout: float | None = None,
    env: Mapping[str, str] | None = None,
    openai_cls: type[Any] | None = None,
    anthropic_cls: type[Any] | None = None,
) -> Any:
    """Build a LangChain chat model from centralized provider settings.

    The module stays dependency-light at import time. Optional LangChain
    providers are imported lazily only when this factory is called.
    """
    source = os.environ if env is None else env
    provider_key = str(provider or "").strip().lower()
    if not provider_key:
        provider_key = detect_provider_from_env(env=source) or "deepseek"

    resolved_url, resolved_model, resolved_key = resolve_provider(
        provider=provider_key,
        base_url=base_url,
        model=model,
        api_key=api_key,
        env=source,
    )

    # Lazy import — keep this module dependency-light at import time.
    from omicsclaw.core.llm_models import get_default_features

    default_features = get_default_features(
        provider_key, resolved_model, base_url=resolved_url or "",
    )

    if provider_key == "anthropic":
        if anthropic_cls is None:
            from langchain_anthropic import ChatAnthropic as anthropic_cls

        anthropic_kwargs: dict[str, Any] = {
            "model": resolved_model,
            "anthropic_api_key": resolved_key or None,
            "temperature": temperature,
        }
        effective_anthropic_timeout = (
            anthropic_timeout if anthropic_timeout is not None else timeout
        )
        if effective_anthropic_timeout is not None:
            anthropic_kwargs["timeout"] = effective_anthropic_timeout
        if resolved_url:
            anthropic_kwargs["anthropic_api_url"] = resolved_url
        # Catalog defaults (thinking) — only set when not localhost ccproxy
        for k, v in default_features.items():
            anthropic_kwargs.setdefault(k, v)
        return anthropic_cls(**anthropic_kwargs)

    if openai_cls is None:
        from langchain_openai import ChatOpenAI as _ChatOpenAI

        openai_cls = _build_sanitized_chat_openai_class(_ChatOpenAI)

    openai_kwargs: dict[str, Any] = {
        "model": resolved_model,
        "openai_api_key": resolved_key or None,
        "temperature": temperature,
    }
    if timeout is not None:
        openai_kwargs["timeout"] = timeout
    if resolved_url:
        openai_kwargs["openai_api_base"] = resolved_url
    # Catalog defaults (extra_body.reasoning_effort / include_thoughts /
    # reasoning / enable_thinking) — caller's existing extra_body wins.
    if default_features:
        existing_extra = openai_kwargs.get("extra_body") or {}
        new_extra = dict(default_features.get("extra_body") or {})
        new_extra.update(existing_extra)  # caller wins on conflict
        if new_extra:
            openai_kwargs["extra_body"] = new_extra
        # Forward any non-extra_body keys from defaults (none today, future-proof)
        for k, v in default_features.items():
            if k == "extra_body":
                continue
            openai_kwargs.setdefault(k, v)
    return openai_cls(**openai_kwargs)
