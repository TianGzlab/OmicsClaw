"""OmicsClaw Skill Registry.

Centralises skill definition, discovery, and loading across all omics domains.
"""

from __future__ import annotations

import copy
import json
import logging
import os
from pathlib import Path
from typing import Any

from omicsclaw.core.lazy_metadata import LazySkillMetadata

logger = logging.getLogger(__name__)

def _resolve_omicsclaw_dir() -> Path:
    override = str(os.getenv("OMICSCLAW_DIR", "") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


# Base directories
OMICSCLAW_DIR = _resolve_omicsclaw_dir()
SKILLS_DIR = OMICSCLAW_DIR / "skills"


class OmicsRegistry:
    """Manages skill definitions and dynamic discovery."""

    def __init__(self):
        self.skills: dict[str, dict[str, Any]] = {}
        self.domains = {
            domain: dict(info)
            for domain, info in _HARDCODED_DOMAINS.items()
        }
        self._loaded = False
        self.lazy_skills: dict[str, LazySkillMetadata] = {}

    @staticmethod
    def _top_level_python_files(skill_path: Path) -> list[Path]:
        """Return runnable top-level Python files in a skill directory."""
        return sorted(
            path for path in skill_path.glob("*.py")
            if path.name != "__init__.py" and not path.name.startswith("test_")
        )

    @classmethod
    def _looks_like_skill_dir(cls, skill_path: Path) -> bool:
        """Heuristically decide whether a directory is a skill directory."""
        if (skill_path / "SKILL.md").exists():
            return True

        expected = skill_path / f"{skill_path.name.replace('-', '_')}.py"
        if expected.exists():
            return True

        return len(cls._top_level_python_files(skill_path)) == 1

    @classmethod
    def _is_enabled_skill_dir(cls, skill_path: Path) -> bool:
        try:
            from omicsclaw.extensions import load_extension_state

            return load_extension_state(skill_path).enabled
        except Exception:
            return True

    @classmethod
    def _iter_skill_dirs(cls, domain_path: Path):
        """Yield skill directories, handling optional subdomain nesting.

        Supports both flat layouts (spatial/spatial-preprocess/) and nested
        layouts with a subdomain tier (singlecell/scrna/sc-qc/).  A child
        directory is treated as a skill if it contains a matching
        ``<dir_name>.py`` script or a ``SKILL.md``.  Otherwise it is assumed
        to be a subdomain container and scanned one level deeper.
        """
        for child in domain_path.iterdir():
            if not child.is_dir() or child.name.startswith(('.', '__', '_')):
                continue
            if domain_path.name != "orchestrator" and child.name == "orchestrator":
                continue
            if not cls._is_enabled_skill_dir(child):
                continue

            if cls._looks_like_skill_dir(child):
                yield child
            else:
                # Subdomain container (e.g., scrna/, scatac/, multiome/)
                for grandchild in child.iterdir():
                    if not grandchild.is_dir() or grandchild.name.startswith(('.', '__', '_')):
                        continue
                    if domain_path.name != "orchestrator" and grandchild.name == "orchestrator":
                        continue
                    if not cls._is_enabled_skill_dir(grandchild):
                        continue
                    if cls._looks_like_skill_dir(grandchild):
                        yield grandchild

    @classmethod
    def _resolve_script_path(
        cls,
        skill_path: Path,
        lazy: LazySkillMetadata | None = None,
    ) -> Path | None:
        """Resolve the runnable script for a skill directory."""
        candidates: list[Path] = []

        if lazy and lazy.script:
            candidates.append(skill_path / lazy.script)

        expected = skill_path / f"{skill_path.name.replace('-', '_')}.py"
        candidates.append(expected)

        for candidate in candidates:
            if candidate.exists():
                return candidate

        py_files = cls._top_level_python_files(skill_path)
        if len(py_files) == 1:
            return py_files[0]

        return None

    @staticmethod
    def _unique_strings(values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            text = str(value).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result

    def _register_skill_entry(
        self,
        canonical_alias: str,
        info: dict[str, Any],
        *,
        skill_dir_name: str,
    ) -> None:
        """Register a primary skill entry plus all supported lookup aliases.

        Each alias key gets its own deep-copied snapshot of ``info`` so that a
        future caller mutating one alias view (e.g. ``info["allowed_extra_flags"]
        .add(...)``) does not silently corrupt the canonical or sibling views.
        """
        self.skills[canonical_alias] = copy.deepcopy(info)

        lookup_keys: list[str] = list(info.get("legacy_aliases", []))
        # The directory name is also a valid lookup key (e.g. ``oc run
        # sc-preprocessing`` resolves to the SKILL.md at skills/.../sc-preprocessing).
        lookup_keys.append(skill_dir_name)

        for key in self._unique_strings(lookup_keys):
            if key == canonical_alias:
                continue
            if key not in self.skills:
                self.skills[key] = copy.deepcopy(info)

    def load_all(self, skills_dir: Path | None = None) -> None:
        """Dynamically load skills from the filesystem.

        Each skill directory is expected to contain a ``SKILL.md`` whose
        frontmatter (``metadata.omicsclaw.*``) is the single source of
        truth for the skill's metadata. A skill directory without a
        readable ``SKILL.md`` description gets a minimal dynamic entry
        whose name comes from the directory; all per-skill metadata
        (legacy aliases, allowed flags, saves_h5ad, etc.) must live in
        SKILL.md.
        """
        if self._loaded:
            return

        target_dir = skills_dir or SKILLS_DIR
        if not target_dir.exists():
            return

        # Ensure lightweight metadata is available
        if not self.lazy_skills:
            self.load_lightweight(target_dir)

        # Scan domain directories
        for domain_path in target_dir.iterdir():
            if not domain_path.is_dir() or domain_path.name.startswith(('.', '__', '_')):
                continue

            domain_name = domain_path.name

            candidate_skill_dirs = []
            if self._looks_like_skill_dir(domain_path):
                candidate_skill_dirs.append(domain_path)
            candidate_skill_dirs.extend(self._iter_skill_dirs(domain_path))

            # Scan skill directories (handles subdomain nesting)
            for skill_path in candidate_skill_dirs:
                skill_dir_name = skill_path.name
                lazy = self.lazy_skills.get(skill_dir_name)

                script_path_candidate = self._resolve_script_path(skill_path, lazy=lazy)
                if script_path_candidate is None:
                    continue

                canonical_alias = (
                    (lazy.name if lazy and lazy.name else "")
                    or skill_dir_name
                )

                # Build skill_info from SKILL.md metadata (single source of truth)
                if lazy and lazy.description:
                    md_info: dict[str, Any] = {
                        "domain": lazy.domain or domain_name,
                        "alias": canonical_alias,
                        "canonical_name": canonical_alias,
                        "directory_name": skill_dir_name,
                        "script": script_path_candidate,
                        "demo_args": ["--demo"],
                        "description": lazy.description,
                        "trigger_keywords": lazy.trigger_keywords or [],
                        "allowed_extra_flags": lazy.allowed_extra_flags or set(),
                        "legacy_aliases": self._unique_strings(list(lazy.legacy_aliases or [])),
                        "saves_h5ad": lazy.saves_h5ad,
                        "requires_preprocessed": lazy.requires_preprocessed,
                        "param_hints": lazy.param_hints,
                        "gotchas": lazy.gotchas,
                    }
                else:
                    # SKILL.md missing or has no description — minimal dynamic entry.
                    # All metadata (legacy aliases, flags, saves_h5ad) defaults to
                    # empty; supply a SKILL.md to enrich.
                    md_info = {
                        "domain": domain_name,
                        "alias": canonical_alias,
                        "canonical_name": canonical_alias,
                        "directory_name": skill_dir_name,
                        "script": script_path_candidate,
                        "demo_args": ["--demo"],
                        "description": f"Dynamically loaded {canonical_alias} skill",
                        "trigger_keywords": [],
                        "allowed_extra_flags": set(),
                        "legacy_aliases": [],
                        "saves_h5ad": False,
                        "requires_preprocessed": False,
                        "param_hints": {},
                        "gotchas": [],
                    }

                self._register_skill_entry(
                    canonical_alias,
                    md_info,
                    skill_dir_name=skill_dir_name,
                )

        self._refresh_domain_skill_counts()
        self._loaded = True

    def load_lightweight(self, skills_dir: Path | None = None) -> None:
        """Load only basic skill metadata for fast startup."""
        target_dir = skills_dir or SKILLS_DIR
        if not target_dir.exists():
            return

        for domain_path in target_dir.iterdir():
            if not domain_path.is_dir() or domain_path.name.startswith(('.', '__', '_')):
                continue

            candidate_skill_dirs = []
            if self._looks_like_skill_dir(domain_path):
                candidate_skill_dirs.append(domain_path)
            candidate_skill_dirs.extend(self._iter_skill_dirs(domain_path))

            for skill_path in candidate_skill_dirs:
                skill_md = skill_path / "SKILL.md"
                if not skill_md.exists():
                    continue

                lazy = LazySkillMetadata(skill_path)
                skill_key = skill_path.name
                self.lazy_skills[skill_key] = lazy

    def _resolve_alias(self, skill_dir_name: str) -> str:
        """Map a skill directory name to its registry alias.

        Returns the canonical skill name when the directory or a legacy
        alias is known; otherwise returns ``skill_dir_name`` unchanged.
        """
        if not self._loaded:
            self.load_all()

        info = self.skills.get(skill_dir_name)
        if info:
            return str(info.get("alias", skill_dir_name))
        return skill_dir_name

    def iter_primary_skills(
        self,
        domain: str | None = None,
    ) -> list[tuple[str, dict[str, Any]]]:
        """Return the canonical skill entries, excluding alias pointers."""
        if not self._loaded:
            self.load_all()

        items: list[tuple[str, dict[str, Any]]] = []
        for alias, info in self.skills.items():
            if alias != info.get("alias", alias):
                continue
            if domain and info.get("domain") != domain:
                continue
            items.append((alias, info))
        return items

    def build_skill_catalog(self, domain: str | None = None) -> dict[str, str]:
        """Return a canonical skill->description catalog for a domain."""
        return {
            alias: info.get("description", "")
            for alias, info in self.iter_primary_skills(domain=domain)
        }

    def build_keyword_map(
        self,
        domain: str | None = None,
        fallback_map: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Build keyword->skill_alias map from SKILL.md trigger_keywords.

        Args:
            domain: If provided, only include skills from this domain.
            fallback_map: Legacy hardcoded map merged underneath
                          (SKILL.md keywords take priority).

        Returns:
            Dict mapping lowercase keyword to skill alias.
        """
        if not self.lazy_skills:
            self.load_lightweight()

        keyword_map: dict[str, str] = {}

        # Start with fallback so SKILL.md keywords override
        if fallback_map:
            keyword_map.update(fallback_map)

        for skill_key, lazy in self.lazy_skills.items():
            if domain and lazy.domain != domain:
                continue

            skill_alias = lazy.name or self._resolve_alias(skill_key)

            for kw in lazy.trigger_keywords:
                keyword_map[kw.lower()] = skill_alias

        return keyword_map

    def _refresh_domain_skill_counts(self) -> None:
        """Update domain skill counts from loaded canonical entries."""
        counts: dict[str, int] = {
            domain: 0
            for domain in self.domains
        }
        for alias, info in self.skills.items():
            if alias != info.get("alias", alias):
                continue
            domain = str(info.get("domain", "")).strip()
            if not domain:
                continue
            counts[domain] = counts.get(domain, 0) + 1

        for domain, count in counts.items():
            if domain not in self.domains:
                self.domains[domain] = {"name": domain, "primary_data_types": []}
            self.domains[domain]["skill_count"] = count


def ensure_registry_loaded(skills_dir: Path | None = None) -> OmicsRegistry:
    """Return the shared registry after ensuring full skill metadata is loaded."""
    registry.load_all(skills_dir)
    return registry


# ---------------------------------------------------------------------------
# Baseline hardcoded definitions for stable legacy mapping
# ---------------------------------------------------------------------------

_HARDCODED_DOMAINS = {
    "spatial": {
        "name": "Spatial Transcriptomics",
        "primary_data_types": ["h5ad", "h5", "zarr", "loom"],
        "skill_count": 17,
        "summary": (
            "Spatial transcriptomics for Visium/Xenium/MERFISH/Slide-seq: QC, "
            "domain detection, SVG, deconvolution, cell communication, trajectories, CNV."
        ),
        "representative_skills": [
            "spatial-preprocess", "spatial-domains", "spatial-de",
            "spatial-deconv", "spatial-communication",
        ],
    },
    "singlecell": {
        "name": "Single-Cell Omics",
        "primary_data_types": ["h5ad", "h5", "loom", "mtx"],
        "skill_count": 14,
        "summary": (
            "scRNA-seq + scATAC-seq: FASTQ→counts, QC, filter, doublet removal, "
            "normalize→HVG→PCA→UMAP→cluster, annotation, DE, trajectory, velocity, GRN, CCC."
        ),
        "representative_skills": [
            "sc-preprocessing", "sc-cell-annotation", "sc-de",
            "sc-batch-integration", "sc-pseudotime",
        ],
    },
    "genomics": {
        "name": "Genomics",
        "primary_data_types": ["vcf", "bam", "cram", "fasta", "fastq", "bed"],
        "skill_count": 10,
        "summary": (
            "Bulk DNA-seq: FASTQ QC, alignment, SNV/indel/SV/CNV calling, VCF ops, "
            "variant annotation, phasing, de novo assembly, ATAC/ChIP peak calling."
        ),
        "representative_skills": [
            "genomics-alignment", "genomics-variant-calling",
            "genomics-variant-annotation", "genomics-sv-detection",
        ],
    },
    "proteomics": {
        "name": "Proteomics",
        "primary_data_types": ["mzml", "mzxml", "csv"],
        "skill_count": 8,
        "summary": (
            "Mass spec proteomics: raw MS QC, peptide/protein ID, LFQ/TMT/DIA "
            "quantification, differential abundance, PTM, pathway enrichment."
        ),
        "representative_skills": [
            "proteomics-identification", "proteomics-quantification",
            "proteomics-de", "proteomics-enrichment",
        ],
    },
    "metabolomics": {
        "name": "Metabolomics",
        "primary_data_types": ["mzml", "cdf", "csv"],
        "skill_count": 8,
        "summary": (
            "LC-MS metabolomics: XCMS preprocessing, peak detection, metabolite "
            "annotation (SIRIUS/GNPS), normalization, DE, pathway enrichment."
        ),
        "representative_skills": [
            "metabolomics-peak-detection", "metabolomics-annotation",
            "metabolomics-de", "metabolomics-pathway-enrichment",
        ],
    },
    "bulkrna": {
        "name": "Bulk RNA-seq",
        "primary_data_types": ["csv", "tsv", "fastq", "bam"],
        "skill_count": 13,
        "summary": (
            "Bulk RNA-seq: FASTQ QC, alignment, count QC, DE (DESeq2), enrichment, "
            "splicing, WGCNA, deconvolution, PPI, survival, TrajBlend bulk-to-sc."
        ),
        "representative_skills": [
            "bulkrna-de", "bulkrna-enrichment", "bulkrna-coexpression",
            "bulkrna-deconvolution", "bulkrna-survival",
        ],
    },
    "orchestrator": {
        "name": "Orchestrator",
        "primary_data_types": ["*"],
        "skill_count": 1,
        "summary": (
            "Meta tooling: multi-omics query routing and skill scaffolding. "
            "Not an analysis — dispatches to the right domain skill."
        ),
        "representative_skills": ["orchestrator", "omics-skill-builder"],
    },
    "literature": {
        "name": "Literature",
        "primary_data_types": ["pdf", "txt", "doi", "url"],
        "skill_count": 1,
        "summary": (
            "Scientific literature parsing for PDFs, URLs, DOIs, PubMed IDs, "
            "GEO accession extraction, and dataset metadata handoff."
        ),
        "representative_skills": ["literature"],
    },
}


# Instantiate the global registry
registry = OmicsRegistry()
