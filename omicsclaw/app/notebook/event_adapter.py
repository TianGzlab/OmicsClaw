"""Translate `jupyter_client` messages into the SSE event schema consumed by
the OmicsClaw notebook frontend.

The frontend reducer expects nine event types:
    kernel_status, execute_input, stream, execute_result, display_data,
    update_display_data, clear_output, error, execute_reply

`update_display_data` and `clear_output` are what make dynamic outputs —
tqdm progress bars, ipywidgets refreshes, matplotlib animations — render
faithfully. Forwarding them as `display_data` would append new outputs on
every refresh instead of replacing in place.

This module is intentionally pure: each function takes a raw jupyter_client
message dict + a `cell_id` and returns either an event dict or `None`.
"""

from __future__ import annotations

from typing import Any, Optional


def adapt_iopub_message(msg: dict[str, Any], cell_id: str) -> Optional[dict[str, Any]]:
    """Translate one iopub message to an SSE event dict."""
    msg_type = msg.get("msg_type")
    content = msg.get("content", {}) or {}

    if msg_type == "status":
        state = content.get("execution_state", "")
        return {"type": "kernel_status", "data": {"status": state}}

    if msg_type == "execute_input":
        return {
            "type": "execute_input",
            "data": {
                "cell_id": cell_id,
                "execution_count": content.get("execution_count"),
            },
        }

    if msg_type == "stream":
        return {
            "type": "stream",
            "data": {
                "cell_id": cell_id,
                "name": content.get("name", "stdout"),
                "text": content.get("text", ""),
            },
        }

    if msg_type == "execute_result":
        return {
            "type": "execute_result",
            "data": {
                "cell_id": cell_id,
                "execution_count": content.get("execution_count"),
                "data": content.get("data", {}),
                "metadata": content.get("metadata", {}),
            },
        }

    if msg_type == "display_data":
        transient = content.get("transient") or {}
        display_id = transient.get("display_id")
        event_data: dict[str, Any] = {
            "cell_id": cell_id,
            "data": content.get("data", {}),
            "metadata": content.get("metadata", {}),
        }
        if isinstance(display_id, str) and display_id:
            event_data["display_id"] = display_id
        return {"type": "display_data", "data": event_data}

    if msg_type == "update_display_data":
        transient = content.get("transient") or {}
        display_id = transient.get("display_id") or ""
        return {
            "type": "update_display_data",
            "data": {
                "cell_id": cell_id,
                "display_id": display_id,
                "data": content.get("data", {}),
                "metadata": content.get("metadata", {}),
            },
        }

    if msg_type == "clear_output":
        return {
            "type": "clear_output",
            "data": {
                "cell_id": cell_id,
                "wait": bool(content.get("wait", False)),
            },
        }

    if msg_type == "error":
        return {
            "type": "error",
            "data": {
                "cell_id": cell_id,
                "ename": content.get("ename", ""),
                "evalue": content.get("evalue", ""),
                "traceback": content.get("traceback", []),
            },
        }

    return None


def adapt_shell_reply(msg: dict[str, Any], cell_id: str) -> Optional[dict[str, Any]]:
    """Translate a shell-channel `execute_reply` to the terminating SSE event."""
    if msg.get("msg_type") != "execute_reply":
        return None

    content = msg.get("content", {}) or {}
    return {
        "type": "execute_reply",
        "data": {
            "cell_id": cell_id,
            "status": content.get("status", "ok"),
            "execution_count": content.get("execution_count"),
        },
    }


def is_idle_status_for(msg: dict[str, Any], parent_msg_id: str) -> bool:
    """True iff this iopub `status` message marks our execution as finished."""
    if msg.get("msg_type") != "status":
        return False
    if msg.get("parent_header", {}).get("msg_id") != parent_msg_id:
        return False
    return msg.get("content", {}).get("execution_state") == "idle"


def has_matching_parent(msg: dict[str, Any], parent_msg_id: str) -> bool:
    """Filter helper: True iff `msg.parent_header.msg_id == parent_msg_id`."""
    return msg.get("parent_header", {}).get("msg_id") == parent_msg_id
