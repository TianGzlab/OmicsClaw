"""Runtime activation helpers for installable OmicsClaw extensions."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

from .loader import InstalledExtensionInventoryEntry, list_installed_extensions
from .manifest import ExtensionManifest, discover_extension_manifest, load_extension_manifest

PROMPT_PACK_EXTENSION_TYPE = "prompt-pack"
OUTPUT_STYLE_PACK_EXTENSION_TYPE = "output-style-pack"
AGENT_PACK_EXTENSION_TYPE = "agent-pack"
WORKFLOW_PACK_EXTENSION_TYPE = "workflow-pack"
HOOK_PACK_EXTENSION_TYPE = "hook-pack"

PROMPT_PACK_RUNTIME_CAPABILITY = "prompt-rules"
OUTPUT_STYLE_PACK_RUNTIME_CAPABILITY = "output-style-entry"
AGENT_PACK_RUNTIME_CAPABILITY = "agent-entry"
WORKFLOW_PACK_RUNTIME_CAPABILITY = "workflow-entry"
HOOK_PACK_RUNTIME_CAPABILITY = "hooks"

ACTIVATION_SURFACE_SKILLS = "skills"
ACTIVATION_SURFACE_PROMPTS = "prompts"
ACTIVATION_SURFACE_OUTPUT_STYLES = "output_styles"
ACTIVATION_SURFACE_AGENTS = "agents"
ACTIVATION_SURFACE_WORKFLOWS = "workflows"
ACTIVATION_SURFACE_HOOKS = "hooks"

HOOK_MODE_NOTICE = "notice"
HOOK_MODE_CONTEXT = "context"
HOOK_MODE_RECORD = "record"
VALID_HOOK_MODES = frozenset({HOOK_MODE_NOTICE, HOOK_MODE_CONTEXT, HOOK_MODE_RECORD})


@dataclass(frozen=True, slots=True)
class PromptPackRuleEntry:
    relative_path: str
    content: str
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class LoadedPromptPack:
    name: str
    version: str
    path: Path
    source_kind: str
    trusted_capabilities: tuple[str, ...] = ()
    rules: tuple[PromptPackRuleEntry, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PromptPackRuntimeContext:
    content: str = ""
    active_prompt_packs: tuple[str, ...] = ()
    omitted_prompt_packs: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OutputStyleEntry:
    name: str
    description: str = ""
    instructions: str = ""
    aliases: tuple[str, ...] = ()
    supported_surfaces: tuple[str, ...] = ()
    relative_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LoadedOutputStylePack:
    name: str
    version: str
    path: Path
    source_kind: str
    trusted_capabilities: tuple[str, ...] = ()
    styles: tuple[OutputStyleEntry, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentPackEntry:
    name: str
    description: str = ""
    prompt: str = ""
    tools: tuple[str, ...] = ()
    relative_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LoadedAgentPack:
    name: str
    version: str
    path: Path
    source_kind: str
    trusted_capabilities: tuple[str, ...] = ()
    agents: tuple[AgentPackEntry, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WorkflowPackEntry:
    name: str
    description: str = ""
    steps: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    relative_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LoadedWorkflowPack:
    name: str
    version: str
    path: Path
    source_kind: str
    trusted_capabilities: tuple[str, ...] = ()
    workflows: tuple[WorkflowPackEntry, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HookPackEntry:
    name: str
    event: str
    mode: str
    message: str
    relative_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LoadedHookExtension:
    name: str
    version: str
    extension_type: str
    path: Path
    source_kind: str
    trusted_capabilities: tuple[str, ...] = ()
    hooks: tuple[HookPackEntry, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExtensionActivationSurface:
    surface: str
    active: bool
    entry_count: int = 0
    labels: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ExtensionActivationRecord:
    name: str
    extension_type: str
    path: Path
    enabled: bool
    source_kind: str
    surfaces: tuple[ExtensionActivationSurface, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExtensionRuntimeSnapshot:
    prompt_packs: tuple[LoadedPromptPack, ...] = ()
    output_style_packs: tuple[LoadedOutputStylePack, ...] = ()
    agent_packs: tuple[LoadedAgentPack, ...] = ()
    workflow_packs: tuple[LoadedWorkflowPack, ...] = ()
    hook_extensions: tuple[LoadedHookExtension, ...] = ()
    activation_records: tuple[ExtensionActivationRecord, ...] = ()


@dataclass(frozen=True, slots=True)
class _RuntimeManifestItem:
    inventory: InstalledExtensionInventoryEntry
    manifest_path: Path
    manifest: ExtensionManifest
    trusted_capabilities: tuple[str, ...]


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_local_source_kind(record) -> str:
    return _safe_text(getattr(record, "source_kind", "")) or "local"


def _merge_trusted_capabilities(
    manifest_capabilities: list[str] | tuple[str, ...],
    record_capabilities: list[str] | tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            capability
            for capability in [*manifest_capabilities, *record_capabilities]
            if _safe_text(capability)
        )
    )


def _requires_runtime_capability(
    trusted_capabilities: tuple[str, ...],
    runtime_capability: str,
) -> bool:
    return bool(trusted_capabilities) and runtime_capability not in trusted_capabilities


def _normalize_text_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        text
        for text in (_safe_text(item) for item in value)
        if text
    )


def _read_text_entrypoint(
    path: Path,
    *,
    max_chars: int,
) -> PromptPackRuleEntry | None:
    try:
        content = path.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, IsADirectoryError, OSError, UnicodeDecodeError):
        return None

    if not content:
        return None

    truncated = False
    if max_chars > 0 and len(content) > max_chars:
        truncated = True
        content = content[:max_chars].rstrip() + "\n\n[truncated]"

    return PromptPackRuleEntry(
        relative_path=path.name,
        content=content,
        truncated=truncated,
    )


def _load_structured_entrypoint(path: Path) -> Any | None:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError, OSError, UnicodeDecodeError):
        return None

    if not raw_text.strip():
        return None

    try:
        if path.suffix.lower() == ".json":
            return json.loads(raw_text)
        return yaml.safe_load(raw_text)
    except Exception:
        return None


def _iter_runtime_manifest_items(
    omicsclaw_dir: str | Path,
    *,
    extension_types: tuple[str, ...],
) -> list[_RuntimeManifestItem]:
    loaded: list[_RuntimeManifestItem] = []
    for item in list_installed_extensions(
        omicsclaw_dir,
        extension_types=extension_types,
    ):
        if not item.state.enabled or item.record is None:
            continue
        if _safe_local_source_kind(item.record) != "local":
            continue

        manifest_path = discover_extension_manifest(item.path)
        if manifest_path is None:
            continue
        try:
            manifest = load_extension_manifest(manifest_path)
        except ValueError:
            continue
        if manifest.type != item.extension_type:
            continue

        loaded.append(
            _RuntimeManifestItem(
                inventory=item,
                manifest_path=manifest_path,
                manifest=manifest,
                trusted_capabilities=_merge_trusted_capabilities(
                    manifest.trusted_capabilities,
                    item.record.trusted_capabilities,
                ),
            )
        )

    return loaded


def _iter_entry_mappings(raw: Any, *, collection_key: str) -> list[Mapping[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, Mapping)]
    if isinstance(raw, Mapping):
        nested = raw.get(collection_key)
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, Mapping)]
        return [raw]
    return []


def _load_manifest_for_entry(
    item: InstalledExtensionInventoryEntry,
) -> tuple[ExtensionManifest | None, Path | None, str]:
    manifest_path = discover_extension_manifest(item.path)
    if manifest_path is None:
        return None, None, "manifest missing"
    try:
        manifest = load_extension_manifest(manifest_path)
    except ValueError as exc:
        return None, manifest_path, str(exc)
    return manifest, manifest_path, ""


def _hook_mode(value: Any) -> str:
    mode = _safe_text(value) or HOOK_MODE_NOTICE
    if mode not in VALID_HOOK_MODES:
        return HOOK_MODE_NOTICE
    return mode


def load_enabled_prompt_packs(
    omicsclaw_dir: str | Path,
    *,
    max_chars_per_entry: int = 2000,
) -> list[LoadedPromptPack]:
    """Load enabled, tracked local prompt packs for runtime activation."""

    loaded: list[LoadedPromptPack] = []
    for runtime_item in _iter_runtime_manifest_items(
        omicsclaw_dir,
        extension_types=(PROMPT_PACK_EXTENSION_TYPE,),
    ):
        if _requires_runtime_capability(
            runtime_item.trusted_capabilities,
            PROMPT_PACK_RUNTIME_CAPABILITY,
        ):
            continue

        rules: list[PromptPackRuleEntry] = []
        for relative_path in runtime_item.manifest.entrypoints:
            entry = _read_text_entrypoint(
                runtime_item.inventory.path / relative_path,
                max_chars=max_chars_per_entry,
            )
            if entry is None:
                continue
            rules.append(
                PromptPackRuleEntry(
                    relative_path=relative_path,
                    content=entry.content,
                    truncated=entry.truncated,
                )
            )

        if not rules:
            continue

        loaded.append(
            LoadedPromptPack(
                name=runtime_item.manifest.name,
                version=runtime_item.manifest.version,
                path=runtime_item.inventory.path,
                source_kind=_safe_local_source_kind(runtime_item.inventory.record),
                trusted_capabilities=runtime_item.trusted_capabilities,
                rules=tuple(rules),
                metadata={
                    "manifest_path": str(runtime_item.manifest_path),
                    "relative_install_path": runtime_item.inventory.record.relative_install_path,
                },
            )
        )

    return sorted(loaded, key=lambda pack: (pack.name.lower(), str(pack.path)))


def load_enabled_output_style_packs(
    omicsclaw_dir: str | Path,
) -> list[LoadedOutputStylePack]:
    loaded: list[LoadedOutputStylePack] = []
    for runtime_item in _iter_runtime_manifest_items(
        omicsclaw_dir,
        extension_types=(OUTPUT_STYLE_PACK_EXTENSION_TYPE,),
    ):
        if _requires_runtime_capability(
            runtime_item.trusted_capabilities,
            OUTPUT_STYLE_PACK_RUNTIME_CAPABILITY,
        ):
            continue

        styles: list[OutputStyleEntry] = []
        for relative_path in runtime_item.manifest.entrypoints:
            raw = _load_structured_entrypoint(runtime_item.inventory.path / relative_path)
            if raw is None:
                continue

            for index, entry in enumerate(
                _iter_entry_mappings(raw, collection_key="styles"),
                start=1,
            ):
                style_name = _safe_text(entry.get("name")) or (
                    f"{runtime_item.manifest.name}:{Path(relative_path).stem}:{index}"
                )
                instructions = _safe_text(
                    entry.get("instructions")
                    or entry.get("prompt")
                    or entry.get("content")
                )
                if not instructions:
                    continue
                styles.append(
                    OutputStyleEntry(
                        name=style_name,
                        description=_safe_text(entry.get("description")),
                        instructions=instructions,
                        aliases=_normalize_text_list(entry.get("aliases")),
                        supported_surfaces=_normalize_text_list(
                            entry.get("surfaces") or entry.get("supported_surfaces")
                        ),
                        relative_path=relative_path,
                        metadata={
                            key: value
                            for key, value in entry.items()
                            if key
                            not in {
                                "name",
                                "description",
                                "instructions",
                                "prompt",
                                "content",
                                "aliases",
                                "surfaces",
                                "supported_surfaces",
                            }
                        },
                    )
                )

        if not styles:
            continue

        loaded.append(
            LoadedOutputStylePack(
                name=runtime_item.manifest.name,
                version=runtime_item.manifest.version,
                path=runtime_item.inventory.path,
                source_kind=_safe_local_source_kind(runtime_item.inventory.record),
                trusted_capabilities=runtime_item.trusted_capabilities,
                styles=tuple(styles),
                metadata={
                    "manifest_path": str(runtime_item.manifest_path),
                    "relative_install_path": runtime_item.inventory.record.relative_install_path,
                },
            )
        )

    return sorted(loaded, key=lambda pack: (pack.name.lower(), str(pack.path)))


def load_enabled_agent_packs(
    omicsclaw_dir: str | Path,
) -> list[LoadedAgentPack]:
    loaded: list[LoadedAgentPack] = []
    for runtime_item in _iter_runtime_manifest_items(
        omicsclaw_dir,
        extension_types=(AGENT_PACK_EXTENSION_TYPE,),
    ):
        if _requires_runtime_capability(
            runtime_item.trusted_capabilities,
            AGENT_PACK_RUNTIME_CAPABILITY,
        ):
            continue

        agents: list[AgentPackEntry] = []
        for relative_path in runtime_item.manifest.entrypoints:
            raw = _load_structured_entrypoint(runtime_item.inventory.path / relative_path)
            if raw is None:
                continue

            for index, entry in enumerate(
                _iter_entry_mappings(raw, collection_key="agents"),
                start=1,
            ):
                agent_name = _safe_text(entry.get("name")) or (
                    f"{runtime_item.manifest.name}:{Path(relative_path).stem}:{index}"
                )
                agents.append(
                    AgentPackEntry(
                        name=agent_name,
                        description=_safe_text(entry.get("description")),
                        prompt=_safe_text(entry.get("prompt") or entry.get("system_prompt")),
                        tools=_normalize_text_list(entry.get("tools")),
                        relative_path=relative_path,
                        metadata={
                            key: value
                            for key, value in entry.items()
                            if key not in {"name", "description", "prompt", "system_prompt", "tools"}
                        },
                    )
                )

        if not agents:
            continue

        loaded.append(
            LoadedAgentPack(
                name=runtime_item.manifest.name,
                version=runtime_item.manifest.version,
                path=runtime_item.inventory.path,
                source_kind=_safe_local_source_kind(runtime_item.inventory.record),
                trusted_capabilities=runtime_item.trusted_capabilities,
                agents=tuple(agents),
                metadata={
                    "manifest_path": str(runtime_item.manifest_path),
                    "relative_install_path": runtime_item.inventory.record.relative_install_path,
                },
            )
        )

    return sorted(loaded, key=lambda pack: (pack.name.lower(), str(pack.path)))


def load_enabled_workflow_packs(
    omicsclaw_dir: str | Path,
) -> list[LoadedWorkflowPack]:
    loaded: list[LoadedWorkflowPack] = []
    for runtime_item in _iter_runtime_manifest_items(
        omicsclaw_dir,
        extension_types=(WORKFLOW_PACK_EXTENSION_TYPE,),
    ):
        if _requires_runtime_capability(
            runtime_item.trusted_capabilities,
            WORKFLOW_PACK_RUNTIME_CAPABILITY,
        ):
            continue

        workflows: list[WorkflowPackEntry] = []
        for relative_path in runtime_item.manifest.entrypoints:
            raw = _load_structured_entrypoint(runtime_item.inventory.path / relative_path)
            if raw is None:
                continue

            for index, entry in enumerate(
                _iter_entry_mappings(raw, collection_key="workflows"),
                start=1,
            ):
                workflow_name = _safe_text(entry.get("name")) or (
                    f"{runtime_item.manifest.name}:{Path(relative_path).stem}:{index}"
                )
                workflows.append(
                    WorkflowPackEntry(
                        name=workflow_name,
                        description=_safe_text(entry.get("description")),
                        steps=_normalize_text_list(entry.get("steps")),
                        skills=_normalize_text_list(entry.get("skills")),
                        relative_path=relative_path,
                        metadata={
                            key: value
                            for key, value in entry.items()
                            if key not in {"name", "description", "steps", "skills"}
                        },
                    )
                )

        if not workflows:
            continue

        loaded.append(
            LoadedWorkflowPack(
                name=runtime_item.manifest.name,
                version=runtime_item.manifest.version,
                path=runtime_item.inventory.path,
                source_kind=_safe_local_source_kind(runtime_item.inventory.record),
                trusted_capabilities=runtime_item.trusted_capabilities,
                workflows=tuple(workflows),
                metadata={
                    "manifest_path": str(runtime_item.manifest_path),
                    "relative_install_path": runtime_item.inventory.record.relative_install_path,
                },
            )
        )

    return sorted(loaded, key=lambda pack: (pack.name.lower(), str(pack.path)))


def load_active_hook_extensions(
    omicsclaw_dir: str | Path,
) -> list[LoadedHookExtension]:
    loaded: list[LoadedHookExtension] = []
    for runtime_item in _iter_runtime_manifest_items(
        omicsclaw_dir,
        extension_types=(
            "skill-pack",
            PROMPT_PACK_EXTENSION_TYPE,
            OUTPUT_STYLE_PACK_EXTENSION_TYPE,
            AGENT_PACK_EXTENSION_TYPE,
            WORKFLOW_PACK_EXTENSION_TYPE,
            HOOK_PACK_EXTENSION_TYPE,
        ),
    ):
        if HOOK_PACK_RUNTIME_CAPABILITY not in runtime_item.trusted_capabilities:
            continue

        hooks: list[HookPackEntry] = []
        for relative_path in runtime_item.manifest.hooks:
            raw = _load_structured_entrypoint(runtime_item.inventory.path / relative_path)
            if isinstance(raw, Mapping):
                entries = raw.get("hooks", [])
            else:
                entries = raw
            if not isinstance(entries, list):
                continue

            for index, entry in enumerate(entries, start=1):
                if not isinstance(entry, Mapping):
                    continue
                event_name = _safe_text(entry.get("event"))
                message = _safe_text(entry.get("message"))
                if not event_name or not message:
                    continue
                hook_name = _safe_text(entry.get("name")) or (
                    f"{runtime_item.manifest.name}:{Path(relative_path).stem}:{index}"
                )
                hooks.append(
                    HookPackEntry(
                        name=hook_name,
                        event=event_name,
                        mode=_hook_mode(entry.get("mode")),
                        message=message,
                        relative_path=relative_path,
                        metadata={
                            "manifest_path": str(runtime_item.manifest_path),
                        },
                    )
                )

        if not hooks:
            continue

        loaded.append(
            LoadedHookExtension(
                name=runtime_item.manifest.name,
                version=runtime_item.manifest.version,
                extension_type=runtime_item.inventory.extension_type,
                path=runtime_item.inventory.path,
                source_kind=_safe_local_source_kind(runtime_item.inventory.record),
                trusted_capabilities=runtime_item.trusted_capabilities,
                hooks=tuple(hooks),
                metadata={
                    "manifest_path": str(runtime_item.manifest_path),
                    "relative_install_path": runtime_item.inventory.record.relative_install_path,
                },
            )
        )

    return sorted(loaded, key=lambda item: (item.name.lower(), str(item.path)))


def _build_surface(
    *,
    surface: str,
    active: bool,
    entry_count: int = 0,
    labels: tuple[str, ...] = (),
    reason: str = "",
) -> ExtensionActivationSurface:
    return ExtensionActivationSurface(
        surface=surface,
        active=active,
        entry_count=entry_count,
        labels=labels,
        reason=reason,
    )


def _inactive_surface_reason(
    *,
    surface: str,
    item: InstalledExtensionInventoryEntry,
    manifest: ExtensionManifest | None,
    manifest_error: str,
    trusted_capabilities: tuple[str, ...],
) -> str:
    if not item.state.enabled:
        return item.state.disabled_reason or "disabled"
    if item.record is None and surface != ACTIVATION_SURFACE_SKILLS:
        return "missing install record"
    if _safe_local_source_kind(item.record) != "local" and surface != ACTIVATION_SURFACE_SKILLS:
        return "local/trusted source required"
    if manifest_error:
        return manifest_error
    if manifest is None:
        return "manifest unavailable"
    if surface == ACTIVATION_SURFACE_PROMPTS:
        if _requires_runtime_capability(trusted_capabilities, PROMPT_PACK_RUNTIME_CAPABILITY):
            return f"missing {PROMPT_PACK_RUNTIME_CAPABILITY} capability"
        return "no readable prompt entrypoints"
    if surface == ACTIVATION_SURFACE_OUTPUT_STYLES:
        if _requires_runtime_capability(
            trusted_capabilities,
            OUTPUT_STYLE_PACK_RUNTIME_CAPABILITY,
        ):
            return f"missing {OUTPUT_STYLE_PACK_RUNTIME_CAPABILITY} capability"
        return "no valid output style definitions"
    if surface == ACTIVATION_SURFACE_AGENTS:
        if _requires_runtime_capability(trusted_capabilities, AGENT_PACK_RUNTIME_CAPABILITY):
            return f"missing {AGENT_PACK_RUNTIME_CAPABILITY} capability"
        return "no valid agent definitions"
    if surface == ACTIVATION_SURFACE_WORKFLOWS:
        if _requires_runtime_capability(trusted_capabilities, WORKFLOW_PACK_RUNTIME_CAPABILITY):
            return f"missing {WORKFLOW_PACK_RUNTIME_CAPABILITY} capability"
        return "no valid workflow definitions"
    if surface == ACTIVATION_SURFACE_HOOKS:
        if HOOK_PACK_RUNTIME_CAPABILITY not in trusted_capabilities:
            return f"missing {HOOK_PACK_RUNTIME_CAPABILITY} capability"
        return "no valid hook definitions"
    return "not active"


def build_extension_runtime_snapshot(
    omicsclaw_dir: str | Path,
    *,
    max_prompt_chars_per_entry: int = 2000,
) -> ExtensionRuntimeSnapshot:
    prompt_packs = tuple(
        load_enabled_prompt_packs(
            omicsclaw_dir,
            max_chars_per_entry=max_prompt_chars_per_entry,
        )
    )
    output_style_packs = tuple(load_enabled_output_style_packs(omicsclaw_dir))
    agent_packs = tuple(load_enabled_agent_packs(omicsclaw_dir))
    workflow_packs = tuple(load_enabled_workflow_packs(omicsclaw_dir))
    hook_extensions = tuple(load_active_hook_extensions(omicsclaw_dir))

    prompt_by_path = {pack.path: pack for pack in prompt_packs}
    output_styles_by_path = {pack.path: pack for pack in output_style_packs}
    agent_by_path = {pack.path: pack for pack in agent_packs}
    workflow_by_path = {pack.path: pack for pack in workflow_packs}
    hooks_by_path = {item.path: item for item in hook_extensions}

    activation_records: list[ExtensionActivationRecord] = []
    for item in list_installed_extensions(omicsclaw_dir):
        record = item.record
        manifest, manifest_path, manifest_error = _load_manifest_for_entry(item)
        trusted_capabilities = _merge_trusted_capabilities(
            manifest.trusted_capabilities if manifest is not None else (),
            record.trusted_capabilities if record is not None else (),
        )
        name = (
            record.extension_name
            if record is not None and _safe_text(record.extension_name)
            else (manifest.name if manifest is not None else item.path.name)
        )

        surfaces: list[ExtensionActivationSurface] = []
        if item.extension_type == "skill-pack":
            reason = item.state.disabled_reason or "disabled"
            surfaces.append(
                _build_surface(
                    surface=ACTIVATION_SURFACE_SKILLS,
                    active=item.state.enabled,
                    entry_count=1 if item.state.enabled else 0,
                    labels=(name,) if item.state.enabled else (),
                    reason="" if item.state.enabled else reason,
                )
            )

        if item.extension_type == PROMPT_PACK_EXTENSION_TYPE:
            loaded_pack = prompt_by_path.get(item.path)
            if loaded_pack is not None:
                surfaces.append(
                    _build_surface(
                        surface=ACTIVATION_SURFACE_PROMPTS,
                        active=True,
                        entry_count=len(loaded_pack.rules),
                        labels=tuple(rule.relative_path for rule in loaded_pack.rules),
                    )
                )
            else:
                surfaces.append(
                    _build_surface(
                        surface=ACTIVATION_SURFACE_PROMPTS,
                        active=False,
                        reason=_inactive_surface_reason(
                            surface=ACTIVATION_SURFACE_PROMPTS,
                            item=item,
                            manifest=manifest,
                            manifest_error=manifest_error,
                            trusted_capabilities=trusted_capabilities,
                        ),
                    )
                )

        if item.extension_type == OUTPUT_STYLE_PACK_EXTENSION_TYPE:
            loaded_pack = output_styles_by_path.get(item.path)
            if loaded_pack is not None:
                surfaces.append(
                    _build_surface(
                        surface=ACTIVATION_SURFACE_OUTPUT_STYLES,
                        active=True,
                        entry_count=len(loaded_pack.styles),
                        labels=tuple(style.name for style in loaded_pack.styles),
                    )
                )
            else:
                surfaces.append(
                    _build_surface(
                        surface=ACTIVATION_SURFACE_OUTPUT_STYLES,
                        active=False,
                        reason=_inactive_surface_reason(
                            surface=ACTIVATION_SURFACE_OUTPUT_STYLES,
                            item=item,
                            manifest=manifest,
                            manifest_error=manifest_error,
                            trusted_capabilities=trusted_capabilities,
                        ),
                    )
                )

        if item.extension_type == AGENT_PACK_EXTENSION_TYPE:
            loaded_pack = agent_by_path.get(item.path)
            if loaded_pack is not None:
                surfaces.append(
                    _build_surface(
                        surface=ACTIVATION_SURFACE_AGENTS,
                        active=True,
                        entry_count=len(loaded_pack.agents),
                        labels=tuple(agent.name for agent in loaded_pack.agents),
                    )
                )
            else:
                surfaces.append(
                    _build_surface(
                        surface=ACTIVATION_SURFACE_AGENTS,
                        active=False,
                        reason=_inactive_surface_reason(
                            surface=ACTIVATION_SURFACE_AGENTS,
                            item=item,
                            manifest=manifest,
                            manifest_error=manifest_error,
                            trusted_capabilities=trusted_capabilities,
                        ),
                    )
                )

        if item.extension_type == WORKFLOW_PACK_EXTENSION_TYPE:
            loaded_pack = workflow_by_path.get(item.path)
            if loaded_pack is not None:
                surfaces.append(
                    _build_surface(
                        surface=ACTIVATION_SURFACE_WORKFLOWS,
                        active=True,
                        entry_count=len(loaded_pack.workflows),
                        labels=tuple(workflow.name for workflow in loaded_pack.workflows),
                    )
                )
            else:
                surfaces.append(
                    _build_surface(
                        surface=ACTIVATION_SURFACE_WORKFLOWS,
                        active=False,
                        reason=_inactive_surface_reason(
                            surface=ACTIVATION_SURFACE_WORKFLOWS,
                            item=item,
                            manifest=manifest,
                            manifest_error=manifest_error,
                            trusted_capabilities=trusted_capabilities,
                        ),
                    )
                )

        declares_hooks = item.extension_type == HOOK_PACK_EXTENSION_TYPE or bool(
            manifest.hooks if manifest is not None else ()
        )
        if declares_hooks:
            loaded_hooks = hooks_by_path.get(item.path)
            if loaded_hooks is not None:
                surfaces.append(
                    _build_surface(
                        surface=ACTIVATION_SURFACE_HOOKS,
                        active=True,
                        entry_count=len(loaded_hooks.hooks),
                        labels=tuple(hook.name for hook in loaded_hooks.hooks),
                    )
                )
            else:
                surfaces.append(
                    _build_surface(
                        surface=ACTIVATION_SURFACE_HOOKS,
                        active=False,
                        reason=_inactive_surface_reason(
                            surface=ACTIVATION_SURFACE_HOOKS,
                            item=item,
                            manifest=manifest,
                            manifest_error=manifest_error,
                            trusted_capabilities=trusted_capabilities,
                        ),
                    )
                )

        activation_records.append(
            ExtensionActivationRecord(
                name=name,
                extension_type=item.extension_type,
                path=item.path,
                enabled=item.state.enabled,
                source_kind=_safe_local_source_kind(record),
                surfaces=tuple(surfaces),
                metadata={
                    "manifest_path": str(manifest_path) if manifest_path is not None else "",
                    "trusted_capabilities": trusted_capabilities,
                    "disabled_reason": item.state.disabled_reason,
                },
            )
        )

    activation_records.sort(key=lambda entry: (entry.name.lower(), str(entry.path)))
    return ExtensionRuntimeSnapshot(
        prompt_packs=prompt_packs,
        output_style_packs=output_style_packs,
        agent_packs=agent_packs,
        workflow_packs=workflow_packs,
        hook_extensions=hook_extensions,
        activation_records=tuple(activation_records),
    )


def format_extension_runtime_surface_summary(
    snapshot: ExtensionRuntimeSnapshot,
) -> str:
    counts: dict[str, int] = defaultdict(int)
    for record in snapshot.activation_records:
        for surface in record.surfaces:
            if surface.active:
                counts[surface.surface] += 1
    ordered = (
        ACTIVATION_SURFACE_SKILLS,
        ACTIVATION_SURFACE_PROMPTS,
        ACTIVATION_SURFACE_OUTPUT_STYLES,
        ACTIVATION_SURFACE_AGENTS,
        ACTIVATION_SURFACE_WORKFLOWS,
        ACTIVATION_SURFACE_HOOKS,
    )
    return ", ".join(
        f"{surface}={counts.get(surface, 0)}"
        for surface in ordered
        if counts.get(surface, 0)
    ) or "no active extension runtime surfaces"


def load_prompt_pack_runtime_context(
    omicsclaw_dir: str | Path,
    *,
    max_chars_per_entry: int = 2000,
    max_total_chars: int = 6000,
    surface: str = "",
    skill: str = "",
    query: str = "",
    domain: str = "",
) -> PromptPackRuntimeContext:
    """Build a context block for enabled prompt packs.

    The additional selection hints are accepted for future filtering logic; the
    current implementation activates all enabled local prompt packs.
    """

    del surface, skill, query, domain

    packs = load_enabled_prompt_packs(
        omicsclaw_dir,
        max_chars_per_entry=max_chars_per_entry,
    )
    if not packs:
        return PromptPackRuntimeContext()

    header_lines = [
        "## Active Local Prompt Packs",
        "",
        "Enabled local prompt packs are active for this session. Core OmicsClaw guardrails override them on conflict.",
    ]
    content_parts = ["\n".join(header_lines).strip()]
    active_names: list[str] = []
    omitted_names: list[str] = []

    for index, pack in enumerate(packs):
        version_suffix = f" v{pack.version}" if pack.version else ""
        pack_lines = [f"### {pack.name}{version_suffix}"]
        for rule in pack.rules:
            pack_lines.append(f"[{rule.relative_path}]")
            pack_lines.append(rule.content)
        pack_block = "\n\n".join(pack_lines).strip()

        candidate_parts = [*content_parts, pack_block]
        candidate_text = "\n\n".join(candidate_parts).strip()
        if max_total_chars > 0 and len(candidate_text) > max_total_chars:
            if active_names:
                omitted_names.extend(remaining.name for remaining in packs[index:])
                break

            available_chars = max(max_total_chars - len(content_parts[0]) - 32, 0)
            if available_chars:
                truncated = pack_block[:available_chars].rstrip()
                if truncated:
                    content_parts.append(truncated + "\n\n[truncated due to context budget]")
                    active_names.append(pack.name)
                else:
                    omitted_names.append(pack.name)
            else:
                omitted_names.append(pack.name)
            omitted_names.extend(remaining.name for remaining in packs[index + 1:])
            break

        content_parts.append(pack_block)
        active_names.append(pack.name)

    if omitted_names:
        content_parts.append(
            "Additional prompt packs omitted due to context budget: "
            + ", ".join(omitted_names)
        )

    return PromptPackRuntimeContext(
        content="\n\n".join(part for part in content_parts if part).strip(),
        active_prompt_packs=tuple(active_names),
        omitted_prompt_packs=tuple(omitted_names),
        metadata={
            "pack_count": len(active_names),
            "available_pack_names": tuple(pack.name for pack in packs),
            "max_chars_per_entry": max_chars_per_entry,
            "max_total_chars": max_total_chars,
        },
    )


def build_prompt_pack_context(
    omicsclaw_dir: str | Path,
    *,
    max_chars_per_entry: int = 2000,
    max_total_chars: int = 6000,
    surface: str = "",
    skill: str = "",
    query: str = "",
    domain: str = "",
) -> str:
    return load_prompt_pack_runtime_context(
        omicsclaw_dir,
        max_chars_per_entry=max_chars_per_entry,
        max_total_chars=max_total_chars,
        surface=surface,
        skill=skill,
        query=query,
        domain=domain,
    ).content


__all__ = [
    "ACTIVATION_SURFACE_AGENTS",
    "ACTIVATION_SURFACE_HOOKS",
    "ACTIVATION_SURFACE_OUTPUT_STYLES",
    "ACTIVATION_SURFACE_PROMPTS",
    "ACTIVATION_SURFACE_SKILLS",
    "ACTIVATION_SURFACE_WORKFLOWS",
    "AGENT_PACK_EXTENSION_TYPE",
    "AGENT_PACK_RUNTIME_CAPABILITY",
    "AgentPackEntry",
    "ExtensionActivationRecord",
    "ExtensionActivationSurface",
    "ExtensionRuntimeSnapshot",
    "HOOK_PACK_EXTENSION_TYPE",
    "HOOK_PACK_RUNTIME_CAPABILITY",
    "HookPackEntry",
    "LoadedAgentPack",
    "LoadedHookExtension",
    "LoadedOutputStylePack",
    "LoadedPromptPack",
    "LoadedWorkflowPack",
    "OUTPUT_STYLE_PACK_EXTENSION_TYPE",
    "OUTPUT_STYLE_PACK_RUNTIME_CAPABILITY",
    "OutputStyleEntry",
    "PROMPT_PACK_EXTENSION_TYPE",
    "PROMPT_PACK_RUNTIME_CAPABILITY",
    "PromptPackRuleEntry",
    "PromptPackRuntimeContext",
    "WORKFLOW_PACK_EXTENSION_TYPE",
    "WORKFLOW_PACK_RUNTIME_CAPABILITY",
    "WorkflowPackEntry",
    "build_extension_runtime_snapshot",
    "build_prompt_pack_context",
    "format_extension_runtime_surface_summary",
    "load_active_hook_extensions",
    "load_enabled_agent_packs",
    "load_enabled_output_style_packs",
    "load_enabled_prompt_packs",
    "load_enabled_workflow_packs",
    "load_prompt_pack_runtime_context",
]
