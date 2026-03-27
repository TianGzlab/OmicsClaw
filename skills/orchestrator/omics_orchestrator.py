#!/usr/bin/env python3
"""Multi-Domain Omics Orchestrator — query routing across all omics domains.

Routes queries and files to the correct skill across spatial, single-cell,
genomics, proteomics, metabolomics, and bulk RNA-seq domains.

Usage:
    python omics_orchestrator.py --query "find spatially variable genes" --output <dir>
    python omics_orchestrator.py --input <data.h5ad> --output <dir>
    python omics_orchestrator.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.loaders import EXTENSION_TO_DOMAIN
from omicsclaw.routing.router import route_keyword, route_query_unified
from omicsclaw.core.registry import registry

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain detection — hardcoded maps serve as fallback for SKILL.md keywords
# ---------------------------------------------------------------------------

_FALLBACK_KEYWORD_MAPS = {
    "spatial": {
        "spatial domain": "spatial-domain-identification",
        "tissue region": "spatial-domain-identification",
        "spatially variable": "spatial-svg-detection",
        "spatial statistics": "spatial-statistics",
        "moran": "spatial-statistics",
        "cell type annotation": "spatial-cell-annotation",
        "deconvolution": "spatial-deconvolution",
        "cell communication": "spatial-cell-communication",
        "ligand receptor": "spatial-cell-communication",
        "rna velocity": "spatial-velocity",
        "trajectory": "spatial-trajectory",
        "pseudotime": "spatial-trajectory",
        "pathway enrichment": "spatial-enrichment",
        "cnv": "spatial-cnv",
        "copy number": "spatial-cnv",
        "batch correction": "spatial-integration",
        "integration": "spatial-integration",
        "spatial registration": "spatial-registration",
        "differential expression": "spatial-de",
        "marker genes": "spatial-de",
        "condition comparison": "spatial-condition-comparison",
        "preprocess": "spatial-preprocessing",
        "qc": "spatial-preprocessing",
    },
    "singlecell": {
        "qc metrics": "sc-qc",
        "quality control": "sc-qc",
        "calculate qc": "sc-qc",
        "qc violin": "sc-qc",
        "filter cells": "sc-filter",
        "cell filtering": "sc-filter",
        "gene filtering": "sc-filter",
        "remove low quality": "sc-filter",
        "tissue-specific": "sc-filter",
        "ambient rna": "sc-ambient-removal",
        "ambient removal": "sc-ambient-removal",
        "cellbender": "sc-ambient-removal",
        "background rna": "sc-ambient-removal",
        "single cell": "sc-preprocessing",
        "doublet": "sc-doublet-detection",
        "scrublet": "sc-doublet-detection",
        "trajectory": "sc-pseudotime",
        "pseudotime": "sc-pseudotime",
        "dpt": "sc-pseudotime",
        "paga": "sc-pseudotime",
        "diffusion map": "sc-pseudotime",
        "rna velocity": "sc-velocity",
        "velocity": "sc-velocity",
        "scvelo": "sc-velocity",
        "cell type annotation": "sc-cell-annotation",
        "celltypist": "sc-cell-annotation",
        "integration": "sc-batch-integration",
        "batch correction": "sc-batch-integration",
        "harmony": "sc-batch-integration",
        "scvi": "sc-batch-integration",
        "differential expression": "sc-de",
        "pseudobulk": "sc-de",
        "marker genes": "sc-markers",
        "find markers": "sc-markers",
        "cluster markers": "sc-markers",
        "gene regulatory": "sc-grn",
        "grn": "sc-grn",
        "pyscenic": "sc-grn",
        "grnboost": "sc-grn",
        "cell communication": "sc-cell-communication",
        "ligand receptor": "sc-cell-communication",
        "cellchat": "sc-cell-communication",
    },
    "genomics": {
        "variant call": "genomics-variant-calling",
        "snp": "genomics-variant-calling",
        "structural variant": "genomics-sv-detection",
        "vcf": "genomics-vcf-operations",
        "alignment": "genomics-alignment",
        "read alignment": "genomics-alignment",
        "variant annotation": "genomics-variant-annotation",
        "assembly": "genomics-assembly",
        "genome assembly": "genomics-assembly",
        "phasing": "genomics-phasing",
        "haplotype": "genomics-phasing",
        "cnv": "genomics-cnv-calling",
        "quality control": "genomics-qc",
        "fastq": "genomics-qc",
    },
    "proteomics": {
        "mass spec": "proteomics-ms-qc",
        "ms qc": "proteomics-ms-qc",
        "peptide identification": "proteomics-identification",
        "protein quantification": "proteomics-quantification",
        "differential abundance": "proteomics-de",
        "ptm": "proteomics-ptm",
        "post-translational": "proteomics-ptm",
        "pathway enrichment": "proteomics-enrichment",
        "data import": "proteomics-data-import",
    },
    "metabolomics": {
        "peak detection": "metabolomics-peak-detection",
        "xcms": "metabolomics-xcms-preprocessing",
        "metabolite annotation": "metabolomics-annotation",
        "normalization": "metabolomics-normalization",
        "differential": "metabolomics-de",
        "pathway": "metabolomics-pathway-enrichment",
        "statistical": "metabolomics-statistics",
    },
    "bulkrna": {
        "bulk rna qc": "bulkrna-qc",
        "library size": "bulkrna-qc",
        "gene detection": "bulkrna-qc",
        "count matrix qc": "bulkrna-qc",
        "bulk differential expression": "bulkrna-de",
        "bulk de": "bulkrna-de",
        "deseq2": "bulkrna-de",
        "bulk rna de": "bulkrna-de",
        "differentially expressed genes": "bulkrna-de",
        "alternative splicing": "bulkrna-splicing",
        "splicing analysis": "bulkrna-splicing",
        "psi": "bulkrna-splicing",
        "rmats": "bulkrna-splicing",
        "suppa": "bulkrna-splicing",
        "exon skipping": "bulkrna-splicing",
        "differential splicing": "bulkrna-splicing",
        "bulk enrichment": "bulkrna-enrichment",
        "bulk pathway": "bulkrna-enrichment",
        "gsea": "bulkrna-enrichment",
        "ora": "bulkrna-enrichment",
        "go enrichment": "bulkrna-enrichment",
        "kegg": "bulkrna-enrichment",
        "bulk deconvolution": "bulkrna-deconvolution",
        "cell type proportion": "bulkrna-deconvolution",
        "nnls": "bulkrna-deconvolution",
        "cibersortx": "bulkrna-deconvolution",
        "bulk deconv": "bulkrna-deconvolution",
        "cell fraction": "bulkrna-deconvolution",
        "coexpression": "bulkrna-coexpression",
        "wgcna": "bulkrna-coexpression",
        "gene network": "bulkrna-coexpression",
        "co-expression modules": "bulkrna-coexpression",
        "hub genes": "bulkrna-coexpression",
        "gene modules": "bulkrna-coexpression",
    },
}

_DOMAINS = ("spatial", "singlecell", "genomics", "proteomics", "metabolomics", "bulkrna")


def _get_keyword_maps() -> dict[str, dict[str, str]]:
    """Build per-domain keyword maps from SKILL.md, with hardcoded fallback."""
    return {
        domain: registry.build_keyword_map(
            domain=domain,
            fallback_map=_FALLBACK_KEYWORD_MAPS.get(domain, {}),
        )
        for domain in _DOMAINS
    }


def detect_domain(input_path: str | None = None, query: str | None = None) -> str:
    """Auto-detect omics domain from file extension or query keywords."""
    if input_path:
        ext = Path(input_path).suffix.lower()
        if ext in EXTENSION_TO_DOMAIN:
            return EXTENSION_TO_DOMAIN[ext]

    if query:
        query_lower = query.lower()
        for domain, keywords in _get_keyword_maps().items():
            for kw in keywords:
                if kw in query_lower:
                    return domain

    return "spatial"  # Default fallback


def route_query(query: str, domain: str | None = None) -> tuple[str | None, float]:
    """Route query to best skill within detected domain.

    Returns:
        (skill_name, confidence_score)
    """
    if domain is None:
        domain = detect_domain(None, query)

    keyword_map = _get_keyword_maps().get(domain, {})
    return route_keyword(query, keyword_map)


def route_query_with_mode(query: str, domain: str | None = None, routing_mode: str = "keyword") -> tuple[str | None, float]:
    """Route query using specified mode."""
    if routing_mode in ["llm", "hybrid"]:
        if domain is None:
            domain = detect_domain(None, query)
        keyword_map = _get_keyword_maps().get(domain, {})
        # Use lightweight loading for LLM routing
        registry.load_lightweight()
        skill_names = set(keyword_map.values())
        skill_descriptions = {}

        for skill_name in skill_names:
            # Try lazy_skills first
            if skill_name in registry.lazy_skills:
                lazy = registry.lazy_skills[skill_name]
                skill_descriptions[skill_name] = lazy.description
            else:
                # Fallback to hardcoded skills
                skill_info = registry.skills.get(skill_name)
                if skill_info:
                    skill_descriptions[skill_name] = skill_info.get("description", skill_name)
                else:
                    skill_descriptions[skill_name] = skill_name
        skill, conf = route_query_unified(query, keyword_map, skill_descriptions, domain, routing_mode)
        if skill:
            return skill, conf
    return route_query(query, domain)


DEMO_QUERIES = {
    "spatial": [
        "find spatially variable genes in my tissue",
        "run cell communication analysis",
        "compute diffusion pseudotime for my cells",
        "pathway enrichment on marker genes",
        "batch correction on multiple samples",
        "align serial sections from the same tissue",
        "detect copy number variations in tumor",
    ],
    "singlecell": [
        "remove doublets from single cell data",
        "annotate cell types in my scRNA-seq",
        "infer trajectory and pseudotime",
        "integrate multiple single cell samples",
        "find differentially expressed genes",
        "analyze gene regulatory networks",
    ],
    "genomics": [
        "call variants from my BAM file",
        "detect structural variants in genome",
        "annotate variants with functional effects",
        "align FASTQ reads to reference genome",
        "phase haplotypes from VCF",
        "quality control on sequencing reads",
    ],
    "proteomics": [
        "identify peptides from mass spec data",
        "quantify protein abundance across samples",
        "find differentially abundant proteins",
        "analyze post-translational modifications",
        "run pathway enrichment on proteins",
        "quality control on MS raw data",
    ],
    "metabolomics": [
        "detect peaks in LC-MS data",
        "annotate metabolite features",
        "normalize metabolomics data",
        "find differential metabolites between groups",
        "map metabolites to pathways",
        "run statistical analysis on features",
    ],
    "bulkrna": [
        "check library size and gene detection in bulk RNA-seq",
        "find differentially expressed genes with DESeq2",
        "analyze alternative splicing events",
        "run pathway enrichment on DE genes",
        "deconvolve cell type proportions from bulk",
        "detect co-expression modules with WGCNA",
    ],
}


def run_demo(output_dir: Path, routing_mode: str = "keyword"):
    """Run demo showing query routing across all omics domains."""
    print("\nOrchestrator Demo — Multi-Omics Query Routing\n")

    for domain, queries in DEMO_QUERIES.items():
        print(f"{'=' * 80}")
        print(f"Domain: {domain.upper()}")
        print(f"{'=' * 80}")
        print(f"{'Query':<55} → {'Skill':<20} {'Confidence':>10}")
        print("-" * 80)

        for query in queries:
            skill, confidence = route_query_with_mode(query, domain, routing_mode)
            skill_display = skill if skill else "unknown"
            print(f"  {query:<53} → {skill_display:<20} {confidence:>10.2f}")
        print()

    # Write summary report
    report_path = output_dir / "demo_report.txt"
    with open(report_path, "w") as f:
        f.write("Orchestrator Demo — Multi-Omics Query Routing\n\n")
        for domain, queries in DEMO_QUERIES.items():
            f.write(f"{'=' * 80}\n")
            f.write(f"Domain: {domain.upper()}\n")
            f.write(f"{'=' * 80}\n")
            for query in queries:
                skill, confidence = route_query_with_mode(query, domain, routing_mode)
                f.write(f"  {query} → {skill} (confidence: {confidence:.2f})\n")
            f.write("\n")

    print(f"Demo report written to {report_path}\n")


def main():
    parser = argparse.ArgumentParser(description="Multi-Domain Omics Orchestrator")
    parser.add_argument("--query", help="Natural language query")
    parser.add_argument("--input", help="Input data file")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--routing-mode", default="keyword", choices=["keyword", "llm", "hybrid"], help="Routing mode")
    args = parser.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        run_demo(out_dir, args.routing_mode)
        return

    domain = detect_domain(args.input, args.query)
    logger.info(f"Detected domain: {domain}")

    skill = None
    confidence = 0.0

    if args.query:
        skill, confidence = route_query_with_mode(args.query, domain, args.routing_mode)
        if skill:
            logger.info(f"Routed to skill: {skill} (confidence: {confidence:.2f})")
        else:
            logger.warning(f"No skill found for query: {args.query}")

    if not skill:
        defaults = {
            "spatial": "preprocess",
            "singlecell": "sc-preprocessing",
            "genomics": "genomics-qc",
            "proteomics": "ms-qc",
            "metabolomics": "xcms-preprocess",
            "bulkrna": "bulkrna-qc",
        }
        skill = defaults.get(domain, "preprocess")
        confidence = 0.5
        logger.info(f"Fallback routed to {skill} based on domain {domain}")

    import json
    result = {
        "status": "success",
        "data": {
            "detected_domain": domain,
            "detected_skill": skill,
            "confidence": confidence
        }
    }
    out_json = out_dir / "result.json"
    out_json.write_text(json.dumps(result, indent=2))
    logger.info("Multi-domain orchestrator completed and saved result.json")

if __name__ == "__main__":
    main()
