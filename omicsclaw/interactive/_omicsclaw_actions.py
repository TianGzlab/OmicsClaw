"""Shared OmicsClaw command actions for interactive surfaces."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._skill_run_support import SkillRunCommandArgs

_OMICSCLAW_DIR = Path(__file__).resolve().parent.parent.parent


@dataclass(slots=True)
class SkillsCatalogEntry:
    alias: str
    description: str = ""
    available: bool = False


@dataclass(slots=True)
class SkillsCatalogSection:
    key: str
    title: str
    data_types: list[str] = field(default_factory=list)
    skills: list[SkillsCatalogEntry] = field(default_factory=list)


@dataclass(slots=True)
class SkillsCatalogView:
    total_skills: int
    filter_value: str = ""
    sections: list[SkillsCatalogSection] = field(default_factory=list)


def load_omicsclaw_script():
    """Load the root-level ``omicsclaw.py`` script via importlib."""
    script_path = _OMICSCLAW_DIR / "omicsclaw.py"
    spec = importlib.util.spec_from_file_location("_omicsclaw_script", script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load omicsclaw.py from: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _resolve_domain_filter(
    domains: dict[str, dict[str, Any]],
    domain_filter: str | None,
) -> str | None:
    if not domain_filter:
        return None

    raw = domain_filter.strip()
    if not raw:
        return None

    lowered = raw.lower()
    for key, info in domains.items():
        if lowered == key.lower():
            return key
        name = str(info.get("name", "")).strip().lower()
        if name and lowered == name:
            return key

    partial_matches = [
        key
        for key, info in domains.items()
        if lowered in key.lower() or lowered in str(info.get("name", "")).lower()
    ]
    if len(partial_matches) == 1:
        return partial_matches[0]
    return raw


def build_skills_catalog_view(domain_filter: str | None = None) -> SkillsCatalogView:
    omicsclaw_script = load_omicsclaw_script()
    skills = getattr(omicsclaw_script, "SKILLS")
    domains = getattr(omicsclaw_script, "DOMAINS")
    workflow_order = getattr(omicsclaw_script, "_WORKFLOW_ORDER", {})

    resolved_filter = _resolve_domain_filter(domains, domain_filter)
    total_skills = sum(1 for alias, info in skills.items() if alias == info.get("alias", alias))

    domain_skills: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for alias, info in skills.items():
        if alias != info.get("alias", alias):
            continue
        domain_key = str(info.get("domain", "other"))
        domain_skills.setdefault(domain_key, []).append((alias, info))

    sections: list[SkillsCatalogSection] = []
    for domain_key, domain_info in domains.items():
        if resolved_filter and domain_key != resolved_filter:
            continue
        skills_in_domain = list(domain_skills.get(domain_key, []))
        if not skills_in_domain:
            continue

        order = workflow_order.get(domain_key, [])
        order_index = {name: index for index, name in enumerate(order)}
        skills_in_domain.sort(
            key=lambda pair: (order_index.get(pair[0], len(order)), pair[0])
        )
        sections.append(
            SkillsCatalogSection(
                key=domain_key,
                title=str(domain_info.get("name", domain_key.title())),
                data_types=[str(item) for item in domain_info.get("primary_data_types", [])],
                skills=[
                    SkillsCatalogEntry(
                        alias=alias,
                        description=str(info.get("description", "")),
                        available=bool(info.get("script") and info["script"].exists()),
                    )
                    for alias, info in skills_in_domain
                ],
            )
        )

    known_domains = set(domains.keys())
    extra_skills = [
        (alias, info)
        for alias, info in domain_skills.items()
        if alias not in known_domains
    ]
    if not resolved_filter and extra_skills:
        other_entries: list[SkillsCatalogEntry] = []
        for _, values in extra_skills:
            for alias, info in sorted(values, key=lambda pair: pair[0]):
                other_entries.append(
                    SkillsCatalogEntry(
                        alias=alias,
                        description=str(info.get("description", "")),
                        available=bool(info.get("script") and info["script"].exists()),
                    )
                )
        sections.append(
            SkillsCatalogSection(
                key="other",
                title="Other (Dynamically Discovered)",
                skills=other_entries,
            )
        )

    return SkillsCatalogView(
        total_skills=total_skills,
        filter_value=domain_filter.strip() if domain_filter else "",
        sections=sections,
    )


def format_skills_catalog_plain(view: SkillsCatalogView) -> str:
    lines = [f"OmicsClaw Skills ({view.total_skills} total)", "=" * 40]
    if view.filter_value:
        lines.extend([f"Filter: {view.filter_value}", ""])
    else:
        lines.append("")

    if not view.sections:
        if view.filter_value:
            lines.append(f"No skills found for domain: {view.filter_value}")
        else:
            lines.append("No skills available.")
        return "\n".join(lines)

    for section in view.sections:
        types_str = ", ".join(
            f".{item}" if item and item != "*" else "*"
            for item in section.data_types
        ) or "-"
        lines.append(
            f"[{section.title}] ({len(section.skills)} skills, {types_str})"
        )
        lines.append("~" * 40)
        for skill in section.skills:
            tag = "[OK]" if skill.available else "[--]"
            lines.append(f"  {tag} {skill.alias}")
            if skill.description:
                lines.append(f"       {skill.description}")
        lines.append("")

    lines.append("[OK] = ready  [--] = planned")
    return "\n".join(lines)


def list_skills_text(domain_filter: str | None = None) -> str:
    return format_skills_catalog_plain(build_skills_catalog_view(domain_filter))


def list_registered_skill_names() -> list[str]:
    from omicsclaw.core.registry import registry

    if not getattr(registry, "_loaded", False):
        registry.load_all()
    return sorted(str(name) for name in registry.skills.keys())


def run_skill_command(command: SkillRunCommandArgs) -> dict[str, Any]:
    from omicsclaw.core.skill_runner import run_skill

    return run_skill(
        command.skill,
        input_path=command.input_path,
        output_dir=command.output_dir,
        demo=command.demo,
        extra_args=command.extra_args,
    )
