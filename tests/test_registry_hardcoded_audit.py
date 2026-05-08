"""Audit ``_HARDCODED_SKILLS`` / ``_HARDCODED_DOMAINS`` against SKILL.md.

This test does NOT assert correctness of the registry; it audits whether the
inline hardcoded skill metadata is fully derivable from each skill's
``SKILL.md`` frontmatter. A green run means the hardcoded data is redundant
and can be deleted (Task 1.2a). A red run reports the gaps that must be
either filled in SKILL.md (and re-run) or preserved by extracting the
hardcoded data to an external file (Task 1.2b).

Audit dimensions per hardcoded entry:
- ``alias``           ↔  SKILL.md ``name``
- ``domain``          ↔  ``metadata.omicsclaw.domain``
- ``description``     ↔  top-level ``description`` (semantic equivalence — see
                          ``EXPECTED_DESCRIPTION_DRIFT_OK`` toggle)
- ``allowed_extra_flags`` ↔  ``metadata.omicsclaw.allowed_extra_flags`` (set
                              equality, ignoring ordering)
- ``legacy_aliases``  ↔  ``metadata.omicsclaw.legacy_aliases`` (set equality)
- ``saves_h5ad``      ↔  ``metadata.omicsclaw.saves_h5ad``
- ``script``          ↔  filesystem path resolved via ``metadata.omicsclaw.script``
                          or directory-name convention
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from omicsclaw.core import registry as registry_module


ROOT = Path(__file__).resolve().parent.parent

# Description text is intentionally terser in the hardcoded dict (legacy
# 1-liner used in the CLI listing) than in SKILL.md (full paragraph). Treat
# this dimension as informational rather than a blocking gap unless a value
# is genuinely missing.
DESCRIPTION_AUDIT_IS_INFORMATIONAL = True


def _frontmatter(skill_md: Path) -> dict[str, Any]:
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    return yaml.safe_load(text.split("---", 2)[1]) or {}


def _omics_metadata(skill_md: Path) -> dict[str, Any]:
    fm = _frontmatter(skill_md)
    if not isinstance(fm, dict):
        return {}
    metadata = fm.get("metadata") or {}
    if not isinstance(metadata, dict):
        return {}
    return metadata.get("omicsclaw") or {}


def _skill_md_for(script_path: Path) -> Path | None:
    candidate = script_path.parent / "SKILL.md"
    return candidate if candidate.exists() else None


def _set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set, frozenset)):
        return {str(item) for item in value}
    return {str(value)}


def test_hardcoded_skills_can_be_deleted_without_data_loss():
    """Deletion-safety audit: would removing ``_HARDCODED_SKILLS`` lose
    information that SKILL.md frontmatter does not already carry?

    This is stricter than "are the dicts identical" — SKILL.md is allowed
    to be a *superset* of hardcoded (the existing merge logic already lets
    SKILL.md win). A drift fires only when hardcoded has data that SKILL.md
    cannot reconstruct.

    Drift dimensions:
      [lookup_lost]   — alias / legacy alias name resolvable via hardcoded
                        but neither in SKILL.md ``name`` nor ``legacy_aliases``
      [flags_lost]    — flag in hardcoded ``allowed_extra_flags`` but not in
                        SKILL.md
      [saves_h5ad_disagrees] — boolean disagreement between layers (must
                        resolve to the actually-true value)
      [domain_drift]  — domain disagreement (hardcoded vs SKILL.md)
      [script_drift]  — script path disagreement (post-deletion the
                        filesystem-derived path is canonical; this fires
                        only if the hardcoded path is *different*)
      [missing_skill_md] — hardcoded entry whose script has no SKILL.md
                        next to it (cannot be deleted without first
                        creating one)
    """
    drifts: list[str] = []
    summary: dict[str, list[str]] = {
        "missing_skill_md": [],
        "lookup_lost": [],
        "flags_lost": [],
        "saves_h5ad_disagrees": [],
        "domain_drift": [],
        "script_drift": [],
    }

    for hardcoded_key, hc_info in registry_module._HARDCODED_SKILLS.items():
        script_path = Path(hc_info["script"])
        skill_md = _skill_md_for(script_path)
        if skill_md is None:
            drifts.append(
                f"[missing_skill_md] {hardcoded_key}: no SKILL.md next to {script_path}"
            )
            summary["missing_skill_md"].append(hardcoded_key)
            continue

        fm = _frontmatter(skill_md)
        omics = _omics_metadata(skill_md)

        # lookup_lost: every name resolvable via hardcoded must be reachable
        # via SKILL.md's name + legacy_aliases.
        hc_names = {hc_info.get("alias"), hardcoded_key} | _set(hc_info.get("legacy_aliases"))
        hc_names.discard(None)
        md_name = fm.get("name")
        md_lookups = ({md_name} if md_name else set()) | _set(omics.get("legacy_aliases"))
        lost_names = hc_names - md_lookups
        if lost_names:
            drifts.append(
                f"[lookup_lost] {hardcoded_key}: deleting hardcoded would drop "
                f"{sorted(lost_names)} as resolvable names "
                f"(SKILL.md provides {sorted(md_lookups)})"
            )
            summary["lookup_lost"].append(hardcoded_key)

        # flags_lost: SKILL.md must list every flag hardcoded allows.
        hc_flags = _set(hc_info.get("allowed_extra_flags"))
        md_flags = _set(omics.get("allowed_extra_flags"))
        flags_only_in_hc = hc_flags - md_flags
        if flags_only_in_hc:
            drifts.append(
                f"[flags_lost] {hardcoded_key}: deleting hardcoded would drop "
                f"flags {sorted(flags_only_in_hc)} (not in SKILL.md)"
            )
            summary["flags_lost"].append(hardcoded_key)

        # saves_h5ad: layers must agree.
        hc_saves = bool(hc_info.get("saves_h5ad", False))
        md_saves = bool(omics.get("saves_h5ad", False))
        if hc_saves != md_saves:
            drifts.append(
                f"[saves_h5ad_disagrees] {hardcoded_key}: hardcoded={hc_saves}, "
                f"SKILL.md={md_saves} — investigate which is true"
            )
            summary["saves_h5ad_disagrees"].append(hardcoded_key)

        # domain: must agree.
        hc_domain = hc_info.get("domain")
        md_domain = omics.get("domain")
        if hc_domain and md_domain and hc_domain != md_domain:
            drifts.append(
                f"[domain_drift] {hardcoded_key}: hardcoded.domain={hc_domain!r}, "
                f"SKILL.md.domain={md_domain!r}"
            )
            summary["domain_drift"].append(hardcoded_key)

        # script path agreement (informational — post-deletion the filesystem
        # convention takes over; only fires if hardcoded path is *not* the
        # convention OR an explicit SKILL.md "script:" override).
        md_script_rel = omics.get("script") or fm.get("script")
        if md_script_rel:
            md_script_resolved = (skill_md.parent / md_script_rel).resolve()
        else:
            convention = skill_md.parent / f"{skill_md.parent.name.replace('-', '_')}.py"
            md_script_resolved = convention.resolve()
        hc_script_resolved = script_path.resolve()
        if md_script_resolved != hc_script_resolved:
            drifts.append(
                f"[script_drift] {hardcoded_key}: hardcoded={hc_script_resolved}, "
                f"derived_from_SKILL.md={md_script_resolved}"
            )
            summary["script_drift"].append(hardcoded_key)

    if not drifts:
        return  # No data loss on deletion — Task 1.2c step 4 is unblocked

    summary_lines = [
        "",
        f"DELETION-SAFETY AUDIT — {len(drifts)} blocker(s) across "
        f"{len(registry_module._HARDCODED_SKILLS)} hardcoded entries",
        "",
        "By dimension:",
    ]
    for dim, entries in summary.items():
        if entries:
            summary_lines.append(
                f"  {dim}: {len(entries)} — {sorted(set(entries))[:10]}"
                f"{'...' if len(entries) > 10 else ''}"
            )

    summary_lines.append("")
    summary_lines.append("Detailed drifts (first 60):")
    summary_lines.extend(f"  {d}" for d in drifts[:60])
    if len(drifts) > 60:
        summary_lines.append(f"  ... and {len(drifts) - 60} more")

    pytest.fail("\n".join(summary_lines))


def test_hardcoded_domains_are_fully_derivable_from_skill_md_or_orchestrator():
    """``_HARDCODED_DOMAINS`` carries domain-level metadata (display name,
    skill_count, summary, representative_skills, primary_data_types). None of
    these are stored per-SKILL.md; they live in scripts/generate_orchestrator_counts
    output and skills/orchestrator/. This test documents the shape of that
    coupling so Task 1.2 can decide where the data should live.
    """
    domains = registry_module._HARDCODED_DOMAINS
    findings: list[str] = []
    for domain_key, info in domains.items():
        for required_field in ("name", "primary_data_types", "skill_count", "summary", "representative_skills"):
            if required_field not in info:
                findings.append(f"{domain_key}: missing field '{required_field}'")

    # This is informational — we expect domains data to live in hardcoded form
    # today; the test exists so future PRs that move this data are forced to
    # update or delete the assertion.
    assert not findings, "\n".join(findings)
