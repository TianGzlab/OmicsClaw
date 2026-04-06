#!/usr/bin/env python3
"""Single-cell in-silico perturbation analysis with scTenifoldKnk."""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
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

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-in-silico-perturbation"
SKILL_VERSION = "0.1.0"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Single-cell in-silico perturbation analysis with scTenifoldKnk")
    p.add_argument("--input", type=str, default=None)
    p.add_argument("--output", type=str, required=True)
    p.add_argument("--demo", action="store_true")
    p.add_argument("--ko-gene", type=str, default="G10")
    p.add_argument("--qc", action="store_true")
    p.add_argument("--qc-min-lib-size", type=int, default=0)
    p.add_argument("--qc-min-cells", type=int, default=10)
    p.add_argument("--n-net", type=int, default=2)
    p.add_argument("--n-cells", type=int, default=100)
    p.add_argument("--n-comp", type=int, default=3)
    p.add_argument("--q", type=float, default=0.8)
    p.add_argument("--td-k", type=int, default=2)
    p.add_argument("--ma-dim", type=int, default=2)
    p.add_argument("--n-cores", type=int, default=1)
    return p.parse_args()


def _write_report(output_dir: Path, summary: dict, params: dict, input_path: str | None) -> None:
    header = generate_report_header(
        title="In-Silico Perturbation Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_path)] if input_path else None,
        extra_metadata={
            "KO gene": str(params.get("ko_gene", "NA")),
            "Method": "scTenifoldKnk",
        },
    )
    body = [
        "## Summary",
        "",
        f"- KO gene: `{params.get('ko_gene')}`",
        f"- Differentially regulated genes reported: `{summary.get('n_genes', 'NA')}`",
        f"- Significant genes (`p.adj <= 0.05`): `{summary.get('n_significant', 'NA')}`",
        "",
        "## Interpretation",
        "",
        "- scTenifoldKnk constructs a WT gene regulatory network, zeroes the outgoing edges of the knocked-out gene, and compares WT versus KO manifolds.",
        "- Inspect the differential regulation table first; the top-ranked genes are the predicted downstream response to the virtual knockout.",
    ]
    (output_dir / "report.md").write_text(header + "\n" + "\n".join(body) + "\n" + generate_report_footer(), encoding="utf-8")


def _make_demo_matrix() -> pd.DataFrame:
    import numpy as np

    rng = np.random.default_rng(0)
    mat = rng.poisson(5, size=(120, 500))
    genes = [f"G{i}" for i in range(1, 121)]
    cells = [f"C{i}" for i in range(1, 501)]
    return pd.DataFrame(mat, index=genes, columns=cells)


def _load_expression_matrix(args: argparse.Namespace) -> tuple[pd.DataFrame, str | None, str]:
    if args.demo:
        return _make_demo_matrix(), None, "demo"

    if not args.input:
        raise SystemExit("Provide --input or use --demo")
    adata = sc_io.smart_load(args.input, preserve_all=True)
    matrix = adata.layers["counts"] if "counts" in adata.layers else adata.X
    if hasattr(matrix, "toarray"):
        matrix = matrix.toarray()
    df = pd.DataFrame(matrix.T, index=adata.var_names.astype(str), columns=adata.obs_names.astype(str))
    return df, args.input, "h5ad"


def _run_sctenifoldknk(df: pd.DataFrame, args: argparse.Namespace, output_dir: Path) -> pd.DataFrame:
    with tempfile.TemporaryDirectory(prefix="omicsclaw_tenifold_") as tmpdir:
        matrix_path = Path(tmpdir) / "matrix.csv"
        r_script_path = Path(tmpdir) / "run_sctenifoldknk.R"
        output_csv = Path(tmpdir) / "diff_regulation.csv"
        df.to_csv(matrix_path)

        r_script = f"""
suppressPackageStartupMessages(library(scTenifoldKnk))
mat <- as.matrix(read.csv("{matrix_path.as_posix()}", row.names=1, check.names=FALSE))
out <- scTenifoldKnk(
  countMatrix = mat,
  gKO = "{args.ko_gene}",
  qc = {str(args.qc).upper()},
  qc_minLSize = {args.qc_min_lib_size},
  qc_minCells = {args.qc_min_cells},
  nc_nNet = {args.n_net},
  nc_nCells = {args.n_cells},
  nc_nComp = {args.n_comp},
  nc_q = {args.q},
  td_K = {args.td_k},
  ma_nDim = {args.ma_dim},
  nCores = {args.n_cores}
)
write.csv(out$diffRegulation, "{output_csv.as_posix()}", row.names=FALSE, quote=FALSE)
"""
        r_script_path.write_text(r_script, encoding="utf-8")

        import os
        import subprocess

        r_env = os.environ.copy()
        user_r_lib = str(Path.home() / "R" / "x86_64-pc-linux-gnu-library" / "4.1")
        current_r_libs = r_env.get("R_LIBS_USER", "")
        r_env["R_LIBS_USER"] = user_r_lib if not current_r_libs else f"{user_r_lib}:{current_r_libs}"

        subprocess.run(["Rscript", str(r_script_path)], check=True, env=r_env)
        result = pd.read_csv(output_csv)
        result.to_csv(output_dir / "tables" / "tenifold_diff_regulation.csv", index=False)
        return result


def main() -> int:
    args = _parse_args()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    figures_dir = output_dir / "figures"
    tables_dir.mkdir(exist_ok=True)
    figures_dir.mkdir(exist_ok=True)

    matrix_df, input_path, input_mode = _load_expression_matrix(args)
    input_checksum = sha256_file(input_path) if input_path else ""

    diff_df = _run_sctenifoldknk(matrix_df, args, output_dir)

    fig, ax = plt.subplots(figsize=(6, 4))
    top = diff_df.sort_values("p.adj").head(15)
    ax.barh(top["gene"].astype(str), top["FC"].astype(float), color="#b2182b")
    ax.axvline(0, color="black", linestyle="--", linewidth=0.8)
    ax.set_title("Top virtual-knockout perturbed genes")
    fig.tight_layout()
    fig.savefig(figures_dir / "tenifold_top_fc.png", dpi=200)
    plt.close(fig)

    summary = {
        "method": "sctenifoldknk",
        "n_genes": int(len(diff_df)),
        "n_significant": int((diff_df["p.adj"] <= 0.05).sum()) if "p.adj" in diff_df.columns else 0,
        "input_mode": input_mode,
    }
    params = {
        "ko_gene": args.ko_gene,
        "qc": args.qc,
        "qc_min_lib_size": args.qc_min_lib_size,
        "qc_min_cells": args.qc_min_cells,
        "n_net": args.n_net,
        "n_cells": args.n_cells,
        "n_comp": args.n_comp,
        "q": args.q,
        "td_k": args.td_k,
        "ma_dim": args.ma_dim,
        "n_cores": args.n_cores,
    }
    write_result_json(
        output_dir,
        SKILL_NAME,
        SKILL_VERSION,
        summary,
        {
            "params": params,
            "outputs": {
                "diff_regulation": str(tables_dir / "tenifold_diff_regulation.csv"),
                "top_fc_figure": str(figures_dir / "tenifold_top_fc.png"),
            },
        },
        input_checksum=input_checksum,
    )
    _write_report(output_dir, summary, params, input_path)
    write_output_readme(
        output_dir,
        skill_alias=SKILL_NAME,
        description="Single-cell in-silico perturbation analysis with scTenifoldKnk.",
        preferred_method="sctenifoldknk",
    )
    logger.info("Done: %s", output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
