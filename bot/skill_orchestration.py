"""Skill orchestration helpers — output media collection + auto-routing
banner / disambiguation rendering.

Carved out of ``bot/core.py`` per ADR 0001. **Reduced scope**: this slice
moves only the externally-tested public API (``OutputMediaPaths`` +
``_collect_output_media_paths``; the auto-routing banner / disambiguation
formatters and ``_AUTO_DISAMBIGUATE_GAP``). The remaining skill-execution
machinery the issue spec lists (``_run_omics_skill_step``,
``_run_skill_via_shared_runner``, ``_lookup_skill_info``,
``_resolve_param_hint_info``, ``_infer_skill_for_method``,
``_build_method_preview``, ``_build_param_hint``, the
``_auto_capture_*`` async helpers, the env-error parsing helpers, and
``_resolve_last_output_dir`` / ``_read_result_json`` /
``_update_preprocessing_state`` / ``_format_next_steps``) stays in
``bot.core`` for now — they have no external test imports and moving the
~700 LOC en bloc would require many late-import surgery passes that buy
no immediate win. A follow-up issue can complete the migration once the
agent-loop slice (#121) has consolidated the LLM client globals.

The functions in this module are pure formatters; ``_format_auto_*``
late-imports ``_skill_registry`` from ``bot.core`` to look up skill
descriptions for the disambiguation block.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OutputMediaPaths:
    figure_paths: list[Path]
    table_paths: list[Path]
    notebook_paths: list[Path]
    media_items: list[dict]


def _collect_output_media_paths(out_dir: Path) -> OutputMediaPaths:
    figure_paths: list[Path] = []
    table_paths: list[Path] = []
    notebook_paths: list[Path] = []
    media_items: list[dict] = []

    if not out_dir.exists():
        return OutputMediaPaths(figure_paths, table_paths, notebook_paths, media_items)

    for f in sorted(out_dir.rglob("*")):
        if not f.is_file():
            continue
        if f.suffix in (".md", ".html"):
            media_items.append({"type": "document", "path": str(f)})
        elif f.suffix == ".ipynb":
            media_items.append({"type": "document", "path": str(f)})
            notebook_paths.append(f)
        elif f.suffix == ".png":
            media_items.append({"type": "photo", "path": str(f)})
            figure_paths.append(f)
        elif f.suffix == ".csv":
            media_items.append({"type": "document", "path": str(f)})
            table_paths.append(f)

    return OutputMediaPaths(figure_paths, table_paths, notebook_paths, media_items)


# Auto-routing disambiguation block: emitted when the capability resolver's
# top-2 candidates are within ~``_AUTO_DISAMBIGUATE_GAP`` of each other.
# Tuned against ``capability_resolver._candidate_score`` output magnitudes
# (single keyword match is worth ~0.85 points; an alias hit is worth ~10).
_AUTO_DISAMBIGUATE_GAP = 2.0


def _format_auto_disambiguation(decision, query_text: str) -> str:
    """Return a human-readable disambiguation block for close-tie auto routing."""
    from bot.core import _skill_registry  # late import — defined later in bot.core

    candidates = list(decision.skill_candidates or [])[:3]
    if not candidates:
        return ""
    reg = _skill_registry()
    lines = [
        "🤔 **Auto-routing found multiple close candidates** — I won't execute yet.",
        f"Query: `{query_text.strip()[:200]}`",
        "",
        "**Top candidates (score — higher is better):**",
    ]
    for i, c in enumerate(candidates, 1):
        info = reg.skills.get(c.skill, {}) or {}
        desc = (info.get("description") or "").strip().replace("\n", " ")
        if len(desc) > 140:
            desc = desc[:137] + "…"
        reason = c.reasons[0] if c.reasons else ""
        lines.append(f"{i}. `{c.skill}` (score {c.score:.2f}) — {desc}")
        if reason:
            lines.append(f"   matched: {reason}")
    lines.extend([
        "",
        "**Next step:** re-invoke `omicsclaw` with `skill='<chosen alias above>'` "
        "and the same `mode`/`query`. Pick based on the user's data modality "
        "(H&E+coordinates → spatial; h5ad single-cell counts → singlecell; "
        "bulk counts csv → bulkrna; raw MS/LC-MS → proteomics/metabolomics).",
    ])
    return "\n".join(lines)


def _format_auto_route_banner(decision) -> str:
    """Return a short banner prepended to tool output when auto routing chose a skill."""
    chosen = decision.chosen_skill
    conf = float(getattr(decision, "confidence", 0.0) or 0.0)
    candidates = list(decision.skill_candidates or [])
    alts = [c.skill for c in candidates[1:3] if c.skill != chosen]
    alt_str = f" Close alternatives: {', '.join(alts)}." if alts else ""
    return (
        f"📍 Auto-routed to `{chosen}` (confidence {conf:.2f}).{alt_str} "
        "If this doesn't match the user's intent, re-invoke with an explicit `skill`.\n---\n"
    )
