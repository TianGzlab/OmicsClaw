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


@dataclass(frozen=True)
class ProviderRuntimeConfig:
    provider: str = ""
    base_url: str = ""
    model: str = ""
    api_key: str = ""


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


def _normalize_api_key_for_client(provider: str, api_key: str) -> str:
    resolved_key = str(api_key or "").strip()
    if resolved_key:
        return resolved_key
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
) -> ProviderRuntimeConfig:
    global _ACTIVE_PROVIDER_RUNTIME

    runtime = ProviderRuntimeConfig(
        provider=_normalize_provider_name(provider),
        base_url=str(base_url or "").strip(),
        model=str(model or "").strip(),
        api_key=str(api_key or "").strip(),
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
    active_runtime: ProviderRuntimeConfig | None = None,
    env: Mapping[str, str] | None = None,
) -> ResolvedProviderRuntime:
    """Resolve the provider runtime for a request.

    Priority:
    1. Explicit base_url/api_key/provider/model when present
    2. Active OmicsClaw runtime when compatible with the request
    3. Environment / provider preset resolution
    """
    requested_provider = _normalize_provider_name(provider)
    requested_base_url = str(base_url or "").strip()
    requested_model = str(model or "").strip()
    requested_key = str(api_key or "").strip()
    runtime = active_runtime if active_runtime is not None else get_active_provider_runtime()

    can_reuse_active_runtime = (
        runtime is not None
        and not requested_base_url
        and not requested_key
        and (not requested_provider or requested_provider == runtime.provider)
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
            ),
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

    return ResolvedProviderRuntime(
        provider=resolved_provider,
        base_url=str(resolved_url or "").strip(),
        model=str(resolved_model or "").strip(),
        api_key=_normalize_api_key_for_client(resolved_provider, resolved_key),
        source=(
            "explicit-request"
            if any((requested_provider, requested_base_url, requested_model, requested_key))
            else "environment"
        ),
    )
