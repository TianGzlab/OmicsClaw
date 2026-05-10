#!/usr/bin/env python3
"""Render `references/parameters.md` from a v2 skill's `parameters.yaml`.

The generated markdown is the human-readable view of the runtime contract:
the SKILL.md frontmatter no longer carries this material in v2 skills, so
this file is what an LLM (or human) reads to understand which CLI flags the
skill accepts and which per-method parameter hints exist.

Usage:
    python scripts/generate_parameters_md.py <skill_dir>          # write
    python scripts/generate_parameters_md.py --all                # all v2 skills
    python scripts/generate_parameters_md.py <skill_dir> --check  # CI: diff-only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from omicsclaw.core.registry import SKILLS_DIR  # noqa: E402

AUTOGEN_HEADER = (
    "<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->\n"
    "<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->\n\n"
)


def render_parameters_md(sidecar: dict) -> str:
    """Render a parameters.yaml dict to the canonical markdown layout.

    Empty / missing fields render as informative one-liners so a reader
    always knows whether the absence is intentional.
    """
    lines: list[str] = [AUTOGEN_HEADER, "# Parameters\n"]

    flags = sidecar.get("allowed_extra_flags", []) or []
    lines.append("## Allowed extra CLI flags\n")
    if flags:
        for flag in flags:
            lines.append(f"- `{flag}`")
    else:
        lines.append("_No extra flags beyond the standard `--input` / `--output` / `--demo` set._")
    lines.append("")

    lines.append("## Per-method parameter hints\n")
    hints: dict = sidecar.get("param_hints", {}) or {}
    if not hints:
        lines.append("_No method-specific tuning hints._\n")
        return "\n".join(lines).rstrip() + "\n"

    for method in sorted(hints):
        info = hints[method] or {}
        lines.append(f"### `{method}`\n")

        priority = info.get("priority")
        if priority:
            lines.append(f"**Tuning priority:** {priority}\n")

        for label, key in (("Core parameters", "params"), ("Advanced parameters", "advanced_params")):
            params = info.get(key) or []
            if params:
                lines.append(f"**{label}:**")
                lines.append("")
                lines.append("| name | default |")
                lines.append("|---|---|")
                defaults = info.get("defaults", {}) or {}
                for p in params:
                    dval = defaults.get(p, "—")
                    lines.append(f"| `{p}` | `{dval}` |")
                lines.append("")

        requires = info.get("requires") or []
        if requires:
            lines.append("**Requires:**")
            for r in requires:
                lines.append(f"- `{r}`")
            lines.append("")

        tips = info.get("tips") or []
        if tips:
            lines.append("**Tips:**")
            for t in tips:
                lines.append(f"- {t}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_for_skill(skill_dir: Path) -> str | None:
    """Return the rendered markdown for `skill_dir`, or None if no sidecar."""
    sidecar_path = skill_dir / "parameters.yaml"
    if not sidecar_path.exists():
        return None
    sidecar = yaml.safe_load(sidecar_path.read_text(encoding="utf-8")) or {}
    return render_parameters_md(sidecar)


def write_or_check(skill_dir: Path, *, check: bool) -> int:
    """Write `references/parameters.md` for `skill_dir`, or compare in --check.

    Returns shell exit code.
    """
    rendered = render_for_skill(skill_dir)
    if rendered is None:
        print(f"skip: {skill_dir} has no parameters.yaml")
        return 0

    target_dir = skill_dir / "references"
    target_dir.mkdir(exist_ok=True)
    target = target_dir / "parameters.md"

    if check:
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
        if existing != rendered:
            print(f"FAIL {skill_dir}: parameters.md is stale")
            return 1
        print(f"ok   {skill_dir}")
        return 0

    target.write_text(rendered, encoding="utf-8")
    print(f"wrote {target.relative_to(_ROOT)}")
    return 0


def discover_v2_skills(skills_root: Path) -> list[Path]:
    """Return every directory under `skills_root` that has a parameters.yaml."""
    return sorted(p.parent for p in skills_root.rglob("parameters.yaml"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("skill_dir", nargs="?", type=Path, help="Skill directory")
    parser.add_argument("--all", action="store_true", help="Process every v2 skill under skills/")
    parser.add_argument("--check", action="store_true", help="Diff-only mode for CI")
    args = parser.parse_args()

    if args.all == bool(args.skill_dir):
        parser.error("provide either <skill_dir> or --all (not both, not neither)")

    targets = discover_v2_skills(SKILLS_DIR) if args.all else [args.skill_dir]

    failures = 0
    for skill_dir in targets:
        failures += write_or_check(skill_dir, check=args.check)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
