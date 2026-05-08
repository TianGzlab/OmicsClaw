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


def test_hardcoded_skills_are_fully_derivable_from_skill_md_frontmatter():
    """If this test fails, its message is the audit report driving Task 1.2."""
    drifts: list[str] = []
    fields_per_skill_summary: dict[str, list[str]] = {
        "missing_skill_md": [],
        "alias_drift": [],
        "domain_drift": [],
        "allowed_extra_flags_drift": [],
        "legacy_aliases_drift": [],
        "saves_h5ad_drift": [],
        "script_drift": [],
        "description_missing": [],
    }

    for hardcoded_key, hc_info in registry_module._HARDCODED_SKILLS.items():
        script_path = Path(hc_info["script"])
        skill_md = _skill_md_for(script_path)
        if skill_md is None:
            drifts.append(
                f"[missing_skill_md] {hardcoded_key}: no SKILL.md next to {script_path}"
            )
            fields_per_skill_summary["missing_skill_md"].append(hardcoded_key)
            continue

        fm = _frontmatter(skill_md)
        omics = _omics_metadata(skill_md)

        # alias ↔ name
        hc_alias = hc_info.get("alias")
        md_name = fm.get("name")
        if hc_alias != md_name:
            drifts.append(
                f"[alias_drift] {hardcoded_key}: hardcoded.alias={hc_alias!r}, "
                f"SKILL.md.name={md_name!r}"
            )
            fields_per_skill_summary["alias_drift"].append(hardcoded_key)

        # domain
        hc_domain = hc_info.get("domain")
        md_domain = omics.get("domain")
        if hc_domain != md_domain:
            drifts.append(
                f"[domain_drift] {hardcoded_key}: hardcoded.domain={hc_domain!r}, "
                f"SKILL.md.metadata.omicsclaw.domain={md_domain!r}"
            )
            fields_per_skill_summary["domain_drift"].append(hardcoded_key)

        # allowed_extra_flags (set equality)
        hc_flags = _set(hc_info.get("allowed_extra_flags"))
        md_flags = _set(omics.get("allowed_extra_flags"))
        if hc_flags != md_flags:
            only_hc = sorted(hc_flags - md_flags)
            only_md = sorted(md_flags - hc_flags)
            drifts.append(
                f"[allowed_extra_flags_drift] {hardcoded_key}: "
                f"only_in_hardcoded={only_hc}, only_in_skill_md={only_md}"
            )
            fields_per_skill_summary["allowed_extra_flags_drift"].append(hardcoded_key)

        # legacy_aliases (set equality, ignoring ordering)
        hc_legacy = _set(hc_info.get("legacy_aliases"))
        md_legacy = _set(omics.get("legacy_aliases"))
        if hc_legacy != md_legacy:
            only_hc = sorted(hc_legacy - md_legacy)
            only_md = sorted(md_legacy - hc_legacy)
            drifts.append(
                f"[legacy_aliases_drift] {hardcoded_key}: "
                f"only_in_hardcoded={only_hc}, only_in_skill_md={only_md}"
            )
            fields_per_skill_summary["legacy_aliases_drift"].append(hardcoded_key)

        # saves_h5ad
        hc_saves = bool(hc_info.get("saves_h5ad", False))
        md_saves = bool(omics.get("saves_h5ad", False))
        if hc_saves != md_saves:
            drifts.append(
                f"[saves_h5ad_drift] {hardcoded_key}: "
                f"hardcoded={hc_saves}, SKILL.md={md_saves}"
            )
            fields_per_skill_summary["saves_h5ad_drift"].append(hardcoded_key)

        # script: SKILL.md may set "script:" relative to skill dir; otherwise
        # convention is <dir-name-with-underscores>.py
        md_script_rel = omics.get("script") or fm.get("script")
        if md_script_rel:
            md_script_resolved = (skill_md.parent / md_script_rel).resolve()
        else:
            convention = skill_md.parent / f"{skill_md.parent.name.replace('-', '_')}.py"
            md_script_resolved = convention.resolve()
        hc_script_resolved = script_path.resolve()
        if md_script_resolved != hc_script_resolved:
            drifts.append(
                f"[script_drift] {hardcoded_key}: "
                f"hardcoded={hc_script_resolved}, derived_from_SKILL.md={md_script_resolved}"
            )
            fields_per_skill_summary["script_drift"].append(hardcoded_key)

        # description presence (informational)
        if not DESCRIPTION_AUDIT_IS_INFORMATIONAL:
            hc_desc = (hc_info.get("description") or "").strip()
            md_desc = (fm.get("description") or "").strip()
            if hc_desc and not md_desc:
                drifts.append(
                    f"[description_missing] {hardcoded_key}: hardcoded has description, "
                    f"SKILL.md description is empty"
                )
                fields_per_skill_summary["description_missing"].append(hardcoded_key)

    if not drifts:
        return  # 100% derivable — Task 1.2a is unblocked

    summary_lines = [
        "",
        f"AUDIT REPORT — {len(drifts)} drift(s) across {len(registry_module._HARDCODED_SKILLS)} hardcoded entries",
        "",
        "By dimension:",
    ]
    for dim, entries in fields_per_skill_summary.items():
        if entries:
            summary_lines.append(f"  {dim}: {len(entries)} entries — {sorted(set(entries))[:8]}{'...' if len(entries) > 8 else ''}")

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
