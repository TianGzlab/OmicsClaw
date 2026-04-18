#!/usr/bin/env python3
"""Unified entry point for keeping skill-derived docs in sync.

This wraps the three generators that read skill metadata from the Registry and
write it back to human-facing documentation:

* ``scripts/generate_routing_table.py``   → ``CLAUDE.md`` routing table
* ``scripts/generate_orchestrator_counts.py`` → ``skills/orchestrator/SKILL.md``
* ``scripts/generate_catalog.py``          → ``skills/catalog.json``

Usage::

    python scripts/sync_skill_docs.py --check    # CI-friendly, exits 1 on drift
    python scripts/sync_skill_docs.py --apply    # regenerate all three
    python scripts/sync_skill_docs.py            # defaults to --check
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GENERATORS = [
    "generate_routing_table.py",
    "generate_orchestrator_counts.py",
    "generate_catalog.py",
    "generate_domain_index.py",
]


def _run(script: str, flag: str) -> int:
    cmd = [sys.executable, str(ROOT / "scripts" / script), flag]
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync all skill-derived docs in one shot")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="Regenerate all docs")
    group.add_argument("--check", action="store_true", help="Exit 1 if any doc is out of date")
    args = parser.parse_args()

    flag = "--apply" if args.apply else "--check"

    failed: list[str] = []
    for script in GENERATORS:
        rc = _run(script, flag)
        if rc != 0:
            failed.append(script)

    if failed:
        print(
            "\nFAILED: the following generators reported drift or errors: "
            + ", ".join(failed),
            file=sys.stderr,
        )
        if flag == "--check":
            print(
                "To fix locally: python scripts/sync_skill_docs.py --apply",
                file=sys.stderr,
            )
        return 1

    print("\nAll skill docs are in sync." if flag == "--check" else "\nAll skill docs regenerated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
