# LLM Catalog Modernization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port EvoScientist's LLM catalog patterns into OmicsClaw — a single model short-name registry, a context-window table, per-model auto thinking/reasoning defaults, a DeepSeek `reasoning_content` multi-turn passback patch, and an Ollama discovery helper — without unifying the three existing LLM call paths.

**Architecture:** Two new leaf modules in `omicsclaw/core/` (`llm_models.py` static catalog + lookups, `llm_patches.py` runtime patches). `provider_registry.py` is modified to bump default models per the upgrade table and to consume the catalog from `get_langchain_llm`. `autoagent/llm_client.py` opportunistically calls the DeepSeek passback when `provider == "deepseek"`. `routing/llm_router.py` only bumps its fallback model string. `.env.example` is synced. The work is TDD throughout.

**Tech Stack:** Python 3.11+, `pytest` (+ `unittest.mock`), `httpx`, `langchain-anthropic`, `langchain-openai`, `openai` SDK. No new dependencies introduced.

**Reference spec:** `docs/superpowers/specs/2026-04-30-llm-catalog-modernization-design.md`

---

> The plan file and its `.gitignore` allowlist entry have already been
> committed alongside this document — Task numbering starts at 1.

## Task 1: Build `omicsclaw/core/llm_models.py` — catalog and lookups

**Files:**
- Create: `omicsclaw/core/llm_models.py`
- Test: `tests/test_llm_models.py`

This is a pure-data module. No side effects, no I/O, no logging. Builds the model registry, the context-window table, and the per-(provider, model) feature defaults that the three call paths can opportunistically consume.

### 1.1 Write the test file (failing)

- [ ] **Step 1: Create the test file**

Create `tests/test_llm_models.py` with the full content below:

```python
"""Tests for omicsclaw.core.llm_models — the LLM model catalog."""
from __future__ import annotations

import pytest

from omicsclaw.core.llm_models import (
    MODEL_CATALOG,
    ModelInfo,
    all_short_names,
    get_context_window,
    get_default_features,
    list_models_for_provider,
    resolve_model,
)


class TestResolveModel:
    def test_known_short_name(self):
        info = resolve_model("anthropic", "claude-opus-4-7")
        assert info.short_name == "claude-opus-4-7"
        assert info.model_id == "claude-opus-4-7"
        assert info.provider == "anthropic"
        assert info.context_window == 1_000_000
        assert info.default_features.get("thinking") == {"type": "adaptive"}

    def test_unknown_falls_back_to_empty_info(self):
        info = resolve_model("anthropic", "claude-fictional-9-9")
        # Unknown short_name → empty info but model_id preserved
        assert info.model_id == "claude-fictional-9-9"
        assert info.provider == "anthropic"
        # Family-substring still finds claude- → 1M
        assert info.context_window == 1_000_000

    def test_unknown_provider_returns_empty(self):
        info = resolve_model("nonexistent", "some-model")
        assert info.model_id == "some-model"
        assert info.provider == "nonexistent"
        assert info.context_window is None
        assert info.default_features == {}

    def test_provider_disambiguation(self):
        # kimi-k2.5 exists in moonshot, siliconflow, nvidia — provider
        # selects the right entry
        moonshot = resolve_model("moonshot", "kimi-k2.5")
        siliconflow = resolve_model("siliconflow", "kimi-k2.5")
        assert moonshot.model_id == "kimi-k2.5"
        assert siliconflow.model_id == "Pro/moonshotai/Kimi-K2.5"


class TestContextWindow:
    def test_exact_match_overrides_family(self):
        # claude-haiku-4-5 is 200K not 1M (exception to claude- family)
        assert get_context_window("claude-haiku-4-5") == 200_000

    def test_qwen36_27b_exact_override(self):
        assert get_context_window("qwen3.6-27b") == 262_000

    def test_family_match_claude(self):
        assert get_context_window("claude-opus-4-7-20260101") == 1_000_000

    def test_family_match_gpt55(self):
        assert get_context_window("gpt-5.5-pro") == 1_050_000

    def test_family_match_kimi_k2(self):
        assert get_context_window("kimi-k2-thinking-turbo") == 262_000

    def test_family_match_deepseek_v4(self):
        assert get_context_window("deepseek-v4-pro") == 1_050_000

    def test_family_match_qwen36_closed(self):
        assert get_context_window("qwen3.6-plus") == 1_000_000

    def test_unknown_returns_none(self):
        assert get_context_window("gpt-3.5-turbo") is None

    def test_empty_returns_none(self):
        assert get_context_window("") is None
        assert get_context_window(None) is None  # type: ignore[arg-type]


class TestDefaultFeatures:
    def test_anthropic_4_6_uses_adaptive_thinking(self):
        feats = get_default_features("anthropic", "claude-sonnet-4-6")
        assert feats.get("thinking") == {"type": "adaptive"}

    def test_anthropic_4_7_uses_adaptive_thinking(self):
        feats = get_default_features("anthropic", "claude-opus-4-7")
        assert feats.get("thinking") == {"type": "adaptive"}

    def test_anthropic_legacy_uses_enabled_thinking(self):
        feats = get_default_features("anthropic", "claude-sonnet-4-5")
        assert feats.get("thinking") == {
            "type": "enabled",
            "budget_tokens": 10000,
        }

    def test_anthropic_localhost_skips_thinking(self):
        feats = get_default_features(
            "anthropic", "claude-opus-4-7",
            base_url="http://127.0.0.1:11435/claude",
        )
        assert "thinking" not in feats

    def test_openai_5_5_uses_max_effort(self):
        feats = get_default_features("openai", "gpt-5.5")
        assert feats["extra_body"]["reasoning_effort"] == "max"

    def test_openai_codex_uses_max_effort(self):
        feats = get_default_features("openai", "gpt-5.3-codex")
        assert feats["extra_body"]["reasoning_effort"] == "max"

    def test_openai_legacy_uses_high_effort(self):
        feats = get_default_features("openai", "gpt-5")
        assert feats["extra_body"]["reasoning_effort"] == "high"

    def test_openai_localhost_skips_reasoning(self):
        feats = get_default_features(
            "openai", "gpt-5.5", base_url="http://localhost:8000/codex/v1"
        )
        assert feats == {}

    def test_gemini_includes_thoughts(self):
        feats = get_default_features("gemini", "gemini-3-flash-preview")
        assert feats["extra_body"]["include_thoughts"] is True

    def test_ollama_reasoning_true(self):
        feats = get_default_features("ollama", "qwen2.5:7b")
        assert feats["extra_body"]["reasoning"] is True

    def test_siliconflow_disables_thinking(self):
        feats = get_default_features("siliconflow", "Pro/zai-org/GLM-5")
        assert feats["extra_body"]["enable_thinking"] is False

    def test_unknown_provider_empty(self):
        assert get_default_features("custom", "any-model") == {}

    def test_unknown_model_provider_known_anthropic(self):
        # Even for an unknown anthropic model, base policy applies (legacy budget)
        feats = get_default_features("anthropic", "claude-experimental-x")
        assert "thinking" in feats


class TestListing:
    def test_list_models_for_provider_anthropic(self):
        infos = list_models_for_provider("anthropic")
        short_names = [i.short_name for i in infos]
        assert "claude-opus-4-7" in short_names
        assert "claude-sonnet-4-6" in short_names

    def test_list_models_for_unknown_provider(self):
        assert list_models_for_provider("nonexistent") == []

    def test_all_short_names_dedups(self):
        names = all_short_names()
        # kimi-k2.5 appears in moonshot, siliconflow, nvidia — appears once
        assert names.count("kimi-k2.5") == 1

    def test_catalog_has_minimum_provider_coverage(self):
        providers = {p for _, _, p in MODEL_CATALOG}
        # All of OmicsClaw's PROVIDER_PRESETS keys with at least one model
        expected = {
            "anthropic", "openai", "gemini", "nvidia", "siliconflow",
            "openrouter", "volcengine", "dashscope", "moonshot", "zhipu",
            "deepseek",
        }
        assert expected.issubset(providers)
```

- [ ] **Step 2: Run the tests — confirm they fail**

Run: `pytest tests/test_llm_models.py -q`
Expected: ImportError / ModuleNotFoundError on `omicsclaw.core.llm_models`.

### 1.2 Implement `llm_models.py`

- [ ] **Step 3: Create the implementation file**

Create `omicsclaw/core/llm_models.py` with the full content below:

```python
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


_EMPTY_INFO_FACTORY_FEATURES: dict[str, Any] = {}


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
```

- [ ] **Step 4: Run the tests — confirm they pass**

Run: `pytest tests/test_llm_models.py -q`
Expected: all green (~25 tests pass).

- [ ] **Step 5: Commit**

```bash
git add omicsclaw/core/llm_models.py tests/test_llm_models.py
git commit -m "$(cat <<'EOF'
feat(llm): add model catalog with short-name registry and feature defaults

New leaf module omicsclaw/core/llm_models.py exposes:
- MODEL_CATALOG (short_name, model_id, provider) registry covering all 11
  OmicsClaw API providers with current mainstream models (claude-opus-4-7,
  gpt-5.5, gemini-3.1-pro-preview, qwen3.6-plus, kimi-k2.6, deepseek-v4-*,
  glm-5.1, doubao-seed-2.0, etc.)
- Context-window table (claude- 1M, gpt-5.5 1.05M, kimi-k2 262K,
  deepseek-v4 1.05M, qwen3.6 1M, doubao-seed-2 1M, glm-5 203K)
- Per-(provider, model) auto thinking/reasoning defaults that respect
  ccproxy localhost endpoints

Pure data, no I/O, no logging, never raises into callers.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Build `omicsclaw/core/llm_patches.py` — runtime patches

**Files:**
- Create: `omicsclaw/core/llm_patches.py`
- Test: `tests/test_llm_patches.py`

Two leaf utilities: a DeepSeek `reasoning_content` multi-turn passback (called at most once per LLM call from `autoagent`) and an Ollama installed-models discovery helper. No module-import-time side effects.

### 2.1 Write the test file (failing)

- [ ] **Step 1: Create the test file**

Create `tests/test_llm_patches.py` with the full content below:

```python
"""Tests for omicsclaw.core.llm_patches — runtime helpers."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import httpx
import pytest

from omicsclaw.core.llm_patches import (
    apply_deepseek_reasoning_passback,
    discover_ollama_models,
    discover_ollama_models_async,
)


# ---------------------------------------------------------------------------
# DeepSeek passback
# ---------------------------------------------------------------------------


class TestDeepseekPassback:
    def test_injects_empty_string_when_assistant_lacks_reasoning_content(self):
        messages = [
            {"role": "system", "content": "you are helpful"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "again"},
        ]
        out = apply_deepseek_reasoning_passback(messages)
        assert out[0]["role"] == "system"
        assert "reasoning_content" not in out[0]
        assert out[1]["role"] == "user"
        assert "reasoning_content" not in out[1]
        assert out[2]["role"] == "assistant"
        assert out[2]["reasoning_content"] == ""
        assert out[3]["role"] == "user"
        assert "reasoning_content" not in out[3]

    def test_preserves_existing_reasoning_content(self):
        messages = [
            {
                "role": "assistant",
                "content": "result",
                "reasoning_content": "I thought about it",
            }
        ]
        out = apply_deepseek_reasoning_passback(messages)
        assert out[0]["reasoning_content"] == "I thought about it"

    def test_skips_user_and_system_roles(self):
        messages = [
            {"role": "system", "content": "hi"},
            {"role": "user", "content": "ping"},
        ]
        out = apply_deepseek_reasoning_passback(messages)
        for m in out:
            assert "reasoning_content" not in m

    def test_idempotent(self):
        messages = [{"role": "assistant", "content": "x"}]
        first = apply_deepseek_reasoning_passback(messages)
        second = apply_deepseek_reasoning_passback(first)
        assert second == first

    def test_returns_new_list_does_not_mutate_caller_dicts(self):
        messages = [{"role": "assistant", "content": "x"}]
        out = apply_deepseek_reasoning_passback(messages)
        assert out is not messages
        # Original dict should not be mutated
        assert "reasoning_content" not in messages[0]

    def test_handles_empty_list(self):
        assert apply_deepseek_reasoning_passback([]) == []

    def test_handles_non_dict_items_passthrough(self):
        # Unknown items survive untouched
        weird = ["not-a-dict", {"role": "assistant", "content": "ok"}]
        out = apply_deepseek_reasoning_passback(weird)  # type: ignore[arg-type]
        assert out[0] == "not-a-dict"
        assert out[1]["reasoning_content"] == ""


# ---------------------------------------------------------------------------
# Ollama discovery (sync)
# ---------------------------------------------------------------------------


class TestDiscoverOllamaModelsSync:
    def test_returns_models_on_200(self, monkeypatch):
        fake_resp = MagicMock(status_code=200)
        fake_resp.json.return_value = {
            "models": [{"name": "qwen2.5:7b"}, {"name": "llama3.3:70b"}]
        }
        with patch("httpx.get", return_value=fake_resp):
            assert discover_ollama_models("http://127.0.0.1:11434") == [
                "qwen2.5:7b",
                "llama3.3:70b",
            ]

    def test_returns_empty_on_404(self):
        fake_resp = MagicMock(status_code=404)
        with patch("httpx.get", return_value=fake_resp):
            assert discover_ollama_models("http://127.0.0.1:11434") == []

    def test_returns_empty_on_connection_error(self):
        with patch("httpx.get", side_effect=httpx.ConnectError("nope")):
            assert discover_ollama_models("http://127.0.0.1:11434") == []

    def test_returns_empty_on_malformed_json(self):
        fake_resp = MagicMock(status_code=200)
        fake_resp.json.side_effect = ValueError("bad json")
        with patch("httpx.get", return_value=fake_resp):
            assert discover_ollama_models("http://127.0.0.1:11434") == []

    def test_no_url_returns_empty(self):
        assert discover_ollama_models("") == []
        assert discover_ollama_models(None) == []  # type: ignore[arg-type]

    def test_strips_trailing_slash(self):
        captured = {}

        def fake_get(url, *args, **kwargs):
            captured["url"] = url
            resp = MagicMock(status_code=200)
            resp.json.return_value = {"models": []}
            return resp

        with patch("httpx.get", side_effect=fake_get):
            discover_ollama_models("http://127.0.0.1:11434/")
        assert captured["url"] == "http://127.0.0.1:11434/api/tags"


# ---------------------------------------------------------------------------
# Ollama discovery (async)
# ---------------------------------------------------------------------------


class TestDiscoverOllamaModelsAsync:
    def test_no_url_returns_empty(self):
        assert asyncio.run(discover_ollama_models_async("")) == []

    def test_returns_empty_on_exception(self):
        async def fake_get(*args, **kwargs):
            raise httpx.ConnectError("nope")

        client = MagicMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = False
        client.get = fake_get

        with patch("httpx.AsyncClient", return_value=client):
            result = asyncio.run(
                discover_ollama_models_async("http://127.0.0.1:11434")
            )
        assert result == []
```

- [ ] **Step 2: Run the tests — confirm they fail**

Run: `pytest tests/test_llm_patches.py -q`
Expected: ImportError on `omicsclaw.core.llm_patches`.

### 2.2 Implement `llm_patches.py`

- [ ] **Step 3: Create the implementation file**

Create `omicsclaw/core/llm_patches.py` with the full content below:

```python
"""Runtime patches and discovery helpers for LLM provider quirks.

Two leaf utilities, both must be invoked explicitly — no module-import-time
side effects. Both never raise into callers; failure modes degrade to the
unpatched behavior or an empty result.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# DeepSeek reasoning_content multi-turn passback
# ---------------------------------------------------------------------------
#
# DeepSeek V3.x/V4 thinking-mode endpoints require every historical
# assistant message in the request payload to carry a ``reasoning_content``
# field. Without it, multi-turn requests fail with HTTP 400 "The
# reasoning_content in the thinking mode must be passed back".
#
# OmicsClaw's autoagent uses the raw OpenAI SDK and does not capture
# ``reasoning_content`` from past responses, so we inject an empty string
# fallback for any assistant message that lacks the field. Empirically
# tolerated by both thinking and non-thinking DeepSeek endpoints.
# ---------------------------------------------------------------------------


def apply_deepseek_reasoning_passback(
    messages: list[Any],
) -> list[Any]:
    """Return a new list with ``reasoning_content`` injected on assistant messages.

    Caller's dicts are not mutated — non-assistant messages and non-dict items
    pass through by reference.

    Args:
        messages: chat-completions style messages list.

    Returns:
        New list. Each assistant dict that lacks ``reasoning_content`` gets
        a copy with ``reasoning_content=""`` injected.
    """
    out: list[Any] = []
    for msg in messages:
        if not isinstance(msg, dict):
            out.append(msg)
            continue
        if msg.get("role") != "assistant":
            out.append(msg)
            continue
        if "reasoning_content" in msg:
            out.append(msg)
            continue
        copy = dict(msg)
        copy["reasoning_content"] = ""
        out.append(copy)
    return out


# ---------------------------------------------------------------------------
# Ollama installed-model discovery
# ---------------------------------------------------------------------------


def discover_ollama_models(base_url: str | None, *, timeout: float = 5.0) -> list[str]:
    """Probe ``GET {base_url}/api/tags`` for installed models.

    Returns the list of model names, or ``[]`` on any failure (no URL,
    connection error, non-200 status, malformed JSON).
    Never raises.
    """
    if not base_url or not isinstance(base_url, str):
        return []
    try:
        import httpx

        resp = httpx.get(
            f"{base_url.rstrip('/')}/api/tags", timeout=timeout
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []
    models = data.get("models", []) if isinstance(data, dict) else []
    return [
        m.get("name", "") for m in models
        if isinstance(m, dict) and m.get("name")
    ]


async def discover_ollama_models_async(
    base_url: str | None, *, timeout: float = 1.5
) -> list[str]:
    """Async variant of :func:`discover_ollama_models`."""
    if not base_url or not isinstance(base_url, str):
        return []
    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/api/tags")
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []
    models = data.get("models", []) if isinstance(data, dict) else []
    return [
        m.get("name", "") for m in models
        if isinstance(m, dict) and m.get("name")
    ]


__all__ = [
    "apply_deepseek_reasoning_passback",
    "discover_ollama_models",
    "discover_ollama_models_async",
]
```

- [ ] **Step 4: Run the tests — confirm they pass**

Run: `pytest tests/test_llm_patches.py -q`
Expected: all green (~13 tests pass).

- [ ] **Step 5: Commit**

```bash
git add omicsclaw/core/llm_patches.py tests/test_llm_patches.py
git commit -m "$(cat <<'EOF'
feat(llm): add DeepSeek passback and Ollama discovery helpers

omicsclaw/core/llm_patches.py exposes:
- apply_deepseek_reasoning_passback(messages) — fixes HTTP 400
  "reasoning_content must be passed back" on multi-turn DeepSeek thinking
  by injecting reasoning_content="" on historical assistant messages
  that lack it. Caller dicts are not mutated.
- discover_ollama_models / discover_ollama_models_async — probe
  GET {base_url}/api/tags for installed model names. Never raises;
  returns [] on any failure.

Both helpers must be explicitly invoked — no import-time side effects.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Update `provider_registry.py` defaults and integrate the catalog

**Files:**
- Modify: `omicsclaw/core/provider_registry.py`
- Modify: `tests/test_provider_registry.py` (sync default-model assertions)
- Create: `tests/test_provider_registry_defaults.py`

This is the highest-risk task. We modify `PROVIDER_PRESETS` defaults per the upgrade table, expand `PROVIDER_DISPLAY_METADATA.models` lists to include current-mainstream entries, and have `get_langchain_llm` consume `llm_models` for context-window awareness and feature defaults.

### 3.1 Write the new defaults test file (failing)

- [ ] **Step 1: Create `tests/test_provider_registry_defaults.py`**

Create the test file with the full content below:

```python
"""Tests verifying default-model upgrades and llm_models integration in
omicsclaw.core.provider_registry.
"""
from __future__ import annotations

import pytest

from omicsclaw.core.provider_registry import (
    PROVIDER_PRESETS,
    get_langchain_llm,
)


# Spec table — keep in sync with
# docs/superpowers/specs/2026-04-30-llm-catalog-modernization-design.md
DEFAULT_MODEL_UPGRADES = {
    "openai":      "gpt-5.5",
    "anthropic":   "claude-sonnet-4-6",
    "gemini":      "gemini-3-flash-preview",
    "nvidia":      "nvidia/nemotron-3-super-120b-a12b",
    "siliconflow": "Pro/zai-org/GLM-5",
    "openrouter":  "anthropic/claude-sonnet-4.6",
    "volcengine":  "doubao-seed-2-0-pro-260215",
    "dashscope":   "qwen3.6-plus",
    "moonshot":    "kimi-k2.6",
    "zhipu":       "glm-5.1",
    "deepseek":    "deepseek-v4-flash",
    "ollama":      "qwen2.5:7b",
}


@pytest.mark.parametrize("provider, expected", list(DEFAULT_MODEL_UPGRADES.items()))
def test_provider_default_model_matches_spec(provider, expected):
    base_url, default_model, env_key = PROVIDER_PRESETS[provider]
    assert default_model == expected, (
        f"{provider}: PROVIDER_PRESETS default {default_model!r} "
        f"diverges from spec value {expected!r}"
    )


def test_custom_provider_has_empty_default():
    base_url, default_model, env_key = PROVIDER_PRESETS["custom"]
    assert default_model == ""


class TestGetLangchainLlmConsumesCatalog:
    def test_anthropic_injects_thinking_for_4_6(self, monkeypatch):
        captured = {}

        class _FakeAnthropic:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
        get_langchain_llm(
            provider="anthropic",
            model="claude-sonnet-4-6",
            anthropic_cls=_FakeAnthropic,
        )
        assert captured.get("thinking") == {"type": "adaptive"}

    def test_anthropic_respects_caller_thinking_override(self, monkeypatch):
        captured = {}

        class _FakeAnthropic:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
        # The caller doesn't currently expose a thinking kwarg, so this
        # asserts the default still fires. Future callers can pass
        # thinking= in kwargs and it must override; the implementation
        # uses dict.setdefault.
        get_langchain_llm(
            provider="anthropic",
            model="claude-sonnet-4-6",
            anthropic_cls=_FakeAnthropic,
        )
        assert "thinking" in captured

    def test_anthropic_localhost_base_url_skips_thinking(self, monkeypatch):
        captured = {}

        class _FakeAnthropic:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv(
            "ANTHROPIC_BASE_URL", "http://127.0.0.1:11435/claude"
        )
        get_langchain_llm(
            provider="anthropic",
            model="claude-sonnet-4-6",
            anthropic_cls=_FakeAnthropic,
        )
        assert "thinking" not in captured

    def test_openai_injects_reasoning_effort(self, monkeypatch):
        captured = {}

        class _FakeOpenAI:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        get_langchain_llm(
            provider="openai",
            model="gpt-5.5",
            openai_cls=_FakeOpenAI,
        )
        extra_body = captured.get("extra_body", {})
        assert extra_body.get("reasoning_effort") == "max"

    def test_openai_localhost_skips_reasoning(self, monkeypatch):
        captured = {}

        class _FakeOpenAI:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv(
            "OPENAI_BASE_URL", "http://127.0.0.1:11435/codex/v1"
        )
        get_langchain_llm(
            provider="openai",
            model="gpt-5.5",
            openai_cls=_FakeOpenAI,
        )
        extra_body = captured.get("extra_body", {})
        assert "reasoning_effort" not in extra_body
```

- [ ] **Step 2: Run the new tests — confirm they fail**

Run: `pytest tests/test_provider_registry_defaults.py -q`
Expected: assertions fail because (a) defaults haven't been bumped yet,
(b) `get_langchain_llm` doesn't yet consume `llm_models`.

### 3.2 Bump PROVIDER_PRESETS defaults

- [ ] **Step 3: Edit `omicsclaw/core/provider_registry.py` — `PROVIDER_PRESETS`**

In `omicsclaw/core/provider_registry.py`, locate the `PROVIDER_PRESETS` dict (around line 38-91). Apply these per-provider edits — leave entries not listed unchanged:

```diff
 PROVIDER_PRESETS: dict[str, ProviderPreset] = {
     # --- Tier 1: Primary providers ---
-    "deepseek": ("https://api.deepseek.com", "deepseek-chat", "DEEPSEEK_API_KEY"),
+    "deepseek": ("https://api.deepseek.com", "deepseek-v4-flash", "DEEPSEEK_API_KEY"),
-    "openai": ("", "gpt-5.4", "OPENAI_API_KEY"),
+    "openai": ("", "gpt-5.5", "OPENAI_API_KEY"),
     "anthropic": (
         "https://api.anthropic.com/v1/",
         "claude-sonnet-4-6",
         "ANTHROPIC_API_KEY",
     ),
     "gemini": (
         "https://generativelanguage.googleapis.com/v1beta/openai/",
-        "gemini-2.5-flash",
+        "gemini-3-flash-preview",
         "GOOGLE_API_KEY",
     ),
     # ...
     "siliconflow": (
         "https://api.siliconflow.cn/v1",
-        "Pro/MiniMaxAI/MiniMax-M2.5",
+        "Pro/zai-org/GLM-5",
         "SILICONFLOW_API_KEY",
     ),
     # ...
     "dashscope": (
         "https://dashscope.aliyuncs.com/compatible-mode/v1",
-        "qwen3-max",
+        "qwen3.6-plus",
         "DASHSCOPE_API_KEY",
     ),
     "moonshot": (
         "https://api.moonshot.cn/v1",
-        "kimi-k2.5",
+        "kimi-k2.6",
         "MOONSHOT_API_KEY",
     ),
     "zhipu": (
         "https://open.bigmodel.cn/api/paas/v4",
-        "glm-5",
+        "glm-5.1",
         "ZHIPU_API_KEY",
     ),
```

Apply these as 7 separate `Edit` invocations to keep diffs surgical.

- [ ] **Step 4: Update `PROVIDER_DISPLAY_METADATA.models` lists**

In the same file, locate `PROVIDER_DISPLAY_METADATA` (around line 93-212). Update the `models` tuples for these providers (only the listed ones). The first entry of each tuple becomes the new default — keep them in flagship-first order:

```diff
     "openai": {
         "display_name": "OpenAI",
-        "description": "GPT-5 and Codex series models",
+        "description": "GPT-5.5 and Codex series models",
-        "description_zh": "GPT-5 及 Codex 系列模型",
+        "description_zh": "GPT-5.5 及 Codex 系列模型",
         "tier": "primary",
-        "models": ("gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.3-codex", "gpt-5", "gpt-5-mini"),
+        "models": ("gpt-5.5-pro", "gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.3-codex", "gpt-5", "gpt-5-mini"),
     },
     "anthropic": {
         "display_name": "Anthropic",
-        "description": "Claude Opus, Sonnet and Haiku",
-        "description_zh": "Claude Opus、Sonnet 和 Haiku",
+        "description": "Claude Opus 4.7, Sonnet 4.6 and Haiku 4.5",
+        "description_zh": "Claude Opus 4.7、Sonnet 4.6 和 Haiku 4.5",
         "tier": "primary",
-        "models": ("claude-opus-4-6", "claude-sonnet-4-6", "claude-sonnet-4-5", "claude-haiku-4-5"),
+        "models": ("claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6", "claude-sonnet-4-5", "claude-haiku-4-5"),
     },
     "gemini": {
         "display_name": "Google Gemini",
-        "description": "Gemini 3 and 2.5 series",
-        "description_zh": "Gemini 3 和 2.5 系列",
+        "description": "Gemini 3.1 / 3 / 2.5 series",
+        "description_zh": "Gemini 3.1 / 3 / 2.5 系列",
         "tier": "primary",
-        "models": ("gemini-3.1-pro", "gemini-3-flash", "gemini-2.5-flash", "gemini-2.5-pro"),
+        "models": ("gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-2.5-pro", "gemini-2.5-flash"),
     },
     # ... (siliconflow, openrouter, volcengine, dashscope, moonshot, zhipu, deepseek)
     "siliconflow": {
         ...
         "tier": "aggregator",
-        "models": ("Pro/MiniMaxAI/MiniMax-M2.5", "Pro/zai-org/GLM-5", "Pro/moonshotai/Kimi-K2.5", "Pro/zai-org/GLM-4.7"),
+        "models": ("Pro/zai-org/GLM-5", "Pro/MiniMaxAI/MiniMax-M2.5", "Pro/moonshotai/Kimi-K2.5", "Pro/zai-org/GLM-4.7"),
     },
     "openrouter": {
         ...
         "tier": "aggregator",
-        "models": (
-            "anthropic/claude-sonnet-4.6",
-            "openai/gpt-5.4",
-            "google/gemini-3.1-pro-preview",
-            "moonshotai/kimi-k2.5",
-            "minimax/minimax-m2.7",
-        ),
+        "models": (
+            "anthropic/claude-sonnet-4.6",
+            "anthropic/claude-opus-4.7",
+            "openai/gpt-5.5",
+            "openai/gpt-5.4",
+            "google/gemini-3.1-pro-preview",
+            "moonshotai/kimi-k2.6",
+            "minimax/minimax-m2.7",
+            "deepseek/deepseek-v4-pro",
+        ),
     },
     "dashscope": {
         "display_name": "DashScope",
-        "description": "Alibaba Qwen3 / Qwen3.6 models (Max, Plus, Coder, QwQ)",
-        "description_zh": "阿里巴巴通义千问 Qwen3 / Qwen3.6 系列（Max、Plus、Coder、QwQ）",
+        "description": "Alibaba Qwen3.6 / Qwen3 models (Plus, Max, Coder, QwQ)",
+        "description_zh": "阿里巴巴通义千问 Qwen3.6 / Qwen3 系列（Plus、Max、Coder、QwQ）",
         "tier": "aggregator",
         "models": (
+            "qwen3.6-plus",
-            "qwen3-max",
-            "qwen3.6-plus",
+            "qwen3-max",
             "qwen3-coder-plus",
+            "qwen3-235b-a22b",
             "qwq-plus",
-            "qwen3.5-flash",
-            "qwen-turbo-latest",
         ),
     },
     "moonshot": {
         "display_name": "Moonshot",
-        "description": "Kimi K2 series models",
-        "description_zh": "月之暗面 Kimi K2 系列模型",
+        "description": "Kimi K2.6 / K2.5 series models",
+        "description_zh": "月之暗面 Kimi K2.6 / K2.5 系列模型",
         "tier": "aggregator",
-        "models": ("kimi-k2.5", "kimi-k2-thinking", "kimi-k2-thinking-turbo", "moonshot-v1-auto"),
+        "models": ("kimi-k2.6", "kimi-k2.5", "kimi-k2-thinking", "moonshot-v1-auto"),
     },
     "zhipu": {
         "display_name": "Zhipu AI",
-        "description": "GLM-5 series models",
-        "description_zh": "智谱 GLM-5 系列模型",
+        "description": "GLM-5.1 / GLM-5 series models",
+        "description_zh": "智谱 GLM-5.1 / GLM-5 系列模型",
         "tier": "aggregator",
         "models": ("glm-5.1", "glm-5", "glm-5-turbo", "glm-4.7"),
     },
     "deepseek": {
         "display_name": "DeepSeek",
-        "description": "Cost-effective reasoning model",
-        "description_zh": "高性价比推理模型",
+        "description": "DeepSeek V4 series — cost-effective reasoning",
+        "description_zh": "DeepSeek V4 系列 — 高性价比推理",
         "tier": "primary",
-        "models": ("deepseek-chat", "deepseek-reasoner"),
+        "models": ("deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"),
     },
```

Volcengine and NVIDIA model lists keep their current entries.

### 3.3 Wire `get_langchain_llm` into `llm_models`

- [ ] **Step 5: Modify `get_langchain_llm`**

In `omicsclaw/core/provider_registry.py`, replace the body of `get_langchain_llm` (currently lines 461-524) with the version below. The diff: after `resolve_provider`, look up `get_default_features(...)` and apply via `setdefault` so caller-supplied kwargs always win.

Replace:

```python
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
```

with:

```python
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
```

### 3.4 Sync existing `tests/test_provider_registry.py` assertions

- [ ] **Step 6: Update default-model assertions in the existing test file**

In `tests/test_provider_registry.py`, fix the two assertions that pin old defaults:

```diff
@@ test_dashscope_preset_exposes_latest_qwen_models
-    assert dashscope["default_model"] == "qwen3-max"
-    assert dashscope["models"][0] == "qwen3-max"
+    assert dashscope["default_model"] == "qwen3.6-plus"
+    assert dashscope["models"][0] == "qwen3.6-plus"
     assert "qwen3.6-plus" in dashscope["models"]
     assert "qwen3-coder-plus" in dashscope["models"]
-    assert "qwen3-235b-a22b" not in dashscope["models"]
+    assert "qwen3-235b-a22b" in dashscope["models"]

@@ test_resolve_provider_uses_provider_specific_defaults
-    assert resolved_model == "deepseek-chat"
+    assert resolved_model == "deepseek-v4-flash"

@@ test_resolve_provider_auto_detects_specific_key
-    assert resolved_model == "gpt-5.4"
+    assert resolved_model == "gpt-5.5"
```

Note that the `test_normalize_model_for_provider_*` and
`test_resolve_provider_normalizes_stale_foreign_default_model` cases use
`PROVIDER_PRESETS["anthropic"][1]` directly via lookups, not hard-coded
strings, so they don't need updates.

The `test_get_langchain_llm_uses_*` cases use `PROVIDER_PRESETS["..."][1]`
similarly. They will, however, now see a `thinking` kwarg (anthropic) and
an `extra_body` kwarg (openai-routed providers like openrouter). The
existing assertions only positively-assert specific kwargs and don't use
`captured == {...}`, so they should still pass — verify in the next step.

### 3.5 Run tests

- [ ] **Step 7: Run the updated and new test files**

Run: `pytest tests/test_provider_registry.py tests/test_provider_registry_defaults.py -q`
Expected: all green.

If `test_get_langchain_llm_uses_openai_compatible_kwargs` fails with an
unexpected `extra_body` key in `captured`, that's because the test asserts
specific kwargs but doesn't reject extras — re-read the test in the
"check existing tests" step. If it does fail, **stop** and add an
appropriate `assert "extra_body" in captured` rather than removing the
new behavior.

- [ ] **Step 8: Run the pipeline-resolution tests as well**

Run: `pytest tests/test_pipeline_provider_resolution.py -q`
Expected: all green.

If a test pinned a stale default-model string, update it to match the
new default per `DEFAULT_MODEL_UPGRADES` in step 1's spec table. (Pre-flight
check showed no hits in `test_pipeline_provider_resolution.py`, so this
is a safety net.)

- [ ] **Step 9: Commit**

```bash
git add omicsclaw/core/provider_registry.py tests/test_provider_registry.py tests/test_provider_registry_defaults.py
git commit -m "$(cat <<'EOF'
feat(llm): bump provider defaults and consume llm_models from get_langchain_llm

Default-model upgrades per spec table (anthropic kept on sonnet-4-6 for
cost reasons; ollama/custom unchanged):
  openai      gpt-5.4              → gpt-5.5
  gemini      gemini-2.5-flash     → gemini-3-flash-preview
  siliconflow MiniMax-M2.5         → GLM-5
  dashscope   qwen3-max            → qwen3.6-plus
  moonshot    kimi-k2.5            → kimi-k2.6
  zhipu       glm-5                → glm-5.1
  deepseek    deepseek-chat        → deepseek-v4-flash

PROVIDER_DISPLAY_METADATA.models lists refreshed to current mainstream
flagships, preserving order with new defaults first.

get_langchain_llm() now consumes omicsclaw.core.llm_models.
get_default_features at construction time:
- anthropic: setdefault thinking={"type": "adaptive"} on 4-6/4-7 models,
  enabled+10K budget on legacy claude-* — skipped when base_url is
  localhost (ccproxy 422 risk).
- openai-routed: extra_body.reasoning_effort=max for 5.4/5.5/codex, high
  otherwise — skipped on localhost ccproxy. Caller-supplied extra_body
  wins on conflict.
- gemini/ollama/siliconflow: respective extra_body defaults forwarded.

Test sync: dashscope default + qwen3-235b-a22b inclusion,
deepseek default deepseek-chat → deepseek-v4-flash, openai default
gpt-5.4 → gpt-5.5.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Wire DeepSeek passback into `autoagent/llm_client.py`

**Files:**
- Modify: `omicsclaw/autoagent/llm_client.py`
- Create: `tests/test_autoagent_llm_client_deepseek.py`

The autoagent path uses raw `openai.OpenAI`. We patch its `messages` list before sending when the provider is `"deepseek"`, and forward the catalog's `extra_body` so DeepSeek thinking auto-enables.

### 4.1 Write the new test file (failing)

- [ ] **Step 1: Create `tests/test_autoagent_llm_client_deepseek.py`**

```python
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
```

- [ ] **Step 2: Run the new test file — confirm it fails**

Run: `pytest tests/test_autoagent_llm_client_deepseek.py -q`
Expected: failures. Likely cause depends on which import fails first
(`apply_deepseek_reasoning_passback` not yet imported in `llm_client`,
or `extra_body` test still passes because we haven't wired the catalog
yet — that one is acceptable to start passing).

### 4.2 Wire the passback and catalog forwarding

- [ ] **Step 3: Modify `omicsclaw/autoagent/llm_client.py`**

At the top of the file, just below the existing `from omicsclaw.autoagent.constants import ...`, add:

```python
from omicsclaw.core.llm_models import get_default_features
from omicsclaw.core.llm_patches import apply_deepseek_reasoning_passback
```

Then in the body of `call_llm`, replace the `messages = [...]` block + the
retry loop's `client.chat.completions.create(...)` call. Locate this region
(currently around lines 96-118):

```python
    from openai import OpenAI

    client = OpenAI(
        api_key=runtime.api_key,
        base_url=runtime.base_url or None,
        timeout=LLM_CALL_TIMEOUT_SECONDS,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": directive},
    ]

    last_exc: Exception | None = None
    for attempt in range(1, LLM_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=runtime.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
```

Replace with:

```python
    from openai import OpenAI

    client = OpenAI(
        api_key=runtime.api_key,
        base_url=runtime.base_url or None,
        timeout=LLM_CALL_TIMEOUT_SECONDS,
    )

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": directive},
    ]
    if runtime.provider == "deepseek":
        messages = apply_deepseek_reasoning_passback(messages)

    extra_body = (
        get_default_features(
            runtime.provider, runtime.model, base_url=runtime.base_url or "",
        ).get("extra_body")
        or None
    )

    last_exc: Exception | None = None
    for attempt in range(1, LLM_MAX_RETRIES + 1):
        try:
            create_kwargs: dict[str, object] = {
                "model": runtime.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if extra_body:
                create_kwargs["extra_body"] = extra_body
            response = client.chat.completions.create(**create_kwargs)
            return response.choices[0].message.content or ""
```

Leave the existing `except Exception as exc:` block and below untouched.

- [ ] **Step 4: Run the test file — confirm it passes**

Run: `pytest tests/test_autoagent_llm_client_deepseek.py -q`
Expected: 3 tests pass.

- [ ] **Step 5: Run the full autoagent client tests for regression**

Run: `pytest tests/test_autoagent_llm_client.py tests/test_autoagent_llm_client_deepseek.py -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add omicsclaw/autoagent/llm_client.py tests/test_autoagent_llm_client_deepseek.py
git commit -m "$(cat <<'EOF'
feat(autoagent): apply DeepSeek reasoning_content passback and forward catalog extra_body

call_llm() now:
- Calls apply_deepseek_reasoning_passback(messages) when
  runtime.provider == "deepseek". Single-shot directive calls remain
  no-ops; the patch only matters when callers later pass historical
  assistant messages — but pre-wiring it here means we won't have to
  re-touch this surface when multi-turn lands.
- Looks up llm_models.get_default_features() and forwards any non-empty
  extra_body to the OpenAI SDK. ccproxy localhost endpoints opt out
  via the same get_default_features rule.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Bump fallback model in `routing/llm_router.py`

**Files:**
- Modify: `omicsclaw/routing/llm_router.py:29`

This is a one-line change — the very last `or` fallback before `resolve_provider` returns nothing.

- [ ] **Step 1: Edit the fallback model string**

In `omicsclaw/routing/llm_router.py`, locate line 29:

```python
    return api_key, (base_url or "https://api.openai.com/v1"), (model or "gpt-4o-mini")
```

Replace with:

```python
    return api_key, (base_url or "https://api.openai.com/v1"), (model or "gpt-5-mini")
```

- [ ] **Step 2: Run the routing tests**

Run: `pytest tests/test_keyword_routing.py tests/test_auto_routing_disambiguation.py -q`
Expected: all green (these tests don't pin model strings).

- [ ] **Step 3: Commit**

```bash
git add omicsclaw/routing/llm_router.py
git commit -m "$(cat <<'EOF'
feat(routing): bump LLM-routing fallback model gpt-4o-mini → gpt-5-mini

Aligns with the catalog modernization. The fallback only triggers when
neither LLM_MODEL nor OMICSCLAW_MODEL nor a provider-specific default is
set, which is rare in practice.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Sync `.env.example` documentation

**Files:**
- Modify: `.env.example`

The comment block at the top of `.env.example` lists per-provider default
model names. Sync it to the new defaults so users following the .env
example see consistent values.

- [ ] **Step 1: Update the supported-providers comment block**

In `.env.example`, find the comment block listing providers (around lines
30-43, starting with `# Supported providers:`). Replace the parenthetical
defaults to match the new spec table:

```diff
 # Supported providers:
-#   deepseek    — https://api.deepseek.com       (default: deepseek-chat)
+#   deepseek    — https://api.deepseek.com       (default: deepseek-v4-flash)
-#   openai      — OpenAI API                     (default: gpt-4o)
+#   openai      — OpenAI API                     (default: gpt-5.5)
-#   anthropic   — Anthropic Claude via API        (default: claude-sonnet-4-5)
+#   anthropic   — Anthropic Claude via API        (default: claude-sonnet-4-6)
-#   gemini      — Google Gemini via OpenAI compat (default: gemini-2.5-flash)
+#   gemini      — Google Gemini via OpenAI compat (default: gemini-3-flash-preview)
 #   nvidia      — NVIDIA NIM                     (default: deepseek-ai/deepseek-r1)
-#   siliconflow — SiliconFlow (硅基流动)           (default: DeepSeek-V3)
+#   siliconflow — SiliconFlow (硅基流动)           (default: Pro/zai-org/GLM-5)
-#   openrouter  — OpenRouter aggregator           (default: deepseek-chat-v3)
+#   openrouter  — OpenRouter aggregator           (default: anthropic/claude-sonnet-4.6)
-#   volcengine  — Volcengine 火山引擎 (Doubao)     (default: doubao-1.5-pro-256k)
+#   volcengine  — Volcengine 火山引擎 (Doubao)     (default: doubao-seed-2-0-pro-260215)
-#   dashscope   — Alibaba DashScope 阿里云 (Qwen) (default: qwen-max)
+#   dashscope   — Alibaba DashScope 阿里云 (Qwen) (default: qwen3.6-plus)
-#   zhipu       — Zhipu AI 智谱 (GLM)             (default: glm-4-flash)
+#   zhipu       — Zhipu AI 智谱 (GLM)             (default: glm-5.1)
 #   ollama      — Local Ollama server             (default: qwen2.5:7b)
 #   custom      — Any OpenAI-compatible endpoint
```

Also add the moonshot entry (it was previously missing from the comment):

```diff
-#   zhipu       — Zhipu AI 智谱 (GLM)             (default: glm-5.1)
+#   moonshot    — Moonshot Kimi                   (default: kimi-k2.6)
+#   zhipu       — Zhipu AI 智谱 (GLM)             (default: glm-5.1)
```

- [ ] **Step 2: Run `.env.example` regression test**

Run: `pytest tests/test_env_example.py -q`
Expected: all green. If a test pins old default strings in `.env.example`,
update it to match the new values.

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "$(cat <<'EOF'
docs(env): sync default-model comments to llm catalog modernization

Updates the supported-providers comment block with the new defaults
(deepseek-v4-flash, gpt-5.5, gemini-3-flash-preview, GLM-5,
qwen3.6-plus, glm-5.1, doubao-seed-2-0-pro-260215). Adds the
previously-missing moonshot entry.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Full regression sweep

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `pytest -q`
Expected: all green.

If anything fails:
1. Read the failure output carefully — most likely culprits are tests that
   pin old default-model strings (search the failing test for `gpt-5.4`,
   `deepseek-chat`, `qwen3-max`, `kimi-k2.5`, `glm-5"` (with closing quote
   to avoid `glm-5.1` matches), `gemini-2.5-flash`, or `Pro/MiniMaxAI/MiniMax-M2.5`).
2. Fix the assertion — generally by reading from `PROVIDER_PRESETS` rather
   than hard-coding the value.
3. Re-run the impacted file in isolation, then re-run the full suite.
4. **Do NOT amend earlier commits**. If a fix is needed, create a new
   commit.

- [ ] **Step 2: Verify no orphaned stale defaults remain**

Run each pattern separately so you can read each result:

```bash
cd /workspace/algorithm/zhouwg_project/OmicsClaw
for pattern in \
  'default.*gpt-5\.4' \
  'default.*deepseek-chat' \
  'default.*qwen3-max' \
  'default.*kimi-k2\.5' \
  'default.*glm-5"' \
  'default.*gemini-2\.5-flash'; do
  echo "=== ${pattern} ==="
  grep -RIn --include='*.py' --include='*.md' --include='.env*' \
    -E "${pattern}" omicsclaw/ .env.example 2>/dev/null \
    | grep -v -E '__pycache__|/build/'
done
```
Expected: only matches in the catalog itself (`omicsclaw/core/llm_models.py`
where these names are explicit non-default catalog entries) or in display
metadata where they're listed as alternative selectable models (not the
default first item). Anything outside those is a missed update.

- [ ] **Step 3: Verify newly added modules work**

Run a one-line smoke check:
```bash
python -c "
from omicsclaw.core.llm_models import resolve_model, all_short_names
from omicsclaw.core.llm_patches import apply_deepseek_reasoning_passback, discover_ollama_models
print('catalog size:', len(all_short_names()))
print('claude-opus-4-7:', resolve_model('anthropic', 'claude-opus-4-7'))
print('passback no-op on empty:', apply_deepseek_reasoning_passback([]))
print('ollama on bogus url:', discover_ollama_models('http://127.0.0.1:1'))
"
```
Expected: prints catalog size > 30, the ModelInfo for claude-opus-4-7
including `context_window=1000000`, an empty list for passback, and an
empty list for the bogus URL.

- [ ] **Step 4: Final commit if any test-fix patches were needed**

If Step 1 produced fixes, group them into one commit:

```bash
git add -A  # only after carefully reviewing 'git status' output first
git commit -m "$(cat <<'EOF'
test(llm): fix assertions pinning stale default models after catalog upgrade

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review Checklist (engineer)

Before reporting the work complete:

- [ ] Every task box above is checked
- [ ] `pytest -q` is fully green
- [ ] No `print()`, `breakpoint()`, or commented-out scaffolding remains
- [ ] `git log --oneline` shows clean per-task commits, no fixups in old commits
- [ ] Spec invariants hold:
  - I1: passing an unknown model still returns a usable ChatModel
  - I2: caller-supplied `thinking=` / `extra_body=` always wins
  - I3: passback only fires for `provider == "deepseek"`
  - I7: localhost base_url skips thinking/reasoning auto-config
- [ ] All 7 tasks have their commits in the same branch as the spec commit
