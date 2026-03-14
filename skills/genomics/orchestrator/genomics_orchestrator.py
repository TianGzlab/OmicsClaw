#!/usr/bin/env python3
"""Genomics Orchestrator — query routing for genomics analysis.

Routes queries to genomics analysis skills.

Usage:
    python genomics_orchestrator.py --query "call variants" --output <dir>
    python genomics_orchestrator.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import (
    DISCLAIMER,
    generate_report_footer,
    generate_report_header,
    write_result_json,
)
from omicsclaw.routing.router import route_query_unified

# Original import removed

    DISCLAIMER,
    generate_report_footer,
    generate_report_header,
    write_result_json,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "genomics-orchestrator"
SKILL_VERSION = "0.1.0"

KEYWORD_MAP: dict[str, str] = {
    "variant call": "variant-call",
    "call variants": "variant-call",
    "snp": "variant-call",
    "indel": "variant-call",
    "gatk": "variant-call",
    "deepvariant": "variant-call",
    "structural variant": "sv-detect",
    "sv detection": "sv-detect",
    "manta": "sv-detect",
    "lumpy": "sv-detect",
    "vcf": "vcf-ops",
    "filter vcf": "vcf-ops",
    "merge vcf": "vcf-ops",
    "bcftools": "vcf-ops",
    "alignment": "align",
    "align reads": "align",
    "bwa": "align",
    "bowtie": "align",
    "minimap": "align",
    "variant annotation": "variant-annotate",
    "annotate variants": "variant-annotate",
    "vep": "variant-annotate",
    "snpeff": "variant-annotate",
    "annovar": "variant-annotate",
    "assembly": "assemble",
    "genome assembly": "assemble",
    "spades": "assemble",
    "flye": "assemble",
    "phasing": "phase",
    "haplotype": "phase",
    "whatshap": "phase",
    "shapeit": "phase",
    "cnv": "cnv-calling",
    "copy number": "cnv-calling",
    "cnvkit": "cnv-calling",
    "quality control": "genomics-qc",
    "qc": "genomics-qc",
    "fastqc": "genomics-qc",
    "fastp": "genomics-qc",
    "chip-seq": "epigenomics",
    "atac-seq": "epigenomics",
    "peak calling": "epigenomics",
    "macs2": "epigenomics",
}

SKILL_DESCRIPTIONS: dict[str, str] = {
    "genomics-qc": "Sequencing reads QC and adapter trimming (FastQC, MultiQC, fastp)",
    "align": "Short/long read alignment to reference genome (BWA-MEM, Bowtie2, Minimap2)",
    "variant-call": "Germline/somatic variant calling (GATK, DeepVariant, FreeBayes)",
    "sv-detect": "Structural variant calling (Manta, Lumpy, Delly, Sniffles)",
    "cnv-calling": "Copy number variation analysis (CNVkit, Control-FREEC, GATK gCNV)",
    "vcf-ops": "VCF manipulation, filtering, and merging (bcftools, GATK SelectVariants)",
    "variant-annotate": "Variant annotation and functional effect prediction (VEP, snpEff, ANNOVAR)",
    "assemble": "De novo genome assembly (SPAdes, Megahit, Flye, Canu)",
    "epigenomics": "ChIP-seq/ATAC-seq peak calling and motif analysis (MACS2, Homer)",
    "phase": "Haplotype phasing (WhatsHap, SHAPEIT, Eagle)",
}

def route_query(query: str) -> dict:
    """Route a natural language query to the best skill."""
    query_lower = query.lower().strip()
    
    scores: dict[str, int] = {}
    for kw, skill in KEYWORD_MAP.items():
        if kw in query_lower:
            scores[skill] = scores.get(skill, 0) + len(kw)
    
    if scores:
        best_skill = max(scores, key=lambda s: scores[s])
        confidence = min(1.0, scores[best_skill] / 20.0)
        matched_kws = [kw for kw, sk in KEYWORD_MAP.items() if sk == best_skill and kw in query_lower]
        return {
            "matched": True,
            "skill": best_skill,
            "confidence": round(confidence, 2),
            "matched_keywords": matched_kws,
        }
    
    return {
        "matched": False,
        "skill": "genomics-qc",
        "confidence": 0.0,
        "matched_keywords": [],
        "fallback_reason": "No keywords matched; defaulting to genomics-qc",
    }

def route_query_with_mode(query: str, routing_mode: str = "keyword") -> dict:
    """Route query using specified mode."""
    if routing_mode in ["llm", "hybrid"]:
        skill, conf = route_query_unified(query, KEYWORD_MAP, SKILL_DESCRIPTIONS, "genomics", routing_mode)
        if skill:
            return {"matched": True, "skill": skill, "confidence": conf, "matched_keywords": []}
    return route_query(query)

def main():
    parser = argparse.ArgumentParser(description="Genomics Orchestrator")
    parser.add_argument("--query", help="Natural language query")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--routing-mode", default="keyword", choices=["keyword", "llm", "hybrid"], help="Routing mode")
    args = parser.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        example_queries = [
            "call variants from my BAM file",
            "detect structural variants in genome",
            "annotate variants with functional effects",
            "align FASTQ reads to reference genome",
            "phase haplotypes from VCF",
            "quality control on sequencing reads",
        ]
        print("\nGenomics Orchestrator Demo — Query Routing\n")
        print(f"{'Query':<50} {'→ Skill':<20} Confidence")
        print("-" * 80)
        demo_routes = []
        for q in example_queries:
            r = route_query_with_mode(q, args.routing_mode)
            print(f"  {q[:48]:<50} → {r['skill']:<20} {r['confidence']:.2f}")
            demo_routes.append({
                "query": q,
                "skill": r["skill"],
                "confidence": r["confidence"],
                "keywords": r["matched_keywords"],
            })
        print()

        header = generate_report_header(
            title="Genomics Orchestrator — Demo Report",
            skill_name=SKILL_NAME,
        )
        body_lines = [
            "## Routing Demo\n",
            f"- **Total skills**: {len(SKILL_DESCRIPTIONS)}",
            f"- **Keyword entries**: {len(KEYWORD_MAP)}",
            "",
            "### Example Query Routing\n",
            "| Query | Routed Skill | Confidence |",
            "|-------|-------------|------------|",
        ]
        for r in demo_routes:
            q_short = r["query"][:45]
            body_lines.append(f"| {q_short} | `{r['skill']}` | {r['confidence']:.2f} |")
        
        body_lines.extend([
            "",
            "## All Skills\n",
            "| Alias | Description |",
            "|-------|-------------|",
        ])
        for alias, desc in SKILL_DESCRIPTIONS.items():
            body_lines.append(f"| `{alias}` | {desc} |")
        
        footer = generate_report_footer()
        report_md = out_dir / "report.md"
        report_md.write_text(header + "\n".join(body_lines) + "\n" + footer)
        
        write_result_json(
            out_dir,
            skill=SKILL_NAME,
            version=SKILL_VERSION,
            summary={"demo_routes": len(demo_routes), "total_skills": len(SKILL_DESCRIPTIONS)},
            data={"demo_routes": demo_routes},
        )
        
        print(f"Demo report written to {out_dir}\n")
        return

    if args.query:
        result = route_query(args.query)
        logger.info(f"Routed to skill: {result['skill']} (confidence: {result['confidence']:.2f})")
        write_result_json(out_dir, skill=SKILL_NAME, version=SKILL_VERSION, summary={}, data=result)
    else:
        logger.error("Either --query or --demo is required")
        sys.exit(1)

if __name__ == "__main__":
    main()
