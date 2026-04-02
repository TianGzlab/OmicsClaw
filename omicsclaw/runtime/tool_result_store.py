from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .policy import ToolPolicyDecision
from .tool_spec import (
    RESULT_POLICY_INLINE,
    RESULT_POLICY_INSPECTION_REFERENCE,
    RESULT_POLICY_KNOWLEDGE_REFERENCE,
    RESULT_POLICY_MEMORY_WRITE,
    RESULT_POLICY_SUMMARY_OR_MEDIA,
    RESULT_POLICY_WEB_REFERENCE,
    ToolSpec,
)


def _safe_name(value: int | str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("._-")
    return text or "item"


@dataclass(frozen=True, slots=True)
class ToolResultRecord:
    chat_id: int | str
    tool_call_id: str
    tool_name: str
    content: str
    success: bool
    stored_at: str
    output_bytes: int
    error_type: str = ""
    storage_path: str = ""
    is_compacted: bool = False
    result_policy: str = RESULT_POLICY_INLINE
    policy_action: str = ""
    policy_reason: str = ""


class ToolResultStore:
    """Tool-result store with optional file-backed compaction for large outputs."""

    def __init__(
        self,
        *,
        storage_dir: Path,
        inline_bytes: int = 6000,
        preview_chars: int = 1200,
    ) -> None:
        self.storage_dir = Path(storage_dir)
        self.inline_bytes = inline_bytes
        self.preview_chars = preview_chars
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.records_by_chat: dict[int | str, list[ToolResultRecord]] = {}
        self.policy_inline_bytes: dict[str, int] = {
            RESULT_POLICY_INLINE: self.inline_bytes,
            RESULT_POLICY_SUMMARY_OR_MEDIA: max(3200, min(self.inline_bytes, 5000)),
            RESULT_POLICY_MEMORY_WRITE: self.inline_bytes,
            RESULT_POLICY_KNOWLEDGE_REFERENCE: max(2200, min(self.inline_bytes, 3200)),
            RESULT_POLICY_INSPECTION_REFERENCE: max(1800, min(self.inline_bytes, 2600)),
            RESULT_POLICY_WEB_REFERENCE: max(1800, min(self.inline_bytes, 2800)),
        }
        self.policy_preview_chars: dict[str, int] = {
            RESULT_POLICY_INLINE: self.preview_chars,
            RESULT_POLICY_SUMMARY_OR_MEDIA: max(1200, min(self.preview_chars, 1800)),
            RESULT_POLICY_MEMORY_WRITE: self.preview_chars,
            RESULT_POLICY_KNOWLEDGE_REFERENCE: max(1000, min(self.preview_chars, 1500)),
            RESULT_POLICY_INSPECTION_REFERENCE: max(900, min(self.preview_chars, 1400)),
            RESULT_POLICY_WEB_REFERENCE: max(900, min(self.preview_chars, 1400)),
        }

    def clear(self, chat_id: int | str) -> None:
        self.records_by_chat.pop(chat_id, None)
        shutil.rmtree(self.storage_dir / _safe_name(chat_id), ignore_errors=True)

    def get_records(self, chat_id: int | str) -> list[ToolResultRecord]:
        return list(self.records_by_chat.get(chat_id, []))

    def load_full_content(self, record: ToolResultRecord) -> str:
        if record.storage_path:
            return Path(record.storage_path).read_text(encoding="utf-8")
        return record.content

    def _effective_result_policy(self, spec: ToolSpec | None) -> str:
        if spec is None:
            return RESULT_POLICY_INLINE
        policy = str(spec.result_policy or RESULT_POLICY_INLINE).strip()
        return policy or RESULT_POLICY_INLINE

    def _inline_bytes_for_policy(self, policy: str) -> int:
        return self.policy_inline_bytes.get(policy, self.inline_bytes)

    def _preview_chars_for_policy(self, policy: str) -> int:
        return self.policy_preview_chars.get(policy, self.preview_chars)

    def _build_preview(self, content: str, *, preview_chars: int) -> str:
        if preview_chars <= 0 or len(content) <= preview_chars:
            return content
        if preview_chars < 80:
            return content[:preview_chars]

        head_chars = int(preview_chars * 0.7)
        tail_chars = max(0, preview_chars - head_chars)
        head = content[:head_chars].rstrip()
        tail = ""
        if tail_chars:
            lines = content.splitlines()
            if len(lines) > 1:
                source_lines = [line for line in lines if line.strip()] or lines
                source_lines = source_lines[-3:]
                rendered: list[str] = []
                slot_count = len(source_lines)
                base_budget = max(16, tail_chars // max(1, slot_count))
                for index, line in enumerate(source_lines):
                    used = sum(len(item) for item in rendered) + max(0, len(rendered))
                    remaining_lines = slot_count - index - 1
                    remaining_floor = remaining_lines * 8
                    max_line_chars = max(16, tail_chars - used - remaining_floor)
                    line_budget = max(16, min(max_line_chars, max(base_budget, 16)))
                    candidate = line
                    if len(candidate) > line_budget:
                        candidate = "..." + candidate[-(line_budget - 3):]
                    rendered.append(candidate)
                tail = "\n".join(rendered).lstrip()
            else:
                tail = content[-tail_chars:].lstrip()
        if not tail:
            return head
        return f"{head}\n...\n{tail}"

    def record(
        self,
        *,
        chat_id: int | str,
        tool_call_id: str,
        tool_name: str,
        output: Any,
        success: bool,
        error: Exception | None = None,
        spec: ToolSpec | None = None,
        policy_decision: ToolPolicyDecision | None = None,
    ) -> ToolResultRecord:
        raw_content = str(output)
        output_bytes = len(raw_content.encode("utf-8"))
        storage_path = ""
        content = raw_content
        result_policy = self._effective_result_policy(spec)
        is_compacted = output_bytes > self._inline_bytes_for_policy(result_policy)

        if is_compacted:
            storage_path = str(
                self._persist_result(
                    chat_id=chat_id,
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    content=raw_content,
                )
            )
            content = self._build_compact_reference(
                tool_name=tool_name,
                output_bytes=output_bytes,
                storage_path=storage_path,
                result_policy=result_policy,
                preview=self._build_preview(
                    raw_content,
                    preview_chars=self._preview_chars_for_policy(result_policy),
                ),
            )

        record = ToolResultRecord(
            chat_id=chat_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            content=content,
            success=success,
            stored_at=datetime.now(timezone.utc).isoformat(),
            output_bytes=output_bytes,
            error_type=type(error).__name__ if error else "",
            storage_path=storage_path,
            is_compacted=is_compacted,
            result_policy=result_policy,
            policy_action=policy_decision.action if policy_decision else "",
            policy_reason=policy_decision.reason if policy_decision else "",
        )
        self.records_by_chat.setdefault(chat_id, []).append(record)
        return record

    def _persist_result(
        self,
        *,
        chat_id: int | str,
        tool_call_id: str,
        tool_name: str,
        content: str,
    ) -> Path:
        chat_dir = self.storage_dir / _safe_name(chat_id)
        chat_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"{ts}_{_safe_name(tool_name)}_{_safe_name(tool_call_id)}.txt"
        path = chat_dir / filename
        path.write_text(content, encoding="utf-8")
        return path

    def _build_compact_reference(
        self,
        *,
        tool_name: str,
        output_bytes: int,
        storage_path: str,
        result_policy: str,
        preview: str,
    ) -> str:
        return (
            "[tool result compacted]\n"
            f"tool: {tool_name}\n"
            f"policy: {result_policy}\n"
            f"bytes: {output_bytes}\n"
            f"full_result_path: {storage_path}\n"
            "preview:\n"
            f"{preview}"
        )
