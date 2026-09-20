"""``omicsclaw/provider`` — where a model backend is configured.

Plan 0026 §4. The endpoint table in ``omicsclaw/providers/registry.py``
is the highest-value asset of the package this layer eventually replaces:
thirteen presets, their base URLs, their API-key environment variables,
and the order in which a key is auto-detected. That knowledge is copied
forward here, shed of the LangChain factory it was entangled with. The
old module stays live and untouched until the closing migration task.

Two shapes:

``ProviderPreset``
    Static per-vendor facts — endpoint, default model, key variable,
    curated model list. Data, never resolved.

``ProviderConfig``
    One *resolved* call configuration, frozen. It holds precisely what
    :class:`~omicsclaw.provider.base.LLMProvider`'s two hot-path methods
    deliberately refuse to take as parameters: model, temperature,
    ``max_tokens``, thinking budget, timeouts. An adapter is built from
    one and never mutates it; ``bind()`` is :meth:`ProviderConfig.with_overrides`
    plus a fresh adapter instance.

**Stdlib only.** ``providers/timeout.py``'s policy is ported as plain
numbers rather than as an ``httpx.Timeout``: this layer may not import a
transport library, so each adapter builds its own SDK timeout object out
of :attr:`ProviderConfig.timeout_seconds` and
:attr:`ProviderConfig.connect_timeout_seconds`. For the same reason an
unparseable environment value is silently replaced by its default here
rather than logged, as ``timeout.py`` does — a configuration module that
depends on logging setup is a module that cannot be imported early.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from ._model_limits import ModelLimits, get_model_limits
from .base import ProviderError


class ProviderTier(StrEnum):
    """How a backend is reached, which is what its failure modes follow."""

    PRIMARY = "primary"
    """The model vendor's own endpoint."""

    AGGREGATOR = "aggregator"
    """A gateway reselling other vendors' models under prefixed names."""

    LOCAL = "local"
    """Runs on this machine, or is an operator-supplied endpoint."""


class ProviderDialect(StrEnum):
    """The request grammar a backend speaks.

    The one fact that decides which adapter can talk to a backend, and so
    the datum :func:`~omicsclaw.provider.factory.provider_for` dispatches
    on. Note that it is *not* the same question as "whose model is this":
    OpenRouter resells Claude, and is still reached over Chat Completions.
    """

    OPENAI_CHAT = "openai_chat"
    """OpenAI's ``/chat/completions``, which twelve of the thirteen presets
    speak — the de-facto lingua franca of everything that is not Anthropic."""

    ANTHROPIC_MESSAGES = "anthropic_messages"
    """Anthropic's ``/v1/messages``: no system role, no tool role, tool
    arguments as objects. Only the ``anthropic`` preset speaks it."""


@dataclass(frozen=True, slots=True)
class ProviderPreset:
    """Everything known about one backend before a user configures it."""

    name: str
    base_url: str
    """Empty means "the SDK's own default", which is how ``openai`` is
    reached without hard-coding a URL that the vendor may move."""

    default_model: str
    api_key_env: str
    """Environment variable holding this vendor's key. Empty for backends
    that need none, which is also what makes them auto-detectable: a
    preset with no key variable can never win :data:`DETECT_ORDER`."""

    tier: ProviderTier
    display_name: str = ""
    models: tuple[str, ...] = ()
    """Curated model list for pickers. Not exhaustive and not a
    whitelist — a model absent from it still works if the backend has it."""

    dialect: ProviderDialect = ProviderDialect.OPENAI_CHAT
    """Which wire grammar this backend speaks, and therefore which adapter
    :func:`~omicsclaw.provider.factory.provider_for` builds for it.

    It lives *here*, on the preset, rather than in a lookup table beside
    the factory, because it is a static per-vendor fact of exactly the
    same kind as :attr:`base_url` and :attr:`api_key_env` — "SiliconFlow
    is reached over Chat Completions" is knowledge about SiliconFlow, not
    knowledge about the factory. A table beside the factory would be a
    second list of preset names kept in step with this one by hand, and
    the failure mode of forgetting an entry there is silent: a new preset
    would be dispatched to the majority adapter anyway, and only a 400
    from the wire would say so. A field cannot be forgotten in that way.

    Defaulted rather than required for the same reason the enum has a
    majority member: twelve of thirteen presets take the default, so
    spelling it out on each of them would be noise that hides the one
    preset where the value is the interesting part.
    """


PRESETS: Mapping[str, ProviderPreset] = MappingProxyType(
    {
        preset.name: preset
        for preset in (
            # --- Tier 1: primary providers ---------------------------------
            ProviderPreset(
                name="deepseek",
                base_url="https://api.deepseek.com",
                default_model="deepseek-v4-flash",
                api_key_env="DEEPSEEK_API_KEY",
                tier=ProviderTier.PRIMARY,
                display_name="DeepSeek",
                models=("deepseek-v4-flash", "deepseek-v4-pro"),
            ),
            ProviderPreset(
                name="openai",
                base_url="",
                default_model="gpt-5.5",
                api_key_env="OPENAI_API_KEY",
                tier=ProviderTier.PRIMARY,
                display_name="OpenAI",
                models=(
                    "gpt-5.5-pro",
                    "gpt-5.5",
                    "gpt-5.4",
                    "gpt-5.4-mini",
                    "gpt-5.3-codex",
                    "gpt-5",
                    "gpt-5-mini",
                ),
            ),
            ProviderPreset(
                name="anthropic",
                base_url="https://api.anthropic.com/v1/",
                default_model="claude-sonnet-4-6",
                api_key_env="ANTHROPIC_API_KEY",
                tier=ProviderTier.PRIMARY,
                display_name="Anthropic",
                dialect=ProviderDialect.ANTHROPIC_MESSAGES,
                models=(
                    "claude-opus-4-7",
                    "claude-opus-4-6",
                    "claude-sonnet-4-6",
                    "claude-sonnet-4-5",
                    "claude-haiku-4-5",
                ),
            ),
            ProviderPreset(
                name="gemini",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                default_model="gemini-3-flash-preview",
                api_key_env="GOOGLE_API_KEY",
                tier=ProviderTier.PRIMARY,
                display_name="Google Gemini",
                models=(
                    "gemini-3.1-pro-preview",
                    "gemini-3-flash-preview",
                    "gemini-2.5-pro",
                    "gemini-2.5-flash",
                ),
            ),
            ProviderPreset(
                name="nvidia",
                base_url="https://integrate.api.nvidia.com/v1",
                default_model="nvidia/nemotron-3-super-120b-a12b",
                api_key_env="NVIDIA_API_KEY",
                tier=ProviderTier.PRIMARY,
                display_name="NVIDIA NIM",
                models=(
                    "nvidia/nemotron-3-super-120b-a12b",
                    "deepseek-ai/deepseek-v3.2",
                    "moonshotai/kimi-k2.5",
                    "qwen/qwen3.5-397b-a17b",
                ),
            ),
            # --- Tier 2: third-party aggregators ---------------------------
            ProviderPreset(
                name="siliconflow",
                base_url="https://api.siliconflow.cn/v1",
                default_model="Pro/zai-org/GLM-5",
                api_key_env="SILICONFLOW_API_KEY",
                tier=ProviderTier.AGGREGATOR,
                display_name="SiliconFlow",
                models=(
                    "Pro/zai-org/GLM-5",
                    "Pro/MiniMaxAI/MiniMax-M2.5",
                    "Pro/moonshotai/Kimi-K2.5",
                    "Pro/zai-org/GLM-4.7",
                ),
            ),
            ProviderPreset(
                name="openrouter",
                base_url="https://openrouter.ai/api/v1",
                default_model="anthropic/claude-sonnet-4.6",
                api_key_env="OPENROUTER_API_KEY",
                tier=ProviderTier.AGGREGATOR,
                display_name="OpenRouter",
                models=(
                    "anthropic/claude-sonnet-4.6",
                    "anthropic/claude-opus-4.7",
                    "openai/gpt-5.5",
                    "openai/gpt-5.4",
                    "google/gemini-3.1-pro-preview",
                    "moonshotai/kimi-k2.6",
                    "minimax/minimax-m2.7",
                    "deepseek/deepseek-v4-pro",
                ),
            ),
            ProviderPreset(
                name="volcengine",
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                default_model="doubao-seed-2-0-pro-260215",
                api_key_env="VOLCENGINE_API_KEY",
                tier=ProviderTier.AGGREGATOR,
                display_name="Volcengine",
                models=(
                    "doubao-seed-2-0-pro-260215",
                    "doubao-seed-2-0-lite-260215",
                    "doubao-1.5-pro-256k",
                    "doubao-1.5-thinking-pro",
                ),
            ),
            ProviderPreset(
                name="dashscope",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                default_model="qwen3.6-plus",
                api_key_env="DASHSCOPE_API_KEY",
                tier=ProviderTier.AGGREGATOR,
                display_name="DashScope",
                models=(
                    "qwen3.6-plus",
                    "qwen3.7-max",
                    "qwen3-max",
                    "qwen3-coder-plus",
                    "qwen3-235b-a22b",
                    "qwq-plus",
                    "qwen3.5-flash",
                    "qwen-turbo-latest",
                ),
            ),
            ProviderPreset(
                name="moonshot",
                base_url="https://api.moonshot.cn/v1",
                default_model="kimi-k2.6",
                api_key_env="MOONSHOT_API_KEY",
                tier=ProviderTier.AGGREGATOR,
                display_name="Moonshot",
                models=("kimi-k2.6", "kimi-k2.5", "kimi-k2-thinking"),
            ),
            ProviderPreset(
                name="zhipu",
                base_url="https://open.bigmodel.cn/api/paas/v4",
                default_model="glm-5.1",
                api_key_env="ZHIPU_API_KEY",
                tier=ProviderTier.AGGREGATOR,
                display_name="Zhipu AI",
                models=("glm-5.1", "glm-5", "glm-5-turbo", "glm-4.7"),
            ),
            # --- Tier 3: local and custom ----------------------------------
            ProviderPreset(
                name="ollama",
                base_url="http://localhost:11434/v1",
                default_model="qwen2.5:7b",
                api_key_env="",
                tier=ProviderTier.LOCAL,
                display_name="Ollama",
                models=(
                    "qwen2.5:7b",
                    "qwen2.5:14b",
                    "qwen2.5:32b",
                    "qwen3:8b",
                    "llama3.3:70b",
                    "llama3.1:8b",
                    "gemma4:e2b",
                    "gemma4:e4b",
                    "gemma4:12b",
                    "gemma4:26b",
                    "gemma4:31b",
                    "deepseek-r1:7b",
                    "deepseek-r1:14b",
                    "deepseek-r1:32b",
                    "gemma3:12b",
                ),
            ),
            ProviderPreset(
                name="custom",
                base_url="",
                default_model="",
                api_key_env="",
                tier=ProviderTier.LOCAL,
                display_name="Custom Endpoint",
            ),
        )
    }
)

DETECT_ORDER: tuple[str, ...] = (
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
"""Order in which a bare API key in the environment picks the backend.

Ordered, not sorted: the first preset whose key variable is set wins, so
an operator with several keys present gets a stable, documented choice
instead of whichever one a dict happened to yield first. ``ollama`` and
``custom`` are absent because they have no key to detect.
"""

FALLBACK_MODEL = "deepseek-v4-flash"
"""Model of last resort when neither argument, environment, nor preset
names one. Matches the existing registry's behavior exactly."""

DEFAULT_TEMPERATURE = 0.3
"""The value every existing OmicsClaw call path already passes."""

DEFAULT_TIMEOUT_SECONDS = 120.0
"""Wall-clock ceiling for one model call.

``providers/timeout.py``'s existing default, kept deliberately. The
reference harness uses 600s (``LLM_REQUEST_TIMEOUT_SECS``), a value tuned
for unattended benchmark batches; adopting it here would quintuple how
long an interactive Surface sits on a hung connection before saying
anything. The harness's variable name is accepted as an alias so a
harness-shaped ``.env`` still configures something, but this repo's name
and default win.
"""

DEFAULT_CONNECT_TIMEOUT_SECONDS = 10.0
"""Separate from the total: a refused connection should fail fast even
when a long generation is allowed to run."""

DEFAULT_MAX_RETRIES = 5
"""Vendor-SDK retry count for 429 and 5xx, from the reference harness.

Higher than every SDK default (2) because rate limiting is the common
failure under batch use and the SDKs honor ``Retry-After``. Retries
cover errors before the first byte only; a stream dying mid-flight is the
Engine's problem, not this layer's.
"""

TIMEOUT_ENV_VARS = ("OMICSCLAW_LLM_TIMEOUT_SECONDS", "LLM_REQUEST_TIMEOUT_SECS")
CONNECT_TIMEOUT_ENV_VARS = ("OMICSCLAW_LLM_CONNECT_TIMEOUT_SECONDS",)
MAX_RETRIES_ENV_VARS = ("OMICSCLAW_LLM_MAX_RETRIES", "LLM_MAX_RETRIES")
"""First name wins. The repo-namespaced spelling is listed first in each
pair so this repo's own convention takes precedence over the harness's."""

MODEL_NORMALIZATION_EXEMPT_PROVIDERS: frozenset[str] = frozenset(
    {"custom", "ollama", "openrouter", "siliconflow", "nvidia"}
)
"""Backends with deliberately open model-identifier spaces. Rewriting a
model name for these would break a valid custom deployment."""

DEPRECATED_PROVIDER_DEFAULT_MODELS: Mapping[str, frozenset[str]] = MappingProxyType(
    {"deepseek": frozenset({"deepseek-chat", "deepseek-reasoner"})}
)
"""Models a vendor has retired. Left over in someone's ``.env``, they
produce a 404 that looks like an outage rather than stale config."""

_EMPTY_EXTRA: Mapping[str, Any] = MappingProxyType({})


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """One resolved model configuration — the whole of what a call needs.

    Frozen on purpose. An adapter holds one for its lifetime and
    ``bind()`` produces a new one, so two turns running concurrently
    against two binds of the same provider cannot observe each other's
    settings. Mutability here would make that a race with no obvious
    symptom.
    """

    provider: str
    """Preset key, e.g. ``"deepseek"``. Empty when nothing was resolved,
    which the adapter should treat as unconfigured rather than as a
    default — guessing a backend for an unset key hides the real problem."""

    model: str
    base_url: str = ""
    """Empty means "use the SDK default endpoint"."""

    api_key: str = ""
    """Never logged, never included in ``repr`` output by convention.
    Empty is legal: Ollama and other local endpoints need none."""

    max_tokens: int = 0
    """Output ceiling for one response. ``0`` means "unset" — use
    :attr:`max_output_tokens`, which substitutes the model's known
    ceiling. OpenAI-compatible endpoints may omit the parameter entirely;
    Anthropic's Messages API requires it, so its adapter must resolve it."""

    temperature: float = DEFAULT_TEMPERATURE
    thinking_budget_tokens: int = 0
    """Extended-thinking token budget. ``0`` disables it. Anthropic
    rejects a budget below 1024, which is the adapter's clamp to apply,
    not this record's — the config stores what was asked for."""

    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES

    extra: Mapping[str, Any] = field(default_factory=lambda: _EMPTY_EXTRA)
    """Vendor-specific knobs with no neutral meaning — ``reasoning_effort``,
    ``include_thoughts``, ``enable_thinking``, an OpenRouter
    ``include_reasoning`` flag. Deliberately untyped and deliberately
    ignored by every adapter but the one that understands the key, so
    adding a vendor feature never edits this dataclass."""

    @property
    def limits(self) -> ModelLimits:
        """Known context/output window for :attr:`model`."""
        return get_model_limits(self.model)

    @property
    def max_output_tokens(self) -> int:
        """:attr:`max_tokens` if set, else the model's known ceiling.

        What an adapter should send when the API demands a number.
        """
        return self.max_tokens if self.max_tokens > 0 else self.limits.output_tokens

    def with_overrides(self, **overrides: Any) -> ProviderConfig:
        """Copy-on-write, the mechanism behind ``LLMProvider.bind``.

        Rejects unknown field names instead of silently dropping them: a
        typo'd ``max_token=`` that quietly did nothing would surface much
        later as an unexplained cost or truncation.
        """
        unknown = sorted(set(overrides) - set(ProviderConfig.__dataclass_fields__))
        if unknown:
            known = ", ".join(sorted(ProviderConfig.__dataclass_fields__))
            raise ProviderError(
                f"unknown provider configuration field(s): {', '.join(unknown)}"
                f" — known fields are {known}",
                provider=self.provider,
            )
        return replace(self, **overrides)


def preset_for(provider: str) -> ProviderPreset | None:
    """Look up a preset by name, case- and whitespace-insensitively."""
    return PRESETS.get(str(provider or "").strip().lower())


def dialect_for(provider: str) -> ProviderDialect:
    """Which wire grammar ``provider`` speaks.

    An unknown name — a self-hosted gateway, a preset that does not exist,
    or the empty string a wholly unconfigured environment resolves to —
    is answered with :attr:`ProviderDialect.OPENAI_CHAT` rather than with
    an error. That dialect is what a backend nobody has classified almost
    always turns out to speak, and refusing to answer would make a working
    custom endpoint unreachable through the factory purely for want of a
    preset. A caller that knows better passes the dialect explicitly to
    :func:`~omicsclaw.provider.factory.provider_for`.
    """
    preset = preset_for(provider)
    return preset.dialect if preset is not None else ProviderDialect.OPENAI_CHAT


def _first_env(source: Mapping[str, str], *names: str) -> str:
    for name in names:
        value = str(source.get(name, "") or "").strip()
        if value:
            return value
    return ""


def _env_float(source: Mapping[str, str], default: float, *names: str) -> float:
    """Positive floats only; anything else falls back to ``default``.

    A zero or negative timeout is not a faster timeout, it is an
    immediately-failing client, so an obvious typo must not be honored.
    """
    raw = _first_env(source, *names)
    if not raw:
        return float(default)
    try:
        value = float(raw)
    except ValueError:
        return float(default)
    return value if value > 0 else float(default)


def _env_int(source: Mapping[str, str], default: int, *names: str) -> int:
    """Non-negative integers only. ``0`` is meaningful — it disables retries."""
    raw = _first_env(source, *names)
    if not raw:
        return int(default)
    try:
        value = int(raw)
    except ValueError:
        return int(default)
    return value if value >= 0 else int(default)


def detect_provider_from_env(
    *,
    env: Mapping[str, str] | None = None,
    detect_order: tuple[str, ...] = DETECT_ORDER,
) -> str:
    """Name the backend the environment implies, or ``""``.

    An explicit ``LLM_PROVIDER`` short-circuits everything; otherwise the
    first preset in ``detect_order`` whose key variable is populated wins.
    """
    source = os.environ if env is None else env
    requested = str(source.get("LLM_PROVIDER", "") or "").strip().lower()
    if requested:
        return requested

    for name in detect_order:
        preset = PRESETS.get(name)
        if preset is not None and preset.api_key_env and source.get(preset.api_key_env):
            return name
    return ""


def normalize_model_for_provider(
    provider: str, model: str, *, base_url: str = ""
) -> str:
    """Repair a model name left over from a different backend.

    Switching ``LLM_PROVIDER`` without also updating ``OMICSCLAW_MODEL``
    is the single most common misconfiguration, and it fails as a 404 that
    reads like an outage. Deliberately conservative — it rewrites only
    when the name is *exactly* another preset's default (or a model the
    vendor has retired), never for open-identifier backends, and never
    when a custom ``base_url`` says the user knows what they are doing.
    """
    key = str(provider or "").strip().lower()
    candidate = str(model or "").strip()
    if not key or not candidate:
        return candidate
    if str(base_url or "").strip() or key in MODEL_NORMALIZATION_EXEMPT_PROVIDERS:
        return candidate

    current = PRESETS.get(key)
    if current is None or not current.default_model:
        return candidate
    if candidate == current.default_model:
        return candidate

    for deprecated in DEPRECATED_PROVIDER_DEFAULT_MODELS.values():
        if candidate in deprecated:
            return current.default_model
    for other in PRESETS.values():
        if other.name != key and candidate == other.default_model:
            return current.default_model
    return candidate


def resolve_config(
    provider: str = "",
    model: str = "",
    *,
    base_url: str = "",
    api_key: str = "",
    env: Mapping[str, str] | None = None,
    **overrides: Any,
) -> ProviderConfig:
    """Build a :class:`ProviderConfig` from arguments, environment, presets.

    Priority, ported verbatim from ``providers/registry.resolve_provider``:

    1. explicit arguments
    2. provider-scoped environment (``DEEPSEEK_BASE_URL``, …)
    3. auto-detection from a provider-specific API key
    4. the generic ``LLM_*`` / ``OMICSCLAW_*`` variables
    5. the preset

    The generic variables apply only when they plausibly describe the
    backend in play — the environment names this provider, nothing was
    requested at all, or the caller asked for ``custom``. Without that
    guard, a ``LLM_BASE_URL`` left set for one vendor silently hijacks an
    explicit request for another.

    ``**overrides`` are applied last, so a caller can pin ``max_tokens``
    or ``temperature`` without a second call.
    """
    source = os.environ if env is None else env
    requested = str(provider or "").strip().lower()
    key = requested
    resolved_key = str(api_key or "")

    env_provider = _first_env(source, "LLM_PROVIDER", "OMICSCLAW_PROVIDER").lower()

    if not key and not resolved_key:
        key = detect_provider_from_env(env=source)
        detected = PRESETS.get(key)
        if detected is not None and detected.api_key_env:
            resolved_key = str(source.get(detected.api_key_env, "") or "")

    preset = PRESETS.get(key)
    generic_applies = (
        (bool(env_provider) and env_provider == key)
        or (not key and not requested)
        or (requested == "custom" and not env_provider)
    )

    scoped_base_url = (
        str(source.get(f"{key.upper()}_BASE_URL", "") or "") if key else ""
    )
    generic_base_url = (
        _first_env(source, "LLM_BASE_URL", "OMICSCLAW_BASE_URL")
        if generic_applies
        else ""
    )
    env_base_url = scoped_base_url or generic_base_url
    env_model = (
        _first_env(source, "OMICSCLAW_MODEL", "LLM_MODEL", "SPATIALCLAW_MODEL")
        if generic_applies
        else ""
    )

    resolved_url = str(base_url or env_base_url or (preset.base_url if preset else ""))
    resolved_model = str(
        model or env_model or (preset.default_model if preset else "") or FALLBACK_MODEL
    )
    resolved_model = normalize_model_for_provider(
        key, resolved_model, base_url=base_url or env_base_url
    )

    if not resolved_key and preset is not None and preset.api_key_env:
        resolved_key = str(source.get(preset.api_key_env, "") or "")
    if not resolved_key and generic_applies:
        resolved_key = _first_env(source, "LLM_API_KEY", "OMICSCLAW_API_KEY")
    if not resolved_key and key in {"", "openai"}:
        # The historical fallback: OPENAI_API_KEY is what most
        # OpenAI-compatible tooling sets, including for third-party
        # endpoints, so it stands in when nothing more specific exists.
        resolved_key = str(source.get("OPENAI_API_KEY", "") or "")

    config = ProviderConfig(
        provider=key,
        model=resolved_model,
        base_url=resolved_url,
        api_key=resolved_key,
        timeout_seconds=_env_float(source, DEFAULT_TIMEOUT_SECONDS, *TIMEOUT_ENV_VARS),
        connect_timeout_seconds=_env_float(
            source, DEFAULT_CONNECT_TIMEOUT_SECONDS, *CONNECT_TIMEOUT_ENV_VARS
        ),
        max_retries=_env_int(source, DEFAULT_MAX_RETRIES, *MAX_RETRIES_ENV_VARS),
    )
    return config.with_overrides(**overrides) if overrides else config


__all__ = [
    "DEFAULT_CONNECT_TIMEOUT_SECONDS",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_TEMPERATURE",
    "DEFAULT_TIMEOUT_SECONDS",
    "DETECT_ORDER",
    "FALLBACK_MODEL",
    "PRESETS",
    "ProviderConfig",
    "ProviderDialect",
    "ProviderPreset",
    "ProviderTier",
    "detect_provider_from_env",
    "dialect_for",
    "normalize_model_for_provider",
    "preset_for",
    "resolve_config",
]
