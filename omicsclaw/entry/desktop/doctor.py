"""``GET /env/doctor``: what this running backend was assembled with.

:func:`doctor_report` reads facts off the live
:class:`~omicsclaw.entry.AgentApp` — the provider and the model it calls,
the skill index, the MCP servers, the sandbox, memory, the permission
mode and the workspace — and answers them as a checklist. Nothing is
probed from scratch: every fact is what start-up already produced.

The payload::

    {
      "generated_at": "2026-09-28T08:00:00Z",
      "workspace_dir": "/path/to/project",
      "omicsclaw_dir": "/path/to/project",
      "overall_status": "ok" | "warn" | "fail",
      "failure_count": 0,
      "warning_count": 0,
      "checks": [
        {"name": "provider", "status": "ok" | "warn" | "fail" | "info",
         "summary": "...", "details": ["..."]},
        ...
      ]
    }

``omicsclaw_dir`` is the same value ``/health`` reports. A check is
``warn`` or ``fail`` only for something a person should act on; a
deliberate configuration that is merely off (no sandbox, no memory) is
``info``.

:func:`effective_model` is the model the provider calls, which is also what
``/health`` and the ``result`` frame report.
"""

from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path
from typing import Any, Final

from omicsclaw.entry.assembly import AgentApp
from omicsclaw.provider.config import resolve_config

__all__ = ["DOCTOR_CHECKS", "doctor_report", "effective_model"]

DOCTOR_CHECKS: Final = (
    "provider",
    "skills",
    "skipped_skills",
    "mcp",
    "sandbox",
    "memory",
    "permission",
    "workspace",
)
"""The ``name`` of every check, in the order they are reported."""

_MAX_DETAILS: Final = 20
"""Longest list of details one check reports; the rest are counted."""

_MAX_DETAIL_CHARS: Final = 300
"""Longest single detail line; an error message is cut to this."""


def effective_model(app: AgentApp) -> str:
    """The model *app*'s provider calls.

    :attr:`~omicsclaw.entry.AppConfig.model` is empty when the deployment
    named none and the provider's preset supplies it; this resolves the
    same configuration the app was built from, read-only, and falls back
    to the configured name when it cannot be resolved.
    """
    try:
        resolved = resolve_config(app.config.provider, app.config.model).model
    except Exception:  # noqa: BLE001 - a report must not fail on this
        resolved = ""
    return resolved or app.config.model


def doctor_report(app: AgentApp) -> dict[str, Any]:
    """The ``GET /env/doctor`` payload for *app*. Pure apart from the clock
    and one ``os.access`` on the workspace."""
    checks = [
        _provider(app),
        _skills(app),
        _skipped_skills(app),
        _mcp(app),
        _sandbox(app),
        _memory(app),
        _permission(app),
        _workspace(app),
    ]
    failures = sum(1 for check in checks if check["status"] == "fail")
    warnings = sum(1 for check in checks if check["status"] == "warn")
    overall = "fail" if failures else "warn" if warnings else "ok"
    return {
        "generated_at": _dt.datetime.now(_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "workspace_dir": str(app.config.workspace),
        "omicsclaw_dir": str(app.config.workspace),
        "overall_status": overall,
        "failure_count": failures,
        "warning_count": warnings,
        "checks": checks,
    }


def _check(name: str, status: str, summary: str, details: list[str] | None = None) -> dict[str, Any]:
    shown = [_clip(line) for line in details or ()]
    if len(shown) > _MAX_DETAILS:
        hidden = len(shown) - _MAX_DETAILS
        shown = [*shown[:_MAX_DETAILS], f"... and {hidden} more"]
    return {"name": name, "status": status, "summary": summary, "details": shown}


def _clip(line: str) -> str:
    line = " ".join(line.split())
    if len(line) <= _MAX_DETAIL_CHARS:
        return line
    return line[: _MAX_DETAIL_CHARS - 3] + "..."


def _provider(app: AgentApp) -> dict[str, Any]:
    provider = app.provider.name
    model = effective_model(app)
    if not provider:
        return _check("provider", "fail", "No LLM provider is configured.")
    if not model:
        return _check(
            "provider",
            "warn",
            f"Provider {provider} has no model named; the provider picks one.",
        )
    return _check("provider", "ok", f"{provider} / {model}")


def _skills(app: AgentApp) -> dict[str, Any]:
    index = app.skills
    count = len(index.skills)
    root = str(index.root)
    if count == 0:
        return _check(
            "skills",
            "warn",
            "No skills are indexed. Set OMICSCLAW_SKILLS_DIR to the skills "
            "directory of the OmicsClaw checkout, or pass --skills-dir.",
            [f"scanned: {root}"],
        )
    return _check("skills", "ok", f"{count} skills indexed.", [f"root: {root}"])


def _skipped_skills(app: AgentApp) -> dict[str, Any]:
    skipped = app.skills.skipped
    if not skipped:
        return _check("skipped_skills", "ok", "No skill was skipped.")
    details = [
        f"{entry.path}: {entry.reason}"
        + (f" ({entry.detail})" if entry.detail else "")
        for entry in skipped
    ]
    return _check(
        "skipped_skills",
        "warn",
        f"{len(skipped)} SKILL.md file(s) were found and not indexed.",
        details,
    )


def _mcp(app: AgentApp) -> dict[str, Any]:
    manager = app.mcp
    statuses = manager.statuses() if manager is not None else ()
    if not statuses:
        return _check("mcp", "info", "No MCP servers are configured.")
    failed = [status for status in statuses if status.state.value == "failed"]
    details = [
        f"{status.name}: {status.state.value}"
        + (f" ({status.error})" if status.error else f", {len(status.tools)} tool(s)")
        for status in statuses
    ]
    if failed:
        return _check(
            "mcp",
            "warn",
            f"{len(failed)} of {len(statuses)} MCP server(s) failed to connect.",
            details,
        )
    return _check("mcp", "ok", f"{len(statuses)} MCP server(s) configured.", details)


def _sandbox(app: AgentApp) -> dict[str, Any]:
    binding = app.sandbox
    if binding is not None and binding.active:
        return _check("sandbox", "ok", "bash runs in the sandbox container.")
    if binding is not None and binding.degraded:
        why = [binding.unavailable] if binding.unavailable else []
        return _check(
            "sandbox",
            "warn",
            "A sandbox was requested but is not in use; bash runs on this machine.",
            why,
        )
    return _check(
        "sandbox",
        "info",
        "No sandbox: bash runs on this machine. OMICSCLAW_SANDBOX=docker "
        "puts it in a container.",
    )


def _memory(app: AgentApp) -> dict[str, Any]:
    if app.memory is not None:
        return _check("memory", "ok", "Long-term memory is on for this workspace.")
    return _check("memory", "info", "Long-term memory is off.")


def _permission(app: AgentApp) -> dict[str, Any]:
    gate = app.permission
    if gate is None:
        return _check("permission", "warn", "No permission gate is mounted.")
    mode = gate.mode.value
    details = [f"rules: {app.config.permission_rules_path()}"]
    if mode == "bypass-all":
        return _check(
            "permission",
            "warn",
            "Permission mode bypass-all: no tool call is asked about.",
            details,
        )
    return _check("permission", "ok", f"Permission mode {mode}.", details)


def _workspace(app: AgentApp) -> dict[str, Any]:
    workspace = Path(app.config.workspace)
    if not workspace.is_dir():
        return _check(
            "workspace", "fail", "The workspace is not a directory.", [str(workspace)]
        )
    if not os.access(workspace, os.W_OK | os.X_OK):
        return _check(
            "workspace", "fail", "The workspace is not writable.", [str(workspace)]
        )
    return _check("workspace", "ok", "The workspace is writable.", [str(workspace)])
