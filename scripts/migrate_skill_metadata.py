#!/usr/bin/env python3
"""One-time migration: populate SKILL.md frontmatter with fields from _HARDCODED_SKILLS.

Reads allowed_extra_flags, legacy_aliases, saves_h5ad, requires_preprocessed
from registry.py and inserts them into each SKILL.md's metadata.omicsclaw block.

Usage:
    python scripts/migrate_skill_metadata.py          # dry-run (default)
    python scripts/migrate_skill_metadata.py --apply   # write changes
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from omicsclaw.core.registry import _HARDCODED_SKILLS, SKILLS_DIR


def _find_skill_md(skill_info: dict) -> Path | None:
    """Locate the SKILL.md for a hardcoded skill entry."""
    script = skill_info.get("script")
    if script and Path(script).parent.is_dir():
        md = Path(script).parent / "SKILL.md"
        if md.exists():
            return md
    return None


def _build_yaml_lines(skill_info: dict) -> list[str]:
    """Build the YAML lines to insert into metadata.omicsclaw block."""
    lines = []

    # allowed_extra_flags
    flags = skill_info.get("allowed_extra_flags", set())
    if flags:
        sorted_flags = sorted(flags)
        lines.append("    allowed_extra_flags:")
        for f in sorted_flags:
            lines.append(f"      - \"{f}\"")
    else:
        lines.append("    allowed_extra_flags: []")

    # legacy_aliases
    aliases = skill_info.get("legacy_aliases", [])
    if aliases:
        items = ", ".join(aliases)
        lines.append(f"    legacy_aliases: [{items}]")

    # saves_h5ad
    saves = skill_info.get("saves_h5ad", False)
    lines.append(f"    saves_h5ad: {'true' if saves else 'false'}")

    # requires_preprocessed
    req = skill_info.get("requires_preprocessed", False)
    if req:
        lines.append(f"    requires_preprocessed: true")

    return lines


def _has_field(content: str, field: str) -> bool:
    """Check if a field already exists in the YAML frontmatter."""
    return bool(re.search(rf"^\s+{field}\s*:", content, re.MULTILINE))


def migrate_skill(alias: str, skill_info: dict, apply: bool) -> str:
    """Migrate one skill. Returns status message."""
    md_path = _find_skill_md(skill_info)
    if not md_path:
        return f"  SKIP {alias}: no SKILL.md found"

    content = md_path.read_text(encoding="utf-8")

    # Check if frontmatter exists
    if not content.startswith("---"):
        return f"  SKIP {alias}: no YAML frontmatter"

    # Check if allowed_extra_flags already present (already migrated)
    if _has_field(content, "allowed_extra_flags"):
        return f"  SKIP {alias}: already has allowed_extra_flags"

    # Find the insertion point: after trigger_keywords block or after domain line
    # We look for the last line of metadata.omicsclaw section before the closing ---
    parts = content.split("---", 2)
    if len(parts) < 3:
        return f"  SKIP {alias}: malformed frontmatter"

    fm_lines = parts[1].split("\n")
    insert_idx = None

    # Find the best insertion point inside metadata.omicsclaw
    in_omicsclaw = False
    in_trigger_keywords = False
    for i, line in enumerate(fm_lines):
        stripped = line.strip()
        if "omicsclaw:" in line:
            in_omicsclaw = True
        if in_omicsclaw and "trigger_keywords:" in line:
            in_trigger_keywords = True
            if stripped.startswith("trigger_keywords:") and "[" in stripped:
                # Inline list: insert after this line
                insert_idx = i + 1
                in_trigger_keywords = False
                continue
        if in_trigger_keywords:
            if stripped.startswith("- "):
                insert_idx = i + 1  # Keep updating to last keyword line
            else:
                # Exited trigger_keywords block
                in_trigger_keywords = False
                if insert_idx is None:
                    insert_idx = i
        if in_omicsclaw and not in_trigger_keywords and stripped and not stripped.startswith("-"):
            # Track last meaningful line in omicsclaw block
            if "domain:" in line or "trigger_keywords:" in line:
                if insert_idx is None:
                    insert_idx = i + 1

    if insert_idx is None:
        # Fallback: insert before the last non-empty line of frontmatter
        for i in range(len(fm_lines) - 1, -1, -1):
            if fm_lines[i].strip():
                insert_idx = i + 1
                break
        if insert_idx is None:
            return f"  SKIP {alias}: cannot find insertion point"

    new_lines = _build_yaml_lines(skill_info)
    for j, new_line in enumerate(new_lines):
        fm_lines.insert(insert_idx + j, new_line)

    new_frontmatter = "\n".join(fm_lines)
    new_content = f"---{new_frontmatter}---{parts[2]}"

    if apply:
        md_path.write_text(new_content, encoding="utf-8")
        return f"  OK   {alias}: wrote {len(new_lines)} lines to {md_path.name}"
    else:
        return f"  DRY  {alias}: would write {len(new_lines)} lines to {md_path.name}"


def main():
    parser = argparse.ArgumentParser(description="Migrate hardcoded skill metadata to SKILL.md")
    parser.add_argument("--apply", action="store_true", help="Actually write changes (default: dry-run)")
    args = parser.parse_args()

    print(f"Migration mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    print(f"Skills to process: {len(_HARDCODED_SKILLS)}\n")

    stats = {"ok": 0, "skip": 0}
    for alias, info in sorted(_HARDCODED_SKILLS.items()):
        msg = migrate_skill(alias, info, args.apply)
        print(msg)
        if "OK" in msg or "DRY" in msg:
            stats["ok"] += 1
        else:
            stats["skip"] += 1

    print(f"\nDone: {stats['ok']} migrated, {stats['skip']} skipped")


if __name__ == "__main__":
    main()
