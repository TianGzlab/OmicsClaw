#!/usr/bin/env python3
"""Auto-generate the Skill Routing Table section of CLAUDE.md.

Reads skill metadata from the Registry + SKILL.md frontmatter and generates
markdown tables grouped by domain.  Replaces the content between
``<!-- ROUTING-TABLE-START -->`` and ``<!-- ROUTING-TABLE-END -->`` markers.

Usage:
    python scripts/generate_routing_table.py              # preview to stdout
    python scripts/generate_routing_table.py --apply      # write to CLAUDE.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from omicsclaw.core.registry import OmicsRegistry, SKILLS_DIR, _HARDCODED_DOMAINS

START_MARKER = "<!-- ROUTING-TABLE-START -->"
END_MARKER = "<!-- ROUTING-TABLE-END -->"

CLAUDE_MD = _ROOT / "CLAUDE.md"

# Domain display order and human-readable names
DOMAIN_ORDER = [
    ("spatial", "Spatial Transcriptomics"),
    ("singlecell", "Single-Cell Omics"),
    ("genomics", "Genomics"),
    ("proteomics", "Proteomics"),
    ("metabolomics", "Metabolomics"),
    ("bulkrna", "Bulk RNA-seq"),
    ("orchestrator", "Orchestration"),
]


def _skill_path_display(script_path: Path) -> str:
    """Convert a script path to a display path like ``skills/spatial/spatial-preprocess/``."""
    try:
        rel = script_path.parent.relative_to(SKILLS_DIR)
        return f"skills/{rel}/"
    except ValueError:
        return f"skills/{script_path.parent.name}/"


def _build_user_intent(lazy_meta, description: str) -> str:
    """Build the User Intent column from trigger_keywords or description."""
    if lazy_meta and lazy_meta.trigger_keywords:
        kws = lazy_meta.trigger_keywords
        # Limit to 8 keywords for readability
        if len(kws) > 8:
            kws = kws[:8]
        return ", ".join(kws)
    # Fallback: use description
    return description


def generate_tables() -> str:
    """Generate the full routing table markdown from Registry metadata."""
    reg = OmicsRegistry()
    reg.load_all()
    reg.load_lightweight()

    lines: list[str] = []

    for domain_key, domain_display in DOMAIN_ORDER:
        # Collect skills for this domain
        domain_skills: list[tuple[str, dict]] = []
        for alias, info in reg.skills.items():
            if info.get("domain") != domain_key:
                continue
            # Skip legacy alias duplicates (same dict object)
            if info.get("alias") != alias:
                continue
            domain_skills.append((alias, info))

        if not domain_skills:
            continue

        count = len(domain_skills)
        lines.append(f"### {domain_display} ({count} skills)")
        lines.append("")
        lines.append("| User Intent | Skill | Action |")
        lines.append("|---|---|---|")

        for alias, info in domain_skills:
            script = info.get("script")
            if not script:
                continue

            # Build skill path display
            skill_path = _skill_path_display(Path(script))

            # Build user intent from SKILL.md trigger_keywords
            dir_name = Path(script).parent.name
            lazy = reg.lazy_skills.get(dir_name)
            intent = _build_user_intent(lazy, info.get("description", alias))

            # Build action
            action = f"Run `python omicsclaw.py run {alias}`"

            lines.append(f"| {intent} | `{skill_path}` | {action} |")

        lines.append("")

    return "\n".join(lines)


def apply_to_claude_md(table_content: str) -> bool:
    """Replace the routing table section in CLAUDE.md between markers."""
    if not CLAUDE_MD.exists():
        print(f"ERROR: {CLAUDE_MD} not found", file=sys.stderr)
        return False

    content = CLAUDE_MD.read_text(encoding="utf-8")

    start_idx = content.find(START_MARKER)
    end_idx = content.find(END_MARKER)

    if start_idx == -1 or end_idx == -1:
        print(f"ERROR: Markers not found in {CLAUDE_MD}", file=sys.stderr)
        print(f"  Expected: {START_MARKER} ... {END_MARKER}")
        return False

    # Replace between markers (keep markers themselves)
    new_content = (
        content[: start_idx + len(START_MARKER)]
        + "\n\n"
        + table_content
        + content[end_idx:]
    )

    CLAUDE_MD.write_text(new_content, encoding="utf-8")
    return True


def main():
    parser = argparse.ArgumentParser(description="Generate CLAUDE.md routing table")
    parser.add_argument("--apply", action="store_true", help="Write to CLAUDE.md (default: preview)")
    args = parser.parse_args()

    table = generate_tables()

    if args.apply:
        if apply_to_claude_md(table):
            print(f"Updated {CLAUDE_MD}")
            # Count rows
            row_count = sum(1 for line in table.splitlines() if line.startswith("|") and "User Intent" not in line and "---" not in line)
            print(f"  {row_count} skill rows across {len(DOMAIN_ORDER)} domains")
        else:
            sys.exit(1)
    else:
        print(table)


if __name__ == "__main__":
    main()
