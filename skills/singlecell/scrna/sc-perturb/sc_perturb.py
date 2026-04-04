#!/usr/bin/env python3
"""Single-cell perturbation analysis with Mixscape."""

from __future__ import annotations

import argparse
import logging
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
from omicsclaw.common.report import generate_report_footer, generate_report_header, write_output_readme, write_result_json
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.perturbation import make_demo_perturb_adata, run_mixscape_workflow

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-perturb"
SKILL_VERSION = "0.1.0"


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
    return p.parse_args()


def _write_report(output_dir: Path, summary: dict, params: dict, input_path: str | None) -> None:
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
        "",
        "## Interpretation",
        "",
        "- Mixscape separates perturbation-expressing cells into perturbed versus non-perturbed subpopulations.",
        "- Use the global class counts first, then inspect perturbation-specific classes and posterior probabilities.",
    ]
    (output_dir / "report.md").write_text(header + "\n" + "\n".join(body) + "\n" + generate_report_footer(), encoding="utf-8")


def main() -> int:
    args = _parse_args()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    figures_dir = output_dir / "figures"
    tables_dir.mkdir(exist_ok=True)
    figures_dir.mkdir(exist_ok=True)

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

    if args.pert_key not in adata.obs.columns:
        raise SystemExit(
            f"Perturbation column '{args.pert_key}' not found in adata.obs. "
            "Prepare barcode-to-guide assignments first, for example with `sc-perturb-prep`."
        )
    if args.control not in set(adata.obs[args.pert_key].astype(str)):
        raise SystemExit(
            f"Control label '{args.control}' not found in adata.obs['{args.pert_key}']. "
            "Confirm the perturbation column and control label before running Mixscape."
        )

    if "X_pca" not in adata.obsm:
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

    fig, ax = plt.subplots(figsize=(8, 4))
    global_counts.plot.bar(x="global_class", y="n_cells", ax=ax, color="#1f78b4")
    ax.set_title("Mixscape global classes")
    fig.tight_layout()
    fig.savefig(figures_dir / "mixscape_global_classes.png", dpi=200)
    plt.close(fig)

    annotated_h5ad = output_dir / "perturbation_annotated.h5ad"
    adata.write_h5ad(annotated_h5ad)

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
    write_result_json(
        output_dir,
        SKILL_NAME,
        SKILL_VERSION,
        summary,
        {
            "params": params,
            "outputs": {
                "mixscape_class_counts": str(tables_dir / "mixscape_class_counts.csv"),
                "mixscape_global_class_counts": str(tables_dir / "mixscape_global_class_counts.csv"),
                "mixscape_cell_classes": str(tables_dir / "mixscape_cell_classes.csv"),
                "annotated_h5ad": str(annotated_h5ad),
            },
        },
        input_checksum=input_checksum,
    )
    _write_report(output_dir, summary, params, input_path)
    write_output_readme(
        output_dir,
        skill_alias=SKILL_NAME,
        description="Single-cell perturbation analysis with Mixscape.",
        preferred_method=args.method,
    )
    logger.info("Done: %s", output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
