"""Shared bridge helpers between interactive surfaces and bot.core."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from omicsclaw.runtime.transcript_store import sanitize_tool_history


@dataclass(frozen=True, slots=True)
class UsageDelta:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    api_calls: int = 0
    estimated_cost_usd: float = 0.0
    model: str = ""
    provider: str = ""
    input_price_per_1m: float = 0.0
    output_price_per_1m: float = 0.0

    @property
    def has_usage(self) -> bool:
        return any(
            (
                self.prompt_tokens > 0,
                self.completion_tokens > 0,
                self.total_tokens > 0,
                self.api_calls > 0,
            )
        )


def _extract_user_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            str(block.get("text", "") or "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
    return str(content or "")


def seed_core_conversation(
    core_module,
    conversation_id: int | str,
    messages: list[dict],
    *,
    touched_at: float | None = None,
) -> str:
    seed = sanitize_tool_history(
        list(messages[:-1]) if len(messages) > 1 else [],
        warn=False,
    )
    core_module.conversations[conversation_id] = seed
    core_module._conversation_access[conversation_id] = (
        time.time() if touched_at is None else touched_at
    )
    if not messages:
        return ""
    return _extract_user_text(messages[-1].get("content", ""))


def sync_core_conversation(
    core_module,
    conversation_id: int | str,
    messages: list[dict] | None = None,
) -> list[dict]:
    updated = sanitize_tool_history(
        list(core_module.conversations.get(conversation_id, [])),
        warn=False,
    )
    core_module.conversations[conversation_id] = list(updated)
    if messages is not None:
        messages.clear()
        messages.extend(updated)
    return updated


def append_interruption_notice(
    core_module,
    conversation_id: int | str,
    *,
    text: str,
    messages: list[dict] | None = None,
) -> list[dict]:
    updated = sync_core_conversation(core_module, conversation_id)
    updated.append({"role": "user", "content": text})
    core_module.conversations[conversation_id] = list(updated)
    if messages is not None:
        messages.clear()
        messages.extend(updated)
    return updated


def build_usage_delta(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> UsageDelta:
    before_snapshot = dict(before or {})
    after_snapshot = dict(after or {})
    prompt_tokens = max(
        0,
        int(after_snapshot.get("prompt_tokens", 0) or 0)
        - int(before_snapshot.get("prompt_tokens", 0) or 0),
    )
    completion_tokens = max(
        0,
        int(after_snapshot.get("completion_tokens", 0) or 0)
        - int(before_snapshot.get("completion_tokens", 0) or 0),
    )
    total_tokens = max(
        0,
        int(after_snapshot.get("total_tokens", 0) or 0)
        - int(before_snapshot.get("total_tokens", 0) or 0),
    )
    api_calls = max(
        0,
        int(after_snapshot.get("api_calls", 0) or 0)
        - int(before_snapshot.get("api_calls", 0) or 0),
    )
    estimated_cost_usd = max(
        0.0,
        float(after_snapshot.get("estimated_cost_usd", 0.0) or 0.0)
        - float(before_snapshot.get("estimated_cost_usd", 0.0) or 0.0),
    )
    if estimated_cost_usd <= 0:
        estimated_cost_usd = (
            prompt_tokens / 1_000_000 * float(after_snapshot.get("input_price_per_1m", 0.0) or 0.0)
            + completion_tokens / 1_000_000 * float(after_snapshot.get("output_price_per_1m", 0.0) or 0.0)
        )

    return UsageDelta(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        api_calls=api_calls,
        estimated_cost_usd=estimated_cost_usd,
        model=str(after_snapshot.get("model", "") or ""),
        provider=str(after_snapshot.get("provider", "") or ""),
        input_price_per_1m=float(after_snapshot.get("input_price_per_1m", 0.0) or 0.0),
        output_price_per_1m=float(after_snapshot.get("output_price_per_1m", 0.0) or 0.0),
    )
