#!/usr/bin/env python3
"""Multi-Domain Omics Orchestrator — query routing across all omics domains.

Routes queries and files to the correct skill across spatial, single-cell,
genomics, proteomics, and metabolomics domains.

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
from omicsclaw.routing.router import route_query_unified
from omicsclaw.core.registry import registry

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain detection
# ---------------------------------------------------------------------------

DOMAIN_KEYWORD_MAPS = {
    "spatial": {
        "spatial domain": "domains",
        "tissue region": "domains",
        "spatially variable": "genes",
        "spatial statistics": "statistics",
        "moran": "statistics",
        "cell type annotation": "annotate",
        "deconvolution": "deconv",
        "cell communication": "communication",
        "ligand receptor": "communication",
        "rna velocity": "velocity",
        "trajectory": "trajectory",
        "pseudotime": "trajectory",
        "pathway enrichment": "enrichment",
        "cnv": "cnv",
        "copy number": "cnv",
        "batch correction": "integrate",
        "integration": "integrate",
        "spatial registration": "register",
        "differential expression": "de",
        "marker genes": "de",
        "condition comparison": "condition",
        "preprocess": "preprocess",
        "qc": "preprocess",
    },
    "singlecell": {
        "single cell": "sc-preprocess",
        "doublet": "sc-doublet",
        "trajectory": "sc-trajectory",
        "pseudotime": "sc-trajectory",
        "cell type annotation": "sc-annotate",
        "integration": "sc-integrate",
        "batch correction": "sc-integrate",
        "differential expression": "sc-de",
        "gene regulatory": "sc-grn",
        "grn": "sc-grn",
        "cell communication": "sc-communication",
        "multiome": "sc-multiome",
    },
    "genomics": {
        "variant call": "variant-call",
        "snp": "variant-call",
        "structural variant": "sv-detect",
        "vcf": "vcf-ops",
        "alignment": "align",
        "read alignment": "align",
        "variant annotation": "variant-annotate",
        "assembly": "assemble",
        "genome assembly": "assemble",
        "phasing": "phase",
        "haplotype": "phase",
        "cnv": "cnv-calling",
        "quality control": "genomics-qc",
        "fastq": "genomics-qc",
    },
    "proteomics": {
        "mass spec": "ms-qc",
        "ms qc": "ms-qc",
        "peptide identification": "peptide-id",
        "protein quantification": "quantification",
        "differential abundance": "differential-abundance",
        "ptm": "ptm",
        "post-translational": "ptm",
        "pathway enrichment": "prot-enrichment",
        "data import": "data-import",
    },
    "metabolomics": {
        "peak detection": "peak-detect",
        "xcms": "xcms-preprocess",
        "metabolite annotation": "met-annotate",
        "normalization": "met-normalize",
        "differential": "met-diff",
        "pathway": "met-pathway",
        "statistical": "met-stat",
    },
}


def detect_domain(input_path: str | None = None, query: str | None = None) -> str:
    """Auto-detect omics domain from file extension or query keywords."""
    if input_path:
        ext = Path(input_path).suffix.lower()
        if ext in EXTENSION_TO_DOMAIN:
            return EXTENSION_TO_DOMAIN[ext]

    if query:
        query_lower = query.lower()
        for domain, keywords in DOMAIN_KEYWORD_MAPS.items():
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

    keyword_map = DOMAIN_KEYWORD_MAPS.get(domain, {})
    query_lower = query.lower()

    # Find best match with confidence scoring
    best_match = None
    best_score = 0.0

    for keyword, skill in keyword_map.items():
        if keyword in query_lower:
            # Confidence based on keyword length and position
            score = len(keyword) / len(query_lower)
            if score > best_score:
                best_score = score
                best_match = skill

    if best_match:
        # Normalize confidence to 0.5-1.0 range
        confidence = 0.5 + (best_score * 0.5)
        return best_match, min(confidence, 1.0)

    return None, 0.0


def route_query_with_mode(query: str, domain: str | None = None, routing_mode: str = "keyword") -> tuple[str | None, float]:
    """Route query using specified mode."""
    if routing_mode in ["llm", "hybrid"]:
        if domain is None:
            domain = detect_domain(None, query)
        keyword_map = DOMAIN_KEYWORD_MAPS.get(domain, {})
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
            "singlecell": "sc-preprocess",
            "genomics": "genomics-qc",
            "proteomics": "ms-qc",
            "metabolomics": "xcms-preprocess"
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
