from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from omicsclaw.core.registry import OmicsRegistry
from omicsclaw.core.skill_runner import resolve_skill_alias


ROOT = Path(__file__).resolve().parent.parent


def _frontmatter(skill_md: Path) -> dict[str, Any]:
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    return yaml.safe_load(text.split("---", 2)[1]) or {}


def test_discovered_skill_legacy_aliases_are_owned_by_skill_md():
    registry = OmicsRegistry()
    registry.load_all()

    mismatches: list[str] = []
    for alias, info in registry.iter_primary_skills():
        script_path = Path(info["script"])
        skill_md = script_path.parent / "SKILL.md"
        if not skill_md.exists():
            continue

        data = _frontmatter(skill_md)
        omics = data.get("metadata", {}).get("omicsclaw", {}) if isinstance(data, dict) else {}
        expected_aliases = list(omics.get("legacy_aliases", []) or [])
        actual_aliases = list(info.get("legacy_aliases", []) or [])
        if actual_aliases != expected_aliases:
            mismatches.append(
                f"{alias}: registry legacy_aliases={actual_aliases!r}, "
                f"SKILL.md legacy_aliases={expected_aliases!r}"
            )

    assert not mismatches, "\n".join(mismatches[:80])


def test_declared_legacy_aliases_still_resolve_to_canonical_skill_names():
    assert resolve_skill_alias("preprocess") == "spatial-preprocess"
    assert resolve_skill_alias("domains") == "spatial-domains"
    assert resolve_skill_alias("sc-preprocess") == "sc-preprocessing"


# Snapshot of user-facing legacy aliases that must keep resolving.
# Adding to this set is fine; removing requires a deliberate review because it
# breaks existing user invocations like `oc run preprocess` or chat history
# that referenced the short name.
_LOCKED_LEGACY_ALIASES: tuple[tuple[str, str], ...] = (
    ("preprocess", "spatial-preprocess"),
    ("domains", "spatial-domains"),
    ("de", "spatial-de"),
    ("genes", "spatial-genes"),
    ("statistics", "spatial-statistics"),
    ("annotate", "spatial-annotate"),
    ("deconv", "spatial-deconv"),
    ("communication", "spatial-communication"),
    ("velocity", "spatial-velocity"),
    ("trajectory", "spatial-trajectory"),
    ("cnv", "spatial-cnv"),
    ("enrichment", "spatial-enrichment"),
    ("integrate", "spatial-integrate"),
    ("register", "spatial-register"),
    ("condition", "spatial-condition"),
    ("sc-preprocess", "sc-preprocessing"),
    ("sc-annotate", "sc-cell-annotation"),
    ("sc-doublet", "sc-doublet-detection"),
    ("sc-integrate", "sc-batch-integration"),
    ("scatac-preprocess", "scatac-preprocessing"),
    ("bulk-de", "bulkrna-de"),
    ("bulk-wgcna", "bulkrna-coexpression"),
    ("met-diff", "metabolomics-de"),
    ("peak-detect", "metabolomics-peak-detection"),
    ("variant-call", "genomics-variant-calling"),
    ("align", "genomics-alignment"),
    ("differential-abundance", "proteomics-de"),
)


def test_locked_legacy_aliases_resolve_to_canonical_names():
    """Snapshot test: removing any of these aliases breaks existing user invocations.

    If this test fails, a SKILL.md `legacy_aliases:` entry was likely removed.
    Either restore it, or - if the rename is intentional - update this snapshot
    in the same PR so the breakage is reviewed explicitly.
    """
    failed: list[str] = []
    for legacy, canonical in _LOCKED_LEGACY_ALIASES:
        resolved = resolve_skill_alias(legacy)
        if resolved != canonical:
            failed.append(f"{legacy!r} -> {resolved!r} (expected {canonical!r})")
    assert not failed, "Locked legacy aliases changed:\n  " + "\n  ".join(failed)
