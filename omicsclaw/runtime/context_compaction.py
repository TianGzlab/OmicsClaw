from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from .context_budget import estimate_message_size, trim_history_to_budget
from .tool_result_store import ToolResultRecord, ToolResultStore
from .transcript_store import (
    TranscriptReplaySummary,
    build_transcript_summary,
    sanitize_tool_history,
)

STAGE_SNIP_COMPACT = "snip_compact"
STAGE_MICRO_COMPACT = "micro_compact"
STAGE_CONTEXT_COLLAPSE = "context_collapse"
STAGE_AUTO_COMPACT = "auto_compact"
STAGE_REACTIVE_COMPACT = "reactive_compact"

# Marker that wraps the body of a manual /compact summary message stored in
# the transcript. The next /compact invocation uses this to skip
# re-summarising the previous summary (CodePilot bug #7 — boundary tracking).
COMPACTION_SUMMARY_OPEN = "<compaction-summary>"
COMPACTION_SUMMARY_CLOSE = "</compaction-summary>"


def wrap_compaction_summary(body: str) -> str:
    """Wrap a summary body so subsequent compactions can detect and skip it."""
    return f"{COMPACTION_SUMMARY_OPEN}\n{body.strip()}\n{COMPACTION_SUMMARY_CLOSE}"


def unwrap_compaction_summary(content: str) -> str:
    """Return the inner body of a wrapped summary, or pass through unchanged."""
    text = (content or "").strip()
    if not text.startswith(COMPACTION_SUMMARY_OPEN):
        return content
    inner = text[len(COMPACTION_SUMMARY_OPEN):]
    end = inner.rfind(COMPACTION_SUMMARY_CLOSE)
    if end == -1:
        return content
    return inner[:end].strip()


def is_compaction_summary_message(message: dict[str, Any]) -> bool:
    """True if ``message`` is a manual-/compact summary header."""
    if not isinstance(message, dict):
        return False
    if message.get("role") != "system":
        return False
    content = message.get("content")
    if not isinstance(content, str):
        return False
    return content.lstrip().startswith(COMPACTION_SUMMARY_OPEN)


@dataclass(frozen=True, slots=True)
class ContextCompactionConfig:
    enabled: bool = True
    max_prompt_chars: int | None = 96000
    snip_message_chars: int = 2400
    snip_tool_argument_chars: int = 1200
    protected_tail_messages: int = 4
    micro_keep_recent_tool_messages: int = 1
    collapse_trigger_ratio: float = 0.82
    auto_compact_trigger_ratio: float = 0.92
    collapse_preserve_messages: int = 16
    collapse_preserve_chars: int | None = 12000
    auto_compact_preserve_messages: int = 8
    auto_compact_preserve_chars: int | None = 6000
    reactive_preserve_messages: int = 6
    reactive_preserve_chars: int | None = 4000
    max_highlights_per_role: int = 3
    max_compacted_refs: int = 3
    max_plan_refs: int = 2
    max_advisory_refs: int = 3


@dataclass(frozen=True, slots=True)
class PreparedModelMessages:
    system_prompt: str
    messages: list[dict[str, Any]]
    estimated_chars: int
    applied_stages: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _CollapseResult:
    messages: list[dict[str, Any]]
    summary: str
    omitted_count: int


def estimate_prompt_chars(system_prompt: str, messages: list[dict[str, Any]]) -> int:
    return len(str(system_prompt or "")) + sum(
        estimate_message_size(message) for message in messages
    )


def _flatten_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = str(block.get("text", "") or "").strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return str(content or "").strip()


def _truncate_text(text: str, *, max_chars: int, label: str) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text

    omitted = len(text) - max_chars
    marker = f"\n[{label}: omitted {omitted} chars]"
    if len(marker) >= max_chars:
        return marker[-max_chars:]

    available = max_chars - len(marker)
    if available <= 24:
        return text[:available] + marker

    separator = "\n...\n"
    if available <= len(separator) + 16:
        return text[:available].rstrip() + marker

    body_budget = available - len(separator)
    head_budget = max(8, int(body_budget * 0.7))
    tail_budget = max(0, body_budget - head_budget)
    head = text[:head_budget].rstrip()
    tail = text[-tail_budget:].lstrip() if tail_budget else ""
    compacted = head
    if tail:
        compacted = f"{head}{separator}{tail}"
    return f"{compacted}{marker}"


def _append_system_summary(system_prompt: str, heading: str, summary: str) -> str:
    if not summary.strip():
        return system_prompt
    return (
        f"{system_prompt.rstrip()}\n\n{heading}\n\n{summary.strip()}"
    ).strip()


def _threshold_chars(max_prompt_chars: int | None, ratio: float) -> int | None:
    if max_prompt_chars is None or max_prompt_chars <= 0:
        return None
    bounded_ratio = min(1.0, max(0.0, ratio))
    return max(1, int(max_prompt_chars * bounded_ratio))


def _apply_snip_compaction(
    messages: list[dict[str, Any]],
    *,
    config: ContextCompactionConfig,
) -> tuple[list[dict[str, Any]], bool]:
    if not messages:
        return messages, False

    changed = False
    protected_from = max(0, len(messages) - max(0, config.protected_tail_messages))
    compacted: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        if index >= protected_from:
            compacted.append(copy.deepcopy(message))
            continue

        updated = copy.deepcopy(message)
        content = updated.get("content")
        if isinstance(content, str) and len(content) > config.snip_message_chars > 0:
            updated["content"] = _truncate_text(
                content,
                max_chars=config.snip_message_chars,
                label="snip compacted older message",
            )
            changed = True

        tool_calls = updated.get("tool_calls")
        if isinstance(tool_calls, list):
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                function_block = tool_call.get("function")
                if not isinstance(function_block, dict):
                    continue
                arguments = function_block.get("arguments")
                if (
                    isinstance(arguments, str)
                    and len(arguments) > config.snip_tool_argument_chars > 0
                ):
                    function_block["arguments"] = _truncate_text(
                        arguments,
                        max_chars=config.snip_tool_argument_chars,
                        label="snip compacted older tool arguments",
                    )
                    changed = True

        compacted.append(updated)

    return compacted, changed


def _build_micro_tool_reference(record: ToolResultRecord) -> str:
    return (
        "[tool result micro-compacted]\n"
        f"tool: {record.tool_name}\n"
        f"bytes: {record.output_bytes}\n"
        f"policy: {record.result_policy}\n"
        f"full_result_path: {record.storage_path}\n"
        "note: reload the referenced file if earlier tool details are needed."
    )


def _apply_micro_compaction(
    messages: list[dict[str, Any]],
    *,
    chat_id: int | str,
    tool_result_store: ToolResultStore,
    config: ContextCompactionConfig,
) -> tuple[list[dict[str, Any]], bool]:
    records_by_call_id = {
        record.tool_call_id: record
        for record in tool_result_store.get_records(chat_id)
        if record.storage_path
    }
    if not records_by_call_id:
        return [copy.deepcopy(message) for message in messages], False

    tool_indexes = [
        index
        for index, message in enumerate(messages)
        if message.get("role") == "tool"
    ]
    keep_recent = max(0, config.micro_keep_recent_tool_messages)
    protected_indexes = set(tool_indexes[-keep_recent:]) if keep_recent else set()

    changed = False
    compacted: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        updated = copy.deepcopy(message)
        if index not in protected_indexes and updated.get("role") == "tool":
            record = records_by_call_id.get(str(updated.get("tool_call_id", "") or ""))
            if record is not None:
                compact_content = _build_micro_tool_reference(record)
                current_content = str(updated.get("content", "") or "")
                if (
                    len(compact_content) < len(current_content)
                    or "[tool result compacted]" in current_content
                    or "[snip compacted older message" in current_content
                ):
                    updated["content"] = compact_content
                    changed = True
        compacted.append(updated)

    return compacted, changed


def _message_preview(message: dict[str, Any], *, max_chars: int = 180) -> str:
    role = str(message.get("role", "") or "")
    if role == "assistant" and message.get("tool_calls"):
        tool_names = []
        for tool_call in message.get("tool_calls", []) or []:
            if not isinstance(tool_call, dict):
                continue
            function_block = tool_call.get("function")
            if isinstance(function_block, dict) and function_block.get("name"):
                tool_names.append(str(function_block.get("name")))
        if tool_names:
            # XML self-closing tag — Claude/DeepSeek treat structural tags
            # as metadata and don't reproduce them as text. Bare prose form
            # ("Read, Edit") triggers few-shot mimicry: the model writes
            # plain-text tool descriptions on the next turn instead of
            # invoking real tool_calls.
            joined_names = _truncate_text(
                ",".join(tool_names),
                max_chars=max(16, max_chars - 32),
                label="tool-call summary",
            ).replace("\n", " ").strip()
            return f'<prior-tool-calls names="{joined_names}"/>'

    content = _flatten_message_content(message.get("content", ""))
    if not content:
        return ""
    preview = " ".join(content.split())
    return _truncate_text(
        preview,
        max_chars=max_chars,
        label="collapsed summary",
    ).replace("\n", " ").strip()


def _collect_role_highlights(
    messages: list[dict[str, Any]],
    *,
    role: str,
    limit: int,
) -> list[str]:
    if limit <= 0:
        return []

    seen: set[str] = set()
    highlights: list[str] = []
    for message in reversed(messages):
        if message.get("role") != role:
            continue
        preview = _message_preview(message)
        if not preview or preview in seen:
            continue
        highlights.append(preview)
        seen.add(preview)
        if len(highlights) >= limit:
            break
    highlights.reverse()
    return highlights


def _build_collapse_summary(
    omitted_history: list[dict[str, Any]],
    *,
    metadata: dict[str, Any] | None,
    workspace: str | None,
    config: ContextCompactionConfig,
) -> str:
    lines = [
        (
            f"- {len(omitted_history)} earlier message(s) were compacted to keep the "
            "active prompt within budget."
        ),
        "- Preserve the prior user intent, tool references, and durable workspace state when continuing.",
    ]

    user_highlights = _collect_role_highlights(
        omitted_history,
        role="user",
        limit=config.max_highlights_per_role,
    )
    if user_highlights:
        lines.extend(("", "### Omitted User Goals"))
        lines.extend(f"- {item}" for item in user_highlights)

    assistant_highlights = _collect_role_highlights(
        omitted_history,
        role="assistant",
        limit=config.max_highlights_per_role,
    )
    if assistant_highlights:
        lines.extend(("", "### Omitted Assistant State"))
        lines.extend(f"- {item}" for item in assistant_highlights)

    structured_summary = build_transcript_summary(
        omitted_history,
        metadata=metadata,
        workspace=workspace,
    )
    replay_block = TranscriptReplaySummary(
        omitted_message_count=len(omitted_history),
        compacted_tool_results=structured_summary.compacted_tool_results[
            : config.max_compacted_refs
        ],
        plan_references=structured_summary.plan_references[: config.max_plan_refs],
        advisory_events=structured_summary.advisory_events[: config.max_advisory_refs],
    ).to_prompt_block()
    if replay_block:
        lines.extend(("", replay_block))

    return "\n".join(lines).strip()


def compact_history(
    messages: list[dict[str, Any]],
    *,
    preserve_messages: int,
    preserve_chars: int | None,
    config: ContextCompactionConfig,
    metadata: dict[str, Any] | None = None,
    workspace: str | None = None,
) -> "_CollapseResult":
    """Public entry point for on-demand transcript compaction.

    Returns a result with:
      * ``messages`` — the trimmed tail (preserved messages, sanitized).
      * ``summary`` — a deterministic, template-built summary of what was
        omitted (empty when nothing was compacted).
      * ``omitted_count`` — number of messages dropped from the head.

    No LLM call. Intended for slash-command surfaces (e.g. ``/compact``).
    """
    return _collapse_history(
        messages,
        preserve_messages=preserve_messages,
        preserve_chars=preserve_chars,
        metadata=metadata,
        workspace=workspace,
        config=config,
    )


def _collapse_history(
    messages: list[dict[str, Any]],
    *,
    preserve_messages: int,
    preserve_chars: int | None,
    metadata: dict[str, Any] | None,
    workspace: str | None,
    config: ContextCompactionConfig,
) -> _CollapseResult:
    sanitized = sanitize_tool_history(copy.deepcopy(messages), warn=False)
    trimmed = trim_history_to_budget(
        sanitized,
        max_messages=preserve_messages,
        max_chars=preserve_chars,
    )
    omitted_count = max(0, len(sanitized) - len(trimmed))
    if omitted_count <= 0:
        return _CollapseResult(messages=sanitized, summary="", omitted_count=0)

    omitted_history = sanitized[:omitted_count]
    summary = _build_collapse_summary(
        omitted_history,
        metadata=metadata,
        workspace=workspace,
        config=config,
    )
    return _CollapseResult(
        messages=trimmed,
        summary=summary,
        omitted_count=omitted_count,
    )


def prepare_model_messages(
    *,
    system_prompt: str,
    history: list[dict[str, Any]],
    chat_id: int | str,
    tool_result_store: ToolResultStore,
    config: ContextCompactionConfig,
    metadata: dict[str, Any] | None = None,
    workspace: str | None = None,
    force_reactive_compact: bool = False,
) -> PreparedModelMessages:
    messages = [copy.deepcopy(message) for message in history]
    prompt = str(system_prompt or "")
    if not config.enabled:
        return PreparedModelMessages(
            system_prompt=prompt,
            messages=messages,
            estimated_chars=estimate_prompt_chars(prompt, messages),
        )

    applied_stages: list[str] = []

    messages, snip_changed = _apply_snip_compaction(messages, config=config)
    if snip_changed:
        applied_stages.append(STAGE_SNIP_COMPACT)

    messages, micro_changed = _apply_micro_compaction(
        messages,
        chat_id=chat_id,
        tool_result_store=tool_result_store,
        config=config,
    )
    if micro_changed:
        applied_stages.append(STAGE_MICRO_COMPACT)

    if force_reactive_compact:
        reactive_result = _collapse_history(
            messages,
            preserve_messages=config.reactive_preserve_messages,
            preserve_chars=config.reactive_preserve_chars,
            metadata=metadata,
            workspace=workspace,
            config=config,
        )
        if reactive_result.omitted_count > 0:
            prompt = _append_system_summary(
                prompt,
                "## Reactive Compact Context",
                reactive_result.summary,
            )
            messages = reactive_result.messages
            applied_stages.append(STAGE_REACTIVE_COMPACT)
        return PreparedModelMessages(
            system_prompt=prompt,
            messages=messages,
            estimated_chars=estimate_prompt_chars(prompt, messages),
            applied_stages=tuple(applied_stages),
        )

    collapse_threshold = _threshold_chars(
        config.max_prompt_chars,
        config.collapse_trigger_ratio,
    )
    auto_threshold = _threshold_chars(
        config.max_prompt_chars,
        config.auto_compact_trigger_ratio,
    )

    current_chars = estimate_prompt_chars(prompt, messages)
    if collapse_threshold is not None and current_chars > collapse_threshold:
        collapse_result = _collapse_history(
            messages,
            preserve_messages=config.collapse_preserve_messages,
            preserve_chars=config.collapse_preserve_chars,
            metadata=metadata,
            workspace=workspace,
            config=config,
        )
        if collapse_result.omitted_count > 0:
            prompt = _append_system_summary(
                prompt,
                "## Context Collapse",
                collapse_result.summary,
            )
            messages = collapse_result.messages
            applied_stages.append(STAGE_CONTEXT_COLLAPSE)
            current_chars = estimate_prompt_chars(prompt, messages)

    if auto_threshold is not None and current_chars > auto_threshold:
        auto_result = _collapse_history(
            messages,
            preserve_messages=config.auto_compact_preserve_messages,
            preserve_chars=config.auto_compact_preserve_chars,
            metadata=metadata,
            workspace=workspace,
            config=config,
        )
        if auto_result.omitted_count > 0:
            prompt = _append_system_summary(
                prompt,
                "## Auto Compacted Context",
                auto_result.summary,
            )
            messages = auto_result.messages
            applied_stages.append(STAGE_AUTO_COMPACT)

    return PreparedModelMessages(
        system_prompt=prompt,
        messages=messages,
        estimated_chars=estimate_prompt_chars(prompt, messages),
        applied_stages=tuple(applied_stages),
    )
