"""``omicsclaw.provider`` — the simultaneous interpreter.

Plan 0026, step 2 of the staged rebuild. One interface the Main Loop
programs against, so switching or adding an LLM backend never touches
loop logic::

    from omicsclaw.provider import LLMProvider, provider_from_env

    llm = provider_from_env()          # the backend the environment implies
    completion = await llm.generate(messages, tools)

:mod:`omicsclaw.schema` types go in, :mod:`omicsclaw.schema` types come
out, and every vendor-shaped field name lives and dies inside one adapter
module. See :mod:`omicsclaw.provider.base` for why the interface takes
only the conversation and the tools.

Singular ``provider``, alongside the existing plural
``omicsclaw.providers``, which stays live and untouched until the closing
migration task folds it in (plan 0026 §10). This package imports
``omicsclaw.schema`` and the standard library and nothing else, so the
two can coexist without a cycle.

The adapter classes are exported alongside the contract, and importing
them still requires neither vendor SDK: each loads its package inside its
own client factory, on the first call that needs a socket. A caller that
only wants "the provider my environment implies" should reach for
:func:`~omicsclaw.provider.factory.provider_from_env` and never name an
adapter class at all — that is the coupling this package exists to absorb.
"""

from ._model_limits import DEFAULT_MODEL_LIMITS, ModelLimits, get_model_limits
from .anthropic_provider import AnthropicProvider
from .base import Completion, LLMProvider, ProviderDeadlineExceeded, ProviderError
from .config import (
    DETECT_ORDER,
    PRESETS,
    ProviderConfig,
    ProviderDialect,
    ProviderPreset,
    ProviderTier,
    detect_provider_from_env,
    dialect_for,
    preset_for,
    resolve_config,
)
from .factory import provider_for, provider_from_env
from .openai_provider import OpenAIProvider

__all__ = [
    "DEFAULT_MODEL_LIMITS",
    "DETECT_ORDER",
    "PRESETS",
    "AnthropicProvider",
    "Completion",
    "LLMProvider",
    "ModelLimits",
    "OpenAIProvider",
    "ProviderConfig",
    "ProviderDeadlineExceeded",
    "ProviderDialect",
    "ProviderError",
    "ProviderPreset",
    "ProviderTier",
    "detect_provider_from_env",
    "dialect_for",
    "get_model_limits",
    "preset_for",
    "provider_for",
    "provider_from_env",
    "resolve_config",
]
