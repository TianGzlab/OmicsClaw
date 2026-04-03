#!/usr/bin/env python3
"""Prepare velocity-ready AnnData inputs for scVelo."""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import numpy as np
import pandas as pd

try:
    import anndata

    anndata.settings.allow_write_nullable_strings = True
except Exception:
    pass

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    load_result_json,
    write_repro_requirements,
    write_result_json,
    write_standard_run_artifacts,
)
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.adata_utils import record_standardized_input_contract, store_analysis_metadata
from skills.singlecell._lib.export import save_h5ad
from skills.singlecell._lib.upstream import (
    choose_fastq_sample,
    detect_cellranger_bam_and_barcodes,
    detect_starsolo_output,
    discover_fastq_samples,
    find_starsolo_velocyto_dir,
    guess_starsolo_whitelist,
    load_loom_velocity,
    load_starsolo_velocyto_dir,
    merge_velocity_layers,
    run_starsolo_count,
    run_velocyto_from_bam,
)
from skills.singlecell._lib.viz import plot_velocity_gene_balance, plot_velocity_layer_summary

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-velocity-prep"
SKILL_VERSION = "0.1.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-velocity-prep/sc_velocity_prep.py"


def _demo_velocity_adata():
    adata, demo_path = sc_io.load_repo_demo_data("pbmc3k_raw")
    counts = adata.X.copy()
    spliced = counts.multiply(0.82) if hasattr(counts, "multiply") else counts * 0.82
    unspliced = counts.multiply(0.14) if hasattr(counts, "multiply") else counts * 0.14
    ambiguous = counts.multiply(0.04) if hasattr(counts, "multiply") else counts * 0.04
    demo = adata.copy()
    demo.layers["counts"] = counts.copy()
    demo.layers["spliced"] = spliced.copy()
    demo.layers["unspliced"] = unspliced.copy()
    demo.layers["ambiguous"] = ambiguous.copy()
    demo.X = counts.copy()
    return demo, str(demo_path) if demo_path else None


def _layer_summary_df(adata) -> pd.DataFrame:
    rows = []
    for layer_name in ("spliced", "unspliced", "ambiguous"):
        if layer_name in adata.layers:
            rows.append(
                {
                    "layer": layer_name,
                    "molecules": float(np.asarray(adata.layers[layer_name].sum()).ravel()[0]),
                }
            )
    return pd.DataFrame(rows)


def _top_velocity_genes_df(adata, n_top: int = 40) -> pd.DataFrame:
    if "spliced" not in adata.layers or "unspliced" not in adata.layers:
        return pd.DataFrame(columns=["gene", "spliced", "unspliced", "ambiguous"])
    spliced = np.asarray(adata.layers["spliced"].sum(axis=0)).ravel()
    unspliced = np.asarray(adata.layers["unspliced"].sum(axis=0)).ravel()
    ambiguous = np.asarray(adata.layers["ambiguous"].sum(axis=0)).ravel() if "ambiguous" in adata.layers else np.zeros_like(spliced)
    frame = pd.DataFrame(
        {
            "gene": adata.var_names.astype(str),
            "spliced": spliced,
            "unspliced": unspliced,
            "ambiguous": ambiguous,
        }
    )
    frame["total"] = frame["spliced"] + frame["unspliced"] + frame["ambiguous"]
    return frame.sort_values("total", ascending=False).head(n_top).drop(columns=["total"]).reset_index(drop=True)


def _write_figure_data_manifest(output_dir: Path, manifest: dict) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    (figure_data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _export_tables(output_dir: Path, layer_summary: pd.DataFrame, gene_summary: pd.DataFrame) -> dict[str, str]:
    tables_dir = output_dir / "tables"
    figure_data_dir = output_dir / "figure_data"
    tables_dir.mkdir(parents=True, exist_ok=True)
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "layer_summary": "velocity_layer_summary.csv",
        "gene_summary": "top_velocity_genes.csv",
    }
    layer_summary.to_csv(tables_dir / files["layer_summary"], index=False)
    gene_summary.to_csv(tables_dir / files["gene_summary"], index=False)
    layer_summary.to_csv(figure_data_dir / files["layer_summary"], index=False)
    gene_summary.to_csv(figure_data_dir / files["gene_summary"], index=False)
    _write_figure_data_manifest(
        output_dir,
        {
            "skill": SKILL_NAME,
            "available_files": {
                "velocity_layer_summary": files["layer_summary"],
                "top_velocity_genes": files["gene_summary"],
            },
        },
    )
    return files


def _write_reproducibility(output_dir: Path, args: argparse.Namespace, *, demo_mode: bool) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)
    command_parts = ["python", SCRIPT_REL_PATH]
    if demo_mode:
        command_parts.append("--demo")
    elif args.input_path:
        command_parts.extend(["--input", args.input_path])
    command_parts.extend(["--output", str(output_dir), "--method", args.method])
    if args.base_h5ad:
        command_parts.extend(["--base-h5ad", args.base_h5ad])
    if args.gtf:
        command_parts.extend(["--gtf", args.gtf])
    if args.reference:
        command_parts.extend(["--reference", args.reference])
    if args.read2:
        command_parts.extend(["--read2", args.read2])
    if args.sample:
        command_parts.extend(["--sample", args.sample])
    if args.threads != 8:
        command_parts.extend(["--threads", str(args.threads)])
    if args.chemistry != "auto":
        command_parts.extend(["--chemistry", args.chemistry])
    if args.whitelist:
        command_parts.extend(["--whitelist", args.whitelist])
    command = " ".join(shlex.quote(part) for part in command_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")
    write_repro_requirements(output_dir, ["scanpy", "anndata", "numpy", "pandas", "matplotlib"])


def _write_report(
    output_dir: Path,
    *,
    summary: dict,
    input_file: str | None,
    artifact_info: dict[str, object],
    layer_summary: pd.DataFrame,
) -> None:
    header = generate_report_header(
        title="Single-Cell Velocity Prep Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file and Path(input_file).is_file() else None,
        extra_metadata={
            "Method": summary["method"],
            "Cells": str(summary["n_cells"]),
            "Genes": str(summary["n_genes"]),
        },
    )
    lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Cells in velocity-ready object**: {summary['n_cells']:,}",
        f"- **Genes in velocity-ready object**: {summary['n_genes']:,}",
        f"- **Merged into base h5ad**: {summary['used_base_h5ad']}",
        "",
        "## Velocity Layer Totals\n",
    ]
    for _, row in layer_summary.iterrows():
        lines.append(f"- **{row['layer']}**: {row['molecules']:.0f}")

    lines.extend(["", "## Source Artifacts\n"])
    for key, value in artifact_info.items():
        lines.append(f"- **{key}**: {value}")

    lines.extend(
        [
            "",
            "## Output Files\n",
            "- `velocity_input.h5ad` — velocity-ready AnnData with `spliced` and `unspliced` layers",
            "- `figures/velocity_layer_summary.png` — total molecules per velocity layer",
            "- `figures/velocity_gene_balance.png` — top-gene spliced versus unspliced balance",
            "- `tables/velocity_layer_summary.csv` — layer totals",
            "- `tables/top_velocity_genes.csv` — top genes by velocity-layer abundance",
            "",
            "## Recommended Next Step\n",
            "- Continue with `sc-velocity` on `velocity_input.h5ad`.",
        ]
    )
    (output_dir / "report.md").write_text(header + "\n".join(lines) + "\n" + generate_report_footer(), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare velocity-ready AnnData objects for scVelo.")
    parser.add_argument("--input", dest="input_path", help="Cell Ranger output, STARsolo output, FASTQ path, or loom file")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run built-in demo mode")
    parser.add_argument("--method", choices=["velocyto", "starsolo"], default="velocyto", help="Velocity preparation backend")
    parser.add_argument("--gtf", help="GTF file required for BAM-backed velocyto runs")
    parser.add_argument("--base-h5ad", help="Optional existing AnnData to merge velocity layers into")
    parser.add_argument("--reference", help="STAR genome directory for FASTQ-backed STARsolo runs")
    parser.add_argument("--sample", help="Choose one sample from a multi-sample FASTQ directory")
    parser.add_argument("--read2", help="Explicit mate FASTQ when --input points to one file")
    parser.add_argument("--threads", type=int, default=8, help="Backend thread count")
    parser.add_argument("--chemistry", default="auto", help="STARsolo chemistry; real FASTQ runs require explicit 10xv2, 10xv3, or 10xv4")
    parser.add_argument("--whitelist", help="STARsolo barcode whitelist file")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    execution = None
    artifact_info: dict[str, object] = {}

    if args.demo:
        velocity_adata, input_file = _demo_velocity_adata()
        artifact_info = {"source": "demo"}
    else:
        if not args.input_path:
            parser.error("--input required when not using --demo")
        input_path = Path(args.input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input path not found: {input_path}")
        input_file = str(input_path)

        if args.method == "velocyto":
            if input_path.suffix.lower() == ".loom":
                velocity_adata = load_loom_velocity(input_path)
                artifact_info = {"loom_path": str(input_path)}
            else:
                if not args.gtf:
                    raise ValueError("BAM-backed velocyto preparation requires `--gtf`.")
                bam_path, barcode_path = detect_cellranger_bam_and_barcodes(input_path)
                sample_id = args.sample or input_path.name
                loom_path, execution = run_velocyto_from_bam(
                    bam_path=bam_path,
                    barcode_path=barcode_path,
                    gtf_path=args.gtf,
                    output_dir=output_dir,
                    sample_id=sample_id,
                    threads=args.threads,
                )
                velocity_adata = load_loom_velocity(loom_path)
                artifact_info = {
                    "bam_path": str(bam_path),
                    "barcode_path": str(barcode_path),
                    "loom_path": str(loom_path),
                }
        else:
            if detect_starsolo_output(input_path) or find_starsolo_velocyto_dir(input_path):
                velocity_adata, velo_dir = load_starsolo_velocyto_dir(input_path)
                artifact_info = {"starsolo_velocyto_dir": str(velo_dir)}
            else:
                if not args.reference:
                    raise ValueError("FASTQ-backed STARsolo velocity preparation requires `--reference`.")
                if args.chemistry == "auto":
                    raise ValueError("FASTQ-backed STARsolo velocity preparation requires an explicit `--chemistry`.")
                samples = discover_fastq_samples(input_path, read2=args.read2, sample=args.sample)
                sample = choose_fastq_sample(samples, sample=args.sample)
                whitelist = Path(args.whitelist) if args.whitelist else guess_starsolo_whitelist(args.reference, args.chemistry)
                if whitelist is None:
                    raise ValueError(
                        "Could not infer a compatible STARsolo whitelist. Pass `--whitelist <barcode_whitelist.txt>` explicitly."
                    )
                artifacts, execution = run_starsolo_count(
                    sample,
                    reference=args.reference,
                    output_dir=output_dir,
                    threads=args.threads,
                    chemistry=args.chemistry,
                    whitelist=whitelist,
                    features=("Gene", "Velocyto"),
                )
                velocity_adata, velo_dir = load_starsolo_velocyto_dir(artifacts.run_dir)
                artifact_info = {
                    "starsolo_run_dir": str(artifacts.run_dir),
                    "starsolo_velocyto_dir": str(velo_dir),
                    "bam_path": str(artifacts.bam_path) if artifacts.bam_path else "",
                }

    if args.base_h5ad:
        base_adata = sc_io.smart_load(args.base_h5ad, skill_name=SKILL_NAME, preserve_all=True)
        output_adata = merge_velocity_layers(base_adata, velocity_adata)
        used_base = True
    else:
        output_adata = velocity_adata.copy()
        used_base = False

    contract = record_standardized_input_contract(
        output_adata,
        expression_source=f"{args.method}.velocity_layers" if not args.demo else "demo.velocity_layers",
        gene_name_source="var.gene_symbols" if "gene_symbols" in output_adata.var.columns else "var_names",
        warnings=[],
        standardizer_skill=SKILL_NAME,
    )
    store_analysis_metadata(output_adata, SKILL_NAME, args.method if not args.demo else "demo", {"used_base_h5ad": used_base})
    output_adata.uns.setdefault("omicsclaw_velocity_prep", {})
    output_adata.uns["omicsclaw_velocity_prep"].update(artifact_info)
    output_adata.uns["omicsclaw_velocity_prep"]["used_base_h5ad"] = used_base

    layer_summary = _layer_summary_df(output_adata)
    gene_summary = _top_velocity_genes_df(output_adata)
    table_files = _export_tables(output_dir, layer_summary, gene_summary)
    plot_velocity_layer_summary(layer_summary, output_dir)
    plot_velocity_gene_balance(gene_summary, output_dir)
    _write_reproducibility(output_dir, args, demo_mode=args.demo)

    output_h5ad = output_dir / "velocity_input.h5ad"
    save_h5ad(output_adata, output_h5ad)

    summary = {
        "method": args.method if not args.demo else "demo",
        "n_cells": int(output_adata.n_obs),
        "n_genes": int(output_adata.n_vars),
        "used_base_h5ad": bool(used_base),
        "spliced_layer_present": "spliced" in output_adata.layers,
        "unspliced_layer_present": "unspliced" in output_adata.layers,
    }
    _write_report(output_dir, summary=summary, input_file=input_file, artifact_info=artifact_info, layer_summary=layer_summary)

    checksum = sha256_file(input_file) if input_file and Path(input_file).is_file() else ""
    result_data = {
        "method": args.method if not args.demo else "demo",
        "params": {
            "base_h5ad": args.base_h5ad or "",
            "gtf": args.gtf or "",
            "reference": args.reference or "",
            "sample": args.sample or "",
            "threads": int(args.threads),
            "chemistry": args.chemistry,
            "whitelist": args.whitelist or "",
        },
        "input_contract": contract,
        "artifacts": artifact_info,
        "visualization": {
            "available_figure_data": {
                "velocity_layer_summary": table_files["layer_summary"],
                "top_velocity_genes": table_files["gene_summary"],
            }
        },
        "execution": list(execution.command) if execution is not None else [],
    }
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    result_payload = load_result_json(output_dir) or {"skill": SKILL_NAME, "summary": summary, "data": result_data}
    write_standard_run_artifacts(
        output_dir,
        skill_alias=SKILL_NAME,
        description="Prepare RNA-velocity-ready inputs by generating or importing spliced and unspliced count layers.",
        result_payload=result_payload,
        preferred_method=summary["method"],
        script_path=Path(__file__).resolve(),
        actual_command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
    )

    print(f"\n{'=' * 60}")
    print(f"Success: {SKILL_NAME} v{SKILL_VERSION}")
    print(f"{'=' * 60}")
    print(f"  Output directory: {output_dir}")
    print(f"  Velocity-ready cells: {summary['n_cells']:,}")
    print(f"  Velocity-ready genes: {summary['n_genes']:,}")
    print(f"  Output object: {output_h5ad}")
    print(f"  Base h5ad merged: {summary['used_base_h5ad']}")


if __name__ == "__main__":
    main()
