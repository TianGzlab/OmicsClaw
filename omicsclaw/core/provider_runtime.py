"""Shared provider runtime state and resolution helpers.

This module keeps a lightweight snapshot of the active OmicsClaw provider
runtime so non-chat flows can reuse the same credentials and endpoint without
having to re-read environment variables or duplicate provider-switch logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from omicsclaw.core.provider_registry import (
    PROVIDER_PRESETS,
    detect_provider_from_env,
    resolve_provider,
)
# OAuth identity lives in ccproxy_manager (the only module that actually
# runs ccproxy). provider_runtime just needs the two small helpers to
# rewrite base_url / validate provider support when auth_mode="oauth".
from omicsclaw.core.ccproxy_manager import (
    oauth_base_url,
    provider_supports_oauth,
)

# Default port used when ``auth_mode="oauth"`` but no explicit port is given.
# Kept in sync with ``omicsclaw.core.ccproxy_manager.DEFAULT_CCPROXY_PORT``.
# Deliberately avoids 8765 (OmicsClaw app-server default) to prevent the
# ccproxy subprocess from trying to bind the same port as the app-server.
DEFAULT_CCPROXY_PORT: int = 11435

# Sentinel API key that tells downstream OpenAI/Anthropic SDK clients the
# request is routed through ccproxy (which supplies real OAuth tokens).
_OAUTH_SENTINEL_KEY: str = "ccproxy-oauth"


@dataclass(frozen=True)
class ProviderRuntimeConfig:
    provider: str = ""
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    auth_mode: str = "api_key"  # "api_key" | "oauth"
    ccproxy_port: int = DEFAULT_CCPROXY_PORT


@dataclass(frozen=True)
class ResolvedProviderRuntime(ProviderRuntimeConfig):
    source: str = ""


_ACTIVE_PROVIDER_RUNTIME: ProviderRuntimeConfig | None = None


def _normalize_provider_name(provider: str = "") -> str:
    return str(provider or "").strip().lower()


def _match_provider_from_base_url(base_url: str = "") -> str:
    normalized = str(base_url or "").strip()
    if not normalized:
        return ""

    for provider_name, (preset_url, _, _) in PROVIDER_PRESETS.items():
        if preset_url and preset_url.rstrip("/") in normalized.rstrip("/"):
            return provider_name
    return "custom"


def infer_provider_name(
    *,
    provider: str = "",
    base_url: str = "",
    env: Mapping[str, str] | None = None,
) -> str:
    """Infer the effective provider name for a resolved config."""
    normalized = _normalize_provider_name(provider)
    if normalized:
        return normalized

    matched = _match_provider_from_base_url(base_url)
    if matched:
        return matched

    detected = detect_provider_from_env(env=env)
    if detected:
        return detected

    return "openai"


def provider_requires_api_key(provider: str) -> bool:
    """Return whether the provider normally requires an API key."""
    return _normalize_provider_name(provider) != "ollama"


def _normalize_api_key_for_client(
    provider: str,
    api_key: str,
    auth_mode: str = "api_key",
) -> str:
    resolved_key = str(api_key or "").strip()
    if resolved_key:
        return resolved_key
    if (
        str(auth_mode or "").strip().lower() == "oauth"
        and provider_supports_oauth(provider)
    ):
        return _OAUTH_SENTINEL_KEY
    if not provider_requires_api_key(provider):
        return "omicsclaw-local"
    return ""


def clear_active_provider_runtime() -> None:
    global _ACTIVE_PROVIDER_RUNTIME
    _ACTIVE_PROVIDER_RUNTIME = None


def set_active_provider_runtime(
    *,
    provider: str = "",
    base_url: str = "",
    model: str = "",
    api_key: str = "",
    auth_mode: str = "api_key",
    ccproxy_port: int = DEFAULT_CCPROXY_PORT,
) -> ProviderRuntimeConfig:
    """Persist the active provider runtime snapshot.

    When ``auth_mode == "oauth"`` and the provider is OAuth-capable
    (Claude / OpenAI), the ``base_url`` is overridden with the local
    ccproxy endpoint and ``api_key`` is set to the ccproxy sentinel value
    — downstream callers (``AsyncOpenAI``, ``get_langchain_llm``) then
    transparently route through ccproxy with no code changes.
    """
    global _ACTIVE_PROVIDER_RUNTIME

    normalized_provider = _normalize_provider_name(provider)
    normalized_auth_mode = str(auth_mode or "api_key").strip().lower() or "api_key"
    resolved_base_url = str(base_url or "").strip()
    resolved_api_key = str(api_key or "").strip()

    if (
        normalized_auth_mode == "oauth"
        and provider_supports_oauth(normalized_provider)
    ):
        resolved_base_url = oauth_base_url(normalized_provider, ccproxy_port)
        resolved_api_key = _OAUTH_SENTINEL_KEY

    runtime = ProviderRuntimeConfig(
        provider=normalized_provider,
        base_url=resolved_base_url,
        model=str(model or "").strip(),
        api_key=resolved_api_key,
        auth_mode=normalized_auth_mode,
        ccproxy_port=int(ccproxy_port),
    )
    _ACTIVE_PROVIDER_RUNTIME = runtime
    return runtime


def get_active_provider_runtime() -> ProviderRuntimeConfig | None:
    runtime = _ACTIVE_PROVIDER_RUNTIME
    if runtime is None:
        return None
    if any((runtime.provider, runtime.base_url, runtime.model, runtime.api_key)):
        return runtime
    return None


def resolve_provider_runtime(
    *,
    provider: str = "",
    base_url: str = "",
    model: str = "",
    api_key: str = "",
    auth_mode: str = "",
    ccproxy_port: int | None = None,
    active_runtime: ProviderRuntimeConfig | None = None,
    env: Mapping[str, str] | None = None,
) -> ResolvedProviderRuntime:
    """Resolve the provider runtime for a request.

    Priority:
    1. Explicit base_url/api_key/provider/model when present
    2. Active OmicsClaw runtime when compatible with the request
    3. Environment / provider preset resolution

    When ``auth_mode`` is unspecified it defaults to the active runtime's
    mode, or falls back to ``"api_key"``.
    """
    requested_provider = _normalize_provider_name(provider)
    requested_base_url = str(base_url or "").strip()
    requested_model = str(model or "").strip()
    requested_key = str(api_key or "").strip()
    requested_auth_mode = str(auth_mode or "").strip().lower()
    runtime = active_runtime if active_runtime is not None else get_active_provider_runtime()

    effective_auth_mode = (
        requested_auth_mode
        or (runtime.auth_mode if runtime is not None else "")
        or "api_key"
    )
    effective_port = int(
        ccproxy_port
        if ccproxy_port is not None
        else (runtime.ccproxy_port if runtime is not None else DEFAULT_CCPROXY_PORT)
    )

    # Explicit auth_mode that differs from the active runtime's mode means
    # the caller is performing a deliberate switch (OAuth ↔ API key). We
    # must NOT silently reuse the old runtime's base_url / sentinel key in
    # that case — otherwise switching back to API key mode would still
    # route requests through ccproxy (Bug 4: state machine not reversible).
    auth_mode_compatible = (
        runtime is None
        or not requested_auth_mode
        or requested_auth_mode == runtime.auth_mode
    )
    can_reuse_active_runtime = (
        runtime is not None
        and not requested_base_url
        and not requested_key
        and (not requested_provider or requested_provider == runtime.provider)
        and auth_mode_compatible
    )
    if can_reuse_active_runtime:
        resolved_provider = infer_provider_name(
            provider=requested_provider or runtime.provider,
            base_url=runtime.base_url,
            env=env,
        )
        resolved_runtime = ResolvedProviderRuntime(
            provider=resolved_provider,
            base_url=runtime.base_url,
            model=requested_model or runtime.model,
            api_key=_normalize_api_key_for_client(
                resolved_provider,
                runtime.api_key,
                auth_mode=effective_auth_mode,
            ),
            auth_mode=effective_auth_mode,
            ccproxy_port=effective_port,
            source="active-runtime",
        )
        if any((
            resolved_runtime.provider,
            resolved_runtime.base_url,
            resolved_runtime.model,
            resolved_runtime.api_key,
        )):
            return resolved_runtime

    resolved_url, resolved_model, resolved_key = resolve_provider(
        provider=requested_provider,
        base_url=requested_base_url,
        model=requested_model,
        api_key=requested_key,
        env=env,
    )
    resolved_provider = infer_provider_name(
        provider=requested_provider,
        base_url=resolved_url or requested_base_url,
        env=env,
    )

    # If the caller explicitly requested OAuth for a supported provider,
    # override the base URL with the local ccproxy endpoint. Preset URLs
    # from resolve_provider() would otherwise point at the cloud API.
    if (
        effective_auth_mode == "oauth"
        and provider_supports_oauth(resolved_provider)
    ):
        resolved_url = oauth_base_url(resolved_provider, effective_port)

    return ResolvedProviderRuntime(
        provider=resolved_provider,
        base_url=str(resolved_url or "").strip(),
        model=str(resolved_model or "").strip(),
        api_key=_normalize_api_key_for_client(
            resolved_provider,
            resolved_key,
            auth_mode=effective_auth_mode,
        ),
        auth_mode=effective_auth_mode,
        ccproxy_port=effective_port,
        source=(
            "explicit-request"
            if any((requested_provider, requested_base_url, requested_model, requested_key))
            else "environment"
        ),
    )
