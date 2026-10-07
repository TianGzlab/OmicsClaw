#!/usr/bin/env python3
"""Single-cell statistical enrichment on marker or DE rankings."""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import anndata

    anndata.settings.allow_write_nullable_strings = True
except Exception:
    pass

_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))

from skills._sdk.checksums import sha256_file
from skills._sdk.report import (
    generate_report_footer,
    generate_report_header,
)
from skills._sdk.result import (
    load_result_json,
    write_result_json,
)
from skills._sdk.notebook import load_skill

_api = load_skill("sc-enrichment")
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
    canonicalize_gene_sets,
    normalize_ranking_table,
    sanitize_term_slug,
    sort_results,
    write_gene_sets_gmt,
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
SKILL_VERSION = "0.4.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-enrichment/sc_enrichment.py"

# R Enhanced renderers for this skill.
# Shared renderers always run; GSEA-specific renderers only run for gsea method.
_R_ENHANCED_SHARED: dict[str, str] = {
    "plot_enrichment_bar": "r_enrichment_bar.png",
    "plot_enrichment_dotplot": "r_enrichment_dotplot.png",
    "plot_enrichment_lollipop": "r_enrichment_lollipop.png",
    "plot_enrichment_network": "r_enrichment_network.png",
    "plot_enrichment_enrichmap": "r_enrichment_enrichmap.png",
}
_R_ENHANCED_GSEA: dict[str, str] = {
    "plot_gsea_mountain": "r_gsea_mountain.png",
    "plot_gsea_nes_heatmap": "r_gsea_nes_heatmap.png",
}
# Full dict kept for template compatibility
R_ENHANCED_PLOTS: dict[str, str] = {**_R_ENHANCED_SHARED, **_R_ENHANCED_GSEA}


def _render_r_enhanced(
    output_dir: Path,
    figure_data_dir: Path,
    r_enhanced: bool,
    *,
    method: str = "ora",
) -> list[str]:
    """Run R Enhanced rendering pass. Always called after Python figures are complete."""
    if not r_enhanced:
        return []
    from skills.singlecell._lib.viz.r import call_r_plot
    r_figures_dir = output_dir / "figures" / "r_enhanced"
    r_figures_dir.mkdir(parents=True, exist_ok=True)
    plots = dict(_R_ENHANCED_SHARED)
    if method == "gsea":
        plots.update(_R_ENHANCED_GSEA)
    r_figure_paths: list[str] = []
    for renderer, filename in plots.items():
        out_path = r_figures_dir / filename
        call_r_plot(renderer, figure_data_dir, out_path)
        if out_path.exists():
            r_figure_paths.append(str(out_path))
    return r_figure_paths

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
    "gsea_r": MethodConfig(
        name="gsea_r",
        description="Gene set enrichment analysis via clusterProfiler + fgsea (R bridge)",
        dependencies=(),
    ),
    "gsva_r": MethodConfig(
        name="gsva_r",
        description="Gene Set Variation Analysis (group-level pathway scores) via GSVA R bridge",
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
    ranking_df = _api.rank_groups(adata, groupby=resolved_groupby, method=ranking_method)
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
        ranking_df = normalize_ranking_table(_api.rank_groups(adata, groupby=resolved_groupby, method=ranking_method))
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
    ranking_df = normalize_ranking_table(_api.rank_groups(adata, groupby=resolved_groupby, method=ranking_method))
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
        gene_sets = canonicalize_gene_sets(_api.demo_gene_sets(species=species), gene_universe)
        resolved_path = write_gene_sets_gmt(gene_sets, output_dir / "demo_gene_sets.gmt")
        return gene_sets, resolved_path, {
            "requested_source": "omicsclaw_demo",
            "resolved_source": "omicsclaw_demo",
            "library_mode": "builtin_demo",
        }

    if gene_sets_path:
        raw_sets = _api.load_gene_sets(gene_sets_path)
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
        selected_groups = [item.strip() for item in str(marker_group).split(",") if item.strip()] if marker_group else markers_df["group"].astype(str).unique().tolist()
        limit = None if str(marker_top_n).lower() == "all" else int(marker_top_n)
        gene_sets = _api.marker_gene_sets(markers_df, groups=selected_groups, top_n=limit, universe=gene_universe)
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

    raw_sets = _api.load_gene_sets(gene_set_db, species=species)
    resolved_source = raw_sets.source
    gene_sets = canonicalize_gene_sets(raw_sets, gene_universe)
    resolved_path = write_gene_sets_gmt(gene_sets, output_dir / f"{sanitize_term_slug(resolved_source)}.gmt")
    return gene_sets, resolved_path, {
        "requested_source": gene_set_db,
        "resolved_source": resolved_source,
        "library_mode": "remote_library",
    }









def _plot_gsva_heatmap(scores_df: pd.DataFrame, output_dir: Path) -> list[dict]:
    """Plot a heatmap of GSVA scores (pathways x groups). Returns figure metadata list."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    fig_path = figures_dir / "gsva_r_heatmap.png"
    fig_meta: list[dict] = []

    if scores_df.empty:
        # Write a placeholder figure
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.text(0.5, 0.5, "GSVA scores unavailable\n(R script did not produce results)",
                ha="center", va="center", fontsize=12, color="gray")
        ax.set_axis_off()
        fig.savefig(fig_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        fig_meta.append({"name": "gsva_r_heatmap", "path": str(fig_path), "placeholder": True})
        return fig_meta

    # Pivot to wide format: pathways x groups
    try:
        wide = scores_df.pivot(index="pathway", columns="group", values="gsva_score")
    except Exception:
        wide = scores_df.pivot_table(index="pathway", columns="group", values="gsva_score", aggfunc="mean")

    # Sort by variance to keep top 30 most variable pathways
    if len(wide) > 30:
        row_var = wide.var(axis=1).sort_values(ascending=False)
        wide = wide.loc[row_var.index[:30]]

    fig, ax = plt.subplots(figsize=(max(6, len(wide.columns) * 0.8), max(4, len(wide) * 0.3)))
    try:
        import seaborn as sns

        sns.heatmap(
            wide,
            cmap="RdBu_r",
            center=0,
            ax=ax,
            xticklabels=True,
            yticklabels=True,
            linewidths=0.5,
            cbar_kws={"label": "GSVA score"},
        )
    except ImportError:
        im = ax.imshow(wide.values, cmap="RdBu_r", aspect="auto")
        ax.set_xticks(range(len(wide.columns)))
        ax.set_xticklabels(wide.columns, rotation=45, ha="right")
        ax.set_yticks(range(len(wide.index)))
        ax.set_yticklabels(wide.index)
        plt.colorbar(im, ax=ax, label="GSVA score")

    ax.set_title("GSVA Pathway Activity Scores", fontsize=12)
    ax.set_xlabel("")
    ax.set_ylabel("")
    plt.tight_layout()
    fig.savefig(fig_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    fig_meta.append({"name": "gsva_r_heatmap", "path": str(fig_path), "placeholder": False})
    logger.info("GSVA heatmap saved to %s", fig_path)
    return fig_meta



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
    elif params["method"] == "gsva_r":
        lines.extend(
            [
                f"- `gsva_method`: {params.get('gsva_method', 'gsva')}",
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
    elif params["method"] == "gsva_r":
        pass  # gsva_r uses R-side gene sets; no extra CLI params needed
    else:
        for key in ("gsea_ranking_metric", "gsea_min_size", "gsea_max_size", "gsea_permutation_num", "gsea_weight", "gsea_seed"):
            parts.extend([f"--{key.replace('_', '-')}", str(params[key])])
    command = " ".join(shlex.quote(part) for part in parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")
    _write_repro_requirements(repro_dir, ["scanpy", "anndata", "numpy", "pandas", "matplotlib", "seaborn", "gseapy"])


def _restore_r_artifacts(table, output_dir, adata):
    """Persist the retained R bridge's files after its temporary run has ended."""
    for relative, content in table.attrs.pop("_cli_artifacts", {}).items():
        target = output_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    for key, value in table.attrs.pop("_legacy_uns", {}).items():
        adata.uns[key] = value


def main() -> None:
    parser = argparse.ArgumentParser(description="Single-cell statistical enrichment")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--method", choices=list(METHOD_REGISTRY.keys()), default="ora")
    parser.add_argument("--engine", choices=["auto", "python", "r"], default="python")
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
    parser.add_argument("--fdr-threshold", type=float, default=0.05,
                        help="FDR threshold for group-level summary (default: 0.05)")
    parser.add_argument(
        "--r-enhanced", action="store_true",
        help="Generate R Enhanced ggplot2 figures in addition to standard Python plots."
    )
    args = parser.parse_args()

    # -- Parameter validation --
    from skills.singlecell._lib.param_validators import ParamValidator
    v = ParamValidator(SKILL_NAME)
    v.positive("top_terms", args.top_terms, min_val=1)
    v.fraction("ora_padj_cutoff", args.ora_padj_cutoff)
    v.non_negative("ora_log2fc_cutoff", args.ora_log2fc_cutoff)
    v.positive("ora_max_genes", args.ora_max_genes, min_val=1)
    v.positive("gsea_min_size", args.gsea_min_size, min_val=1)
    v.positive("gsea_max_size", args.gsea_max_size, min_val=1)
    v.min_max_consistent("gsea_min_size", args.gsea_min_size, "gsea_max_size", args.gsea_max_size)
    v.positive("gsea_permutation_num", args.gsea_permutation_num, min_val=1)
    v.fraction("fdr_threshold", args.fdr_threshold)
    v.check()

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
        demo_mode=args.demo,
    )

    # --- gsva_r: dedicated R bridge path (bypasses gene set resolution entirely) ---
    if method == "gsva_r":
        resolved_groupby = source_meta.get("groupby") or args.groupby
        if not resolved_groupby:
            resolved_groupby, _, _ = _resolve_groupby(adata, args.groupby)
        if not resolved_groupby:
            raise ValueError("gsva_r needs a groupby column. Use --groupby <column>.")
        gsva_params = {
            "species": args.species,
            "gene_set_db": args.gene_set_db,
            "gsva_method": "gsva",
        }
        gsva_sets = _api.load_gene_sets(args.gene_sets_path, species=args.species) if args.gene_sets_path else None
        gsva_scores_df = _api.gsva(adata, gsva_sets, groupby=resolved_groupby, species=args.species,
                                  gene_set_db=args.gene_set_db or "GO_BP",
                                  min_size=args.gsea_min_size, max_size=args.gsea_max_size)
        gsva_meta = _api.run_info(gsva_scores_df)
        _restore_r_artifacts(gsva_scores_df, output_dir, adata)
        gsva_plots = _plot_gsva_heatmap(gsva_scores_df, output_dir)

        # Save processed h5ad
        source_matrix_contract = get_matrix_contract(adata)
        input_contract, matrix_contract = propagate_singlecell_contracts(
            adata,
            adata,
            producer_skill=SKILL_NAME,
            x_kind=source_matrix_contract.get("X") or infer_x_matrix_kind(adata),
            raw_kind=source_matrix_contract.get("raw"),
            primary_cluster_key=source_matrix_contract.get("primary_cluster_key") or resolved_groupby,
        )
        store_analysis_metadata(adata, SKILL_NAME, method, {"method": method, "groupby": resolved_groupby, **gsva_params})
        output_h5ad = output_dir / "processed.h5ad"
        save_h5ad(adata, output_h5ad)

        # Write tables
        tables_dir = output_dir / "tables"
        tables_dir.mkdir(parents=True, exist_ok=True)
        if not gsva_scores_df.empty:
            gsva_scores_df.to_csv(tables_dir / "gsva_r_scores.csv", index=False)

        summary = {
            "method": "gsva_r",
            "ranking_source": source_meta.get("ranking_source"),
            "upstream_skill": source_meta.get("upstream_skill"),
            "groupby": resolved_groupby,
            "n_groups": gsva_meta.get("n_groups", 0),
            "n_gene_sets_available": 0,
            "n_terms_tested": gsva_meta.get("n_pathways", 0),
            "n_significant_terms": gsva_meta.get("n_pathways", 0),
            "engine_summary": "r.gsva_r",
            "requested_engine": "r",
            "resolved_engine": "r.gsva_r",
            "requested_source": gsva_meta.get("db", "GO_BP"),
            "resolved_source": gsva_meta.get("db", "GO_BP"),
            "library_mode": "r_gsva_r",
            "warnings": list(gsva_meta.get("warnings", [])),
            "fdr_threshold": 0.05,
            "r_success": gsva_meta.get("r_success", False),
            "n_pathways": gsva_meta.get("n_pathways", 0),
        }

        # Write report
        _write_report(output_dir, summary=summary, params={"method": method, "groupby": resolved_groupby, **gsva_params},
                       input_file=input_file, group_summary_df=pd.DataFrame())
        _write_reproducibility(output_dir, params={"method": method, "groupby": resolved_groupby, **gsva_params},
                                input_file=input_file, demo=args.demo)

        checksum = (
            sha256_file(input_file)
            if input_file and Path(input_file).is_file()
            else ""
        )
        result_data = {
            "params": {"method": method, "groupby": resolved_groupby, **gsva_params},
            "input_contract": input_contract,
            "matrix_contract": matrix_contract,
            "requested_source": gsva_meta.get("db", "GO_BP"),
            "resolved_source": gsva_meta.get("db", "GO_BP"),
            "library_mode": "r_gsva_r",
            "visualization": {"available_figure_data": [p["path"] for p in gsva_plots]},
            "ranking_source": source_meta,
        }
        result_data["next_steps"] = [
            {"skill": "sc-cell-communication", "reason": "Explore ligand-receptor interactions between cell types", "priority": "optional"},
        ]
        write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
        result_payload = load_result_json(output_dir) or {"skill": SKILL_NAME, "summary": summary, "data": result_data}

        # R Enhanced figures (only when --r-enhanced flag is set)
        r_enhanced_figures = _render_r_enhanced(
            output_dir=output_dir,
            figure_data_dir=output_dir / "figure_data",
            r_enhanced=args.r_enhanced,
            method="gsva",
        )
        if r_enhanced_figures:
            result_data["r_enhanced_figures"] = r_enhanced_figures

        print(f"Success: {SKILL_NAME}")
        print(f"  Output: {output_dir}")
        print(f"GSVA complete: method=gsva_r, groups={gsva_meta.get('n_groups', 0)}, pathways={gsva_meta.get('n_pathways', 0)}")
        return

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

    if method == "ora":
        enrich_df = _api.ora(ranking_df, gene_sets, background=adata.var_names.astype(str).tolist(),
            engine=args.engine, padj_cutoff=args.ora_padj_cutoff, log2fc_cutoff=args.ora_log2fc_cutoff,
            max_genes=args.ora_max_genes, source=str(gene_set_meta["resolved_source"]),
            library_mode=str(gene_set_meta["library_mode"]), n_top=args.top_terms)
    else:
        enrich_df = _api.gsea(ranking_df, None if method == "gsea_r" else gene_sets,
            engine="gsea_r" if method == "gsea_r" else args.engine,
            ranking_metric=args.gsea_ranking_metric, min_size=args.gsea_min_size,
            max_size=args.gsea_max_size, permutation_num=args.gsea_permutation_num,
            weight=args.gsea_weight, random_state=args.gsea_seed,
            source=str(gene_set_meta["resolved_source"]), library_mode=str(gene_set_meta["library_mode"]),
            n_top=args.top_terms, species=args.species, gene_set_db=args.gene_set_db)
    method_meta = _api.run_info(enrich_df)
    resolved_engine = method_meta.pop("resolved_engine")
    missing_r_packages = method_meta.pop("missing_r_packages")
    ranking_by_group = enrich_df.attrs.get("ranking_by_group")
    _restore_r_artifacts(enrich_df, output_dir, adata)
    enrich_df.attrs.clear()

    enrich_df = sort_results(enrich_df)
    if args.engine == "auto" and resolved_engine == "python" and missing_r_packages:
        method_meta.setdefault("warnings", []).append(
            "R clusterProfiler engine was unavailable and this run used the Python implementation instead. "
            f"Missing R packages: {', '.join(missing_r_packages)}"
        )
    top_terms_df = _api.top_terms(enrich_df, n_top=args.top_terms)
    group_summary_df = _api.group_summary(enrich_df, fdr_threshold=args.fdr_threshold)
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

    checksum = (
        sha256_file(input_file)
        if input_file and Path(input_file).is_file()
        else ""
    )
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
    result_data["next_steps"] = [
        {"skill": "sc-cell-communication", "reason": "Explore ligand-receptor interactions between cell types", "priority": "optional"},
        {"skill": "sc-grn", "reason": "Infer gene regulatory networks", "priority": "optional"},
    ]
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    result_payload = load_result_json(output_dir) or {"skill": SKILL_NAME, "summary": summary, "data": result_data}

    # R Enhanced figures (only when --r-enhanced flag is set)
    r_enhanced_figures = _render_r_enhanced(
        output_dir=output_dir,
        figure_data_dir=output_dir / "figure_data",
        r_enhanced=args.r_enhanced,
        method=args.method,
    )
    if r_enhanced_figures:
        result_data["r_enhanced_figures"] = r_enhanced_figures

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Statistical enrichment complete: method={method}, groups={summary['n_groups']}, significant_terms={summary['n_significant_terms']}")

    # --- Next-step guidance ---
    print()
    print(">> Analysis complete. Further exploration:")
    print(f"  - sc-cell-communication: python skills/singlecell/scrna/sc-cell-communication/sc_cell_communication.py --input {output_dir}/processed.h5ad --output <dir>")
    print(f"  - sc-grn:                python skills/singlecell/scrna/sc-grn/sc_grn.py --input {output_dir}/processed.h5ad --output <dir>")


if __name__ == "__main__":
    main()
