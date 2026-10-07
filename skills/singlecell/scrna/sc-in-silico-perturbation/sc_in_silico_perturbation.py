#!/usr/bin/env python3
"""Descriptive correlation edge scores or the optional R scTenifoldKnk method.

The default grn_ko CLI name is retained for compatibility. Its score is not a
causal knockout simulation and it does not provide calibrated significance.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scanpy as sc

_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))

from skills._sdk.checksums import sha256_file
from skills._sdk.notebook import load_skill

_api = load_skill("sc-in-silico-perturbation")
from skills._sdk.report import (
    generate_report_footer,
    generate_report_header,
)
from skills._sdk.result import write_result_json
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.adata_utils import (
    ensure_input_contract,
    infer_x_matrix_kind,
    propagate_singlecell_contracts,
    store_analysis_metadata,
)
from skills.singlecell._lib.export import save_h5ad

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-in-silico-perturbation"
SKILL_VERSION = "0.2.0"

R_ENHANCED_PLOTS: dict[str, str] = {
    # sc-ISP exports diff_regulation.csv as de_top_markers.csv alias for volcano.
    # No UMAP/embedding CSV at this stage.
    "plot_de_volcano": "r_isp_volcano.png",
}


def _render_r_enhanced(output_dir: Path, figure_data_dir: Path, r_enhanced: bool) -> list[str]:
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

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Single-cell in-silico perturbation analysis"
    )
    p.add_argument("--input", type=str, default=None)
    p.add_argument("--output", type=str, required=True)
    p.add_argument("--demo", action="store_true")
    p.add_argument(
        "--method",
        type=str,
        default="grn_ko",
        choices=["grn_ko", "sctenifoldknk"],
        help="grn_ko (Python, default) or sctenifoldknk (R)",
    )
    p.add_argument("--ko-gene", type=str, default="G10",
                    help="Target gene to virtually knock out")
    # -- Python method params --
    p.add_argument("--n-top-genes", type=int, default=2000,
                    help="Number of HVGs used for GRN (grn_ko)")
    p.add_argument("--corr-threshold", type=float, default=0.05,
                    help="Deprecated compatibility argument; the descriptive score does not threshold edges")
    # -- R method params --
    p.add_argument("--seed", type=int, default=0, help="R scTenifoldKnk random seed")
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
    p.add_argument("--r-enhanced", action="store_true", default=False,
                   help="Generate R-enhanced figures via ggplot2 renderers")
    return p.parse_args()

# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

def _make_demo_adata():
    """Create a small synthetic AnnData for demo runs."""
    rng = np.random.default_rng(0)
    n_genes, n_cells = 120, 500
    mat = rng.poisson(5, size=(n_cells, n_genes))
    genes = [f"G{i}" for i in range(1, n_genes + 1)]
    cells = [f"C{i}" for i in range(1, n_cells + 1)]
    adata = sc.AnnData(
        X=mat.astype(np.float32),
        obs=pd.DataFrame(index=cells),
        var=pd.DataFrame(index=genes),
    )
    adata.layers["counts"] = adata.X.copy()
    return adata


def _make_demo_matrix() -> pd.DataFrame:
    """Create a genes-x-cells DataFrame for the R path."""
    rng = np.random.default_rng(0)
    mat = rng.poisson(5, size=(120, 500))
    genes = [f"G{i}" for i in range(1, 121)]
    cells = [f"C{i}" for i in range(1, 501)]
    return pd.DataFrame(mat, index=genes, columns=cells)

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def _preflight(adata, *, ko_gene: str, method: str) -> list[str]:
    """Validate inputs before running.  Raises SystemExit on fatal issues."""
    warnings: list[str] = []

    # 1. KO gene must exist
    if ko_gene not in adata.var_names:
        print()
        print(f"  *** KO gene '{ko_gene}' not found in adata.var_names ({adata.n_vars} genes). ***")
        print()
        print("  How to fix:")
        print("    Option 1 -- Specify a gene that exists in your data:")
        sample_genes = list(adata.var_names[:5])
        print(f"      Available genes (first 5): {sample_genes}")
        print(f"      python skills/singlecell/scrna/sc-in-silico-perturbation/sc_in_silico_perturbation.py --input data.h5ad --output out/ --ko-gene {sample_genes[0]}")
        print("    Option 2 -- Check gene name casing (human=UPPER, mouse=Title-case)")
        raise SystemExit(1)

    # 2. Matrix semantics
    has_counts = "counts" in adata.layers
    if not has_counts:
        warnings.append(
            "No 'counts' layer found. The GRN will be built from adata.X directly. "
            "For best results, provide raw counts in layers['counts']."
        )
        logger.warning("No 'counts' layer. Using adata.X for GRN construction.")

    # 3. Minimum cells / genes
    if adata.n_obs < 50:
        warnings.append(
            f"Only {adata.n_obs} cells -- GRN estimation may be unreliable. "
            "Consider using at least 200 cells."
        )
    if adata.n_vars < 20:
        warnings.append(
            f"Only {adata.n_vars} genes -- perturbation analysis will be limited."
        )

    # 4. R availability for sctenifoldknk
    if method == "sctenifoldknk":
        import shutil
        if not shutil.which("Rscript"):
            print()
            print("  *** Rscript not found on PATH. ***")
            print("  The sctenifoldknk method requires R with the scTenifoldKnk package.")
            print()
            print("  How to fix:")
            print("    Option 1 -- Use the Python method instead (no R required):")
            print(f"      python skills/singlecell/scrna/sc-in-silico-perturbation/sc_in_silico_perturbation.py --input data.h5ad --output out/ --method grn_ko --ko-gene {ko_gene}")
            print("    Option 2 -- Install R and scTenifoldKnk:")
            print("      install.packages('scTenifoldKnk')  # in R console")
            raise SystemExit(1)

    return warnings


def _preflight_matrix(adata, *, ko_gene: str, method: str) -> list[str]:
    """Thin wrapper that also detects species hint."""
    warnings = _preflight(adata, ko_gene=ko_gene, method=method)

    # Species hint detection
    sample = list(adata.var_names[:500])
    upper_ratio = sum(1 for g in sample if g == g.upper()) / max(len(sample), 1)
    if upper_ratio > 0.7:
        species_hint = "human"
    else:
        title_ratio = sum(1 for g in sample if g != g.upper() and g[0].isupper()) / max(len(sample), 1)
        species_hint = "mouse" if title_ratio > 0.5 else "unknown"

    if species_hint != "unknown":
        logger.info("Species hint: %s (based on gene name casing)", species_hint)

    return warnings

# ---------------------------------------------------------------------------
# Python method: GRN knockout
# ---------------------------------------------------------------------------

def _check_degenerate(diff_df: pd.DataFrame, *, ko_gene: str) -> dict:
    """Detect degenerate perturbation results."""
    diagnostics: dict = {
        "degenerate": False,
        "suggested_actions": [],
    }

    if diff_df.empty:
        diagnostics["degenerate"] = True
        diagnostics["reason"] = "empty_result"
        diagnostics["suggested_actions"] = [
            "The analysis produced no results. Check that the input has enough genes and cells.",
            f"Verify that '{ko_gene}' exists in the expression matrix.",
        ]
        return diagnostics

    if "p.adj" not in diff_df.columns:
        diagnostics["interpretation"] = "Descriptive correlation score; no significance test was performed."
        return diagnostics
    n_sig = int((diff_df["p.adj"] <= 0.05).sum())
    if n_sig == 0:
        diagnostics["degenerate"] = True
        diagnostics["reason"] = "no_significant_genes"
        diagnostics["n_tested"] = int(len(diff_df))
        diagnostics["n_significant"] = 0
        diagnostics["suggested_actions"] = [
            f"No genes were significantly perturbed by knocking out '{ko_gene}'.",
            "This can happen if the gene has weak regulatory connections.",
            "Try a different KO gene: --ko-gene <GENE>",
            "For the R method, try increasing --n-net or --n-cells for more robust GRN estimation.",
        ]

    return diagnostics

# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def _write_figures_manifest(output_dir: Path, figure_files: list[str]) -> None:
    """Write figures/manifest.json."""
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "skill": SKILL_NAME,
        "figures": {Path(f).stem: f for f in figure_files},
    }
    (figures_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def _write_figure_data(output_dir: Path, diff_df: pd.DataFrame) -> dict[str, str]:
    """Write plot-ready CSV and manifest to figure_data/."""
    fd_dir = output_dir / "figure_data"
    fd_dir.mkdir(parents=True, exist_ok=True)

    files: dict[str, str] = {}
    if not diff_df.empty:
        fname = "diff_regulation.csv"
        diff_df.to_csv(fd_dir / fname, index=False)
        files["diff_regulation"] = fname

        # Write de_top_markers.csv alias for plot_de_volcano renderer.
        # Maps ISP columns to expected DE column schema.
        try:
            if "p.adj" not in diff_df.columns:
                raise ValueError("Correlation scores are not differential-expression tests")
            alias_df = diff_df.copy()
            # Rename to scanpy-style DE columns expected by de.R
            col_map = {}
            if "gene" in alias_df.columns and "names" not in alias_df.columns:
                col_map["gene"] = "names"
            if "FC" in alias_df.columns and "logfoldchanges" not in alias_df.columns:
                col_map["FC"] = "logfoldchanges"
            if "p.adj" in alias_df.columns and "pvals_adj" not in alias_df.columns:
                col_map["p.adj"] = "pvals_adj"
            elif "p_value" in alias_df.columns and "pvals_adj" not in alias_df.columns:
                col_map["p_value"] = "pvals_adj"
            if col_map:
                alias_df = alias_df.rename(columns=col_map)
            alias_df["group"] = "KO"
            alias_df.to_csv(fd_dir / "de_top_markers.csv", index=False)
            files["de_top_markers"] = "de_top_markers.csv"
        except Exception:
            pass

    manifest = {"skill": SKILL_NAME, "available_files": files}
    (fd_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return files


def _write_report(
    output_dir: Path,
    summary: dict,
    params: dict,
    input_path: str | None,
    diagnostics: dict,
    preflight_warnings: list[str],
) -> None:
    header = generate_report_header(
        title="In-Silico Perturbation Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_path)] if input_path else None,
        extra_metadata={
            "KO gene": str(params.get("ko_gene", "NA")),
            "Method": str(summary.get("method", "NA")),
        },
    )
    body = [
        "## Summary",
        "",
        f"- Method: `{summary.get('method')}`",
        f"- KO gene: `{params.get('ko_gene')}`",
        f"- Differentially regulated genes reported: `{summary.get('n_genes', 'NA')}`",
        f"- Significant genes (R method only): `{summary.get('n_significant', 'not tested')}`",
        "",
    ]

    if preflight_warnings:
        body.extend(["## Preflight Warnings", ""])
        for w in preflight_warnings:
            body.append(f"- {w}")
        body.append("")

    body.extend([
        "## Interpretation",
        "",
        "- `grn_ko` is a descriptive Pearson-correlation edge-removal score, not a causal KO simulation.",
        "- It does not test significance; no p-values or adjusted p-values are reported.",
        "- `sctenifoldknk` runs the separate R network method and preserves its statistical output.",
        "- Inspect the top genes in `tables/diff_regulation.csv`.",
    ])

    if diagnostics.get("degenerate"):
        body.extend([
            "",
            f"## Troubleshooting: {diagnostics.get('reason', 'degenerate output')}",
            "",
            "The perturbation result appears degenerate. Possible fixes:",
            "",
        ])
        for i, action in enumerate(diagnostics.get("suggested_actions", []), 1):
            body.append(f"{i}. {action}")

    (output_dir / "report.md").write_text(
        header + "\n" + "\n".join(body) + "\n" + generate_report_footer(),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    args = _parse_args()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = output_dir / "tables"
    figures_dir = output_dir / "figures"
    fd_dir = output_dir / "figure_data"
    tables_dir.mkdir(exist_ok=True)
    figures_dir.mkdir(exist_ok=True)
    fd_dir.mkdir(exist_ok=True)

    # -- Load data --
    adata = None
    input_path: str | None = None
    input_checksum = ""

    if args.demo:
        if args.method == "sctenifoldknk":
            # R path uses a DataFrame directly
            matrix_df = _make_demo_matrix()
            adata = sc.AnnData(matrix_df.T)
        else:
            adata = _make_demo_adata()
        input_path = None
    else:
        if not args.input:
            raise SystemExit("Provide --input or use --demo")
        adata = sc_io.smart_load(args.input, preserve_all=True)
        input_checksum = sha256_file(args.input)
        input_path = args.input

    # -- Preflight (Python path only -- R path does its own validation) --
    preflight_warnings: list[str] = []
    if adata is not None:
        ensure_input_contract(adata, source_path=input_path)
        preflight_warnings = _preflight_matrix(
            adata, ko_gene=args.ko_gene, method=args.method
        )

    # -- Run method --
    assert adata is not None
    if args.method == "sctenifoldknk":
        diff_df = _api.sctenifoldknk(
            adata, ko_gene=args.ko_gene, qc=args.qc, qc_min_lib_size=args.qc_min_lib_size,
            qc_min_cells=args.qc_min_cells, n_net=args.n_net, n_cells=args.n_cells,
            n_comp=args.n_comp, q=args.q, td_k=args.td_k, ma_dim=args.ma_dim,
            n_cores=args.n_cores, random_state=args.seed,
        )
        diff_df.to_csv(tables_dir / "tenifold_diff_regulation.csv", index=False)
        executed_method = "sctenifoldknk"
    else:
        diff_df = _api.knockout_correlation(adata, ko_gene=args.ko_gene, n_top_genes=args.n_top_genes)
        executed_method = "grn_ko"

    # -- Save results table --
    diff_df.to_csv(tables_dir / "diff_regulation.csv", index=False)

    # -- Degenerate output check --
    diagnostics = _check_degenerate(diff_df, ko_gene=args.ko_gene)
    if diagnostics.get("degenerate"):
        print()
        print(f"  *** Perturbation result is degenerate: {diagnostics.get('reason')} ***")
        print()
        print("  How to fix:")
        for i, action in enumerate(diagnostics.get("suggested_actions", []), 1):
            print(f"    Option {i} -- {action}")
        print()

    # -- Figures --
    figure_files: list[str] = []
    if not diff_df.empty:
        fig = _api.perturbed_genes_figure(diff_df)
        fig.savefig(figures_dir / "top_perturbed_genes.png", dpi=200)
        plt.close(fig)
        figure_files.append("top_perturbed_genes.png")

    if not diff_df.empty and "p.adj" in diff_df.columns:
        fig2, ax2 = plt.subplots(figsize=(6, 4))
        pvals = diff_df["p.adj"].values
        pvals_log = -np.log10(np.clip(pvals, 1e-300, 1.0))
        ax2.hist(pvals_log, bins=30, color="#5e81ac", edgecolor="white")
        ax2.set_xlabel("-log10(adjusted p-value)")
        ax2.set_ylabel("Count")
        ax2.set_title("P-value distribution")
        ax2.axvline(-np.log10(0.05), color="red", linestyle="--", linewidth=0.8, label="p.adj=0.05")
        ax2.legend()
        fig2.tight_layout()
        fig2.savefig(figures_dir / "pvalue_distribution.png", dpi=200)
        plt.close(fig2)
        figure_files.append("pvalue_distribution.png")

    # -- Manifests --
    _write_figures_manifest(output_dir, figure_files)
    _write_figure_data(output_dir, diff_df)

    # -- Summary --
    n_sig = int((diff_df["p.adj"] <= 0.05).sum()) if "p.adj" in diff_df.columns else 0
    summary = {
        "method": executed_method,
        "ko_gene": args.ko_gene,
        "n_genes": int(len(diff_df)),
        "input_mode": "demo" if args.demo else "h5ad",
    }
    if "p.adj" in diff_df:
        summary["n_significant"] = n_sig
    params = {
        "ko_gene": args.ko_gene,
        "method": args.method,
        "n_top_genes": args.n_top_genes,
        "corr_threshold": args.corr_threshold,
    }
    if args.method == "sctenifoldknk":
        params.update({
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
            "random_state": args.seed,
        })

    # -- Contracts & processed.h5ad (Python path only) --
    if adata is not None:
        # Store perturbation results in adata.var
        if not diff_df.empty:
            dr_indexed = diff_df.set_index("gene")
            for col in ["dr_score", "p.adj", "FC"]:
                if col in dr_indexed.columns:
                    key = f"perturbation_{col.replace('.', '_')}"
                    adata.var[key] = dr_indexed[col].reindex(adata.var_names)

        store_analysis_metadata(adata, SKILL_NAME, executed_method, params)
        _, matrix_contract = propagate_singlecell_contracts(
            adata,
            adata,
            producer_skill=SKILL_NAME,
            x_kind=infer_x_matrix_kind(adata),
        )

        output_h5ad = output_dir / "processed.h5ad"
        save_h5ad(adata, output_h5ad)
        logger.info("Saved processed object to %s", output_h5ad)

        summary["matrix_contract"] = matrix_contract

    # -- result.json --
    outputs_dict: dict = {
        "diff_regulation": str(tables_dir / "diff_regulation.csv"),
    }
    if figure_files:
        outputs_dict["figures"] = [str(figures_dir / f) for f in figure_files]

    result_data: dict = {
        "params": params,
        "outputs": outputs_dict,
    }
    if diagnostics.get("degenerate"):
        result_data["perturbation_diagnostics"] = diagnostics

    result_data["next_steps"] = [
        {"skill": "sc-enrichment", "reason": "Pathway enrichment on predicted perturbation effects", "priority": "optional"},
    ]
    r_enhanced_figures = _render_r_enhanced(output_dir, output_dir / "figure_data", args.r_enhanced and "p.adj" in diff_df)
    result_data["r_enhanced_figures"] = r_enhanced_figures
    write_result_json(
        output_dir,
        SKILL_NAME,
        SKILL_VERSION,
        summary,
        result_data,
        input_checksum=input_checksum,
    )

    # -- report.md --
    _write_report(output_dir, summary, params, input_path, diagnostics, preflight_warnings)

    logger.info("Done: %s", output_dir)

    # --- Next-step guidance ---
    print()
    print(">> Next step: Run sc-enrichment to enrich perturbed genes")
    print(f"  python skills/singlecell/scrna/sc-enrichment/sc_enrichment.py --input {output_dir}/processed.h5ad --output <dir>")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
