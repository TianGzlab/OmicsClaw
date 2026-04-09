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


PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    # --- Tier 1: Primary providers ---
    "deepseek": ("https://api.deepseek.com", "deepseek-chat", "DEEPSEEK_API_KEY"),
    "openai": ("", "gpt-4o", "OPENAI_API_KEY"),
    "anthropic": (
        "https://api.anthropic.com/v1/",
        "claude-sonnet-4-5-20250514",
        "ANTHROPIC_API_KEY",
    ),
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini-2.5-flash",
        "GOOGLE_API_KEY",
    ),
    "nvidia": (
        "https://integrate.api.nvidia.com/v1",
        "deepseek-ai/deepseek-r1",
        "NVIDIA_API_KEY",
    ),
    # --- Tier 2: Third-party aggregators ---
    "siliconflow": (
        "https://api.siliconflow.cn/v1",
        "deepseek-ai/DeepSeek-V3",
        "SILICONFLOW_API_KEY",
    ),
    "openrouter": (
        "https://openrouter.ai/api/v1",
        "deepseek/deepseek-chat-v3-0324",
        "OPENROUTER_API_KEY",
    ),
    "volcengine": (
        "https://ark.cn-beijing.volces.com/api/v3",
        "doubao-1.5-pro-256k",
        "VOLCENGINE_API_KEY",
    ),
    "dashscope": (
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "qwen-max",
        "DASHSCOPE_API_KEY",
    ),
    "zhipu": (
        "https://open.bigmodel.cn/api/paas/v4",
        "glm-4-flash",
        "ZHIPU_API_KEY",
    ),
    # --- Tier 3: Local & custom ---
    "ollama": ("http://localhost:11434/v1", "qwen2.5:7b", ""),
    "custom": ("", "", ""),
}

PROVIDER_DISPLAY_METADATA: dict[str, ProviderDisplayMetadata] = {
    "deepseek": {
        "display_name": "DeepSeek",
        "description": "Cost-effective reasoning model",
        "description_zh": "高性价比推理模型",
        "tier": "primary",
        "models": ("deepseek-chat", "deepseek-reasoner"),
    },
    "openai": {
        "display_name": "OpenAI",
        "description": "GPT-4o and o-series models",
        "description_zh": "GPT-4o 及 o 系列模型",
        "tier": "primary",
        "models": ("gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "o3", "o3-mini", "o4-mini"),
    },
    "anthropic": {
        "display_name": "Anthropic",
        "description": "Claude Sonnet and Opus",
        "description_zh": "Claude Sonnet 和 Opus",
        "tier": "primary",
        "models": ("claude-sonnet-4-5-20250514", "claude-opus-4-20250514", "claude-haiku-4-5-20251001"),
    },
    "gemini": {
        "display_name": "Google Gemini",
        "description": "Gemini Flash and Pro",
        "description_zh": "Gemini Flash 和 Pro",
        "tier": "primary",
        "models": ("gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"),
    },
    "nvidia": {
        "display_name": "NVIDIA NIM",
        "description": "Hosted inference on NVIDIA infrastructure",
        "description_zh": "NVIDIA 基础设施托管推理",
        "tier": "primary",
        "models": (
            "deepseek-ai/deepseek-r1",
            "meta/llama-3.3-70b-instruct",
            "nvidia/llama-3.1-nemotron-70b-instruct",
        ),
    },
    "siliconflow": {
        "display_name": "SiliconFlow",
        "description": "China-optimized multi-model hosting",
        "description_zh": "国内优化的多模型托管平台",
        "tier": "aggregator",
        "models": ("deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-R1", "Qwen/Qwen2.5-72B-Instruct"),
    },
    "openrouter": {
        "display_name": "OpenRouter",
        "description": "Multi-model gateway",
        "description_zh": "多模型网关",
        "tier": "aggregator",
        "models": (
            "deepseek/deepseek-chat-v3-0324",
            "anthropic/claude-sonnet-4",
            "openai/gpt-4o",
            "google/gemini-2.5-flash",
        ),
    },
    "volcengine": {
        "display_name": "Volcengine",
        "description": "ByteDance Doubao models",
        "description_zh": "字节跳动豆包模型",
        "tier": "aggregator",
        "models": ("doubao-1.5-pro-256k", "doubao-1.5-pro-32k", "doubao-lite-32k"),
    },
    "dashscope": {
        "display_name": "DashScope",
        "description": "Alibaba Qwen models",
        "description_zh": "阿里巴巴通义千问模型",
        "tier": "aggregator",
        "models": ("qwen-max", "qwen-plus", "qwen-turbo", "qwen-long"),
    },
    "zhipu": {
        "display_name": "Zhipu AI",
        "description": "GLM-4 series models",
        "description_zh": "GLM-4 系列模型",
        "tier": "aggregator",
        "models": ("glm-4-flash", "glm-4-plus", "glm-4-long", "glm-4-air"),
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
    "zhipu",
)

PROVIDER_CHOICES: tuple[str, ...] = tuple(PROVIDER_PRESETS.keys())


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
    entries: list[ProviderRegistryEntry] = []
    for name, (base_url, default_model, env_key) in provider_presets.items():
        metadata = get_provider_display_metadata(name)
        models = list(dict.fromkeys([
            *metadata["models"],
            *((default_model,) if default_model else tuple()),
        ]))
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
    env_base_url = (
        str(source.get(f"{provider_key.upper()}_BASE_URL", "") or "")
        if provider_key
        else ""
    )
    resolved_url = str(base_url or env_base_url or preset_url or "") or None
    resolved_model = str(model or preset_model or "deepseek-chat")

    if not resolved_key and preset_key_env:
        resolved_key = str(source.get(preset_key_env, "") or "")
    if not resolved_key:
        resolved_key = str(
            source.get("LLM_API_KEY", "")
            or source.get("OPENAI_API_KEY", "")
            or ""
        )

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
    return openai_cls(**openai_kwargs)
