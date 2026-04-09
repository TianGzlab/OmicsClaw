#!/usr/bin/env python3
"""Single-cell statistical enrichment on marker or DE rankings."""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import anndata

    anndata.settings.allow_write_nullable_strings = True
except Exception:
    pass

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
from skills.singlecell._lib.adata_utils import (
    ensure_input_contract,
    get_matrix_contract,
    infer_x_matrix_kind,
    propagate_singlecell_contracts,
    store_analysis_metadata,
)
from skills.singlecell._lib.export import save_h5ad
from skills.singlecell._lib.method_config import MethodConfig, validate_method_choice
from skills.singlecell._lib.preflight import (
    _format_candidates,
    _obs_candidates,
    apply_preflight,
    preflight_sc_enrichment,
)
from skills.singlecell._lib.stat_enrichment import (
    auto_rank_markers,
    build_demo_gene_sets,
    canonicalize_gene_sets,
    fetch_gene_sets_from_library,
    normalize_ranking_table,
    run_gsea,
    run_ora,
    sanitize_term_slug,
    select_top_terms,
    sort_results,
    write_gene_sets_gmt,
    read_gene_sets,
)
from skills.singlecell._lib.viz import (
    compute_running_score_curve,
    plot_enrichment_enrichmap,
    plot_enrichment_group_summary,
    plot_enrichment_group_term_dotplot,
    plot_enrichment_ridgeplot,
    plot_enrichment_top_terms_bar,
    plot_gsea_running_score_panels,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-enrichment"
SKILL_VERSION = "0.1.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-enrichment/sc_enrichment.py"
R_SCRIPTS_DIR = Path(__file__).resolve().parent / "rscripts"

METHOD_REGISTRY: dict[str, MethodConfig] = {
    "ora": MethodConfig(
        name="ora",
        description="Over-representation analysis on positive markers / DE genes",
        dependencies=(),
    ),
    "gsea": MethodConfig(
        name="gsea",
        description="Preranked gene set enrichment on full marker / DE rankings",
        dependencies=(),
    ),
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
            description="Single-cell statistical enrichment on marker or DE rankings.",
            result_payload=result_payload,
            preferred_method=summary.get("method", "ora"),
            script_path=Path(__file__).resolve(),
            actual_command=[sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to write analysis notebook: %s", exc)

    try:
        write_output_readme(
            output_dir,
            skill_alias=SKILL_NAME,
            description="Single-cell statistical enrichment on marker or DE rankings.",
            result_payload=result_payload,
            preferred_method=summary.get("method", "ora"),
            notebook_path=notebook_path,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to write README.md: %s", exc)


def _resolve_groupby(adata, requested_groupby: str | None) -> tuple[str | None, list[str], str | None]:
    candidates = []
    matrix_contract = get_matrix_contract(adata)
    primary_cluster_key = matrix_contract.get("primary_cluster_key")
    if primary_cluster_key and primary_cluster_key in adata.obs.columns:
        candidates.append(str(primary_cluster_key))
    for family in ("cluster", "cell_type"):
        for column in _obs_candidates(adata, family):
            if column not in candidates:
                candidates.append(column)

    if requested_groupby:
        return (requested_groupby if requested_groupby in adata.obs.columns else None), candidates, None
    if not candidates:
        return None, candidates, None
    auto_groupby = candidates[0]
    guidance = (
        f"No `--groupby` was provided, so cluster-vs-rest rankings will use `{auto_groupby}`. "
        f"Other plausible label columns: {_format_candidates(candidates)}."
    )
    return auto_groupby, candidates, guidance


def _load_adata(input_path: Path):
    adata = sc_io.smart_load(str(input_path), skill_name=SKILL_NAME, preserve_all=True)
    ensure_input_contract(adata)
    return adata


def _detect_ranking_source_from_dir(
    input_dir: Path,
    *,
    method: str,
    adata,
    groupby: str | None,
    ranking_method: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    tables_dir = input_dir / "tables"
    markers_path = tables_dir / "markers_all.csv"
    de_path = tables_dir / "de_full.csv"
    result_json_path = input_dir / "result.json"
    upstream_skill = None
    if result_json_path.exists():
        try:
            upstream_skill = json.loads(result_json_path.read_text(encoding="utf-8")).get("skill")
        except Exception:
            upstream_skill = None

    if method == "ora" and markers_path.exists():
        return normalize_ranking_table(pd.read_csv(markers_path)), {
            "ranking_source": "markers_table",
            "upstream_skill": upstream_skill or "sc-markers",
            "auto_ranked": False,
        }

    if de_path.exists():
        return normalize_ranking_table(pd.read_csv(de_path)), {
            "ranking_source": "de_table",
            "upstream_skill": upstream_skill or "sc-de",
            "auto_ranked": False,
        }

    resolved_groupby, candidates, guidance = _resolve_groupby(adata, groupby)
    if not resolved_groupby:
        raise ValueError(
            "This directory did not contain reusable ranking tables, and no valid `groupby` column was found in `processed.h5ad` "
            f"for automatic cluster-vs-rest ranking. Candidate columns: {_format_candidates(candidates)}."
        )
    ranking_df = auto_rank_markers(adata, groupby=resolved_groupby, method=ranking_method)
    return normalize_ranking_table(ranking_df), {
        "ranking_source": "auto_cluster_ranking",
        "upstream_skill": upstream_skill or "processed_h5ad",
        "auto_ranked": True,
        "groupby": resolved_groupby,
        "guidance": guidance,
    }


def _load_input_context(
    *,
    input_path: str | None,
    demo: bool,
    method: str,
    groupby: str | None,
    ranking_method: str,
    output_dir: Path,
) -> tuple[object, pd.DataFrame, dict[str, object], str | None]:
    if demo:
        adata, _ = sc_io.load_repo_demo_data("pbmc3k_processed")
        ensure_input_contract(adata)
        resolved_groupby, candidates, guidance = _resolve_groupby(adata, groupby)
        if not resolved_groupby:
            raise ValueError(
                "Demo single-cell enrichment needs a cluster/cell-type column for auto-ranking, but none was found."
            )
        ranking_df = normalize_ranking_table(auto_rank_markers(adata, groupby=resolved_groupby, method=ranking_method))
        source_meta = {
            "input_mode": "demo",
            "ranking_source": "auto_cluster_ranking",
            "upstream_skill": "demo_pbmc3k_processed",
            "auto_ranked": True,
            "groupby": resolved_groupby,
            "guidance": guidance,
            "candidate_groupby": candidates,
        }
        return adata, ranking_df, source_meta, None

    if not input_path:
        raise ValueError("--input is required unless `--demo` is used.")

    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input path not found: {path}")

    if path.is_dir():
        processed_h5ad = path / "processed.h5ad"
        if not processed_h5ad.exists():
            raise FileNotFoundError(
                f"Input directory `{path}` does not contain `processed.h5ad`. "
                "Pass a standard output directory from `sc-markers`/`sc-de` or a processed h5ad directly."
            )
        adata = _load_adata(processed_h5ad)
        ranking_df, source_meta = _detect_ranking_source_from_dir(
            path,
            method=method,
            adata=adata,
            groupby=groupby,
            ranking_method=ranking_method,
        )
        source_meta["input_mode"] = "upstream_output_dir"
        source_meta["input_path"] = str(path)
        return adata, ranking_df, source_meta, str(processed_h5ad)

    if path.suffix.lower() != ".h5ad":
        raise ValueError(
            "sc-enrichment currently accepts a processed `.h5ad`, or an output directory from `sc-markers` / `sc-de`."
        )

    adata = _load_adata(path)
    resolved_groupby, candidates, guidance = _resolve_groupby(adata, groupby)
    if not resolved_groupby:
        raise ValueError(
            "Direct h5ad input needs a cluster/cell-type column for automatic ranking. "
            f"Candidate columns: {_format_candidates(candidates)}."
        )
    ranking_df = normalize_ranking_table(auto_rank_markers(adata, groupby=resolved_groupby, method=ranking_method))
    source_meta = {
        "input_mode": "h5ad_auto_ranking",
        "ranking_source": "auto_cluster_ranking",
        "upstream_skill": "input_h5ad",
        "auto_ranked": True,
        "groupby": resolved_groupby,
        "guidance": guidance,
        "candidate_groupby": candidates,
    }
    return adata, ranking_df, source_meta, str(path)


def _resolve_gene_sets(
    *,
    demo: bool,
    species: str,
    gene_sets_path: str | None,
    gene_set_db: str | None,
    gene_set_from_markers: str | None,
    marker_group: str | None,
    marker_top_n: str,
    gene_universe: list[str],
    output_dir: Path,
) -> tuple[dict[str, list[str]], Path, dict[str, object]]:
    if demo:
        gene_sets = canonicalize_gene_sets(build_demo_gene_sets(species=species), gene_universe)
        resolved_path = write_gene_sets_gmt(gene_sets, output_dir / "demo_gene_sets.gmt")
        return gene_sets, resolved_path, {
            "requested_source": "omicsclaw_demo",
            "resolved_source": "omicsclaw_demo",
            "library_mode": "builtin_demo",
        }

    if gene_sets_path:
        raw_sets = read_gene_sets(gene_sets_path)
        gene_sets = canonicalize_gene_sets(raw_sets, gene_universe)
        resolved_path = write_gene_sets_gmt(gene_sets, output_dir / "resolved_gene_sets.gmt")
        return gene_sets, resolved_path, {
            "requested_source": str(gene_sets_path),
            "resolved_source": str(Path(gene_sets_path).name),
            "library_mode": "local_file",
        }

    if gene_set_from_markers:
        marker_source = Path(gene_set_from_markers)
        marker_table = marker_source
        if marker_source.is_dir():
            marker_table = marker_source / "tables" / "markers_all.csv"
        if not marker_table.exists():
            raise FileNotFoundError(
                f"`--gene-set-from-markers` did not resolve to a marker table. Expected `markers_all.csv` at {marker_table}."
            )
        markers_df = pd.read_csv(marker_table)
        if "group" not in markers_df.columns or "names" not in markers_df.columns:
            raise ValueError("Marker gene-set source must contain `group` and `names` columns.")
        groups = markers_df["group"].astype(str)
        requested_groups = [item.strip() for item in str(marker_group).split(",") if item.strip()] if marker_group else []
        selected_groups = requested_groups or groups.dropna().unique().tolist()
        top_n_value = str(marker_top_n).strip().lower()
        limit = None if top_n_value == "all" else int(top_n_value)
        gene_sets_raw: dict[str, list[str]] = {}
        for group in selected_groups:
            group_df = markers_df[groups == str(group)].copy()
            if group_df.empty:
                continue
            if "pvals_adj" in group_df.columns:
                group_df = group_df.sort_values("pvals_adj", ascending=True, na_position="last")
            elif "scores" in group_df.columns:
                group_df = group_df.sort_values("scores", ascending=False, na_position="last")
            if limit is not None:
                group_df = group_df.head(limit)
            genes = [str(gene).strip() for gene in group_df["names"].dropna().astype(str).tolist() if str(gene).strip()]
            if genes:
                gene_sets_raw[str(group)] = list(dict.fromkeys(genes))
        gene_sets = canonicalize_gene_sets(gene_sets_raw, gene_universe)
        if not gene_sets:
            raise ValueError(
                "No valid marker-derived gene sets remained after applying group selection and gene-universe overlap."
            )
        resolved_path = write_gene_sets_gmt(gene_sets, output_dir / "marker_gene_sets.gmt")
        return gene_sets, resolved_path, {
            "requested_source": str(gene_set_from_markers),
            "resolved_source": str(marker_table.name),
            "library_mode": "marker_gene_sets",
            "marker_groups": selected_groups,
            "marker_top_n": marker_top_n,
        }

    if not gene_set_db:
        raise ValueError("Provide either `--gene-sets <local.gmt>` or `--gene-set-db <hallmark|kegg|...>`.")

    raw_sets, resolved_source = fetch_gene_sets_from_library(gene_set_db, species=species)
    gene_sets = canonicalize_gene_sets(raw_sets, gene_universe)
    resolved_path = write_gene_sets_gmt(gene_sets, output_dir / f"{sanitize_term_slug(resolved_source)}.gmt")
    return gene_sets, resolved_path, {
        "requested_source": gene_set_db,
        "resolved_source": resolved_source,
        "library_mode": "remote_library",
    }


def _r_stack_available() -> tuple[bool, list[str]]:
    required = ["clusterProfiler", "enrichplot"]
    try:
        validate_r_environment(required_r_packages=required)
        return True, []
    except Exception:
        runner = RScriptRunner(scripts_dir=R_SCRIPTS_DIR, timeout=30, verbose=False)
        return False, runner.get_missing_packages(required) if runner.check_r_available() else required


def _resolve_engine(requested: str) -> tuple[str, list[str]]:
    if requested == "python":
        return "python", []
    available, missing = _r_stack_available()
    if requested == "r":
        if not available:
            raise ImportError(
                "R enrichment engine requires `clusterProfiler` and `enrichplot`.\n"
                f"Missing packages: {', '.join(missing) or 'unknown'}"
            )
        return "r", []
    if available:
        return "r", []
    return "python", missing


def _build_ora_gene_table(
    ranking_df: pd.DataFrame,
    *,
    ora_padj_cutoff: float,
    ora_log2fc_cutoff: float,
    ora_max_genes: int,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for group, group_df in ranking_df.groupby("group", sort=False):
        filtered = group_df.dropna(subset=["gene"]).copy()
        if "pvals_adj" in filtered.columns and pd.to_numeric(filtered["pvals_adj"], errors="coerce").notna().any():
            filtered = filtered[pd.to_numeric(filtered["pvals_adj"], errors="coerce").fillna(np.inf) <= float(ora_padj_cutoff)]
        effect_source = None
        for candidate in ("logfoldchanges", "scores", "stat"):
            if candidate in filtered.columns and pd.to_numeric(filtered[candidate], errors="coerce").notna().any():
                effect_source = candidate
                break
        if effect_source == "logfoldchanges":
            filtered = filtered[pd.to_numeric(filtered["logfoldchanges"], errors="coerce").fillna(-np.inf) >= float(ora_log2fc_cutoff)]
        elif effect_source in {"scores", "stat"}:
            filtered = filtered[pd.to_numeric(filtered[effect_source], errors="coerce").fillna(-np.inf) > 0]
        filtered = filtered.head(int(ora_max_genes))
        if filtered.empty:
            continue
        frame = filtered[["group", "gene"]].copy()
        rows.append(frame)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["group", "gene"])


def _run_clusterprofiler_engine(
    *,
    method: str,
    ranking_df: pd.DataFrame,
    background_genes: list[str],
    gene_sets_path: Path,
    output_dir: Path,
    top_terms: int,
    ora_padj_cutoff: float,
    ora_log2fc_cutoff: float,
    ora_max_genes: int,
    gsea_ranking_metric: str,
    gsea_min_size: int,
    gsea_max_size: int,
    gsea_permutation_num: int,
    gsea_seed: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    runner = RScriptRunner(scripts_dir=R_SCRIPTS_DIR, timeout=7200)
    r_input_dir = output_dir / "reproducibility" / "r_engine_inputs"
    r_input_dir.mkdir(parents=True, exist_ok=True)
    background_path = r_input_dir / "background_genes.txt"
    background_path.write_text("\n".join(dict.fromkeys(background_genes)) + "\n", encoding="utf-8")

    if method == "ora":
        r_input = _build_ora_gene_table(
            ranking_df,
            ora_padj_cutoff=ora_padj_cutoff,
            ora_log2fc_cutoff=ora_log2fc_cutoff,
            ora_max_genes=ora_max_genes,
        )
    else:
        rows: list[pd.DataFrame] = []
        for group, group_df in ranking_df.groupby("group", sort=False):
            metric = group_df.copy()
            metric_name = group_df.attrs.get("ranking_metric", gsea_ranking_metric)
            if metric_name == "auto":
                metric_name = "stat" if "stat" in group_df.columns else ("scores" if "scores" in group_df.columns else "logfoldchanges")
            metric["score"] = pd.to_numeric(metric[metric_name], errors="coerce")
            rows.append(metric[["group", "gene", "score"]])
        r_input = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["group", "gene", "score"])

    ranking_csv = r_input_dir / ("ora_input.csv" if method == "ora" else "gsea_input.csv")
    r_input.to_csv(ranking_csv, index=False)

    runner.run_script(
        "sc_clusterprofiler_enrichment.R",
        args=[
            method,
            str(ranking_csv),
            str(background_path),
            str(gene_sets_path),
            str(output_dir),
            str(top_terms),
            str(gsea_min_size),
            str(gsea_max_size),
            str(gsea_permutation_num),
            str(gsea_seed),
        ],
        output_dir=output_dir,
        expected_outputs=["clusterprofiler_results.csv"],
    )

    result_path = output_dir / "clusterprofiler_results.csv"
    if not result_path.exists():
        return pd.DataFrame(), {"warnings": ["clusterProfiler returned no output table."], "engine": "r.clusterProfiler"}

    res = pd.read_csv(result_path)
    if res.empty:
        return res, {"warnings": ["clusterProfiler returned an empty result table."], "engine": "r.clusterProfiler"}

    metadata_path = output_dir / "r_plot_metadata.json"
    plot_metadata = {}
    if metadata_path.exists():
        try:
            plot_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            plot_metadata = {}
    r_fig_dir = output_dir / "r_figures"
    if r_fig_dir.exists():
        figures_dir = output_dir / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)
        for png in r_fig_dir.glob("*.png"):
            shutil.copy2(png, figures_dir / png.name)

    if method == "ora":
        standardized = res.rename(
            columns={
                "Description": "term",
                "ID": "gene_set",
                "pvalue": "pvalue",
                "p.adjust": "pvalue_adj",
                "Count": "gene_count",
                "GeneRatio": "overlap",
                "qvalue": "qvalue",
            }
        )
        standardized["term"] = standardized.get("term", standardized.get("gene_set", "")).astype(str)
        standardized["gene_set"] = standardized.get("gene_set", standardized.get("term", "")).astype(str)
        standardized["score"] = -np.log10(pd.to_numeric(standardized["pvalue_adj"], errors="coerce").clip(lower=1e-300))
        standardized["odds_ratio"] = np.nan
        standardized["genes"] = standardized.get("geneID", standardized.get("genes", "")).astype(str).str.replace("/", ";", regex=False)
        standardized["source"] = "clusterProfiler"
        standardized["library_mode"] = "r_clusterprofiler"
        standardized["engine"] = "r.clusterProfiler"
        standardized["method_used"] = "ora"
        standardized["n_input_genes"] = standardized.groupby("group")["gene_count"].transform("max")
        desired = ["group", "term", "gene_set", "source", "library_mode", "engine", "method_used", "score", "odds_ratio", "gene_count", "overlap", "pvalue", "pvalue_adj", "genes", "n_input_genes"]
    else:
        standardized = res.rename(
            columns={
                "Description": "term",
                "ID": "gene_set",
                "NES": "nes",
                "enrichmentScore": "es",
                "pvalue": "pvalue",
                "p.adjust": "pvalue_adj",
                "core_enrichment": "leading_edge",
            }
        )
        standardized["term"] = standardized.get("term", standardized.get("gene_set", "")).astype(str)
        standardized["gene_set"] = standardized.get("gene_set", standardized.get("term", "")).astype(str)
        standardized["score"] = pd.to_numeric(standardized["nes"], errors="coerce")
        standardized["source"] = "clusterProfiler"
        standardized["library_mode"] = "r_clusterprofiler"
        standardized["engine"] = "r.clusterProfiler"
        standardized["method_used"] = "gsea"
        standardized["ranking_metric"] = gsea_ranking_metric
        desired = ["group", "term", "gene_set", "source", "library_mode", "engine", "method_used", "ranking_metric", "score", "nes", "es", "pvalue", "pvalue_adj", "leading_edge"]
    for column in desired:
        if column not in standardized.columns:
            standardized[column] = np.nan
    return standardized[desired], {
        "warnings": [],
        "engine": "r.clusterProfiler",
        "plot_metadata": plot_metadata,
    }


def _build_group_summary(enrich_df: pd.DataFrame, *, fdr_threshold: float) -> pd.DataFrame:
    if enrich_df.empty:
        return pd.DataFrame(columns=["group", "n_terms", "n_significant", "top_term", "top_abs_score", "best_pvalue_adj"])

    frame = enrich_df.copy()
    if "score" not in frame.columns:
        frame["score"] = np.nan
    frame["score"] = pd.to_numeric(frame["score"], errors="coerce")
    frame["pvalue_adj"] = pd.to_numeric(frame.get("pvalue_adj"), errors="coerce")
    rows: list[dict[str, object]] = []
    for group, group_df in frame.groupby("group", sort=False):
        ordered = sort_results(group_df)
        top_row = ordered.iloc[0] if not ordered.empty else pd.Series(dtype=object)
        rows.append(
            {
                "group": str(group),
                "n_terms": int(len(group_df)),
                "n_significant": int(group_df["pvalue_adj"].fillna(np.inf).le(float(fdr_threshold)).sum()) if "pvalue_adj" in group_df.columns else 0,
                "top_term": str(top_row.get("term", "")),
                "top_abs_score": abs(float(pd.to_numeric(pd.Series([top_row.get("score")]), errors="coerce").fillna(0.0).iloc[0])),
                "best_pvalue_adj": float(pd.to_numeric(group_df["pvalue_adj"], errors="coerce").min()) if "pvalue_adj" in group_df.columns else np.nan,
            }
        )
    summary_df = pd.DataFrame(rows)
    summary_df = summary_df.sort_values(
        by=["n_significant", "top_abs_score", "n_terms", "group"],
        ascending=[False, False, False, True],
        kind="mergesort",
    ).reset_index(drop=True)
    return summary_df


def _write_tables(
    output_dir: Path,
    *,
    enrich_df: pd.DataFrame,
    group_summary_df: pd.DataFrame,
    ranking_df: pd.DataFrame,
    top_terms_df: pd.DataFrame,
    gsea_running_tables: dict[tuple[str, str], pd.DataFrame] | None = None,
) -> dict[str, str]:
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    files = {
        "enrichment_results": "enrichment_results.csv",
        "enrichment_significant": "enrichment_significant.csv",
        "group_summary": "group_summary.csv",
        "ranking_input": "ranking_input.csv",
        "top_terms": "top_terms.csv",
    }
    enrich_df.to_csv(tables_dir / files["enrichment_results"], index=False)
    significant_df = enrich_df.copy()
    if "pvalue_adj" in significant_df.columns:
        significant_df = significant_df[pd.to_numeric(significant_df["pvalue_adj"], errors="coerce").fillna(np.inf) <= 0.05]
    significant_df.to_csv(tables_dir / files["enrichment_significant"], index=False)
    group_summary_df.to_csv(tables_dir / files["group_summary"], index=False)
    ranking_df.to_csv(tables_dir / files["ranking_input"], index=False)
    top_terms_df.to_csv(tables_dir / files["top_terms"], index=False)

    for key, value in files.items():
        source = tables_dir / value
        target = figure_data_dir / value
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    if gsea_running_tables:
        running_rows = []
        for (group, term), table in gsea_running_tables.items():
            if table.empty:
                continue
            frame = table.copy()
            frame.insert(0, "term", term)
            frame.insert(0, "group", group)
            running_rows.append(frame)
        if running_rows:
            running_df = pd.concat(running_rows, ignore_index=True)
            files["gsea_running_scores"] = "gsea_running_scores.csv"
            running_df.to_csv(tables_dir / files["gsea_running_scores"], index=False)
            running_df.to_csv(figure_data_dir / files["gsea_running_scores"], index=False)

    (figure_data_dir / "manifest.json").write_text(
        json.dumps({"skill": SKILL_NAME, "available_files": files}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return files


def _render_figures(
    output_dir: Path,
    *,
    enrich_df: pd.DataFrame,
    top_terms_df: pd.DataFrame,
    group_summary_df: pd.DataFrame,
    method: str,
    ranking_by_group: dict[str, pd.Series] | None,
    ranking_df: pd.DataFrame,
    gene_sets: dict[str, list[str]],
) -> None:
    plot_enrichment_top_terms_bar(top_terms_df, output_dir)
    plot_enrichment_group_term_dotplot(top_terms_df, output_dir)
    plot_enrichment_group_summary(group_summary_df, output_dir)
    plot_enrichment_enrichmap(top_terms_df, gene_sets, output_dir)
    plot_enrichment_ridgeplot(top_terms_df, ranking_df, gene_sets, output_dir)
    if method != "gsea":
        return
    if not ranking_by_group:
        ranking_by_group = {}
        metric = None
        for candidate in ("stat", "scores", "logfoldchanges", "log2FoldChange", "score"):
            if candidate in ranking_df.columns and pd.to_numeric(ranking_df[candidate], errors="coerce").notna().any():
                metric = candidate
                break
        if metric is not None:
            for group, group_df in ranking_df.groupby("group", sort=False):
                ranking_by_group[str(group)] = (
                    group_df[["gene", metric]]
                    .dropna()
                    .drop_duplicates(subset=["gene"], keep="first")
                    .set_index("gene")[metric]
                    .sort_values(ascending=False)
                )
    running_tables: dict[tuple[str, str], pd.DataFrame] = {}
    for _, row in top_terms_df.head(4).iterrows():
        group = str(row.get("group", ""))
        term = str(row.get("term", ""))
        ranking = ranking_by_group.get(group)
        genes = gene_sets.get(term)
        if ranking is None or not genes:
            continue
        running_tables[(group, term)] = compute_running_score_curve(ranking, genes)
    plot_gsea_running_score_panels(running_tables, output_dir)


def _write_report(
    output_dir: Path,
    *,
    summary: dict,
    params: dict,
    input_file: str | None,
    group_summary_df: pd.DataFrame,
) -> None:
    header = generate_report_header(
        title="Single-Cell Statistical Enrichment Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary["method"],
            "Ranking source": summary["ranking_source"],
            "Groups": str(summary["n_groups"]),
            "Significant terms": str(summary["n_significant_terms"]),
        },
    )

    lines = [
        "## Summary\n",
        f"- **Method**: `{summary['method']}`",
        f"- **Requested engine**: `{summary['requested_engine']}`",
        f"- **Resolved engine**: `{summary['resolved_engine']}`",
        f"- **Engine(s)**: {summary['engine_summary']}",
        f"- **Ranking source**: `{summary['ranking_source']}`",
        f"- **Gene-set source**: `{summary['resolved_source']}` ({summary['library_mode']})",
        f"- **Groups tested**: {summary['n_groups']}",
        f"- **Terms tested**: {summary['n_terms_tested']}",
        f"- **Significant terms (`p_adj <= {summary['fdr_threshold']}`)**: {summary['n_significant_terms']}",
        "",
        "## What This Skill Does\n",
        "- `sc-enrichment` performs **statistical enrichment** on marker or DE rankings.",
        "- Use it when you want GO / KEGG / Reactome / Hallmark terms that are statistically over-represented or enriched.",
        "- If you instead want a **per-cell pathway activity score**, use `sc-pathway-scoring`.",
        "",
        "## First-pass Settings\n",
        f"- `method`: {params['method']}",
        f"- `groupby`: {params.get('groupby', 'embedded in ranking table')}",
        f"- `ranking_method` (auto-ranking only): {params.get('ranking_method')}",
        f"- `gene_sets`: {params.get('gene_sets')}",
        f"- `gene_set_db`: {params.get('gene_set_db')}",
        f"- `species`: {params.get('species')}",
    ]

    if params["method"] == "ora":
        lines.extend(
            [
                f"- `ora_padj_cutoff`: {params['ora_padj_cutoff']}",
                f"- `ora_log2fc_cutoff`: {params['ora_log2fc_cutoff']}",
                f"- `ora_max_genes`: {params['ora_max_genes']}",
            ]
        )
    else:
        lines.extend(
            [
                f"- `gsea_ranking_metric`: {params['gsea_ranking_metric']}",
                f"- `gsea_min_size`: {params['gsea_min_size']}",
                f"- `gsea_max_size`: {params['gsea_max_size']}",
                f"- `gsea_permutation_num`: {params['gsea_permutation_num']}",
                f"- `gsea_weight`: {params['gsea_weight']}",
            ]
        )

    lines.extend(
        [
            "",
            "## Beginner Notes\n",
            "- If you just finished clustering and want biological interpretation, this skill can auto-rank cluster markers from a processed h5ad.",
            "- If you already ran `sc-markers` or `sc-de`, passing that output directory reuses the exported ranking table when possible.",
            "- For condition DE enrichment with biological replicates, run `sc-de` first and then pass its output directory here.",
            "",
            "## Recommended Next Steps\n",
            "- Use `sc-cell-annotation` if enriched terms suggest a clearer lineage interpretation than your current labels.",
            "- Use `sc-pathway-scoring` if you want to project a specific signature back to each individual cell.",
            "- Revisit `sc-de` if you need a cleaner ranked list or a replicate-aware condition contrast before enrichment.",
            "",
            "## Output Files\n",
            "- `processed.h5ad` — downstream-facing AnnData with enrichment metadata attached.",
            "- `tables/enrichment_results.csv` — all tested terms.",
            "- `tables/enrichment_significant.csv` — significant subset.",
            "- `tables/group_summary.csv` — counts of significant terms and the strongest term per group.",
            "- `tables/ranking_input.csv` — the gene ranking actually used for enrichment.",
            "- `figures/` — bar/dot/summary plus GSEA running-score panels when applicable.",
        ]
    )

    if summary.get("warnings"):
        lines.extend(["", "## Warnings\n"])
        for warning in summary["warnings"]:
            lines.append(f"- {warning}")

    if not group_summary_df.empty:
        lines.extend(["", "## Top-term snapshot\n"])
        for _, row in group_summary_df.head(8).iterrows():
            lines.append(
                f"- `{row['group']}`: top term `{row['top_term']}` with {int(row['n_significant'])} significant terms"
            )

    report = header + "\n".join(lines) + "\n" + generate_report_footer()
    (output_dir / "report.md").write_text(report, encoding="utf-8")


def _write_reproducibility(output_dir: Path, *, params: dict, input_file: str | None, demo: bool) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)
    parts = ["python", SCRIPT_REL_PATH]
    if demo:
        parts.append("--demo")
    elif input_file:
        parts.extend(["--input", input_file])
    else:
        parts.extend(["--input", "<input>"])
    parts.extend(["--output", str(output_dir), "--method", params["method"]])
    for key in ("groupby", "gene_sets", "gene_set_db", "gene_set_from_markers", "marker_group", "marker_top_n", "species", "top_terms", "ranking_method"):
        value = params.get(key)
        if value not in (None, ""):
            parts.extend([f"--{key.replace('_', '-')}", str(value)])
    if params["method"] == "ora":
        for key in ("ora_padj_cutoff", "ora_log2fc_cutoff", "ora_max_genes"):
            parts.extend([f"--{key.replace('_', '-')}", str(params[key])])
    else:
        for key in ("gsea_ranking_metric", "gsea_min_size", "gsea_max_size", "gsea_permutation_num", "gsea_weight", "gsea_seed"):
            parts.extend([f"--{key.replace('_', '-')}", str(params[key])])
    command = " ".join(shlex.quote(part) for part in parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")
    _write_repro_requirements(repro_dir, ["scanpy", "anndata", "numpy", "pandas", "matplotlib", "seaborn", "gseapy"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Single-cell statistical enrichment")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=list(METHOD_REGISTRY.keys()), default="ora")
    parser.add_argument("--engine", choices=["auto", "python", "r"], default="auto")
    parser.add_argument("--groupby", default=None)
    parser.add_argument("--ranking-method", default="wilcoxon", choices=["wilcoxon", "t-test", "logreg"])
    parser.add_argument("--gene-sets", dest="gene_sets_path", default=None)
    parser.add_argument("--gene-set-db", dest="gene_set_db", default=None)
    parser.add_argument("--gene-set-from-markers", dest="gene_set_from_markers", default=None)
    parser.add_argument("--marker-group", dest="marker_group", default=None, help="Comma-separated marker groups to convert into gene sets")
    parser.add_argument("--marker-top-n", dest="marker_top_n", default="100", help="How many marker genes to keep per group, or `all`")
    parser.add_argument("--species", choices=["human", "mouse"], default="human")
    parser.add_argument("--top-terms", type=int, default=18)
    parser.add_argument("--ora-padj-cutoff", type=float, default=0.05)
    parser.add_argument("--ora-log2fc-cutoff", type=float, default=0.25)
    parser.add_argument("--ora-max-genes", type=int, default=200)
    parser.add_argument("--gsea-ranking-metric", default="auto", choices=["auto", "stat", "scores", "logfoldchanges", "log2FoldChange"])
    parser.add_argument("--gsea-min-size", type=int, default=5)
    parser.add_argument("--gsea-max-size", type=int, default=500)
    parser.add_argument("--gsea-permutation-num", type=int, default=100)
    parser.add_argument("--gsea-weight", type=float, default=1.0)
    parser.add_argument("--gsea-seed", type=int, default=123)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    method = validate_method_choice(args.method, METHOD_REGISTRY)
    adata, ranking_df, source_meta, input_file = _load_input_context(
        input_path=args.input_path,
        demo=args.demo,
        method=method,
        groupby=args.groupby,
        ranking_method=args.ranking_method,
        output_dir=output_dir,
    )

    apply_preflight(
        preflight_sc_enrichment(
            adata,
            method=method,
            engine=args.engine,
            groupby=args.groupby or source_meta.get("groupby"),
            gene_sets_path=args.gene_sets_path,
            gene_set_db=args.gene_set_db,
            gene_set_from_markers=args.gene_set_from_markers,
            marker_group=args.marker_group,
            marker_top_n=args.marker_top_n,
            source_mode=str(source_meta.get("ranking_source")),
            source_path=input_file,
            ranking_method=args.ranking_method,
            demo=args.demo,
        ),
        logger,
    )

    gene_sets, resolved_gene_sets_path, gene_set_meta = _resolve_gene_sets(
        demo=args.demo,
        species=args.species,
        gene_sets_path=args.gene_sets_path,
        gene_set_db=args.gene_set_db,
        gene_set_from_markers=args.gene_set_from_markers,
        marker_group=args.marker_group,
        marker_top_n=args.marker_top_n,
        gene_universe=adata.var_names.astype(str).tolist(),
        output_dir=output_dir,
    )
    if not gene_sets:
        raise ValueError("No overlapping genes remained after aligning the selected gene sets to the dataset gene universe.")

    params = {
        "method": method,
        "engine": args.engine,
        "groupby": source_meta.get("groupby", args.groupby),
        "ranking_method": args.ranking_method,
        "gene_sets": str(resolved_gene_sets_path),
        "gene_set_db": args.gene_set_db,
        "gene_set_from_markers": args.gene_set_from_markers,
        "marker_group": args.marker_group,
        "marker_top_n": args.marker_top_n,
        "species": args.species,
        "top_terms": args.top_terms,
        "ora_padj_cutoff": args.ora_padj_cutoff,
        "ora_log2fc_cutoff": args.ora_log2fc_cutoff,
        "ora_max_genes": args.ora_max_genes,
        "gsea_ranking_metric": args.gsea_ranking_metric,
        "gsea_min_size": args.gsea_min_size,
        "gsea_max_size": args.gsea_max_size,
        "gsea_permutation_num": args.gsea_permutation_num,
        "gsea_weight": args.gsea_weight,
        "gsea_seed": args.gsea_seed,
    }

    ranking_df = normalize_ranking_table(ranking_df)
    resolved_engine, missing_r_packages = _resolve_engine(args.engine)
    if resolved_engine == "r":
        enrich_df, method_meta = _run_clusterprofiler_engine(
            method=method,
            ranking_df=ranking_df,
            background_genes=adata.var_names.astype(str).tolist(),
            gene_sets_path=resolved_gene_sets_path,
            output_dir=output_dir,
            top_terms=args.top_terms,
            ora_padj_cutoff=args.ora_padj_cutoff,
            ora_log2fc_cutoff=args.ora_log2fc_cutoff,
            ora_max_genes=args.ora_max_genes,
            gsea_ranking_metric=args.gsea_ranking_metric,
            gsea_min_size=args.gsea_min_size,
            gsea_max_size=args.gsea_max_size,
            gsea_permutation_num=args.gsea_permutation_num,
            gsea_seed=args.gsea_seed,
        )
        ranking_by_group = None
    else:
        if args.engine == "auto" and missing_r_packages:
            logger.info(
                "R clusterProfiler stack is not fully available (%s); using Python enrichment engine.",
                ", ".join(missing_r_packages),
            )
        if method == "ora":
            enrich_df, method_meta = run_ora(
                ranking_df,
                source=str(gene_set_meta["resolved_source"]),
                library_mode=str(gene_set_meta["library_mode"]),
                gene_sets=gene_sets,
                background_genes=adata.var_names.astype(str).tolist(),
                ora_padj_cutoff=args.ora_padj_cutoff,
                ora_log2fc_cutoff=args.ora_log2fc_cutoff,
                ora_max_genes=args.ora_max_genes,
            )
            ranking_by_group = None
        else:
            enrich_df, method_meta = run_gsea(
                ranking_df,
                source=str(gene_set_meta["resolved_source"]),
                library_mode=str(gene_set_meta["library_mode"]),
                gene_sets=gene_sets,
                ranking_metric=args.gsea_ranking_metric,
                gsea_min_size=args.gsea_min_size,
                gsea_max_size=args.gsea_max_size,
                gsea_permutation_num=args.gsea_permutation_num,
                gsea_weight=args.gsea_weight,
                gsea_seed=args.gsea_seed,
            )
            ranking_by_group = method_meta.get("ranking_by_group")

    enrich_df = sort_results(enrich_df)
    if args.engine == "auto" and resolved_engine == "python" and missing_r_packages:
        method_meta.setdefault("warnings", []).append(
            "R clusterProfiler engine was unavailable and this run used the Python implementation instead. "
            f"Missing R packages: {', '.join(missing_r_packages)}"
        )
    top_terms_df = select_top_terms(enrich_df, top_terms=args.top_terms)
    group_summary_df = _build_group_summary(enrich_df, fdr_threshold=0.05)
    _render_figures(
        output_dir,
        enrich_df=enrich_df,
        top_terms_df=top_terms_df,
        group_summary_df=group_summary_df,
        method=method,
        ranking_by_group=ranking_by_group,
        ranking_df=ranking_df,
        gene_sets=gene_sets,
    )

    running_tables: dict[tuple[str, str], pd.DataFrame] | None = None
    if method == "gsea" and ranking_by_group:
        running_tables = {}
        for _, row in top_terms_df.head(4).iterrows():
            group = str(row.get("group", ""))
            term = str(row.get("term", ""))
            ranking = ranking_by_group.get(group)
            genes = gene_sets.get(term)
            if ranking is None or not genes:
                continue
            running_tables[(group, term)] = compute_running_score_curve(ranking, genes, weight=args.gsea_weight)

    figure_data_files = _write_tables(
        output_dir,
        enrich_df=enrich_df,
        group_summary_df=group_summary_df,
        ranking_df=ranking_df,
        top_terms_df=top_terms_df,
        gsea_running_tables=running_tables,
    )

    source_matrix_contract = get_matrix_contract(adata)
    input_contract, matrix_contract = propagate_singlecell_contracts(
        adata,
        adata,
        producer_skill=SKILL_NAME,
        x_kind=source_matrix_contract.get("X") or infer_x_matrix_kind(adata),
        raw_kind=source_matrix_contract.get("raw"),
        primary_cluster_key=source_matrix_contract.get("primary_cluster_key") or source_meta.get("groupby"),
    )
    store_analysis_metadata(adata, SKILL_NAME, method, params)
    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(adata, output_h5ad)

    engines = sorted(set(enrich_df["engine"].dropna().astype(str).tolist())) if not enrich_df.empty and "engine" in enrich_df.columns else []
    summary = {
        "method": method,
        "ranking_source": source_meta.get("ranking_source"),
        "upstream_skill": source_meta.get("upstream_skill"),
        "groupby": source_meta.get("groupby"),
        "n_groups": int(ranking_df["group"].astype(str).nunique()) if "group" in ranking_df.columns else 0,
        "n_gene_sets_available": int(len(gene_sets)),
        "n_terms_tested": int(len(enrich_df)),
        "n_significant_terms": int(pd.to_numeric(enrich_df.get("pvalue_adj"), errors="coerce").fillna(1.0).le(0.05).sum()) if not enrich_df.empty else 0,
        "engine_summary": ", ".join(engines) if engines else "none",
        "requested_engine": args.engine,
        "resolved_engine": resolved_engine,
        "requested_source": gene_set_meta["requested_source"],
        "resolved_source": gene_set_meta["resolved_source"],
        "library_mode": gene_set_meta["library_mode"],
        "warnings": list(method_meta.get("warnings", [])),
        "fdr_threshold": 0.05,
    }
    _write_report(output_dir, summary=summary, params=params, input_file=input_file, group_summary_df=group_summary_df)
    _write_reproducibility(output_dir, params=params, input_file=input_file, demo=args.demo)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {
        "params": params,
        "input_contract": input_contract,
        "matrix_contract": matrix_contract,
        "requested_source": gene_set_meta["requested_source"],
        "resolved_source": gene_set_meta["resolved_source"],
        "library_mode": gene_set_meta["library_mode"],
        "visualization": {"available_figure_data": figure_data_files},
        "ranking_source": source_meta,
    }
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    result_payload = load_result_json(output_dir) or {"skill": SKILL_NAME, "summary": summary, "data": result_data}
    write_standard_run_artifacts(output_dir, result_payload, summary)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Statistical enrichment complete: method={method}, groups={summary['n_groups']}, significant_terms={summary['n_significant_terms']}")


if __name__ == "__main__":
    main()
