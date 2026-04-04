#!/usr/bin/env python3
"""Single-cell gene program discovery."""

from __future__ import annotations

import argparse
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
from skills.singlecell._lib.gene_programs import make_demo_gene_program_adata, run_cnmf_programs, run_nmf_programs

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-gene-programs"
SKILL_VERSION = "0.1.0"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Single-cell gene program discovery")
    p.add_argument("--input", type=str, default=None)
    p.add_argument("--output", type=str, required=True)
    p.add_argument("--demo", action="store_true")
    p.add_argument("--method", type=str, default="cnmf", choices=["cnmf", "nmf"])
    p.add_argument("--n-programs", type=int, default=6)
    p.add_argument("--n-iter", type=int, default=400)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--layer", type=str, default=None)
    p.add_argument("--top-genes", type=int, default=30)
    return p.parse_args()


def _write_report(output_dir: Path, summary: dict, params: dict, input_path: str | None) -> None:
    backend = str(summary.get("backend", summary.get("method", "NA")))
    header = generate_report_header(
        title="Single-Cell Gene Programs Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_path)] if input_path else None,
        extra_metadata={
            "Method": str(params.get("method", "NA")),
            "Backend": backend,
            "Programs": str(params.get("n_programs", 0)),
        },
    )
    body = [
        "## Summary",
        "",
        f"- Requested method: `{params.get('method')}`",
        f"- Execution backend: `{backend}`",
        f"- Programs inferred: `{summary.get('n_programs', 'NA')}`",
        f"- Reconstruction error: `{summary.get('reconstruction_err', 'NA')}`",
        "",
        "## Interpretation",
        "",
        "- Gene programs summarize coordinated expression modules across cells.",
        "- `nmf` is a lightweight factorization baseline; `cnmf` is requested as the preferred consensus-style backend but this wrapper will report honestly if it falls back to an NMF-compatible implementation.",
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
        adata = make_demo_gene_program_adata(seed=args.seed)
        input_checksum = ""
        input_path = None
    else:
        if not args.input:
            raise SystemExit("Provide --input or use --demo")
        adata = sc_io.smart_load(args.input, preserve_all=True)
        input_checksum = sha256_file(args.input)
        input_path = args.input

    if args.method == "cnmf":
        result = run_cnmf_programs(
            adata,
            n_programs=args.n_programs,
            seed=args.seed,
            max_iter=args.n_iter,
            layer=args.layer,
            top_genes=args.top_genes,
        )
    else:
        result = run_nmf_programs(
            adata,
            n_programs=args.n_programs,
            seed=args.seed,
            max_iter=args.n_iter,
            layer=args.layer,
            top_genes=args.top_genes,
        )

    usage_df = result["usage"]
    weights_df = result["weights"]
    top_df = result["top_genes"]
    spectra_tpm_df = result.get("spectra_tpm")
    adata.obsm["X_gene_programs"] = usage_df.to_numpy()
    adata.uns["gene_programs"] = {
        "method": result.get("method", args.method),
        "program_names": usage_df.columns.tolist(),
        "top_genes_csv": "tables/top_program_genes.csv",
    }
    usage_df.to_csv(tables_dir / "program_usage.csv")
    weights_df.to_csv(tables_dir / "program_weights.csv")
    top_df.to_csv(tables_dir / "top_program_genes.csv", index=False)
    if spectra_tpm_df is not None:
        spectra_tpm_df.to_csv(tables_dir / "program_tpm.csv")

    if not usage_df.empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        usage_df.mean(axis=0).plot.bar(ax=ax, color="#756bb1")
        ax.set_title("Mean program usage")
        fig.tight_layout()
        fig.savefig(figures_dir / "mean_program_usage.png", dpi=200)
        plt.close(fig)

    annotated_h5ad = output_dir / "annotated_programs.h5ad"
    adata.write_h5ad(annotated_h5ad)

    summary = {
        "method": args.method,
        "backend": result.get("method", args.method),
        "n_programs": int(usage_df.shape[1]),
        "reconstruction_err": float(result.get("reconstruction_err", float("nan"))),
    }
    params = {
        "method": args.method,
        "n_programs": args.n_programs,
        "n_iter": args.n_iter,
        "seed": args.seed,
        "layer": args.layer,
        "top_genes": args.top_genes,
    }
    write_result_json(
        output_dir,
        SKILL_NAME,
        SKILL_VERSION,
        summary,
        {
            "params": params,
            "outputs": {
                "program_usage": str(tables_dir / "program_usage.csv"),
                "program_weights": str(tables_dir / "program_weights.csv"),
                "top_program_genes": str(tables_dir / "top_program_genes.csv"),
                "program_tpm": str(tables_dir / "program_tpm.csv") if spectra_tpm_df is not None else None,
                "annotated_h5ad": str(annotated_h5ad),
            },
        },
        input_checksum=input_checksum,
    )
    _write_report(output_dir, summary, params, input_path)
    write_output_readme(
        output_dir,
        skill_alias=SKILL_NAME,
        description="Gene program discovery and usage scoring for scRNA-seq.",
        preferred_method=args.method,
    )
    logger.info("Done: %s", output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
