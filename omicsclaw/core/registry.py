"""OmicsClaw Skill Registry.

Centralises skill definition, discovery, and loading across all omics domains.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import omicsclaw
from omicsclaw.core.lazy_metadata import LazySkillMetadata

logger = logging.getLogger(__name__)

# Base directories
OMICSCLAW_DIR = Path(omicsclaw.__file__).resolve().parent.parent
SKILLS_DIR = OMICSCLAW_DIR / "skills"


class OmicsRegistry:
    """Manages skill definitions and dynamic discovery."""

    def __init__(self):
        self.skills: dict[str, dict[str, Any]] = {}
        self.domains = _HARDCODED_DOMAINS.copy()
        self._loaded = False
        self.lazy_skills: dict[str, LazySkillMetadata] = {}

    @staticmethod
    def _iter_skill_dirs(domain_path: Path):
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

            script_name = f"{child.name.replace('-', '_')}.py"
            if (child / script_name).exists() or (child / "SKILL.md").exists():
                yield child
            else:
                # Subdomain container (e.g., scrna/, scatac/, multiome/)
                for grandchild in child.iterdir():
                    if not grandchild.is_dir() or grandchild.name.startswith(('.', '__', '_')):
                        continue
                    yield grandchild

    def load_all(self, skills_dir: Path | None = None) -> None:
        """Dynamically load and merge skills from the filesystem.

        For each skill directory found, metadata is read from SKILL.md first.
        The hardcoded ``_HARDCODED_SKILLS`` dict fills in any fields that
        SKILL.md does not define (backward-compatible fallback).
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
            if not domain_path.is_dir() or domain_path.name.startswith(('.', '__')):
                continue

            domain_name = domain_path.name

            # Scan skill directories (handles subdomain nesting)
            for skill_path in self._iter_skill_dirs(domain_path):
                skill_dir_name = skill_path.name

                # Convention: script matches dir name with underscores
                script_name = f"{skill_dir_name.replace('-', '_')}.py"
                script_path_candidate = skill_path / script_name

                if not script_path_candidate.exists():
                    continue

                # Determine the registry alias for this skill.
                # Check if a hardcoded entry already maps to this script.
                hardcoded_alias = None
                hardcoded_info = None
                for alias, info in _HARDCODED_SKILLS.items():
                    if info.get("script") == script_path_candidate:
                        hardcoded_alias = alias
                        hardcoded_info = info
                        break

                skill_alias = hardcoded_alias or skill_dir_name

                # Build skill_info from SKILL.md metadata (primary source)
                lazy = self.lazy_skills.get(skill_dir_name)
                if lazy and lazy.description:
                    md_info: dict[str, Any] = {
                        "domain": lazy.domain or domain_name,
                        "alias": skill_alias,
                        "script": script_path_candidate,
                        "demo_args": ["--demo"],
                        "description": lazy.description,
                        "allowed_extra_flags": lazy.allowed_extra_flags or set(),
                        "legacy_aliases": lazy.legacy_aliases or [],
                        "saves_h5ad": lazy.saves_h5ad,
                        "requires_preprocessed": lazy.requires_preprocessed,
                        "param_hints": lazy.param_hints,
                    }
                else:
                    # No SKILL.md or empty — minimal dynamic entry
                    md_info = {
                        "domain": domain_name,
                        "alias": skill_alias,
                        "script": script_path_candidate,
                        "demo_args": ["--demo"],
                        "description": f"Dynamically loaded {skill_alias} skill",
                        "allowed_extra_flags": set(),
                        "saves_h5ad": False,
                    }

                # Merge: hardcoded fills gaps that SKILL.md didn't provide
                if hardcoded_info:
                    for key, value in hardcoded_info.items():
                        if key not in md_info:
                            md_info[key] = value
                        elif key == "allowed_extra_flags" and not md_info[key]:
                            # If SKILL.md has empty flags, use hardcoded
                            md_info[key] = value
                        elif key == "description" and md_info[key].startswith("Dynamically loaded"):
                            md_info[key] = value

                self.skills[skill_alias] = md_info

                # Register legacy aliases as pointers
                for la in md_info.get("legacy_aliases", []):
                    if la not in self.skills:
                        self.skills[la] = md_info

        # Fallback: register any hardcoded skills not discovered on filesystem
        for alias, info in _HARDCODED_SKILLS.items():
            if alias not in self.skills:
                self.skills[alias] = info
                # Also register legacy aliases from hardcoded
                for la in info.get("legacy_aliases", []):
                    if la not in self.skills:
                        self.skills[la] = info

        self._loaded = True

    def load_lightweight(self, skills_dir: Path | None = None) -> None:
        """Load only basic skill metadata for fast startup."""
        target_dir = skills_dir or SKILLS_DIR
        if not target_dir.exists():
            return

        for domain_path in target_dir.iterdir():
            if not domain_path.is_dir() or domain_path.name.startswith(('.', '__')):
                continue

            for skill_path in self._iter_skill_dirs(domain_path):
                skill_md = skill_path / "SKILL.md"
                if not skill_md.exists():
                    continue

                lazy = LazySkillMetadata(skill_path)
                skill_key = skill_path.name
                self.lazy_skills[skill_key] = lazy

    def _resolve_alias(self, skill_dir_name: str) -> str:
        """Map a skill directory name to its registry alias.

        Handles cases like ``spatial-preprocess`` -> ``spatial-preprocessing``.
        Falls back to the directory name itself if no explicit mapping exists.
        """
        for alias, info in self.skills.items():
            script_path = info.get("script")
            if script_path and Path(script_path).parent.name == skill_dir_name:
                return alias
        return skill_dir_name

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

            skill_alias = self._resolve_alias(skill_key)

            for kw in lazy.trigger_keywords:
                keyword_map[kw.lower()] = skill_alias

        return keyword_map





# ---------------------------------------------------------------------------
# Baseline hardcoded definitions for stable legacy mapping
# ---------------------------------------------------------------------------

_HARDCODED_DOMAINS = {
    "spatial": {
        "name": "Spatial Transcriptomics",
        "primary_data_types": ["h5ad", "h5", "zarr", "loom"],
        "skill_count": 16,
    },
    "singlecell": {
        "name": "Single-Cell Omics",
        "primary_data_types": ["h5ad", "h5", "loom", "mtx"],
        "skill_count": 13,
    },
    "genomics": {
        "name": "Genomics",
        "primary_data_types": ["vcf", "bam", "cram", "fasta", "fastq", "bed"],
        "skill_count": 10,
    },
    "proteomics": {
        "name": "Proteomics",
        "primary_data_types": ["mzml", "mzxml", "csv"],
        "skill_count": 8,
    },
    "metabolomics": {
        "name": "Metabolomics",
        "primary_data_types": ["mzml", "cdf", "csv"],
        "skill_count": 8,
    },
    "bulkrna": {
        "name": "Bulk RNA-seq",
        "primary_data_types": ["csv", "tsv", "fastq", "bam"],
        "skill_count": 13,
    },
    "orchestrator": {
        "name": "Orchestrator",
        "primary_data_types": ["*"],
        "skill_count": 1,
    },
}


_HARDCODED_SKILLS: dict[str, dict[str, Any]] = {
    "spatial-preprocessing": {
        "domain": "spatial",
        "alias": "spatial-preprocessing",
        "legacy_aliases": ["preprocess"],
        "script": SKILLS_DIR / "spatial" / "spatial-preprocess" / "spatial_preprocess.py",
        "demo_args": ["--demo"],
        "description": "Spatial data QC, normalization, HVG, PCA/UMAP, Leiden clustering",
        "allowed_extra_flags": {
            "--data-type", "--min-genes", "--min-cells", "--max-mt-pct",
            "--n-top-hvg", "--n-pcs", "--n-neighbors", "--leiden-resolution",
            "--species",
        },
        "saves_h5ad": True,
    },
    "spatial-domain-identification": {
        "domain": "spatial",
        "alias": "spatial-domain-identification",
        "legacy_aliases": ["domains"],
        "script": SKILLS_DIR / "spatial" / "spatial-domains" / "spatial_domains.py",
        "demo_args": ["--demo"],
        "description": "Tissue region/niche identification (Leiden, Louvain, SpaGCN, STAGATE, GraphST, BANKSY)",
        "allowed_extra_flags": {
            "--method", "--n-domains", "--resolution",
            "--spatial-weight", "--rad-cutoff", "--lambda-param", "--refine",
        },
        "saves_h5ad": True,
    },
    "spatial-cell-annotation": {
        "domain": "spatial",
        "alias": "spatial-cell-annotation",
        "legacy_aliases": ["annotate"],
        "script": SKILLS_DIR / "spatial" / "spatial-annotate" / "spatial_annotate.py",
        "demo_args": ["--demo"],
        "description": "Cell type annotation (marker_based, Tangram, scANVI, CellAssign)",
        "allowed_extra_flags": {
            "--method", "--reference", "--cell-type-key",
            "--cluster-key", "--species", "--model",
        },
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "spatial-deconvolution": {
        "domain": "spatial",
        "alias": "spatial-deconvolution",
        "legacy_aliases": ["deconv"],
        "script": SKILLS_DIR / "spatial" / "spatial-deconv" / "spatial_deconv.py",
        "demo_args": ["--demo"],
        "description": "Deconvolution — cell type proportions (NNLS, Cell2Location, RCTD, Tangram, CARD)",
        "allowed_extra_flags": {"--method", "--reference", "--cell-type-key", "--n-epochs", "--no-gpu"},
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "spatial-statistics": {
        "domain": "spatial",
        "alias": "spatial-statistics",
        "legacy_aliases": ["statistics"],
        "script": SKILLS_DIR / "spatial" / "spatial-statistics" / "spatial_statistics.py",
        "demo_args": ["--demo"],
        "description": "Spatial statistics (Moran's I, Geary's C, Getis-Ord Gi*, Ripley, neighborhood enrichment, network properties)",
        "allowed_extra_flags": {
            "--analysis-type", "--cluster-key", "--genes", "--n-top-genes",
        },
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "spatial-svg-detection": {
        "domain": "spatial",
        "alias": "spatial-svg-detection",
        "legacy_aliases": ["genes"],
        "script": SKILLS_DIR / "spatial" / "spatial-genes" / "spatial_genes.py",
        "demo_args": ["--demo"],
        "description": "Spatially variable genes (Moran's I, SpatialDE, SPARK-X, FlashS)",
        "allowed_extra_flags": {
            "--method",
            "--n-top-genes",
            "--fdr-threshold",
            "--morans-coord-type",
            "--morans-corr-method",
            "--morans-n-neighs",
            "--morans-n-perms",
            "--spatialde-min-counts",
            "--spatialde-no-aeh",
            "--spatialde-aeh-patterns",
            "--spatialde-aeh-lengthscale",
            "--sparkx-num-cores",
            "--sparkx-option",
            "--sparkx-max-genes",
            "--flashs-n-rand-features",
            "--flashs-bandwidth",
        },
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "spatial-de": {
        "domain": "spatial",
        "alias": "spatial-de",
        "legacy_aliases": ["de"],
        "script": SKILLS_DIR / "spatial" / "spatial-de" / "spatial_de.py",
        "demo_args": ["--demo"],
        "description": "Differential expression (Wilcoxon, t-test, PyDESeq2 pseudobulk)",
        "allowed_extra_flags": {
            "--groupby", "--group1", "--group2", "--method", "--n-top-genes",
        },
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "spatial-condition-comparison": {
        "domain": "spatial",
        "alias": "spatial-condition-comparison",
        "legacy_aliases": ["condition"],
        "script": SKILLS_DIR / "spatial" / "spatial-condition" / "spatial_condition.py",
        "demo_args": ["--demo"],
        "description": "Condition comparison with pseudobulk DESeq2 statistics",
        "allowed_extra_flags": {
            "--condition-key", "--sample-key", "--reference-condition",
        },
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "spatial-cell-communication": {
        "domain": "spatial",
        "alias": "spatial-cell-communication",
        "legacy_aliases": ["communication"],
        "script": SKILLS_DIR / "spatial" / "spatial-communication" / "spatial_communication.py",
        "demo_args": ["--demo"],
        "description": "Cell-cell communication (LIANA+, CellPhoneDB, FastCCC)",
        "allowed_extra_flags": {"--method", "--species", "--cell-type-key"},
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "spatial-velocity": {
        "domain": "spatial",
        "alias": "spatial-velocity",
        "legacy_aliases": ["velocity"],
        "script": SKILLS_DIR / "spatial" / "spatial-velocity" / "spatial_velocity.py",
        "demo_args": ["--demo"],
        "description": "RNA velocity and cellular dynamics (scVelo, VeloVI)",
        "allowed_extra_flags": {"--method", "--mode"},
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "spatial-trajectory": {
        "domain": "spatial",
        "alias": "spatial-trajectory",
        "legacy_aliases": ["trajectory"],
        "script": SKILLS_DIR / "spatial" / "spatial-trajectory" / "spatial_trajectory.py",
        "demo_args": ["--demo"],
        "description": "Trajectory inference (CellRank, Palantir, DPT)",
        "allowed_extra_flags": {"--method", "--root-cell", "--n-states"},
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "spatial-enrichment": {
        "domain": "spatial",
        "alias": "spatial-enrichment",
        "legacy_aliases": ["enrichment"],
        "script": SKILLS_DIR / "spatial" / "spatial-enrichment" / "spatial_enrichment.py",
        "demo_args": ["--demo"],
        "description": "Pathway enrichment (GSEA, ORA, Enrichr, ssGSEA)",
        "allowed_extra_flags": {"--method", "--gene-set", "--species", "--source"},
        "requires_preprocessed": True,
    },
    "spatial-cnv": {
        "domain": "spatial",
        "alias": "spatial-cnv",
        "legacy_aliases": ["cnv"],
        "script": SKILLS_DIR / "spatial" / "spatial-cnv" / "spatial_cnv.py",
        "demo_args": ["--demo"],
        "description": "Copy number variation inference (inferCNVpy, Numbat)",
        "allowed_extra_flags": {"--method", "--reference-key"},
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "spatial-integration": {
        "domain": "spatial",
        "alias": "spatial-integration",
        "legacy_aliases": ["integrate"],
        "script": SKILLS_DIR / "spatial" / "spatial-integrate" / "spatial_integrate.py",
        "demo_args": ["--demo"],
        "description": "Multi-sample integration (Harmony, BBKNN, Scanorama, scVI)",
        "allowed_extra_flags": {"--method", "--batch-key"},
        "saves_h5ad": True,
    },
    "spatial-registration": {
        "domain": "spatial",
        "alias": "spatial-registration",
        "legacy_aliases": ["register"],
        "script": SKILLS_DIR / "spatial" / "spatial-register" / "spatial_register.py",
        "demo_args": ["--demo"],
        "description": "Spatial registration / slice alignment (PASTE, STalign)",
        "allowed_extra_flags": {"--method", "--reference-slice"},
        "saves_h5ad": True,
    },
    "orchestrator": {
        "domain": "orchestrator",
        "alias": "orchestrator",
        "script": SKILLS_DIR / "orchestrator" / "omics_orchestrator.py",
        "demo_args": ["--demo"],
        "description": "Multi-omics query routing across all domains (spatial, single-cell, genomics, proteomics, metabolomics, bulk RNA-seq)",
        "allowed_extra_flags": {
            "--query", "--pipeline", "--list-skills",
        },
    },
    # -----------------------------------------------------------------------
    # Single-cell domain
    # -----------------------------------------------------------------------
    "sc-qc": {
        "domain": "singlecell",
        "alias": "sc-qc",
        "script": SKILLS_DIR / "singlecell" / "scrna" / "sc-qc" / "sc_qc.py",
        "demo_args": ["--demo"],
        "description": "Calculate and visualize QC metrics for scRNA-seq data",
        "allowed_extra_flags": {"--species"},
        "saves_h5ad": True,
    },
    "sc-filter": {
        "domain": "singlecell",
        "alias": "sc-filter",
        "script": SKILLS_DIR / "singlecell" / "scrna" / "sc-filter" / "sc_filter.py",
        "demo_args": ["--demo"],
        "description": "Filter cells and genes based on QC metrics with tissue-specific presets",
        "allowed_extra_flags": {
            "--min-genes", "--max-genes", "--min-counts", "--max-counts",
            "--max-mt-percent", "--min-cells", "--tissue",
        },
        "saves_h5ad": True,
    },
    "sc-ambient-removal": {
        "domain": "singlecell",
        "alias": "sc-ambient-removal",
        "script": SKILLS_DIR / "singlecell" / "scrna" / "sc-ambient-removal" / "sc_ambient.py",
        "demo_args": ["--demo"],
        "description": "Remove ambient RNA contamination using CellBender, SoupX, or simple subtraction",
        "allowed_extra_flags": {"--method", "--expected-cells", "--raw-h5", "--raw-matrix-dir", "--filtered-matrix-dir", "--contamination"},
        "saves_h5ad": True,
    },
    "sc-preprocessing": {
        "domain": "singlecell",
        "alias": "sc-preprocessing",
        "legacy_aliases": ["sc-preprocess"],
        "script": SKILLS_DIR / "singlecell" / "scrna" / "sc-preprocessing" / "sc_preprocess.py",
        "demo_args": ["--demo"],
        "description": "scRNA-seq QC, normalization, HVG, PCA/UMAP, Leiden clustering (Scanpy, Seurat, Pegasus)",
        "allowed_extra_flags": {
            "--method", "--min-genes", "--min-cells", "--max-mt-pct",
            "--n-top-hvg", "--n-pcs", "--n-neighbors", "--leiden-resolution",
        },
        "saves_h5ad": True,
    },
    "sc-doublet-detection": {
        "domain": "singlecell",
        "alias": "sc-doublet-detection",
        "legacy_aliases": ["sc-doublet"],
        "script": SKILLS_DIR / "singlecell" / "scrna" / "sc-doublet-detection" / "sc_doublet.py",
        "demo_args": ["--demo"],
        "description": "Doublet detection and removal (Scrublet, scDblFinder, DoubletFinder)",
        "allowed_extra_flags": {"--method", "--expected-doublet-rate", "--threshold"},
        "saves_h5ad": True,
    },
    "sc-cell-annotation": {
        "domain": "singlecell",
        "alias": "sc-cell-annotation",
        "legacy_aliases": ["sc-annotate"],
        "script": SKILLS_DIR / "singlecell" / "scrna" / "sc-cell-annotation" / "sc_annotate.py",
        "demo_args": ["--demo"],
        "description": "Cell type annotation (CellTypist, SingleR, scmap, GARNET, scANVI)",
        "allowed_extra_flags": {"--method", "--reference", "--species", "--cluster-key"},
        "saves_h5ad": True,
    },
    # sc-trajectory: replaced by sc-pseudotime and sc-velocity
    "sc-pseudotime": {
        "domain": "singlecell",
        "alias": "sc-pseudotime",
        "script": SKILLS_DIR / "singlecell" / "scrna" / "sc-pseudotime" / "sc_pseudotime.py",
        "demo_args": ["--demo"],
        "description": "Pseudotime analysis with PAGA, Diffusion Map, and DPT (scanpy)",
        "allowed_extra_flags": {
            "--cluster-key", "--root-cluster", "--root-cell", "--n-dcs",
            "--n-genes", "--method",
        },
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "sc-velocity": {
        "domain": "singlecell",
        "alias": "sc-velocity",
        "script": SKILLS_DIR / "singlecell" / "scrna" / "sc-velocity" / "sc_velocity.py",
        "demo_args": ["--demo"],
        "description": "RNA velocity analysis with scVelo (requires spliced/unspliced layers)",
        "allowed_extra_flags": {"--method", "--n-jobs"},
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "sc-batch-integration": {
        "domain": "singlecell",
        "alias": "sc-batch-integration",
        "legacy_aliases": ["sc-integrate"],
        "script": SKILLS_DIR / "singlecell" / "scrna" / "sc-batch-integration" / "sc_integrate.py",
        "demo_args": ["--demo"],
        "description": "Multi-sample integration and batch correction (Harmony, scVI, BBKNN, Scanorama, fastMNN, Seurat CCA/RPCA)",
        "allowed_extra_flags": {"--method", "--batch-key", "--n-epochs", "--no-gpu"},
        "saves_h5ad": True,
    },
    "sc-de": {
        "domain": "singlecell",
        "alias": "sc-de",
        "script": SKILLS_DIR / "singlecell" / "scrna" / "sc-de" / "sc_de.py",
        "demo_args": ["--demo"],
        "description": "Differential expression analysis (Wilcoxon, t-test, MAST compatibility, pseudobulk DESeq2 via R)",
        "allowed_extra_flags": {
            "--groupby", "--group1", "--group2", "--method", "--n-top-genes", "--sample-key", "--celltype-key",
        },
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "sc-markers": {
        "domain": "singlecell",
        "alias": "sc-markers",
        "script": SKILLS_DIR / "singlecell" / "scrna" / "sc-markers" / "sc_markers.py",
        "demo_args": ["--demo"],
        "description": "Find marker genes for cell clusters using Wilcoxon, t-test, or logistic regression",
        "allowed_extra_flags": {"--groupby", "--method", "--n-genes", "--n-top"},
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "sc-grn": {
        "domain": "singlecell",
        "alias": "sc-grn",
        "script": SKILLS_DIR / "singlecell" / "scrna" / "sc-grn" / "sc_grn.py",
        "demo_args": ["--demo"],
        "description": "Gene regulatory network inference with pySCENIC (GRNBoost2, cisTarget, AUCell)",
        "allowed_extra_flags": {
            "--tf-list", "--db", "--motif", "--n-top-targets", "--n-jobs", "--seed",
        },
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "sc-cell-communication": {
        "domain": "singlecell",
        "alias": "sc-cell-communication",
        "script": SKILLS_DIR / "singlecell" / "scrna" / "sc-cell-communication" / "sc_cell_communication.py",
        "demo_args": ["--demo"],
        "description": "Cell-cell communication analysis (builtin, LIANA, CellChat)",
        "allowed_extra_flags": {"--method", "--cell-type-key", "--species"},
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    # sc-multiome: script not yet implemented
    # -----------------------------------------------------------------------
    # Genomics domain
    # -----------------------------------------------------------------------
    "genomics-qc": {
        "domain": "genomics",
        "alias": "genomics-qc",
        "script": SKILLS_DIR / "genomics" / "genomics-qc" / "genomics_qc.py",
        "demo_args": ["--demo"],
        "description": "Sequencing reads QC and adapter trimming (FastQC, MultiQC, fastp, Trimmomatic)",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    "genomics-alignment": {
        "domain": "genomics",
        "alias": "genomics-alignment",
        "legacy_aliases": ["align"],
        "script": SKILLS_DIR / "genomics" / "genomics-alignment" / "genomics_alignment.py",
        "demo_args": ["--demo"],
        "description": "Short/long read alignment to reference genome (BWA-MEM, Bowtie2, Minimap2)",
        "allowed_extra_flags": {"--method"},
        "saves_h5ad": False,
    },
    "genomics-variant-calling": {
        "domain": "genomics",
        "alias": "genomics-variant-calling",
        "legacy_aliases": ["variant-call"],
        "script": SKILLS_DIR / "genomics" / "genomics-variant-calling" / "genomics_variant_calling.py",
        "demo_args": ["--demo"],
        "description": "Germline/somatic variant calling — SNVs, Indels (GATK, DeepVariant, FreeBayes)",
        "allowed_extra_flags": {"--method"},
        "saves_h5ad": False,
    },
    "genomics-sv-detection": {
        "domain": "genomics",
        "alias": "genomics-sv-detection",
        "legacy_aliases": ["sv-detect"],
        "script": SKILLS_DIR / "genomics" / "genomics-sv-detection" / "sv_detection.py",
        "demo_args": ["--demo"],
        "description": "Structural variant calling (Manta, Lumpy, Delly, Sniffles)",
        "allowed_extra_flags": {"--method"},
        "saves_h5ad": False,
    },
    "genomics-cnv-calling": {
        "domain": "genomics",
        "alias": "genomics-cnv-calling",
        "legacy_aliases": ["cnv-calling"],
        "script": SKILLS_DIR / "genomics" / "genomics-cnv-calling" / "genomics_cnv_calling.py",
        "demo_args": ["--demo"],
        "description": "Copy number variation analysis (CNVkit, Control-FREEC, GATK gCNV)",
        "allowed_extra_flags": {"--method"},
        "saves_h5ad": False,
    },
    "genomics-vcf-operations": {
        "domain": "genomics",
        "alias": "genomics-vcf-operations",
        "legacy_aliases": ["vcf-ops"],
        "script": SKILLS_DIR / "genomics" / "genomics-vcf-operations" / "genomics_vcf_operations.py",
        "demo_args": ["--demo"],
        "description": "VCF manipulation, filtering, and merging (bcftools, GATK SelectVariants)",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    "genomics-variant-annotation": {
        "domain": "genomics",
        "alias": "genomics-variant-annotation",
        "legacy_aliases": ["variant-annotate"],
        "script": SKILLS_DIR / "genomics" / "genomics-variant-annotation" / "variant_annotation.py",
        "demo_args": ["--demo"],
        "description": "Variant annotation and functional effect prediction (VEP, snpEff, ANNOVAR)",
        "allowed_extra_flags": {"--method"},
        "saves_h5ad": False,
    },
    "genomics-assembly": {
        "domain": "genomics",
        "alias": "genomics-assembly",
        "legacy_aliases": ["assemble"],
        "script": SKILLS_DIR / "genomics" / "genomics-assembly" / "genome_assembly.py",
        "demo_args": ["--demo"],
        "description": "De novo genome assembly (SPAdes, Megahit, Flye, Canu)",
        "allowed_extra_flags": {"--method"},
        "saves_h5ad": False,
    },
    "genomics-epigenomics": {
        "domain": "genomics",
        "alias": "genomics-epigenomics",
        "legacy_aliases": ["epigenomics"],
        "script": SKILLS_DIR / "genomics" / "genomics-epigenomics" / "genomics_epigenomics.py",
        "demo_args": ["--demo"],
        "description": "ChIP-seq/ATAC-seq peak calling and motif analysis (MACS2, Homer, pyGenomeTracks)",
        "allowed_extra_flags": {"--method", "--assay"},
        "saves_h5ad": False,
    },
    "genomics-phasing": {
        "domain": "genomics",
        "alias": "genomics-phasing",
        "legacy_aliases": ["phase"],
        "script": SKILLS_DIR / "genomics" / "genomics-phasing" / "genomics_phasing.py",
        "demo_args": ["--demo"],
        "description": "Haplotype phasing (WhatsHap, SHAPEIT, Eagle)",
        "allowed_extra_flags": {"--method"},
        "saves_h5ad": False,
    },
    # -----------------------------------------------------------------------
    # Proteomics domain
    # -----------------------------------------------------------------------
    "proteomics-ms-qc": {
        "domain": "proteomics",
        "alias": "proteomics-ms-qc",
        "legacy_aliases": ["ms-qc"],
        "script": SKILLS_DIR / "proteomics" / "proteomics-ms-qc" / "proteomics_ms_qc.py",
        "demo_args": ["--demo"],
        "description": "Mass spectrometry raw data quality control (PTXQC, rawTools, MSstatsQC)",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    "proteomics-identification": {
        "domain": "proteomics",
        "alias": "proteomics-identification",
        "legacy_aliases": ["peptide-id"],
        "script": SKILLS_DIR / "proteomics" / "proteomics-identification" / "proteomics_identification.py",
        "demo_args": ["--demo"],
        "description": "Database search for peptide/protein identification (MaxQuant, MS-GF+, Comet, Mascot)",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    "proteomics-quantification": {
        "domain": "proteomics",
        "alias": "proteomics-quantification",
        "legacy_aliases": ["quantification"],
        "script": SKILLS_DIR / "proteomics" / "proteomics-quantification" / "proteomics_quantification.py",
        "demo_args": ["--demo"],
        "description": "Protein/peptide quantification — LFQ, TMT, DIA (MaxQuant LFQ, DIA-NN, Spectronaut, Skyline)",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    "proteomics-de": {
        "domain": "proteomics",
        "alias": "proteomics-de",
        "legacy_aliases": ["differential-abundance"],
        "script": SKILLS_DIR / "proteomics" / "proteomics-de" / "proteomics_de.py",
        "demo_args": ["--demo"],
        "description": "Differential abundance testing (MSstats, limma, t-test)",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    "proteomics-ptm": {
        "domain": "proteomics",
        "alias": "proteomics-ptm",
        "legacy_aliases": ["ptm"],
        "script": SKILLS_DIR / "proteomics" / "proteomics-ptm" / "proteomics_ptm.py",
        "demo_args": ["--demo"],
        "description": "Post-translational modification site localization and scoring (ptmRS, PhosphoRS)",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    "proteomics-enrichment": {
        "domain": "proteomics",
        "alias": "proteomics-enrichment",
        "legacy_aliases": ["prot-enrichment"],
        "script": SKILLS_DIR / "proteomics" / "proteomics-enrichment" / "prot_enrichment.py",
        "demo_args": ["--demo"],
        "description": "Pathway and functional enrichment analysis (STRING, DAVID, g:Profiler, Perseus)",
        "allowed_extra_flags": {"--method", "--species"},
        "saves_h5ad": False,
    },
    "proteomics-structural": {
        "domain": "proteomics",
        "alias": "proteomics-structural",
        "legacy_aliases": ["struct-proteomics"],
        "script": SKILLS_DIR / "proteomics" / "proteomics-structural" / "struct_proteomics.py",
        "demo_args": ["--demo"],
        "description": "Structural proteomics and cross-linking MS analysis (XlinkX, pLink, xiSEARCH)",
        "allowed_extra_flags": {"--method"},
        "saves_h5ad": False,
    },
    "proteomics-data-import": {
        "domain": "proteomics",
        "alias": "proteomics-data-import",
        "legacy_aliases": ["data-import"],
        "script": SKILLS_DIR / "proteomics" / "proteomics-data-import" / "proteomics_data_import.py",
        "demo_args": ["--demo"],
        "description": "Import and convert proteomics data formats",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    # -----------------------------------------------------------------------
    # Metabolomics domain
    # -----------------------------------------------------------------------
    "metabolomics-xcms-preprocessing": {
        "domain": "metabolomics",
        "alias": "metabolomics-xcms-preprocessing",
        "legacy_aliases": ["xcms-preprocess"],
        "script": SKILLS_DIR / "metabolomics" / "metabolomics-xcms-preprocessing" / "metabolomics_xcms_preprocessing.py",
        "demo_args": ["--demo"],
        "description": "LC-MS/GC-MS raw data QC and XCMS preprocessing",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    "metabolomics-peak-detection": {
        "domain": "metabolomics",
        "alias": "metabolomics-peak-detection",
        "legacy_aliases": ["peak-detect"],
        "script": SKILLS_DIR / "metabolomics" / "metabolomics-peak-detection" / "peak_detect.py",
        "demo_args": ["--demo"],
        "description": "Peak picking, feature detection, alignment and grouping (XCMS, MZmine 3, MS-DIAL)",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    "metabolomics-annotation": {
        "domain": "metabolomics",
        "alias": "metabolomics-annotation",
        "legacy_aliases": ["met-annotate"],
        "script": SKILLS_DIR / "metabolomics" / "metabolomics-annotation" / "metabolomics_annotation.py",
        "demo_args": ["--demo"],
        "description": "Metabolite annotation and structural identification (SIRIUS, CSI:FingerID, GNPS, MetFrag)",
        "allowed_extra_flags": {"--method"},
        "saves_h5ad": False,
    },
    "metabolomics-quantification": {
        "domain": "metabolomics",
        "alias": "metabolomics-quantification",
        "legacy_aliases": ["met-quantify"],
        "script": SKILLS_DIR / "metabolomics" / "metabolomics-quantification" / "met_quantify.py",
        "demo_args": ["--demo"],
        "description": "Feature quantification, missing value imputation, and normalization (NOREVA)",
        "allowed_extra_flags": {"--impute", "--normalize"},
        "saves_h5ad": False,
    },
    "metabolomics-normalization": {
        "domain": "metabolomics",
        "alias": "metabolomics-normalization",
        "legacy_aliases": ["met-normalize"],
        "script": SKILLS_DIR / "metabolomics" / "metabolomics-normalization" / "metabolomics_normalization.py",
        "demo_args": ["--demo"],
        "description": "Data normalization, scaling, and transformation",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    "metabolomics-de": {
        "domain": "metabolomics",
        "alias": "metabolomics-de",
        "legacy_aliases": ["met-diff"],
        "script": SKILLS_DIR / "metabolomics" / "metabolomics-de" / "met_diff.py",
        "demo_args": ["--demo"],
        "description": "Differential metabolite abundance — PCA, PLS-DA, univariate statistics (MetaboAnalystR, ropls)",
        "allowed_extra_flags": {"--group-a-prefix", "--group-b-prefix"},
        "saves_h5ad": False,
    },
    "metabolomics-pathway-enrichment": {
        "domain": "metabolomics",
        "alias": "metabolomics-pathway-enrichment",
        "legacy_aliases": ["met-pathway"],
        "script": SKILLS_DIR / "metabolomics" / "metabolomics-pathway-enrichment" / "met_pathway.py",
        "demo_args": ["--demo"],
        "description": "Metabolic pathway enrichment and mapping (mummichog, FELLA, MetaboAnalyst)",
        "allowed_extra_flags": {"--method"},
        "saves_h5ad": False,
    },
    "metabolomics-statistics": {
        "domain": "metabolomics",
        "alias": "metabolomics-statistics",
        "legacy_aliases": ["met-stat"],
        "script": SKILLS_DIR / "metabolomics" / "metabolomics-statistics" / "metabolomics_statistics.py",
        "demo_args": ["--demo"],
        "description": "Statistical analysis — PCA, PLS-DA, clustering, univariate tests",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    # -----------------------------------------------------------------------
    # Bulk RNA-seq domain
    # -----------------------------------------------------------------------
    "bulkrna-qc": {
        "domain": "bulkrna",
        "alias": "bulkrna-qc",
        "legacy_aliases": ["bulk-align"],
        "script": SKILLS_DIR / "bulkrna" / "bulkrna-qc" / "bulkrna_qc.py",
        "demo_args": ["--demo"],
        "description": "Count matrix QC — library size, gene detection rates, sample correlation, outlier detection",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    "bulkrna-de": {
        "domain": "bulkrna",
        "alias": "bulkrna-de",
        "legacy_aliases": ["bulk-de"],
        "script": SKILLS_DIR / "bulkrna" / "bulkrna-de" / "bulkrna_de.py",
        "demo_args": ["--demo"],
        "description": "Differential expression (PyDESeq2, t-test fallback)",
        "allowed_extra_flags": {
            "--method", "--control-prefix", "--treat-prefix",
            "--padj-cutoff", "--lfc-cutoff",
        },
        "saves_h5ad": False,
    },
    "bulkrna-splicing": {
        "domain": "bulkrna",
        "alias": "bulkrna-splicing",
        "legacy_aliases": ["bulk-splicing"],
        "script": SKILLS_DIR / "bulkrna" / "bulkrna-splicing" / "bulkrna_splicing.py",
        "demo_args": ["--demo"],
        "description": "Alternative splicing analysis — PSI quantification, rMATS/SUPPA2 output parsing",
        "allowed_extra_flags": {"--dpsi-cutoff", "--padj-cutoff"},
        "saves_h5ad": False,
    },
    "bulkrna-enrichment": {
        "domain": "bulkrna",
        "alias": "bulkrna-enrichment",
        "legacy_aliases": ["bulk-enrichment"],
        "script": SKILLS_DIR / "bulkrna" / "bulkrna-enrichment" / "bulkrna_enrichment.py",
        "demo_args": ["--demo"],
        "description": "Pathway enrichment — ORA/GSEA via GSEApy with hypergeometric fallback",
        "allowed_extra_flags": {
            "--method", "--padj-cutoff", "--lfc-cutoff", "--gene-set-file",
        },
        "saves_h5ad": False,
    },
    "bulkrna-deconvolution": {
        "domain": "bulkrna",
        "alias": "bulkrna-deconvolution",
        "legacy_aliases": ["bulk-deconv"],
        "script": SKILLS_DIR / "bulkrna" / "bulkrna-deconvolution" / "bulkrna_deconvolution.py",
        "demo_args": ["--demo"],
        "description": "Cell type deconvolution via NNLS (built-in), optional CIBERSORTx/MuSiC bridges",
        "allowed_extra_flags": {"--reference"},
        "saves_h5ad": False,
    },
    "bulkrna-coexpression": {
        "domain": "bulkrna",
        "alias": "bulkrna-coexpression",
        "legacy_aliases": ["bulk-wgcna"],
        "script": SKILLS_DIR / "bulkrna" / "bulkrna-coexpression" / "bulkrna_coexpression.py",
        "demo_args": ["--demo"],
        "description": "WGCNA-style co-expression network — module detection, soft thresholding, hub genes",
        "allowed_extra_flags": {"--power", "--min-module-size"},
        "saves_h5ad": False,
    },
    "bulkrna-batch-correction": {
        "domain": "bulkrna",
        "alias": "bulkrna-batch-correction",
        "legacy_aliases": ["bulk-combat"],
        "script": SKILLS_DIR / "bulkrna" / "bulkrna-batch-correction" / "bulkrna_batch_correction.py",
        "demo_args": ["--demo"],
        "description": "Batch effect correction using ComBat — parametric/non-parametric, PCA visualization",
        "allowed_extra_flags": {"--batch-info", "--mode"},
        "saves_h5ad": False,
    },
    "bulkrna-geneid-mapping": {
        "domain": "bulkrna",
        "alias": "bulkrna-geneid-mapping",
        "legacy_aliases": ["bulk-geneid"],
        "script": SKILLS_DIR / "bulkrna" / "bulkrna-geneid-mapping" / "bulkrna_geneid_mapping.py",
        "demo_args": ["--demo"],
        "description": "Gene ID conversion — Ensembl, Entrez, HGNC symbol mapping with duplicate resolution",
        "allowed_extra_flags": {"--from", "--to", "--species", "--on-duplicate", "--mapping-file"},
        "saves_h5ad": False,
    },
    "bulkrna-ppi-network": {
        "domain": "bulkrna",
        "alias": "bulkrna-ppi-network",
        "legacy_aliases": ["bulk-ppi"],
        "script": SKILLS_DIR / "bulkrna" / "bulkrna-ppi-network" / "bulkrna_ppi_network.py",
        "demo_args": ["--demo"],
        "description": "PPI network analysis — STRING API query, graph centrality, hub gene identification",
        "allowed_extra_flags": {"--species", "--score-threshold", "--top-n"},
        "saves_h5ad": False,
    },
    "bulkrna-survival": {
        "domain": "bulkrna",
        "alias": "bulkrna-survival",
        "legacy_aliases": ["bulk-survival"],
        "script": SKILLS_DIR / "bulkrna" / "bulkrna-survival" / "bulkrna_survival.py",
        "demo_args": ["--demo"],
        "description": "Survival analysis — Kaplan-Meier, log-rank test, Cox proportional hazards",
        "allowed_extra_flags": {"--clinical", "--genes", "--cutoff-method"},
        "saves_h5ad": False,
    },
    "bulkrna-read-qc": {
        "domain": "bulkrna",
        "alias": "bulkrna-read-qc",
        "legacy_aliases": ["bulk-fastqc"],
        "script": SKILLS_DIR / "bulkrna" / "bulkrna-read-qc" / "bulkrna_read_qc.py",
        "demo_args": ["--demo"],
        "description": "FASTQ quality assessment — Phred scores, GC content, adapter detection, read length",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    "bulkrna-read-alignment": {
        "domain": "bulkrna",
        "alias": "bulkrna-read-alignment",
        "legacy_aliases": ["bulk-align-reads"],
        "script": SKILLS_DIR / "bulkrna" / "bulkrna-read-alignment" / "bulkrna_read_alignment.py",
        "demo_args": ["--demo"],
        "description": "RNA-seq read alignment/quantification — STAR, HISAT2, Salmon statistics and QC",
        "allowed_extra_flags": {"--method", "--species"},
        "saves_h5ad": False,
    },
    "bulkrna-trajblend": {
        "domain": "bulkrna",
        "alias": "bulkrna-trajblend",
        "legacy_aliases": ["bulk-trajblend"],
        "script": SKILLS_DIR / "bulkrna" / "bulkrna-trajblend" / "bulkrna_trajblend.py",
        "demo_args": ["--demo"],
        "description": "Bulk→single-cell trajectory interpolation (BulkTrajBlend-style VAE + GNN)",
        "allowed_extra_flags": {"--reference", "--n-epochs"},
        "saves_h5ad": False,
    },
}

# Instantiate the global registry
registry = OmicsRegistry()
