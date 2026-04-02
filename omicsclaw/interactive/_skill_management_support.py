"""Shared helpers for extension install/uninstall/list command flows."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from omicsclaw.extensions import (
    build_extension_runtime_snapshot,
    extension_store_dir,
    find_installed_extensions,
    format_extension_runtime_surface_summary,
    list_installed_extensions,
    load_extension_state,
    set_extension_enabled,
    validate_extension_directory,
    write_extension_state,
    write_install_record,
)
from omicsclaw.interactive._session import format_relative_time
from omicsclaw.runtime.events import EVENT_EXTENSION_INSTALLED
from omicsclaw.runtime.hook_payloads import ExtensionHookPayload
from omicsclaw.runtime.hooks import (
    HOOK_MODE_NOTICE,
    build_default_lifecycle_hook_runtime,
    format_hook_notice_block,
)


@dataclass(slots=True)
class SkillCommandStatus:
    level: str
    text: str


@dataclass(slots=True)
class SkillInstallPlan:
    source_kind: str
    skill_name: str
    dest: Path | None = None
    source_url: str = ""
    source_path: Path | None = None
    repo_url: str = ""
    repo_branch: str = ""
    repo_subpath: str = ""
    expected_type: str = ""


@dataclass(slots=True)
class SkillRemovalPlan:
    skill_name: str
    candidate: Path
    extension_type: str = "skill-pack"


@dataclass(slots=True)
class SkillEnablementPlan:
    skill_name: str
    candidate: Path
    enable: bool
    extension_type: str = "skill-pack"


@dataclass(slots=True)
class InstalledSkillEntry:
    skill_name: str
    extension_type: str = "skill-pack"
    source_kind: str = ""
    source: str = ""
    manifest_version: str = ""
    installed_at: str = ""
    installed_label: str = ""
    tracked: bool = False
    enabled: bool = True
    disabled_reason: str = ""
    trusted_capabilities: list[str] = field(default_factory=list)
    active_surfaces: list[str] = field(default_factory=list)
    inactive_surfaces: list[str] = field(default_factory=list)
    runtime_entries: list[str] = field(default_factory=list)
    path: str = ""


@dataclass(slots=True)
class InstalledSkillListView:
    entries: list[InstalledSkillEntry] = field(default_factory=list)
    empty_text: str = "No installed extensions found."
    hint_text: str = "Use /install-extension <src> or /install-skill <src> to add local or GitHub packs."


def build_skill_install_usage_text() -> str:
    return (
        "Usage: /install-skill <local-path | github-url>\n"
        "Examples:\n"
        "  /install-skill /path/to/my-skill\n"
        "  /install-skill https://github.com/user/my-skill-repo\n"
        "  /install-skill https://github.com/user/repo/tree/main/skills/my-skill"
    )


def build_extension_install_usage_text() -> str:
    return (
        "Usage: /install-extension <local-path | github-url>\n"
        "Examples:\n"
        "  /install-extension /path/to/my-extension\n"
        "  /install-extension https://github.com/user/my-skill-repo\n"
        "Notes:\n"
        "  - GitHub sources are treated as untrusted and may only install skill-pack extensions.\n"
        "  - agent-pack, prompt-pack, workflow-pack, hook-pack, and mcp-bundle are local-source extension types.\n"
        "  - hook-pack installs are tracked in a disabled state until explicitly enabled."
    )


def build_extension_toggle_usage_text(*, enable: bool) -> str:
    command = "/enable-extension" if enable else "/disable-extension"
    return f"Usage: {command} <extension-name>"


def _extension_install_hook_statuses(
    *,
    omicsclaw_dir: str | Path,
    extension_name: str,
    extension_type: str,
    source_kind: str,
    install_path: Path,
    enabled: bool,
    trusted_capabilities: list[str] | tuple[str, ...],
    manifest_version: str = "",
) -> list[SkillCommandStatus]:
    runtime = build_default_lifecycle_hook_runtime(omicsclaw_dir)
    runtime.emit(
        EVENT_EXTENSION_INSTALLED,
        ExtensionHookPayload(
            extension_name=extension_name,
            extension_type=extension_type,
            source_kind=source_kind,
            install_path=str(install_path),
            enabled=enabled,
            trusted_capabilities=tuple(trusted_capabilities),
            manifest_version=manifest_version,
        ),
        context={
            "workspace": str(install_path),
            "source": "extension_install",
        },
    )
    notice_block = format_hook_notice_block(
        runtime.consume_pending_messages(
            mode=HOOK_MODE_NOTICE,
            event_names=(EVENT_EXTENSION_INSTALLED,),
        )
    )
    if not notice_block:
        return []
    return [SkillCommandStatus("info", notice_block)]


def _infer_github_source(source: str) -> tuple[str, str, str]:
    normalized = source.strip()
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or parsed.netloc != "github.com":
        return normalized, "", ""

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return normalized, "", ""

    repo_url = f"{parsed.scheme}://{parsed.netloc}/{parts[0]}/{parts[1]}.git"
    if len(parts) >= 5 and parts[2] == "tree":
        branch = parts[3]
        subpath = "/".join(parts[4:])
        return repo_url, branch, subpath
    return repo_url, "", ""


def _resolve_install_dest(
    *,
    omicsclaw_dir: str | Path,
    extension_type: str,
    install_name: str,
) -> Path:
    return extension_store_dir(omicsclaw_dir, extension_type) / install_name


def _source_exists_message(source_path: Path) -> SkillCommandStatus:
    return SkillCommandStatus(
        "warning",
        f"Extension '{source_path.name}' already exists at {source_path}\n"
        "To reinstall, uninstall it first.",
    )


def prepare_extension_install_plan(
    src: str,
    *,
    omicsclaw_dir: str | Path,
    expected_type: str = "",
) -> SkillInstallPlan | SkillCommandStatus:
    source = src.strip()
    if not source:
        return SkillCommandStatus("error", build_extension_install_usage_text())

    is_github = source.startswith(
        ("https://github.com", "http://github.com", "git@github.com")
    )
    if is_github:
        repo_url, repo_branch, repo_subpath = _infer_github_source(source)
        install_name = repo_subpath.split("/")[-1] if repo_subpath else repo_url.rstrip("/").split("/")[-1]
        if install_name.endswith(".git"):
            install_name = install_name[:-4]
        dest = (
            _resolve_install_dest(
                omicsclaw_dir=omicsclaw_dir,
                extension_type=expected_type or "skill-pack",
                install_name=install_name,
            )
            if expected_type
            else None
        )
        if dest is not None and dest.exists():
            return _source_exists_message(dest)
        return SkillInstallPlan(
            source_kind="github",
            skill_name=install_name,
            dest=dest,
            source_url=source,
            repo_url=repo_url,
            repo_branch=repo_branch,
            repo_subpath=repo_subpath,
            expected_type=expected_type,
        )

    source_path = Path(source).expanduser().resolve()
    if not source_path.exists():
        return SkillCommandStatus("error", f"Path not found: {source_path}")
    if not source_path.is_dir():
        return SkillCommandStatus(
            "error",
            f"Source must be a directory (extension folder): {source_path}",
        )

    dest = (
        _resolve_install_dest(
            omicsclaw_dir=omicsclaw_dir,
            extension_type=expected_type or "skill-pack",
            install_name=source_path.name,
        )
        if expected_type
        else None
    )
    if dest is not None and dest.exists():
        return _source_exists_message(dest)

    return SkillInstallPlan(
        source_kind="local",
        skill_name=source_path.name,
        dest=dest,
        source_path=source_path,
        expected_type=expected_type,
    )


def prepare_skill_install_plan(
    src: str,
    *,
    omicsclaw_dir: str | Path,
) -> SkillInstallPlan | SkillCommandStatus:
    plan_or_status = prepare_extension_install_plan(
        src,
        omicsclaw_dir=omicsclaw_dir,
        expected_type="skill-pack",
    )
    if isinstance(plan_or_status, SkillCommandStatus) and not src.strip():
        return SkillCommandStatus("error", build_skill_install_usage_text())
    return plan_or_status


def build_skill_install_start_status(plan: SkillInstallPlan) -> SkillCommandStatus:
    if plan.source_kind == "github":
        return SkillCommandStatus(
            "info",
            f"Staging '{plan.skill_name}' from GitHub for validation...",
        )
    assert plan.source_path is not None
    return SkillCommandStatus(
        "info",
        f"Staging '{plan.skill_name}' from {plan.source_path} for validation...",
    )


def build_skill_install_copy_status(plan: SkillInstallPlan) -> SkillCommandStatus:
    return SkillCommandStatus("success", f"Staged local extension source for {plan.skill_name}")


def build_skill_install_clone_status(plan: SkillInstallPlan) -> SkillCommandStatus:
    target = plan.repo_url or plan.source_url
    suffix = f" (subpath: {plan.repo_subpath})" if plan.repo_subpath else ""
    return SkillCommandStatus("success", f"Cloned {target}{suffix}")


def _build_validation_statuses(validation) -> list[SkillCommandStatus]:
    statuses: list[SkillCommandStatus] = []
    found_text = f"type={validation.extension_type or 'unknown'}"
    if validation.script_paths:
        found_text += f", scripts={len(validation.script_paths)}"
    if validation.has_skill_md:
        found_text += ", SKILL.md=yes"
    if validation.manifest is not None:
        found_text += f", manifest={validation.manifest.name}@{validation.manifest.version}"
    statuses.append(SkillCommandStatus("info", f"Validated extension candidate: {found_text}"))
    for warning in validation.warnings:
        statuses.append(SkillCommandStatus("warning", warning))
    for error in validation.errors:
        statuses.append(SkillCommandStatus("error", error))
    return statuses


def _default_enabled_state_for_extension_type(extension_type: str) -> bool:
    return extension_type != "hook-pack"


def _format_surface_brief(surface) -> str:
    if getattr(surface, "entry_count", 0):
        return f"{surface.surface}({surface.entry_count})"
    return surface.surface


def _format_surface_inactive(surface) -> str:
    reason = str(getattr(surface, "reason", "") or "").strip()
    if reason:
        return f"{surface.surface}: {reason}"
    return surface.surface


def _format_surface_runtime_entries(surface) -> str:
    labels = [str(label).strip() for label in getattr(surface, "labels", ()) if str(label).strip()]
    if not labels:
        return ""
    preview = labels[:3]
    suffix = " ..." if len(labels) > 3 else ""
    return f"{surface.surface}: {', '.join(preview)}{suffix}"


def _build_runtime_surface_lists(activation_record) -> tuple[list[str], list[str], list[str]]:
    if activation_record is None:
        return [], [], []

    active_surfaces: list[str] = []
    inactive_surfaces: list[str] = []
    runtime_entries: list[str] = []
    for surface in activation_record.surfaces:
        if surface.active:
            active_surfaces.append(_format_surface_brief(surface))
            entry_text = _format_surface_runtime_entries(surface)
            if entry_text:
                runtime_entries.append(entry_text)
        else:
            inactive_surfaces.append(_format_surface_inactive(surface))
    return active_surfaces, inactive_surfaces, runtime_entries


def _build_post_install_statuses(
    *,
    omicsclaw_dir: str | Path,
    install_name: str,
    extension_type: str,
    install_path: Path,
) -> list[SkillCommandStatus]:
    snapshot = build_extension_runtime_snapshot(omicsclaw_dir)
    activation_record = next(
        (record for record in snapshot.activation_records if record.path == install_path),
        None,
    )
    active_surfaces, inactive_surfaces, _runtime_entries = _build_runtime_surface_lists(
        activation_record
    )

    statuses = [
        SkillCommandStatus(
            "success",
            f"Extension '{install_name}' ({extension_type}) installed at {install_path}.",
        )
    ]
    if active_surfaces:
        statuses.append(
            SkillCommandStatus(
                "info",
                "Active runtime surfaces: " + ", ".join(active_surfaces),
            )
        )
    elif inactive_surfaces:
        statuses.append(
            SkillCommandStatus(
                "info",
                "Runtime activation pending: " + ", ".join(inactive_surfaces),
            )
        )

    if extension_type == "hook-pack":
        statuses.append(
            SkillCommandStatus(
                "info",
                "Hook packs install in a gated state. Use /enable-extension "
                f"{install_name} after reviewing the hook behavior.",
            )
        )
    return statuses


def _finish_install_from_candidate(
    candidate_dir: Path,
    *,
    plan: SkillInstallPlan,
    omicsclaw_dir: str | Path,
) -> list[SkillCommandStatus]:
    validation = validate_extension_directory(
        candidate_dir,
        source_kind=plan.source_kind,
    )
    statuses = _build_validation_statuses(validation)
    if not validation.valid:
        statuses.append(
            SkillCommandStatus(
                "error",
                f"Extension '{plan.skill_name}' failed validation and was not installed.",
            )
        )
        return statuses

    if plan.expected_type and validation.extension_type != plan.expected_type:
        statuses.append(
            SkillCommandStatus(
                "error",
                f"Expected extension type '{plan.expected_type}', but candidate declares '{validation.extension_type}'.",
            )
        )
        return statuses

    install_name = validation.effective_name or plan.skill_name
    dest = _resolve_install_dest(
        omicsclaw_dir=omicsclaw_dir,
        extension_type=validation.extension_type,
        install_name=install_name,
    )
    if dest.exists():
        statuses.append(_source_exists_message(dest))
        return statuses

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(candidate_dir, dest)
    enabled_by_default = _default_enabled_state_for_extension_type(validation.extension_type)
    try:
        write_install_record(
            dest,
            extension_name=install_name,
            source_kind=plan.source_kind,
            source=plan.source_url or str(plan.source_path or ""),
            manifest=validation.manifest,
            extension_type=validation.extension_type,
            relative_install_path=str(dest.relative_to(Path(omicsclaw_dir))),
        )
        write_extension_state(
            dest,
            enabled=enabled_by_default,
            disabled_reason=(
                "hook-pack installs are gated until explicitly enabled"
                if not enabled_by_default
                else ""
            ),
        )
    except Exception as exc:
        statuses.append(
            SkillCommandStatus(
                "warning",
                f"Extension installed to {dest}, but install metadata could not be written: {exc}",
            )
        )

    if validation.extension_type == "skill-pack":
        refresh_error = refresh_skill_registry()
        if refresh_error:
            statuses.append(
                SkillCommandStatus(
                    "warning",
                    f"Skill pack installed to {dest}, but registry refresh failed: {refresh_error}",
                )
            )
        else:
            statuses.append(
                SkillCommandStatus(
                    "success",
                    f"Skill pack '{install_name}' installed and registered at {dest}.",
                )
            )
    elif validation.extension_type == "prompt-pack":
        statuses.append(
            SkillCommandStatus(
                "success",
                f"Extension '{install_name}' (prompt-pack) installed at {dest} and will be applied while enabled.",
            )
        )
    else:
        statuses.extend(
            _build_post_install_statuses(
                omicsclaw_dir=omicsclaw_dir,
                install_name=install_name,
                extension_type=validation.extension_type,
                install_path=dest,
            )
        )

    statuses.extend(
        _extension_install_hook_statuses(
            omicsclaw_dir=omicsclaw_dir,
            extension_name=install_name,
            extension_type=validation.extension_type,
            source_kind=plan.source_kind,
            install_path=dest,
            enabled=enabled_by_default,
            trusted_capabilities=(
                validation.manifest.trusted_capabilities if validation.manifest is not None else []
            ),
            manifest_version=(
                validation.manifest.version if validation.manifest is not None else ""
            ),
        )
    )
    return statuses


def finalize_installed_skill(plan: SkillInstallPlan) -> list[SkillCommandStatus]:
    if plan.dest is None:
        return [
            SkillCommandStatus(
                "error",
                "Install plan has no destination. Use install_extension_from_source() for staged installs.",
            )
        ]
    validation = validate_extension_directory(
        plan.dest,
        source_kind=plan.source_kind,
    )
    statuses = _build_validation_statuses(validation)
    if not validation.valid:
        statuses.append(
            SkillCommandStatus(
                "error",
                f"Extension '{plan.skill_name}' failed validation and was not registered.",
            )
        )
        return statuses

    if plan.expected_type and validation.extension_type != plan.expected_type:
        statuses.append(
            SkillCommandStatus(
                "error",
                f"Expected extension type '{plan.expected_type}', but candidate declares '{validation.extension_type}'.",
            )
        )
        return statuses

    source_root = plan.dest.parents[2]
    install_name = validation.effective_name or plan.skill_name
    enabled_by_default = _default_enabled_state_for_extension_type(validation.extension_type)
    try:
        write_install_record(
            plan.dest,
            extension_name=install_name,
            source_kind=plan.source_kind,
            source=plan.source_url or str(plan.source_path or ""),
            manifest=validation.manifest,
            extension_type=validation.extension_type,
            relative_install_path=str(plan.dest.relative_to(source_root)),
        )
        write_extension_state(
            plan.dest,
            enabled=enabled_by_default,
            disabled_reason=(
                "hook-pack installs are gated until explicitly enabled"
                if not enabled_by_default
                else ""
            ),
        )
    except Exception as exc:
        statuses.append(
            SkillCommandStatus(
                "warning",
                f"Extension metadata could not be written: {exc}",
            )
        )

    refresh_error = ""
    if validation.extension_type == "skill-pack":
        refresh_error = refresh_skill_registry()
    if refresh_error:
        statuses.append(
            SkillCommandStatus(
                "warning",
                f"Extension '{install_name}' registered on disk, but registry refresh failed: {refresh_error}",
            )
        )
    elif validation.extension_type == "skill-pack":
        statuses.append(
            SkillCommandStatus(
                "success",
                f"Skill pack '{install_name}' installed and registered at {plan.dest}.",
            )
        )
    elif validation.extension_type == "prompt-pack":
        statuses.append(
            SkillCommandStatus(
                "success",
                f"Extension '{install_name}' (prompt-pack) installed at {plan.dest} and will be applied while enabled.",
            )
        )
    else:
        statuses.extend(
            _build_post_install_statuses(
                omicsclaw_dir=source_root,
                install_name=install_name,
                extension_type=validation.extension_type,
                install_path=plan.dest,
            )
        )
    statuses.extend(
        _extension_install_hook_statuses(
            omicsclaw_dir=source_root,
            extension_name=install_name,
            extension_type=validation.extension_type,
            source_kind=plan.source_kind,
            install_path=plan.dest,
            enabled=enabled_by_default,
            trusted_capabilities=(
                validation.manifest.trusted_capabilities if validation.manifest is not None else []
            ),
            manifest_version=(
                validation.manifest.version if validation.manifest is not None else ""
            ),
        )
    )
    return statuses


def _stage_local_source(plan: SkillInstallPlan, staging_root: Path) -> tuple[Path, SkillCommandStatus]:
    assert plan.source_path is not None
    candidate = staging_root / plan.source_path.name
    shutil.copytree(plan.source_path, candidate)
    return candidate, build_skill_install_copy_status(plan)


def _stage_github_source(plan: SkillInstallPlan, staging_root: Path) -> tuple[Path, SkillCommandStatus]:
    checkout_dir = staging_root / "repo"
    target_url = plan.repo_url or plan.source_url
    clone_cmd = ["git", "clone", "--depth=1", target_url, str(checkout_dir)]
    result = subprocess.run(
        clone_cmd,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[:500] or "git clone failed")
    if plan.repo_branch:
        checkout = subprocess.run(
            ["git", "-C", str(checkout_dir), "checkout", plan.repo_branch],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if checkout.returncode != 0:
            raise RuntimeError(checkout.stderr[:500] or f"git checkout {plan.repo_branch} failed")
    candidate = checkout_dir / plan.repo_subpath if plan.repo_subpath else checkout_dir
    if not candidate.exists() or not candidate.is_dir():
        raise RuntimeError(
            f"GitHub source path not found after clone: {plan.repo_subpath or '.'}"
        )
    return candidate, build_skill_install_clone_status(plan)


def install_extension_from_source(
    src: str,
    *,
    omicsclaw_dir: str | Path,
    expected_type: str = "",
) -> list[SkillCommandStatus]:
    plan_or_status = prepare_extension_install_plan(
        src,
        omicsclaw_dir=omicsclaw_dir,
        expected_type=expected_type,
    )
    if isinstance(plan_or_status, SkillCommandStatus):
        return [plan_or_status]
    plan = plan_or_status

    statuses = [build_skill_install_start_status(plan)]
    staging_base = Path(omicsclaw_dir) / "installed_extensions" / ".staging"
    staging_base.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.TemporaryDirectory(dir=staging_base) as temp_dir:
            staging_root = Path(temp_dir)
            if plan.source_kind == "github":
                candidate_dir, stage_status = _stage_github_source(plan, staging_root)
            else:
                candidate_dir, stage_status = _stage_local_source(plan, staging_root)
            statuses.append(stage_status)
            statuses.extend(
                _finish_install_from_candidate(
                    candidate_dir,
                    plan=plan,
                    omicsclaw_dir=omicsclaw_dir,
                )
            )
    except FileNotFoundError:
        statuses.append(
            SkillCommandStatus("error", "git is not installed. Please install git and try again.")
        )
    except subprocess.TimeoutExpired:
        statuses.append(
            SkillCommandStatus("error", "Git operation timed out after 120 seconds.")
        )
    except Exception as exc:
        statuses.append(
            SkillCommandStatus("error", f"Extension install failed: {exc}")
        )
    return statuses


def install_skill_from_source(
    src: str,
    *,
    omicsclaw_dir: str | Path,
) -> list[SkillCommandStatus]:
    statuses = install_extension_from_source(
        src,
        omicsclaw_dir=omicsclaw_dir,
        expected_type="skill-pack",
    )
    if len(statuses) == 1 and statuses[0].text == build_extension_install_usage_text():
        return [SkillCommandStatus("error", build_skill_install_usage_text())]
    return statuses


def prepare_extension_uninstall_plan(
    name: str,
    *,
    omicsclaw_dir: str | Path,
    expected_type: str = "",
) -> SkillRemovalPlan | SkillCommandStatus:
    extension_name = name.strip()
    if not extension_name:
        command = "/uninstall-skill" if expected_type == "skill-pack" else "/uninstall-extension"
        return SkillCommandStatus("error", f"Usage: {command} <name>")

    matches = find_installed_extensions(
        omicsclaw_dir,
        extension_name,
        extension_type=expected_type,
    )
    if len(matches) == 1:
        match = matches[0]
        return SkillRemovalPlan(
            skill_name=match.record.extension_name if match.record is not None else match.path.name,
            candidate=match.path,
            extension_type=match.extension_type,
        )

    if not matches and expected_type == "skill-pack":
        skills_dir = Path(omicsclaw_dir) / "skills"
        found_builtin = any(
            (domain_path / extension_name).exists()
            for domain_path in skills_dir.iterdir()
            if domain_path.is_dir() and not domain_path.name.startswith((".", "__"))
        )
        if found_builtin:
            return SkillCommandStatus(
                "warning",
                f"Skill '{extension_name}' is a built-in skill and cannot be removed via /uninstall-skill.\n"
                "Built-in skills are part of the OmicsClaw core and should not be deleted.",
            )

    if len(matches) > 1:
        names = ", ".join(f"{entry.extension_type}:{entry.path.name}" for entry in matches)
        return SkillCommandStatus(
            "error",
            f"Extension name '{extension_name}' is ambiguous. Matches: {names}",
        )

    view = build_installed_extension_list_view(
        omicsclaw_dir=omicsclaw_dir,
        extension_type=expected_type,
    )
    text = (
        f"Installed extension '{extension_name}' not found."
        if not expected_type
        else f"User-installed skill '{extension_name}' not found."
    )
    if view.entries:
        text += "\nInstalled entries: " + ", ".join(entry.skill_name for entry in view.entries)
    else:
        text += "\nNo installed entries found."
    return SkillCommandStatus("error", text)


def prepare_skill_uninstall_plan(
    name: str,
    *,
    omicsclaw_dir: str | Path,
) -> SkillRemovalPlan | SkillCommandStatus:
    return prepare_extension_uninstall_plan(
        name,
        omicsclaw_dir=omicsclaw_dir,
        expected_type="skill-pack",
    )


def finalize_uninstalled_skill(plan: SkillRemovalPlan) -> SkillCommandStatus:
    refresh_error = ""
    if plan.extension_type == "skill-pack":
        refresh_error = refresh_skill_registry()
    if refresh_error:
        return SkillCommandStatus(
            "warning",
            f"Extension '{plan.skill_name}' removed, but registry refresh failed: {refresh_error}",
        )
    return SkillCommandStatus(
        "success",
        f"Extension '{plan.skill_name}' removed.",
    )


def uninstall_extension(
    name: str,
    *,
    omicsclaw_dir: str | Path,
    expected_type: str = "",
) -> list[SkillCommandStatus]:
    plan_or_status = prepare_extension_uninstall_plan(
        name,
        omicsclaw_dir=omicsclaw_dir,
        expected_type=expected_type,
    )
    if isinstance(plan_or_status, SkillCommandStatus):
        return [plan_or_status]
    plan = plan_or_status

    try:
        shutil.rmtree(plan.candidate)
    except Exception as exc:
        return [SkillCommandStatus("error", f"Failed to remove extension: {exc}")]
    return [finalize_uninstalled_skill(plan)]


def prepare_extension_enablement_plan(
    name: str,
    *,
    enable: bool,
    omicsclaw_dir: str | Path,
    expected_type: str = "",
) -> SkillEnablementPlan | SkillCommandStatus:
    extension_name = name.strip()
    if not extension_name:
        return SkillCommandStatus("error", build_extension_toggle_usage_text(enable=enable))

    matches = find_installed_extensions(
        omicsclaw_dir,
        extension_name,
        extension_type=expected_type,
    )
    if len(matches) > 1:
        names = ", ".join(f"{entry.extension_type}:{entry.path.name}" for entry in matches)
        return SkillCommandStatus(
            "error",
            f"Extension name '{extension_name}' is ambiguous. Matches: {names}",
        )
    if not matches:
        return SkillCommandStatus(
            "error",
            f"Installed extension '{extension_name}' not found.",
        )

    match = matches[0]
    state = load_extension_state(match.path)
    if state.enabled == enable:
        status = "enabled" if enable else "disabled"
        return SkillCommandStatus(
            "warning",
            f"Extension '{extension_name}' is already {status}.",
        )

    return SkillEnablementPlan(
        skill_name=match.record.extension_name if match.record is not None else match.path.name,
        candidate=match.path,
        enable=enable,
        extension_type=match.extension_type,
    )


def finalize_extension_enablement(plan: SkillEnablementPlan) -> SkillCommandStatus:
    set_extension_enabled(
        plan.candidate,
        enabled=plan.enable,
        disabled_reason="" if plan.enable else "disabled via interactive command",
    )
    refresh_error = ""
    if plan.extension_type == "skill-pack":
        refresh_error = refresh_skill_registry()

    action = "enabled" if plan.enable else "disabled"
    if refresh_error:
        return SkillCommandStatus(
            "warning",
            f"Extension '{plan.skill_name}' {action}, but registry refresh failed: {refresh_error}",
        )
    return SkillCommandStatus(
        "success",
        f"Extension '{plan.skill_name}' {action}.",
    )


def set_installed_extension_enabled(
    name: str,
    *,
    enable: bool,
    omicsclaw_dir: str | Path,
    expected_type: str = "",
) -> list[SkillCommandStatus]:
    plan_or_status = prepare_extension_enablement_plan(
        name,
        enable=enable,
        omicsclaw_dir=omicsclaw_dir,
        expected_type=expected_type,
    )
    if isinstance(plan_or_status, SkillCommandStatus):
        return [plan_or_status]
    return [finalize_extension_enablement(plan_or_status)]


def build_installed_extension_list_view(
    *,
    omicsclaw_dir: str | Path,
    extension_type: str = "",
) -> InstalledSkillListView:
    entries: list[InstalledSkillEntry] = []
    runtime_snapshot = build_extension_runtime_snapshot(omicsclaw_dir)
    activation_by_path = {
        str(record.path): record
        for record in runtime_snapshot.activation_records
    }
    inventory = list_installed_extensions(
        omicsclaw_dir,
        extension_types=(extension_type,) if extension_type else None,
    )
    for item in inventory:
        record = item.record
        activation_record = activation_by_path.get(str(item.path))
        active_surfaces, inactive_surfaces, runtime_entries = _build_runtime_surface_lists(
            activation_record
        )
        entries.append(
            InstalledSkillEntry(
                skill_name=(record.extension_name if record is not None else item.path.name),
                extension_type=item.extension_type,
                source_kind=record.source_kind if record is not None else "",
                source=record.source if record is not None else "",
                manifest_version=record.manifest_version if record is not None else "",
                installed_at=record.installed_at if record is not None else "",
                installed_label=format_relative_time(record.installed_at) if record and record.installed_at else "",
                tracked=record is not None,
                enabled=item.state.enabled,
                disabled_reason=item.state.disabled_reason,
                trusted_capabilities=list(record.trusted_capabilities) if record is not None else [],
                active_surfaces=active_surfaces,
                inactive_surfaces=inactive_surfaces,
                runtime_entries=runtime_entries,
                path=str(item.path),
            )
        )

    entries.sort(key=lambda entry: entry.skill_name.lower())
    entries.sort(key=lambda entry: entry.installed_at or "", reverse=True)
    entries.sort(key=lambda entry: 0 if entry.tracked else 1)

    empty_text = "No installed extensions found."
    hint_text = "Use /install-extension <src> or /install-skill <src> to add local or GitHub packs."
    if extension_type == "skill-pack":
        empty_text = "No user-installed skills found."
        hint_text = "Use /install-skill <src> to add a local or GitHub skill pack."

    return InstalledSkillListView(
        entries=entries,
        empty_text=empty_text,
        hint_text=hint_text,
    )


def build_installed_skill_list_view(
    *,
    omicsclaw_dir: str | Path,
) -> InstalledSkillListView:
    return build_installed_extension_list_view(
        omicsclaw_dir=omicsclaw_dir,
        extension_type="skill-pack",
    )


def format_installed_extension_list_plain(
    view: InstalledSkillListView,
    *,
    header: str = "Installed extensions:",
) -> str:
    if not view.entries:
        return view.empty_text

    lines = [header]
    for entry in view.entries:
        tag = "tracked" if entry.tracked else "legacy"
        state = "enabled" if entry.enabled else "disabled"
        details = [f"{tag}: {entry.skill_name}", entry.extension_type, state]
        if entry.manifest_version:
            details.append(f"v{entry.manifest_version}")
        if entry.source_kind:
            details.append(entry.source_kind)
        if entry.installed_label:
            details.append(entry.installed_label)
        lines.append("  " + " · ".join(details))
        if entry.disabled_reason:
            lines.append(f"    reason: {entry.disabled_reason}")
        if entry.active_surfaces:
            lines.append(f"    active surfaces: {', '.join(entry.active_surfaces)}")
        if entry.inactive_surfaces:
            lines.append(f"    inactive surfaces: {', '.join(entry.inactive_surfaces)}")
        if entry.runtime_entries:
            lines.append(f"    runtime entries: {'; '.join(entry.runtime_entries)}")
        if entry.trusted_capabilities:
            lines.append(f"    capabilities: {', '.join(entry.trusted_capabilities)}")
        if entry.source:
            lines.append(f"    source: {entry.source}")
        lines.append(f"    path: {entry.path}")

    if view.hint_text:
        lines.append("")
        lines.append(view.hint_text)
    return "\n".join(lines)


def format_installed_skill_list_plain(
    view: InstalledSkillListView,
    *,
    header: str = "Installed user skills:",
) -> str:
    return format_installed_extension_list_plain(view, header=header)


def _inventory_summary_text(view: InstalledSkillListView) -> str:
    counts: dict[str, int] = {}
    disabled = 0
    for entry in view.entries:
        counts[entry.extension_type] = counts.get(entry.extension_type, 0) + 1
        if not entry.enabled:
            disabled += 1
    pieces = [f"{extension_type}={count}" for extension_type, count in sorted(counts.items())]
    if disabled:
        pieces.append(f"disabled={disabled}")
    return ", ".join(pieces) if pieces else "no installed extensions"


def build_refresh_extensions_statuses(
    *,
    omicsclaw_dir: str | Path,
) -> list[SkillCommandStatus]:
    statuses: list[SkillCommandStatus] = []
    refresh_error = refresh_skill_registry()
    if refresh_error:
        statuses.append(
            SkillCommandStatus(
                "warning",
                f"Skill registry refresh failed: {refresh_error}",
            )
        )
    else:
        statuses.append(SkillCommandStatus("success", "Extension system refreshed."))

    view = build_installed_extension_list_view(omicsclaw_dir=omicsclaw_dir)
    runtime_snapshot = build_extension_runtime_snapshot(omicsclaw_dir)
    statuses.append(
        SkillCommandStatus(
            "info",
            f"Installed extension inventory: {_inventory_summary_text(view)}",
        )
    )
    statuses.append(
        SkillCommandStatus(
            "info",
            "Active extension runtime surfaces: "
            + format_extension_runtime_surface_summary(runtime_snapshot),
        )
    )
    if runtime_snapshot.prompt_packs:
        statuses.append(
            SkillCommandStatus(
                "info",
                "Active prompt packs: "
                + ", ".join(pack.name for pack in runtime_snapshot.prompt_packs),
            )
        )
    if runtime_snapshot.agent_packs:
        statuses.append(
            SkillCommandStatus(
                "info",
                "Active agent packs: "
                + ", ".join(pack.name for pack in runtime_snapshot.agent_packs),
            )
        )
    if runtime_snapshot.workflow_packs:
        statuses.append(
            SkillCommandStatus(
                "info",
                "Active workflow packs: "
                + ", ".join(pack.name for pack in runtime_snapshot.workflow_packs),
            )
        )
    if runtime_snapshot.hook_extensions:
        statuses.append(
            SkillCommandStatus(
                "info",
                "Active hook providers: "
                + ", ".join(item.name for item in runtime_snapshot.hook_extensions),
            )
        )
    for item in list_installed_extensions(omicsclaw_dir):
        validation = validate_extension_directory(
            item.path,
            source_kind=item.record.source_kind if item.record is not None else "local",
        )
        if not validation.valid:
            statuses.append(
                SkillCommandStatus(
                    "warning",
                    f"Installed extension '{item.path.name}' has validation issues: "
                    + "; ".join(validation.errors),
                )
            )
    return statuses


def build_refresh_skills_statuses(
    *,
    omicsclaw_dir: str | Path,
) -> list[SkillCommandStatus]:
    refresh_error = refresh_skill_registry()
    if refresh_error:
        return [
            SkillCommandStatus(
                "warning",
                f"Skill registry refresh failed: {refresh_error}",
            )
        ]

    view = build_installed_skill_list_view(omicsclaw_dir=omicsclaw_dir)
    statuses = [SkillCommandStatus("success", "Skill registry refreshed.")]
    if view.entries:
        statuses.append(
            SkillCommandStatus(
                "info",
                f"User-installed skill packs detected: {len(view.entries)}\n"
                "Use /installed-skills to inspect sources, capabilities, and install records.",
            )
        )
    else:
        statuses.append(
            SkillCommandStatus(
                "info",
                "No user-installed skill packs detected under skills/user.",
            )
        )
    return statuses


def refresh_skill_registry() -> str:
    try:
        from omicsclaw.core.registry import registry

        registry._loaded = False
        registry.skills.clear()
        registry.lazy_skills.clear()
        registry.load_all()
        return ""
    except Exception as exc:
        return str(exc)


__all__ = [
    "InstalledSkillEntry",
    "InstalledSkillListView",
    "SkillCommandStatus",
    "SkillEnablementPlan",
    "SkillInstallPlan",
    "SkillRemovalPlan",
    "build_extension_install_usage_text",
    "build_extension_toggle_usage_text",
    "build_installed_extension_list_view",
    "build_installed_skill_list_view",
    "build_refresh_extensions_statuses",
    "build_refresh_skills_statuses",
    "build_skill_install_clone_status",
    "build_skill_install_copy_status",
    "build_skill_install_start_status",
    "build_skill_install_usage_text",
    "finalize_extension_enablement",
    "finalize_installed_skill",
    "finalize_uninstalled_skill",
    "format_installed_extension_list_plain",
    "format_installed_skill_list_plain",
    "install_extension_from_source",
    "install_skill_from_source",
    "prepare_extension_enablement_plan",
    "prepare_extension_install_plan",
    "prepare_extension_uninstall_plan",
    "prepare_skill_install_plan",
    "prepare_skill_uninstall_plan",
    "refresh_skill_registry",
    "set_installed_extension_enabled",
    "uninstall_extension",
]
