from __future__ import annotations

from typing import Any


def estimate_message_size(message: dict[str, Any]) -> int:
    """Approximate one transcript message's budget footprint."""
    size = len(str(message.get("role", "") or ""))

    content = message.get("content", "")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                size += len(str(block.get("type", "") or ""))
                size += len(str(block.get("text", "") or ""))
            else:
                size += len(str(block))
    else:
        size += len(str(content or ""))

    for tool_call in message.get("tool_calls", []) or []:
        if not isinstance(tool_call, dict):
            size += len(str(tool_call))
            continue
        size += len(str(tool_call.get("id", "") or ""))
        size += len(str(tool_call.get("type", "") or ""))
        function_block = tool_call.get("function", {}) or {}
        if isinstance(function_block, dict):
            size += len(str(function_block.get("name", "") or ""))
            size += len(str(function_block.get("arguments", "") or ""))
        else:
            size += len(str(function_block))

    size += len(str(message.get("tool_call_id", "") or ""))
    size += len(str(message.get("reasoning_content", "") or ""))
    return size


def _group_history_blocks(history: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    blocks: list[list[dict[str, Any]]] = []
    index = 0
    while index < len(history):
        message = history[index]
        if message.get("role") == "assistant" and message.get("tool_calls"):
            block = [message]
            index += 1
            while index < len(history) and history[index].get("role") == "tool":
                block.append(history[index])
                index += 1
            blocks.append(block)
            continue

        blocks.append([message])
        index += 1
    return blocks


def trim_history_to_budget(
    history: list[dict[str, Any]],
    *,
    max_messages: int = 50,
    max_chars: int | None = None,
) -> list[dict[str, Any]]:
    """Return the newest contiguous history suffix that fits the current budget.

    The budget is block-aware: assistant tool-call messages stay grouped with their
    following tool results so truncation does not split bundles in the middle.
    """
    if not history:
        return []
    if max_messages == 0:
        return []

    char_budget = max_chars if max_chars and max_chars > 0 else None
    blocks = _group_history_blocks(history)

    selected_reversed: list[list[dict[str, Any]]] = []
    selected_message_count = 0
    selected_chars = 0

    for block in reversed(blocks):
        block_message_count = len(block)
        block_chars = sum(estimate_message_size(message) for message in block)
        fits_messages = max_messages < 0 or (selected_message_count + block_message_count) <= max_messages
        fits_chars = char_budget is None or (selected_chars + block_chars) <= char_budget

        if selected_reversed:
            if not (fits_messages and fits_chars):
                break
        elif not (fits_messages and fits_chars):
            # Always preserve the newest block so the model still sees the
            # active turn, even when the configured budget is very small.
            selected_reversed.append(block)
            break

        if not selected_reversed or (fits_messages and fits_chars):
            selected_reversed.append(block)
            selected_message_count += block_message_count
            selected_chars += block_chars

    trimmed: list[dict[str, Any]] = []
    for block in reversed(selected_reversed):
        trimmed.extend(block)
    return trimmed
