from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from omicsclaw.core.registry import OmicsRegistry
from omicsclaw.core.skill_runner import resolve_skill_alias


ROOT = Path(__file__).resolve().parent.parent


def _frontmatter(skill_md: Path) -> dict[str, Any]:
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    return yaml.safe_load(text.split("---", 2)[1]) or {}


def test_discovered_skill_legacy_aliases_are_owned_by_skill_md():
    registry = OmicsRegistry()
    registry.load_all()

    mismatches: list[str] = []
    for alias, info in registry.iter_primary_skills():
        script_path = Path(info["script"])
        skill_md = script_path.parent / "SKILL.md"
        if not skill_md.exists():
            continue

        data = _frontmatter(skill_md)
        omics = data.get("metadata", {}).get("omicsclaw", {}) if isinstance(data, dict) else {}
        expected_aliases = list(omics.get("legacy_aliases", []) or [])
        actual_aliases = list(info.get("legacy_aliases", []) or [])
        if actual_aliases != expected_aliases:
            mismatches.append(
                f"{alias}: registry legacy_aliases={actual_aliases!r}, "
                f"SKILL.md legacy_aliases={expected_aliases!r}"
            )

    assert not mismatches, "\n".join(mismatches[:80])


def test_declared_legacy_aliases_still_resolve_to_canonical_skill_names():
    assert resolve_skill_alias("preprocess") == "spatial-preprocess"
    assert resolve_skill_alias("domains") == "spatial-domains"
    assert resolve_skill_alias("sc-preprocess") == "sc-preprocessing"
