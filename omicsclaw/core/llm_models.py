"""LLM model catalog: short-name registry, context-window table, and
per-(provider, model) feature defaults.

This module is intentionally pure-data + pure-function. It has no I/O, no
logging, and never raises into callers. The three OmicsClaw LLM call paths
(``provider_registry.get_langchain_llm``, ``autoagent.llm_client.call_llm``,
``routing.llm_router.route_with_llm``) opportunistically consume it.

Public API:
    ModelInfo                — frozen dataclass
    resolve_model            — (provider, model) → ModelInfo
    get_context_window       — model_id → window in tokens, or None
    get_default_features     — (provider, model, base_url) → kwargs dict
    list_models_for_provider — provider → list[ModelInfo]
    all_short_names          — deduplicated short-name list
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

# (short_name, model_id, provider). Order matters for tools that pick a
# default — list flagship/most-capable first within each provider section.
MODEL_CATALOG: list[tuple[str, str, str]] = [
    # anthropic
    ("claude-opus-4-7",   "claude-opus-4-7",   "anthropic"),
    ("claude-opus-4-6",   "claude-opus-4-6",   "anthropic"),
    ("claude-sonnet-4-6", "claude-sonnet-4-6", "anthropic"),
    ("claude-sonnet-4-5", "claude-sonnet-4-5", "anthropic"),
    ("claude-haiku-4-5",  "claude-haiku-4-5",  "anthropic"),
    # openai
    ("gpt-5.5-pro",   "gpt-5.5-pro",   "openai"),
    ("gpt-5.5",       "gpt-5.5",       "openai"),
    ("gpt-5.4",       "gpt-5.4",       "openai"),
    ("gpt-5.4-mini",  "gpt-5.4-mini",  "openai"),
    ("gpt-5.3-codex", "gpt-5.3-codex", "openai"),
    ("gpt-5",         "gpt-5",         "openai"),
    ("gpt-5-mini",    "gpt-5-mini",    "openai"),
    # gemini
    ("gemini-3.1-pro",   "gemini-3.1-pro-preview",   "gemini"),
    ("gemini-3-flash",   "gemini-3-flash-preview",   "gemini"),
    ("gemini-2.5-flash", "gemini-2.5-flash",         "gemini"),
    ("gemini-2.5-pro",   "gemini-2.5-pro",           "gemini"),
    # nvidia
    ("nemotron-super", "nvidia/nemotron-3-super-120b-a12b", "nvidia"),
    ("deepseek-v3.2",  "deepseek-ai/deepseek-v3.2",         "nvidia"),
    ("kimi-k2.5",      "moonshotai/kimi-k2.5",              "nvidia"),
    ("qwen3.5-397b",   "qwen/qwen3.5-397b-a17b",            "nvidia"),
    # siliconflow
    ("minimax-m2.5", "Pro/MiniMaxAI/MiniMax-M2.5", "siliconflow"),
    ("glm-5",        "Pro/zai-org/GLM-5",          "siliconflow"),
    ("kimi-k2.5",    "Pro/moonshotai/Kimi-K2.5",   "siliconflow"),
    ("glm-4.7",      "Pro/zai-org/GLM-4.7",        "siliconflow"),
    # openrouter
    ("claude-opus-4.7",   "anthropic/claude-opus-4.7",     "openrouter"),
    ("claude-sonnet-4.6", "anthropic/claude-sonnet-4.6",   "openrouter"),
    ("gpt-5.5",           "openai/gpt-5.5",                "openrouter"),
    ("gpt-5.4",           "openai/gpt-5.4",                "openrouter"),
    ("gemini-3.1-pro",    "google/gemini-3.1-pro-preview", "openrouter"),
    ("kimi-k2.6",         "moonshotai/kimi-k2.6",          "openrouter"),
    ("minimax-m2.7",      "minimax/minimax-m2.7",          "openrouter"),
    ("deepseek-v4-pro",   "deepseek/deepseek-v4-pro",      "openrouter"),
    # volcengine (Doubao)
    ("doubao-seed-2.0-pro",     "doubao-seed-2-0-pro-260215",          "volcengine"),
    ("doubao-seed-2.0-lite",    "doubao-seed-2-0-lite-260215",         "volcengine"),
    ("doubao-seed-2.0-code",    "doubao-seed-2-0-code-preview-260215", "volcengine"),
    ("doubao-1.5-pro",          "doubao-1.5-pro-256k",                 "volcengine"),
    ("doubao-1.5-thinking-pro", "doubao-1.5-thinking-pro",             "volcengine"),
    # dashscope (Qwen)
    ("qwen3-coder",  "qwen3-coder-plus", "dashscope"),
    ("qwen3-235b",   "qwen3-235b-a22b",  "dashscope"),
    ("qwen3-max",    "qwen-max",         "dashscope"),
    ("qwen3.6-plus", "qwen3.6-plus",     "dashscope"),
    ("qwq-plus",     "qwq-plus",         "dashscope"),
    # moonshot
    ("kimi-k2.6",        "kimi-k2.6",        "moonshot"),
    ("kimi-k2.5",        "kimi-k2.5",        "moonshot"),
    ("kimi-k2-thinking", "kimi-k2-thinking", "moonshot"),
    ("moonshot-v1-auto", "moonshot-v1-auto", "moonshot"),
    # zhipu
    ("glm-5.1",     "glm-5.1",     "zhipu"),
    ("glm-5",       "glm-5",       "zhipu"),
    ("glm-5-turbo", "glm-5-turbo", "zhipu"),
    ("glm-4.7",     "glm-4.7",     "zhipu"),
    # deepseek
    ("deepseek-v4-pro",   "deepseek-v4-pro",   "deepseek"),
    ("deepseek-v4-flash", "deepseek-v4-flash", "deepseek"),
    ("deepseek-r1",       "deepseek-reasoner", "deepseek"),  # legacy alias
    ("deepseek-v3",       "deepseek-chat",     "deepseek"),  # legacy alias
]


# ---------------------------------------------------------------------------
# Context window table
# ---------------------------------------------------------------------------

# Exact-name overrides, lowercased. Wins over family substring matches.
_KNOWN_MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "qwen3.6-27b":      262_000,
    "qwen3.6-35b-a3b":  262_000,
    "claude-haiku-4-5": 200_000,
}

# Family-level substring fallbacks. Order matters — first match wins.
_KNOWN_MODEL_FAMILIES: list[tuple[str, int]] = [
    ("claude-",       1_000_000),  # via context-1m beta header
    ("gpt-5.5",       1_050_000),
    ("kimi-k2",         262_000),
    ("glm-5",           203_000),
    ("deepseek-v4",   1_050_000),
    ("qwen3.6",       1_000_000),
    ("doubao-seed-2", 1_000_000),
]


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelInfo:
    short_name: str
    model_id: str
    provider: str
    context_window: int | None = None
    default_features: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


def _is_localhost(base_url: str) -> bool:
    if not base_url:
        return False
    lowered = base_url.lower()
    return "127.0.0.1" in lowered or "localhost" in lowered


def get_context_window(model: str | None) -> int | None:
    """Return the context-window for a model_id (or short name).

    Priority: exact lowercased match → final ``/``-segment exact match →
    family-level substring match. Returns ``None`` if nothing matches.
    """
    if not model or not isinstance(model, str):
        return None
    lowered = model.lower()
    if lowered in _KNOWN_MODEL_CONTEXT_WINDOWS:
        return _KNOWN_MODEL_CONTEXT_WINDOWS[lowered]
    short = lowered.split("/")[-1]
    if short != lowered and short in _KNOWN_MODEL_CONTEXT_WINDOWS:
        return _KNOWN_MODEL_CONTEXT_WINDOWS[short]
    for pattern, window in _KNOWN_MODEL_FAMILIES:
        if pattern in lowered:
            return window
    return None


def get_default_features(
    provider: str,
    model: str,
    *,
    base_url: str = "",
) -> dict[str, Any]:
    """Return per-(provider, model) recommended kwargs for an LLM call.

    Returned dict is fresh (caller may mutate). Localhost base_urls (ccproxy)
    cause anthropic/openai feature injection to be skipped — those proxies
    don't accept the same payload shape.

    Never raises.
    """
    p = (provider or "").strip().lower()
    m = (model or "").strip()
    m_lower = m.lower()
    on_localhost = _is_localhost(base_url)

    if p == "anthropic":
        if on_localhost:
            return {}
        # 4-6 / 4-7 → adaptive (server-side resolves to enabled with budget)
        if "4-6" in m_lower or "4-7" in m_lower:
            return {"thinking": {"type": "adaptive"}}
        # All other claude- → enabled with default budget
        return {"thinking": {"type": "enabled", "budget_tokens": 10000}}

    if p == "openai":
        if on_localhost:
            return {}
        effort = "max" if any(s in m_lower for s in ("5.4", "5.5", "codex")) else "high"
        return {"extra_body": {"reasoning_effort": effort}}

    if p == "gemini":
        return {"extra_body": {"include_thoughts": True}}

    if p == "ollama":
        return {"extra_body": {"reasoning": True}}

    if p == "siliconflow":
        return {"extra_body": {"enable_thinking": False}}

    return {}


def resolve_model(provider: str, model: str) -> ModelInfo:
    """Find catalog entry for (provider, model). Falls back gracefully.

    The returned ModelInfo always has ``model_id`` populated (with the input
    if no entry matched), so callers can use it as a passthrough.
    Never raises.
    """
    p = (provider or "").strip().lower()
    m = (model or "").strip()

    short_name = m
    model_id = m
    for entry_short, entry_model_id, entry_provider in MODEL_CATALOG:
        if entry_provider != p:
            continue
        if m == entry_short or m == entry_model_id:
            short_name = entry_short
            model_id = entry_model_id
            break

    return ModelInfo(
        short_name=short_name,
        model_id=model_id,
        provider=p,
        context_window=get_context_window(model_id),
        default_features=get_default_features(p, model_id),
    )


def list_models_for_provider(provider: str) -> list[ModelInfo]:
    """Return every catalog entry for ``provider``, in registry order."""
    p = (provider or "").strip().lower()
    return [
        ModelInfo(
            short_name=short_name,
            model_id=model_id,
            provider=p,
            context_window=get_context_window(model_id),
            default_features=get_default_features(p, model_id),
        )
        for short_name, model_id, entry_provider in MODEL_CATALOG
        if entry_provider == p
    ]


def all_short_names() -> list[str]:
    """Deduplicated list of short names, preserving registry order."""
    seen: set[str] = set()
    out: list[str] = []
    for short_name, _, _ in MODEL_CATALOG:
        if short_name in seen:
            continue
        seen.add(short_name)
        out.append(short_name)
    return out


__all__ = [
    "MODEL_CATALOG",
    "ModelInfo",
    "all_short_names",
    "get_context_window",
    "get_default_features",
    "list_models_for_provider",
    "resolve_model",
]
