#!/usr/bin/env python3
"""Generate skills/catalog.json from SKILL.md YAML frontmatter."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

OMICSCLAW_DIR = Path(__file__).resolve().parent.parent
SKILLS_DIR = OMICSCLAW_DIR / "skills"


def parse_yaml_frontmatter(text: str) -> dict:
    """Extract YAML frontmatter from a SKILL.md file (simple parser, supports >- blocks)."""
    if not text.startswith("---"):
        return {}
    end = text.index("---", 3)
    yaml_block = text[3:end].strip()

    result: dict = {}
    lines = yaml_block.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if ":" in stripped and not stripped.startswith("-") and not stripped.startswith("#"):
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if value in (">-", ">", "|", "|-"):
                # Collect following indented lines as a folded scalar
                folded_parts = []
                i += 1
                while i < len(lines) and (lines[i].startswith("  ") or lines[i].strip() == ""):
                    folded_parts.append(lines[i].strip())
                    i += 1
                result[key] = " ".join(p for p in folded_parts if p)
                continue
            elif value.startswith("[") and value.endswith("]"):
                value = [v.strip().strip('"').strip("'") for v in value[1:-1].split(",") if v.strip()]
            elif value == "":
                # YAML list syntax — `key:` followed by `- item` indented lines.
                # Peek the next non-empty line: if it starts with `- ` it's a
                # block sequence; collect until we hit a top-level key or EOF.
                items: list[str] = []
                j = i + 1
                while j < len(lines):
                    next_line = lines[j]
                    next_stripped = next_line.strip()
                    if not next_stripped:
                        j += 1
                        continue
                    if next_line.startswith("- "):
                        items.append(next_line[2:].strip().strip('"').strip("'"))
                        j += 1
                        continue
                    break  # top-level key or other non-sequence line
                if items:
                    result[key] = items
                    i = j
                    continue
                # `value == ""` with no list items below: leave as empty string.
            result[key] = value
        i += 1
    return result


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
