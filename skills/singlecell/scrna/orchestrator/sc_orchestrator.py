#!/usr/bin/env python3
"""Single-Cell Orchestrator — query routing for single-cell omics.

Routes queries to single-cell analysis skills.

Usage:
    python sc_orchestrator.py --query "remove doublets" --output <dir>
    python sc_orchestrator.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import (
    DISCLAIMER,
    generate_report_footer,
    generate_report_header,
    write_result_json,
)
from omicsclaw.routing.router import route_keyword, route_query_unified
from omicsclaw.core.registry import registry

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "orchestrator"
SKILL_VERSION = "0.2.0"

_FALLBACK_KEYWORD_MAP: dict[str, str] = {
    # QC
    "qc": "sc-qc",
    "quality control": "sc-qc",
    "qc metrics": "sc-qc",
    # Filtering
    "filter cells": "sc-filter",
    "filter genes": "sc-filter",
    "cell filtering": "sc-filter",
    # Preprocessing
    "preprocess": "sc-preprocessing",
    "normalize": "sc-preprocessing",
    "clustering": "sc-preprocessing",
    "scrna-seq": "sc-preprocessing",
    "single cell": "sc-preprocessing",
    "hvg": "sc-preprocessing",
    "pca": "sc-preprocessing",
    "umap": "sc-preprocessing",
    "leiden": "sc-preprocessing",
    # Ambient RNA
    "ambient": "sc-ambient-removal",
    "ambient rna": "sc-ambient-removal",
    "cellbender": "sc-ambient-removal",
    "soupx": "sc-ambient-removal",
    "soup": "sc-ambient-removal",
    # Doublet detection
    "doublet": "sc-doublet-detection",
    "scrublet": "sc-doublet-detection",
    "doubletfinder": "sc-doublet-detection",
    "remove doublets": "sc-doublet-detection",
    # Annotation
    "cell type": "sc-cell-annotation",
    "annotation": "sc-cell-annotation",
    "celltypist": "sc-cell-annotation",
    "singler": "sc-cell-annotation",
    "annotate": "sc-cell-annotation",
    # Integration
    "integration": "sc-batch-integration",
    "batch correction": "sc-batch-integration",
    "harmony": "sc-batch-integration",
    "scvi": "sc-batch-integration",
    "integrate": "sc-batch-integration",
    "bbknn": "sc-batch-integration",
    "scanorama": "sc-batch-integration",
    # Differential expression
    "differential expression": "sc-de",
    "de analysis": "sc-de",
    "differentially expressed": "sc-de",
    # Markers
    "marker genes": "sc-markers",
    "find markers": "sc-markers",
    "cluster markers": "sc-markers",
    # Pseudotime / Trajectory
    "trajectory": "sc-pseudotime",
    "pseudotime": "sc-pseudotime",
    "diffusion pseudotime": "sc-pseudotime",
    "dpt": "sc-pseudotime",
    "paga": "sc-pseudotime",
    "cell fate": "sc-pseudotime",
    # Velocity
    "velocity": "sc-velocity",
    "rna velocity": "sc-velocity",
    "scvelo": "sc-velocity",
    "spliced unspliced": "sc-velocity",
    # GRN
    "grn": "sc-grn",
    "gene regulatory": "sc-grn",
    "scenic": "sc-grn",
    "pyscenic": "sc-grn",
    "regulon": "sc-grn",
    # Cell-cell communication
    "cell communication": "sc-cell-communication",
    "cell-cell communication": "sc-cell-communication",
    "ligand receptor": "sc-cell-communication",
    "cellchat": "sc-cell-communication",
    "liana": "sc-cell-communication",
}


def _get_keyword_map() -> dict[str, str]:
    """Build keyword map from SKILL.md trigger_keywords with hardcoded fallback."""
    return registry.build_keyword_map(domain="singlecell", fallback_map=_FALLBACK_KEYWORD_MAP)


SKILL_DESCRIPTIONS: dict[str, str] = {
    "sc-qc": "QC metrics calculation and visualization",
    "sc-filter": "Cell/gene filtering with tissue-specific presets",
    "sc-preprocessing": "scRNA-seq QC, normalization, HVG, PCA/UMAP, Leiden clustering",
    "sc-ambient-removal": "Ambient RNA removal (CellBender, SoupX, simple)",
    "sc-doublet-detection": "Doublet detection and removal (Scrublet, scDblFinder, DoubletFinder)",
    "sc-cell-annotation": "Cell type annotation (marker-based, CellTypist, SingleR, scmap)",
    "sc-batch-integration": "Batch correction (Harmony, scVI, BBKNN, Scanorama)",
    "sc-de": "Differential expression (Wilcoxon, t-test, MAST, DESeq2)",
    "sc-markers": "Marker gene identification (Wilcoxon, t-test, logistic regression)",
    "sc-pseudotime": "Pseudotime and trajectory (PAGA, DPT)",
    "sc-velocity": "RNA velocity (scVelo stochastic/dynamical)",
    "sc-grn": "Gene regulatory network inference (pySCENIC)",
    "sc-cell-communication": "Cell-cell communication analysis (LIANA, CellChat)",
}

def route_query(query: str) -> dict:
    """Route a natural language query to the best skill."""
    effective_map = _get_keyword_map()
    skill, confidence = route_keyword(query, effective_map)

    if skill:
        query_lower = query.lower().strip()
        matched_kws = [kw for kw, sk in effective_map.items() if sk == skill and kw in query_lower]
        return {
            "matched": True,
            "skill": skill,
            "confidence": confidence,
            "matched_keywords": matched_kws,
        }

    return {
        "matched": False,
        "skill": "sc-preprocessing",
        "confidence": 0.0,
        "matched_keywords": [],
        "fallback_reason": "No keywords matched; defaulting to sc-preprocessing",
    }

def route_query_with_mode(query: str, routing_mode: str = "keyword") -> dict:
    """Route query using specified mode."""
    if routing_mode in ["llm", "hybrid"]:
        effective_map = _get_keyword_map()
        skill, conf = route_query_unified(query, effective_map, SKILL_DESCRIPTIONS, "singlecell", routing_mode)
        if skill:
            return {"matched": True, "skill": skill, "confidence": conf, "matched_keywords": []}
    # Fallback to keyword routing
    return route_query(query)

def main():
    parser = argparse.ArgumentParser(description="Single-Cell Orchestrator")
    parser.add_argument("--query", help="Natural language query")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--routing-mode", default="keyword", choices=["keyword", "llm", "hybrid"], help="Routing mode")
    args = parser.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        example_queries = [
            "remove doublets from single cell data",
            "annotate cell types in my scRNA-seq",
            "compute pseudotime and trajectory",
            "integrate multiple single cell samples with harmony",
            "find differentially expressed genes",
            "analyze gene regulatory networks",
            "run RNA velocity analysis",
            "find marker genes for each cluster",
        ]
        print("\nSingle-Cell Orchestrator Demo — Query Routing\n")
        print(f"{'Query':<55} {'→ Skill':<22} Confidence")
        print("-" * 90)
        demo_routes = []
        for q in example_queries:
            r = route_query_with_mode(q, args.routing_mode)
            print(f"  {q[:53]:<55} → {r['skill']:<22} {r['confidence']:.2f}")
            demo_routes.append({
                "query": q,
                "skill": r["skill"],
                "confidence": r["confidence"],
                "keywords": r["matched_keywords"],
            })
        print()

        header = generate_report_header(
            title="Single-Cell Orchestrator — Demo Report",
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
        write_result_json(
            out_dir,
            skill=SKILL_NAME,
            version=SKILL_VERSION,
            summary={"matched": result["matched"], "confidence": result["confidence"]},
            data=result,
        )
    else:
        logger.error("Either --query or --demo is required")
        sys.exit(1)

if __name__ == "__main__":
    main()
