#!/usr/bin/env python3
"""Single-cell gene-set enrichment and pathway scoring."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

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
from skills._sdk.report import (
    generate_report_footer,
    generate_report_header,
)
from skills._sdk.result import (
    load_result_json,
    write_result_json,
)
from skills._sdk.deps import validate_r_environment
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.adata_utils import (
    GENE_SYMBOL_CANDIDATE_COLUMNS,
    ensure_input_contract,
    get_matrix_contract,
    infer_x_matrix_kind,
    matrix_kind_is_normalized,
    record_matrix_contract,
    store_analysis_metadata,
)
from skills.singlecell._lib.export import save_h5ad
from skills.singlecell._lib.method_config import MethodConfig, validate_method_choice
from skills.singlecell._lib.preflight import (
    _format_candidates,
    _obs_candidates,
    apply_preflight,
    preflight_sc_pathway_scoring,
)
from skills.singlecell._lib.viz import (
    plot_enrichment_embedding_panels,
    plot_group_mean_dotplot,
    plot_group_mean_heatmap,
    plot_pathway_score_distributions,
    plot_top_gene_sets_bar,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-pathway-scoring"
SKILL_VERSION = "0.3.0"
DEFAULT_METHOD = "aucell_r"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-pathway-scoring/sc_pathway_scoring.py"

R_ENHANCED_PLOTS = {
    # pathway-scoring exports gene_expression.csv (pathway score per cell, long format).
    # No UMAP/embedding CSV — embedding renderers not appropriate at this stage.
    "plot_feature_violin": "r_pathway_violin.png",
}
R_SCRIPTS_DIR = Path(__file__).resolve().parent / "rscripts"
SHARED_PARAM_KEYS = ("method", "gene_sets", "groupby", "top_pathways")
GENE_SET_DB_ALIASES = {
    "hallmark": {"human": "MSigDB_Hallmark_2020", "mouse": "MSigDB_Hallmark_2020"},
    "kegg": {"human": "KEGG_2021_Human", "mouse": "KEGG_2021_Mouse"},
    "reactome": {"human": "Reactome_2022", "mouse": "Reactome_2022"},
    "go_bp": {"human": "GO_Biological_Process_2023", "mouse": "GO_Biological_Process_2023"},
    "go_cc": {"human": "GO_Cellular_Component_2023", "mouse": "GO_Cellular_Component_2023"},
    "go_mf": {"human": "GO_Molecular_Function_2023", "mouse": "GO_Molecular_Function_2023"},
}

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "aucell_r": MethodConfig(
        name="aucell_r",
        description="AUCell gene-set activity scoring using the official Bioconductor package",
        dependencies=(),
    ),
    "score_genes_py": MethodConfig(
        name="score_genes_py",
        description="Scanpy/Seurat-style module scoring on normalized expression",
        dependencies=(),
    ),
    "aucell_py": MethodConfig(
        name="aucell_py",
        description="Pure Python AUCell gene-set scoring (no R required)",
        dependencies=(),
    ),
}

METHOD_PARAM_DEFAULTS: dict[str, dict[str, object]] = {
    "aucell_r": {
        "method": "aucell_r",
        "groupby": None,
        "top_pathways": 20,
        "aucell_auc_max_rank": None,
    },
    "score_genes_py": {
        "method": "score_genes_py",
        "groupby": None,
        "top_pathways": 20,
        "score_genes_ctrl_size": 50,
        "score_genes_n_bins": 25,
    },
    "aucell_py": {
        "method": "aucell_py",
        "groupby": None,
        "top_pathways": 20,
        "aucell_py_auc_threshold": 0.05,
    },
}

METHOD_PARAM_KEYS: dict[str, tuple[str, ...]] = {
    "aucell_r": ("aucell_auc_max_rank",),
    "score_genes_py": ("score_genes_ctrl_size", "score_genes_n_bins"),
    "aucell_py": ("aucell_py_auc_threshold",),
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




def _slugify_gene_set_name(name: str) -> str:
    chars = []
    for char in str(name):
        chars.append(char.lower() if char.isalnum() else "_")
    slug = "".join(chars).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "gene_set"





def _resolve_groupby(adata, requested_groupby: str | None) -> tuple[str | None, list[str], str | None]:
    candidates = []
    for family in ("cell_type", "cluster"):
        for column in _obs_candidates(adata, family):
            if column not in candidates:
                candidates.append(column)

    if requested_groupby:
        return (requested_groupby if requested_groupby in adata.obs.columns else None), candidates, None

    if not candidates:
        return None, candidates, None

    auto_groupby = candidates[0]
    guidance = (
        f"No `--groupby` was provided, so grouped summaries will default to `{auto_groupby}`. "
        f"Other plausible label columns: {_format_candidates(candidates)}."
    )
    return auto_groupby, candidates, guidance


def _ensure_matrix_contract_for_output(adata) -> None:
    if get_matrix_contract(adata):
        return
    layers: dict[str, str | None] = {}
    if "counts" in adata.layers:
        layers["counts"] = "raw_counts"
    raw_kind = "raw_counts_snapshot" if adata.raw is not None else None
    record_matrix_contract(
        adata,
        x_kind=infer_x_matrix_kind(adata),
        raw_kind=raw_kind,
        layers=layers,
        producer_skill=SKILL_NAME,
    )




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


def _normalize_species(species: str | None) -> str:
    normalized = str(species or "human").strip().lower()
    if normalized in {"human", "hs", "homo_sapiens", "homo sapiens"}:
        return "human"
    if normalized in {"mouse", "mm", "mus_musculus", "mus musculus"}:
        return "mouse"
    return normalized


def _gseapy_organism(species: str) -> str:
    normalized = _normalize_species(species)
    if normalized == "mouse":
        return "Mouse"
    return "Human"


def _resolve_gene_set_library_name(gene_set_db: str, species: str) -> str:
    normalized_db = str(gene_set_db).strip().lower()
    normalized_species = _normalize_species(species)
    alias = GENE_SET_DB_ALIASES.get(normalized_db)
    if alias:
        return alias.get(normalized_species, alias.get("human", gene_set_db))
    return str(gene_set_db).strip()


def _write_gene_sets_gmt(gene_sets: dict[str, list[str]], output_path: Path) -> Path:
    lines = []
    for name, members in gene_sets.items():
        clean_members = [str(member).strip() for member in members if str(member).strip()]
        if clean_members:
            lines.append("\t".join([str(name), "omicsclaw"] + clean_members))
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return output_path










def generate_figures(output_dir: Path, adata, summary: dict) -> list[str]:
    figures: list[str] = []

    top_df = summary.get("top_pathways_df", pd.DataFrame())
    path = plot_top_gene_sets_bar(top_df, output_dir)
    if path:
        figures.append(str(path))

    group_means_df = summary.get("group_means_df", pd.DataFrame())
    group_high_fraction_df = summary.get("group_high_fraction_df", pd.DataFrame())
    path = plot_group_mean_heatmap(group_means_df, output_dir)
    if path:
        figures.append(str(path))
    path = plot_group_mean_dotplot(group_means_df, group_high_fraction_df, output_dir)
    if path:
        figures.append(str(path))

    long_df = summary.get("top_pathway_scores_long_df", pd.DataFrame())
    path = plot_pathway_score_distributions(long_df, output_dir)
    if path:
        figures.append(str(path))

    embedding_key = next((key for key in ("X_umap", "X_tsne", "X_phate", "X_diffmap") if key in adata.obsm), None)
    score_columns = list(summary.get("score_columns", []))
    path = plot_enrichment_embedding_panels(
        adata,
        output_dir,
        obsm_key=embedding_key or "",
        score_columns=score_columns,
        score_labels=adata.uns.get("sc_pathway_scoring", {}).get("score_column_labels", {}),
    )
    if path:
        figures.append(str(path))

    return figures


def _write_figure_data(output_dir: Path, summary: dict, overlap_df: pd.DataFrame) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}

    datasets = {
        "top_pathways.csv": summary.get("top_pathways_df", pd.DataFrame()),
        "group_mean_scores.csv": summary.get("group_means_df", pd.DataFrame()),
        "group_high_fraction.csv": summary.get("group_high_fraction_df", pd.DataFrame()),
        "top_pathway_scores_long.csv": summary.get("top_pathway_scores_long_df", pd.DataFrame()),
        "gene_set_overlap.csv": overlap_df,
    }
    for filename, data in datasets.items():
        if isinstance(data, pd.DataFrame) and not data.empty:
            output_path = figure_data_dir / filename
            keep_index = not isinstance(data.index, pd.RangeIndex)
            data.to_csv(output_path, index=keep_index)
            manifest[filename] = output_path.name

    # Write gene_expression.csv for plot_feature_violin renderer.
    # Renames gene_set -> gene and score -> expression from top_pathway_scores_long.csv.
    long_df = summary.get("top_pathway_scores_long_df", pd.DataFrame())
    if isinstance(long_df, pd.DataFrame) and not long_df.empty:
        try:
            expr_df = long_df[["cell_id", "gene_set", "score"]].rename(
                columns={"gene_set": "gene", "score": "expression"}
            )
            expr_df.to_csv(figure_data_dir / "gene_expression.csv", index=False)
            manifest["gene_expression.csv"] = "gene_expression.csv"
        except Exception:
            pass

    (figure_data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def write_report(output_dir: Path, summary: dict, params: dict, input_file: str | None) -> None:
    header = generate_report_header(
        title="Single-Cell Pathway Scoring Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method"],
            "Gene sets scored": str(summary["n_gene_sets"]),
            "Grouping column": str(summary.get("groupby") or "none"),
        },
    )
    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary['method']}",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Gene sets requested**: {summary['n_gene_sets_requested']}",
        f"- **Gene sets scored**: {summary['n_gene_sets']}",
        f"- **Gene-set source**: {summary['gene_set_source']}",
        f"- **Grouping column**: {summary.get('groupby') or 'none'}",
        f"- **Expression source**: {summary['expression_source']}",
        f"- **Feature label source**: {summary['feature_label_source']}",
    ]
    if summary.get("effective_auc_max_rank") is not None:
        body_lines.append(f"- **Effective AUCell aucMaxRank**: {summary['effective_auc_max_rank']}")
    if summary.get("skipped_gene_sets"):
        body_lines.append(f"- **Skipped gene sets**: {', '.join(summary['skipped_gene_sets'])}")
    body_lines.extend(
        [
            "",
            "## What This Means\n",
            "- This skill scores pathway or gene-program activity per cell, then optionally summarizes those scores across a label column such as `cell_type` or `leiden`.",
            "- It is usually most interpretable after `sc-preprocessing`, and often after `sc-clustering` or `sc-cell-annotation` when grouped summaries matter.",
            "",
            "## Top Gene Sets\n",
            "| Gene set | Mean score | Mean absolute score |",
            "|----------|------------|---------------------|",
        ]
    )
    for _, row in summary["top_pathways_df"].head(15).iterrows():
        body_lines.append(
            f"| {row['gene_set']} | {row['mean_score']:.4f} | {row['mean_abs_score']:.4f} |"
        )
    body_lines.extend(["", "## Parameters\n"])
    for key, value in params.items():
        body_lines.append(f"- `{key}`: {value}")
    if summary.get("next_steps"):
        body_lines.extend(["", "## Usual Next Step\n"])
        body_lines.extend(f"- {line}" for line in summary["next_steps"])
    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer, encoding="utf-8")


def _next_step_guidance(groupby: str | None) -> list[str]:
    if groupby:
        return [
            f"If `{groupby}` reflects clusters or cell types, inspect the grouped pathway plots first, then continue to `sc-cell-annotation` or `sc-de` for biological interpretation.",
            "If these pathway scores highlight a condition effect, the usual follow-up is `sc-de` or a focused marker/pathway validation pass.",
        ]
    return [
        "This run produced per-cell pathway scores only. If you want cluster- or cell-type-level summaries next, run `sc-clustering` or `sc-cell-annotation` first and rerun with `--groupby`.",
    ]


def _render_r_enhanced(output_dir, figure_data_dir, r_enhanced):
    if not r_enhanced:
        return []
    from skills.singlecell._lib.viz.r import call_r_plot
    r_figures_dir = output_dir / "figures" / "r_enhanced"
    r_figures_dir.mkdir(parents=True, exist_ok=True)
    r_figure_paths = []
    for renderer, filename in R_ENHANCED_PLOTS.items():
        out_path = r_figures_dir / filename
        call_r_plot(renderer, figure_data_dir, out_path)
        if out_path.exists():
            r_figure_paths.append(str(out_path))
    return r_figure_paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Single-cell pathway and gene-set scoring")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", default=DEFAULT_METHOD, choices=list(METHOD_REGISTRY.keys()))
    parser.add_argument("--gene-sets", dest="gene_sets_path")
    parser.add_argument("--gene-set-db", dest="gene_set_db", default=None)
    parser.add_argument("--species", default="human")
    parser.add_argument("--groupby", default=None)
    parser.add_argument("--top-pathways", type=int, default=20)
    parser.add_argument("--aucell-auc-max-rank", type=int, default=None)
    parser.add_argument("--score-genes-ctrl-size", type=int, default=50)
    parser.add_argument("--score-genes-n-bins", type=int, default=25)
    # AUCell Python-specific
    parser.add_argument("--aucell-py-auc-threshold", type=float, default=0.05,
                        help="AUCell (Python) fraction of ranked genome for AUC (default 0.05)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for AUCell ranking (default: 42)")
    parser.add_argument("--r-enhanced", action="store_true", default=False, help="Generate R-enhanced figures via ggplot2 renderers")
    args = parser.parse_args()
    api = load_skill(SKILL_NAME)

    # -- Parameter validation --
    from skills.singlecell._lib.param_validators import ParamValidator
    v = ParamValidator(SKILL_NAME)
    v.positive("top_pathways", args.top_pathways, min_val=1)
    v.positive("score_genes_ctrl_size", args.score_genes_ctrl_size, min_val=1)
    v.positive("score_genes_n_bins", args.score_genes_n_bins, min_val=1)
    v.in_range("aucell_py_auc_threshold", args.aucell_py_auc_threshold, low=0, high=1, low_exclusive=True)
    v.check()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    method = validate_method_choice(args.method, METHOD_REGISTRY, fallback=DEFAULT_METHOD)
    if args.demo:
        adata, _ = sc_io.load_repo_demo_data("pbmc3k_processed")
        ensure_input_contract(adata, standardized=True)
        input_file = None
        gene_sets_path = _write_demo_gene_sets(adata, output_dir / "demo_gene_sets.gmt")
        gene_set_source = "demo_gmt"
        gene_sets = api.load_gene_sets(gene_sets_path)
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        if not args.gene_sets_path and not args.gene_set_db:
            raise ValueError("--gene-sets or --gene-set-db is required unless --demo is used")
        input_file = args.input_path
        adata = sc_io.smart_load(args.input_path, skill_name=SKILL_NAME, preserve_all=True)
        if args.gene_sets_path:
            gene_sets_path = Path(args.gene_sets_path)
            if not gene_sets_path.exists():
                raise FileNotFoundError(f"Gene set file not found: {gene_sets_path}")
            gene_set_source = str(gene_sets_path)
            gene_sets = api.load_gene_sets(gene_sets_path)
        else:
            gene_sets = api.load_gene_sets(args.gene_set_db, species=args.species)
            resolved_library = _resolve_gene_set_library_name(args.gene_set_db, args.species)
            gene_sets_path = _write_gene_sets_gmt(
                gene_sets,
                output_dir / f"resolved_{_slugify_gene_set_name(resolved_library)}.gmt",
            )
            gene_set_source = f"library:{resolved_library}"

    _ensure_matrix_contract_for_output(adata)
    overlap_df = api.gene_set_overlap(adata, gene_sets)
    feature_label_source = overlap_df["feature_label_source"].iloc[0]
    if overlap_df["n_matched_genes"].sum() <= 0:
        raise ValueError(
            "None of the supplied gene-set members matched the input features. Check gene identifiers or run a standardized object with consistent gene symbols."
        )

    resolved_groupby, groupby_candidates, auto_groupby_message = _resolve_groupby(adata, args.groupby)
    decision = preflight_sc_pathway_scoring(
        adata,
        method=method,
        gene_sets_path=str(gene_sets_path) if gene_sets_path else None,
        gene_set_db=args.gene_set_db,
        groupby=resolved_groupby,
        source_path=input_file,
    )
    if auto_groupby_message:
        decision.add_guidance(auto_groupby_message)
    if method == "aucell_r":
        try:
            validate_r_environment(required_r_packages=["AUCell", "GSEABase"])
        except ImportError as exc:
            decision.block(str(exc).strip())
    apply_preflight(decision, logger)

    shared_params = {
        "method": method,
        "groupby": resolved_groupby,
        "top_pathways": args.top_pathways,
        "gene_sets": str(gene_sets_path),
        "gene_set_db": args.gene_set_db,
        "species": args.species,
    }
    method_params_map = {
        "aucell_r": {"aucell_auc_max_rank": args.aucell_auc_max_rank},
        "score_genes_py": {
            "score_genes_ctrl_size": args.score_genes_ctrl_size,
            "score_genes_n_bins": args.score_genes_n_bins,
        },
        "aucell_py": {
            "aucell_py_auc_threshold": args.aucell_py_auc_threshold,
        },
    }
    method_params = method_params_map[method]
    params = dict(METHOD_PARAM_DEFAULTS[method])
    params.update(shared_params)
    params.update(method_params)

    scores_df = api.score_gene_sets(
        adata, gene_sets, method=method, auc_max_rank=args.aucell_auc_max_rank,
        auc_threshold=args.aucell_py_auc_threshold, ctrl_size=args.score_genes_ctrl_size,
        n_bins=args.score_genes_n_bins,
        random_state=0 if method == "score_genes_py" else args.seed,
    )
    info = api.run_info(scores_df)
    skipped_gene_sets = info["skipped_gene_sets"]
    effective_auc_max_rank = info["effective_auc_max_rank"]
    expression_source = info["expression_source"]
    adata = api.attach_scores(adata, scores_df)
    score_columns = adata.uns["sc_pathway_scoring"]["score_columns"]
    api.run_info(adata, keep=False)
    table_summary = api.score_summary(adata, scores_df, groupby=resolved_groupby, top_pathways=args.top_pathways)
    summary = {
        "method": method,
        "n_cells": int(adata.n_obs),
        "n_gene_sets_requested": int(len(gene_sets)),
        "n_gene_sets": int(scores_df.shape[1]),
        "gene_set_source": gene_set_source,
        "groupby": resolved_groupby,
        "expression_source": expression_source,
        "feature_label_source": feature_label_source,
        "effective_auc_max_rank": effective_auc_max_rank,
        "score_columns": score_columns,
        "skipped_gene_sets": skipped_gene_sets,
        "next_steps": _next_step_guidance(resolved_groupby),
        **table_summary,
    }

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    scores_df.reset_index().rename(columns={"index": "Cell"}).to_csv(tables_dir / "enrichment_scores.csv", index=False)
    overlap_df.to_csv(tables_dir / "gene_set_overlap.csv", index=False)
    summary["top_pathways_df"].to_csv(tables_dir / "top_pathways.csv", index=False)
    if not summary["group_means_df"].empty:
        summary["group_means_df"].to_csv(tables_dir / "group_mean_scores.csv")
    if not summary["group_high_fraction_df"].empty:
        summary["group_high_fraction_df"].to_csv(tables_dir / "group_high_fraction.csv")

    generate_figures(output_dir, adata, summary)
    _write_figure_data(output_dir, summary, overlap_df)
    write_report(output_dir, summary, params, input_file)

    store_analysis_metadata(adata, SKILL_NAME, method, params)
    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(adata, output_h5ad)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    command_parts = [
        "python",
        SCRIPT_REL_PATH,
        "--output",
        str(output_dir),
        "--method",
        method,
        "--top-pathways",
        str(args.top_pathways),
        "--gene-sets",
        str(gene_sets_path),
    ]
    if input_file:
        command_parts.extend(["--input", input_file])
    if resolved_groupby:
        command_parts.extend(["--groupby", resolved_groupby])
    if method == "aucell_r" and args.aucell_auc_max_rank is not None:
        command_parts.extend(["--aucell-auc-max-rank", str(args.aucell_auc_max_rank)])
    if method == "score_genes_py":
        command_parts.extend(
            [
                "--score-genes-ctrl-size",
                str(args.score_genes_ctrl_size),
                "--score-genes-n-bins",
                str(args.score_genes_n_bins),
            ]
        )
    (repro_dir / "commands.sh").write_text("#!/bin/bash\n" + " ".join(command_parts) + "\n", encoding="utf-8")
    repro_packages = ["scanpy", "anndata", "pandas", "matplotlib"]
    _write_repro_requirements(repro_dir, repro_packages)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    summary_json = {
        key: value
        for key, value in summary.items()
        if key
        not in {
            "top_pathways_df",
            "group_means_df",
            "group_high_fraction_df",
            "top_pathway_scores_long_df",
        }
    }
    result_data = {"params": params}
    result_data["next_steps"] = []
    r_enhanced_figures = _render_r_enhanced(output_dir, output_dir / "figure_data", args.r_enhanced)
    result_data["r_enhanced_figures"] = r_enhanced_figures
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary_json, result_data, checksum)
    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME,
        "summary": summary_json,
        "data": result_data,
    }

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"  Gene sets scored: {summary['n_gene_sets']}")

    # --- Next-step guidance ---
    print()
    print(">> Analysis complete. Consider sc-de to compare scores between groups:")
    print(f"  python skills/singlecell/scrna/sc-de/sc_de.py --input {output_dir}/processed.h5ad --output <dir>")


if __name__ == "__main__":
    main()
