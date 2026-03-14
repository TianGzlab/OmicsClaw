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

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "genomics-orchestrator"
SKILL_VERSION = "0.1.0"

KEYWORD_MAP: dict[str, str] = {
    "variant call": "genomics-variant-calling",
    "call variants": "genomics-variant-calling",
    "snp": "genomics-variant-calling",
    "indel": "genomics-variant-calling",
    "gatk": "genomics-variant-calling",
    "deepvariant": "genomics-variant-calling",
    "structural variant": "genomics-sv-detection",
    "sv detection": "genomics-sv-detection",
    "manta": "genomics-sv-detection",
    "lumpy": "genomics-sv-detection",
    "vcf": "genomics-vcf-operations",
    "filter vcf": "genomics-vcf-operations",
    "merge vcf": "genomics-vcf-operations",
    "bcftools": "genomics-vcf-operations",
    "alignment": "genomics-alignment",
    "align reads": "genomics-alignment",
    "bwa": "genomics-alignment",
    "bowtie": "genomics-alignment",
    "minimap": "genomics-alignment",
    "variant annotation": "genomics-variant-annotation",
    "annotate variants": "genomics-variant-annotation",
    "vep": "genomics-variant-annotation",
    "snpeff": "genomics-variant-annotation",
    "annovar": "genomics-variant-annotation",
    "assembly": "genomics-assembly",
    "genome assembly": "genomics-assembly",
    "spades": "genomics-assembly",
    "flye": "genomics-assembly",
    "phasing": "genomics-phasing",
    "haplotype": "genomics-phasing",
    "whatshap": "genomics-phasing",
    "shapeit": "genomics-phasing",
    "cnv": "genomics-cnv-calling",
    "copy number": "genomics-cnv-calling",
    "cnvkit": "genomics-cnv-calling",
    "quality control": "genomics-qc",
    "qc": "genomics-qc",
    "fastqc": "genomics-qc",
    "fastp": "genomics-qc",
    "chip-seq": "genomics-epigenomics",
    "atac-seq": "genomics-epigenomics",
    "peak calling": "genomics-epigenomics",
    "macs2": "genomics-epigenomics",
}

SKILL_DESCRIPTIONS: dict[str, str] = {
    "genomics-qc": "Sequencing reads QC and adapter trimming (FastQC, MultiQC, fastp)",
    "genomics-alignment": "Short/long read alignment to reference genome (BWA-MEM, Bowtie2, Minimap2)",
    "genomics-variant-calling": "Germline/somatic variant calling (GATK, DeepVariant, FreeBayes)",
    "genomics-sv-detection": "Structural variant calling (Manta, Lumpy, Delly, Sniffles)",
    "genomics-cnv-calling": "Copy number variation analysis (CNVkit, Control-FREEC, GATK gCNV)",
    "genomics-vcf-operations": "VCF manipulation, filtering, and merging (bcftools, GATK SelectVariants)",
    "genomics-variant-annotation": "Variant annotation and functional effect prediction (VEP, snpEff, ANNOVAR)",
    "genomics-assembly": "De novo genome assembly (SPAdes, Megahit, Flye, Canu)",
    "genomics-epigenomics": "ChIP-seq/ATAC-seq peak calling and motif analysis (MACS2, Homer)",
    "genomics-phasing": "Haplotype phasing (WhatsHap, SHAPEIT, Eagle)",
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
