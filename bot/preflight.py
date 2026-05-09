"""Preflight question-loop state machine.

Carved out of ``bot/core.py`` per ADR 0001. When a Skill needs missing
input parameters before it can run, the agent surfaces a structured
"needs_user_input" payload; this module parses the user's reply, applies
resolved answers back to the original tool args, and renders the next
pending-field message. Pure-Python; no I/O, no LLM client, no network.

The mutable bookkeeping dict ``pending_preflight_requests`` is owned by
``bot.core`` (multiple modules touch it across the agent loop), so
``_remember_pending_preflight_request`` late-imports it inside the
function to avoid a load-order circular.
"""

from __future__ import annotations

import copy
import re

from omicsclaw.runtime.query_engine import (
    extract_user_guidance_payloads,
    render_guidance_block,
)


# Top-level keys that go directly onto the tool args, as opposed to being
# pushed into the ``extra_args`` flag list.
_PREFLIGHT_TOP_LEVEL_ARGS: set[str] = {
    "skill",
    "mode",
    "method",
    "file_path",
    "data_type",
    "n_epochs",
    "return_media",
}


def _strip_answer_prefix(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^\s*(?:[-*]\s+|\d+\.\s+)", "", cleaned)
    return cleaned.strip()


def _coerce_preflight_value(value: str, value_type: str) -> object:
    text = _strip_answer_prefix(value)
    if value_type == "integer":
        return int(text)
    if value_type == "number":
        return float(text)
    if value_type == "boolean":
        lowered = text.lower()
        if lowered in {"yes", "y", "true", "1", "ok", "okay", "accept"}:
            return True
        if lowered in {"no", "n", "false", "0", "reject"}:
            return False
    return text


def _set_or_replace_extra_arg(extra_args: list[str], flag: str, value: object) -> list[str]:
    updated: list[str] = []
    i = 0
    while i < len(extra_args):
        token = str(extra_args[i])
        if token == flag:
            i += 2
            continue
        if token.startswith(flag + "="):
            i += 1
            continue
        updated.append(token)
        i += 1
    if isinstance(value, bool):
        if value:
            updated.append(flag)
    else:
        updated.extend([flag, str(value)])
    return updated


def _parse_preflight_reply(state: dict, user_text: str) -> tuple[dict[str, object], list[dict]]:
    pending_fields = list(state.get("pending_fields", []) or [])
    existing_answers = dict(state.get("answers", {}) or {})
    text = str(user_text or "").strip()
    resolved = dict(existing_answers)
    lowered = text.lower()

    segments: list[str] = []
    for chunk in re.split(r"[\n;]+", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" in chunk or ":" in chunk:
            segments.extend([piece.strip() for piece in chunk.split(",") if piece.strip()])
        else:
            segments.append(chunk)

    for field in pending_fields:
        key = str(field.get("key", "") or "")
        if not key or key in resolved:
            continue
        aliases = [str(item).lower() for item in field.get("aliases", []) if str(item).strip()]
        value_type = str(field.get("value_type", "string") or "string")
        for segment in segments:
            if "=" in segment:
                left, right = segment.split("=", 1)
            elif ":" in segment:
                left, right = segment.split(":", 1)
            else:
                continue
            left_norm = left.strip().lstrip("-").replace("-", "_").lower()
            if left_norm in aliases:
                resolved[key] = _coerce_preflight_value(right, value_type)
                break
            if any(left_norm == alias.replace("-", "_") for alias in aliases):
                resolved[key] = _coerce_preflight_value(right, value_type)
                break

    for field in pending_fields:
        key = str(field.get("key", "") or "")
        if not key or key in resolved:
            continue
        choices = [str(choice) for choice in field.get("choices", []) if str(choice).strip()]
        if choices:
            for choice in choices:
                pattern = rf"(?<![a-z0-9_]){re.escape(choice.lower())}(?![a-z0-9_])"
                if re.search(pattern, lowered):
                    resolved[key] = _coerce_preflight_value(choice, str(field.get("value_type", "string") or "string"))
                    break

    unresolved = [field for field in pending_fields if str(field.get("key", "") or "") not in resolved]

    if unresolved:
        ordered_lines = [_strip_answer_prefix(line) for line in re.split(r"[\n;]+", text) if _strip_answer_prefix(line)]
        if len(unresolved) == 1 and ordered_lines and not any(("=" in line or ":" in line) for line in ordered_lines):
            field = unresolved[0]
            resolved[str(field.get("key", "") or "")] = _coerce_preflight_value(
                ordered_lines[-1],
                str(field.get("value_type", "string") or "string"),
            )
        elif len(ordered_lines) >= len(unresolved) and not any(("=" in line or ":" in line) for line in ordered_lines):
            for field, line in zip(unresolved, ordered_lines, strict=False):
                resolved[str(field.get("key", "") or "")] = _coerce_preflight_value(
                    line,
                    str(field.get("value_type", "string") or "string"),
                )

    remaining = [field for field in pending_fields if str(field.get("key", "") or "") not in resolved]
    return resolved, remaining


def _apply_preflight_answers(original_args: dict, pending_fields: list[dict], answers: dict[str, object]) -> dict:
    updated_args = copy.deepcopy(original_args)
    extra_args = list(updated_args.get("extra_args", []) or [])
    field_map = {
        str(field.get("key", "") or ""): field
        for field in pending_fields
        if str(field.get("key", "") or "")
    }
    for key, value in answers.items():
        field = field_map.get(key, {})
        flag = str(field.get("flag", "") or "").strip()
        if key in _PREFLIGHT_TOP_LEVEL_ARGS:
            updated_args[key] = value
            continue
        if key.startswith("allow_"):
            continue
        if flag:
            extra_args = _set_or_replace_extra_arg(extra_args, flag, value)
    if extra_args:
        updated_args["extra_args"] = extra_args
    return updated_args


def _build_pending_preflight_message(
    state: dict,
    *,
    answered: dict[str, object] | None = None,
    remaining_fields: list[dict] | None = None,
) -> str:
    payload = dict(state.get("payload", {}) or {})
    if remaining_fields is not None:
        remaining_keys = {str(field.get("key", "") or "") for field in remaining_fields}
        payload["pending_fields"] = remaining_fields
        payload["confirmations"] = [
            str(field.get("prompt", "") or "").strip()
            for field in remaining_fields
            if str(field.get("prompt", "") or "").strip()
        ]
        payload["status"] = "needs_user_input" if payload["confirmations"] else payload.get("status", "needs_user_input")
        if payload.get("missing_requirements") and not remaining_keys:
            payload["missing_requirements"] = list(payload.get("missing_requirements", []))
    block = render_guidance_block([], payloads=[payload]) or ""
    if answered:
        accepted = "\n".join(f"- `{key}` = {value}" for key, value in answered.items())
        if accepted:
            return f"## Accepted answers\n\n{accepted}\n\n---\n{block}".strip()
    return block


def _extract_pending_preflight_payload(result_text: str) -> dict | None:
    payloads = extract_user_guidance_payloads(result_text)
    relevant = [
        payload
        for payload in payloads
        if payload.get("kind") == "preflight" and payload.get("status") in {"needs_user_input", "blocked"}
    ]
    return relevant[-1] if relevant else None


def _preflight_payload_needs_reply(payload: dict | None) -> bool:
    if not payload or payload.get("status") != "needs_user_input":
        return False
    return bool(payload.get("pending_fields") or payload.get("confirmations"))


def _remember_pending_preflight_request(
    chat_id: int | str,
    *,
    args: dict,
    payload: dict,
) -> None:
    """Late-imports ``pending_preflight_requests`` from ``bot.core`` to
    avoid a load-order circular."""
    from bot.core import pending_preflight_requests

    pending_preflight_requests[chat_id] = {
        "tool_name": "omicsclaw",
        "original_args": copy.deepcopy(args),
        "payload": payload,
        "pending_fields": list(payload.get("pending_fields", []) or []),
        "answers": {},
    }


def _is_affirmative_preflight_confirmation(user_text: str) -> bool:
    text = _strip_answer_prefix(user_text).strip().lower()
    if not text:
        return False
    negative_markers = (
        "no",
        "not",
        "don't",
        "dont",
        "do not",
        "cancel",
        "stop",
        "reject",
        "先",
        "不要",
        "别",
        "不继续",
        "取消",
        "停止",
        "先跑",
    )
    if any(marker in text for marker in negative_markers):
        return False
    affirmative_markers = (
        "yes",
        "y",
        "ok",
        "okay",
        "confirm",
        "confirmed",
        "accept",
        "continue",
        "proceed",
        "go ahead",
        "use default",
        "default threshold",
        "默认",
        "确认",
        "可以",
        "继续",
        "接受",
        "同意",
        "用默认",
    )
    return any(marker in text for marker in affirmative_markers)
