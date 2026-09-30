"""``GET /skills``, ``GET /skills/{domain}/{name}`` and ``GET /mcp/servers``.

Read-only views of what the running :class:`~omicsclaw.entry.AgentApp`
loaded at start-up: the skill index and the MCP configuration with each
server's connection state. Nothing is rescanned; a change on disk shows
after a restart.

The catalog payload::

    {"domains": [{"domain": "spatial", "domain_name": "spatial",
                  "primary_data_types": [],
                  "skills": [{"name": "spatial-de", "description": "...",
                              "domain": "spatial", "collection": "curated",
                              "status": "ready"}]}],
     "total": 94}

A skill with no domain directory is listed under :data:`GENERAL_DOMAIN`.

One skill::

    {"name": "spatial-de", "domain": "spatial", "description": "...",
     "aliases": [], "script_path": null, "tags": ["..."],
     "skill_md": "<SKILL.md without its frontmatter, or null>",
     "resources": [{"path": "scripts/run.py", "kind": "script"}]}

``resources`` holds paths relative to the skill's directory only.

The MCP payload is ``{"servers": [...]}``, configured servers in file
order and then rejected entries. ``env`` and ``headers`` carry their keys
with every value replaced by :data:`MASK`; ``command``, ``args`` and
``url`` are the text written in ``.mcp.json`` before ``${VAR}``
expansion, and are left out when that file can no longer be read. An
``error`` has the values of the start-up environment replaced by
:data:`MASK` and is cut to :data:`MAX_ERROR_CHARS`.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path, PurePosixPath
from typing import Any, Final, Mapping

from omicsclaw.skills import Skill

from .turn_submission import DesktopIngressError

__all__ = [
    "GENERAL_DOMAIN",
    "MASK",
    "MAX_ERROR_CHARS",
    "MAX_RESOURCES",
    "MIN_REPLACED_CHARS",
    "mcp_servers",
    "skill_catalog",
    "skill_detail",
]

_log = logging.getLogger(__name__)

GENERAL_DOMAIN: Final = "general"
"""The domain reported for a skill that sits directly under the root."""

MAX_RESOURCES: Final = 200
"""Most files one skill detail lists."""

MASK: Final = "••••"
"""What a hidden value is shown as."""

MAX_ERROR_CHARS: Final = 300
"""Longest ``error`` one MCP entry reports."""

MIN_REPLACED_CHARS: Final = 8
"""Shortest environment value replaced inside an error."""

_SCRIPT_SUFFIXES: Final = frozenset({".py", ".r", ".sh"})
_CONFIG_SUFFIXES: Final = frozenset({".yaml", ".yml", ".json", ".toml"})
_SKIPPED_NAMES: Final = frozenset({"__pycache__"})


# ---- skills ---------------------------------------------------------------


def _domain_of(skill: Skill) -> str:
    return skill.domain or GENERAL_DOMAIN


def skill_catalog(app: Any) -> dict[str, Any]:
    """The ``GET /skills`` payload for *app*'s skill index."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for domain, skills in app.skills.by_domain():
        entries = grouped.setdefault(domain or GENERAL_DOMAIN, [])
        entries.extend(
            {
                "name": skill.name,
                "description": skill.description,
                "domain": domain or GENERAL_DOMAIN,
                "collection": "curated",
                "status": "ready",
            }
            for skill in skills
        )
    domains = [
        {
            "domain": domain,
            "domain_name": domain,
            "primary_data_types": [],
            "skills": entries,
        }
        for domain, entries in grouped.items()
    ]
    return {"domains": domains, "total": sum(len(e) for e in grouped.values())}


def skill_detail(app: Any, domain: str, name: str) -> dict[str, Any]:
    """The ``GET /skills/{domain}/{name}`` payload.

    :raises DesktopIngressError: 404 ``skill_not_found`` when no skill has
        *name*, or when it is not in *domain*.
    """
    index = app.skills
    skill = index.get(name)
    if skill is None or _domain_of(skill) != domain:
        raise DesktopIngressError("skill_not_found", status_code=404)
    try:
        body: str | None = index.get_full_content(name)
    except (OSError, UnicodeDecodeError):
        body = None
    return {
        "name": skill.name,
        "domain": _domain_of(skill),
        "description": skill.description,
        "aliases": [],
        "script_path": None,
        "tags": list(skill.tags),
        "skill_md": body,
        "resources": [
            {"path": path, "kind": _resource_kind(path)}
            for path in _resource_paths(skill.directory)
        ],
    }


def _resource_paths(directory: Path) -> list[str]:
    """Regular files under *directory*, relative, sorted, at most
    :data:`MAX_RESOURCES`. Symlinks, hidden names and ``__pycache__`` are
    skipped."""
    found: list[str] = []

    def walk(current: Path, prefix: PurePosixPath | None) -> None:
        try:
            entries = sorted(os.scandir(current), key=lambda entry: entry.name)
        except OSError:
            return
        for entry in entries:
            if len(found) >= MAX_RESOURCES:
                return
            if entry.name.startswith(".") or entry.name in _SKIPPED_NAMES:
                continue
            if entry.is_symlink():
                continue
            relative = (
                PurePosixPath(entry.name) if prefix is None else prefix / entry.name
            )
            if entry.is_dir(follow_symlinks=False):
                walk(Path(entry.path), relative)
            elif entry.is_file(follow_symlinks=False):
                found.append(str(relative))

    walk(directory, None)
    return sorted(found)


def _resource_kind(path: str) -> str:
    relative = PurePosixPath(path)
    if relative.suffix.lower() in _SCRIPT_SUFFIXES:
        return "script"
    if relative.parts[0] == "references":
        return "reference"
    if relative.suffix.lower() in _CONFIG_SUFFIXES:
        return "config"
    return "doc"


# ---- MCP --------------------------------------------------------------------


def mcp_servers(
    app: Any, *, startup: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """The ``GET /mcp/servers`` payload for *app*'s MCP manager.

    *startup* is the environment ``.mcp.json`` was expanded against. Its
    values are replaced inside every ``error``; without it a rejected
    entry reports ``"invalid_config"`` and not its reason.
    """
    manager = getattr(app, "mcp", None)
    if manager is None:
        return {"servers": []}
    config = manager.config
    statuses = {status.name: status for status in manager.statuses()}
    raw = _raw_servers(config.source)
    environment_values = _replaceable(startup.values()) if startup is not None else ()

    servers: list[dict[str, Any]] = []
    for server in config.servers:
        status = statuses.get(server.name)
        if status is not None:
            state = status.state.value
            error = status.error
        else:
            state = "pending" if server.enabled else "disabled"
            error = ""
        kind = server.kind.value
        entry: dict[str, Any] = {"name": server.name, "type": kind, "transport": kind}
        written = raw.get(server.name) if raw is not None else None
        if kind == "stdio":
            command = _raw_string(written, "command")
            if command is not None:
                entry["command"] = command
            args = _raw_strings(written, "args")
            if args is not None:
                entry["args"] = args
            entry["env"] = {key: MASK for key in server.env}
        else:
            url = _raw_string(written, "url")
            if url is not None:
                entry["url"] = url
            entry["headers"] = {key: MASK for key in server.headers}
        entry["enabled"] = server.enabled
        if server.tools is not None:
            entry["tools"] = list(server.tools)
        hidden = (
            *environment_values,
            *_replaceable(server.env.values()),
            *_replaceable(server.headers.values()),
        )
        entry["state"] = state
        entry["active"] = state == "connected"
        entry["error"] = _clip(_replace(error, hidden))
        servers.append(entry)

    for rejected in config.rejected:
        error = (
            _clip(_replace(rejected.reason, environment_values))
            if startup is not None
            else "invalid_config"
        )
        servers.append(
            {"name": rejected.name, "state": "failed", "active": False, "error": error}
        )
    return {"servers": servers}


def _raw_servers(source: Path | None) -> Mapping[str, Any] | None:
    """The ``mcpServers`` object of *source* as written, or ``None``."""
    if source is None:
        return None
    try:
        data = json.loads(Path(source).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        _log.info("cannot re-read the MCP configuration: %s", type(exc).__name__)
        return None
    if not isinstance(data, Mapping):
        return None
    servers = data.get("mcpServers", {})
    return servers if isinstance(servers, Mapping) else None


def _raw_string(entry: Any, key: str) -> str | None:
    if not isinstance(entry, Mapping):
        return None
    value = entry.get(key, "")
    return value if isinstance(value, str) else None


def _raw_strings(entry: Any, key: str) -> list[str] | None:
    if not isinstance(entry, Mapping):
        return None
    value = entry.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return list(value)


def _replaceable(values: Any) -> tuple[str, ...]:
    return tuple(
        value
        for value in values
        if isinstance(value, str) and len(value) >= MIN_REPLACED_CHARS
    )


def _replace(text: str, values: tuple[str, ...]) -> str:
    """*text* with every one of *values* replaced by :data:`MASK`, longest
    first so a value containing another is replaced whole."""
    for value in sorted(set(values), key=len, reverse=True):
        text = text.replace(value, MASK)
    return text


def _clip(text: str) -> str:
    return text[:MAX_ERROR_CHARS]
