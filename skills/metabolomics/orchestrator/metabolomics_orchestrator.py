#!/usr/bin/env python3
"""Metabolomics Orchestrator — query routing for metabolomics analysis."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import DISCLAIMER, generate_report_footer, generate_report_header, write_result_json
from omicsclaw.routing.router import route_keyword, route_query_unified
from omicsclaw.core.registry import registry

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "metabolomics-orchestrator"
SKILL_VERSION = "0.1.0"

_FALLBACK_KEYWORD_MAP: dict[str, str] = {
    "peak detection": "metabolomics-peak-detection", "detect peaks": "metabolomics-peak-detection", "feature detection": "metabolomics-peak-detection",
    "xcms": "metabolomics-xcms-preprocessing", "preprocessing": "metabolomics-xcms-preprocessing", "alignment": "metabolomics-xcms-preprocessing",
    "metabolite annotation": "metabolomics-annotation", "annotate metabolites": "metabolomics-annotation", "sirius": "metabolomics-annotation",
    "normalization": "metabolomics-normalization", "normalize": "metabolomics-normalization", "scaling": "metabolomics-normalization",
    "differential": "metabolomics-de", "pls-da": "metabolomics-de", "metaboanalyst": "metabolomics-de",
    "pathway": "metabolomics-pathway-enrichment", "mummichog": "metabolomics-pathway-enrichment", "pathway enrichment": "metabolomics-pathway-enrichment",
    "statistical": "metabolomics-statistics", "pca": "metabolomics-statistics", "clustering": "metabolomics-statistics",
}


def _get_keyword_map() -> dict[str, str]:
    """Build keyword map from SKILL.md trigger_keywords with hardcoded fallback."""
    return registry.build_keyword_map(domain="metabolomics", fallback_map=_FALLBACK_KEYWORD_MAP)


SKILL_DESCRIPTIONS: dict[str, str] = {
    "metabolomics-xcms-preprocessing": "LC-MS/GC-MS raw data QC and XCMS preprocessing",
    "metabolomics-peak-detection": "Peak picking, feature detection, alignment and grouping (XCMS, MZmine 3)",
    "metabolomics-annotation": "Metabolite annotation and structural identification (SIRIUS, CSI:FingerID, GNPS)",
    "metabolomics-quantification": "Feature quantification, missing value imputation, and normalization",
    "metabolomics-normalization": "Data normalization, scaling, and transformation",
    "metabolomics-de": "Differential metabolite abundance (MetaboAnalystR, ropls)",
    "metabolomics-pathway-enrichment": "Metabolic pathway enrichment and mapping (mummichog, FELLA)",
    "metabolomics-statistics": "Statistical analysis (PCA, PLS-DA, clustering, univariate tests)",
}

def route_query(query: str) -> dict:
    effective_map = _get_keyword_map()
    skill, confidence = route_keyword(query, effective_map)
    if skill:
        query_lower = query.lower().strip()
        matched_kws = [kw for kw, sk in effective_map.items() if sk == skill and kw in query_lower]
        return {"matched": True, "skill": skill, "confidence": confidence, "matched_keywords": matched_kws}
    return {"matched": False, "skill": "metabolomics-xcms-preprocessing", "confidence": 0.0, "matched_keywords": [], "fallback_reason": "No keywords matched"}

def route_query_with_mode(query: str, routing_mode: str = "keyword") -> dict:
    """Route query using specified mode."""
    if routing_mode in ["llm", "hybrid"]:
        effective_map = _get_keyword_map()
        skill, conf = route_query_unified(query, effective_map, SKILL_DESCRIPTIONS, "metabolomics", routing_mode)
        if skill:
            return {"matched": True, "skill": skill, "confidence": conf, "matched_keywords": []}
    return route_query(query)

def main():
    parser = argparse.ArgumentParser(description="Metabolomics Orchestrator")
    parser.add_argument("--query", help="Natural language query")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--routing-mode", default="keyword", choices=["keyword", "llm", "hybrid"], help="Routing mode")
    args = parser.parse_args()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.demo:
        example_queries = [
            "detect peaks in LC-MS data",
            "annotate metabolite features",
            "normalize metabolomics data",
            "find differential metabolites between groups",
            "map metabolites to pathways",
            "run statistical analysis on features",
        ]
        print("\nMetabolomics Orchestrator Demo — Query Routing\n")
        print(f"{'Query':<50} {'→ Skill':<20} Confidence")
        print("-" * 80)
        demo_routes = []
        for q in example_queries:
            r = route_query_with_mode(q, args.routing_mode)
            print(f"  {q[:48]:<50} → {r['skill']:<20} {r['confidence']:.2f}")
            demo_routes.append({"query": q, "skill": r["skill"], "confidence": r["confidence"], "keywords": r["matched_keywords"]})
        print()
        header = generate_report_header(title="Metabolomics Orchestrator — Demo Report", skill_name=SKILL_NAME)
        effective_map = _get_keyword_map()
        body_lines = ["## Routing Demo\n", f"- **Total skills**: {len(SKILL_DESCRIPTIONS)}", f"- **Keyword entries**: {len(effective_map)}", "", "### Example Query Routing\n", "| Query | Routed Skill | Confidence |", "|-------|-------------|------------|"]
        for r in demo_routes:
            body_lines.append(f"| {r['query'][:45]} | `{r['skill']}` | {r['confidence']:.2f} |")
        body_lines.extend(["", "## All Skills\n", "| Alias | Description |", "|-------|-------------|"])
        for alias, desc in SKILL_DESCRIPTIONS.items():
            body_lines.append(f"| `{alias}` | {desc} |")
        footer = generate_report_footer()
        (out_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)
        write_result_json(out_dir, skill=SKILL_NAME, version=SKILL_VERSION, summary={"demo_routes": len(demo_routes), "total_skills": len(SKILL_DESCRIPTIONS)}, data={"demo_routes": demo_routes})
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
