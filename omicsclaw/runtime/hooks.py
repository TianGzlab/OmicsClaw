from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from string import Formatter
from typing import Any, Callable, Mapping

from omicsclaw.extensions.loader import list_installed_extensions
from omicsclaw.extensions.manifest import discover_extension_manifest, load_extension_manifest

from .events import LifecycleEvent, VALID_LIFECYCLE_EVENTS
from .hook_payloads import payload_to_dict

HOOK_MODE_NOTICE = "notice"
HOOK_MODE_CONTEXT = "context"
HOOK_MODE_RECORD = "record"
VALID_HOOK_MODES = frozenset({HOOK_MODE_NOTICE, HOOK_MODE_CONTEXT, HOOK_MODE_RECORD})
HOOKS_TRUSTED_CAPABILITY = "hooks"


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_hook_mode(value: str) -> str:
    mode = _safe_text(value) or HOOK_MODE_NOTICE
    if mode not in VALID_HOOK_MODES:
        return HOOK_MODE_NOTICE
    return mode


def _merge_trusted_capabilities(
    manifest_capabilities: list[str] | tuple[str, ...],
    record_capabilities: list[str] | tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            capability
            for capability in [*manifest_capabilities, *record_capabilities]
            if _safe_text(capability)
        )
    )


def _flatten_template_context(value: Mapping[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}

    def visit(prefix: str, raw: Any) -> None:
        if isinstance(raw, Mapping):
            for key, nested in raw.items():
                safe_key = str(key).strip().replace("-", "_")
                nested_prefix = f"{prefix}{safe_key}_" if prefix else f"{safe_key}_"
                visit(nested_prefix, nested)
            return

        if prefix:
            flattened[prefix[:-1]] = raw

    for key, item in value.items():
        safe_key = str(key).strip().replace("-", "_")
        if isinstance(item, Mapping):
            visit(f"{safe_key}_", item)
        else:
            flattened[safe_key] = item
    return flattened


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _render_template(template: str, context: Mapping[str, Any]) -> str:
    formatter = Formatter()
    return formatter.vformat(template, (), _SafeFormatDict(context))


@dataclass(frozen=True, slots=True)
class LifecycleHookSpec:
    name: str
    event: str
    message: str
    mode: str = HOOK_MODE_NOTICE
    source: str = "managed"
    extension_name: str = ""
    relative_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class HookExecutionRecord:
    hook_name: str
    event_name: str
    mode: str
    source: str
    success: bool
    message: str = ""
    error: str = ""
    extension_name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hook_name": self.hook_name,
            "event_name": self.event_name,
            "mode": self.mode,
            "source": self.source,
            "success": self.success,
            "message": self.message,
            "error": self.error,
            "extension_name": self.extension_name,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class LifecycleDispatchRecord:
    event: LifecycleEvent
    hook_records: tuple[HookExecutionRecord, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event.to_dict(),
            "hook_records": [record.to_dict() for record in self.hook_records],
        }


@dataclass(frozen=True, slots=True)
class PendingHookMessage:
    event_name: str
    mode: str
    message: str
    call_id: str = ""


class LifecycleHookRuntime:
    """Shared lifecycle event bus with safe managed/extension hooks."""

    def __init__(
        self,
        hooks: list[LifecycleHookSpec] | tuple[LifecycleHookSpec, ...] | None = None,
    ) -> None:
        self._hooks: list[LifecycleHookSpec] = []
        self._records: list[LifecycleDispatchRecord] = []
        self._pending_messages: list[PendingHookMessage] = []
        self._subscribers: list[Callable[[LifecycleDispatchRecord], Any]] = []
        for hook in hooks or ():
            self.register_hook(hook)

    @property
    def records(self) -> tuple[LifecycleDispatchRecord, ...]:
        return tuple(self._records)

    def register_hook(self, hook: LifecycleHookSpec) -> None:
        if hook.event not in VALID_LIFECYCLE_EVENTS:
            raise ValueError(f"Unsupported lifecycle hook event: {hook.event}")
        self._hooks.append(
            LifecycleHookSpec(
                name=hook.name,
                event=hook.event,
                message=hook.message,
                mode=_normalize_hook_mode(hook.mode),
                source=hook.source,
                extension_name=hook.extension_name,
                relative_path=hook.relative_path,
                metadata=dict(hook.metadata),
                enabled=bool(hook.enabled),
            )
        )

    def subscribe(self, callback: Callable[[LifecycleDispatchRecord], Any]) -> None:
        self._subscribers.append(callback)

    def emit(
        self,
        event_name: str,
        payload: Mapping[str, Any] | Any,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> LifecycleDispatchRecord:
        if event_name not in VALID_LIFECYCLE_EVENTS:
            raise ValueError(f"Unsupported lifecycle event: {event_name}")

        context_map = dict(context or {})
        payload_map = payload_to_dict(payload)
        event = LifecycleEvent(
            name=event_name,
            payload=payload_map,
            surface=_safe_text(context_map.get("surface")),
            session_id=_safe_text(context_map.get("session_id")),
            chat_id=_safe_text(context_map.get("chat_id")),
            workspace=_safe_text(context_map.get("workspace")),
            source=_safe_text(context_map.get("source")),
        )

        render_context = {
            "event_name": event.name,
            "surface": event.surface,
            "session_id": event.session_id,
            "chat_id": event.chat_id,
            "workspace": event.workspace,
            "source": event.source,
            **payload_map,
        }
        render_context.update(_flatten_template_context(payload_map))

        hook_records: list[HookExecutionRecord] = []
        call_id = _safe_text(payload_map.get("call_id"))
        for hook in self._hooks:
            if not hook.enabled or hook.event != event_name:
                continue
            try:
                message = _render_template(hook.message, render_context).strip()
                record = HookExecutionRecord(
                    hook_name=hook.name,
                    event_name=event_name,
                    mode=hook.mode,
                    source=hook.source,
                    success=True,
                    message=message,
                    extension_name=hook.extension_name,
                    metadata=dict(hook.metadata),
                )
                if message and hook.mode in {HOOK_MODE_NOTICE, HOOK_MODE_CONTEXT}:
                    self._pending_messages.append(
                        PendingHookMessage(
                            event_name=event_name,
                            mode=hook.mode,
                            message=message,
                            call_id=call_id,
                        )
                    )
            except Exception as exc:
                record = HookExecutionRecord(
                    hook_name=hook.name,
                    event_name=event_name,
                    mode=hook.mode,
                    source=hook.source,
                    success=False,
                    error=f"{type(exc).__name__}: {exc}",
                    extension_name=hook.extension_name,
                    metadata=dict(hook.metadata),
                )
            hook_records.append(record)

        dispatch = LifecycleDispatchRecord(
            event=event,
            hook_records=tuple(hook_records),
        )
        self._records.append(dispatch)

        for callback in list(self._subscribers):
            try:
                callback(dispatch)
            except Exception:
                continue

        return dispatch

    def consume_pending_messages(
        self,
        *,
        mode: str = "",
        event_names: tuple[str, ...] | list[str] | None = None,
        call_id: str = "",
    ) -> list[str]:
        target_mode = _normalize_hook_mode(mode) if mode else ""
        target_events = {str(name) for name in (event_names or ()) if _safe_text(name)}
        target_call_id = _safe_text(call_id)
        consumed: list[str] = []
        kept: list[PendingHookMessage] = []

        for item in self._pending_messages:
            if target_mode and item.mode != target_mode:
                kept.append(item)
                continue
            if target_events and item.event_name not in target_events:
                kept.append(item)
                continue
            if target_call_id and item.call_id != target_call_id:
                kept.append(item)
                continue
            consumed.append(item.message)

        self._pending_messages = kept
        return consumed


def load_extension_hook_specs(
    omicsclaw_dir: str | Path,
) -> list[LifecycleHookSpec]:
    loaded: list[LifecycleHookSpec] = []
    for item in list_installed_extensions(omicsclaw_dir):
        if not item.state.enabled or item.record is None:
            continue
        if _safe_text(item.record.source_kind) != "local":
            continue

        manifest_path = discover_extension_manifest(item.path)
        if manifest_path is None:
            continue
        try:
            manifest = load_extension_manifest(manifest_path)
        except ValueError:
            continue

        capabilities = _merge_trusted_capabilities(
            manifest.trusted_capabilities,
            item.record.trusted_capabilities,
        )
        if HOOKS_TRUSTED_CAPABILITY not in capabilities:
            continue

        for relative_path in manifest.hooks:
            hook_path = item.path / relative_path
            try:
                raw = json.loads(hook_path.read_text(encoding="utf-8"))
            except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue

            if isinstance(raw, dict):
                entries = raw.get("hooks", [])
            elif isinstance(raw, list):
                entries = raw
            else:
                entries = []

            if not isinstance(entries, list):
                continue

            for index, entry in enumerate(entries, start=1):
                if not isinstance(entry, Mapping):
                    continue
                event_name = _safe_text(entry.get("event"))
                message = _safe_text(entry.get("message"))
                if event_name not in VALID_LIFECYCLE_EVENTS or not message:
                    continue
                hook_name = _safe_text(entry.get("name")) or (
                    f"{manifest.name}:{Path(relative_path).stem}:{index}"
                )
                loaded.append(
                    LifecycleHookSpec(
                        name=hook_name,
                        event=event_name,
                        message=message,
                        mode=_normalize_hook_mode(_safe_text(entry.get("mode"))),
                        source="extension",
                        extension_name=manifest.name,
                        relative_path=relative_path,
                        metadata={"manifest_path": str(manifest_path)},
                    )
                )

    return sorted(
        loaded,
        key=lambda hook: (
            hook.event,
            hook.source,
            hook.extension_name,
            hook.name,
            hook.relative_path,
        ),
    )


def build_default_lifecycle_hook_runtime(
    omicsclaw_dir: str | Path,
    *,
    managed_hooks: list[LifecycleHookSpec] | tuple[LifecycleHookSpec, ...] | None = None,
) -> LifecycleHookRuntime:
    runtime = LifecycleHookRuntime(list(managed_hooks or ()))
    for hook in load_extension_hook_specs(omicsclaw_dir):
        runtime.register_hook(hook)
    return runtime


def format_hook_notice_block(notices: list[str] | tuple[str, ...]) -> str:
    lines = [notice.strip() for notice in notices if _safe_text(notice)]
    if not lines:
        return ""
    return "\n".join(f"Hook notice: {line}" for line in lines)


__all__ = [
    "HOOK_MODE_CONTEXT",
    "HOOK_MODE_NOTICE",
    "HOOK_MODE_RECORD",
    "HOOKS_TRUSTED_CAPABILITY",
    "HookExecutionRecord",
    "LifecycleDispatchRecord",
    "LifecycleHookRuntime",
    "LifecycleHookSpec",
    "PendingHookMessage",
    "build_default_lifecycle_hook_runtime",
    "format_hook_notice_block",
    "load_extension_hook_specs",
]
