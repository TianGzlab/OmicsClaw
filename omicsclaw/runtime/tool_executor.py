from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .tool_spec import ToolSpec

ToolCallable = Callable[..., Any]


def build_executor_map(
    specs: Sequence[ToolSpec],
    available_executors: Mapping[str, ToolCallable],
) -> dict[str, ToolCallable]:
    """Resolve callable executors for a set of tool specs."""

    missing: list[str] = []
    resolved: dict[str, ToolCallable] = {}

    for spec in specs:
        executor = available_executors.get(spec.resolved_executor_name)
        if executor is None:
            missing.append(f"{spec.name}->{spec.resolved_executor_name}")
            continue
        resolved[spec.name] = executor

    if missing:
        missing_text = ", ".join(sorted(missing))
        raise KeyError(f"Missing tool executors for: {missing_text}")

    return resolved


def build_executor_kwargs(
    spec: ToolSpec,
    runtime_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not runtime_context:
        return {}

    kwargs: dict[str, Any] = {}
    for param_name in spec.context_params:
        value = runtime_context.get(param_name)
        if value is not None:
            kwargs[param_name] = value
    return kwargs


async def invoke_tool(
    spec: ToolSpec,
    executor: ToolCallable,
    args: dict[str, Any],
    runtime_context: Mapping[str, Any] | None = None,
) -> Any:
    result = executor(args, **build_executor_kwargs(spec, runtime_context))
    if inspect.isawaitable(result):
        return await result
    return result
