"""``omicsclaw/provider`` — the assembly point: config in, adapter out.

Plan 0026 §1. The layer exists so that switching or adding a backend never
touches loop logic, and that promise has one more hole in it than the
:class:`~omicsclaw.provider.base.LLMProvider` interface alone can close:
*somebody* still has to decide which adapter class to instantiate. If that
somebody is the Main Loop, the loop imports ``anthropic_provider`` by path
and hard-codes which preset names speak Messages — which is precisely the
coupling the interface was introduced to prevent, reintroduced one import
line lower down.

So the decision lives here, as the reference harness's ``NewFromEnv``
lives in its provider package: one unified assembly point that ``main``,
a sub-agent, and a benchmark runner all call instead of each growing its
own copy of the mapping.

The mapping itself is *data* — :data:`ADAPTERS`, keyed by
:class:`~omicsclaw.provider.config.ProviderDialect`, whose value for a
given preset is recorded on the preset itself (see
``ProviderPreset.dialect`` for why it belongs there rather than here). A
third backend is then a new adapter module, a new dialect member, and one
entry in this table; no branch in this file changes.

**Importing this module installs no SDK requirement.** Both adapters load
their vendor package inside their client factory, so naming their classes
here — and re-exporting them from the package — costs an import of two
stdlib-only modules and nothing else.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

from .anthropic_provider import AnthropicProvider
from .base import LLMProvider, ProviderError
from .config import ProviderConfig, ProviderDialect, dialect_for, resolve_config
from .openai_provider import OpenAIProvider

ADAPTERS: Mapping[ProviderDialect, Callable[[ProviderConfig], LLMProvider]] = (
    MappingProxyType(
        {
            ProviderDialect.OPENAI_CHAT: OpenAIProvider,
            ProviderDialect.ANTHROPIC_MESSAGES: AnthropicProvider,
        }
    )
)
"""Which adapter speaks which dialect. Read-only: a mutable registry would
let one import silently change what every later ``provider_for`` returns,
and the set of dialects is small, closed, and known at import time."""


def provider_for(
    config: ProviderConfig,
    *,
    dialect: ProviderDialect | None = None,
) -> LLMProvider:
    """Build the adapter that can talk to ``config``'s backend.

    The dialect is normally derived from ``config.provider`` through its
    preset. ``dialect`` overrides that, for the case the preset table
    cannot express: an operator pointing ``custom`` (or any unlisted name)
    at an Anthropic-compatible endpoint. Deriving it from the *model* name
    instead would be wrong in a way that is easy to reach — Claude resold
    through OpenRouter is a Chat Completions request whose model string
    says ``anthropic/``.

    An empty ``config.provider`` is not an error here. Nothing detected
    still leaves a usable configuration — ``resolve_config`` falls back to
    ``OPENAI_API_KEY`` and a default model — and that bare setup is the
    common one. A genuinely unconfigured environment fails at the wire
    with the backend's own authentication error, which says more than a
    guess made here could.

    No client is constructed and no vendor SDK is imported: the returned
    adapter builds its client on first use.
    """
    chosen = dialect_for(config.provider) if dialect is None else dialect
    build = ADAPTERS.get(chosen)
    if build is None:
        known = ", ".join(sorted(str(name) for name in ADAPTERS))
        raise ProviderError(
            f"no adapter speaks dialect {str(chosen)!r} — known dialects "
            f"are {known}",
            provider=config.provider,
        )
    return build(config)


def provider_from_env(
    provider: str = "",
    model: str = "",
    **kwargs: Any,
) -> LLMProvider:
    """The provider the environment implies, assembled in one call.

    :func:`~omicsclaw.provider.config.resolve_config` answers "what is
    configured"; this answers "what can I call". The signature is
    deliberately that of ``resolve_config`` — same positional arguments,
    same ``base_url`` / ``api_key`` / ``env`` keywords, same trailing
    :class:`~omicsclaw.provider.config.ProviderConfig` overrides — so the
    two are interchangeable at a call site and nothing has to learn a
    second set of parameter names::

        provider = provider_from_env()                     # detect
        provider = provider_from_env("anthropic")           # pin the backend
        titler = provider_from_env(model="claude-haiku-4-5", max_tokens=64)

    Pass ``env={...}`` to resolve against something other than
    ``os.environ``; that is what keeps this testable without mutating
    process state.
    """
    return provider_for(resolve_config(provider, model, **kwargs))


__all__ = ["ADAPTERS", "provider_for", "provider_from_env"]
