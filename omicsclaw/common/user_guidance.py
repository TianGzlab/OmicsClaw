"""Helpers for emitting and extracting user-facing guidance across subprocess skills."""

from __future__ import annotations

import json
import logging

USER_GUIDANCE_PREFIX = "USER_GUIDANCE:"
USER_GUIDANCE_JSON_PREFIX = "USER_GUIDANCE_JSON:"


def format_user_guidance(message: str) -> str:
    text = str(message or "").strip()
    return f"{USER_GUIDANCE_PREFIX} {text}" if text else USER_GUIDANCE_PREFIX


def emit_user_guidance(logger: logging.Logger, message: str) -> None:
    """Emit a user-facing advisory line through standard logging channels."""
    logger.warning(format_user_guidance(message))


def format_user_guidance_payload(payload: dict) -> str:
    """Serialize a structured user-guidance payload onto one log line."""
    return f"{USER_GUIDANCE_JSON_PREFIX} {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"


def emit_user_guidance_payload(logger: logging.Logger, payload: dict) -> None:
    """Emit a structured user-guidance payload through standard logging channels."""
    logger.warning(format_user_guidance_payload(payload))


def extract_user_guidance_lines(text: str | None) -> list[str]:
    """Extract structured user-guidance lines from stderr/stdout text."""
    if not text:
        return []
    lines: list[str] = []
    for raw in str(text).splitlines():
        if USER_GUIDANCE_PREFIX not in raw:
            continue
        _, _, tail = raw.partition(USER_GUIDANCE_PREFIX)
        cleaned = tail.strip(" :-\t")
        if cleaned:
            lines.append(cleaned)
    return lines


def extract_user_guidance_payloads(text: str | None) -> list[dict]:
    """Extract structured user-guidance payloads from stderr/stdout text."""
    if not text:
        return []
    payloads: list[dict] = []
    for raw in str(text).splitlines():
        if USER_GUIDANCE_JSON_PREFIX not in raw:
            continue
        _, _, tail = raw.partition(USER_GUIDANCE_JSON_PREFIX)
        tail = tail.strip()
        if not tail:
            continue
        try:
            parsed = json.loads(tail)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            payloads.append(parsed)
    return payloads


def strip_user_guidance_lines(text: str | None) -> str:
    """Remove structured guidance lines from a stderr/stdout blob."""
    if not text:
        return ""
    kept = [
        line
        for line in str(text).splitlines()
        if USER_GUIDANCE_PREFIX not in line and USER_GUIDANCE_JSON_PREFIX not in line
    ]
    return "\n".join(kept).strip()


def _render_guidance_payload(payload: dict, *, title: str = "Important follow-up") -> str:
    confirmations = [str(item).strip() for item in payload.get("confirmations", []) if str(item).strip()]
    blockers = [str(item).strip() for item in payload.get("missing_requirements", []) if str(item).strip()]
    guidance = [str(item).strip() for item in payload.get("guidance", []) if str(item).strip()]

    sections: list[str] = []
    if confirmations:
        questions = []
        for idx, line in enumerate(confirmations, start=1):
            text = line.rstrip(". ")
            if not text.endswith("?"):
                text += "?"
            questions.append(f"{idx}. {text}")
        sections.append("## Before I run this, please confirm\n\n" + "\n".join(questions))
    if blockers:
        bullets = "\n".join(f"- {line}" for line in blockers)
        sections.append("## I Need This First\n\n" + bullets)
    if guidance:
        bullets = "\n".join(f"- {line}" for line in guidance)
        sections.append(f"## {title}\n\n" + bullets)
    return "\n\n".join(sections).strip()


def render_guidance_block(lines: list[str], *, title: str = "Important follow-up", payloads: list[dict] | None = None) -> str:
    """Render extracted guidance lines into a compact markdown block."""
    if payloads:
        best = payloads[-1]
        rendered = _render_guidance_payload(best, title=title)
        if rendered:
            return rendered

    cleaned = [str(line).strip() for line in lines if str(line).strip()]
    if not cleaned:
        return ""
    confirmations = [line.removeprefix("User confirmation required:").strip() for line in cleaned if line.startswith("User confirmation required:")]
    blockers = [line.removeprefix("Cannot continue yet:").strip() for line in cleaned if line.startswith("Cannot continue yet:")]
    general = [line for line in cleaned if not line.startswith("User confirmation required:") and not line.startswith("Cannot continue yet:")]

    sections: list[str] = []
    if confirmations:
        questions = []
        for idx, line in enumerate(confirmations, start=1):
            text = line.rstrip(". ")
            if not text.endswith("?"):
                text += "?"
            questions.append(f"{idx}. {text}")
        sections.append("## Before I run this, please confirm\n\n" + "\n".join(questions))
    if blockers:
        bullets = "\n".join(f"- {line}" for line in blockers)
        sections.append("## I Need This First\n\n" + bullets)
    if general:
        bullets = "\n".join(f"- {line}" for line in general)
        sections.append(f"## {title}\n\n" + bullets)
    return "\n\n".join(sections).strip()
