"""Rank groups and test explicit gene sets; file output belongs to the caller."""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from skills._sdk.deps import validate_r_environment
from skills._sdk.r_script_runner import RScriptRunner
from skills._sdk.r_script_runner import R_SCRIPTS_DIR as _SDK_R_SCRIPTS_DIR
from skills.singlecell._lib.stat_enrichment import (
    auto_rank_markers, build_demo_gene_sets, canonicalize_gene_sets,
    fetch_gene_sets_from_library, normalize_ranking_table, read_gene_sets,
    run_gsea, run_ora, select_top_terms, sort_results, write_gene_sets_gmt,
)

__all__ = ["rank_groups", "load_gene_sets", "demo_gene_sets", "marker_gene_sets",
           "ora", "gsea", "gsva", "run_info", "top_terms", "group_summary", "top_terms_figure"]

logger = logging.getLogger(__name__)
R_SCRIPTS_DIR = Path(__file__).resolve().parent / "rscripts"
R_SCRIPTS_PROJECT_DIR = _SDK_R_SCRIPTS_DIR


class _GeneSets(dict):
    def __init__(self, sets, source):
        super().__init__(sets)
        self.source = source


def rank_groups(adata, *, groupby: str, method: str = "wilcoxon") -> pd.DataFrame:
    """Rank each group's genes against the rest using log-normalised ``X``.

    ``method`` is wilcoxon (default), t-test or logreg. This uses ``X``, not
    ``raw``; convert a scaled object with ``adata.raw.to_adata()`` first when
    raw holds log-normalised values. Scanpy ranking statistics remain in
    ``uns``. Return a table with group, gene and available scores/p-values.
    """
    return normalize_ranking_table(auto_rank_markers(adata, groupby=groupby, method=method))


def load_gene_sets(source, *, species: str = "human", universe=None) -> dict[str, list[str]]:
    """Load GMT/JSON or fetch an Enrichr library; optionally match genes to a universe.

    ``source`` accepts a local path or hallmark/kegg/reactome/go_bp aliases
    and full Enrichr library names. Remote sources need network access and
    gseapy; local files do not. ``species`` is human (default) or mouse.
    Return a term-to-gene-list mapping; no output files are written.
    """
    path = Path(source)
    if path.is_file() or path.suffix.lower() in {".gmt", ".json"}:
        sets, resolved = read_gene_sets(path), path.name
    else:
        try:
            sets, resolved = fetch_gene_sets_from_library(str(source), species=species)
        except ImportError as exc:
            raise ImportError("Remote gene sets need gseapy; use install_skill_deps for sc-enrichment.") from exc
    if universe is not None:
        sets = canonicalize_gene_sets(sets, universe)
    return _GeneSets(sets, resolved)


def demo_gene_sets(*, species: str = "human") -> dict[str, list[str]]:
    """Return the six named PBMC demo signatures, human by default or mouse symbols."""
    return build_demo_gene_sets(species=species)


def marker_gene_sets(markers: pd.DataFrame, *, groups=None, top_n: int | None = 100,
                     universe=None) -> dict[str, list[str]]:
    """Convert marker groups to gene sets, sorted by adjusted p-value or score.

    ``markers`` needs group and names (or gene). ``groups=None`` selects all;
    ``top_n=None`` keeps all genes. ``universe`` optionally restricts and
    canonicalises gene symbols. Raise ValueError when no sets remain.
    """
    frame = normalize_ranking_table(markers)
    selected = [str(x) for x in groups] if groups is not None else frame['group'].astype(str).unique()
    if top_n is not None and top_n < 1:
        raise ValueError("top_n must be positive or None")
    result = {}
    for group in selected:
        rows = frame[frame['group'].astype(str) == group]
        if 'pvals_adj' in rows:
            rows = rows.sort_values('pvals_adj', ascending=True, na_position='last')
        elif 'scores' in rows:
            rows = rows.sort_values('scores', ascending=False, na_position='last')
        genes = list(dict.fromkeys(rows.head(top_n)['gene'].dropna().astype(str))) if top_n is not None else list(dict.fromkeys(rows['gene'].dropna().astype(str)))
        if genes:
            result[group] = genes
    if universe is not None:
        result = canonicalize_gene_sets(result, universe)
    if not result:
        raise ValueError("No marker gene sets remained after group selection and universe overlap")
    return result


def _checked_sets(gene_sets, universe):
    if not gene_sets:
        raise ValueError("Provide non-empty gene sets; no synthetic pathways are generated")
    sets = canonicalize_gene_sets(gene_sets, universe)
    if not sets:
        raise ValueError("No gene sets overlap the input gene universe")
    return sets


def _finish(table, metadata, *, resolved_engine, missing=(), scratch=None):
    result = sort_results(table)
    result.attrs['run_info'] = {k: v for k, v in metadata.items() if k != 'ranking_by_group'}
    result.attrs['run_info'].update(resolved_engine=resolved_engine, missing_r_packages=list(missing))
    if 'ranking_by_group' in metadata:
        result.attrs['ranking_by_group'] = metadata['ranking_by_group']
    if scratch is not None:
        result.attrs['_cli_artifacts'] = {
            str(path.relative_to(scratch)): path.read_bytes()
            for path in Path(scratch).rglob('*') if path.is_file()
        }
    return result


def ora(ranking: pd.DataFrame, gene_sets, *, background=None, engine: str = "python",
        padj_cutoff: float = 0.05, log2fc_cutoff: float = 0.25, max_genes: int = 200,
        source: str = "custom", library_mode: str = "local", n_top: int = 18) -> pd.DataFrame:
    """Test over-representation with a local hypergeometric test or clusterProfiler.

    ``ranking`` accepts marker/DE columns and optional group (default all).
    ``background=None`` uses every ranked gene; pass all tested genes to make
    the universe explicit. Positive genes passing adjusted p-value <= 0.05
    and log2FC >= 0.25 are kept, up to 200 per group, by default. Score-only
    rankings keep positive scores. ``engine`` is python (default), r or auto
    (R when available). ``source`` and ``library_mode`` label result rows;
    ``n_top`` controls R's optional plots. Return a sorted enrichment table;
    :func:`run_info` returns warnings and the resolved engine.
    """
    frame = normalize_ranking_table(ranking)
    universe = list(background) if background is not None else frame['gene'].dropna().astype(str).unique().tolist()
    sets = _checked_sets(gene_sets, universe)
    resolved, missing = _resolve_engine(engine)
    if resolved == 'python':
        table, meta = run_ora(frame, source=source, library_mode=library_mode, gene_sets=sets,
            background_genes=universe, ora_padj_cutoff=padj_cutoff,
            ora_log2fc_cutoff=log2fc_cutoff, ora_max_genes=max_genes)
        return _finish(table, meta, resolved_engine=resolved, missing=missing)
    with tempfile.TemporaryDirectory(prefix='omicsclaw_ora_') as name:
        scratch = Path(name)
        gmt = write_gene_sets_gmt(sets, scratch / 'gene_sets.gmt')
        table, meta = _run_clusterprofiler_engine(method='ora', ranking_df=frame,
            background_genes=universe, gene_sets_path=gmt, output_dir=scratch, top_terms=n_top,
            ora_padj_cutoff=padj_cutoff, ora_log2fc_cutoff=log2fc_cutoff, ora_max_genes=max_genes,
            gsea_ranking_metric='auto', gsea_min_size=5, gsea_max_size=500, gsea_permutation_num=100, gsea_seed=123)
        return _finish(table, meta, resolved_engine=resolved, scratch=scratch)


def gsea(ranking: pd.DataFrame, gene_sets, *, engine: str = "python", ranking_metric: str = "auto",
         min_size: int = 5, max_size: int = 500, permutation_num: int = 100,
         weight: float = 1.0, random_state: int = 123, source: str = "custom",
         library_mode: str = "local", n_top: int = 18, species: str = "human",
         gene_set_db: str | None = None) -> pd.DataFrame:
    """Run preranked GSEA and return sorted terms with NES, p-values and leading edges.

    ``engine`` is python (default), r (clusterProfiler GMT), auto, or gsea_r
    (the retained annotation-database R bridge; pass ``gene_sets=None`` and
    select GO_BP, KEGG or Reactome with ``gene_set_db``). Python uses gseapy
    when available and reports its existing local rank-based fallback.
    ``ranking_metric='auto'`` chooses stat, scores or logfoldchanges.
    Defaults: gene-set sizes 5..500, 100 permutations, weight 1.0, seed 123.
    Permutation count and weight configure Python; the retained R bridge
    uses fgsea's multilevel defaults and exponent 1.
    ``source``/``library_mode`` label rows; ``n_top`` controls R plot selection;
    ``species`` selects human or mouse annotation for gsea_r. Seeds are passed
    to Python and R. No gene sets are fabricated when input or mapping fails.
    """
    frame = normalize_ranking_table(ranking)
    if engine == 'gsea_r':
        if gene_sets is not None:
            raise ValueError("gsea_r uses annotation databases; use engine='r' for explicit gene sets")
        with tempfile.TemporaryDirectory(prefix='omicsclaw_gsea_r_') as name:
            table, meta = _run_gsea_r(frame, Path(name), dict(species=species, gene_set_db=gene_set_db,
                gsea_min_size=min_size, gsea_max_size=max_size, gsea_seed=random_state))
            return _finish(table, meta, resolved_engine='r.gsea_r', scratch=Path(name))
    sets = _checked_sets(gene_sets, frame['gene'].dropna().astype(str).unique())
    resolved, missing = _resolve_engine(engine)
    if resolved == 'python':
        table, meta = run_gsea(frame, source=source, library_mode=library_mode, gene_sets=sets,
            ranking_metric=ranking_metric, gsea_min_size=min_size, gsea_max_size=max_size,
            gsea_permutation_num=permutation_num, gsea_weight=weight, gsea_seed=random_state)
        return _finish(table, meta, resolved_engine=resolved, missing=missing)
    with tempfile.TemporaryDirectory(prefix='omicsclaw_gsea_') as name:
        scratch = Path(name)
        gmt = write_gene_sets_gmt(sets, scratch / 'gene_sets.gmt')
        table, meta = _run_clusterprofiler_engine(method='gsea', ranking_df=frame,
            background_genes=frame['gene'].dropna().astype(str).unique().tolist(),
            gene_sets_path=gmt, output_dir=scratch, top_terms=n_top,
            ora_padj_cutoff=.05, ora_log2fc_cutoff=.25, ora_max_genes=200,
            gsea_ranking_metric=ranking_metric, gsea_min_size=min_size, gsea_max_size=max_size,
            gsea_permutation_num=permutation_num, gsea_seed=random_state)
        return _finish(table, meta, resolved_engine=resolved, scratch=scratch)


def gsva(adata, gene_sets, *, groupby: str, species: str = "human", gene_set_db: str = "GO_BP",
         method: str = "gsva", min_size: int = 5, max_size: int = 500) -> pd.DataFrame:
    """Score mean log-normalised expression per group with R GSVA, returning a long table.

    Supply a term-to-genes mapping, or None for the retained GO_BP/KEGG R
    annotation bridge selected by ``gene_set_db`` and human/mouse ``species``.
    ``method`` is gsva (default), ssgsea or zscore; gene-set size defaults are
    5..500. R runs serially in a temporary directory. Missing annotation or
    gene sets raises an error rather than producing synthetic pathways.
    """
    if groupby not in adata.obs:
        raise ValueError(f"Group column {groupby!r} is absent from adata.obs")
    if method not in {'gsva', 'ssgsea', 'zscore'}:
        raise ValueError(f"Unknown GSVA method: {method}")
    with tempfile.TemporaryDirectory(prefix='omicsclaw_gsva_') as name:
        scratch = Path(name)
        params = dict(species=species, gene_set_db=gene_set_db, gsva_method=method,
                      gsea_min_size=min_size, gsea_max_size=max_size)
        if gene_sets is not None:
            sets = _checked_sets(gene_sets, adata.var_names)
            params['gene_sets_path'] = str(write_gene_sets_gmt(sets, scratch / 'gene_sets.gmt'))
        table, meta = _run_gsva_r(adata, groupby, scratch, params)
        return _finish(table, meta, resolved_engine='r.gsva_r', scratch=scratch)


def run_info(results: pd.DataFrame, *, keep: bool = True) -> dict:
    """Return a JSON-serialisable diagnostics summary, excluding rankings and R artifacts."""
    info = results.attrs.get('run_info', {}) if keep else results.attrs.pop('run_info', {})
    return json.loads(json.dumps(info))


def top_terms(results: pd.DataFrame, *, n_top: int = 18, per_group: int = 3) -> pd.DataFrame:
    """Select up to n_top terms, first reserving per_group rows for each group."""
    return select_top_terms(results, top_terms=n_top, per_group=per_group)


def top_terms_figure(results: pd.DataFrame, *, n_top: int = 18):
    """Return a horizontal score bar Figure; the caller saves and closes it."""
    import matplotlib.pyplot as plt

    table = top_terms(results, n_top=n_top)
    fig, ax = plt.subplots(figsize=(7, max(3, .3 * len(table))))
    if not table.empty:
        ax.barh(table['group'].astype(str) + ': ' + table['term'].astype(str), table['score'])
        ax.invert_yaxis()
    ax.set_xlabel('Enrichment score')
    fig.tight_layout()
    return fig


def _r_stack_available() -> tuple[bool, list[str]]:
    required = ["clusterProfiler", "enrichplot"]
    try:
        validate_r_environment(required_r_packages=required)
        return True, []
    except Exception:
        runner = RScriptRunner(scripts_dir=R_SCRIPTS_DIR, timeout=30, verbose=False)
        return False, runner.get_missing_packages(required) if runner.check_r_available() else required


def _resolve_engine(requested: str) -> tuple[str, list[str]]:
    if requested not in {"python", "auto", "r"}:
        raise ValueError(f"Unknown enrichment engine: {requested}")
    if requested == "python":
        return "python", []
    available, missing = _r_stack_available()
    if requested == "r":
        if not available:
            raise ImportError(
                "R enrichment needs clusterProfiler and enrichplot; ask install_skill_deps for sc-enrichment.\n"
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

    try:
        res = pd.read_csv(result_path)
    except pd.errors.EmptyDataError:
        res = pd.DataFrame()
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


def _run_gsea_r(ranking_df: pd.DataFrame, output_dir: Path, params: dict) -> tuple[pd.DataFrame, dict]:
    """Run clusterProfiler GSEA via R bridge. Returns (enrichment_df, summary_dict)."""

    r_script = R_SCRIPTS_PROJECT_DIR / "sc_gsea_r.R"
    if not r_script.exists():
        raise FileNotFoundError(f"R script not found: {r_script}")

    # Export ranking table for R
    r_work_dir = output_dir / "r_work"
    r_work_dir.mkdir(parents=True, exist_ok=True)
    de_csv = r_work_dir / "de_for_gsea_r.csv"

    # Prepare DE table with columns R script expects
    export_df = ranking_df.copy()
    # Ensure we have the right column names
    col_map = {}
    if "names" in export_df.columns and "gene" not in export_df.columns:
        col_map["names"] = "gene"
    if "logfoldchanges" in export_df.columns and "avg_log2FC" not in export_df.columns:
        col_map["logfoldchanges"] = "avg_log2FC"
    elif "scores" in export_df.columns and "avg_log2FC" not in export_df.columns:
        col_map["scores"] = "avg_log2FC"
    elif "stat" in export_df.columns and "avg_log2FC" not in export_df.columns:
        col_map["stat"] = "avg_log2FC"
    if col_map:
        export_df = export_df.rename(columns=col_map)
    export_df.to_csv(de_csv, index=False)

    species_map = {"human": "Homo_sapiens", "mouse": "Mus_musculus"}
    species = species_map.get(params.get("species", "human"), params.get("species", "Homo_sapiens"))
    db = params.get("gene_set_db", "GO_BP") or "GO_BP"
    # Map common db names
    db_map = {"go_bp": "GO_BP", "kegg": "KEGG", "reactome": "Reactome"}
    db = db_map.get(db.lower(), db)
    score_type = params.get("score_type", "std")

    runner = RScriptRunner(timeout=600)
    result_csv = r_work_dir / "gsea_r_results.csv"
    runner.run_script(
        r_script,
        args=[str(de_csv), str(r_work_dir), species, db, score_type,
              str(params.get("gsea_min_size", 10)),
              str(params.get("gsea_max_size", 500)),
              str(params.get("gsea_seed", 123))],
        expected_outputs=["gsea_r_results.csv"],
        output_dir=r_work_dir,
    )

    enrichment_df = pd.read_csv(result_csv)

    # Standardize columns for the common enrichment pipeline
    standardized = pd.DataFrame()
    if not enrichment_df.empty:
        standardized = enrichment_df.copy()
        standardized = standardized.rename(columns={
            "Description": "term",
            "ID": "gene_set",
            "NES": "nes",
            "pvalue": "pvalue",
            "p.adjust": "pvalue_adj",
            "core_enrichment": "leading_edge",
            "Group": "group",
            "Database": "database",
        })
        standardized["term"] = standardized.get("term", standardized.get("gene_set", "")).astype(str)
        standardized["gene_set"] = standardized.get("gene_set", standardized.get("term", "")).astype(str)
        standardized["score"] = pd.to_numeric(standardized.get("nes"), errors="coerce")
        standardized["source"] = "clusterProfiler_gsea_r"
        standardized["library_mode"] = "r_gsea_r"
        standardized["engine"] = "r.gsea_r"
        standardized["method_used"] = "gsea_r"

    standardized.attrs["_legacy_uns"] = {"gsea_r_results": enrichment_df.to_dict(orient="list")}
    return standardized, {
        "method": "gsea_r",
        "r_success": True,
        "n_terms": len(standardized),
        "species": species,
        "db": db,
        "warnings": [],
    }


def _export_group_expr_for_gsva(adata, groupby: str, output_dir: Path) -> Path:
    """Average expression per group, exported as CSV rows=groups, cols=genes."""
    groups = adata.obs[groupby].astype(str).unique().tolist()
    X = adata.X
    if hasattr(X, "toarray"):
        X = X.toarray()
    rows = {}
    for grp in groups:
        mask = adata.obs[groupby].astype(str) == grp
        rows[grp] = np.asarray(X[mask]).mean(axis=0)
    group_expr_df = pd.DataFrame(rows, index=adata.var_names).T  # groups x genes
    csv_path = output_dir / "group_expr_for_gsva.csv"
    group_expr_df.to_csv(csv_path)
    return csv_path


def _run_gsva_r(adata, groupby: str, output_dir: Path, params: dict) -> tuple[pd.DataFrame, dict]:
    """Run GSVA group-level pathway scoring via R bridge. Returns (scores_df_long, summary_dict)."""

    r_script = R_SCRIPTS_PROJECT_DIR / "sc_gsva_r.R"
    if not r_script.exists():
        raise FileNotFoundError(f"R script not found: {r_script}")

    r_work_dir = output_dir / "r_work_gsva"
    r_work_dir.mkdir(parents=True, exist_ok=True)

    group_expr_csv = _export_group_expr_for_gsva(adata, groupby, r_work_dir)

    species_map = {"human": "Homo_sapiens", "mouse": "Mus_musculus"}
    species = species_map.get(params.get("species", "human"), params.get("species", "Homo_sapiens"))
    db = params.get("gene_set_db", "GO_BP") or "GO_BP"
    db_map = {"go_bp": "GO_BP", "kegg": "KEGG", "reactome": "Reactome"}
    db = db_map.get(db.lower(), db)
    gsva_method = params.get("gsva_method", "gsva")

    runner = RScriptRunner(timeout=1800)  # GSVA can be slow on large gene sets
    result_csv = r_work_dir / "gsva_r_scores.csv"
    runner.run_script(
        r_script,
        args=[str(group_expr_csv), str(r_work_dir), species, db, gsva_method, groupby,
              str(params.get("gsea_min_size", 5)),
              str(params.get("gsea_max_size", 500)),
              str(params.get("gene_sets_path", ""))],
        expected_outputs=["gsva_r_scores.csv"],
        output_dir=r_work_dir,
    )

    scores_df = pd.read_csv(result_csv)

    if not scores_df.empty:
        adata.uns["gsva_r_scores"] = scores_df.to_dict(orient="list")

    return scores_df, {
        "method": "gsva_r",
        "r_success": True,
        "n_pathways": int(scores_df["pathway"].nunique()) if not scores_df.empty else 0,
        "n_groups": int(scores_df["group"].nunique()) if not scores_df.empty else 0,
        "species": species,
        "db": db,
        "gsva_method": gsva_method,
        "warnings": [],
    }


def group_summary(enrich_df: pd.DataFrame, *, fdr_threshold: float = 0.05) -> pd.DataFrame:
    """Summarise term counts, FDR-significant terms and the top term per group."""
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
