"""Extension install-record, state, and inventory helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .manifest import ExtensionManifest, VALID_EXTENSION_TYPES

INSTALL_RECORD_FILENAME = ".omicsclaw-install.json"
EXTENSION_STATE_FILENAME = ".omicsclaw-extension-state.json"
USER_EXTENSION_ROOTNAME = "installed_extensions"
EXTENSION_TYPE_STORE_DIRS = {
    "skill-pack": ("skills", "user"),
    "agent-pack": (USER_EXTENSION_ROOTNAME, "agent-packs"),
    "mcp-bundle": (USER_EXTENSION_ROOTNAME, "mcp-bundles"),
    "prompt-pack": (USER_EXTENSION_ROOTNAME, "prompt-packs"),
    "output-style-pack": (USER_EXTENSION_ROOTNAME, "output-style-packs"),
    "workflow-pack": (USER_EXTENSION_ROOTNAME, "workflow-packs"),
    "hook-pack": (USER_EXTENSION_ROOTNAME, "hook-packs"),
}


@dataclass(slots=True)
class InstalledExtensionRecord:
    extension_name: str
    source_kind: str
    source: str
    installed_at: str
    manifest_name: str = ""
    manifest_version: str = ""
    extension_type: str = "skill-pack"
    trusted_capabilities: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    relative_install_path: str = ""

    @property
    def skill_name(self) -> str:
        return self.extension_name


@dataclass(slots=True)
class ExtensionState:
    enabled: bool = True
    updated_at: str = ""
    disabled_reason: str = ""


@dataclass(frozen=True, slots=True)
class InstalledExtensionInventoryEntry:
    extension_type: str
    path: Path
    record: InstalledExtensionRecord | None
    state: ExtensionState


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def extension_store_dir(
    omicsclaw_dir: str | Path,
    extension_type: str,
) -> Path:
    if extension_type not in VALID_EXTENSION_TYPES:
        raise ValueError(f"Unknown extension type: {extension_type}")
    path = Path(omicsclaw_dir)
    for part in EXTENSION_TYPE_STORE_DIRS[extension_type]:
        path = path / part
    return path


def iter_extension_store_dirs(
    omicsclaw_dir: str | Path,
    *,
    extension_types: Iterable[str] | None = None,
) -> list[tuple[str, Path]]:
    canonical_order = tuple(EXTENSION_TYPE_STORE_DIRS.keys())
    requested = tuple(extension_types or canonical_order)
    selected = tuple(
        extension_type
        for extension_type in canonical_order
        if extension_type in requested
    )
    return [
        (extension_type, extension_store_dir(omicsclaw_dir, extension_type))
        for extension_type in selected
    ]


def write_install_record(
    extension_dir: str | Path,
    *,
    extension_name: str = "",
    skill_name: str = "",
    source_kind: str,
    source: str,
    manifest: ExtensionManifest | None = None,
    extension_type: str = "",
    relative_install_path: str = "",
) -> Path:
    path = Path(extension_dir) / INSTALL_RECORD_FILENAME
    normalized_name = str(extension_name or skill_name or "").strip()
    if not normalized_name:
        raise ValueError("extension_name is required to write an install record")
    normalized_type = extension_type or (manifest.type if manifest is not None else "skill-pack")
    record = InstalledExtensionRecord(
        extension_name=normalized_name,
        source_kind=source_kind,
        source=source,
        installed_at=utcnow_iso(),
        manifest_name=manifest.name if manifest is not None else "",
        manifest_version=manifest.version if manifest is not None else "",
        extension_type=normalized_type,
        trusted_capabilities=list(manifest.trusted_capabilities) if manifest is not None else [],
        dependencies=list(manifest.dependencies) if manifest is not None else [],
        relative_install_path=relative_install_path,
    )
    path.write_text(
        json.dumps(asdict(record), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def load_install_record(extension_dir: str | Path) -> InstalledExtensionRecord | None:
    path = Path(extension_dir) / INSTALL_RECORD_FILENAME
    if not path.exists():
        return None

    raw = json.loads(path.read_text(encoding="utf-8"))
    normalized_name = str(
        raw.get("extension_name", "") or raw.get("skill_name", "") or ""
    ).strip()
    return InstalledExtensionRecord(
        extension_name=normalized_name,
        source_kind=str(raw.get("source_kind", "") or ""),
        source=str(raw.get("source", "") or ""),
        installed_at=str(raw.get("installed_at", "") or ""),
        manifest_name=str(raw.get("manifest_name", "") or ""),
        manifest_version=str(raw.get("manifest_version", "") or ""),
        extension_type=str(raw.get("extension_type", "") or "skill-pack"),
        trusted_capabilities=[str(item) for item in raw.get("trusted_capabilities", [])],
        dependencies=[str(item) for item in raw.get("dependencies", [])],
        relative_install_path=str(raw.get("relative_install_path", "") or ""),
    )


def write_extension_state(
    extension_dir: str | Path,
    *,
    enabled: bool = True,
    disabled_reason: str = "",
) -> Path:
    path = Path(extension_dir) / EXTENSION_STATE_FILENAME
    state = ExtensionState(
        enabled=bool(enabled),
        updated_at=utcnow_iso(),
        disabled_reason=str(disabled_reason or "").strip() if not enabled else "",
    )
    path.write_text(
        json.dumps(asdict(state), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def load_extension_state(extension_dir: str | Path) -> ExtensionState:
    path = Path(extension_dir) / EXTENSION_STATE_FILENAME
    if not path.exists():
        return ExtensionState(enabled=True)

    raw = json.loads(path.read_text(encoding="utf-8"))
    return ExtensionState(
        enabled=bool(raw.get("enabled", True)),
        updated_at=str(raw.get("updated_at", "") or ""),
        disabled_reason=str(raw.get("disabled_reason", "") or ""),
    )


def set_extension_enabled(
    extension_dir: str | Path,
    *,
    enabled: bool,
    disabled_reason: str = "",
) -> ExtensionState:
    write_extension_state(
        extension_dir,
        enabled=enabled,
        disabled_reason=disabled_reason,
    )
    return load_extension_state(extension_dir)


def list_installed_extension_records(
    user_extensions_dir: str | Path,
) -> list[tuple[Path, InstalledExtensionRecord | None]]:
    base_dir = Path(user_extensions_dir)
    if not base_dir.exists():
        return []

    entries: list[tuple[Path, InstalledExtensionRecord | None]] = []
    for candidate in sorted(path for path in base_dir.iterdir() if path.is_dir() and not path.name.startswith(".")):
        entries.append((candidate, load_install_record(candidate)))
    return entries


def list_installed_extensions(
    omicsclaw_dir: str | Path,
    *,
    extension_types: Iterable[str] | None = None,
) -> list[InstalledExtensionInventoryEntry]:
    entries: list[InstalledExtensionInventoryEntry] = []
    for extension_type, store_dir in iter_extension_store_dirs(
        omicsclaw_dir,
        extension_types=extension_types,
    ):
        if not store_dir.exists():
            continue
        for candidate in sorted(
            path for path in store_dir.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        ):
            entries.append(
                InstalledExtensionInventoryEntry(
                    extension_type=extension_type,
                    path=candidate,
                    record=load_install_record(candidate),
                    state=load_extension_state(candidate),
                )
            )
    return entries


def find_installed_extensions(
    omicsclaw_dir: str | Path,
    name: str,
    *,
    extension_type: str = "",
) -> list[InstalledExtensionInventoryEntry]:
    target = str(name or "").strip()
    if not target:
        return []

    entries = list_installed_extensions(
        omicsclaw_dir,
        extension_types=(extension_type,) if extension_type else None,
    )
    matches: list[InstalledExtensionInventoryEntry] = []
    for entry in entries:
        names = {
            entry.path.name,
            entry.record.extension_name if entry.record is not None else "",
            entry.record.manifest_name if entry.record is not None else "",
        }
        if target in {value for value in names if value}:
            matches.append(entry)
    return matches


__all__ = [
    "EXTENSION_STATE_FILENAME",
    "EXTENSION_TYPE_STORE_DIRS",
    "ExtensionState",
    "INSTALL_RECORD_FILENAME",
    "InstalledExtensionInventoryEntry",
    "InstalledExtensionRecord",
    "USER_EXTENSION_ROOTNAME",
    "extension_store_dir",
    "find_installed_extensions",
    "iter_extension_store_dirs",
    "list_installed_extension_records",
    "list_installed_extensions",
    "load_extension_state",
    "load_install_record",
    "set_extension_enabled",
    "write_extension_state",
    "write_install_record",
]
