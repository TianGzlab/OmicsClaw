#!/usr/bin/env python3
"""Measure the token footprint of routing-related artifacts.

Reports sizes of the four places that always travel in LLM context on routing
turns, so we can track regressions as the project grows:

* ``CLAUDE.md`` routing block (between ``<!-- ROUTING-TABLE-* -->`` markers)
* ``CLAUDE.md`` full file
* bot ``omicsclaw`` tool description (built from the live registry)
* bot ``omicsclaw`` tool ``skill`` enum (N skill names)
* ``skills/orchestrator/SKILL.md`` full file

We use a 4-char/token rule of thumb (conservative for mixed English+code+YAML).
Run before and after routing-context refactors to quantify savings.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CHARS_PER_TOKEN = 4


def tok(n_chars: int) -> int:
    return n_chars // CHARS_PER_TOKEN


def _routing_block_chars() -> int:
    text = (ROOT / "CLAUDE.md").read_text()
    m = re.search(
        r"<!-- ROUTING-TABLE-START -->(.*?)<!-- ROUTING-TABLE-END -->",
        text,
        re.S,
    )
    return len(m.group(1)) if m else 0


def _claude_md_chars() -> int:
    return len((ROOT / "CLAUDE.md").read_text())


def _orchestrator_skill_chars() -> int:
    return len((ROOT / "skills" / "orchestrator" / "SKILL.md").read_text())


def _bot_tool_sizes() -> tuple[int, int, int, int, int]:
    """Return size tuple for bot-surface tool registry.

    Returns
    -------
    (description_chars, skill_enum_chars, omicsclaw_spec_json_chars,
     all_bot_tools_json_chars, bot_tool_count)
    """
    from omicsclaw.core.registry import OmicsRegistry
    from omicsclaw.runtime.bot_tools import BotToolContext, build_bot_tool_specs

    reg = OmicsRegistry()
    reg.load_all()

    skill_names: list[str] = ["auto"]
    desc_parts: list[str] = []
    seen: set[str] = set()
    for alias, info in reg.skills.items():
        if info.get("alias") != alias:
            continue
        canonical = info.get("canonical_name") or alias
        if canonical in seen:
            continue
        seen.add(canonical)
        skill_names.append(alias)
        desc_parts.append(f"{alias} ({info.get('description', alias)})")

    ctx = BotToolContext(
        skill_names=tuple(skill_names),
        skill_desc_text=", ".join(desc_parts),
    )
    specs = build_bot_tool_specs(ctx)
    omics = next(s for s in specs if s.name == "omicsclaw")

    desc = omics.description or ""
    enum_vals: list[str] = (
        omics.parameters.get("properties", {}).get("skill", {}).get("enum", [])
    )
    enum_repr = ", ".join(f'"{v}"' for v in enum_vals)

    spec_json = json.dumps(
        {"name": omics.name, "description": desc, "parameters": omics.parameters}
    )

    # Full bot-surface registry — this is the honest number the LLM sees
    # on every turn (not just omicsclaw's slice).
    all_tools_json = json.dumps(
        [
            {"name": s.name, "description": s.description, "parameters": s.parameters}
            for s in specs
        ]
    )
    return len(desc), len(enum_repr), len(spec_json), len(all_tools_json), len(specs)


def measure() -> dict[str, int]:
    routing_block = _routing_block_chars()
    claude_md = _claude_md_chars()
    orch = _orchestrator_skill_chars()
    tool_desc, skill_enum, tool_spec_json, all_tools_json, tool_count = _bot_tool_sizes()

    return {
        "claude_md_routing_block_chars": routing_block,
        "claude_md_full_chars": claude_md,
        "orchestrator_skill_md_chars": orch,
        "bot_tool_description_chars": tool_desc,
        "bot_tool_skill_enum_chars": skill_enum,
        "bot_tool_spec_json_chars": tool_spec_json,
        # Honest "what the LLM sees every turn" on the bot surface:
        "bot_all_tools_json_chars": all_tools_json,
        "bot_tool_count": tool_count,
    }


def _print_row(label: str, chars: int) -> None:
    print(f"  {label:<42} {chars:>7,} chars  ~{tok(chars):>5,} tokens")


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure routing context token footprint")
    parser.add_argument("--json", action="store_true", help="Emit raw JSON (for diffing)")
    parser.add_argument(
        "--compare",
        type=Path,
        default=None,
        help="Compare against a previous JSON snapshot",
    )
    parser.add_argument(
        "--save",
        type=Path,
        default=None,
        help="Save this snapshot to the given JSON path",
    )
    args = parser.parse_args()

    data = measure()

    if args.save:
        args.save.write_text(json.dumps(data, indent=2))
        print(f"Saved snapshot to {args.save}")

    if args.json:
        print(json.dumps(data, indent=2))
        return 0

    print("Routing context token footprint")
    print("-" * 70)
    _print_row("CLAUDE.md routing block", data["claude_md_routing_block_chars"])
    _print_row("CLAUDE.md full file", data["claude_md_full_chars"])
    _print_row("orchestrator SKILL.md", data["orchestrator_skill_md_chars"])
    _print_row("bot omicsclaw.description", data["bot_tool_description_chars"])
    _print_row("bot omicsclaw.skill enum", data["bot_tool_skill_enum_chars"])
    _print_row("bot omicsclaw full spec JSON", data["bot_tool_spec_json_chars"])
    _print_row(
        f"bot ALL tools JSON (n={data['bot_tool_count']})",
        data["bot_all_tools_json_chars"],
    )
    print("-" * 70)
    # The honest "always-loaded" budget is: full bot tool registry (LLM sees
    # every tool spec, not just omicsclaw) PLUS the claudemd routing block
    # injection. Old measure combined only the omicsclaw slice — understated.
    always_in_bot = data["bot_all_tools_json_chars"]
    print(f"  Bot tool registry always-loaded:   ~{tok(always_in_bot):,} tokens")
    print(f"  CLAUDE.md routing addend:          ~{tok(data['claude_md_routing_block_chars']):,} tokens")

    if args.compare and args.compare.exists():
        baseline = json.loads(args.compare.read_text())
        print()
        print(f"Compared to baseline ({args.compare.name}):")
        print("-" * 70)
        for key, after in data.items():
            before = baseline.get(key, 0)
            delta = after - before
            pct = (delta / before * 100.0) if before else 0.0
            sign = "+" if delta >= 0 else ""
            print(
                f"  {key:<42} {before:>7,} → {after:>7,}  "
                f"({sign}{delta:,} chars, {sign}{pct:.1f}%)"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
