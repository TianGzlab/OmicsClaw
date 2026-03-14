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
        # Initialize with baseline pre-defined skills
        self.skills = _HARDCODED_SKILLS.copy()
        self.domains = _HARDCODED_DOMAINS.copy()
        self._loaded = False
        self.lazy_skills = {}

    def load_all(self, skills_dir: Path | None = None) -> None:
        """Dynamically load and merge skills from the filesystem."""
        if self._loaded:
            return
            
        target_dir = skills_dir or SKILLS_DIR
        if not target_dir.exists():
            return
            
        # Scan domain directories
        for domain_path in target_dir.iterdir():
            if not domain_path.is_dir() or domain_path.name.startswith(('.', '__')):
                continue
                
            domain_name = domain_path.name
            
            # Scan skill directories within the domain
            for skill_path in domain_path.iterdir():
                if not skill_path.is_dir() or skill_path.name.startswith(('.', '__')):
                    continue
                    
                skill_dir_name = skill_path.name
                
                # Check for catalog.json or registry.json logic could go here
                # Check for python execution script
                # Convention: script matches dir name with underscores instead of dashes
                script_name = f"{skill_dir_name.replace('-', '_')}.py"
                script_path_candidate = skill_path / script_name
                
                # For backward compatibility, check if already in hardcoded skills
                # Some hardcoded aliases differ from dir name, so we check path
                already_registered = any(
                    s.get("script") == script_path_candidate for s in self.skills.values()
                )
                
                if script_path_candidate.exists() and not already_registered:
                    # Dynamically register the found skill
                    alias = skill_dir_name
                    # Make sure no clash
                    if alias not in self.skills:
                        self.skills[alias] = {
                            "domain": domain_name,
                            "alias": alias,
                            "script": script_path_candidate,
                            "demo_args": ["--demo"],
                            "description": f"Dynamically loaded {alias} skill",
                            "allowed_extra_flags": set(),  # Strict default
                            "saves_h5ad": False,
                        }
                        logger.debug(f"Dynamically discovered skill: {alias}")

        self._loaded = True

    def load_lightweight(self, skills_dir: Path | None = None) -> None:
        """Load only basic skill metadata for fast startup."""
        target_dir = skills_dir or SKILLS_DIR
        if not target_dir.exists():
            return

        for domain_path in target_dir.iterdir():
            if not domain_path.is_dir() or domain_path.name.startswith(('.', '__')):
                continue

            for skill_path in domain_path.iterdir():
                if not skill_path.is_dir() or skill_path.name.startswith(('.', '__')):
                    continue

                skill_md = skill_path / "SKILL.md"
                if not skill_md.exists():
                    continue

                lazy = LazySkillMetadata(skill_path)
                skill_key = skill_path.name
                self.lazy_skills[skill_key] = lazy





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
        "skill_count": 9,
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
    "orchestrator": {
        "name": "Orchestrator",
        "primary_data_types": ["*"],
        "skill_count": 1,
    },
}


_HARDCODED_SKILLS: dict[str, dict[str, Any]] = {
    "preprocess": {
        "domain": "spatial",
        "alias": "preprocess",
        "script": SKILLS_DIR / "spatial" / "preprocess" / "spatial_preprocess.py",
        "demo_args": ["--demo"],
        "description": "Spatial data QC, normalization, HVG, PCA/UMAP, Leiden clustering",
        "allowed_extra_flags": {
            "--data-type", "--min-genes", "--min-cells", "--max-mt-pct",
            "--n-top-hvg", "--n-pcs", "--n-neighbors", "--leiden-resolution",
            "--species",
        },
        "saves_h5ad": True,
    },
    "domains": {
        "domain": "spatial",
        "alias": "domains",
        "script": SKILLS_DIR / "spatial" / "domains" / "spatial_domains.py",
        "demo_args": ["--demo"],
        "description": "Tissue region/niche identification (Leiden, Louvain, SpaGCN, STAGATE, GraphST, BANKSY)",
        "allowed_extra_flags": {
            "--method", "--n-domains", "--resolution",
            "--spatial-weight", "--rad-cutoff", "--lambda-param", "--refine",
        },
        "saves_h5ad": True,
    },
    "annotate": {
        "domain": "spatial",
        "alias": "annotate",
        "script": SKILLS_DIR / "spatial" / "annotate" / "spatial_annotate.py",
        "demo_args": ["--demo"],
        "description": "Cell type annotation (marker_based, Tangram, scANVI, CellAssign)",
        "allowed_extra_flags": {
            "--method", "--reference", "--cell-type-key",
            "--cluster-key", "--species", "--model",
        },
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "deconv": {
        "domain": "spatial",
        "alias": "deconv",
        "script": SKILLS_DIR / "spatial" / "deconv" / "spatial_deconv.py",
        "demo_args": ["--demo"],
        "description": "Deconvolution — cell type proportions (NNLS, Cell2Location, RCTD, Tangram, CARD)",
        "allowed_extra_flags": {"--method", "--reference", "--cell-type-key", "--n-epochs"},
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "statistics": {
        "domain": "spatial",
        "alias": "statistics",
        "script": SKILLS_DIR / "spatial" / "statistics" / "spatial_statistics.py",
        "demo_args": ["--demo"],
        "description": "Spatial statistics (Moran's I, Geary's C, Getis-Ord Gi*, Ripley, neighborhood enrichment, network properties)",
        "allowed_extra_flags": {
            "--analysis-type", "--cluster-key", "--genes", "--n-top-genes",
        },
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "genes": {
        "domain": "spatial",
        "alias": "genes",
        "script": SKILLS_DIR / "spatial" / "genes" / "spatial_genes.py",
        "demo_args": ["--demo"],
        "description": "Spatially variable genes (Moran's I, SpatialDE, SPARK-X, FlashS)",
        "allowed_extra_flags": {"--method", "--n-top-genes", "--fdr-threshold"},
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "de": {
        "domain": "spatial",
        "alias": "de",
        "script": SKILLS_DIR / "spatial" / "de" / "spatial_de.py",
        "demo_args": ["--demo"],
        "description": "Differential expression (Wilcoxon, t-test, PyDESeq2 pseudobulk)",
        "allowed_extra_flags": {
            "--groupby", "--group1", "--group2", "--method", "--n-top-genes",
        },
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "condition": {
        "domain": "spatial",
        "alias": "condition",
        "script": SKILLS_DIR / "spatial" / "condition" / "spatial_condition.py",
        "demo_args": ["--demo"],
        "description": "Condition comparison with pseudobulk DESeq2 statistics",
        "allowed_extra_flags": {
            "--condition-key", "--sample-key", "--reference-condition",
        },
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "communication": {
        "domain": "spatial",
        "alias": "communication",
        "script": SKILLS_DIR / "spatial" / "communication" / "spatial_communication.py",
        "demo_args": ["--demo"],
        "description": "Cell-cell communication (LIANA+, CellPhoneDB, FastCCC)",
        "allowed_extra_flags": {"--method", "--species", "--cell-type-key"},
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "velocity": {
        "domain": "spatial",
        "alias": "velocity",
        "script": SKILLS_DIR / "spatial" / "velocity" / "spatial_velocity.py",
        "demo_args": ["--demo"],
        "description": "RNA velocity and cellular dynamics (scVelo, VeloVI)",
        "allowed_extra_flags": {"--method", "--mode"},
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "trajectory": {
        "domain": "spatial",
        "alias": "trajectory",
        "script": SKILLS_DIR / "spatial" / "trajectory" / "spatial_trajectory.py",
        "demo_args": ["--demo"],
        "description": "Trajectory inference (CellRank, Palantir, DPT)",
        "allowed_extra_flags": {"--method", "--root-cell", "--n-states"},
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "enrichment": {
        "domain": "spatial",
        "alias": "enrichment",
        "script": SKILLS_DIR / "spatial" / "enrichment" / "spatial_enrichment.py",
        "demo_args": ["--demo"],
        "description": "Pathway enrichment (GSEA, ORA, Enrichr, ssGSEA)",
        "allowed_extra_flags": {"--method", "--gene-set", "--species", "--source"},
        "requires_preprocessed": True,
    },
    "cnv": {
        "domain": "spatial",
        "alias": "cnv",
        "script": SKILLS_DIR / "spatial" / "cnv" / "spatial_cnv.py",
        "demo_args": ["--demo"],
        "description": "Copy number variation inference (inferCNVpy, Numbat)",
        "allowed_extra_flags": {"--method", "--reference-key"},
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "integrate": {
        "domain": "spatial",
        "alias": "integrate",
        "script": SKILLS_DIR / "spatial" / "integrate" / "spatial_integrate.py",
        "demo_args": ["--demo"],
        "description": "Multi-sample integration (Harmony, BBKNN, Scanorama, scVI)",
        "allowed_extra_flags": {"--method", "--batch-key"},
        "saves_h5ad": True,
    },
    "register": {
        "domain": "spatial",
        "alias": "register",
        "script": SKILLS_DIR / "spatial" / "register" / "spatial_register.py",
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
        "description": "Multi-omics query routing across all domains (spatial, single-cell, genomics, proteomics, metabolomics)",
        "allowed_extra_flags": {
            "--query", "--pipeline", "--list-skills",
        },
    },
    # -----------------------------------------------------------------------
    # Single-cell domain
    # -----------------------------------------------------------------------
    "sc-preprocess": {
        "domain": "singlecell",
        "alias": "sc-preprocess",
        "script": SKILLS_DIR / "singlecell" / "preprocessing" / "sc_preprocess.py",
        "demo_args": ["--demo"],
        "description": "scRNA-seq QC, normalization, HVG, PCA/UMAP, Leiden clustering (Scanpy, Seurat, Pegasus)",
        "allowed_extra_flags": {
            "--min-genes", "--min-cells", "--max-mt-pct",
            "--n-top-hvg", "--n-pcs", "--n-neighbors", "--leiden-resolution",
        },
        "saves_h5ad": True,
    },
    "sc-doublet": {
        "domain": "singlecell",
        "alias": "sc-doublet",
        "script": SKILLS_DIR / "singlecell" / "doublet-detection" / "sc_doublet.py",
        "demo_args": ["--demo"],
        "description": "Doublet detection and removal (Scrublet, scDblFinder, DoubletFinder)",
        "allowed_extra_flags": {"--expected-doublet-rate", "--threshold"},
        "saves_h5ad": True,
    },
    "sc-annotate": {
        "domain": "singlecell",
        "alias": "sc-annotate",
        "script": SKILLS_DIR / "singlecell" / "annotation" / "sc_annotate.py",
        "demo_args": ["--demo"],
        "description": "Cell type annotation (CellTypist, SingleR, scmap, GARNET, scANVI)",
        "allowed_extra_flags": {"--method", "--reference", "--species"},
        "saves_h5ad": True,
    },
    "sc-trajectory": {
        "domain": "singlecell",
        "alias": "sc-trajectory",
        "script": SKILLS_DIR / "singlecell" / "trajectory" / "sc_trajectory.py",
        "demo_args": ["--demo"],
        "description": "Trajectory inference and pseudotime (Monocle3, Slingshot, CellRank, scVelo)",
        "allowed_extra_flags": {"--method", "--root-cluster"},
        "saves_h5ad": True,
    },
    "sc-integrate": {
        "domain": "singlecell",
        "alias": "sc-integrate",
        "script": SKILLS_DIR / "singlecell" / "batch-integration" / "sc_integrate.py",
        "demo_args": ["--demo"],
        "description": "Multi-sample integration and batch correction (Harmony, scVI, BBKNN, Seurat CCA/RPCA)",
        "allowed_extra_flags": {"--method", "--batch-key"},
        "saves_h5ad": True,
    },
    "sc-de": {
        "domain": "singlecell",
        "alias": "sc-de",
        "script": SKILLS_DIR / "singlecell" / "de" / "sc_de.py",
        "demo_args": ["--demo"],
        "description": "Differential expression analysis (Wilcoxon, MAST, pseudobulk PyDESeq2)",
        "allowed_extra_flags": {
            "--groupby", "--group1", "--group2", "--method", "--n-top-genes",
        },
        "requires_preprocessed": True,
        "saves_h5ad": True,
    },
    "sc-grn": {
        "domain": "singlecell",
        "alias": "sc-grn",
        "script": SKILLS_DIR / "singlecell" / "grn" / "sc_grn.py",
        "demo_args": ["--demo"],
        "description": "Gene regulatory network inference (pySCENIC, CellOracle)",
        "allowed_extra_flags": {"--method", "--n-top-targets"},
        "requires_preprocessed": True,
        "saves_h5ad": False,
    },
    "sc-communication": {
        "domain": "singlecell",
        "alias": "sc-communication",
        "script": SKILLS_DIR / "singlecell" / "communication" / "sc_communication.py",
        "demo_args": ["--demo"],
        "description": "Cell-cell communication (CellPhoneDB, LIANA+, NicheNet)",
        "allowed_extra_flags": {"--method", "--species", "--cell-type-key", "--n-perms"},
        "requires_preprocessed": True,
        "saves_h5ad": False,
    },
    "sc-multiome": {
        "domain": "singlecell",
        "alias": "sc-multiome",
        "script": SKILLS_DIR / "singlecell" / "multiome" / "sc_multiome.py",
        "demo_args": ["--demo"],
        "description": "Paired multi-omics integration — scRNA+scATAC, CITE-seq (WNN, MOFA+, scVI-tools)",
        "allowed_extra_flags": {"--method"},
        "saves_h5ad": True,
    },
    # -----------------------------------------------------------------------
    # Genomics domain
    # -----------------------------------------------------------------------
    "genomics-qc": {
        "domain": "genomics",
        "alias": "genomics-qc",
        "script": SKILLS_DIR / "genomics" / "qc" / "genomics_qc.py",
        "demo_args": ["--demo"],
        "description": "Sequencing reads QC and adapter trimming (FastQC, MultiQC, fastp, Trimmomatic)",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    "align": {
        "domain": "genomics",
        "alias": "align",
        "script": SKILLS_DIR / "genomics" / "alignment" / "alignment.py",
        "demo_args": ["--demo"],
        "description": "Short/long read alignment to reference genome (BWA-MEM, Bowtie2, Minimap2)",
        "allowed_extra_flags": {"--method"},
        "saves_h5ad": False,
    },
    "variant-call": {
        "domain": "genomics",
        "alias": "variant-call",
        "script": SKILLS_DIR / "genomics" / "variant-calling" / "variant_calling.py",
        "demo_args": ["--demo"],
        "description": "Germline/somatic variant calling — SNVs, Indels (GATK, DeepVariant, FreeBayes)",
        "allowed_extra_flags": {"--method"},
        "saves_h5ad": False,
    },
    "sv-detect": {
        "domain": "genomics",
        "alias": "sv-detect",
        "script": SKILLS_DIR / "genomics" / "structural-variants" / "sv_detection.py",
        "demo_args": ["--demo"],
        "description": "Structural variant calling (Manta, Lumpy, Delly, Sniffles)",
        "allowed_extra_flags": {"--method"},
        "saves_h5ad": False,
    },
    "cnv-calling": {
        "domain": "genomics",
        "alias": "cnv-calling",
        "script": SKILLS_DIR / "genomics" / "cnv-calling" / "cnv_calling.py",
        "demo_args": ["--demo"],
        "description": "Copy number variation analysis (CNVkit, Control-FREEC, GATK gCNV)",
        "allowed_extra_flags": {"--method"},
        "saves_h5ad": False,
    },
    "vcf-ops": {
        "domain": "genomics",
        "alias": "vcf-ops",
        "script": SKILLS_DIR / "genomics" / "vcf-operations" / "vcf_operations.py",
        "demo_args": ["--demo"],
        "description": "VCF manipulation, filtering, and merging (bcftools, GATK SelectVariants)",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    "variant-annotate": {
        "domain": "genomics",
        "alias": "variant-annotate",
        "script": SKILLS_DIR / "genomics" / "annotation" / "variant_annotation.py",
        "demo_args": ["--demo"],
        "description": "Variant annotation and functional effect prediction (VEP, snpEff, ANNOVAR)",
        "allowed_extra_flags": {"--method"},
        "saves_h5ad": False,
    },
    "assemble": {
        "domain": "genomics",
        "alias": "assemble",
        "script": SKILLS_DIR / "genomics" / "assembly" / "genome_assembly.py",
        "demo_args": ["--demo"],
        "description": "De novo genome assembly (SPAdes, Megahit, Flye, Canu)",
        "allowed_extra_flags": {"--method"},
        "saves_h5ad": False,
    },
    "epigenomics": {
        "domain": "genomics",
        "alias": "epigenomics",
        "script": SKILLS_DIR / "genomics" / "epigenomics" / "epigenomics.py",
        "demo_args": ["--demo"],
        "description": "ChIP-seq/ATAC-seq peak calling and motif analysis (MACS2, Homer, pyGenomeTracks)",
        "allowed_extra_flags": {"--method", "--assay"},
        "saves_h5ad": False,
    },
    "phase": {
        "domain": "genomics",
        "alias": "phase",
        "script": SKILLS_DIR / "genomics" / "phasing" / "phasing.py",
        "demo_args": ["--demo"],
        "description": "Haplotype phasing (WhatsHap, SHAPEIT, Eagle)",
        "allowed_extra_flags": {"--method"},
        "saves_h5ad": False,
    },
    # -----------------------------------------------------------------------
    # Proteomics domain
    # -----------------------------------------------------------------------
    "ms-qc": {
        "domain": "proteomics",
        "alias": "ms-qc",
        "script": SKILLS_DIR / "proteomics" / "ms-qc" / "ms_qc.py",
        "demo_args": ["--demo"],
        "description": "Mass spectrometry raw data quality control (PTXQC, rawTools, MSstatsQC)",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    "peptide-id": {
        "domain": "proteomics",
        "alias": "peptide-id",
        "script": SKILLS_DIR / "proteomics" / "peptide-id" / "peptide_id.py",
        "demo_args": ["--demo"],
        "description": "Database search for peptide/protein identification (MaxQuant, MS-GF+, Comet, Mascot)",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    "quantification": {
        "domain": "proteomics",
        "alias": "quantification",
        "script": SKILLS_DIR / "proteomics" / "quantification" / "quantification.py",
        "demo_args": ["--demo"],
        "description": "Protein/peptide quantification — LFQ, TMT, DIA (MaxQuant LFQ, DIA-NN, Spectronaut, Skyline)",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    "differential-abundance": {
        "domain": "proteomics",
        "alias": "differential-abundance",
        "script": SKILLS_DIR / "proteomics" / "differential-abundance" / "differential_abundance.py",
        "demo_args": ["--demo"],
        "description": "Differential abundance testing (MSstats, limma, t-test)",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    "ptm": {
        "domain": "proteomics",
        "alias": "ptm",
        "script": SKILLS_DIR / "proteomics" / "ptm" / "ptm.py",
        "demo_args": ["--demo"],
        "description": "Post-translational modification site localization and scoring (ptmRS, PhosphoRS)",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    "prot-enrichment": {
        "domain": "proteomics",
        "alias": "prot-enrichment",
        "script": SKILLS_DIR / "proteomics" / "enrichment" / "prot_enrichment.py",
        "demo_args": ["--demo"],
        "description": "Pathway and functional enrichment analysis (STRING, DAVID, g:Profiler, Perseus)",
        "allowed_extra_flags": {"--method", "--species"},
        "saves_h5ad": False,
    },
    "struct-proteomics": {
        "domain": "proteomics",
        "alias": "struct-proteomics",
        "script": SKILLS_DIR / "proteomics" / "struct" / "struct_proteomics.py",
        "demo_args": ["--demo"],
        "description": "Structural proteomics and cross-linking MS analysis (XlinkX, pLink, xiSEARCH)",
        "allowed_extra_flags": {"--method"},
        "saves_h5ad": False,
    },
    "data-import": {
        "domain": "proteomics",
        "alias": "data-import",
        "script": SKILLS_DIR / "proteomics" / "data-import" / "data_import.py",
        "demo_args": ["--demo"],
        "description": "Import and convert proteomics data formats",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    # -----------------------------------------------------------------------
    # Metabolomics domain
    # -----------------------------------------------------------------------
    "xcms-preprocess": {
        "domain": "metabolomics",
        "alias": "xcms-preprocess",
        "script": SKILLS_DIR / "metabolomics" / "xcms-preprocess" / "xcms_preprocess.py",
        "demo_args": ["--demo"],
        "description": "LC-MS/GC-MS raw data QC and XCMS preprocessing",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    "peak-detect": {
        "domain": "metabolomics",
        "alias": "peak-detect",
        "script": SKILLS_DIR / "metabolomics" / "peak-detection" / "peak_detect.py",
        "demo_args": ["--demo"],
        "description": "Peak picking, feature detection, alignment and grouping (XCMS, MZmine 3, MS-DIAL)",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    "met-annotate": {
        "domain": "metabolomics",
        "alias": "met-annotate",
        "script": SKILLS_DIR / "metabolomics" / "annotation" / "annotation.py",
        "demo_args": ["--demo"],
        "description": "Metabolite annotation and structural identification (SIRIUS, CSI:FingerID, GNPS, MetFrag)",
        "allowed_extra_flags": {"--method"},
        "saves_h5ad": False,
    },
    "met-quantify": {
        "domain": "metabolomics",
        "alias": "met-quantify",
        "script": SKILLS_DIR / "metabolomics" / "quantify" / "met_quantify.py",
        "demo_args": ["--demo"],
        "description": "Feature quantification, missing value imputation, and normalization (NOREVA)",
        "allowed_extra_flags": {"--impute", "--normalize"},
        "saves_h5ad": False,
    },
    "met-normalize": {
        "domain": "metabolomics",
        "alias": "met-normalize",
        "script": SKILLS_DIR / "metabolomics" / "normalization" / "normalization.py",
        "demo_args": ["--demo"],
        "description": "Data normalization, scaling, and transformation",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
    "met-diff": {
        "domain": "metabolomics",
        "alias": "met-diff",
        "script": SKILLS_DIR / "metabolomics" / "diff" / "met_diff.py",
        "demo_args": ["--demo"],
        "description": "Differential metabolite abundance — PCA, PLS-DA, univariate statistics (MetaboAnalystR, ropls)",
        "allowed_extra_flags": {"--group-a-prefix", "--group-b-prefix"},
        "saves_h5ad": False,
    },
    "met-pathway": {
        "domain": "metabolomics",
        "alias": "met-pathway",
        "script": SKILLS_DIR / "metabolomics" / "pathway" / "met_pathway.py",
        "demo_args": ["--demo"],
        "description": "Metabolic pathway enrichment and mapping (mummichog, FELLA, MetaboAnalyst)",
        "allowed_extra_flags": {"--method"},
        "saves_h5ad": False,
    },
    "met-stat": {
        "domain": "metabolomics",
        "alias": "met-stat",
        "script": SKILLS_DIR / "metabolomics" / "statistical-analysis" / "statistical_analysis.py",
        "demo_args": ["--demo"],
        "description": "Statistical analysis — PCA, PLS-DA, clustering, univariate tests",
        "allowed_extra_flags": set(),
        "saves_h5ad": False,
    },
}

# Instantiate the global registry
registry = OmicsRegistry()
