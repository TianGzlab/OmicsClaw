"""Validation helpers for installable OmicsClaw extension packs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from omicsclaw.core.registry import OmicsRegistry
from omicsclaw.extensions.manifest import (
    ExtensionManifest,
    RESTRICTED_UNTRUSTED_CAPABILITIES,
    UNTRUSTED_ALLOWED_CAPABILITIES,
    UNTRUSTED_ALLOWED_EXTENSION_TYPES,
    discover_extension_manifest,
    load_extension_manifest,
)
from omicsclaw.knowledge.registry import parse_frontmatter


@dataclass(slots=True)
class ExtensionValidationReport:
    valid: bool
    extension_dir: Path
    extension_type: str = ""
    manifest: ExtensionManifest | None = None
    script_paths: list[Path] = field(default_factory=list)
    entrypoint_paths: list[Path] = field(default_factory=list)
    has_skill_md: bool = False
    effective_name: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    restricted_capabilities: list[str] = field(default_factory=list)

    @property
    def skill_dir(self) -> Path:
        return self.extension_dir


SkillPackValidationReport = ExtensionValidationReport

_RUNTIME_SURFACE_CAPABILITY_HINTS = {
    "prompt-pack": "prompt-rules",
    "output-style-pack": "output-style-entry",
    "agent-pack": "agent-entry",
    "workflow-pack": "workflow-entry",
}


def _validate_manifest_contract(
    path: Path,
    manifest: ExtensionManifest,
    *,
    entrypoint_paths: list[Path],
    errors: list[str],
) -> None:
    for required_file in manifest.required_files:
        if not (path / required_file).exists():
            errors.append(f"Extension manifest requires missing file: {required_file}")
    for entrypoint in manifest.entrypoints:
        candidate = path / entrypoint
        if not candidate.exists():
            errors.append(f"Extension manifest entrypoint not found: {entrypoint}")
        else:
            entrypoint_paths.append(candidate)
    for hook_path in manifest.hooks:
        candidate = path / hook_path
        if not candidate.exists():
            errors.append(f"Extension manifest hook file not found: {hook_path}")
    if manifest.hooks and "hooks" not in manifest.trusted_capabilities:
        errors.append(
            "Extension manifests that declare hooks must request the 'hooks' trusted capability."
        )


def _apply_source_policy(
    manifest: ExtensionManifest | None,
    extension_type: str,
    *,
    source_kind: str,
    errors: list[str],
) -> list[str]:
    restricted: list[str] = []
    if source_kind == "local":
        return restricted

    if extension_type and extension_type not in UNTRUSTED_ALLOWED_EXTENSION_TYPES:
        errors.append(
            "Untrusted extension sources may only install 'skill-pack' extensions."
        )

    if manifest is None:
        return restricted

    for capability in manifest.trusted_capabilities:
        if capability in RESTRICTED_UNTRUSTED_CAPABILITIES:
            restricted.append(capability)
        elif capability not in UNTRUSTED_ALLOWED_CAPABILITIES:
            restricted.append(capability)

    if restricted:
        errors.append(
            "Untrusted extension sources may not request privileged capabilities: "
            + ", ".join(sorted(restricted))
        )
    return restricted


def validate_extension_directory(
    extension_dir: str | Path,
    *,
    source_kind: str = "local",
) -> ExtensionValidationReport:
    path = Path(extension_dir)
    script_paths = sorted(path.glob("*.py"))
    skill_md_path = path / "SKILL.md"
    has_skill_md = skill_md_path.exists()
    errors: list[str] = []
    warnings: list[str] = []
    entrypoint_paths: list[Path] = []
    manifest: ExtensionManifest | None = None
    extension_type = ""
    effective_name = path.name

    manifest_path = discover_extension_manifest(path)
    if manifest_path is not None:
        try:
            manifest = load_extension_manifest(manifest_path)
        except ValueError as exc:
            errors.append(str(exc))
        else:
            extension_type = manifest.type
            effective_name = manifest.name or path.name
            _validate_manifest_contract(
                path,
                manifest,
                entrypoint_paths=entrypoint_paths,
                errors=errors,
            )
    elif OmicsRegistry._looks_like_skill_dir(path):
        extension_type = "skill-pack"
        warnings.append(
            "Legacy skill pack detected without omicsclaw-extension.json; installing with inferred 'skill-pack' type."
        )
    else:
        errors.append(
            "No omicsclaw-extension.json manifest found, and the directory does not match the legacy skill-pack layout."
        )

    restricted_capabilities = _apply_source_policy(
        manifest,
        extension_type,
        source_kind=source_kind,
        errors=errors,
    )

    if extension_type == "skill-pack":
        if not script_paths and not has_skill_md:
            errors.append(
                "No .py script or SKILL.md found in the installed directory.\n"
                "The skill may not be loadable. Make sure the directory follows OmicsClaw conventions."
            )

        if has_skill_md:
            content = skill_md_path.read_text(encoding="utf-8")
            if content.lstrip().startswith("---"):
                frontmatter = parse_frontmatter(content)
                missing_fields = [
                    field_name
                    for field_name in ("name", "description", "version")
                    if not str(frontmatter.get(field_name, "") or "").strip()
                ]
                if missing_fields:
                    warnings.append(
                        "SKILL.md frontmatter missing recommended fields: "
                        + ", ".join(missing_fields)
                    )
    elif extension_type:
        if manifest is None:
            errors.append(
                f"Extension type '{extension_type}' requires an omicsclaw-extension.json manifest."
            )
        if manifest is not None and extension_type != "hook-pack" and not manifest.entrypoints:
            errors.append(
                f"Extension type '{extension_type}' must declare at least one manifest entrypoint."
            )
        if manifest is not None and extension_type == "hook-pack" and not manifest.hooks:
            errors.append(
                "Extension type 'hook-pack' must declare at least one hook manifest file."
            )
        hinted_capability = _RUNTIME_SURFACE_CAPABILITY_HINTS.get(extension_type, "")
        if (
            manifest is not None
            and hinted_capability
            and manifest.trusted_capabilities
            and hinted_capability not in manifest.trusted_capabilities
        ):
            warnings.append(
                f"Extension type '{extension_type}' declares trusted_capabilities but omits "
                f"'{hinted_capability}'; runtime activation will be skipped until it is added."
            )

    return ExtensionValidationReport(
        valid=not errors,
        extension_dir=path,
        extension_type=extension_type,
        manifest=manifest,
        script_paths=script_paths,
        entrypoint_paths=entrypoint_paths,
        has_skill_md=has_skill_md,
        effective_name=effective_name,
        errors=errors,
        warnings=warnings,
        restricted_capabilities=restricted_capabilities,
    )


def validate_skill_pack_directory(skill_dir: str | Path) -> SkillPackValidationReport:
    report = validate_extension_directory(skill_dir)
    errors = list(report.errors)
    if report.extension_type and report.extension_type != "skill-pack":
        errors.append(
            f"Extension manifest type must be 'skill-pack' for skill installs: {report.extension_dir}"
        )

    return SkillPackValidationReport(
        valid=not errors,
        extension_dir=report.extension_dir,
        extension_type=report.extension_type,
        manifest=report.manifest,
        script_paths=report.script_paths,
        entrypoint_paths=report.entrypoint_paths,
        has_skill_md=report.has_skill_md,
        effective_name=report.effective_name,
        errors=errors,
        warnings=report.warnings,
        restricted_capabilities=report.restricted_capabilities,
    )


__all__ = [
    "ExtensionValidationReport",
    "SkillPackValidationReport",
    "validate_extension_directory",
    "validate_skill_pack_directory",
]
