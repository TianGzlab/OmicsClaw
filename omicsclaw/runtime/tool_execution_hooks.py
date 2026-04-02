from __future__ import annotations

from fnmatch import fnmatchcase
from string import Formatter
from typing import Any, Mapping

from omicsclaw.extensions.runtime import (
    ExtensionToolExecutionHookEntry,
    LoadedToolExecutionHookExtension,
    ToolExecutionHookStageEntry,
    load_active_tool_execution_hook_extensions,
)

from .policy import (
    TOOL_POLICY_ALLOW,
    TOOL_POLICY_DENY,
    TOOL_POLICY_REQUIRE_APPROVAL,
)
from .tool_orchestration import (
    ToolExecutionHook,
    ToolExecutionHookResult,
    ToolExecutionRequest,
    ToolExecutionTrace,
)

_VALID_HOOK_ACTIONS = frozenset(
    {TOOL_POLICY_ALLOW, TOOL_POLICY_DENY, TOOL_POLICY_REQUIRE_APPROVAL}
)


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


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
    return Formatter().vformat(template, (), _SafeFormatDict(context))


def _render_value(value: Any, context: Mapping[str, Any]) -> Any:
    if isinstance(value, str):
        return _render_template(value, context)
    if isinstance(value, list):
        return [_render_value(item, context) for item in value]
    if isinstance(value, tuple):
        return tuple(_render_value(item, context) for item in value)
    if isinstance(value, Mapping):
        return {
            str(key): _render_value(item, context)
            for key, item in value.items()
        }
    return value


def _normalize_action(value: str) -> str:
    action = _safe_text(value) or TOOL_POLICY_ALLOW
    if action == "ask":
        return TOOL_POLICY_REQUIRE_APPROVAL
    if action in {"require-approval", "require approval"}:
        return TOOL_POLICY_REQUIRE_APPROVAL
    if action not in _VALID_HOOK_ACTIONS:
        return TOOL_POLICY_ALLOW
    return action


def _active_workspace(runtime_context: Mapping[str, Any] | None) -> str:
    if not runtime_context:
        return ""
    return _safe_text(
        runtime_context.get("pipeline_workspace") or runtime_context.get("workspace")
    )


def _matches_patterns(value: str, patterns: tuple[str, ...]) -> bool:
    if not patterns:
        return True
    if not value:
        return False
    return any(pattern == "*" or fnmatchcase(value, pattern) for pattern in patterns)


def _hook_matches(
    hook: ExtensionToolExecutionHookEntry,
    request: ToolExecutionRequest,
    runtime_context: Mapping[str, Any] | None,
) -> bool:
    surface = _safe_text((runtime_context or {}).get("surface"))
    return _matches_patterns(request.name, hook.tools) and _matches_patterns(
        surface,
        hook.surfaces,
    )


def _build_render_context(
    request: ToolExecutionRequest,
    *,
    runtime_context: Mapping[str, Any] | None,
    arguments: Mapping[str, Any] | None = None,
    output: Any = None,
    error: Exception | None = None,
    trace: ToolExecutionTrace | None = None,
) -> dict[str, Any]:
    runtime_map = dict(runtime_context or {})
    arguments_map = dict(arguments or {})
    context = {
        "tool_name": request.name,
        "call_id": request.call_id,
        "surface": _safe_text(runtime_map.get("surface")),
        "session_id": _safe_text(runtime_map.get("session_id")),
        "chat_id": _safe_text(runtime_map.get("chat_id")),
        "workspace": _active_workspace(runtime_map),
        "pipeline_workspace": _safe_text(runtime_map.get("pipeline_workspace")),
        "arguments": arguments_map,
        "runtime_context": runtime_map,
        "output": "" if output is None else str(output),
        "error": "" if error is None else f"{type(error).__name__}: {error}",
        "trace": trace.to_dict() if trace is not None else {},
    }
    context.update(
        {
            key: value
            for key, value in runtime_map.items()
            if _safe_text(key)
            and key
            not in {
                "workspace",
                "pipeline_workspace",
                "surface",
                "session_id",
                "chat_id",
            }
        }
    )
    context.update(_flatten_template_context(context))
    return context


def _stage_metadata(
    extension: LoadedToolExecutionHookExtension,
    hook: ExtensionToolExecutionHookEntry,
    stage: ToolExecutionHookStageEntry,
    *,
    matched: bool,
) -> dict[str, Any]:
    metadata = {
        "matched": matched,
        "extension_name": extension.name,
        "extension_type": extension.extension_type,
        "relative_path": hook.relative_path,
    }
    metadata.update(extension.metadata)
    metadata.update(hook.metadata)
    metadata.update(stage.metadata)
    return metadata


def _prefixed_hook_name(
    extension: LoadedToolExecutionHookExtension,
    hook: ExtensionToolExecutionHookEntry,
) -> str:
    if hook.name.startswith(f"{extension.name}:"):
        return hook.name
    return f"{extension.name}:{hook.name}"


def _build_pre_tool_hook(
    extension: LoadedToolExecutionHookExtension,
    hook: ExtensionToolExecutionHookEntry,
    stage: ToolExecutionHookStageEntry,
):
    def pre_tool(
        request: ToolExecutionRequest,
        arguments: dict[str, Any],
        runtime_context: Mapping[str, Any] | None,
    ) -> ToolExecutionHookResult:
        matched = _hook_matches(hook, request, runtime_context)
        metadata = _stage_metadata(extension, hook, stage, matched=matched)
        if not matched:
            return ToolExecutionHookResult(metadata=metadata)

        current_arguments = dict(arguments)
        changed = False
        render_context = _build_render_context(
            request,
            runtime_context=runtime_context,
            arguments=current_arguments,
        )
        for key, value in stage.defaults.items():
            if key not in current_arguments:
                current_arguments[key] = _render_value(value, render_context)
                changed = True

        render_context = _build_render_context(
            request,
            runtime_context=runtime_context,
            arguments=current_arguments,
        )
        for key, value in stage.set_arguments.items():
            rendered = _render_value(value, render_context)
            if current_arguments.get(key) != rendered:
                current_arguments[key] = rendered
                changed = True

        final_context = _build_render_context(
            request,
            runtime_context=runtime_context,
            arguments=current_arguments,
        )
        message = (
            _render_template(stage.message, final_context).strip()
            if stage.message
            else ""
        )
        return ToolExecutionHookResult(
            action=_normalize_action(stage.action),
            message=message,
            updated_arguments=current_arguments if changed else None,
            metadata=metadata,
        )

    return pre_tool


def _build_post_tool_hook(
    extension: LoadedToolExecutionHookExtension,
    hook: ExtensionToolExecutionHookEntry,
    stage: ToolExecutionHookStageEntry,
):
    def post_tool(
        request: ToolExecutionRequest,
        output: Any,
        trace: ToolExecutionTrace,
        runtime_context: Mapping[str, Any] | None,
    ) -> ToolExecutionHookResult:
        matched = _hook_matches(hook, request, runtime_context)
        metadata = _stage_metadata(extension, hook, stage, matched=matched)
        if not matched:
            return ToolExecutionHookResult(metadata=metadata)

        render_context = _build_render_context(
            request,
            runtime_context=runtime_context,
            arguments=trace.effective_arguments,
            output=output,
            trace=trace,
        )
        result_kwargs: dict[str, Any] = {
            "action": _normalize_action(stage.action),
            "message": (
                _render_template(stage.message, render_context).strip()
                if stage.message
                else ""
            ),
            "metadata": metadata,
        }
        if stage.output_template:
            result_kwargs["updated_output"] = _render_template(
                stage.output_template,
                render_context,
            )
        return ToolExecutionHookResult(**result_kwargs)

    return post_tool


def _build_failure_tool_hook(
    extension: LoadedToolExecutionHookExtension,
    hook: ExtensionToolExecutionHookEntry,
    stage: ToolExecutionHookStageEntry,
):
    def on_failure(
        request: ToolExecutionRequest,
        error: Exception | None,
        output: Any,
        trace: ToolExecutionTrace,
        runtime_context: Mapping[str, Any] | None,
    ) -> ToolExecutionHookResult:
        matched = _hook_matches(hook, request, runtime_context)
        metadata = _stage_metadata(extension, hook, stage, matched=matched)
        if not matched:
            return ToolExecutionHookResult(metadata=metadata)

        render_context = _build_render_context(
            request,
            runtime_context=runtime_context,
            arguments=trace.effective_arguments,
            output=output,
            error=error,
            trace=trace,
        )
        result_kwargs: dict[str, Any] = {
            "action": _normalize_action(stage.action),
            "message": (
                _render_template(stage.message, render_context).strip()
                if stage.message
                else ""
            ),
            "metadata": metadata,
        }
        if stage.output_template:
            result_kwargs["updated_output"] = _render_template(
                stage.output_template,
                render_context,
            )
        return ToolExecutionHookResult(**result_kwargs)

    return on_failure


def _build_runtime_hook(
    extension: LoadedToolExecutionHookExtension,
    hook: ExtensionToolExecutionHookEntry,
) -> ToolExecutionHook:
    return ToolExecutionHook(
        name=_prefixed_hook_name(extension, hook),
        pre_tool=(
            _build_pre_tool_hook(extension, hook, hook.pre)
            if hook.pre is not None
            else None
        ),
        post_tool=(
            _build_post_tool_hook(extension, hook, hook.post)
            if hook.post is not None
            else None
        ),
        on_failure=(
            _build_failure_tool_hook(extension, hook, hook.failure)
            if hook.failure is not None
            else None
        ),
    )


def build_default_tool_execution_hooks(
    omicsclaw_dir: str,
) -> tuple[ToolExecutionHook, ...]:
    hooks: list[ToolExecutionHook] = []
    for extension in load_active_tool_execution_hook_extensions(omicsclaw_dir):
        for hook in extension.tool_execution_hooks:
            hooks.append(_build_runtime_hook(extension, hook))
    return tuple(sorted(hooks, key=lambda item: item.name))


def merge_tool_execution_hooks(
    runtime_context: Mapping[str, Any] | None,
    hooks: tuple[ToolExecutionHook, ...] | list[ToolExecutionHook],
) -> dict[str, Any]:
    merged = dict(runtime_context or {})
    existing = merged.get("tool_execution_hooks")
    normalized: list[ToolExecutionHook] = []
    if isinstance(existing, (list, tuple)):
        normalized.extend(
            hook for hook in existing if isinstance(hook, ToolExecutionHook)
        )

    seen = {hook.name for hook in normalized}
    for hook in hooks:
        if not isinstance(hook, ToolExecutionHook):
            continue
        if hook.name in seen:
            continue
        normalized.append(hook)
        seen.add(hook.name)

    if normalized:
        merged["tool_execution_hooks"] = tuple(normalized)
    else:
        merged.pop("tool_execution_hooks", None)
    return merged


__all__ = [
    "build_default_tool_execution_hooks",
    "merge_tool_execution_hooks",
]
