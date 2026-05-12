#!/usr/bin/env python3
"""Enforce the routing-context token budget.

Runs the same measurement as ``scripts/measure_routing_tokens.py`` and
compares each field against the ceiling declared in
``build/routing-baselines/ceiling.json``. Exits 1 when any ceiling is
exceeded so CI can block PRs that silently inflate the LLM's always-loaded
context.

Usage::

    python scripts/check_routing_budget.py          # check against committed ceiling
    python scripts/check_routing_budget.py --show   # print table only, no enforcement
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.measure_routing_tokens import measure  # noqa: E402

CEILING_PATH = ROOT / "build" / "routing-baselines" / "ceiling.json"


def _load_ceilings() -> dict[str, int]:
    if not CEILING_PATH.exists():
        print(f"ERROR: ceiling file not found: {CEILING_PATH}", file=sys.stderr)
        sys.exit(2)
    data = json.loads(CEILING_PATH.read_text())
    ceilings = data.get("ceilings") or {}
    if not isinstance(ceilings, dict):
        print("ERROR: ceiling.json must contain a 'ceilings' object", file=sys.stderr)
        sys.exit(2)
    return ceilings


def _print_table(current: dict[str, int], ceilings: dict[str, int]) -> list[str]:
    """Render a table; return the list of metric names that are over budget."""
    over: list[str] = []
    print(f"{'metric':<42} {'current':>9}  {'ceiling':>9}  status")
    print("-" * 72)
    for key, ceiling in ceilings.items():
        cur = current.get(key)
        if cur is None:
            print(f"{key:<42} {'--':>9}  {ceiling:>9,}  MISSING")
            continue
        status = "OK"
        if cur > ceiling:
            status = f"OVER (+{cur - ceiling:,})"
            over.append(key)
        print(f"{key:<42} {cur:>9,}  {ceiling:>9,}  {status}")
    return over


def main() -> int:
    parser = argparse.ArgumentParser(description="Check routing-context budget")
    parser.add_argument(
        "--show",
        action="store_true",
        help="Print table only; never exit non-zero",
    )
    args = parser.parse_args()

    ceilings = _load_ceilings()
    current = measure()

    print(f"Ceiling file: {CEILING_PATH.relative_to(ROOT)}\n")
    over = _print_table(current, ceilings)
    print()

    if over and not args.show:
        print("FAIL: the following metrics exceed their ceiling:")
        for key in over:
            print(f"  - {key}: {current[key]:,} > {ceilings[key]:,}")
        print()
        print(
            "If the growth is intentional, raise the ceiling in "
            "`build/routing-baselines/ceiling.json` and justify it in the PR."
        )
        return 1

    print("OK: all routing-context metrics are within budget.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
