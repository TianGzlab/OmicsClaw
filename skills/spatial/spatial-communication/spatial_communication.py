#!/usr/bin/env python3
"""Spatial Communication — ligand-receptor interaction analysis.

Supported methods:
  liana        LIANA+ multi-method consensus ranking (default)
  cellphonedb  CellPhoneDB statistical permutation test
  fastccc      FastCCC FFT-based communication (no permutation, fastest)
  cellchat_r   CellChat via R

Core analysis functions are in skills.spatial._lib.communication.

Usage:
    python spatial_communication.py --input <preprocessed.h5ad> --output <dir>
    python spatial_communication.py --input <data.h5ad> --output <dir> --method liana
    python spatial_communication.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import scanpy as sc

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    write_result_json,
)
from skills.spatial._lib.adata_utils import store_analysis_metadata
from skills.spatial._lib.communication import run_communication, SUPPORTED_METHODS
from skills.spatial._lib.viz_utils import save_figure
from skills.spatial._lib.viz import VizParams, plot_communication

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-communication"
SKILL_VERSION = "0.2.0"


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(adata, output_dir: Path, summary: dict) -> list[str]:
    """Generate CCC visualizations using the OmicsClaw viz library."""
    import matplotlib.pyplot as plt

    figures: list[str] = []

    try:
        fig = plot_communication(adata, VizParams(), subtype="dotplot", top_n=20)
        p = save_figure(fig, output_dir, "lr_dotplot.png")
        figures.append(str(p))
        plt.close('all')
    except Exception as exc:
        logger.warning("LR dotplot failed: %s", exc)

    try:
        fig = plot_communication(adata, VizParams(), subtype="heatmap", top_n=20)
        p = save_figure(fig, output_dir, "lr_heatmap.png")
        figures.append(str(p))
        plt.close('all')
    except Exception as exc:
        logger.warning("LR heatmap failed: %s", exc)

    if any("spatial_scores" in k for k in adata.obsm.keys()):
        try:
            fig = plot_communication(adata, VizParams(), subtype="spatial", top_n=5)
            p = save_figure(fig, output_dir, "lr_spatial.png")
            figures.append(str(p))
            plt.close('all')
        except Exception as exc:
            logger.warning("LR spatial map failed: %s", exc)

    return figures


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def write_report(
    output_dir: Path, summary: dict, input_file: str | None, params: dict,
) -> None:
    header = generate_report_header(
        title="Spatial Cell-Cell Communication Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary.get("method", ""),
            "Cell type key": summary.get("cell_type_key", ""),
        },
    )

    top_df = summary.get("top_df", pd.DataFrame())
    body_lines = [
        "## Summary\n",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Cell types**: {summary['n_cell_types']}",
        f"- **Method**: {summary['method']}",
        f"- **L-R pairs tested**: {summary['n_interactions_tested']}",
        f"- **Significant (p < 0.05)**: {summary['n_significant']}",
    ]

    if not top_df.empty:
        body_lines.extend(["", "### Top Interactions\n"])
        body_lines.append("| Ligand | Receptor | Source | Target | Score |")
        body_lines.append("|--------|----------|--------|--------|-------|")
        for _, r in top_df.head(15).iterrows():
            body_lines.append(
                f"| {r['ligand']} | {r['receptor']} | {r['source']} | {r['target']} | {r['score']:.4f} |"
            )

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(
        output_dir, skill=SKILL_NAME, version=SKILL_VERSION,
        summary={k: v for k, v in summary.items() if k not in ("lr_df", "top_df")},
        data={"params": params},
        input_checksum=checksum,
    )

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    lr_df = summary.get("lr_df", pd.DataFrame())
    if not lr_df.empty:
        lr_df.to_csv(tables_dir / "lr_interactions.csv", index=False)
        if not top_df.empty:
            top_df.head(50).to_csv(tables_dir / "top_interactions.csv", index=False)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = (
        f"python spatial_communication.py --input <input.h5ad>"
        f" --method {params.get('method', 'liana')}"
        f" --cell-type-key {params.get('cell_type_key', 'leiden')}"
        f" --output {output_dir}"
    )
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    from importlib.metadata import version as _ver, PackageNotFoundError
    env_lines = []
    for pkg in ["scanpy", "anndata", "liana", "numpy", "pandas"]:
        try:
            env_lines.append(f"{pkg}=={_ver(pkg)}")
        except PackageNotFoundError:
            pass
    (repro_dir / "environment.txt").write_text("\n".join(env_lines) + "\n")


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------


def get_demo_data() -> tuple:
    preprocess_script = (
        _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    )
    if not preprocess_script.exists():
        raise FileNotFoundError(f"spatial-preprocess not found at {preprocess_script}")

    with tempfile.TemporaryDirectory(prefix="spatial_comm_demo_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        logger.info("Generating demo data via spatial-preprocess ...")
        result = subprocess.run(
            [sys.executable, str(preprocess_script), "--demo", "--output", str(tmp_path)],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(f"spatial-preprocess --demo failed:\n{result.stderr}")
        processed = tmp_path / "processed.h5ad"
        if not processed.exists():
            raise FileNotFoundError(f"Expected {processed}")
        adata = sc.read_h5ad(processed)
        logger.info("Demo: %d cells × %d genes", adata.n_obs, adata.n_vars)

        # Inject realistic gene names so LIANA's built-in resource can match them.
        valid_genes = [
            "A1BG", "A2M", "AANAT", "ABCA1", "ACE", "ACKR1", "ACKR2", "ACKR3", "ACKR4", "ACTR2", 
            "ACVR1", "ACVR1B", "ACVR1C", "ACVR2A", "ACVR2B", "ACVRL1", "ADA", "ADAM10", "ADAM11", "ADAM12", 
            "ADAM15", "ADAM17", "ADAM2", "ADAM22", "ADAM23", "ADAM28", "ADAM29", "ADAM7", "ADAM9", "ADAMTS3", 
            "ADCY1", "ADCY7", "ADCY8", "ADCY9", "ADCYAP1", "ADCYAP1R1", "ADGRA2", "ADGRB1", "ADGRE2", "ADGRE5", 
            "ADGRG1", "ADGRG3", "ADGRG5", "ADGRL1", "ADGRL4", "ADGRV1", "ADIPOQ", "ADIPOR1", "ADIPOR2", "ADM", 
            "ADM2", "ADO", "ADORA1", "ADORA2A", "ADORA2B", "ADORA3", "ADRA2A", "ADRA2B", "ADRB1", "ADRB2", 
            "ADRB3", "AFDN", "AGER", "AGR2", "AGRN", "AGRP", "AGT", "AGTR1", "AGTR2", "AGTRAP", 
            "AHSG", "AIMP1", "ALB", "ALCAM", "ALK", "ALKAL1", "ALKAL2", "ALOX5", "AMBN", "AMELX", 
            "AMELY", "AMFR", "AMH", "AMHR2", "ANG", "ANGPT1", "ANGPT2", "ANGPT4", "ANGPTL1", "ANGPTL2", 
            "ANGPTL3", "ANGPTL4", "ANGPTL7", "ANOS1", "ANTXR1", "ANXA1", "ANXA2", "APCDD1", "APELA", "APLN"
        ]
        # Pad with dummies if somehow n_vars > 100
        if adata.n_vars > len(valid_genes):
            valid_genes += [f"Gene_dummy_{i}" for i in range(adata.n_vars - len(valid_genes))]
        valid_genes = valid_genes[:adata.n_vars]
        adata.var_names = valid_genes

        # LIANA reads from `.raw` when available, so keep raw gene symbols aligned.
        if adata.raw is not None:
            raw_adata = adata.raw.to_adata()
            if raw_adata.n_vars == len(valid_genes):
                raw_adata.var_names = valid_genes
                adata.raw = raw_adata
            else:
                logger.warning(
                    "Demo raw matrix gene count (%d) did not match processed matrix (%d); "
                    "refreshing `.raw` from the processed matrix for LIANA demo compatibility.",
                    raw_adata.n_vars,
                    len(valid_genes),
                )
                adata.raw = adata.copy()
        
        return adata, None

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Spatial Communication — ligand-receptor interaction analysis\n"
                    "Requires: pip install liana  (for default LIANA+ method)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument(
        "--method", default="liana", choices=list(SUPPORTED_METHODS),
    )
    parser.add_argument("--cell-type-key", default="leiden")
    parser.add_argument("--species", default="human", choices=["human", "mouse", "zebrafish"])
    parser.add_argument("--n-perms", type=int, default=100)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
    elif args.input_path:
        if not Path(args.input_path).exists():
            print(f"ERROR: Input not found: {args.input_path}", file=sys.stderr)
            sys.exit(1)
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
    else:
        print("ERROR: Provide --input <file.h5ad> or --demo", file=sys.stderr)
        sys.exit(1)

    params = {
        "method": args.method,
        "cell_type_key": args.cell_type_key,
        "species": args.species,
        "n_perms": args.n_perms,
    }

    summary = run_communication(
        adata,
        method=args.method,
        cell_type_key=args.cell_type_key,
        species=args.species,
        n_perms=args.n_perms,
    )

    generate_figures(adata, output_dir, summary)
    write_report(output_dir, summary, input_file, params)

    store_analysis_metadata(
        adata, SKILL_NAME, summary["method"],
        params=params,
    )

    adata.write_h5ad(output_dir / "processed.h5ad")
    logger.info("Saved: %s", output_dir / "processed.h5ad")

    print(
        f"Communication complete ({summary['method']}): "
        f"{summary['n_interactions_tested']} L-R pairs, "
        f"{summary['n_significant']} significant (p<0.05)"
    )


if __name__ == "__main__":
    main()
