"""Emit user-facing guidance lines that the framework picks out of a skill's output.

A plain line starts with :data:`USER_GUIDANCE_PREFIX`; a structured one starts
with :data:`USER_GUIDANCE_JSON_PREFIX` followed by one JSON object.
"""

from __future__ import annotations

import json
import logging

__all__ = ["emit_user_guidance", "emit_user_guidance_payload"]

USER_GUIDANCE_PREFIX = "USER_GUIDANCE:"
USER_GUIDANCE_JSON_PREFIX = "USER_GUIDANCE_JSON:"


def _format_user_guidance(message: str) -> str:
    text = str(message or "").strip()
    return f"{USER_GUIDANCE_PREFIX} {text}" if text else USER_GUIDANCE_PREFIX


def _format_user_guidance_payload(payload: dict) -> str:
    return f"{USER_GUIDANCE_JSON_PREFIX} {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"


def emit_user_guidance(logger: logging.Logger, message: str) -> None:
    """Log *message* at WARNING as one user-guidance line."""
    logger.warning(_format_user_guidance(message))


def emit_user_guidance_payload(logger: logging.Logger, payload: dict) -> None:
    """Log *payload* at WARNING as one structured user-guidance line."""
    logger.warning(_format_user_guidance_payload(payload))
