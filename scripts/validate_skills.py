#!/usr/bin/env python3
"""Validate all OmicsClaw skill scripts against the SkillProtocol conventions.

Scans every skill directory for Python scripts and checks them for
required constants (SKILL_NAME, SKILL_VERSION), main(), write_report(),
generate_figures(), and CLI argument conventions.

Usage:
    python scripts/validate_skills.py            # summary view
    python scripts/validate_skills.py --verbose  # show all details
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from omicsclaw.core.registry import OmicsRegistry, SKILLS_DIR
from omicsclaw.core.skill_protocol import validate_skill_module


def find_skill_scripts() -> list[Path]:
    """Find all skill main scripts via registry directory scanning."""
    reg = OmicsRegistry()
    scripts: list[Path] = []

    for domain_path in SKILLS_DIR.iterdir():
        if not domain_path.is_dir() or domain_path.name.startswith((".", "__")):
            continue
        for skill_path in reg._iter_skill_dirs(domain_path):
            script_name = f"{skill_path.name.replace('-', '_')}.py"
            script = skill_path / script_name
            if script.exists():
                scripts.append(script)

    return sorted(scripts)


def main():
    parser = argparse.ArgumentParser(description="Validate OmicsClaw skill conventions")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show info and warnings")
    args = parser.parse_args()

    scripts = find_skill_scripts()
    print(f"Found {len(scripts)} skill scripts\n")

    passed = 0
    failed = 0
    total_warnings = 0

    for script in scripts:
        result = validate_skill_module(script)
        print(result.summary_line())

        if args.verbose:
            for info in result.info:
                print(f"      {info}")
            for warn in result.warnings:
                print(f"      WARNING: {warn}")
            for err in result.errors:
                print(f"      ERROR: {err}")

        if result.passed:
            passed += 1
        else:
            failed += 1
            if not args.verbose:
                for err in result.errors:
                    print(f"      ERROR: {err}")
        total_warnings += len(result.warnings)

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed, {total_warnings} warnings")
    print(f"Total skills checked: {len(scripts)}")

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
