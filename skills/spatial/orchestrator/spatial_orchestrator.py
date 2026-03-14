#!/usr/bin/env python3
"""Spatial Orchestrator — query routing and pipeline orchestration.

Routes natural language queries and file inputs to the correct OmicsClaw
skill, and can execute multi-skill pipelines end-to-end.

Usage:
    python spatial_orchestrator.py --query "find spatially variable genes" --output <dir>
    python spatial_orchestrator.py --input <data.h5ad> --output <dir>
    python spatial_orchestrator.py --pipeline standard --input <data.h5ad> --output <dir>
    python spatial_orchestrator.py --list-skills
    python spatial_orchestrator.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import (
    DISCLAIMER,
    generate_report_footer,
    generate_report_header,
    write_result_json,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "orchestrator"
SKILL_VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# Routing maps
# ---------------------------------------------------------------------------

KEYWORD_MAP: dict[str, str] = {
    # Spatial Transcriptomics
    "qc": "spatial-preprocessing",
    "quality control": "spatial-preprocessing",
    "preprocess": "spatial-preprocessing",
    "normalize": "spatial-preprocessing",
    "normalise": "spatial-preprocessing",
    "clustering": "spatial-preprocessing",
    "leiden": "spatial-preprocessing",
    "visium": "spatial-preprocessing",
    "xenium": "spatial-preprocessing",
    "merfish": "spatial-preprocessing",
    # Spatial domains
    "spatial domain": "spatial-domain-identification",
    "tissue region": "spatial-domain-identification",
    "tissue domain": "spatial-domain-identification",
    "niche": "spatial-domain-identification",
    "spagcn": "spatial-domain-identification",
    "stagate": "spatial-domain-identification",
    "graphst": "spatial-domain-identification",
    "banksy": "spatial-domain-identification",
    # Cell type annotation
    "cell type annotation": "spatial-cell-annotation",
    "cell type": "spatial-cell-annotation",
    "cell assignment": "spatial-cell-annotation",
    "tangram": "spatial-cell-annotation",
    "scanvi": "spatial-cell-annotation",
    "cellassign": "spatial-cell-annotation",
    # Deconvolution
    "deconvolution": "spatial-deconvolution",
    "deconvolve": "spatial-deconvolution",
    "cell proportion": "spatial-deconvolution",
    "cell type proportion": "spatial-deconvolution",
    "card": "spatial-deconvolution",
    "cell2location": "spatial-deconvolution",
    "rctd": "spatial-deconvolution",
    # Spatial statistics
    "spatial statistics": "spatial-statistics",
    "spatial autocorrelation": "spatial-statistics",
    "autocorrelation": "spatial-statistics",
    "moran": "spatial-statistics",
    "moran's i": "spatial-statistics",
    "geary": "spatial-statistics",
    "ripley": "spatial-statistics",
    "neighborhood enrichment": "spatial-statistics",
    "co-occurrence": "spatial-statistics",
    # Spatially variable genes
    "spatially variable gene": "spatial-svg-detection",
    "spatially variable": "spatial-svg-detection",
    "spatial gene": "spatial-svg-detection",
    "svg": "spatial-svg-detection",
    "spatialde": "spatial-svg-detection",
    "spark": "spatial-svg-detection",
    # Differential expression
    "differential expression": "spatial-de",
    "marker gene": "spatial-de",
    "marker genes": "spatial-de",
    "de analysis": "spatial-de",
    "wilcoxon": "spatial-de",
    # Condition comparison
    "condition comparison": "spatial-condition-comparison",
    "pseudobulk": "spatial-condition-comparison",
    "deseq2": "spatial-condition-comparison",
    "treatment vs control": "spatial-condition-comparison",
    "experimental condition": "spatial-condition-comparison",
    # Cell communication
    "cell communication": "spatial-cell-communication",
    "cell-cell communication": "spatial-cell-communication",
    "ligand receptor": "spatial-cell-communication",
    "ligand-receptor": "spatial-cell-communication",
    "liana": "spatial-cell-communication",
    "cellphonedb": "spatial-cell-communication",
    "fastccc": "spatial-cell-communication",
    # RNA velocity
    "rna velocity": "spatial-velocity",
    "velocity": "spatial-velocity",
    "cellular dynamics": "spatial-velocity",
    "scvelo": "spatial-velocity",
    "spliced unspliced": "spatial-velocity",
    # Trajectory
    "trajectory": "spatial-trajectory",
    "pseudotime": "spatial-trajectory",
    "diffusion pseudotime": "spatial-trajectory",
    "dpt": "spatial-trajectory",
    "cellrank": "spatial-trajectory",
    "palantir": "spatial-trajectory",
    "cell fate": "spatial-trajectory",
    # Enrichment
    "pathway enrichment": "spatial-enrichment",
    "enrichment": "spatial-enrichment",
    "gsea": "spatial-enrichment",
    "gene set enrichment": "spatial-enrichment",
    "go analysis": "spatial-enrichment",
    "kegg": "spatial-enrichment",
    "reactome": "spatial-enrichment",
    "pathway": "spatial-enrichment",
    # CNV
    "copy number": "spatial-cnv",
    "cnv": "spatial-cnv",
    "infercnv": "spatial-cnv",
    "chromosomal aberration": "spatial-cnv",
    # Integration
    "multi-sample integration": "spatial-integration",
    "multi sample integration": "spatial-integration",
    "batch correction": "spatial-integration",
    "batch effect": "spatial-integration",
    "harmony": "spatial-integration",
    "bbknn": "spatial-integration",
    "scanorama": "spatial-integration",
    "integration": "spatial-integration",
    # Registration
    "spatial registration": "spatial-registration",
    "slice alignment": "spatial-registration",
    "paste": "spatial-registration",
    "stalign": "spatial-registration",
    "serial section": "spatial-registration",
    "multi-slice": "spatial-registration",
}

EXTENSION_MAP: dict[str, str] = {
    ".h5ad": "spatial-preprocessing",
    ".h5": "spatial-preprocessing",
    ".zarr": "spatial-preprocessing",
    ".loom": "spatial-preprocessing",
    ".csv": "spatial-preprocessing",
    ".txt": "spatial-preprocessing",
}

# Named pipelines: ordered list of skill aliases to execute in sequence
NAMED_PIPELINES: dict[str, list[str]] = {
    "standard": ["preprocess", "domains", "de", "genes", "statistics"],
    "full": ["preprocess", "domains", "de", "genes", "statistics", "communication", "enrichment"],
    "integration": ["integrate", "domains", "de"],
    "spatial_only": ["preprocess", "genes", "statistics"],
    "cancer": ["preprocess", "cnv", "de", "enrichment"],
}

# Human-readable skill descriptions for listing
SKILL_DESCRIPTIONS: dict[str, str] = {
    "preprocess": "Spatial data QC, normalization, HVG, PCA/UMAP, Leiden clustering",
    "domains": "Tissue region/niche identification (SpaGCN, STAGATE, Leiden)",
    "annotate": "Cell type annotation (Tangram, scANVI, CellAssign)",
    "deconv": "Deconvolution — cell type proportions (CARD, Cell2Location, RCTD)",
    "statistics": "Spatial statistics (Moran's I, Geary's C, Ripley, neighborhood enrichment)",
    "genes": "Spatially variable genes (Moran's I, SpatialDE, SPARK-X)",
    "de": "Differential expression (Wilcoxon, t-test, cluster markers)",
    "condition": "Condition comparison with pseudobulk DESeq2 statistics",
    "communication": "Cell-cell communication (LIANA+, CellPhoneDB, built-in L-R)",
    "velocity": "RNA velocity and cellular dynamics (scVelo, S/U ratio)",
    "trajectory": "Trajectory inference (DPT, CellRank, Palantir)",
    "enrichment": "Pathway enrichment (GSEA, ORA, Enrichr)",
    "cnv": "Copy number variation inference (inferCNVpy, expression-based)",
    "integrate": "Multi-sample integration (Harmony, BBKNN, Scanorama)",
    "register": "Spatial registration / slice alignment (Procrustes, PASTE)",
}


# ---------------------------------------------------------------------------
# Core routing logic
# ---------------------------------------------------------------------------


def route_query(query: str) -> dict:
    """Route a natural language query to the best skill."""
    query_lower = query.lower().strip()

    # Score all skills by keyword matches (longest match wins)
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
            "scores": scores,
        }

    return {
        "matched": False,
        "skill": "preprocess",
        "confidence": 0.0,
        "matched_keywords": [],
        "scores": {},
        "fallback_reason": "No keywords matched; defaulting to preprocess",
    }


def route_file(input_path: str) -> dict:
    """Route by input file extension."""
    ext = Path(input_path).suffix.lower()
    skill = EXTENSION_MAP.get(ext, "preprocess")
    return {
        "matched": ext in EXTENSION_MAP,
        "skill": skill,
        "extension": ext,
        "input_file": input_path,
    }


def list_skills() -> dict:
    """Return all registered skills with descriptions."""
    return {alias: desc for alias, desc in SKILL_DESCRIPTIONS.items()}


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------


def _run_skill_subprocess(
    skill_alias: str,
    *,
    input_path: str | None,
    output_dir: Path,
    extra_args: list[str] | None = None,
    timeout: int = 600,
) -> dict:
    """Invoke omicsclaw.py run <skill> via subprocess."""
    omicsclaw_script = _PROJECT_ROOT / "omicsclaw.py"

    cmd = [sys.executable, str(omicsclaw_script), "run", skill_alias]
    if input_path:
        cmd.extend(["--input", input_path])
    cmd.extend(["--output", str(output_dir)])
    if extra_args:
        cmd.extend(extra_args)

    logger.info("  Running skill '%s' -> %s", skill_alias, output_dir)
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(_PROJECT_ROOT),
        )
        elapsed = round(time.time() - t0, 2)
        return {
            "skill": skill_alias,
            "success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "output_dir": str(output_dir),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "duration_seconds": elapsed,
        }
    except subprocess.TimeoutExpired:
        return {
            "skill": skill_alias,
            "success": False,
            "exit_code": -1,
            "output_dir": str(output_dir),
            "stdout": "",
            "stderr": f"Timed out after {timeout}s",
            "duration_seconds": round(time.time() - t0, 2),
        }
    except Exception as exc:
        return {
            "skill": skill_alias,
            "success": False,
            "exit_code": -1,
            "output_dir": str(output_dir),
            "stdout": "",
            "stderr": str(exc),
            "duration_seconds": round(time.time() - t0, 2),
        }


def run_pipeline(
    pipeline_name: str,
    *,
    input_path: str,
    output_dir: Path,
    timeout: int = 600,
) -> dict:
    """Execute a named pipeline, chaining processed.h5ad between steps."""
    if pipeline_name not in NAMED_PIPELINES:
        return {
            "success": False,
            "error": f"Unknown pipeline '{pipeline_name}'. Available: {list(NAMED_PIPELINES.keys())}",
        }

    steps = NAMED_PIPELINES[pipeline_name]
    logger.info("Pipeline '%s': %d steps — %s", pipeline_name, len(steps), " → ".join(steps))

    results: dict[str, dict] = {}
    current_input = input_path
    all_succeeded = True

    for step in steps:
        step_out = output_dir / step
        step_out.mkdir(parents=True, exist_ok=True)

        result = _run_skill_subprocess(
            step,
            input_path=current_input,
            output_dir=step_out,
            timeout=timeout,
        )
        results[step] = {
            "success": result["success"],
            "duration_seconds": result["duration_seconds"],
        }

        if not result["success"]:
            logger.warning("  Step '%s' FAILED: %s", step, result["stderr"][:200])
            all_succeeded = False
            break

        # Chain: pass processed.h5ad to the next step
        processed = step_out / "processed.h5ad"
        if processed.exists():
            current_input = str(processed)

    return {
        "pipeline": pipeline_name,
        "steps": steps,
        "results": results,
        "success": all_succeeded,
        "n_succeeded": sum(1 for r in results.values() if r["success"]),
        "n_total": len(steps),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def write_routing_report(
    output_dir: Path,
    routing: dict,
    query: str | None,
    input_file: str | None,
    params: dict,
) -> None:
    """Write a routing decision report."""
    header = generate_report_header(
        title="Spatial Orchestrator — Routing Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={"Query": query or "(none)", "Input": input_file or "(none)"},
    )

    body_lines = [
        "## Routing Decision\n",
        f"- **Recommended skill**: `{routing['skill']}`",
        f"- **Confidence**: {routing.get('confidence', 0):.2f}",
        f"- **Matched**: {routing.get('matched', False)}",
    ]

    if routing.get("matched_keywords"):
        body_lines.append(f"- **Matched keywords**: {', '.join(routing['matched_keywords'])}")

    if not routing.get("matched"):
        body_lines.append(f"- **Fallback reason**: {routing.get('fallback_reason', '')}")

    skill = routing["skill"]
    desc = SKILL_DESCRIPTIONS.get(skill, "")
    if desc:
        body_lines.extend(["", f"### About `{skill}`\n", desc])

    body_lines.extend([
        "", "### Suggested Command\n",
        "```bash",
        f"python omicsclaw.py run {skill} --input <your_data.h5ad> --output /tmp/{skill}_output",
        "```",
    ])

    body_lines.extend(["", "## Available Skills\n"])
    body_lines.append("| Alias | Description |")
    body_lines.append("|-------|-------------|")
    for alias, desc in SKILL_DESCRIPTIONS.items():
        body_lines.append(f"| `{alias}` | {desc} |")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)
    logger.info("Wrote %s", output_dir / "report.md")

    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary={
            "routed_to": routing["skill"],
            "confidence": routing.get("confidence", 0),
            "matched": routing.get("matched", False),
            "query": query,
            "input_file": input_file,
        },
        data={"params": params, "routing": routing},
    )

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python spatial_orchestrator.py"
    if query:
        cmd += f' --query "{query}"'
    if input_file:
        cmd += f" --input {input_file}"
    cmd += f" --output {output_dir}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


def write_pipeline_report(
    output_dir: Path,
    pipeline_result: dict,
    input_file: str,
    params: dict,
) -> None:
    """Write a pipeline execution report."""
    header = generate_report_header(
        title=f"Spatial Pipeline Report — {pipeline_result['pipeline']}",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={"Pipeline": pipeline_result["pipeline"]},
    )

    n_ok = pipeline_result["n_succeeded"]
    n_tot = pipeline_result["n_total"]
    body_lines = [
        "## Pipeline Summary\n",
        f"- **Pipeline**: {pipeline_result['pipeline']}",
        f"- **Steps**: {' → '.join(pipeline_result['steps'])}",
        f"- **Succeeded**: {n_ok}/{n_tot}",
        f"- **Status**: {'✅ All passed' if pipeline_result['success'] else '❌ Some failed'}",
        "",
        "### Step Results\n",
        "| Step | Status | Duration (s) |",
        "|------|--------|--------------|",
    ]
    for step, res in pipeline_result["results"].items():
        status = "✅" if res["success"] else "❌"
        body_lines.append(f"| {step} | {status} | {res['duration_seconds']:.1f} |")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)
    logger.info("Wrote %s", output_dir / "report.md")

    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary={
            "pipeline": pipeline_result["pipeline"],
            "n_succeeded": n_ok,
            "n_total": n_tot,
            "success": pipeline_result["success"],
        },
        data={"params": params, **pipeline_result},
    )

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = (
        f"python spatial_orchestrator.py "
        f"--pipeline {pipeline_result['pipeline']} "
        f"--input {input_file} --output {output_dir}"
    )
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Spatial Orchestrator — query routing and pipeline orchestration",
    )
    parser.add_argument("--query", "-q", default=None,
                        help="Natural language query to route to the best skill")
    parser.add_argument("--input", dest="input_path", default=None,
                        help="Input file (routes by file extension)")
    parser.add_argument("--output", dest="output_dir", default=None)
    parser.add_argument("--demo", action="store_true",
                        help="Run a routing demo on built-in example queries")
    parser.add_argument("--list-skills", action="store_true",
                        help="List all available skills and exit")
    parser.add_argument("--pipeline", default=None,
                        choices=list(NAMED_PIPELINES.keys()),
                        help="Run a named pipeline end-to-end")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    # --list-skills: no output dir needed
    if args.list_skills:
        skills = list_skills()
        print(f"\nOmicsClaw Skills ({len(skills)} registered)\n")
        print(f"{'Alias':<18} Description")
        print("-" * 70)
        for alias, desc in skills.items():
            print(f"  {alias:<16} {desc}")
        print()
        print("Named pipelines:", ", ".join(NAMED_PIPELINES.keys()))
        print()
        sys.exit(0)

    # Require --output for all other modes
    if not args.output_dir:
        print("ERROR: --output is required", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # --demo: showcase routing on example queries
    if args.demo:
        example_queries = [
            "find spatially variable genes in my tissue",
            "run cell communication analysis",
            "compute diffusion pseudotime for my cells",
            "I want to do pathway enrichment on marker genes",
            "run batch correction on multiple samples",
            "align serial sections from the same tissue",
            "detect copy number variations in tumor tissue",
        ]
        print("\nOrchestrator Demo — Query Routing Examples\n")
        print(f"{'Query':<50} {'→ Skill':<16} Confidence")
        print("-" * 80)
        demo_routes = []
        for q in example_queries:
            r = route_query(q)
            print(f"  {q[:48]:<50} → {r['skill']:<16} {r['confidence']:.2f}")
            demo_routes.append({
                "query": q,
                "skill": r["skill"],
                "confidence": r["confidence"],
                "keywords": r["matched_keywords"],
            })
        print()

        # Write demo report and result.json
        routing_summary = {
            "demo_routes": demo_routes,
            "total_skills": len(SKILL_DESCRIPTIONS),
            "total_keywords": len(KEYWORD_MAP),
            "named_pipelines": list(NAMED_PIPELINES.keys()),
        }

        header = generate_report_header(
            title="Spatial Orchestrator — Demo Report",
            skill_name=SKILL_NAME,
        )
        body_lines = [
            "## Routing Demo\n",
            f"- **Total skills**: {len(SKILL_DESCRIPTIONS)}",
            f"- **Keyword entries**: {len(KEYWORD_MAP)}",
            f"- **Named pipelines**: {', '.join(NAMED_PIPELINES.keys())}",
            "",
            "### Example Query Routing\n",
            "| Query | Routed Skill | Confidence |",
            "|-------|-------------|------------|",
        ]
        for r in demo_routes:
            q_short = r["query"][:45]
            body_lines.append(f"| {q_short} | `{r['skill']}` | {r['confidence']:.2f} |")

        body_lines.extend([
            "", "## All Skills\n",
            "| Alias | Description |",
            "|-------|-------------|",
        ])
        for alias, desc in SKILL_DESCRIPTIONS.items():
            body_lines.append(f"| `{alias}` | {desc} |")

        body_lines.extend(["", "## Named Pipelines\n"])
        for name, steps in NAMED_PIPELINES.items():
            body_lines.append(f"- **{name}**: {' → '.join(steps)}")

        footer = generate_report_footer()
        report = header + "\n".join(body_lines) + "\n" + footer
        (output_dir / "report.md").write_text(report)

        write_result_json(
            output_dir, skill=SKILL_NAME, version=SKILL_VERSION,
            summary=routing_summary,
            data={"demo_routes": demo_routes, "keyword_map_size": len(KEYWORD_MAP)},
        )

        repro_dir = output_dir / "reproducibility"
        repro_dir.mkdir(exist_ok=True)
        (repro_dir / "commands.sh").write_text(
            f"#!/bin/bash\npython spatial_orchestrator.py --demo --output {output_dir}\n"
        )

        print(f"Demo report written to {output_dir}")
        sys.exit(0)

    # --pipeline: run named pipeline
    if args.pipeline:
        if not args.input_path:
            print("ERROR: --pipeline requires --input", file=sys.stderr)
            sys.exit(1)
        print(f"Running pipeline '{args.pipeline}'...")
        pipeline_result = run_pipeline(
            args.pipeline,
            input_path=args.input_path,
            output_dir=output_dir,
            timeout=args.timeout,
        )
        params = {"pipeline": args.pipeline, "input": args.input_path}
        write_pipeline_report(output_dir, pipeline_result, args.input_path, params)
        n_ok = pipeline_result["n_succeeded"]
        n_tot = pipeline_result["n_total"]
        status = "✅" if pipeline_result["success"] else "❌"
        print(f"{status} Pipeline '{args.pipeline}': {n_ok}/{n_tot} steps succeeded")
        sys.exit(0 if pipeline_result["success"] else 1)

    # --query: text-based routing
    if args.query:
        routing = route_query(args.query)
        print(f"\nQuery: {args.query}")
        print(f"→ Recommended skill: {routing['skill']} (confidence: {routing['confidence']:.2f})")
        if routing["matched_keywords"]:
            print(f"  Matched keywords: {', '.join(routing['matched_keywords'])}")
        print(f"\nSuggested command:")
        print(f"  python omicsclaw.py run {routing['skill']} \\")
        inp_str = f"--input {args.input_path}" if args.input_path else "--input <your_data.h5ad>"
        print(f"    {inp_str} --output {output_dir}")

        params = {"query": args.query, "input": args.input_path}
        write_routing_report(output_dir, routing, args.query, args.input_path, params)
        sys.exit(0)

    # --input only: route by file extension
    if args.input_path:
        routing = route_file(args.input_path)
        print(f"\nInput: {args.input_path}")
        print(f"→ Recommended skill: {routing['skill']} (extension: {routing['extension']})")
        print(f"\nSuggested command:")
        print(f"  python omicsclaw.py run {routing['skill']} \\")
        print(f"    --input {args.input_path} --output {output_dir}")

        params = {"input": args.input_path}
        write_routing_report(output_dir, routing, None, args.input_path, params)
        sys.exit(0)

    # No action specified
    print("ERROR: Provide --query, --input, --pipeline, --list-skills, or --demo", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
