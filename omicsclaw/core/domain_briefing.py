"""Compact domain-level briefing for LLM routing context.

Replaces the flat ``alias (description), alias (description), ...`` blob that
used to live in the bot ``omicsclaw`` tool description. A domain briefing is
cheaper (~300 tokens vs ~4,000) and more stable — it changes only when a new
domain is added, which keeps the Anthropic prompt cache warm across turns.

Single source of truth: ``_HARDCODED_DOMAINS`` in ``omicsclaw.core.registry``
(``summary`` + ``representative_skills`` fields). Skill counts are refreshed
at runtime by ``registry._refresh_domain_skill_counts``.

Display order is defined locally so new domains don't silently reorder the
briefing every time ``_HARDCODED_DOMAINS`` iteration order changes.
"""

from __future__ import annotations

from typing import Iterable

from omicsclaw.core.registry import registry

_DOMAIN_DISPLAY_ORDER = (
    "spatial",
    "singlecell",
    "genomics",
    "proteomics",
    "metabolomics",
    "bulkrna",
    "orchestrator",
    "literature",
)


def _domain_line(domain_key: str, info: dict) -> str:
    """Render one compact line for a single domain."""
    name = info.get("name", domain_key)
    count = info.get("skill_count", 0)
    summary = info.get("summary", "").strip()
    reps: Iterable[str] = info.get("representative_skills") or ()
    rep_text = ", ".join(reps)
    parts = [f"- **{domain_key}** ({count} skills — {name})"]
    if summary:
        parts.append(f"  {summary}")
    if rep_text:
        parts.append(f"  Key skills: {rep_text}")
    return "\n".join(parts)


def build_domain_briefing(
    *,
    lead_in: str = "",
    trailing_hint: str = "",
    ensure_loaded: bool = True,
) -> str:
    """Return a compact multi-domain briefing block.

    Parameters
    ----------
    lead_in:
        Optional sentence prepended to the block (e.g. context-specific intro).
    trailing_hint:
        Optional sentence appended. Common use: tell the LLM where to fetch
        the full per-domain skill list (e.g. ``skills/<domain>/INDEX.md``).
    ensure_loaded:
        If True, call ``registry.load_all()`` so ``skill_count`` is accurate.
        Tests may pass False to avoid disk I/O.
    """
    if ensure_loaded:
        registry.load_all()

    lines: list[str] = []
    if lead_in:
        lines.append(lead_in.strip())
        lines.append("")

    for key in _DOMAIN_DISPLAY_ORDER:
        info = registry.domains.get(key)
        if not info:
            continue
        lines.append(_domain_line(key, info))

    if trailing_hint:
        lines.append("")
        lines.append(trailing_hint.strip())

    return "\n".join(lines)


__all__ = ["build_domain_briefing"]
