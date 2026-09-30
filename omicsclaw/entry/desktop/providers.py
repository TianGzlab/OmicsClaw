"""``GET``/``PUT /providers`` and ``POST /providers/test``: the model backend
the deployment's ``.env`` configures.

The settings live in the ``.env`` files the process shell loads at
start-up. :class:`SettingsFile` is what these functions need to know about
them, and :class:`DotenvSettings` is the implementation the shell builds
and hands to :func:`~omicsclaw.entry.desktop.server.create_desktop_app`.

**Two configurations are compared.** The *running* one is resolved from
the environment the process started with (:attr:`SettingsFile.startup`).
The one the *next start* will run is resolved from :func:`next_start_environment`:
every candidate file, the first to name a variable deciding it, and then
the variables exported before start-up, which beat every file. Where their
provider, model or endpoint differ, the listing reports
``restart_pending``.

The listing::

    {"providers": [{"name": "deepseek", "display_name": "DeepSeek",
                    "tier": "primary", "base_url": "https://api.deepseek.com",
                    "default_model": "deepseek-v4-flash",
                    "models": ["..."],
                    "model_metadata": [{"id": "...", "context_window": 1000000}],
                    "env_key": "DEEPSEEK_API_KEY",
                    "configured": true, "configured_via": "provider-env",
                    "configured_base_url": "https://api.deepseek.com",
                    "active": true}],
     "current": "deepseek", "current_model": "deepseek-v4-flash",
     "restart_pending": false, "env_file": "/path/to/.env"}

A save answers::

    {"ok": true, "provider": "deepseek", "model": "deepseek-v4-pro",
     "restart_required": true, "env_file": "/path/.env",
     "written": ["LLM_PROVIDER", "DEEPSEEK_API_KEY", "LLM_MODEL"],
     "shadowed_by_environment": []}

``configured_base_url`` is the endpoint the next start resolves for that
provider if it is selected with no endpoint given: its scoped
``<PROVIDER>_BASE_URL``, the generic variables when they apply to it, or
the preset's own; ``""`` means none (the SDK default, or ``custom`` with
nothing set).

``provider`` and ``model`` there are what the next start will run.
``shadowed_by_environment`` names exported variables that keep a written
value from taking effect.

No payload carries a key or any part of one.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Final, Mapping, Protocol

from omicsclaw.provider import (
    DEFAULT_MODEL_LIMITS,
    DETECT_ORDER,
    PRESETS,
    ProviderConfig,
    ProviderPreset,
    get_model_limits,
    provider_for,
    resolve_config,
)
from omicsclaw.schema import Message, Role

from .doctor import effective_model
from .turn_submission import DesktopIngressError

__all__ = [
    "MAX_VALUE_CHARS",
    "PROVIDER_TEST_TIMEOUT_S",
    "DotenvSettings",
    "SettingsFile",
    "next_start_environment",
    "provider_listing",
    "provider_settings_updates",
    "save_provider",
    "test_provider",
]

_log = logging.getLogger(__name__)

MAX_VALUE_CHARS: Final = 4096
"""Longest value a save or a test accepts."""

PROVIDER_TEST_TIMEOUT_S: Final = 20.0
"""Wall-clock ceiling of one ``POST /providers/test`` call."""

_MAX_MESSAGE_CHARS: Final = 300
_MIN_SCRUBBED_CHARS: Final = 8
_CONTROL: Final = re.compile(r"[\x00-\x1f]")
_FIELDS: Final = frozenset({"provider", "api_key", "model", "base_url"})
_TEST_OVERRIDES: Final[Mapping[str, Any]] = {
    "max_retries": 0,
    "max_tokens": 256,
    "timeout_seconds": 15.0,
    "thinking_budget_tokens": 0,
}
_EXPLICIT_PROVIDERS: Final = frozenset({"ollama", "custom"})


class SettingsFile(Protocol):
    """The ``.env`` files a deployment is configured by."""

    @property
    def path(self) -> Path:
        """The file a save writes to."""
        ...

    @property
    def candidates(self) -> tuple[Path, ...]:
        """Every file start-up loads, in the order it loads them."""
        ...

    @property
    def exported(self) -> Mapping[str, str]:
        """Variables set before start-up read any file."""
        ...

    @property
    def startup(self) -> Mapping[str, str]:
        """The environment this process started with, files included."""
        ...

    def read(self) -> Mapping[str, str]:
        """The variables :attr:`path` sets.

        :raises OSError: the file exists and cannot be read.
        :raises UnicodeDecodeError: it is not UTF-8.
        """
        ...

    def read_candidates(self) -> tuple[Mapping[str, str], ...]:
        """The variables each of :attr:`candidates` sets, in order; a file
        that is missing or unreadable is empty."""
        ...

    def write(self, updates: Mapping[str, str | None]) -> None:
        """Set each variable of *updates* in :attr:`path`; ``None``
        removes it. Every other line is kept.

        :raises OSError: the file cannot be read or written.
        :raises UnicodeDecodeError: it is not UTF-8.
        """
        ...


@dataclass(frozen=True)
class DotenvSettings:
    """A :class:`SettingsFile` over real ``.env`` files.

    Built once at start-up; constructing one reads nothing. Reads and
    writes use the same parser and writer as ``oc cli --configure``: a
    write replaces only the given keys, keeps the file's mode, is atomic,
    and first copies the old file to ``.env.backup-<timestamp>``.
    """

    path: Path
    candidates: tuple[Path, ...] = ()
    exported: Mapping[str, str] = field(default_factory=dict)
    startup: Mapping[str, str] = field(default_factory=dict)

    def read(self) -> Mapping[str, str]:
        from omicsclaw.entry.cli._configure import read_dotenv

        return read_dotenv(self.path)

    def read_candidates(self) -> tuple[Mapping[str, str], ...]:
        from omicsclaw.entry.cli._configure import read_dotenv

        found: list[Mapping[str, str]] = []
        for candidate in self.candidates:
            try:
                found.append(read_dotenv(candidate))
            except (OSError, UnicodeDecodeError):
                found.append({})
        return tuple(found)

    def write(self, updates: Mapping[str, str | None]) -> None:
        from omicsclaw.entry.cli._configure import write_dotenv

        write_dotenv(self.path, updates)


# ---- what the next start sees ------------------------------------------------


def next_start_environment(settings: SettingsFile | None) -> dict[str, str]:
    """The environment the next start of this deployment will have.

    Every candidate file in order, the first to set a variable keeping
    it, then :attr:`SettingsFile.exported` over all of them. Empty when
    *settings* is ``None``.
    """
    if settings is None:
        return {}
    merged: dict[str, str] = {}
    for variables in settings.read_candidates():
        for key, value in variables.items():
            merged.setdefault(key, value)
    merged.update(settings.exported)
    return merged


def _first(environment: Mapping[str, str], *names: str) -> str:
    for name in names:
        value = str(environment.get(name, "") or "").strip()
        if value:
            return value
    return ""


def _next_start_config(environment: Mapping[str, str]) -> ProviderConfig:
    """What the next start resolves: provider and model read in the order
    :class:`~omicsclaw.entry.AppConfig` reads them."""
    return resolve_config(
        _first(environment, "OMICSCLAW_PROVIDER", "LLM_PROVIDER"),
        _first(environment, "OMICSCLAW_MODEL", "LLM_MODEL"),
        env=environment,
    )


def _running_config(app: Any, settings: SettingsFile) -> ProviderConfig:
    return resolve_config(app.config.provider, app.config.model, env=settings.startup)


def _triple(config: ProviderConfig) -> tuple[str, str, str]:
    return (config.provider, config.model, config.base_url)


# ---- GET /providers ------------------------------------------------------------


def _ordered_presets() -> list[ProviderPreset]:
    names = [name for name in DETECT_ORDER if name in PRESETS]
    names += [name for name in PRESETS if name not in names]
    return [PRESETS[name] for name in names]


def _configured_via(
    preset: ProviderPreset, environment: Mapping[str, str]
) -> str | None:
    if preset.api_key_env and _first(environment, preset.api_key_env):
        return "provider-env"
    resolved = resolve_config(preset.name, env=environment)
    if resolved.api_key.strip():
        return "generic-env"
    named = _first(environment, "LLM_PROVIDER", "OMICSCLAW_PROVIDER").lower()
    if preset.name in _EXPLICIT_PROVIDERS and named == preset.name and resolved.base_url:
        return "explicit-provider"
    return None


def _row(
    preset: ProviderPreset, environment: Mapping[str, str], active: str
) -> dict[str, Any]:
    models = list(preset.models)
    if preset.default_model and preset.default_model not in models:
        models.insert(0, preset.default_model)
    metadata = []
    for model in models:
        limits = get_model_limits(model)
        if limits != DEFAULT_MODEL_LIMITS:
            metadata.append({"id": model, "context_window": limits.context_tokens})
    via = _configured_via(preset, environment)
    return {
        "name": preset.name,
        "display_name": preset.display_name or preset.name,
        "tier": preset.tier.value,
        "base_url": preset.base_url,
        "default_model": preset.default_model,
        "models": models,
        "model_metadata": metadata,
        "env_key": preset.api_key_env,
        "configured": via is not None,
        "configured_via": via,
        "configured_base_url": resolve_config(preset.name, env=environment).base_url,
        "active": preset.name == active,
    }


def provider_listing(app: Any, settings: SettingsFile | None) -> dict[str, Any]:
    """The ``GET /providers`` payload.

    Without *settings* no row is configured, ``env_file`` is ``null``,
    ``restart_pending`` is false and ``current``/``current_model`` are
    what ``/health`` reports.
    """
    environment = next_start_environment(settings)
    active = app.provider.name
    if settings is None:
        current, current_model, pending = active, effective_model(app), False
    else:
        running = _running_config(app, settings)
        current, current_model = running.provider, running.model
        pending = _triple(running) != _triple(_next_start_config(environment))
    return {
        "providers": [
            _row(preset, environment, active) for preset in _ordered_presets()
        ],
        "current": current,
        "current_model": current_model,
        "restart_pending": pending,
        "env_file": str(settings.path) if settings is not None else None,
    }


# ---- PUT /providers --------------------------------------------------------------


@dataclass(frozen=True)
class _ProviderRequest:
    provider: str
    api_key: str
    model: str
    base_url: str | None


def _decode_request(document: Mapping[str, Any]) -> _ProviderRequest:
    unknown = set(document) - _FIELDS
    if unknown:
        raise DesktopIngressError("unknown_field")
    values: dict[str, str | None] = {}
    for name in _FIELDS:
        value = document.get(name)
        if value is None:
            values[name] = None
            continue
        if (
            not isinstance(value, str)
            or len(value) > MAX_VALUE_CHARS
            or _CONTROL.search(value)
        ):
            raise DesktopIngressError("invalid_value")
        values[name] = value.strip()
    provider = (values["provider"] or "").lower()
    if provider not in PRESETS:
        raise DesktopIngressError("unknown_provider")
    return _ProviderRequest(
        provider=provider,
        api_key=values["api_key"] or "",
        model=values["model"] or "",
        base_url=values["base_url"],
    )


def _url_names(provider: str) -> tuple[str, ...]:
    from omicsclaw.entry.cli._configure import base_url_names

    return base_url_names(provider)


def provider_settings_updates(
    existing: Mapping[str, str],
    *,
    provider: str,
    api_key: str,
    model: str | None,
    base_url: str | None,
    previous_provider: str,
) -> dict[str, str]:
    """The variables a save of *provider* writes into a file holding *existing*.

    * The provider goes to every one of ``OMICSCLAW_PROVIDER`` and
      ``LLM_PROVIDER`` the file already has, else ``LLM_PROVIDER``.
    * A non-empty *api_key* goes to the preset's own key variable, or to
      ``LLM_API_KEY`` for a preset without one; an empty one writes
      nothing.
    * The model goes to every one of ``OMICSCLAW_MODEL`` and ``LLM_MODEL``
      the file has, else ``LLM_MODEL``; the endpoint to every one of
      ``<PROVIDER>_BASE_URL``,
      ``LLM_BASE_URL``, ``OMICSCLAW_BASE_URL`` the file has, else
      ``LLM_BASE_URL``.
    * When *provider* differs from *previous_provider*, a missing or
      empty *model* writes the preset's default model and a missing
      *base_url* writes ``""``. Otherwise only what was given is written.
      A *base_url* of ``""`` is given, and means the preset's endpoint.

    The variable names are chosen by the same rule as ``oc cli
    --configure`` (:func:`~omicsclaw.entry.cli._configure.names_to_write`).
    """
    from omicsclaw.entry.cli._configure import (
        MODEL_NAMES,
        PROVIDER_NAMES,
        names_to_write,
    )

    preset = PRESETS[provider]
    switched = provider != previous_provider
    updates: dict[str, str] = dict.fromkeys(
        names_to_write(existing, "LLM_PROVIDER", *PROVIDER_NAMES), provider
    )
    if api_key:
        updates[preset.api_key_env or "LLM_API_KEY"] = api_key
    model_value = model or (preset.default_model if switched else None)
    if model_value is not None:
        for name in names_to_write(existing, "LLM_MODEL", *MODEL_NAMES):
            updates[name] = model_value
    url = base_url if base_url is not None else ("" if switched else None)
    if url is not None:
        for name in names_to_write(existing, "LLM_BASE_URL", *_url_names(provider)):
            updates[name] = url
    return updates


def _spellings(name: str, provider: str) -> tuple[str, ...]:
    """The variables that set the same thing as *name* for *provider*,
    in the order ``resolve_config`` reads them; ``()`` for any other."""
    from omicsclaw.entry.cli._configure import MODEL_NAMES, PROVIDER_NAMES

    keys = (PRESETS[provider].api_key_env, "LLM_API_KEY", "OMICSCLAW_API_KEY")
    for group in (PROVIDER_NAMES, MODEL_NAMES, _url_names(provider), keys):
        if name in group:
            return tuple(other for other in group if other)
    return ()


def _shadowed(
    updates: Mapping[str, str], provider: str, exported: Mapping[str, str]
) -> list[str]:
    """Exported variables that keep a value in *updates* from taking effect.

    * The written variable itself, exported with a different value.
    * Another spelling of the same setting, exported non-empty with a
      different value, when it is read before the written one, when the
      written value is empty, or when it is a provider spelling (the
      provider is read in both orders).
    """
    from omicsclaw.entry.cli._configure import PROVIDER_NAMES

    shadowed: list[str] = []
    for name, value in updates.items():
        wanted = str(value or "").strip()
        if name in exported and str(exported[name] or "").strip() != wanted:
            if name not in shadowed:
                shadowed.append(name)
        group = _spellings(name, provider)
        for position, other in enumerate(group):
            theirs = _first(exported, other)
            if other == name or not theirs or theirs == wanted:
                continue
            if (
                position < group.index(name)
                or not wanted
                or group == PROVIDER_NAMES
            ) and other not in shadowed:
                shadowed.append(other)
    return shadowed


def save_provider(
    app: Any, settings: SettingsFile | None, document: Mapping[str, Any]
) -> dict[str, Any]:
    """``PUT /providers``: write ``{provider, api_key?, model?, base_url?}``
    into :attr:`SettingsFile.path` (see :func:`provider_settings_updates`).

    :raises DesktopIngressError: 503 ``settings_unavailable`` without
        *settings*; 422 ``unknown_field``, ``invalid_value``,
        ``unknown_provider`` or ``custom_endpoint_required``; 500
        ``env_write_failed`` when the file cannot be read or written, in
        which case it is unchanged.
    """
    if settings is None:
        raise DesktopIngressError("settings_unavailable", status_code=503)
    request = _decode_request(document)
    if request.provider == "custom" and not (request.model and request.base_url):
        raise DesktopIngressError("custom_endpoint_required")
    previous = _next_start_config(next_start_environment(settings)).provider
    try:
        updates = provider_settings_updates(
            settings.read(),
            provider=request.provider,
            api_key=request.api_key,
            model=request.model,
            base_url=request.base_url,
            previous_provider=previous,
        )
        settings.write(updates)
    except (OSError, UnicodeDecodeError) as exc:
        _log.warning(
            "could not write provider settings to %s: %s",
            settings.path,
            type(exc).__name__,
        )
        raise DesktopIngressError("env_write_failed", status_code=500) from None
    after = _next_start_config(next_start_environment(settings))
    written = list(updates)
    return {
        "ok": True,
        "provider": after.provider,
        "model": after.model,
        "restart_required": True,
        "env_file": str(settings.path),
        "written": written,
        "shadowed_by_environment": _shadowed(
            updates, request.provider, settings.exported
        ),
    }


# ---- POST /providers/test ---------------------------------------------------------


def _scrub(text: str, secret: str) -> str:
    if len(secret) >= _MIN_SCRUBBED_CHARS:
        text = text.replace(secret, "…")
    return text[:_MAX_MESSAGE_CHARS]


def _failure_detail(exc: BaseException) -> str:
    status = getattr(exc, "status_code", None)
    name = type(exc).__name__
    return f"{name} (HTTP {status})" if isinstance(status, int) else name


async def test_provider(
    settings: SettingsFile | None,
    document: Mapping[str, Any],
    *,
    provider_factory: Callable[[ProviderConfig], Any] = provider_for,
    timeout_s: float = PROVIDER_TEST_TIMEOUT_S,
) -> dict[str, Any]:
    """``POST /providers/test``: one short call to ``{provider, model?,
    base_url?, api_key?}``, resolved against the next start's environment.

    The call passes when it returns, whatever the text. Answers
    ``{ok: true, message, provider, model, duration_ms}`` or
    ``{ok: false, message, detail, duration_ms}``; ``message`` has the key
    used, when it is at least 8 characters, replaced by ``…`` and is at
    most 300 characters. The adapter is closed afterwards when it has an
    ``aclose()`` or ``close()``.

    :raises DesktopIngressError: 503 ``settings_unavailable`` without
        *settings*; 422 for a malformed request.
    """
    if settings is None:
        raise DesktopIngressError("settings_unavailable", status_code=503)
    request = _decode_request(document)
    config = resolve_config(
        request.provider,
        request.model,
        base_url=request.base_url or "",
        api_key=request.api_key,
        env=next_start_environment(settings),
    ).with_overrides(**_TEST_OVERRIDES)
    messages = (
        Message(role=Role.SYSTEM, content="Reply with the single word: pong."),
        Message(role=Role.USER, content="ping"),
    )
    started = time.monotonic()
    try:
        async with asyncio.timeout(timeout_s):
            adapter = provider_factory(config)
            try:
                reply: Awaitable[Any] = adapter.generate(messages, None)
                await reply
            finally:
                await _close(adapter)
    except Exception as exc:  # noqa: BLE001 - every failure is a result
        return {
            "ok": False,
            "message": _scrub(str(exc) or type(exc).__name__, config.api_key),
            "detail": _failure_detail(exc),
            "duration_ms": _elapsed_ms(started),
        }
    return {
        "ok": True,
        "message": "Live provider test passed.",
        "provider": config.provider,
        "model": config.model,
        "duration_ms": _elapsed_ms(started),
    }


async def _close(adapter: Any) -> None:
    """Close *adapter* through its ``aclose()`` or ``close()``, when it has one."""
    closer = getattr(adapter, "aclose", None) or getattr(adapter, "close", None)
    if closer is None:
        return
    try:
        result = closer()
        if asyncio.iscoroutine(result):
            await result
    except Exception as exc:  # noqa: BLE001 - closing never decides the result
        _log.debug("closing the test adapter failed: %s", type(exc).__name__)


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
