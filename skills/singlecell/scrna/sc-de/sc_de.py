#!/usr/bin/env python3
"""Single-cell differential expression across exploratory and pseudobulk paths."""

from __future__ import annotations

import argparse
import json
import logging
import tempfile
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scanpy as sc

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_header,
    generate_report_footer,
    load_result_json,
    write_output_readme,
    write_result_json,
)
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.adata_utils import (
    ensure_input_contract,
    get_matrix_contract,
    infer_x_matrix_kind,
    matrix_looks_count_like,
    propagate_singlecell_contracts,
    raw_matrix_kind,
    record_matrix_contract,
    store_analysis_metadata,
)
from skills.singlecell._lib.method_config import MethodConfig, validate_method_choice
from skills.singlecell._lib.preflight import apply_preflight, preflight_sc_de
from skills.singlecell._lib.pseudobulk import (
    aggregate_to_pseudobulk,
    plot_ma,
    plot_volcano,
    run_deseq2_analysis,
)
from omicsclaw.core.dependency_manager import validate_r_environment
from omicsclaw.core.r_script_runner import RScriptRunner

from skills.singlecell._lib.viz import (
    plot_de_effect_summary,
    plot_de_group_summary,
    plot_de_rank_panels,
    save_figure,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-de"
SKILL_VERSION = "0.4.0"

# R Enhanced renderers for this skill.
# Key   = renderer name registered in viz/r/registry.R R_PLOT_REGISTRY
# Value = output filename (written to figures/r_enhanced/)
R_ENHANCED_PLOTS: dict[str, str] = {
    "plot_de_volcano": "r_de_volcano.png",
    "plot_de_heatmap": "r_de_heatmap.png",
    "plot_feature_violin": "r_feature_violin.png",
    "plot_feature_cor": "r_feature_cor.png",
}


def _render_r_enhanced(
    output_dir: Path,
    figure_data_dir: Path,
    r_enhanced: bool,
) -> list[str]:
    """Run R Enhanced rendering pass. Always called after Python figures are complete."""
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

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "wilcoxon": MethodConfig(
        name="wilcoxon",
        description="Wilcoxon rank-sum test (scanpy built-in)",
        dependencies=("scanpy",),
    ),
    "t-test": MethodConfig(
        name="t-test",
        description="Welch's t-test (scanpy built-in)",
        dependencies=("scanpy",),
    ),
    "logreg": MethodConfig(
        name="logreg",
        description="Logistic-regression marker ranking (scanpy built-in)",
        dependencies=("scanpy",),
    ),
    "mast": MethodConfig(
        name="mast",
        description="MAST hurdle-model differential expression (R)",
        dependencies=(),
    ),
    "deseq2_r": MethodConfig(
        name="deseq2_r",
        description="DESeq2 pseudobulk differential expression (R)",
        dependencies=(),
    ),
}


def _validate_runtime_dependencies(method: str) -> None:
    if method == "mast":
        validate_r_environment(required_r_packages=["MAST", "SingleCellExperiment", "zellkonverter"])
    elif method == "deseq2_r":
        validate_r_environment(required_r_packages=["DESeq2", "SingleCellExperiment", "zellkonverter"])


def _write_repro_requirements(repro_dir: Path, packages: list[str]) -> None:
    try:
        from importlib.metadata import PackageNotFoundError, version as get_version
    except ImportError:  # pragma: no cover
        PackageNotFoundError = Exception
        from importlib_metadata import version as get_version  # type: ignore

    lines: list[str] = []
    for pkg in packages:
        try:
            lines.append(f"{pkg}=={get_version(pkg)}")
        except PackageNotFoundError:
            continue
        except Exception:
            continue
    (repro_dir / "requirements.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def write_standard_run_artifacts(output_dir: Path, result_payload: dict, summary: dict) -> None:
    notebook_path = None
    try:
        from omicsclaw.common.notebook_export import write_analysis_notebook

        notebook_path = write_analysis_notebook(
            output_dir,
            skill_alias=SKILL_NAME,
            description="Differential expression analysis for single-cell RNA-seq data.",
            result_payload=result_payload,
            preferred_method=summary.get("method", "wilcoxon"),
            script_path=Path(__file__).resolve(),
            actual_command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        )
    except Exception as exc:
        logger.warning("Failed to write analysis notebook: %s", exc)

    try:
        write_output_readme(
            output_dir,
            skill_alias=SKILL_NAME,
            description="Differential expression analysis for single-cell RNA-seq data.",
            result_payload=result_payload,
            preferred_method=summary.get("method", "wilcoxon"),
            notebook_path=notebook_path,
        )
    except Exception as exc:
        logger.warning("Failed to write README.md: %s", exc)


def run_de_scanpy(
    adata,
    groupby="leiden",
    method="wilcoxon",
    group1=None,
    group2=None,
    *,
    logreg_solver: str = "lbfgs",
):
    resolved_groupby = groupby
    if resolved_groupby not in adata.obs.columns:
        if resolved_groupby == "leiden" and "louvain" in adata.obs.columns:
            logger.warning("Column 'leiden' not found; falling back to legacy 'louvain' for DE demo compatibility")
            resolved_groupby = "louvain"
        else:
            raise ValueError(f"Column '{groupby}' not found in adata.obs")

    effective_method = method
    method_kwargs: dict[str, object] = {"pts": True, "use_raw": False}
    if method == "logreg":
        method_kwargs["solver"] = logreg_solver

    if group1 and group2:
        sc.tl.rank_genes_groups(
            adata,
            groupby=resolved_groupby,
            groups=[group1],
            reference=group2,
            method=effective_method,
            **method_kwargs,
        )
    else:
        sc.tl.rank_genes_groups(
            adata,
            groupby=resolved_groupby,
            method=effective_method,
            **method_kwargs,
        )

    result_df = sc.get.rank_genes_groups_df(adata, group=None)
    n_groups = len(result_df["group"].unique()) if "group" in result_df.columns else 0
    return result_df, {
        "method": method,
        "groupby": resolved_groupby,
        "n_groups": n_groups,
        "n_genes_tested": int(adata.n_vars),
        "expression_source": "adata.X",
    }


def _build_count_like_adata(adata) -> tuple[sc.AnnData, str]:
    if "counts" in adata.layers and matrix_looks_count_like(adata.layers["counts"]):
        prepared = adata.copy()
        prepared.X = adata.layers["counts"].copy()
        return prepared, "layers.counts"

    if adata.raw is not None and adata.raw.shape == adata.shape and matrix_looks_count_like(adata.raw.X):
        prepared = sc.AnnData(X=adata.raw.X.copy(), obs=adata.obs.copy(), var=adata.raw.var.copy())
        prepared.obs_names = adata.obs_names.copy()
        prepared.var_names = adata.raw.var_names.copy()
        return prepared, "adata.raw"

    matrix_contract = get_matrix_contract(adata)
    if matrix_contract.get("X") == "raw_counts" or matrix_looks_count_like(adata.X):
        return adata.copy(), "adata.X"

    raise ValueError(
        "deseq2_r requires raw counts in `layers['counts']`, aligned raw counts in `adata.raw`, or an unnormalized count-like `adata.X` matrix."
    )


def run_de_deseq2_r_method(
    adata,
    *,
    condition_key: str,
    group1: str,
    group2: str,
    sample_key: str,
    celltype_key: str,
    pseudobulk_min_cells: int = 10,
    pseudobulk_min_counts: int = 1000,
):
    if not group1 or not group2:
        raise ValueError("R pseudobulk DESeq2 requires both --group1 and --group2")
    if sample_key not in adata.obs.columns:
        raise ValueError(f"sample_key '{sample_key}' not found in adata.obs")
    if celltype_key not in adata.obs.columns:
        raise ValueError(f"celltype_key '{celltype_key}' not found in adata.obs")

    pb_adata, expression_source = _build_count_like_adata(adata)
    pb = aggregate_to_pseudobulk(
        pb_adata,
        sample_key=sample_key,
        celltype_key=celltype_key,
        min_cells=pseudobulk_min_cells,
        min_counts=pseudobulk_min_counts,
        layer=None,
    )
    if pb["counts"].empty:
        raise RuntimeError("Pseudobulk aggregation returned no sample-celltype combinations")

    sample_meta = adata.obs[[sample_key, condition_key]].drop_duplicates().rename(columns={sample_key: "sample"})
    de_results = run_deseq2_analysis(
        pb,
        sample_meta,
        formula="~ condition",
        contrast=["condition", group1, group2],
        celltype_key="celltype",
        use_rpy2=True,
    )
    if not de_results:
        raise RuntimeError("R pseudobulk DESeq2 returned no results")

    frames = []
    for cell_type, df in de_results.items():
        tmp = df.copy()
        tmp["cell_type"] = cell_type
        frames.append(tmp)
    full_df = pd.concat(frames, ignore_index=True)
    n_groups = full_df["cell_type"].nunique() if "cell_type" in full_df.columns else 0
    return full_df, {
        "method": "deseq2_r",
        "n_groups": int(n_groups),
        "n_genes_tested": int(full_df["gene"].nunique()) if "gene" in full_df.columns else 0,
        "expression_source": expression_source,
    }


def run_de_mast_method(adata, *, groupby: str, group1: str | None, group2: str | None):
    resolved_groupby = groupby
    if resolved_groupby not in adata.obs.columns:
        if resolved_groupby == "leiden" and "louvain" in adata.obs.columns:
            logger.warning("Column 'leiden' not found; falling back to legacy 'louvain' for MAST demo compatibility")
            resolved_groupby = "louvain"
        else:
            raise ValueError(f"Column '{groupby}' not found in adata.obs")
    scripts_dir = _PROJECT_ROOT / "omicsclaw" / "r_scripts"
    runner = RScriptRunner(scripts_dir=scripts_dir, timeout=1800)
    export = sc.AnnData(X=adata.X.copy(), obs=adata.obs.copy(), var=adata.var.copy())
    export.obs_names = adata.obs_names.copy()
    export.var_names = adata.var_names.copy()
    expression_source = "adata.X"
    with tempfile.TemporaryDirectory(prefix="omicsclaw_mast_") as tmpdir:
        tmpdir = Path(tmpdir)
        input_h5ad = tmpdir / "input.h5ad"
        output_dir = tmpdir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        export.write_h5ad(input_h5ad)
        args = [str(input_h5ad), str(output_dir), resolved_groupby]
        if group1:
            args.append(group1)
        if group2:
            args.append(group2)
        runner.run_script(
            "sc_mast_de.R",
            args=args,
            expected_outputs=["mast_results.csv"],
            output_dir=output_dir,
        )
        full_df = pd.read_csv(output_dir / "mast_results.csv")
    n_groups = full_df["group"].nunique() if "group" in full_df.columns else 0
    return full_df, {
        "method": "mast",
        "groupby": resolved_groupby,
        "n_groups": int(n_groups),
        "n_genes_tested": int(full_df["gene"].nunique()) if "gene" in full_df.columns else 0,
        "expression_source": expression_source,
    }


def _write_figure_data(
    output_dir: Path,
    *,
    exploratory_top: pd.DataFrame | None = None,
    group_summary: pd.DataFrame | None = None,
    pseudobulk_summary: pd.DataFrame | None = None,
) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(exist_ok=True)
    manifest: dict[str, str] = {}
    if exploratory_top is not None and not exploratory_top.empty:
        path = figure_data_dir / "de_top_markers.csv"
        exploratory_top.to_csv(path, index=False)
        manifest["de_top_markers"] = path.name
    if group_summary is not None and not group_summary.empty:
        path = figure_data_dir / "de_group_summary.csv"
        group_summary.to_csv(path, index=False)
        manifest["de_group_summary"] = path.name
    if pseudobulk_summary is not None and not pseudobulk_summary.empty:
        path = figure_data_dir / "pseudobulk_summary.csv"
        pseudobulk_summary.to_csv(path, index=False)
        manifest["pseudobulk_summary"] = path.name
    (figure_data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _group_summary(full_df: pd.DataFrame, top_df: pd.DataFrame, *, group_col: str = "group", gene_col: str = "names") -> pd.DataFrame:
    if full_df.empty or group_col not in full_df.columns:
        return pd.DataFrame()
    frame = full_df.copy()
    if "pvals_adj" in frame.columns:
        frame["significant"] = pd.to_numeric(frame["pvals_adj"], errors="coerce").fillna(1.0) < 0.05
    elif "padj" in frame.columns:
        frame["significant"] = pd.to_numeric(frame["padj"], errors="coerce").fillna(1.0) < 0.05
    else:
        frame["significant"] = False
    summary = (
        frame.groupby(group_col, observed=False)
        .agg(
            n_genes=(gene_col, "count"),
            n_significant=("significant", "sum"),
        )
        .reset_index()
        .rename(columns={group_col: "group"})
    )
    top_lookup = (
        top_df.groupby(group_col, observed=False)
        .head(1)[[group_col, gene_col]]
        .rename(columns={group_col: "group", gene_col: "top_gene"})
    )
    return summary.merge(top_lookup, on="group", how="left")


def _pseudobulk_group_summary(full_df: pd.DataFrame) -> pd.DataFrame:
    if full_df.empty:
        return pd.DataFrame()
    frame = full_df.copy()
    if "padj" in frame.columns:
        frame["significant"] = pd.to_numeric(frame["padj"], errors="coerce").fillna(1.0) < 0.05
    else:
        frame["significant"] = False
    group_col = "cell_type" if "cell_type" in frame.columns else "group"
    gene_col = "gene" if "gene" in frame.columns else "names"
    summary = (
        frame.groupby(group_col, observed=False)
        .agg(
            n_genes=(gene_col, "count"),
            n_significant=("significant", "sum"),
        )
        .reset_index()
        .rename(columns={group_col: "group"})
    )
    top_lookup = (
        frame.sort_values("padj", na_position="last")
        .groupby(group_col, observed=False)
        .head(1)[[group_col, gene_col]]
        .rename(columns={group_col: "group", gene_col: "top_gene"})
    )
    return summary.merge(top_lookup, on="group", how="left")


def generate_scanpy_figures(adata, full_df: pd.DataFrame, top_df: pd.DataFrame, output_dir: Path, n_top_genes=5) -> list[str]:
    figures = []
    try:
        sc.pl.rank_genes_groups_dotplot(adata, n_genes=n_top_genes, show=False)
        p = save_figure(plt.gcf(), output_dir, "marker_dotplot.png")
        figures.append(str(p))
        plt.close()
    except Exception as exc:
        logger.warning("Dotplot failed: %s", exc)

    try:
        p = plot_de_rank_panels(top_df, output_dir, filename="rank_genes_groups.png")
        if p is not None:
            figures.append(str(p))
    except Exception as exc:
        logger.warning("Rank genes plot failed: %s", exc)

    summary_df = _group_summary(full_df, top_df, group_col="group", gene_col="names")
    try:
        p = plot_de_effect_summary(top_df, output_dir, n_top=min(3, n_top_genes))
        if p is not None:
            figures.append(str(p))
    except Exception as exc:
        logger.warning("DE effect summary failed: %s", exc)

    try:
        p = plot_de_group_summary(summary_df, output_dir)
        if p is not None:
            figures.append(str(p))
    except Exception as exc:
        logger.warning("DE group summary failed: %s", exc)

    _write_figure_data(output_dir, exploratory_top=top_df, group_summary=summary_df)
    return figures


def generate_tabular_de_figures(
    full_df: pd.DataFrame,
    top_df: pd.DataFrame,
    output_dir: Path,
    *,
    group_col: str,
    gene_col: str,
) -> list[str]:
    figures: list[str] = []
    summary_df = _group_summary(full_df, top_df, group_col=group_col, gene_col=gene_col)
    try:
        p = plot_de_effect_summary(top_df.rename(columns={group_col: "group"}), output_dir, n_top=3)
        if p is not None:
            figures.append(str(p))
    except Exception as exc:
        logger.warning("DE effect summary failed: %s", exc)
    try:
        p = plot_de_group_summary(summary_df, output_dir)
        if p is not None:
            figures.append(str(p))
    except Exception as exc:
        logger.warning("DE group summary failed: %s", exc)
    _write_figure_data(output_dir, exploratory_top=top_df, group_summary=summary_df)
    return figures


def generate_pseudobulk_figures(full_df: pd.DataFrame, output_dir: Path, *, padj_threshold: float, log2fc_threshold: float) -> list[str]:
    figures: list[str] = []
    if full_df.empty:
        return figures

    group_col = "cell_type" if "cell_type" in full_df.columns else None
    if group_col is None:
        return figures

    summary_df = _pseudobulk_group_summary(full_df)
    try:
        p = plot_de_group_summary(summary_df, output_dir, filename="pseudobulk_group_summary.png")
        if p is not None:
            figures.append(str(p))
    except Exception as exc:
        logger.warning("Pseudobulk summary plot failed: %s", exc)

    for cell_type, group_df in full_df.groupby(group_col, observed=False):
        try:
            plot_volcano(
                group_df,
                str(cell_type),
                output_dir,
                padj_threshold=padj_threshold,
                log2fc_threshold=log2fc_threshold,
                top_genes=10,
            )
            figures.append(str((output_dir / "figures" / f"{cell_type}_volcano.png")))
        except Exception as exc:
            logger.warning("Volcano plot failed for %s: %s", cell_type, exc)
        try:
            plot_ma(
                group_df,
                str(cell_type),
                output_dir,
                padj_threshold=padj_threshold,
            )
            figures.append(str((output_dir / "figures" / f"{cell_type}_ma.png")))
        except Exception as exc:
            logger.warning("MA plot failed for %s: %s", cell_type, exc)

    _write_figure_data(output_dir, pseudobulk_summary=summary_df)
    return figures


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    requested_method = str(summary.get("requested_method", params.get("method", summary["method"])))
    executed_method = str(summary.get("executed_method", summary["method"]))
    group_label = "Cell types analyzed" if executed_method == "deseq2_r" else "Groups"
    header = generate_report_header(
        title="Differential Expression Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": executed_method,
            group_label: str(summary["n_groups"]),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Requested method**: {requested_method}",
        f"- **Executed method**: {executed_method}",
        f"- **{group_label}**: {summary['n_groups']}",
        f"- **Genes tested**: {summary['n_genes_tested']}",
        f"- **Total cells**: {summary.get('n_cells', 'N/A')}",
        f"- **Expression source**: {summary.get('expression_source', params.get('expression_source', 'adata.X'))}",
        "",
        "## Parameters\n",
    ]
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    body_lines.extend(
        [
            "",
            "## Typical Next Step\n",
            (
                "- Exploratory marker-style DE usually flows into `sc-cell-annotation`, "
                "`sc-markers` refinement, or pathway enrichment."
                if executed_method != "deseq2_r"
                else "- Pseudobulk condition DE usually flows into enrichment or targeted interpretation of the affected cell types."
            ),
        ]
    )

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python sc_de.py --input <input.h5ad> --output {output_dir}"
    cmd += f" --groupby {params['groupby']}"
    cmd += f" --method {params['method']}"
    cmd += f" --n-top-genes {params['n_top_genes']}"
    if params.get("logreg_solver") is not None:
        cmd += f" --logreg-solver {params['logreg_solver']}"
    if params.get("group1") is not None:
        cmd += f" --group1 {params['group1']}"
    if params.get("group2") is not None:
        cmd += f" --group2 {params['group2']}"
    if params.get("sample_key") is not None:
        cmd += f" --sample-key {params['sample_key']}"
    if params.get("celltype_key") is not None:
        cmd += f" --celltype-key {params['celltype_key']}"
    if params.get("pseudobulk_min_cells") is not None:
        cmd += f" --pseudobulk-min-cells {params['pseudobulk_min_cells']}"
    if params.get("pseudobulk_min_counts") is not None:
        cmd += f" --pseudobulk-min-counts {params['pseudobulk_min_counts']}"
    if params.get("padj_threshold") is not None:
        cmd += f" --padj-threshold {params['padj_threshold']}"
    if params.get("log2fc_threshold") is not None:
        cmd += f" --log2fc-threshold {params['log2fc_threshold']}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")
    _write_repro_requirements(
        repro_dir,
        ["scanpy", "anndata", "numpy", "pandas", "matplotlib"],
    )


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Differential Expression")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--groupby", default="leiden", help="Group column for Scanpy DE or condition column for deseq2_r")
    parser.add_argument("--method", default="wilcoxon", choices=list(METHOD_REGISTRY.keys()))
    parser.add_argument("--n-top-genes", type=int, default=10)
    parser.add_argument("--logreg-solver", default="lbfgs", choices=["lbfgs", "liblinear", "newton-cg", "sag", "saga"])
    parser.add_argument("--group1", default=None)
    parser.add_argument("--group2", default=None)
    parser.add_argument("--sample-key", default=None, help="Sample/replicate column for pseudobulk R DE")
    parser.add_argument("--celltype-key", default="cell_type", help="Cell type column for pseudobulk R DE")
    parser.add_argument("--pseudobulk-min-cells", type=int, default=10, help="Minimum cells per sample-celltype pseudobulk bin")
    parser.add_argument("--pseudobulk-min-counts", type=int, default=1000, help="Minimum total counts per sample-celltype pseudobulk bin")
    parser.add_argument("--padj-threshold", type=float, default=0.05, help="Adjusted p-value threshold for DE summary plots")
    parser.add_argument("--log2fc-threshold", type=float, default=1.0, help="log2 fold-change threshold for volcano/summary plots")
    parser.add_argument(
        "--r-enhanced", action="store_true",
        help="Generate R Enhanced ggplot2 figures in addition to standard Python plots."
    )
    args = parser.parse_args()

    # -- Parameter validation --
    from skills.singlecell._lib.param_validators import ParamValidator
    v = ParamValidator(SKILL_NAME)
    v.positive("n_top_genes", args.n_top_genes, min_val=1)
    v.fraction("padj_threshold", args.padj_threshold)
    v.non_negative("log2fc_threshold", args.log2fc_threshold)
    v.non_negative("pseudobulk_min_cells", args.pseudobulk_min_cells)
    v.non_negative("pseudobulk_min_counts", args.pseudobulk_min_counts)
    v.check()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, _ = sc_io.load_repo_demo_data("pbmc3k_processed")
        ensure_input_contract(adata)
        input_file = None
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        adata = sc_io.smart_load(args.input_path, skill_name=SKILL_NAME, preserve_all=True)
        input_file = args.input_path

    if not get_matrix_contract(adata):
        inferred_x_kind = infer_x_matrix_kind(adata)
        inferred_raw_kind = None
        if adata.raw is not None and adata.raw.shape == adata.shape and matrix_looks_count_like(adata.raw.X):
            inferred_raw_kind = "raw_counts_snapshot"
        elif adata.raw is not None and adata.raw.shape == adata.shape:
            inferred_raw_kind = "normalized_expression"
        layers_contract = {"counts": "raw_counts"} if "counts" in adata.layers else {}
        record_matrix_contract(
            adata,
            x_kind=inferred_x_kind,
            raw_kind=inferred_raw_kind,
            layers=layers_contract,
            producer_skill="input_h5ad",
        )

    logger.info("Input: %d cells x %d genes", adata.n_obs, adata.n_vars)
    method = validate_method_choice(args.method, METHOD_REGISTRY)
    apply_preflight(
        preflight_sc_de(
            adata,
            method=method,
            groupby=args.groupby,
            group1=args.group1,
            group2=args.group2,
            sample_key=args.sample_key,
            celltype_key=args.celltype_key,
            source_path=input_file,
            n_top_genes=args.n_top_genes,
            logreg_solver=args.logreg_solver,
            pseudobulk_min_cells=args.pseudobulk_min_cells,
            pseudobulk_min_counts=args.pseudobulk_min_counts,
        ),
        logger,
        demo_mode=args.demo,
    )
    _validate_runtime_dependencies(method)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    if method == "deseq2_r":
        full_df, summary = run_de_deseq2_r_method(
            adata,
            condition_key=args.groupby,
            group1=args.group1,
            group2=args.group2,
            sample_key=args.sample_key or "sample_id",
            celltype_key=args.celltype_key,
            pseudobulk_min_cells=args.pseudobulk_min_cells,
            pseudobulk_min_counts=args.pseudobulk_min_counts,
        )
        full_df.to_csv(tables_dir / "de_full.csv", index=False)
        sig_df = full_df.sort_values("padj", na_position="last")
        sig_df.to_csv(tables_dir / "markers_top.csv", index=False)
        generate_pseudobulk_figures(
            full_df,
            output_dir,
            padj_threshold=args.padj_threshold,
            log2fc_threshold=args.log2fc_threshold,
        )
    elif method == "mast":
        full_df, summary = run_de_mast_method(adata, groupby=args.groupby, group1=args.group1, group2=args.group2)
        top_df = full_df.sort_values(["padj", "pvalue"], na_position="last").groupby("group", observed=False).head(args.n_top_genes)
        full_df.to_csv(tables_dir / "de_full.csv", index=False)
        top_df.to_csv(tables_dir / "markers_top.csv", index=False)
        generate_tabular_de_figures(full_df, top_df, output_dir, group_col="group", gene_col="gene")
    else:
        full_df, summary = run_de_scanpy(
            adata,
            args.groupby,
            method,
            args.group1,
            args.group2,
            logreg_solver=args.logreg_solver,
        )
        top_df = full_df.groupby("group", observed=False).head(args.n_top_genes)
        full_df.to_csv(tables_dir / "de_full.csv", index=False)
        top_df.to_csv(tables_dir / "markers_top.csv", index=False)
        generate_scanpy_figures(adata, full_df, top_df, output_dir, min(5, args.n_top_genes))

    summary["n_cells"] = int(adata.n_obs)
    summary.setdefault("requested_method", method)
    summary.setdefault("executed_method", summary.get("method", method))
    summary.setdefault("fallback_used", summary["requested_method"] != summary["executed_method"])
    params = {
        "groupby": summary.get("groupby", args.groupby),
        "method": method,
        "requested_method": summary["requested_method"],
        "executed_method": summary["executed_method"],
        "n_top_genes": args.n_top_genes,
        "logreg_solver": args.logreg_solver if method == "logreg" else None,
        "group1": args.group1,
        "group2": args.group2,
        "sample_key": args.sample_key,
        "celltype_key": args.celltype_key,
        "pseudobulk_min_cells": args.pseudobulk_min_cells if method == "deseq2_r" else None,
        "pseudobulk_min_counts": args.pseudobulk_min_counts if method == "deseq2_r" else None,
        "padj_threshold": args.padj_threshold,
        "log2fc_threshold": args.log2fc_threshold,
        "expression_source": summary.get("expression_source", "adata.X"),
    }

    write_report(output_dir, summary, input_file, params)

    source_matrix_contract = get_matrix_contract(adata)
    propagate_singlecell_contracts(
        adata,
        adata,
        producer_skill=SKILL_NAME,
        x_kind=source_matrix_contract.get("X") or infer_x_matrix_kind(adata),
        raw_kind=source_matrix_contract.get("raw") or raw_matrix_kind(adata),
        primary_cluster_key=source_matrix_contract.get("primary_cluster_key"),
    )
    store_analysis_metadata(adata, SKILL_NAME, summary["executed_method"], params)

    output_h5ad = output_dir / "processed.h5ad"
    adata.write_h5ad(output_h5ad)
    logger.info("Saved to %s", output_h5ad)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {
        "requested_method": summary["requested_method"],
        "executed_method": summary["executed_method"],
        "fallback_used": bool(summary.get("fallback_used")),
        "fallback_reason": summary.get("fallback_reason"),
        "params": params,
        "input_contract": adata.uns.get("omicsclaw_input_contract", {}),
        "matrix_contract": adata.uns.get("omicsclaw_matrix_contract", {}),
    }
    result_data["next_steps"] = [
        {"skill": "sc-enrichment", "reason": "Pathway enrichment analysis on DE genes", "priority": "recommended"},
    ]
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME,
        "summary": summary,
        "data": result_data,
    }
    write_standard_run_artifacts(output_dir, result_payload, summary)

    # R Enhanced figures (only when --r-enhanced flag is set)
    r_enhanced_figures = _render_r_enhanced(
        output_dir=output_dir,
        figure_data_dir=output_dir / "figure_data",
        r_enhanced=args.r_enhanced,
    )
    if r_enhanced_figures:
        result_data["r_enhanced_figures"] = r_enhanced_figures

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(
        f"DE complete: {summary['n_groups']} groups, "
        f"requested={summary['requested_method']}, executed={summary['executed_method']}"
    )

    # --- Next-step guidance ---
    print()
    print("▶ Next step: Run sc-enrichment for pathway enrichment on DE results")
    print(f"  python omicsclaw.py run sc-enrichment --input {output_dir}/processed.h5ad --output <dir>")


if __name__ == "__main__":
    main()
