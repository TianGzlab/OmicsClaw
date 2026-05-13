"""Skill registry lookup with alias-fallback.

``lookup_skill_info`` resolves a skill key (canonical name or alias) to
its registry metadata dict. It loads the global skill registry on
first call and supports an explicit ``force_reload`` for callers that
expect on-disk SKILL.md edits to take effect mid-process (param-hint
debug paths).
"""

from __future__ import annotations

from omicsclaw.core.registry import registry


def lookup_skill_info(skill_key: str, force_reload: bool = False) -> dict:
    skill_registry = registry
    if force_reload:
        skill_registry.reload()
    else:
        skill_registry.load_all()

    info = skill_registry.skills.get(skill_key)
    if info:
        return info

    for _k, meta in skill_registry.skills.items():
        if meta.get("alias") == skill_key:
            return meta
    return {}


__all__ = ["lookup_skill_info"]
