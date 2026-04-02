"""Typed extension manifest loading for installable OmicsClaw packs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EXTENSION_MANIFEST_FILENAME = "omicsclaw-extension.json"
VALID_EXTENSION_TYPES = {
    "skill-pack",
    "agent-pack",
    "mcp-bundle",
    "prompt-pack",
    "output-style-pack",
    "workflow-pack",
    "hook-pack",
}
VALID_TRUSTED_CAPABILITIES = {
    "skill-run",
    "skill-demo",
    "skill-search",
    "data-read",
    "report-write",
    "knowledge-hints",
    "agent-entry",
    "workflow-entry",
    "mcp-config",
    "prompt-rules",
    "output-style-entry",
    "hooks",
    "runtime-policy",
}
UNTRUSTED_ALLOWED_EXTENSION_TYPES = {"skill-pack"}
UNTRUSTED_ALLOWED_CAPABILITIES = {
    "skill-run",
    "skill-demo",
    "skill-search",
    "data-read",
    "report-write",
    "knowledge-hints",
}
RESTRICTED_UNTRUSTED_CAPABILITIES = {
    "hooks",
    "runtime-policy",
    "agent-entry",
    "workflow-entry",
    "mcp-config",
    "prompt-rules",
}


@dataclass(slots=True)
class ExtensionManifest:
    name: str
    version: str
    type: str
    entrypoints: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)
    required_files: list[str] = field(default_factory=list)
    trusted_capabilities: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    description: str = ""
    manifest_path: Path | None = None


def discover_extension_manifest(extension_dir: str | Path) -> Path | None:
    candidate = Path(extension_dir) / EXTENSION_MANIFEST_FILENAME
    if candidate.exists():
        return candidate
    return None


def _normalize_manifest_list(raw: Any, *, field_name: str) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"Manifest field '{field_name}' must be a list of strings.")
    values: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if not text:
            continue
        values.append(text)
    return values


def _ensure_relative_manifest_paths(
    values: list[str],
    *,
    field_name: str,
) -> list[str]:
    normalized: list[str] = []
    for value in values:
        path = Path(value)
        if path.is_absolute():
            raise ValueError(
                f"Manifest field '{field_name}' must use relative paths only: {value}"
            )
        if ".." in path.parts:
            raise ValueError(
                f"Manifest field '{field_name}' may not escape the extension root: {value}"
            )
        normalized.append(path.as_posix())
    return normalized


def load_extension_manifest(manifest_path: str | Path) -> ExtensionManifest:
    path = Path(manifest_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Extension manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid extension manifest JSON: {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"Extension manifest must be a JSON object: {path}")

    name = str(raw.get("name", "") or "").strip()
    version = str(raw.get("version", "") or "").strip()
    extension_type = str(raw.get("type", "") or "").strip()
    description = str(raw.get("description", "") or "").strip()
    if not name:
        raise ValueError(f"Extension manifest missing required field 'name': {path}")
    if not version:
        raise ValueError(f"Extension manifest missing required field 'version': {path}")
    if extension_type not in VALID_EXTENSION_TYPES:
        raise ValueError(
            f"Extension manifest field 'type' must be one of {sorted(VALID_EXTENSION_TYPES)}: {path}"
        )

    trusted_capabilities = _normalize_manifest_list(
        raw.get("trusted_capabilities"),
        field_name="trusted_capabilities",
    )
    invalid_capabilities = [
        capability
        for capability in trusted_capabilities
        if capability not in VALID_TRUSTED_CAPABILITIES
    ]
    if invalid_capabilities:
        raise ValueError(
            "Extension manifest field 'trusted_capabilities' contains unsupported "
            f"values: {', '.join(invalid_capabilities)}"
        )

    return ExtensionManifest(
        name=name,
        version=version,
        type=extension_type,
        entrypoints=_ensure_relative_manifest_paths(
            _normalize_manifest_list(raw.get("entrypoints"), field_name="entrypoints"),
            field_name="entrypoints",
        ),
        hooks=_ensure_relative_manifest_paths(
            _normalize_manifest_list(raw.get("hooks"), field_name="hooks"),
            field_name="hooks",
        ),
        required_files=_ensure_relative_manifest_paths(
            _normalize_manifest_list(raw.get("required_files"), field_name="required_files"),
            field_name="required_files",
        ),
        trusted_capabilities=trusted_capabilities,
        dependencies=_normalize_manifest_list(
            raw.get("dependencies"),
            field_name="dependencies",
        ),
        description=description,
        manifest_path=path,
    )


__all__ = [
    "EXTENSION_MANIFEST_FILENAME",
    "ExtensionManifest",
    "RESTRICTED_UNTRUSTED_CAPABILITIES",
    "UNTRUSTED_ALLOWED_CAPABILITIES",
    "UNTRUSTED_ALLOWED_EXTENSION_TYPES",
    "VALID_EXTENSION_TYPES",
    "VALID_TRUSTED_CAPABILITIES",
    "discover_extension_manifest",
    "load_extension_manifest",
]
