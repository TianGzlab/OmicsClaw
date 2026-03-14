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

SKILL_NAME = "sc-orchestrator"
SKILL_VERSION = "0.1.0"

KEYWORD_MAP: dict[str, str] = {
    # Preprocessing
    "preprocess": "sc-preprocess",
    "qc": "sc-preprocess",
    "quality control": "sc-preprocess",
    "normalize": "sc-preprocess",
    "clustering": "sc-preprocess",
    "scrna-seq": "sc-preprocess",
    "single cell": "sc-preprocess",
    # Doublet detection
    "doublet": "sc-doublet",
    "scrublet": "sc-doublet",
    "doubletfinder": "sc-doublet",
    "remove doublets": "sc-doublet",
    # Trajectory
    "trajectory": "sc-trajectory",
    "pseudotime": "sc-trajectory",
    "monocle": "sc-trajectory",
    "slingshot": "sc-trajectory",
    "cellrank": "sc-trajectory",
    # Annotation
    "cell type": "sc-annotate",
    "annotation": "sc-annotate",
    "celltypist": "sc-annotate",
    "singler": "sc-annotate",
    "annotate": "sc-annotate",
    # Integration
    "integration": "sc-integrate",
    "batch correction": "sc-integrate",
    "harmony": "sc-integrate",
    "scvi": "sc-integrate",
    "integrate": "sc-integrate",
    # Differential expression
    "differential expression": "sc-de",
    "de analysis": "sc-de",
    "marker genes": "sc-de",
    "wilcoxon": "sc-de",
    # GRN
    "grn": "sc-grn",
    "gene regulatory": "sc-grn",
    "scenic": "sc-grn",
    "celloracle": "sc-grn",
    # Communication
    "cell communication": "sc-communication",
    "ligand receptor": "sc-communication",
    "cellphonedb": "sc-communication",
    "nichenet": "sc-communication",
    # Multiome
    "multiome": "sc-multiome",
    "cite-seq": "sc-multiome",
    "atac": "sc-multiome",
    "wnn": "sc-multiome",
}

SKILL_DESCRIPTIONS: dict[str, str] = {
    "sc-preprocess": "scRNA-seq QC, normalization, HVG, PCA/UMAP, Leiden clustering",
    "sc-doublet": "Doublet detection and removal (Scrublet, scDblFinder, DoubletFinder)",
    "sc-annotate": "Cell type annotation (CellTypist, SingleR, scmap, GARNET, scANVI)",
    "sc-trajectory": "Trajectory inference and pseudotime (Monocle3, Slingshot, CellRank)",
    "sc-integrate": "Multi-sample integration and batch correction (Harmony, scVI, BBKNN)",
    "sc-de": "Differential expression analysis (Wilcoxon, MAST, pseudobulk PyDESeq2)",
    "sc-grn": "Gene regulatory network inference (pySCENIC, CellOracle)",
    "sc-communication": "Cell-cell communication (CellPhoneDB, LIANA+, NicheNet)",
    "sc-multiome": "Paired multi-omics integration (WNN, MOFA+, scVI-tools)",
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
        "skill": "sc-preprocess",
        "confidence": 0.0,
        "matched_keywords": [],
        "fallback_reason": "No keywords matched; defaulting to sc-preprocess",
    }

def route_query_with_mode(query: str, routing_mode: str = "keyword") -> dict:
    """Route query using specified mode."""
    if routing_mode in ["llm", "hybrid"]:
        skill, conf = route_query_unified(query, KEYWORD_MAP, SKILL_DESCRIPTIONS, "singlecell", routing_mode)
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
            "infer trajectory and pseudotime",
            "integrate multiple single cell samples",
            "find differentially expressed genes",
            "analyze gene regulatory networks",
        ]
        print("\nSingle-Cell Orchestrator Demo — Query Routing\n")
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
        write_result_json(out_dir, skill_name=SKILL_NAME, status="success", data=result)
    else:
        logger.error("Either --query or --demo is required")
        sys.exit(1)

if __name__ == "__main__":
    main()
