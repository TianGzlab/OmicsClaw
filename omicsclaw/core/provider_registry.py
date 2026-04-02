"""Shared LLM provider registry and resolution helpers.

This module is intentionally dependency-light so it can be reused by bot,
interactive, routing, onboarding, and diagnostics surfaces without importing
heavier runtime modules.
"""

from __future__ import annotations

import os
from typing import Mapping

ProviderPreset = tuple[str, str, str]


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
