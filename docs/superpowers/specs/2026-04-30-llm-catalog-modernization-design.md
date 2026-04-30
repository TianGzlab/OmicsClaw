# LLM Catalog Modernization Design

**Date**: 2026-04-30
**Status**: Approved (brainstorming complete)
**Reference**: `/workspace/algorithm/zhouwg_project/repo_learn/EvoScientist/EvoScientist/llm/`

## Problem

OmicsClaw's LLM provider layer has three independent gaps relative to current
mainstream support:

1. **Stale model catalog** — `omicsclaw/core/provider_registry.py` lists
   provider models inline as tuples; the entries lag the current state of the
   art (no `claude-opus-4-7`, `gpt-5.5(-pro)`, `qwen3.6-plus`, `kimi-k2.6`,
   `deepseek-v4-pro/flash`, `gemini-3-flash`, `glm-5.1`).
2. **No model→context-window table** — context-compaction triggers default to
   conservative caps (e.g. 170K) instead of the true 1M for Claude / Qwen3.6 /
   DeepSeek-V4 / Doubao-Seed-2 / GPT-5.5.
3. **No per-model auto thinking/reasoning defaults** — every caller in the
   autoagent / pipeline code paths must hand-roll thinking budgets and
   reasoning effort. DeepSeek thinking-mode multi-turn is also broken because
   `reasoning_content` is not preserved across turns (HTTP 400 in production).

EvoScientist's `EvoScientist/llm/` package solves the same set of problems
through a model registry, a context-window patch table, per-model auto-config,
and a small set of runtime patches. We selectively port what applies to
OmicsClaw without taking a hard dependency on EvoScientist.

## Non-Goals

- Replace the existing `provider_registry` / `provider_runtime` /
  `ccproxy_manager` modules. They stay as-is; the new module sits beside them.
- Unify the three current LLM call paths (`get_langchain_llm`,
  `autoagent.llm_client`, `routing.llm_router`) onto a single `init_chat_model`
  entry point. That refactor delivers no user-visible value and would force a
  large diff. The three paths consume the new catalog opportunistically.
- Port EvoScientist's full patch set:
  - **OpenRouter `reasoning_details` patch** — N/A (OmicsClaw does not depend
    on `langchain-openrouter`; it routes OpenRouter through `ChatOpenAI` with
    a `base_url` override).
  - **ccproxy SystemMessage→developer patch** — not currently a known issue in
    OmicsClaw's ccproxy flow.
  - **`lazy_loader.attach`** in package `__init__` — OmicsClaw does not use
    `lazy_loader`; introducing it is out of scope.
- Port providers OmicsClaw does not currently expose:
  - `minimax` (Anthropic-compatible direct endpoint)
  - `kimi-coding` (Anthropic-compatible direct endpoint)

## Architecture

### Files added / modified

```
omicsclaw/core/
  llm_models.py          [NEW]      ~250 LOC  Static catalog + lookups (no side effects)
  llm_patches.py         [NEW]      ~150 LOC  Runtime patches (explicit apply)
  provider_registry.py   [MODIFY]   ~50 LOC   Default-model bumps; consume llm_models in get_langchain_llm

omicsclaw/autoagent/
  llm_client.py          [MODIFY]   ~30 LOC   Apply DeepSeek reasoning_content passback when provider=="deepseek"

omicsclaw/routing/
  llm_router.py          [MODIFY]   ~5 LOC    Fallback model bump

.env.example             [MODIFY]   ~10 LOC   Sync default-model comment block

tests/
  test_llm_models.py                   [NEW]
  test_llm_patches.py                  [NEW]
  test_provider_registry_defaults.py   [NEW]
  test_autoagent_llm_client_deepseek.py [NEW]
```

Total: ~400 LOC added, ~85 LOC modified.

### Module contracts

| Module | Input | Output | Dependencies |
|---|---|---|---|
| `llm_models.py` | provider name, model short-name or full ID | `ModelInfo(model_id, provider, context_window, default_features)` | none |
| `llm_patches.py` | message list / base URL | wrapped messages, model list | `httpx` (already a dep) |
| `provider_registry.py` (modified) | provider/model/api_key/base_url | LangChain ChatModel; `ResolvedConfig` (unchanged surface) | `llm_models` (optional consumer) |
| `autoagent/llm_client.py` (modified) | directive + system_prompt | LLM text response | `provider_runtime` + `llm_patches` (only when `deepseek`) |
| `routing/llm_router.py` (modified) | query + skills | `(skill_name, confidence)` | `provider_registry` |

### `llm_models.py` public API

```python
@dataclass(frozen=True)
class ModelInfo:
    short_name: str                  # alias used by users (e.g. "claude-opus-4-7")
    model_id: str                    # what gets sent to the API
    provider: str                    # OmicsClaw canonical provider name
    context_window: int | None       # None = unknown — caller falls back
    default_features: dict[str, Any] # {} = nothing to inject

def resolve_model(provider: str, model: str) -> ModelInfo: ...
def get_context_window(model: str) -> int | None: ...
def get_default_features(provider: str, model: str, *, base_url: str = "") -> dict[str, Any]: ...
def list_models_for_provider(provider: str) -> list[ModelInfo]: ...
def all_short_names() -> list[str]: ...
```

### Catalog content

#### `MODEL_CATALOG` — `(short_name, model_id, provider)` registry

Provider coverage matches OmicsClaw's existing 12 `PROVIDER_PRESETS` entries:
`anthropic, openai, gemini, nvidia, siliconflow, openrouter, volcengine,
dashscope, moonshot, zhipu, deepseek, ollama` (+ `custom` which is identity-passthrough).

```python
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
    ("nemotron-super",   "nvidia/nemotron-3-super-120b-a12b", "nvidia"),
    ("deepseek-v3.2",    "deepseek-ai/deepseek-v3.2",         "nvidia"),
    ("kimi-k2.5",        "moonshotai/kimi-k2.5",              "nvidia"),
    ("qwen3.5-397b",     "qwen/qwen3.5-397b-a17b",            "nvidia"),
    # siliconflow
    ("minimax-m2.5",  "Pro/MiniMaxAI/MiniMax-M2.5", "siliconflow"),
    ("glm-5",         "Pro/zai-org/GLM-5",          "siliconflow"),
    ("kimi-k2.5",     "Pro/moonshotai/Kimi-K2.5",   "siliconflow"),
    ("glm-4.7",       "Pro/zai-org/GLM-4.7",        "siliconflow"),
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
```

#### `_KNOWN_MODEL_CONTEXT_WINDOWS` (exact-match overrides)

```python
{
    "qwen3.6-27b":      262_000,
    "qwen3.6-35b-a3b":  262_000,
    "claude-haiku-4-5": 200_000,
}
```

#### `_KNOWN_MODEL_FAMILIES` (substring fallback, first match wins)

```python
[
    ("claude-",       1_000_000),  # via context-1m beta header
    ("gpt-5.5",       1_050_000),
    ("kimi-k2",         262_000),
    ("glm-5",           203_000),
    ("deepseek-v4",   1_050_000),
    ("qwen3.6",       1_000_000),
    ("doubao-seed-2", 1_000_000),
]
```

#### `get_default_features` rules

| provider condition | model pattern | injected fields |
|---|---|---|
| `anthropic`, `base_url` not localhost/127.0.0.1 | `claude-*-4-6`, `claude-*-4-7` | `thinking={"type": "adaptive"}` |
| `anthropic`, `base_url` not localhost | other `claude-*` | `thinking={"type": "enabled", "budget_tokens": 10000}` |
| `anthropic`, `base_url` is localhost (ccproxy) | * | `{}` (no thinking — ccproxy 422 risk) |
| `openai`, `base_url` not localhost | `5.4` / `5.5` / `codex` substrings | `extra_body={"reasoning_effort": "xhigh"}` |
| `openai`, `base_url` not localhost | other | `extra_body={"reasoning_effort": "high"}` |
| `openai`, `base_url` is localhost (ccproxy Codex) | * | `{}` |
| `gemini` | * | `extra_body={"include_thoughts": True}` |
| `ollama` | * | `extra_body={"reasoning": True}` |
| `siliconflow` | * | `extra_body={"enable_thinking": False}` |
| any other | * | `{}` |

> **Note on `reasoning_effort`**: OmicsClaw's `provider_registry.get_langchain_llm`
> uses `langchain-openai`'s `ChatOpenAI` with a `base_url` override. The `xhigh`
> string used by EvoScientist is OpenAI-Responses-API specific (via `reasoning={...}`).
> For OmicsClaw's Chat Completions path we send the equivalent through
> `extra_body.reasoning_effort` per OpenAI's reasoning-effort spec — values are
> `low|medium|high|max`, mapped from EvoScientist's `xhigh` to `max`.

### Default-model upgrade table (`PROVIDER_PRESETS`)

| provider | current default | upgraded to | rationale |
|---|---|---|---|
| `openai` | `gpt-5.4` | `gpt-5.5` | flagship-tier rotation |
| `anthropic` | `claude-sonnet-4-6` | **unchanged** | sonnet stays balanced; opus-4-7 is ~4× token cost — let users opt in |
| `gemini` | `gemini-2.5-flash` | `gemini-3-flash-preview` | within-family bump (model_id form, not short_name `gemini-3-flash`) |
| `nvidia` | `nvidia/nemotron-3-super-120b-a12b` | **unchanged** | already current SKU |
| `siliconflow` | `Pro/MiniMaxAI/MiniMax-M2.5` | `Pro/zai-org/GLM-5` | GLM-5 / 203K is more general-purpose |
| `openrouter` | `anthropic/claude-sonnet-4.6` | **unchanged** | already current |
| `volcengine` | `doubao-seed-2-0-pro-260215` | **unchanged** | already current |
| `dashscope` | `qwen3-max` | `qwen3.6-plus` | 3.6 series shipped |
| `moonshot` | `kimi-k2.5` | `kimi-k2.6` | within-family bump |
| `zhipu` | `glm-5` | `glm-5.1` | 5.1 GA |
| `deepseek` | `deepseek-chat` | `deepseek-v4-flash` | v4 series shipped |
| `ollama` | `qwen2.5:7b` | **unchanged** | local; user-driven |
| `custom` | `""` | **unchanged** | identity passthrough |

### Data flow

#### Path 1: `agents/pipeline.py` → `core/provider_registry.get_langchain_llm`

```text
caller(provider="anthropic", model="claude-opus-4-7", ...)
  → resolve_provider() → (base_url, "claude-opus-4-7", api_key)
  → llm_models.resolve_model("anthropic", "claude-opus-4-7")
      ⇒ ModelInfo(model_id="claude-opus-4-7", context_window=1_000_000,
                  default_features={"thinking": {"type": "adaptive"}})
  → llm_models.get_default_features("anthropic", "claude-opus-4-7",
                                     base_url=resolved_url)
      ⇒ thinking config (or {} if base_url is localhost ccproxy)
  → kwargs.setdefault("thinking", default_features["thinking"]) etc
  → ChatAnthropic(**kwargs)
  → llm_patches.apply_known_context_window(chat_model, info.context_window)
```

#### Path 2: `autoagent/llm_client.call_llm` → raw OpenAI SDK

```text
caller(directive, system_prompt)
  → resolve_provider_runtime() → ResolvedProviderRuntime
  → messages = [system, user]
  → if runtime.provider == "deepseek":
        messages = llm_patches.apply_deepseek_reasoning_passback(messages)
  → extra_body = llm_models.get_default_features(
                     runtime.provider, runtime.model,
                     base_url=runtime.base_url
                 ).get("extra_body", {})
  → client.chat.completions.create(..., extra_body=extra_body)
```

#### Path 3: `routing/llm_router.route_with_llm` → raw HTTP

Single-shot, no thinking/reasoning needed. Only the fallback model string in
`_resolve_llm_config` updates: `"gpt-4o-mini"` → `"gpt-5-mini"`.

#### Path 4 (optional): `omicsclaw onboard` → `discover_ollama_models`

When the wizard reaches the Ollama provider step, it calls
`llm_patches.discover_ollama_models(base_url)` and presents the returned model
list. If Ollama is unreachable, the helper returns `[]` and the wizard falls
back to free-text input. Wiring is out-of-scope deltas listed in the
implementation plan but won't be a hard dependency for the catalog work.

## Invariants

| # | Invariant | Enforced at |
|---|---|---|
| I1 | Catalog never breaks unknown model IDs | `resolve_model()` returns empty `ModelInfo` (model_id=input, ctx=None, features={}) |
| I2 | `default_features` never overwrites caller-supplied fields | All consumers use `dict.setdefault` / `kwargs.pop("X", None) or default` |
| I3 | DeepSeek passback only fires when `provider == "deepseek"` | autoagent `if` guard |
| I4 | `llm_models.py` never raises into callers | Internal try/except → empty `ModelInfo` |
| I5 | `discover_ollama_models()` never raises | Inherited from EvoScientist semantics |
| I6 | Same short-name across providers requires `provider` arg | `resolve_model()` is `(provider, model)` keyed |
| I7 | ccproxy localhost endpoints opt out of thinking/reasoning auto-config | `base_url` 127.0.0.1/localhost check in `get_default_features` |

## Edge cases

| scenario | behavior |
|---|---|
| User passes full model_id (`claude-opus-4-7-20251201`) | `resolve_model` misses → empty `ModelInfo`. `get_context_window` family-substring still hits `claude-` → 1M. `get_default_features` substring also hits 4-7 pattern. |
| `provider == "custom"` | empty `ModelInfo`, empty default features — full passthrough |
| `provider == "ollama"` | `extra_body={"reasoning": True}` always injected; non-reasoning models silently ignore the param |
| `anthropic` + ccproxy OAuth (`base_url == "http://127.0.0.1:.../claude"`) | thinking skipped (avoids 422) |
| `openai` + ccproxy Codex | reasoning_effort skipped |
| DeepSeek multi-turn + history from another provider lacks `reasoning_content` | `apply_deepseek_reasoning_passback` injects `reasoning_content=""` (DeepSeek non-thinking endpoints empirically tolerate empty string) |
| Caller already passed `extra_body={"thinking": {...}}` | I2 — no overwrite |
| Same `short_name` in catalog under two providers (e.g. `kimi-k2.5` in `moonshot` and `siliconflow`) | `resolve_model` is `(provider, model)`-keyed; ambiguity impossible |

## Relationship to existing `app/server.py:_build_thinking_extra_body`

`server.py` normalizes user-facing thinking control (frontend "adaptive" →
provider-specific shape) when the API server receives a request. The new
`get_default_features` works in the **opposite** direction — it's used by
backend code paths (autoagent / pipeline) that originate LLM calls themselves
and need a per-model recommended default. The two are orthogonal and never
both touch the same `extra_body` field for a given call.

## Test plan

### New test files

**`tests/test_llm_models.py`**
- `test_resolve_model_known_short_name`
- `test_resolve_model_unknown_falls_back`
- `test_resolve_model_provider_disambiguation`
- `test_get_context_window_exact_match`
- `test_get_context_window_family_match`
- `test_get_context_window_unknown`
- `test_get_default_features_anthropic_4_6`
- `test_get_default_features_anthropic_legacy`
- `test_get_default_features_openai_5_5`
- `test_get_default_features_ccproxy_skips_thinking`
- `test_get_default_features_ccproxy_skips_reasoning`
- `test_get_default_features_unknown_provider`
- `test_default_features_no_overwrite`
- `test_list_models_for_provider`
- `test_all_short_names_unique_when_dedup`

**`tests/test_llm_patches.py`**
- `test_deepseek_passback_injects_empty_when_missing`
- `test_deepseek_passback_preserves_existing_reasoning_content`
- `test_deepseek_passback_skips_user_and_system_messages`
- `test_deepseek_passback_idempotent`
- `test_ollama_discover_returns_models_on_200`
- `test_ollama_discover_returns_empty_on_connection_error`
- `test_ollama_discover_returns_empty_on_404`
- `test_ollama_discover_handles_malformed_json`
- `test_ollama_discover_no_url_returns_empty`

**`tests/test_provider_registry_defaults.py`**
- `test_default_models_match_spec` — table-driven, asserts every row of the
  upgrade table.
- `test_catalog_consistency` — every `PROVIDER_PRESETS` default model
  resolves through `llm_models` *or* belongs to `{ollama, custom}`.
- `test_get_langchain_llm_anthropic_passes_default_features` — mocks
  `ChatAnthropic` and asserts `thinking` is set.
- `test_get_langchain_llm_openai_passes_extra_body` — mocks `ChatOpenAI`
  and asserts `extra_body.reasoning_effort` is set.
- `test_get_langchain_llm_caller_thinking_overrides_default` — I2.
- `test_get_langchain_llm_ccproxy_localhost_skips_thinking` — I7.

**`tests/test_autoagent_llm_client_deepseek.py`**
- `test_deepseek_provider_applies_passback` — monkeypatches
  `llm_patches.apply_deepseek_reasoning_passback` and asserts called with
  the messages list.
- `test_non_deepseek_provider_skips_passback` — assert patch not called.
- `test_deepseek_extra_body_from_catalog` — assert `extra_body` is passed.

### Existing tests requiring update

| file | change |
|---|---|
| `tests/test_provider_registry.py` | sync default-model assertions to spec table |
| `tests/test_pipeline_provider_resolution.py` | sync default-model assertions |
| `tests/test_autoagent_llm_client.py` | unchanged behavior under default (non-deepseek) provider; existing assertions hold |

### Verification

- All tests are mock-based; no live network calls. No new test dependencies.

## Implementation order

| step | file | scope | gate |
|---|---|---|---|
| **S1** | `omicsclaw/core/llm_models.py` (new) | catalog + context window + default features + `ModelInfo` | `pytest tests/test_llm_models.py -q` |
| **S2** | `omicsclaw/core/llm_patches.py` (new) | DeepSeek passback + ollama discovery | `pytest tests/test_llm_patches.py -q` |
| **S3** | `omicsclaw/core/provider_registry.py` (modify) | upgrade `PROVIDER_PRESETS` defaults; expand `PROVIDER_DISPLAY_METADATA.models`; have `get_langchain_llm` consume catalog | `pytest tests/test_provider_registry*.py tests/test_pipeline_provider_resolution.py -q` |
| **S4** | `omicsclaw/autoagent/llm_client.py` (modify) | guard call to passback when provider == deepseek; opportunistic `extra_body` from catalog | `pytest tests/test_autoagent_llm_client*.py -q` |
| **S5** | `omicsclaw/routing/llm_router.py` (modify) | bump fallback model | `pytest tests/test_keyword_routing.py tests/test_auto_routing_disambiguation.py -q` |
| **S6** | `.env.example` (modify) | sync the per-provider default-model comment block | (doc only — no test) |
| **S7** | full regression | `pytest -q` whole suite | red lights cause immediate rollback of the offending step |

Each step is independently reviewable and revertible. S1/S2 are pure
additions (zero blast radius). S3 is the highest-risk step because it
modifies the most-imported module and has the largest test footprint.

## Risks and mitigations

| risk | likelihood | impact | mitigation |
|---|---|---|---|
| Default-model bump breaks user .env files that pinned the old default | low | low | Old defaults still resolve via `resolve_provider` — the bump only changes what users get when they leave the field blank. Documented in commit message. |
| `extra_body.reasoning_effort` not accepted by some OpenAI-compatible gateways | medium | low | Already handled by OmicsClaw's existing `SanitizedChatOpenAI` patch (drops unknown fields server-side errors); plus `extra_body` is opt-in at provider level — gateways without reasoning support can still ignore. Add an env flag `OMICSCLAW_DISABLE_AUTO_REASONING=1` if a regression surfaces. |
| Catalog drifts from upstream model availability | high (always) | low | Catalog is a single Python list — easy to update. No dynamic lookup. |
| DeepSeek passback breaks non-thinking DeepSeek models | low | medium | Empty-string fallback empirically tolerated by both endpoints in EvoScientist's history; failure mode is HTTP 400 caught by autoagent's existing retry+raise wrapper. |

## Open questions

None at design time. All scope decisions resolved during brainstorming:
- Default upgrade policy: option (b), with `anthropic` carve-out
- Patches scope: DeepSeek + ollama discovery; skip OpenRouter / ccproxy /
  system→developer
- Module placement: `omicsclaw/core/llm_models.py` (single new module),
  `omicsclaw/core/llm_patches.py` (single new patches module)
- Three LLM call paths stay separate
