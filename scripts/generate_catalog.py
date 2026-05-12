#!/usr/bin/env python3
"""Generate skills/catalog.json from SKILL.md YAML frontmatter."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

OMICSCLAW_DIR = Path(__file__).resolve().parent.parent
SKILLS_DIR = OMICSCLAW_DIR / "skills"


def parse_yaml_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter from a SKILL.md file via ``yaml.safe_load``.

    Uses the same parser as ``omicsclaw.core.lazy_metadata`` so the catalog
    cannot diverge from the runtime registry on nested structures, folded
    scalars, or list/dict shapes.
    """
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        loaded = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def build_cli_alias_map() -> dict[str, str]:
    """Build {absolute_skill_dir_path: canonical_cli_alias} from the Omics registry."""
    if str(OMICSCLAW_DIR) not in sys.path:
        sys.path.insert(0, str(OMICSCLAW_DIR))
    from omicsclaw.core.registry import registry

    registry.load_all()
    alias_map: dict[str, str] = {}
    for _alias, info in registry.skills.items():
        script = info.get("script")
        if isinstance(script, Path):
            canonical = info.get("canonical_name") or info.get("alias") or _alias
            alias_map[str(script.parent.resolve())] = str(canonical)
    return alias_map


def generate_catalog() -> dict:
    """Scan skills/ and build the catalog."""
    alias_map = build_cli_alias_map()
    skills = []
    for skill_md in sorted(SKILLS_DIR.rglob("SKILL.md")):
        skill_dir = skill_md.parent
        # Use the path RELATIVE to SKILLS_DIR for the hidden/dunder filter,
        # otherwise a worktree checked out at `.worktrees/<branch>` triggers
        # the `.startswith(".")` rule on its own parent directory and the
        # generator silently emits an empty catalog.
        rel_parts = skill_dir.relative_to(SKILLS_DIR).parts
        if any(part.startswith((".", "__")) for part in rel_parts):
            continue

        fm = parse_yaml_frontmatter(skill_md.read_text())
        name = fm.get("name", skill_dir.name)

        has_script = any(skill_dir.glob("*.py"))
        has_tests = (skill_dir / "tests").exists() and any((skill_dir / "tests").glob("test_*.py"))
        has_demo = has_script

        trigger_kw = []
        metadata = fm.get("metadata", {})
        if isinstance(metadata, dict):
            sc_meta = metadata.get("omicsclaw", {}) or metadata.get("spatialclaw", {})
            if isinstance(sc_meta, dict):
                trigger_kw = sc_meta.get("trigger_keywords", [])
        if isinstance(trigger_kw, str):
            trigger_kw = [trigger_kw]

        cli_alias = alias_map.get(str(skill_dir.resolve()))
        entry = {
            "name": name,
            "cli_alias": cli_alias,
            "description": fm.get("description", ""),
            "version": fm.get("version", "0.1.0"),
            "status": "mvp" if has_script else "planned",
            "has_script": has_script,
            "has_tests": has_tests,
            "has_demo": has_demo,
            "demo_command": (
                f"python omicsclaw.py run {cli_alias or skill_dir.name} --demo"
                if has_demo else None
            ),
            "tags": fm.get("tags", []),
            "trigger_keywords": trigger_kw if isinstance(trigger_kw, list) else [],
        }
        skills.append(entry)

    catalog = {
        "version": "1.0.0",
        "generated_by": "scripts/generate_catalog.py",
        "skill_count": len(skills),
        "skills": skills,
    }
    return catalog


def main():
    parser = argparse.ArgumentParser(description="Generate skills/catalog.json from SKILL.md frontmatter")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="Write catalog.json (default behavior)")
    group.add_argument("--check", action="store_true", help="Exit 1 if catalog.json is out of date")
    args = parser.parse_args()

    catalog = generate_catalog()
    out_path = SKILLS_DIR / "catalog.json"
    expected = json.dumps(catalog, indent=2)

    if args.check:
        current = out_path.read_text() if out_path.exists() else ""
        if current.rstrip() != expected.rstrip():
            print(
                "ERROR: skills/catalog.json is out of date.\n"
                "       Run: python scripts/generate_catalog.py --apply",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"skills/catalog.json is up to date ({catalog['skill_count']} skills).")
        return

    out_path.write_text(expected)
    print(f"Generated {out_path} with {catalog['skill_count']} skills")


if __name__ == "__main__":
    main()
