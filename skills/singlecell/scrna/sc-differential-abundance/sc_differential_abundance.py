#!/usr/bin/env python3
"""Single-cell differential abundance and compositional analysis."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import generate_report_footer, generate_report_header, write_output_readme, write_result_json
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.differential_abundance import (
    build_composition_summary,
    make_demo_da_adata,
    run_milo_da,
    run_sccoda_da,
    run_simple_da,
    save_heatmap,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-differential-abundance"
SKILL_VERSION = "0.1.0"


def _extract_backend(result_obj, default: str) -> str:
    if isinstance(result_obj, dict):
        return str(result_obj.get("backend", default))
    if hasattr(result_obj, "uns") and isinstance(getattr(result_obj, "uns"), dict):
        return str(result_obj.uns.get("backend", default))
    return default


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Single-cell differential abundance and compositional analysis")
    p.add_argument("--input", type=str, default=None)
    p.add_argument("--output", type=str, required=True)
    p.add_argument("--demo", action="store_true")
    p.add_argument("--method", type=str, default="milo", choices=["milo", "sccoda", "simple"])
    p.add_argument("--condition-key", type=str, default="condition")
    p.add_argument("--sample-key", type=str, default="sample")
    p.add_argument("--cell-type-key", type=str, default="cell_type")
    p.add_argument("--contrast", type=str, default=None, help="Example: control vs stim")
    p.add_argument("--reference-cell-type", type=str, default="automatic")
    p.add_argument("--fdr", type=float, default=0.05)
    p.add_argument("--prop", type=float, default=0.1)
    p.add_argument("--n-neighbors", type=int, default=30)
    p.add_argument("--min-count", type=int, default=10)
    return p.parse_args()


def _write_report(output_dir: Path, summary: dict, params: dict, input_path: str | None) -> None:
    backend = str(summary.get("backend", summary.get("method", "NA")))
    header = generate_report_header(
        title="Single-Cell Differential Abundance Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_path)] if input_path else None,
        extra_metadata={
            "Method": str(params.get("method", "NA")),
            "Backend": backend,
            "Condition key": str(params.get("condition_key", "condition")),
            "Sample key": str(params.get("sample_key", "sample")),
            "Cell type key": str(params.get("cell_type_key", "cell_type")),
        },
    )
    body = [
        "## Summary",
        "",
        f"- Requested method: `{params.get('method')}`",
        f"- Execution backend: `{backend}`",
        f"- Samples: `{summary.get('n_samples', 'NA')}`",
        f"- Cell types: `{summary.get('n_cell_types', 'NA')}`",
        f"- Significant hits: `{summary.get('n_significant', 'NA')}`",
        "",
        "## Interpretation",
        "",
        "- Differential abundance is a sample-aware comparison of cell-state or cell-type prevalence between biological conditions.",
        "- Prefer replicate-aware methods such as Milo or scCODA when you have multiple samples per condition.",
        "- Treat the exploratory `simple` mode as a lightweight proportion screen, not as a replacement for neighborhood- or Bayesian compositional models.",
    ]
    (output_dir / "report.md").write_text(header + "\n" + "\n".join(body) + "\n" + generate_report_footer(), encoding="utf-8")


def main() -> int:
    args = _parse_args()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = output_dir / "figures"
    tables_dir = output_dir / "tables"
    figures_dir.mkdir(exist_ok=True)
    tables_dir.mkdir(exist_ok=True)

    if args.demo:
        adata = make_demo_da_adata()
        input_checksum = ""
        input_path = None
    else:
        if not args.input:
            raise SystemExit("Provide --input or use --demo")
        adata = sc_io.smart_load(args.input, preserve_all=True)
        input_checksum = sha256_file(args.input)
        input_path = args.input

    counts, props, mean_props = build_composition_summary(
        adata,
        sample_key=args.sample_key,
        condition_key=args.condition_key,
        celltype_key=args.cell_type_key,
    )
    counts.to_csv(tables_dir / "sample_by_celltype_counts.csv")
    props.to_csv(tables_dir / "sample_by_celltype_proportions.csv")
    mean_props.to_csv(tables_dir / "condition_mean_proportions.csv")
    save_heatmap(props, figures_dir / "sample_celltype_proportions.png", "Sample-by-cell-type proportions")

    result_tables = {}
    summary = {
        "method": args.method,
        "backend": args.method,
        "n_samples": int(counts.shape[0]),
        "n_cell_types": int(counts.shape[1]),
    }

    if args.method == "simple":
        da = run_simple_da(
            adata,
            sample_key=args.sample_key,
            condition_key=args.condition_key,
            celltype_key=args.cell_type_key,
            contrast=args.contrast,
            fdr=args.fdr,
        )
        da.to_csv(tables_dir / "simple_da_results.csv", index=False)
        result_tables["simple_da_results"] = str(tables_dir / "simple_da_results.csv")
        summary.update(
            {
                "n_significant": int(da["significant"].sum()) if not da.empty else 0,
                "contrast": args.contrast or "auto",
            }
        )
    elif args.method == "milo":
        mdata, nhood = run_milo_da(
            adata,
            sample_key=args.sample_key,
            condition_key=args.condition_key,
            celltype_key=args.cell_type_key,
            prop=args.prop,
            n_neighbors=args.n_neighbors,
            contrast=args.contrast,
        )
        summary["backend"] = _extract_backend(mdata, args.method)
        nhood.to_csv(tables_dir / "milo_nhood_results.csv", index=False)
        result_tables["milo_nhood_results"] = str(tables_dir / "milo_nhood_results.csv")
        if {"nhood_annotation", "SpatialFDR", "logFC"}.issubset(nhood.columns):
            plot_df = nhood[["nhood_annotation", "SpatialFDR", "logFC"]].copy()
            plot_df = plot_df.dropna().sort_values("logFC")
            if not plot_df.empty:
                fig, ax = plt.subplots(figsize=(8, max(4, 0.25 * len(plot_df))))
                colors = ["#d73027" if x <= args.fdr else "#bdbdbd" for x in plot_df["SpatialFDR"]]
                ax.barh(plot_df["nhood_annotation"].astype(str), plot_df["logFC"], color=colors)
                ax.axvline(0, color="black", linestyle="--", linewidth=0.8)
                ax.set_title("Milo neighborhood logFC by annotation")
                fig.tight_layout()
                fig.savefig(figures_dir / "milo_logfc_barplot.png", dpi=200)
                plt.close(fig)
        summary.update(
            {
                "n_nhoods": int(len(nhood)),
                "n_significant": int((nhood.get("SpatialFDR", pd.Series(dtype=float)) <= args.fdr).sum()) if not nhood.empty else 0,
            }
        )
    else:
        mdata, effect_df = run_sccoda_da(
            adata,
            sample_key=args.sample_key,
            condition_key=args.condition_key,
            celltype_key=args.cell_type_key,
            reference_cell_type=args.reference_cell_type,
            fdr=args.fdr,
        )
        summary["backend"] = _extract_backend(mdata, args.method)
        effect_df.to_csv(tables_dir / "sccoda_effects.csv", index=False)
        result_tables["sccoda_effects"] = str(tables_dir / "sccoda_effects.csv")
        if "log2-fold change" in effect_df.columns:
            plot_df = effect_df.dropna(subset=["log2-fold change"]).copy()
            if not plot_df.empty:
                fig, ax = plt.subplots(figsize=(8, max(4, 0.3 * len(plot_df))))
                ax.barh(plot_df["Cell Type"].astype(str), plot_df["log2-fold change"].astype(float), color="#3182bd")
                ax.axvline(0, color="black", linestyle="--", linewidth=0.8)
                ax.set_title("scCODA log2-fold change")
                fig.tight_layout()
                fig.savefig(figures_dir / "sccoda_log2fc_barplot.png", dpi=200)
                plt.close(fig)
        summary.update(
            {
                "reference_cell_type": args.reference_cell_type,
                "n_effect_rows": int(len(effect_df)),
                "n_significant": int((effect_df.get("Final Parameter", pd.Series(dtype=float)) != 0).sum()) if not effect_df.empty and "Final Parameter" in effect_df.columns else 0,
            }
        )

    adata.uns["differential_abundance"] = summary.copy()
    annotated_h5ad = output_dir / "annotated_input.h5ad"
    adata.write_h5ad(annotated_h5ad)

    params = {
        "method": args.method,
        "condition_key": args.condition_key,
        "sample_key": args.sample_key,
        "cell_type_key": args.cell_type_key,
        "contrast": args.contrast,
        "reference_cell_type": args.reference_cell_type,
        "fdr": args.fdr,
        "prop": args.prop,
        "n_neighbors": args.n_neighbors,
        "min_count": args.min_count,
    }
    payload = {
        "params": params,
        "tables": result_tables,
        "outputs": {
            "figures_dir": str(figures_dir),
            "tables_dir": str(tables_dir),
            "annotated_h5ad": str(annotated_h5ad),
        },
    }
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, payload, input_checksum=input_checksum)
    _write_report(output_dir, summary, params, input_path)
    write_output_readme(
        output_dir,
        skill_alias=SKILL_NAME,
        description="Sample-aware differential abundance and compositional analysis for scRNA-seq.",
        preferred_method=args.method,
    )
    logger.info("Done: %s", output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
