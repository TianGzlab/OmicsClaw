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
from omicsclaw.core.registry import registry
from omicsclaw.common.manifest import (
    PipelineManifest,
    StepRecord,
    read_manifest,
    write_manifest,
)
from omicsclaw.routing.router import route_keyword

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-orchestrator"
SKILL_VERSION = "0.2.0"
SCRIPT_REL_PATH = "skills/spatial/orchestrator/spatial_orchestrator.py"

# ---------------------------------------------------------------------------
# Routing maps — hardcoded fallback; SKILL.md trigger_keywords take priority
# ---------------------------------------------------------------------------

_FALLBACK_KEYWORD_MAP: dict[str, str] = {
    # Spatial Transcriptomics
    "qc": "spatial-preprocess",
    "quality control": "spatial-preprocess",
    "preprocess": "spatial-preprocess",
    "normalize": "spatial-preprocess",
    "normalise": "spatial-preprocess",
    "clustering": "spatial-preprocess",
    "leiden": "spatial-preprocess",
    "visium": "spatial-preprocess",
    "xenium": "spatial-preprocess",
    "merfish": "spatial-preprocess",
    # Spatial domains
    "spatial domain": "spatial-domains",
    "tissue region": "spatial-domains",
    "tissue domain": "spatial-domains",
    "niche": "spatial-domains",
    "spagcn": "spatial-domains",
    "stagate": "spatial-domains",
    "graphst": "spatial-domains",
    "banksy": "spatial-domains",
    # Cell type annotation
    "cell type annotation": "spatial-annotate",
    "cell type": "spatial-annotate",
    "cell assignment": "spatial-annotate",
    "tangram": "spatial-annotate",
    "scanvi": "spatial-annotate",
    "cellassign": "spatial-annotate",
    # Deconvolution
    "deconvolution": "spatial-deconv",
    "deconvolve": "spatial-deconv",
    "cell proportion": "spatial-deconv",
    "cell type proportion": "spatial-deconv",
    "card": "spatial-deconv",
    "cell2location": "spatial-deconv",
    "rctd": "spatial-deconv",
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
    "spatially variable gene": "spatial-genes",
    "spatially variable": "spatial-genes",
    "spatial gene": "spatial-genes",
    "svg": "spatial-genes",
    "spatialde": "spatial-genes",
    "spark": "spatial-genes",
    # Differential expression
    "differential expression": "spatial-de",
    "marker gene": "spatial-de",
    "marker genes": "spatial-de",
    "de analysis": "spatial-de",
    "wilcoxon": "spatial-de",
    # Condition comparison
    "condition comparison": "spatial-condition",
    "pseudobulk": "spatial-condition",
    "deseq2": "spatial-condition",
    "treatment vs control": "spatial-condition",
    "experimental condition": "spatial-condition",
    # Cell communication
    "cell communication": "spatial-communication",
    "cell-cell communication": "spatial-communication",
    "ligand receptor": "spatial-communication",
    "ligand-receptor": "spatial-communication",
    "liana": "spatial-communication",
    "cellphonedb": "spatial-communication",
    "fastccc": "spatial-communication",
    # RNA velocity
    "rna velocity": "spatial-velocity",
    "velocity": "spatial-velocity",
    "cellular dynamics": "spatial-velocity",
    "scvelo": "spatial-velocity",
    "velovi": "spatial-velocity",
    "velocity confidence": "spatial-velocity",
    "velocity pseudotime": "spatial-velocity",
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
    "multi-sample integration": "spatial-integrate",
    "multi sample integration": "spatial-integrate",
    "batch correction": "spatial-integrate",
    "batch effect": "spatial-integrate",
    "harmony": "spatial-integrate",
    "bbknn": "spatial-integrate",
    "scanorama": "spatial-integrate",
    "integration": "spatial-integrate",
    # Registration
    "spatial registration": "spatial-register",
    "slice alignment": "spatial-register",
    "paste": "spatial-register",
    "stalign": "spatial-register",
    "serial section": "spatial-register",
    "multi-slice": "spatial-register",
}


def _get_spatial_skill_catalog() -> dict[str, str]:
    """Build the current canonical spatial-skill catalog."""
    return {
        alias: desc
        for alias, desc in registry.build_skill_catalog(domain="spatial").items()
        if alias != SKILL_NAME
    }


def _get_keyword_map() -> dict[str, str]:
    """Build the canonical spatial keyword map, excluding the orchestrator itself."""
    return {
        keyword: alias
        for keyword, alias in registry.build_keyword_map(
            domain="spatial",
            fallback_map=_FALLBACK_KEYWORD_MAP,
        ).items()
        if alias != SKILL_NAME
    }


# Backward-compatible alias for EXTENSION_MAP (used in route_file)
EXTENSION_MAP: dict[str, str] = {
    ".h5ad": "spatial-preprocess",
    ".h5": "spatial-preprocess",
    ".zarr": "spatial-preprocess",
    ".loom": "spatial-preprocess",
    ".csv": "spatial-preprocess",
    ".txt": "spatial-preprocess",
}

# Named pipelines: ordered list of skill aliases to execute in sequence
NAMED_PIPELINES: dict[str, list[str]] = {
    "standard": [
        "spatial-preprocess",
        "spatial-domains",
        "spatial-de",
        "spatial-genes",
        "spatial-statistics",
    ],
    "full": [
        "spatial-preprocess",
        "spatial-domains",
        "spatial-de",
        "spatial-genes",
        "spatial-statistics",
        "spatial-communication",
        "spatial-enrichment",
    ],
    "integration": ["spatial-integrate", "spatial-domains", "spatial-de"],
    "spatial_only": ["spatial-preprocess", "spatial-genes", "spatial-statistics"],
    "cancer": ["spatial-preprocess", "spatial-cnv", "spatial-de", "spatial-enrichment"],
}


# ---------------------------------------------------------------------------
# Core routing logic
# ---------------------------------------------------------------------------


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
        "skill": "spatial-preprocess",
        "confidence": 0.0,
        "matched_keywords": [],
        "fallback_reason": "No keywords matched; defaulting to spatial-preprocess",
    }


def route_file(input_path: str) -> dict:
    """Route by input file extension."""
    ext = Path(input_path).suffix.lower()
    skill = EXTENSION_MAP.get(ext, "spatial-preprocess")
    return {
        "matched": ext in EXTENSION_MAP,
        "skill": skill,
        "extension": ext,
        "input_file": input_path,
    }


def list_skills() -> dict:
    """Return all registered skills with descriptions."""
    return _get_spatial_skill_catalog()


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
    """Execute a named pipeline, chaining processed.h5ad between steps.

    Each step's output directory gets a ``manifest.json`` that records
    the full execution lineage up to that point.
    """
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
    upstream_manifest: PipelineManifest | None = None

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

        # Build manifest for this step
        processed = step_out / "processed.h5ad"
        step_record = StepRecord(
            skill=step,
            version="",  # version is recorded inside the skill's own result.json
            input_file=current_input,
            output_file=str(processed) if processed.exists() else "",
            params={},
        )
        write_manifest(step_out, step_record, upstream=upstream_manifest)

        # Read back (includes this step) as upstream for next
        upstream_manifest = read_manifest(step_out)

        # Chain: pass processed.h5ad to the next step
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
    desc = list_skills().get(skill, "")
    if desc:
        body_lines.extend(["", f"### About `{skill}`\n", desc])

    body_lines.extend([
        "", "### Suggested Command\n",
        "```bash",
        f"oc run {skill} --input <your_data.h5ad> --output /tmp/{skill}_output",
        "```",
    ])

    body_lines.extend(["", "## Available Skills\n"])
    body_lines.append("| Alias | Description |")
    body_lines.append("|-------|-------------|")
    for alias, desc in list_skills().items():
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
    cmd = f"python {SCRIPT_REL_PATH}"
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
        f"python {SCRIPT_REL_PATH} "
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
        keyword_map = _get_keyword_map()
        skills = list_skills()
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
            "total_skills": len(skills),
            "total_keywords": len(keyword_map),
            "named_pipelines": list(NAMED_PIPELINES.keys()),
        }

        header = generate_report_header(
            title="Spatial Orchestrator — Demo Report",
            skill_name=SKILL_NAME,
        )
        body_lines = [
            "## Routing Demo\n",
            f"- **Total skills**: {len(skills)}",
            f"- **Keyword entries**: {len(keyword_map)}",
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
        for alias, desc in skills.items():
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
            data={"demo_routes": demo_routes, "keyword_map_size": len(keyword_map)},
        )

        repro_dir = output_dir / "reproducibility"
        repro_dir.mkdir(exist_ok=True)
        (repro_dir / "commands.sh").write_text(
            f"#!/bin/bash\npython {SCRIPT_REL_PATH} --demo --output {output_dir}\n"
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
        print(f"  oc run {routing['skill']} \\")
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
        print(f"  oc run {routing['skill']} \\")
        print(f"    --input {args.input_path} --output {output_dir}")

        params = {"input": args.input_path}
        write_routing_report(output_dir, routing, None, args.input_path, params)
        sys.exit(0)

    # No action specified
    print("ERROR: Provide --query, --input, --pipeline, --list-skills, or --demo", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
