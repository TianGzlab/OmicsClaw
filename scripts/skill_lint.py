#!/usr/bin/env python3
"""Lint OmicsClaw v2 skills against the canonical template.

A skill is "v2" iff it has a `parameters.yaml` sidecar.  Lint rules apply only
to v2 skills; legacy skills (frontmatter-only) lint clean by default so the
89-skill migration can proceed one PR at a time without breaking CI.

Usage:
    python scripts/skill_lint.py <skill_dir>          # one skill
    python scripts/skill_lint.py --all                # every skill under skills/
    python scripts/skill_lint.py --all --strict       # treat warnings as errors
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

from generate_parameters_md import render_parameters_md  # noqa: E402

REQUIRED_SECTIONS = (
    "## When to use",
    "## Inputs & Outputs",
    "## Flow",
    "## Gotchas",
    "## Key CLI",
    "## See also",
)

REQUIRED_REFERENCES = ("methodology.md", "output_contract.md", "parameters.md")

ALLOWED_FRONTMATTER_KEYS = {
    "name", "description", "version", "author", "license", "tags", "requires",
}

REQUIRED_SIDECAR_KEYS = {
    "domain", "script", "saves_h5ad", "requires_preprocessed",
    "trigger_keywords", "legacy_aliases", "allowed_extra_flags", "param_hints",
}

MAX_BODY_LINES = 200
MAX_DESCRIPTION_WORDS = 50


def _parse_skill_md(skill_dir: Path) -> tuple[dict, str] | None:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        frontmatter = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return None
    body = parts[2].lstrip("\n")
    return frontmatter, body


def _check_description(description: str) -> list[str]:
    errors: list[str] = []
    desc = (description or "").strip()
    if not desc.lower().startswith("load when"):
        errors.append("description: must start with 'Load when'")
    if len(desc.split()) > MAX_DESCRIPTION_WORDS:
        errors.append(
            f"description: must be <= {MAX_DESCRIPTION_WORDS} words "
            f"(found {len(desc.split())})"
        )
    return errors


def _check_body(body: str) -> list[str]:
    errors: list[str] = []
    line_count = body.count("\n") + 1
    if line_count > MAX_BODY_LINES:
        errors.append(
            f"body: exceeds {MAX_BODY_LINES} lines (found {line_count})"
        )
    for section in REQUIRED_SECTIONS:
        if section not in body:
            errors.append(f"body: missing required section '{section}'")
    return errors


def _check_frontmatter_keys(frontmatter: dict) -> list[str]:
    errors: list[str] = []
    extra = set(frontmatter) - ALLOWED_FRONTMATTER_KEYS
    if "metadata" in extra:
        meta = frontmatter.get("metadata") or {}
        if isinstance(meta, dict) and "omicsclaw" in meta:
            errors.append(
                "frontmatter: legacy 'metadata.omicsclaw' block must be removed "
                "from v2 skills (move runtime fields to parameters.yaml)"
            )
        extra.discard("metadata")
    if extra:
        errors.append(
            f"frontmatter: unexpected keys {sorted(extra)} "
            f"(allowed: {sorted(ALLOWED_FRONTMATTER_KEYS)})"
        )
    return errors


def _check_sidecar(sidecar: dict) -> list[str]:
    errors: list[str] = []
    missing = REQUIRED_SIDECAR_KEYS - set(sidecar)
    for key in sorted(missing):
        errors.append(f"parameters.yaml: missing required field '{key}'")
    flags = sidecar.get("allowed_extra_flags", []) or []
    for flag in flags:
        if not isinstance(flag, str) or not flag.startswith("--"):
            errors.append(
                f"parameters.yaml: allowed_extra_flags entry {flag!r} "
                f"must be a string starting with '--'"
            )
    if "param_hints" in sidecar and not isinstance(sidecar["param_hints"], dict):
        errors.append("parameters.yaml: param_hints must be a dict")
    return errors


def _check_references(skill_dir: Path, sidecar: dict) -> list[str]:
    errors: list[str] = []
    refs = skill_dir / "references"
    for name in REQUIRED_REFERENCES:
        if not (refs / name).exists():
            errors.append(f"references/{name}: missing")
    params_md = refs / "parameters.md"
    if params_md.exists():
        expected = render_parameters_md(sidecar)
        if params_md.read_text(encoding="utf-8") != expected:
            errors.append(
                "references/parameters.md: stale — regenerate with "
                "scripts/generate_parameters_md.py"
            )
    return errors


def lint_skill(skill_dir: Path) -> list[str]:
    """Return a list of lint errors for one skill directory.

    Empty list = clean.  Legacy skills (no parameters.yaml) always return [].
    """
    parsed = _parse_skill_md(skill_dir)
    if parsed is None:
        return [f"{skill_dir}: SKILL.md missing or unparseable"]
    frontmatter, body = parsed

    sidecar_path = skill_dir / "parameters.yaml"
    if not sidecar_path.exists():
        return []  # legacy skill — defer until migrated

    try:
        sidecar = yaml.safe_load(sidecar_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return [f"parameters.yaml: invalid YAML ({exc})"]

    errors: list[str] = []
    errors.extend(_check_description(frontmatter.get("description", "")))
    errors.extend(_check_body(body))
    errors.extend(_check_frontmatter_keys(frontmatter))
    errors.extend(_check_sidecar(sidecar))
    errors.extend(_check_references(skill_dir, sidecar))
    return errors


def discover_skills(skills_root: Path) -> list[Path]:
    """Every directory containing a SKILL.md, recursively."""
    return sorted(p.parent for p in skills_root.rglob("SKILL.md"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("skill_dir", nargs="?", type=Path)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--strict", action="store_true",
                        help="(reserved — currently same as default)")
    args = parser.parse_args()

    if args.all == bool(args.skill_dir):
        parser.error("provide either <skill_dir> or --all")

    from omicsclaw.core.registry import SKILLS_DIR

    targets = discover_skills(SKILLS_DIR) if args.all else [args.skill_dir]

    total_errors = 0
    for skill_dir in targets:
        errors = lint_skill(skill_dir)
        if errors:
            print(f"FAIL {skill_dir}")
            for err in errors:
                print(f"  - {err}")
            total_errors += len(errors)
        else:
            print(f"ok   {skill_dir}")

    if total_errors:
        print(f"\n{total_errors} error(s) across {len(targets)} skill(s)")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
