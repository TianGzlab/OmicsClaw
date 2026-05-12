#!/usr/bin/env python3
"""Measure the assembled tool list size for a given request shape.

Used as a size-regression spot check during the tool-list-compression
refactor. Prints per-tool description + parameter-schema cost so the
top contributors are visible.

Examples:
    python scripts/measure_tool_list.py
    python scripts/measure_tool_list.py --query "do DE on /tmp/x.h5ad"
    python scripts/measure_tool_list.py --skill sc-de --top 10
"""

from __future__ import annotations

import argparse
import json
import sys


def _build_specs(args: argparse.Namespace):
    from omicsclaw.runtime.bot_tools import BotToolContext, build_bot_tool_specs
    from omicsclaw.runtime.context_layers import ContextAssemblyRequest
    from omicsclaw.runtime.tool_registry import select_tool_specs

    skills = tuple(s for s in (args.skill, "spatial-preprocess") if s)
    ctx = BotToolContext(
        skill_names=skills or ("sc-de",),
        domain_briefing=args.domain_briefing or "(test)",
    )
    all_specs = build_bot_tool_specs(ctx)
    if args.no_filter:
        return all_specs
    request = ContextAssemblyRequest(
        surface=args.surface,
        skill=args.skill,
        query=args.query,
        workspace=args.workspace,
        capability_context=args.capability_context,
    )
    return list(select_tool_specs(all_specs, request=request))


def _print_table(specs, top_n: int) -> None:
    rows = []
    for spec in specs:
        desc_chars = len(spec.description)
        params_chars = len(json.dumps(spec.parameters))
        total = desc_chars + params_chars
        rows.append((spec.name, desc_chars, params_chars, total))
    rows.sort(key=lambda r: -r[3])

    total_desc = sum(r[1] for r in rows)
    total_params = sum(r[2] for r in rows)
    total_combined = total_desc + total_params

    print(f"=== Tool list size summary ===")
    print(f"Total ToolSpecs: {len(specs)}")
    print(f"Total description chars: {total_desc}")
    print(f"Total parameter-schema chars: {total_params}")
    print(f"Combined per-turn cost: {total_combined} chars (~{total_combined // 4} tokens)")
    print()
    print(f"Top {top_n} by combined size:")
    print(f"  {'name':32s} {'desc':>7s} {'params':>7s} {'total':>7s} {'%':>5s}")
    print(f"  {'-' * 32} {'-' * 7} {'-' * 7} {'-' * 7} {'-' * 5}")
    for name, desc, params, total in rows[:top_n]:
        pct = 100 * total / total_combined if total_combined else 0
        print(f"  {name:32s} {desc:>7d} {params:>7d} {total:>7d} {pct:>4.1f}%")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--surface", choices=("bot", "interactive", "pipeline"), default="bot")
    parser.add_argument("--skill", default="")
    parser.add_argument("--query", default="")
    parser.add_argument("--workspace", default="")
    parser.add_argument("--capability-context", default="")
    parser.add_argument("--domain-briefing", default="")
    parser.add_argument("--top", type=int, default=10, help="Show top N tools by size")
    parser.add_argument(
        "--no-filter",
        action="store_true",
        help="Show ALL registered tools (skip predicate-gated selection). Default: filter.",
    )
    args = parser.parse_args()

    try:
        specs = _build_specs(args)
    except Exception as exc:
        print(f"ERROR: failed to build tool specs: {exc}", file=sys.stderr)
        return 2

    _print_table(specs, args.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
