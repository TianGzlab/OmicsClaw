#!/usr/bin/env python3
"""Proteomics Orchestrator — query routing for proteomics analysis."""

from __future__ import annotations
import argparse, json, logging, sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import DISCLAIMER, generate_report_footer, generate_report_header, write_result_json

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "proteomics-orchestrator"
SKILL_VERSION = "0.1.0"

KEYWORD_MAP: dict[str, str] = {
    "mass spec": "proteomics-ms-qc", "ms qc": "proteomics-ms-qc", "quality control": "proteomics-ms-qc",
    "peptide identification": "proteomics-identification", "identify peptides": "proteomics-identification", "maxquant": "proteomics-identification",
    "protein quantification": "proteomics-quantification", "quantify proteins": "proteomics-quantification", "lfq": "proteomics-quantification",
    "differential abundance": "proteomics-de", "differentially abundant": "proteomics-de",
    "ptm": "proteomics-ptm", "post-translational": "proteomics-ptm", "phosphorylation": "proteomics-ptm",
    "pathway enrichment": "proteomics-enrichment", "enrichment": "proteomics-enrichment", "string": "proteomics-enrichment",
    "data import": "proteomics-data-import", "convert": "proteomics-data-import",
}

SKILL_DESCRIPTIONS: dict[str, str] = {
    "proteomics-ms-qc": "Mass spectrometry raw data quality control (PTXQC, rawTools, MSstatsQC)",
    "proteomics-identification": "Database search for peptide/protein identification (MaxQuant, MS-GF+, Comet)",
    "proteomics-quantification": "Protein/peptide quantification (MaxQuant LFQ, DIA-NN, Spectronaut)",
    "proteomics-de": "Differential abundance testing (MSstats, limma, t-test)",
    "proteomics-ptm": "Post-translational modification site localization (ptmRS, PhosphoRS)",
    "proteomics-enrichment": "Pathway and functional enrichment analysis (STRING, DAVID, g:Profiler)",
    "proteomics-structural": "Structural proteomics and cross-linking MS (XlinkX, pLink)",
    "proteomics-data-import": "Import and convert proteomics data formats",
}

def route_query(query: str) -> dict:
    query_lower = query.lower().strip()
    scores: dict[str, int] = {}
    for kw, skill in KEYWORD_MAP.items():
        if kw in query_lower:
            scores[skill] = scores.get(skill, 0) + len(kw)
    if scores:
        best_skill = max(scores, key=lambda s: scores[s])
        confidence = min(1.0, scores[best_skill] / 20.0)
        matched_kws = [kw for kw, sk in KEYWORD_MAP.items() if sk == best_skill and kw in query_lower]
        return {"matched": True, "skill": best_skill, "confidence": round(confidence, 2), "matched_keywords": matched_kws}
    return {"matched": False, "skill": "proteomics-ms-qc", "confidence": 0.0, "matched_keywords": [], "fallback_reason": "No keywords matched"}

def route_query_with_mode(query: str, routing_mode: str = "keyword") -> dict:
    """Route query using specified mode."""
    if routing_mode in ["llm", "hybrid"]:
        skill, conf = route_query_unified(query, KEYWORD_MAP, SKILL_DESCRIPTIONS, "proteomics", routing_mode)
        if skill:
            return {"matched": True, "skill": skill, "confidence": conf, "matched_keywords": []}
    return route_query(query)

def main():
    parser = argparse.ArgumentParser(description="Proteomics Orchestrator")
    parser.add_argument("--query", help="Natural language query")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--routing-mode", default="keyword", choices=["keyword", "llm", "hybrid"], help="Routing mode")
    args = parser.parse_args()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.demo:
        example_queries = [
            "identify peptides from mass spec data",
            "quantify protein abundance across samples",
            "find differentially abundant proteins",
            "analyze post-translational modifications",
            "run pathway enrichment on proteins",
            "quality control on MS raw data",
        ]
        print("\nProteomics Orchestrator Demo — Query Routing\n")
        print(f"{'Query':<50} {'→ Skill':<20} Confidence")
        print("-" * 80)
        demo_routes = []
        for q in example_queries:
            r = route_query_with_mode(q, args.routing_mode)
            print(f"  {q[:48]:<50} → {r['skill']:<20} {r['confidence']:.2f}")
            demo_routes.append({"query": q, "skill": r["skill"], "confidence": r["confidence"], "keywords": r["matched_keywords"]})
        print()
        header = generate_report_header(title="Proteomics Orchestrator — Demo Report", skill_name=SKILL_NAME)
        body_lines = ["## Routing Demo\n", f"- **Total skills**: {len(SKILL_DESCRIPTIONS)}", f"- **Keyword entries**: {len(KEYWORD_MAP)}", "", "### Example Query Routing\n", "| Query | Routed Skill | Confidence |", "|-------|-------------|------------|"]
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
