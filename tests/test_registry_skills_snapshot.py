"""Snapshot of ``registry.skills`` shape — the public registry contract.

After the ``_HARDCODED_SKILLS`` deletion (PR registry-data-logic-split),
SKILL.md frontmatter is the single source of truth. This test pins the
*observable* contract so a future refactor that drops a name, drops a
field, or changes a field type fails loudly.

Pinned dimensions:
  - the canonical skill set (≥80 entries) is stable
  - every pre-rename canonical (e.g. ``spatial-preprocessing``) still
    resolves to the new canonical
  - every short legacy alias shipped in CLAUDE.md examples still
    resolves
  - each canonical entry exposes the documented field-and-type set
  - each domain entry exposes its required fields
"""

from __future__ import annotations

from typing import Any

import pytest

from omicsclaw.core.registry import OmicsRegistry


# Fields every skill entry must expose with the documented type.
REQUIRED_FIELDS_AND_TYPES: dict[str, type | tuple[type, ...]] = {
    "domain": str,
    "alias": str,
    "directory_name": str,
    "demo_args": list,
    "description": str,
    "trigger_keywords": list,
    "allowed_extra_flags": (set, frozenset, list),
    "legacy_aliases": list,
    "saves_h5ad": bool,
    "requires_preprocessed": bool,
    "param_hints": dict,
}


@pytest.fixture(scope="module")
def loaded_registry() -> OmicsRegistry:
    registry = OmicsRegistry()
    registry.load_all()
    return registry


def _canonical_keys(registry: OmicsRegistry) -> set[str]:
    """Return the keys that are themselves canonical (alias self-reference)."""
    return {
        name
        for name, info in registry.skills.items()
        if info.get("alias") == name
    }


def _legacy_lookup_keys(registry: OmicsRegistry) -> set[str]:
    """Keys reachable via legacy_aliases or directory-name fallback."""
    return {
        name
        for name, info in registry.skills.items()
        if info.get("alias") and info["alias"] != name
    }


def test_registry_canonical_skill_set_is_stable(loaded_registry: OmicsRegistry):
    """Every canonical alias the registry currently exposes must keep
    existing across the hardcoded-data deletion."""
    canonical_keys = _canonical_keys(loaded_registry)

    # Sanity: a meaningful number of skills are loaded.
    assert len(canonical_keys) >= 80, (
        f"only {len(canonical_keys)} canonical skills loaded; "
        f"expected ≥80 — registry discovery may be broken"
    )


def test_registry_pre_rename_canonical_names_remain_resolvable(loaded_registry: OmicsRegistry):
    """The 9 spatial pre-rename canonical names — currently surfaced both
    by hardcoded and (after this PR) by SKILL.md ``legacy_aliases`` — must
    keep resolving via the registry's lookup table."""
    pre_rename_aliases = {
        "spatial-preprocessing": "spatial-preprocess",
        "spatial-domain-identification": "spatial-domains",
        "spatial-cell-annotation": "spatial-annotate",
        "spatial-deconvolution": "spatial-deconv",
        "spatial-svg-detection": "spatial-genes",
        "spatial-condition-comparison": "spatial-condition",
        "spatial-cell-communication": "spatial-communication",
        "spatial-integration": "spatial-integrate",
        "spatial-registration": "spatial-register",
    }
    missing: list[str] = []
    misrouted: list[str] = []
    for legacy, expected_canonical in pre_rename_aliases.items():
        info = loaded_registry.skills.get(legacy)
        if info is None:
            missing.append(legacy)
            continue
        if info.get("alias") != expected_canonical:
            misrouted.append(
                f"{legacy} → {info.get('alias')!r} (expected {expected_canonical!r})"
            )
    assert not missing, f"pre-rename canonical names missing: {missing}"
    assert not misrouted, f"pre-rename canonical names mis-routed: {misrouted}"


def test_registry_short_legacy_aliases_remain_resolvable(loaded_registry: OmicsRegistry):
    """Sample of user-facing short legacy aliases that must keep
    resolving — these are the commands shipped in CLAUDE.md examples."""
    short_aliases = {
        "preprocess": "spatial-preprocess",
        "domains": "spatial-domains",
        "annotate": "spatial-annotate",
        "deconv": "spatial-deconv",
        "genes": "spatial-genes",
        "communication": "spatial-communication",
        "velocity": "spatial-velocity",
        "trajectory": "spatial-trajectory",
        "cnv": "spatial-cnv",
        "enrichment": "spatial-enrichment",
        "integrate": "spatial-integrate",
        "register": "spatial-register",
        "condition": "spatial-condition",
        "sc-preprocess": "sc-preprocessing",
        "sc-annotate": "sc-cell-annotation",
        "sc-doublet": "sc-doublet-detection",
        "sc-integrate": "sc-batch-integration",
        "scatac-preprocess": "scatac-preprocessing",
        "bulk-de": "bulkrna-de",
        "met-diff": "metabolomics-de",
        "peak-detect": "metabolomics-peak-detection",
        "variant-call": "genomics-variant-calling",
        "align": "genomics-alignment",
        "differential-abundance": "proteomics-de",
    }
    failed: list[str] = []
    for legacy, expected_canonical in short_aliases.items():
        info = loaded_registry.skills.get(legacy)
        if info is None:
            failed.append(f"{legacy} → MISSING")
            continue
        if info.get("alias") != expected_canonical:
            failed.append(f"{legacy} → {info.get('alias')!r} (expected {expected_canonical!r})")
    assert not failed, "short legacy aliases broken:\n  " + "\n  ".join(failed)


def test_every_canonical_skill_entry_exposes_the_expected_field_shape(
    loaded_registry: OmicsRegistry,
):
    """Each canonical skill entry exposes the contracted field set with
    the contracted types. New optional fields are allowed; missing
    required fields or wrong types are not."""
    canonical_keys = _canonical_keys(loaded_registry)
    failures: list[str] = []
    for name in sorted(canonical_keys):
        info = loaded_registry.skills[name]
        for field, expected_type in REQUIRED_FIELDS_AND_TYPES.items():
            if field not in info:
                failures.append(f"{name}: missing field {field!r}")
                continue
            value = info[field]
            if not isinstance(value, expected_type):
                failures.append(
                    f"{name}.{field}: type {type(value).__name__}, "
                    f"expected {expected_type}"
                )
    assert not failures, "field-shape regressions:\n  " + "\n  ".join(failures[:40])


def test_registry_domains_expose_required_fields(loaded_registry: OmicsRegistry):
    """Domain metadata is currently in ``_HARDCODED_DOMAINS``; this test
    pins the shape so any future move to a data file or auto-derivation
    has to update the assertion."""
    assert loaded_registry.domains, "no domains loaded"
    required = {"name", "primary_data_types", "skill_count", "summary", "representative_skills"}
    failures: list[str] = []
    for domain_key, info in loaded_registry.domains.items():
        missing = required - set(info)
        if missing:
            failures.append(f"{domain_key}: missing {sorted(missing)}")
    assert not failures, "\n".join(failures)
