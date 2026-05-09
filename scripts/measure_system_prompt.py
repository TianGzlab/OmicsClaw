#!/usr/bin/env python3
"""Measure the assembled system prompt size for a given request shape.

Used as a size-regression spot check during the system-prompt-compression
refactor. Run before/after each phase to observe per-layer compression.

Examples:
    python scripts/measure_system_prompt.py --skill sc-de --query "do DE"
    python scripts/measure_system_prompt.py --surface interactive --workspace /tmp/run42
    python scripts/measure_system_prompt.py --bare   # baseline, empty dynamic context
"""

from __future__ import annotations

import argparse
import sys

from omicsclaw.runtime.context_assembler import assemble_prompt_context
from omicsclaw.runtime.context_layers import ContextAssemblyRequest


def _build_request(args: argparse.Namespace) -> ContextAssemblyRequest:
    capability_context = ""
    if args.with_capability:
        capability_context = (
            "## Deterministic Capability Assessment\n"
            f"- coverage: exact_skill\n- chosen_skill: {args.skill or 'sc-de'}\n"
            f"- domain: {args.domain or 'singlecell'}"
        )
    memory_context = "User prefers DESeq2-style outputs." if args.with_memory else ""
    plan_context = "## Active Plan\n- Step 1: load data\n- Step 2: run analysis" if args.with_plan else ""
    mcp_servers = ({"name": "github", "transport": "stdio", "active": True},) if args.with_mcp else ()
    return ContextAssemblyRequest(
        surface=args.surface,
        skill=args.skill,
        query=args.query,
        domain=args.domain,
        capability_context=capability_context,
        memory_context=memory_context,
        plan_context=plan_context,
        workspace=args.workspace,
        pipeline_workspace=args.pipeline_workspace or args.workspace,
        mcp_servers=mcp_servers,
    )


def _print_table(asm) -> None:
    total = asm.total_chars or 1
    print(f"=== surface={asm.request.surface} skill={asm.request.skill or '(none)'} "
          f"query={(asm.request.query or '')[:50]!r} ===")
    print(f"Total chars: {asm.total_chars}")
    print(f"Total estimated tokens: {asm.total_estimated_tokens}")
    print(f"System prompt chars: {len(asm.system_prompt)}")
    print()
    print(f"  {'layer':32s} {'order':>5s} {'place':>10s} {'chars':>7s} {'tokens':>7s} {'pct':>6s}")
    print(f"  {'-'*32} {'-'*5} {'-'*10} {'-'*7} {'-'*7} {'-'*6}")
    for layer in asm.layers:
        pct = 100 * layer.cost_chars / total
        print(
            f"  {layer.name:32s} {layer.order:>5d} {layer.placement:>10s} "
            f"{layer.cost_chars:>7d} {layer.estimated_tokens:>7d} {pct:>5.1f}%"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--surface", choices=("bot", "interactive", "pipeline"), default="bot")
    parser.add_argument("--skill", default="")
    parser.add_argument("--query", default="")
    parser.add_argument("--domain", default="")
    parser.add_argument("--workspace", default="")
    parser.add_argument("--pipeline-workspace", default="")
    parser.add_argument("--with-capability", action="store_true",
                        help="include a synthetic capability_assessment block")
    parser.add_argument("--with-memory", action="store_true",
                        help="include a synthetic memory_context block")
    parser.add_argument("--with-plan", action="store_true",
                        help="include a synthetic plan_context block")
    parser.add_argument("--with-mcp", action="store_true",
                        help="include a synthetic active MCP server")
    parser.add_argument("--bare", action="store_true",
                        help="baseline: no dynamic context, surface=bot")
    args = parser.parse_args()

    if args.bare:
        request = ContextAssemblyRequest(surface=args.surface)
    else:
        request = _build_request(args)

    try:
        asm = assemble_prompt_context(request=request)
    except Exception as exc:
        print(f"ERROR: assemble_prompt_context failed: {exc}", file=sys.stderr)
        return 2

    _print_table(asm)
    return 0


if __name__ == "__main__":
    sys.exit(main())
