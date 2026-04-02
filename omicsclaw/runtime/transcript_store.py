from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any, Callable

from .context_budget import trim_history_to_budget

def sanitize_tool_history(history: list[dict], warn: bool = True) -> list[dict]:
    """Drop orphaned or incomplete tool-call bundles from history."""
    sanitised: list[dict] = []
    pending_bundle: list[dict] | None = None
    pending_tool_ids: set[str] = set()

    def flush_pending(drop_incomplete: bool) -> None:
        nonlocal pending_bundle, pending_tool_ids
        if pending_bundle is None:
            return
        if not (drop_incomplete and pending_tool_ids):
            sanitised.extend(pending_bundle)
        pending_bundle = None
        pending_tool_ids = set()

    for msg in history:
        role = msg.get("role")

        if role == "assistant" and msg.get("tool_calls"):
            flush_pending(drop_incomplete=True)
            pending_bundle = [msg]
            pending_tool_ids = {
                tc.get("id")
                for tc in msg.get("tool_calls", [])
                if isinstance(tc, dict) and tc.get("id")
            }
            continue

        if role == "tool":
            tool_call_id = msg.get("tool_call_id")
            if pending_bundle is not None and tool_call_id in pending_tool_ids:
                pending_bundle.append(msg)
                pending_tool_ids.remove(tool_call_id)
                if not pending_tool_ids:
                    flush_pending(drop_incomplete=False)
                continue
            continue

        flush_pending(drop_incomplete=True)
        sanitised.append(msg)

    flush_pending(drop_incomplete=True)
    return sanitised


@dataclass(frozen=True, slots=True)
class CompactedToolResultRef:
    tool_call_id: str
    tool_name: str
    storage_path: str
    output_bytes: int = 0


@dataclass(frozen=True, slots=True)
class PlanReference:
    path: str
    workspace: str = ""
    exists: bool = False


@dataclass(frozen=True, slots=True)
class AdvisoryEventRef:
    message: str
    role: str = "assistant"
    index: int = 0
    kind: str = "advisory"


@dataclass(frozen=True, slots=True)
class TranscriptSummary:
    compacted_tool_results: tuple[CompactedToolResultRef, ...] = ()
    plan_references: tuple[PlanReference, ...] = ()
    advisory_events: tuple[AdvisoryEventRef, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "compacted_tool_results": [
                {
                    "tool_call_id": ref.tool_call_id,
                    "tool_name": ref.tool_name,
                    "storage_path": ref.storage_path,
                    "output_bytes": ref.output_bytes,
                }
                for ref in self.compacted_tool_results
            ],
            "plan_references": [
                {
                    "path": ref.path,
                    "workspace": ref.workspace,
                    "exists": ref.exists,
                }
                for ref in self.plan_references
            ],
            "advisory_events": [
                {
                    "message": ref.message,
                    "role": ref.role,
                    "index": ref.index,
                    "kind": ref.kind,
                }
                for ref in self.advisory_events
            ],
        }


@dataclass(frozen=True, slots=True)
class TranscriptReplaySummary:
    omitted_message_count: int = 0
    compacted_tool_results: tuple[CompactedToolResultRef, ...] = ()
    plan_references: tuple[PlanReference, ...] = ()
    advisory_events: tuple[AdvisoryEventRef, ...] = ()

    def to_prompt_block(self) -> str:
        if (
            self.omitted_message_count <= 0
            or not any(
                (
                    self.compacted_tool_results,
                    self.plan_references,
                    self.advisory_events,
                )
            )
        ):
            return ""

        lines = [
            "## Selective Transcript Replay",
            "",
            (
                f"- {self.omitted_message_count} older message(s) are outside the active context window."
            ),
            "- Preserve these durable references when the user revisits prior work.",
        ]
        if self.compacted_tool_results:
            lines.extend(("", "### Omitted Tool Result References"))
            for ref in self.compacted_tool_results:
                detail = (
                    f"- {ref.tool_name or 'tool'}"
                    f" (`{ref.tool_call_id or 'unknown'}`)"
                    f" -> `{ref.storage_path}`"
                )
                if ref.output_bytes > 0:
                    detail += f" ({ref.output_bytes} bytes)"
                lines.append(detail)
        if self.plan_references:
            lines.extend(("", "### Omitted Plan References"))
            for ref in self.plan_references:
                status = "exists" if ref.exists else "missing"
                line = f"- `{ref.path}` ({status})"
                if ref.workspace:
                    line += f" in workspace `{ref.workspace}`"
                lines.append(line)
        if self.advisory_events:
            lines.extend(("", "### Omitted Advisory Highlights"))
            for ref in self.advisory_events:
                lines.append(f"- {ref.message}")
        return "\n".join(lines).strip()


def extract_compacted_tool_result_refs(
    history: list[dict],
) -> list[CompactedToolResultRef]:
    refs: list[CompactedToolResultRef] = []

    for message in history:
        if message.get("role") != "tool":
            continue

        content = str(message.get("content", "") or "")
        lines = content.splitlines()
        if not lines or lines[0].strip() != "[tool result compacted]":
            continue

        fields: dict[str, str] = {}
        for line in lines[1:]:
            if line.strip() == "preview:":
                break
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()

        storage_path = fields.get("full_result_path", "")
        if not storage_path:
            continue

        try:
            output_bytes = int(fields.get("bytes", "0") or 0)
        except ValueError:
            output_bytes = 0

        refs.append(
            CompactedToolResultRef(
                tool_call_id=str(message.get("tool_call_id", "") or ""),
                tool_name=fields.get("tool", ""),
                storage_path=storage_path,
                output_bytes=output_bytes,
            )
        )

    return refs


def _flatten_message_content(content: Any) -> str:
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "") or ""))
            elif block is not None:
                parts.append(str(block))
        return " ".join(part for part in parts if part.strip()).strip()
    return str(content or "").strip()


def extract_advisory_event_refs(
    history: list[dict],
) -> list[AdvisoryEventRef]:
    refs: list[AdvisoryEventRef] = []
    seen: set[tuple[str, str]] = set()

    for index, message in enumerate(history):
        role = str(message.get("role", "") or "")
        if role != "assistant":
            continue
        content = _flatten_message_content(message.get("content", ""))
        if not content:
            continue

        stripped = content.strip()
        if (
            "💡 Advice:" not in stripped
            and not stripped.startswith("💡 ")
            and not stripped.startswith("Advice:")
        ):
            continue

        preview = stripped[:280]
        key = (role, preview)
        if key in seen:
            continue
        seen.add(key)
        refs.append(
            AdvisoryEventRef(
                message=preview,
                role=role,
                index=index,
            )
        )

    return refs


def extract_plan_references(
    *,
    metadata: dict[str, Any] | None = None,
    workspace: str | None = None,
) -> list[PlanReference]:
    refs: list[PlanReference] = []
    seen: set[str] = set()

    pipeline_workspace = str((metadata or {}).get("pipeline_workspace", "") or "").strip()
    candidates = [pipeline_workspace] if pipeline_workspace else [str(workspace or "").strip()]
    for candidate in candidates:
        if not candidate:
            continue
        workspace_path = Path(candidate).expanduser().resolve()
        plan_path = workspace_path / "plan.md"
        key = str(plan_path)
        if key in seen:
            continue
        seen.add(key)
        refs.append(
            PlanReference(
                path=key,
                workspace=str(workspace_path),
                exists=plan_path.exists(),
            )
        )

    return refs


def build_transcript_summary(
    history: list[dict],
    *,
    metadata: dict[str, Any] | None = None,
    workspace: str | None = None,
) -> TranscriptSummary:
    return TranscriptSummary(
        compacted_tool_results=tuple(extract_compacted_tool_result_refs(history)),
        plan_references=tuple(
            extract_plan_references(
                metadata=metadata,
                workspace=workspace,
            )
        ),
        advisory_events=tuple(extract_advisory_event_refs(history)),
    )


def build_selective_replay_summary(
    history: list[dict],
    *,
    metadata: dict[str, Any] | None = None,
    workspace: str | None = None,
    max_messages: int = 50,
    max_chars: int | None = None,
    max_compacted_refs: int = 3,
    max_plan_refs: int = 2,
    max_advisory_refs: int = 3,
    sanitizer: Callable[[list[dict], bool], list[dict]] = sanitize_tool_history,
) -> TranscriptReplaySummary:
    sanitized = sanitizer(list(history), warn=False)
    trimmed = trim_history_to_budget(
        sanitized,
        max_messages=max_messages,
        max_chars=max_chars,
    )
    omitted_count = max(0, len(sanitized) - len(trimmed))
    if omitted_count <= 0:
        return TranscriptReplaySummary()

    omitted_history = sanitized[:omitted_count]
    summary = build_transcript_summary(
        omitted_history,
        metadata=metadata,
        workspace=workspace,
    )
    return TranscriptReplaySummary(
        omitted_message_count=omitted_count,
        compacted_tool_results=summary.compacted_tool_results[:max_compacted_refs],
        plan_references=summary.plan_references[:max_plan_refs],
        advisory_events=summary.advisory_events[:max_advisory_refs],
    )


def build_selective_replay_context(
    history: list[dict],
    *,
    metadata: dict[str, Any] | None = None,
    workspace: str | None = None,
    max_messages: int = 50,
    max_chars: int | None = None,
    max_compacted_refs: int = 3,
    max_plan_refs: int = 2,
    max_advisory_refs: int = 3,
    sanitizer: Callable[[list[dict], bool], list[dict]] = sanitize_tool_history,
) -> str:
    summary = build_selective_replay_summary(
        history,
        metadata=metadata,
        workspace=workspace,
        max_messages=max_messages,
        max_chars=max_chars,
        max_compacted_refs=max_compacted_refs,
        max_plan_refs=max_plan_refs,
        max_advisory_refs=max_advisory_refs,
        sanitizer=sanitizer,
    )
    return summary.to_prompt_block()


class TranscriptStore:
    """In-memory transcript store with bounded history and LRU eviction."""

    def __init__(
        self,
        *,
        max_history: int = 50,
        max_history_chars: int | None = None,
        max_conversations: int = 1000,
        sanitizer: Callable[[list[dict], bool], list[dict]] = sanitize_tool_history,
    ) -> None:
        self.max_history = max_history
        self.max_history_chars = max_history_chars
        self.max_conversations = max_conversations
        self.sanitizer = sanitizer
        self.messages_by_chat: dict[int | str, list[dict]] = {}
        self.access_by_chat: dict[int | str, float] = {}

    @property
    def active_conversation_count(self) -> int:
        return len(self.messages_by_chat)

    def get_or_create(self, chat_id: int | str) -> list[dict]:
        return self.messages_by_chat.setdefault(chat_id, [])

    def get_history(self, chat_id: int | str) -> list[dict]:
        return self.get_or_create(chat_id)

    def clear(self, chat_id: int | str) -> None:
        self.messages_by_chat.pop(chat_id, None)
        self.access_by_chat.pop(chat_id, None)

    def touch(self, chat_id: int | str, *, at: float | None = None) -> None:
        self.access_by_chat[chat_id] = time.time() if at is None else at

    def evict_lru_conversations(self) -> list[int | str]:
        if len(self.messages_by_chat) <= self.max_conversations:
            return []
        sorted_keys = sorted(self.access_by_chat, key=self.access_by_chat.get)
        to_evict = len(self.messages_by_chat) - self.max_conversations
        evicted = sorted_keys[:to_evict]
        for key in evicted:
            self.messages_by_chat.pop(key, None)
            self.access_by_chat.pop(key, None)
        return evicted

    def append_user_message(self, chat_id: int | str, content: Any) -> dict:
        message = {"role": "user", "content": content}
        self.get_or_create(chat_id).append(message)
        return message

    def append_assistant_message(
        self,
        chat_id: int | str,
        *,
        content: str,
        tool_calls: list[dict] | None = None,
    ) -> dict:
        message: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            message["tool_calls"] = tool_calls
        self.get_or_create(chat_id).append(message)
        return message

    def append_tool_message(
        self,
        chat_id: int | str,
        *,
        tool_call_id: str,
        content: str,
    ) -> dict:
        message = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        }
        self.get_or_create(chat_id).append(message)
        return message

    def prepare_history(self, chat_id: int | str, *, warn: bool = True) -> list[dict]:
        history = self.get_or_create(chat_id)
        history[:] = self.sanitizer(list(history), warn=warn)
        return trim_history_to_budget(
            history,
            max_messages=self.max_history,
            max_chars=self.max_history_chars,
        )

    def build_replay_context(
        self,
        chat_id: int | str,
        *,
        metadata: dict[str, Any] | None = None,
        workspace: str | None = None,
        max_compacted_refs: int = 3,
        max_plan_refs: int = 2,
        max_advisory_refs: int = 3,
    ) -> str:
        return build_selective_replay_context(
            self.get_or_create(chat_id),
            metadata=metadata,
            workspace=workspace,
            max_messages=self.max_history,
            max_chars=self.max_history_chars,
            max_compacted_refs=max_compacted_refs,
            max_plan_refs=max_plan_refs,
            max_advisory_refs=max_advisory_refs,
            sanitizer=self.sanitizer,
        )
