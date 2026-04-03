#!/usr/bin/env python3
"""Single-cell gene-set enrichment via AUCell."""

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
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    load_result_json,
    write_output_readme,
    write_result_json,
)
from omicsclaw.core.dependency_manager import validate_r_environment
from omicsclaw.core.r_script_runner import RScriptRunner
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.adata_utils import store_analysis_metadata
from skills.singlecell._lib.method_config import MethodConfig, validate_method_choice
from skills.singlecell._lib.preflight import apply_preflight, preflight_sc_enrichment
from skills.singlecell._lib.viz_utils import save_figure

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-enrichment"
SKILL_VERSION = "0.1.0"
DEFAULT_METHOD = "aucell_r"
R_SCRIPTS_DIR = Path(__file__).resolve().parent / "rscripts"

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "aucell_r": MethodConfig(
        name="aucell_r",
        description="AUCell gene-set activity scoring using the official Bioconductor package",
        dependencies=(),
    ),
}

METHOD_PARAM_DEFAULTS: dict[str, dict[str, object]] = {
    "aucell_r": {
        "groupby": "leiden",
        "top_pathways": 20,
        "aucell_auc_max_rank": None,
    }
}


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
            description="Single-cell gene-set enrichment using AUCell.",
            result_payload=result_payload,
            preferred_method=summary.get("method", DEFAULT_METHOD),
            script_path=Path(__file__).resolve(),
            actual_command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        )
    except Exception as exc:
        logger.warning("Failed to write analysis notebook: %s", exc)

    try:
        write_output_readme(
            output_dir,
            skill_alias=SKILL_NAME,
            description="Single-cell gene-set enrichment using AUCell.",
            result_payload=result_payload,
            preferred_method=summary.get("method", DEFAULT_METHOD),
            notebook_path=notebook_path,
        )
    except Exception as exc:
        logger.warning("Failed to write README.md: %s", exc)


def _slugify_gene_set_name(name: str) -> str:
    chars = []
    for char in str(name):
        chars.append(char.lower() if char.isalnum() else "_")
    slug = "".join(chars).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "gene_set"


def _build_expression_export_adata(adata) -> tuple[sc.AnnData, str]:
    if adata.raw is not None and adata.raw.shape == adata.shape:
        export = sc.AnnData(X=adata.raw.X.copy(), obs=adata.obs.copy(), var=adata.raw.var.copy())
        export.obs_names = adata.obs_names.copy()
        export.var_names = adata.raw.var_names.copy()
        return export, "adata.raw"
    return adata.copy(), "adata.X"


def _write_expression_matrix_tsv(adata, output_path: Path) -> Path:
    matrix = adata.X
    if hasattr(matrix, "toarray"):
        matrix = matrix.toarray()
    expr_df = pd.DataFrame(
        matrix.T,
        index=adata.var_names.astype(str),
        columns=adata.obs_names.astype(str),
    )
    expr_df.to_csv(output_path, sep="\t")
    return output_path


def _write_demo_gene_sets(adata, output_path: Path) -> Path:
    genes = [str(gene) for gene in adata.var_names[:60]]
    gene_sets = {
        "Demo_Set_A": genes[0:15],
        "Demo_Set_B": genes[15:30],
        "Demo_Set_C": genes[30:45],
        "Demo_Set_D": genes[45:60],
    }
    lines = ["\t".join([name, "demo"] + members) for name, members in gene_sets.items()]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def run_aucell(adata, *, gene_sets_path: Path, auc_max_rank: int | None) -> tuple[pd.DataFrame, str, int]:
    validate_r_environment(required_r_packages=["AUCell", "GSEABase"])
    runner = RScriptRunner(scripts_dir=R_SCRIPTS_DIR, timeout=7200)
    export, source = _build_expression_export_adata(adata)
    effective_auc_max_rank = int(auc_max_rank) if auc_max_rank is not None else max(1, int(round(export.n_vars * 0.05)))
    with tempfile.TemporaryDirectory(prefix="omicsclaw_aucell_") as tmpdir:
        tmpdir_path = Path(tmpdir)
        input_matrix = tmpdir_path / "expression_matrix.tsv"
        output_dir = tmpdir_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        _write_expression_matrix_tsv(export, input_matrix)
        runner.run_script(
            "sc_aucell.R",
            args=[str(input_matrix), str(gene_sets_path), str(output_dir), str(effective_auc_max_rank)],
            expected_outputs=["aucell_scores.csv"],
            output_dir=output_dir,
        )
        scores_df = pd.read_csv(output_dir / "aucell_scores.csv")
    if "Cell" not in scores_df.columns:
        raise ValueError("AUCell output is missing the required 'Cell' column")
    return scores_df.set_index("Cell"), source, effective_auc_max_rank


def attach_scores_to_adata(adata, scores_df: pd.DataFrame) -> list[str]:
    aligned = scores_df.reindex(adata.obs_names.astype(str))
    if aligned.isna().all().all():
        raise ValueError("AUCell scores could not be aligned back to adata.obs_names")
    score_columns: list[str] = []
    for gene_set in aligned.columns:
        obs_key = f"aucell__{_slugify_gene_set_name(gene_set)}"
        adata.obs[obs_key] = pd.to_numeric(aligned[gene_set], errors="coerce")
        score_columns.append(obs_key)
    adata.uns["sc_enrichment"] = {
        "method": DEFAULT_METHOD,
        "score_columns": score_columns,
        "gene_sets": list(aligned.columns.astype(str)),
    }
    return score_columns


def summarize_scores(adata, scores_df: pd.DataFrame, *, groupby: str | None, top_pathways: int) -> dict[str, object]:
    overall = scores_df.mean(axis=0).sort_values(ascending=False)
    top_df = overall.head(top_pathways).rename_axis("gene_set").reset_index(name="mean_auc")
    group_means = pd.DataFrame()
    if groupby and groupby in adata.obs.columns:
        joined = scores_df.join(adata.obs[[groupby]])
        group_means = joined.groupby(groupby).mean(numeric_only=True)
        group_means = group_means.loc[:, overall.index.tolist()]
    return {"top_pathways_df": top_df, "group_means_df": group_means}


def generate_figures(output_dir: Path, summary: dict) -> list[str]:
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    figures: list[str] = []

    top_df = summary.get("top_pathways_df", pd.DataFrame())
    if not top_df.empty:
        fig, ax = plt.subplots(figsize=(10, 6))
        plot_df = top_df.head(15).iloc[::-1]
        ax.barh(plot_df["gene_set"], plot_df["mean_auc"], color="#4C78A8")
        ax.set_xlabel("Mean AUCell score")
        ax.set_title("Top Gene-Set Activities")
        fig.tight_layout()
        figures.append(str(save_figure(fig, figures_dir, "top_gene_sets.png")))
        plt.close(fig)

    group_means = summary.get("group_means_df", pd.DataFrame())
    if not group_means.empty:
        fig, ax = plt.subplots(figsize=(12, 6))
        shown = group_means.iloc[:, : min(20, group_means.shape[1])]
        im = ax.imshow(shown.values, aspect="auto")
        ax.set_yticks(range(len(shown.index)))
        ax.set_yticklabels(shown.index.astype(str))
        ax.set_xticks(range(shown.shape[1]))
        ax.set_xticklabels(shown.columns, rotation=45, ha="right")
        ax.set_title("Group Mean AUCell Scores")
        fig.colorbar(im, ax=ax)
        fig.tight_layout()
        figures.append(str(save_figure(fig, figures_dir, "group_mean_heatmap.png")))
        plt.close(fig)

    return figures


def write_report(output_dir: Path, summary: dict, params: dict, input_file: str | None) -> None:
    header = generate_report_header(
        title="Single-Cell Enrichment Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={"Method": summary["method"], "Gene sets": str(summary["n_gene_sets"])},
    )
    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Gene sets scored**: {summary['n_gene_sets']}",
        f"- **Grouping column**: {summary.get('groupby') or 'none'}",
        f"- **Expression source**: {summary['expression_source']}",
        f"- **Effective AUCell aucMaxRank**: {summary['effective_auc_max_rank']}",
        "",
        "## Top Gene Sets\n",
        "| Gene set | Mean AUCell score |",
        "|----------|-------------------|",
    ]
    for _, row in summary["top_pathways_df"].head(15).iterrows():
        body_lines.append(f"| {row['gene_set']} | {row['mean_auc']:.4f} |")
    body_lines.extend(["", "## Parameters\n"])
    for key, value in params.items():
        body_lines.append(f"- `{key}`: {value}")
    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Single-cell gene-set enrichment via AUCell")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default=DEFAULT_METHOD, choices=list(METHOD_REGISTRY.keys()))
    parser.add_argument("--gene-sets", dest="gene_sets_path")
    parser.add_argument("--groupby", default="leiden")
    parser.add_argument("--top-pathways", type=int, default=20)
    parser.add_argument("--aucell-auc-max-rank", type=int, default=None)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, _ = sc_io.load_repo_demo_data("pbmc3k_processed")
        input_file = None
        gene_sets_path = _write_demo_gene_sets(adata, output_dir / "demo_gene_sets.gmt")
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        if not args.gene_sets_path:
            raise ValueError("--gene-sets is required unless --demo is used")
        input_file = args.input_path
        adata = sc.read_h5ad(args.input_path)
        sc_io.maybe_warn_standardize_first(adata, source_path=args.input_path, skill_name=SKILL_NAME)
        gene_sets_path = Path(args.gene_sets_path)
        if not gene_sets_path.exists():
            raise FileNotFoundError(f"Gene set file not found: {gene_sets_path}")

    method = validate_method_choice(args.method, METHOD_REGISTRY, fallback=DEFAULT_METHOD)
    apply_preflight(
        preflight_sc_enrichment(
            adata,
            gene_sets_path=str(gene_sets_path) if gene_sets_path else None,
            groupby=args.groupby,
            source_path=input_file,
        ),
        logger,
    )
    params = dict(METHOD_PARAM_DEFAULTS[method])
    params.update(
        {
            "method": method,
            "groupby": args.groupby,
            "top_pathways": args.top_pathways,
            "aucell_auc_max_rank": args.aucell_auc_max_rank,
            "gene_sets": str(gene_sets_path),
        }
    )

    scores_df, expression_source, effective_auc_max_rank = run_aucell(
        adata,
        gene_sets_path=gene_sets_path,
        auc_max_rank=args.aucell_auc_max_rank,
    )
    score_columns = attach_scores_to_adata(adata, scores_df)
    groupby = args.groupby if args.groupby in adata.obs.columns else None
    table_summary = summarize_scores(adata, scores_df, groupby=groupby, top_pathways=args.top_pathways)
    summary = {
        "method": method,
        "n_cells": int(adata.n_obs),
        "n_gene_sets": int(scores_df.shape[1]),
        "groupby": groupby,
        "expression_source": expression_source,
        "effective_auc_max_rank": int(effective_auc_max_rank),
        "score_columns": score_columns,
        **table_summary,
    }

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    scores_df.reset_index().rename(columns={"index": "Cell"}).to_csv(tables_dir / "aucell_scores.csv", index=False)
    summary["top_pathways_df"].to_csv(tables_dir / "top_pathways.csv", index=False)
    if not summary["group_means_df"].empty:
        summary["group_means_df"].to_csv(tables_dir / "group_mean_scores.csv")

    generate_figures(output_dir, summary)
    write_report(output_dir, summary, params, input_file)

    store_analysis_metadata(adata, SKILL_NAME, method, params)
    output_h5ad = output_dir / "processed.h5ad"
    adata.write_h5ad(output_h5ad)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    command = f"python sc_enrichment.py --output {output_dir} --method {method} --top-pathways {args.top_pathways}"
    if input_file:
        command += f" --input {input_file}"
    command += f" --gene-sets {gene_sets_path}"
    if groupby:
        command += f" --groupby {groupby}"
    if args.aucell_auc_max_rank is not None:
        command += f" --aucell-auc-max-rank {args.aucell_auc_max_rank}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")
    _write_repro_requirements(repro_dir, ["scanpy", "anndata", "pandas", "matplotlib"])

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    summary_json = {key: value for key, value in summary.items() if key not in {"top_pathways_df", "group_means_df"}}
    result_data = {"params": params}
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary_json, result_data, checksum)
    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME,
        "summary": summary_json,
        "data": result_data,
    }
    write_standard_run_artifacts(output_dir, result_payload, summary)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"  Gene sets scored: {summary['n_gene_sets']}")


if __name__ == "__main__":
    main()
