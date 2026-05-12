from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from omicsclaw.core.registry import OmicsRegistry


ROOT = Path(__file__).resolve().parent.parent


def _frontmatter(skill_md: Path) -> dict[str, Any]:
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}


def _runtime_contract(skill_dir: Path) -> dict[str, Any]:
    """Return the runtime metadata block, regardless of whether the skill
    is in legacy (frontmatter `metadata.omicsclaw`) or v2 (sidecar
    `parameters.yaml`) form.  Mirrors the priority used by
    omicsclaw.core.lazy_metadata."""
    sidecar = skill_dir / "parameters.yaml"
    if sidecar.exists():
        return yaml.safe_load(sidecar.read_text(encoding="utf-8")) or {}
    fm = _frontmatter(skill_dir / "SKILL.md")
    return (fm.get("metadata", {}) or {}).get("omicsclaw", {}) or {}


def test_all_primary_skills_have_standard_omicsclaw_frontmatter():
    registry = OmicsRegistry()
    registry.load_all()

    failures: list[str] = []
    seen_skill_docs: set[Path] = set()
    for alias, info in registry.iter_primary_skills():
        script_path = Path(info["script"])
        skill_md = script_path.parent / "SKILL.md"
        seen_skill_docs.add(skill_md)
        data = _frontmatter(skill_md)
        omics = _runtime_contract(skill_md.parent)

        expected = {
            "name": (data.get("name"), alias, str),
            "domain": (omics.get("domain"), info.get("domain"), str),
            "script": (omics.get("script"), script_path.name, str),
            "allowed_extra_flags": (omics.get("allowed_extra_flags"), None, list),
            "param_hints": (omics.get("param_hints"), None, dict),
            "saves_h5ad": (omics.get("saves_h5ad"), None, bool),
            "requires_preprocessed": (
                omics.get("requires_preprocessed"),
                None,
                bool,
            ),
        }

        for field, (actual, exact, expected_type) in expected.items():
            if actual is None:
                failures.append(f"{skill_md.relative_to(ROOT)}: missing {field}")
                continue
            if not isinstance(actual, expected_type):
                failures.append(
                    f"{skill_md.relative_to(ROOT)}: {field} has type "
                    f"{type(actual).__name__}, expected {expected_type.__name__}"
                )
                continue
            if exact is not None and actual != exact:
                failures.append(
                    f"{skill_md.relative_to(ROOT)}: {field}={actual!r}, expected {exact!r}"
                )

    all_skill_docs = {
        p for p in (ROOT / "skills").rglob("SKILL.md")
        # _template / _lib / similar underscore-prefixed dirs are scaffolds, not
        # registered skills.
        if not any(part.startswith("_") for part in p.relative_to(ROOT / "skills").parts[:-1])
        and not p.parent.name.startswith("_")
    }
    unregistered = sorted(all_skill_docs - seen_skill_docs)
    for skill_md in unregistered:
        failures.append(f"{skill_md.relative_to(ROOT)}: SKILL.md is not a primary registered skill")

    assert not failures, "\n".join(failures[:120])
