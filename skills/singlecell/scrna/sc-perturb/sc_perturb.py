#!/usr/bin/env python3
"""Single-cell perturbation analysis with Mixscape."""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import scanpy as sc

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    load_result_json,
    write_result_json,
    write_replot_hint,
)
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.adata_utils import store_analysis_metadata
from skills.singlecell._lib.export import save_h5ad
from skills.singlecell._lib.perturbation import make_demo_perturb_adata, run_mixscape_workflow

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-perturb"
SKILL_VERSION = "0.1.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-perturb/sc_perturb.py"

# R Enhanced plotting configuration
R_ENHANCED_PLOTS = {
    # sc-perturb exports cell_type_counts.csv (class counts) for barplot renderer.
    # No UMAP/embedding CSV — embedding renderers not appropriate here.
    "plot_cell_barplot": "r_perturbation_barplot.png",
}


def _render_r_enhanced(output_dir: Path, figure_data_dir: Path, r_enhanced: bool) -> list[str]:
    """Render R Enhanced plots if requested. Returns list of generated paths."""
    if not r_enhanced:
        return []
    from skills.singlecell._lib.viz.r import call_r_plot
    r_figures_dir = output_dir / "figures" / "r_enhanced"
    r_figures_dir.mkdir(parents=True, exist_ok=True)
    r_figure_paths: list[str] = []
    for renderer, filename in R_ENHANCED_PLOTS.items():
        out_path = r_figures_dir / filename
        call_r_plot(renderer, figure_data_dir, out_path)
        if out_path.exists():
            r_figure_paths.append(str(out_path))
    return r_figure_paths


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Single-cell perturbation analysis")
    p.add_argument("--input", type=str, default=None)
    p.add_argument("--output", type=str, required=True)
    p.add_argument("--demo", action="store_true")
    p.add_argument("--method", type=str, default="mixscape", choices=["mixscape"])
    p.add_argument("--pert-key", type=str, default="perturbation")
    p.add_argument("--control", type=str, default="NT")
    p.add_argument("--split-by", type=str, default="replicate")
    p.add_argument("--n-neighbors", type=int, default=20)
    p.add_argument("--logfc-threshold", type=float, default=0.25)
    p.add_argument("--pval-cutoff", type=float, default=0.05)
    p.add_argument("--perturbation-type", type=str, default="KO")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--r-enhanced", action="store_true", help="Generate R Enhanced plots (requires R + ggplot2)")
    return p.parse_args()


def _detect_degenerate_output(global_counts: pd.DataFrame, class_counts: pd.DataFrame) -> dict:
    """Detect degenerate Mixscape output and return diagnostic info."""
    diagnostics: dict = {
        "all_non_perturbed": False,
        "single_global_class": False,
        "suggested_actions": [],
    }
    global_classes = set(global_counts["global_class"].astype(str))
    n_global = len(global_classes)

    # All cells classified as NP (non-perturbed)
    if n_global == 1 and "NP" in global_classes:
        diagnostics["all_non_perturbed"] = True
        diagnostics["suggested_actions"] = [
            "Lower the logfc-threshold: --logfc-threshold 0.1",
            "Lower the pval-cutoff: --pval-cutoff 0.1",
            "Verify perturbation labels in adata.obs match real perturbation conditions",
            "Ensure the data was preprocessed (normalized + log1p + PCA) before running",
        ]
    elif n_global == 1:
        diagnostics["single_global_class"] = True
        diagnostics["suggested_actions"] = [
            "Verify perturbation labels and control label are correct",
            "Lower the logfc-threshold: --logfc-threshold 0.1",
        ]

    return diagnostics


def _write_report(output_dir: Path, summary: dict, params: dict, input_path: str | None, diagnostics: dict) -> None:
    header = generate_report_header(
        title="Single-Cell Perturbation Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_path)] if input_path else None,
        extra_metadata={
            "Method": str(summary.get("method", "NA")),
            "Perturbation key": str(params.get("pert_key", "perturbation")),
            "Control": str(params.get("control", "NT")),
        },
    )
    body = [
        "## Summary",
        "",
        f"- Requested method: `{params.get('method')}`",
        f"- Execution backend: `{summary.get('method')}`",
        f"- Perturbation column: `{params.get('pert_key')}`",
        f"- Control label: `{params.get('control')}`",
        f"- Mixscape classes: `{summary.get('n_classes', 'NA')}`",
        f"- Global classes: `{summary.get('n_global_classes', 'NA')}`",
        "",
        "## Interpretation",
        "",
        "- Mixscape separates perturbation-expressing cells into perturbed versus non-perturbed subpopulations.",
        "- Use the global class counts first, then inspect perturbation-specific classes and posterior probabilities.",
    ]

    # Troubleshooting section for degenerate output
    if diagnostics.get("all_non_perturbed"):
        body.extend([
            "",
            "## Troubleshooting: All cells classified as non-perturbed (NP)",
            "",
            "### Cause 1: logfc-threshold too high",
            "The default threshold (0.25) may be too strict for subtle perturbations.",
            "```bash",
            f"python omicsclaw.py run sc-perturb --input <data.h5ad> --output <dir> --logfc-threshold 0.1",
            "```",
            "",
            "### Cause 2: Perturbation labels are incorrect",
            "Verify that the perturbation column and control label match the actual experimental setup.",
            "",
            "### Cause 3: Data not preprocessed",
            "Mixscape expects normalized + log1p + PCA data. Run `sc-preprocessing` first.",
        ])
    elif diagnostics.get("single_global_class"):
        body.extend([
            "",
            "## Troubleshooting: Only one global class detected",
            "",
            "This may indicate the perturbation signal is too weak or the labels are misconfigured.",
            "Try lowering `--logfc-threshold` or verifying the perturbation column.",
        ])

    (output_dir / "report.md").write_text(header + "\n" + "\n".join(body) + "\n" + generate_report_footer(), encoding="utf-8")


def _write_reproducibility(output_dir: Path, args: argparse.Namespace, input_path: str | None) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)

    command_parts = ["python", SCRIPT_REL_PATH]
    if args.demo:
        command_parts.append("--demo")
    elif input_path:
        command_parts.extend(["--input", input_path])
    command_parts.extend(["--output", str(output_dir)])
    if args.method != "mixscape":
        command_parts.extend(["--method", args.method])
    if args.pert_key != "perturbation":
        command_parts.extend(["--pert-key", args.pert_key])
    if args.control != "NT":
        command_parts.extend(["--control", args.control])
    if args.split_by != "replicate":
        command_parts.extend(["--split-by", args.split_by])
    if args.n_neighbors != 20:
        command_parts.extend(["--n-neighbors", str(args.n_neighbors)])
    if args.logfc_threshold != 0.25:
        command_parts.extend(["--logfc-threshold", str(args.logfc_threshold)])
    if args.pval_cutoff != 0.05:
        command_parts.extend(["--pval-cutoff", str(args.pval_cutoff)])
    if args.perturbation_type != "KO":
        command_parts.extend(["--perturbation-type", args.perturbation_type])

    command = " ".join(shlex.quote(part) for part in command_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")


def main() -> int:
    args = _parse_args()

    # -- Parameter validation --
    from skills.singlecell._lib.param_validators import ParamValidator
    v = ParamValidator(SKILL_NAME)
    v.positive("n_neighbors", args.n_neighbors, min_val=2)
    v.non_negative("logfc_threshold", args.logfc_threshold)
    v.fraction("pval_cutoff", args.pval_cutoff)
    v.check()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    figures_dir = output_dir / "figures"
    figure_data_dir = output_dir / "figure_data"
    tables_dir.mkdir(exist_ok=True)
    figures_dir.mkdir(exist_ok=True)
    figure_data_dir.mkdir(exist_ok=True)

    if args.demo:
        adata = make_demo_perturb_adata(seed=args.seed)
        input_checksum = ""
        input_path = None
    else:
        if not args.input:
            raise SystemExit("Provide --input or use --demo")
        adata = sc_io.smart_load(args.input, preserve_all=True)
        input_checksum = sha256_file(args.input)
        input_path = args.input

    # --- Preflight checks ---
    if args.pert_key not in adata.obs.columns:
        raise SystemExit(
            f"Perturbation column '{args.pert_key}' not found in adata.obs.\n"
            "\n"
            "How to fix:\n"
            "  Option 1 - Prepare assignments upstream:\n"
            "    python omicsclaw.py run sc-perturb-prep --input <expr.h5ad> --mapping-file <mapping.tsv> --output <dir>\n"
            "  Option 2 - Specify a different column:\n"
            f"    --pert-key <column_name>  (available: {', '.join(adata.obs.columns[:10])})\n"
        )
    if args.control not in set(adata.obs[args.pert_key].astype(str)):
        available_labels = sorted(adata.obs[args.pert_key].astype(str).unique())[:10]
        raise SystemExit(
            f"Control label '{args.control}' not found in adata.obs['{args.pert_key}'].\n"
            f"Available labels: {', '.join(available_labels)}\n"
            "\n"
            "How to fix:\n"
            f"  --control <label>  (pick one from above)\n"
        )

    # Check split-by column exists when specified
    if args.split_by and args.split_by not in adata.obs.columns:
        logger.warning(
            "split-by column '%s' not found in adata.obs; proceeding without replicate splitting.",
            args.split_by,
        )
        args.split_by = None

    if "X_pca" not in adata.obsm:
        logger.info("Computing PCA (X_pca not found in input).")
        sc.pp.pca(adata)

    result = run_mixscape_workflow(
        adata,
        pert_key=args.pert_key,
        control=args.control,
        split_by=args.split_by if args.split_by else None,
        n_neighbors=args.n_neighbors,
        logfc_threshold=args.logfc_threshold,
        pval_cutoff=args.pval_cutoff,
        perturbation_type=args.perturbation_type,
    )

    class_counts = result["class_counts"]
    global_counts = result["global_counts"]
    class_counts.to_csv(tables_dir / "mixscape_class_counts.csv", index=False)
    global_counts.to_csv(tables_dir / "mixscape_global_class_counts.csv", index=False)

    prob_col = result["probability_column"]
    prob_table = adata.obs[[args.pert_key, prob_col, result["class_column"], result["global_class_column"]]].copy()
    prob_table.to_csv(tables_dir / "mixscape_cell_classes.csv")

    # Save figure data for downstream customization
    global_counts.to_csv(figure_data_dir / "mixscape_global_classes.csv", index=False)
    class_counts.to_csv(figure_data_dir / "mixscape_class_counts.csv", index=False)

    # Write cell_type_counts.csv for plot_cell_barplot R renderer.
    # Renames 'class' -> 'cell_type' and adds proportion_pct column.
    try:
        ct_df = class_counts.rename(columns={"class": "cell_type"}).copy()
        total = ct_df["n_cells"].sum()
        ct_df["proportion_pct"] = (ct_df["n_cells"] / total * 100).round(2) if total > 0 else 0.0
        ct_df.to_csv(figure_data_dir / "cell_type_counts.csv", index=False)
    except Exception:
        pass

    manifest = {
        "skill": SKILL_NAME,
        "available_files": {
            "mixscape_class_counts": "mixscape_class_counts.csv",
            "mixscape_global_classes": "mixscape_global_classes.csv",
            "cell_type_counts": "cell_type_counts.csv",
        },
    }
    (figure_data_dir / "manifest.json").write_text(
        __import__("json").dumps(manifest, indent=2), encoding="utf-8"
    )

    fig, ax = plt.subplots(figsize=(8, 4))
    global_counts.plot.bar(x="global_class", y="n_cells", ax=ax, color="#1f78b4")
    ax.set_title("Mixscape global classes")
    fig.tight_layout()
    fig.savefig(figures_dir / "mixscape_global_classes.png", dpi=200)
    plt.close(fig)

    # --- Degenerate output detection ---
    diagnostics = _detect_degenerate_output(global_counts, class_counts)
    if diagnostics.get("all_non_perturbed"):
        print()
        print("  *** ALL cells were classified as non-perturbed (NP) - Mixscape found no perturbation signal. ***")
        print("  This usually means the perturbation effect is too weak for the current threshold,")
        print("  or the perturbation labels do not match real perturbation conditions.")
        print()
        print("  How to fix:")
        print("    Option 1 - Lower the logfc threshold:")
        print("      python omicsclaw.py run sc-perturb --input <data.h5ad> --output <dir> --logfc-threshold 0.1")
        print("    Option 2 - Lower the pval cutoff:")
        print("      python omicsclaw.py run sc-perturb --input <data.h5ad> --output <dir> --pval-cutoff 0.1")
        print("    Option 3 - Verify perturbation labels match the actual experiment")
        print()

    # --- Write contract metadata into AnnData ---
    # Preserve raw counts in layers if available
    if "counts" not in adata.layers:
        from skills.singlecell._lib.adata_utils import matrix_looks_count_like
        if matrix_looks_count_like(adata.X):
            adata.layers["counts"] = adata.X.copy()

    # Write matrix contract
    x_semantic = "normalized_expression"
    from skills.singlecell._lib.adata_utils import matrix_looks_count_like
    if matrix_looks_count_like(adata.X):
        x_semantic = "raw_counts"

    adata.uns["omicsclaw_input_contract"] = {
        "domain": "singlecell",
        "standardized": True,
        "standardized_by": SKILL_NAME,
        "version": "1.0",
    }
    adata.uns["omicsclaw_matrix_contract"] = {
        "X": x_semantic,
        "layers": {"counts": "raw_counts" if "counts" in adata.layers else None},
        "producer_skill": SKILL_NAME,
        "raw": "raw_counts_snapshot" if adata.raw is not None else None,
    }

    store_analysis_metadata(
        adata,
        SKILL_NAME,
        args.method,
        {
            "pert_key": args.pert_key,
            "control": args.control,
            "split_by": args.split_by,
            "n_neighbors": args.n_neighbors,
            "logfc_threshold": args.logfc_threshold,
            "pval_cutoff": args.pval_cutoff,
            "perturbation_type": args.perturbation_type,
        },
    )

    # --- Save processed.h5ad (canonical output name) ---
    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(adata, output_h5ad)

    summary = {
        "method": result["method"],
        "n_classes": int(class_counts["class"].nunique()),
        "n_global_classes": int(global_counts["global_class"].nunique()),
        "matrix_source": result["matrix_source"],
    }
    params = {
        "method": args.method,
        "pert_key": args.pert_key,
        "control": args.control,
        "split_by": args.split_by,
        "n_neighbors": args.n_neighbors,
        "logfc_threshold": args.logfc_threshold,
        "pval_cutoff": args.pval_cutoff,
        "perturbation_type": args.perturbation_type,
    }

    data_payload: dict = {
        "params": params,
        "outputs": {
            "mixscape_class_counts": str(tables_dir / "mixscape_class_counts.csv"),
            "mixscape_global_class_counts": str(tables_dir / "mixscape_global_class_counts.csv"),
            "mixscape_cell_classes": str(tables_dir / "mixscape_cell_classes.csv"),
            "processed_h5ad": str(output_h5ad),
        },
        "matrix_contract": adata.uns["omicsclaw_matrix_contract"],
    }
    if diagnostics.get("suggested_actions"):
        data_payload["perturbation_diagnostics"] = diagnostics

    data_payload["next_steps"] = [
        {"skill": "sc-de", "reason": "Differential expression between perturbed and control cells", "priority": "optional"},
        {"skill": "sc-enrichment", "reason": "Pathway enrichment on perturbation effects", "priority": "optional"},
    ]
    data_payload["r_enhanced_figures"] = []
    write_result_json(
        output_dir,
        SKILL_NAME,
        SKILL_VERSION,
        summary,
        data_payload,
        input_checksum=input_checksum,
    )

    # R Enhanced plots
    r_enhanced_figures = _render_r_enhanced(
        output_dir, output_dir / "figure_data", args.r_enhanced
    )
    if r_enhanced_figures:
        data_payload["r_enhanced_figures"] = r_enhanced_figures
        write_result_json(
            output_dir, SKILL_NAME, SKILL_VERSION, summary, data_payload,
            input_checksum=input_checksum,
        )
    write_replot_hint(output_dir, SKILL_NAME, R_ENHANCED_PLOTS)

    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME,
        "summary": summary,
        "data": data_payload,
    }
    _write_report(output_dir, summary, params, input_path, diagnostics)
    _write_reproducibility(output_dir, args, input_path)
    logger.info("Done: %s", output_dir)

    # --- Next-step guidance ---
    print()
    print(">> Next steps:")
    print(f"  - sc-de:         python omicsclaw.py run sc-de --input {output_dir}/processed.h5ad --output <dir>")
    print(f"  - sc-enrichment: python omicsclaw.py run sc-enrichment --input {output_dir}/processed.h5ad --output <dir>")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
