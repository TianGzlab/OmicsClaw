#!/usr/bin/env python3
"""Verify every routing surface stays in sync with SKILL.md descriptions.

ADR 2026-05-11: SKILL.md frontmatter `description` is the single source
of truth for routing intent.  Three downstream surfaces are auto-generated
from it — `skills/catalog.json`, every `skills/<domain>/INDEX.md`, and the
routing table in `CLAUDE.md`.  Each has its own ``--check`` mode that
exits non-zero on drift; this orchestrator runs all three and reports a
single unified verdict for CI.

Usage:
    python scripts/check_description_drift.py        # CI mode (exits 1 on any drift)
    python scripts/check_description_drift.py -v     # verbose per-surface output
    python scripts/check_description_drift.py --fix  # run --apply on drifted surfaces

The ``--fix`` mode is for local dev convenience; CI must call without
``--fix`` so drift becomes a blocking PR signal that prompts the author
to regenerate + commit + review the diff.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

LOGGER = logging.getLogger("check_description_drift")


@dataclass
class Surface:
    """One auto-generated routing surface."""
    name: str
    generator: str         # script filename under scripts/
    artefact: str          # human-readable description of what gets regenerated
    fix_command: str = field(init=False)

    def __post_init__(self) -> None:
        self.fix_command = f"python scripts/{self.generator} --apply"


SURFACES = (
    Surface(
        name="catalog",
        generator="generate_catalog.py",
        artefact="skills/catalog.json",
    ),
    Surface(
        name="domain-index",
        generator="generate_domain_index.py",
        artefact="skills/<domain>/INDEX.md (per domain)",
    ),
    Surface(
        name="routing-table",
        generator="generate_routing_table.py",
        artefact="CLAUDE.md routing table (between ROUTING-TABLE-START/END markers)",
    ),
)


def _check_surface(surface: Surface, *, verbose: bool) -> tuple[bool, str]:
    """Run a generator in --check mode.  Returns (clean, captured_output)."""
    cmd = ["python", f"scripts/{surface.generator}", "--check"]
    proc = subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True
    )
    clean = proc.returncode == 0
    output = (proc.stdout + proc.stderr).strip()
    if verbose:
        LOGGER.info(
            "%s surface %s (rc=%d)",
            "✓" if clean else "✗",
            surface.name,
            proc.returncode,
        )
        if output:
            for line in output.splitlines():
                LOGGER.info("    %s", line)
    return clean, output


def _apply_surface(surface: Surface) -> bool:
    cmd = ["python", f"scripts/{surface.generator}", "--apply"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        LOGGER.error("FAILED to regenerate %s:\n%s", surface.name, proc.stderr)
        return False
    LOGGER.info("Regenerated %s (%s)", surface.name, surface.artefact)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-v", "--verbose", action="store_true", help="Per-surface output")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Local dev only — regenerate drifted surfaces in place "
        "(DO NOT use in CI; drift must be a blocking signal)",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )

    results = [(s, *_check_surface(s, verbose=args.verbose)) for s in SURFACES]
    drifted = [(s, out) for s, clean, out in results if not clean]

    if not drifted:
        LOGGER.info("✓ All routing surfaces in sync with SKILL.md descriptions.")
        return 0

    if args.fix:
        LOGGER.info("Drift detected — regenerating:")
        all_ok = all(_apply_surface(s) for s, _ in drifted)
        if all_ok:
            LOGGER.info(
                "Regenerated %d surface(s).  Run `git diff` to review before committing.",
                len(drifted),
            )
            return 0
        return 1

    # CI / strict mode — print unified report and exit 1.
    LOGGER.error("✗ Drift detected in %d routing surface(s):", len(drifted))
    for surface, output in drifted:
        LOGGER.error("")
        LOGGER.error("  Surface: %s", surface.name)
        LOGGER.error("  Artefact: %s", surface.artefact)
        LOGGER.error("  Fix: %s", surface.fix_command)
        if output and args.verbose:
            for line in output.splitlines()[:6]:
                LOGGER.error("    | %s", line)
    LOGGER.error("")
    LOGGER.error(
        "Per ADR 2026-05-11: SKILL.md frontmatter description is the single source "
        "of truth.  Run the fix commands above, review the diff, commit the "
        "regenerated artefacts.  Or run `python scripts/check_description_drift.py --fix` "
        "to regenerate all drifted surfaces in one step (local dev only)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
