"""Statistical enrichment helpers for single-cell gene list and ranked-list analysis."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd
import scanpy as sc
from scipy import stats as scipy_stats

from .dependency_manager import get as get_dependency

logger = logging.getLogger(__name__)

GENE_SET_DB_ALIASES = {
    "hallmark": {"human": "MSigDB_Hallmark_2020", "mouse": "MSigDB_Hallmark_2020"},
    "kegg": {"human": "KEGG_2021_Human", "mouse": "KEGG_2021_Mouse"},
    "reactome": {"human": "Reactome_2022", "mouse": "Reactome_2022"},
    "go_bp": {"human": "GO_Biological_Process_2023", "mouse": "GO_Biological_Process_2023"},
    "go_cc": {"human": "GO_Cellular_Component_2023", "mouse": "GO_Cellular_Component_2023"},
    "go_mf": {"human": "GO_Molecular_Function_2023", "mouse": "GO_Molecular_Function_2023"},
}

RANKING_METRIC_PREFERENCE = ("stat", "scores", "logfoldchanges", "log2FoldChange")


def _human_to_mouse_symbol(gene: str) -> str:
    if not gene:
        return gene
    return gene[0].upper() + gene[1:].lower()


def build_demo_gene_sets(species: str = "human") -> dict[str, list[str]]:
    """Return a compact PBMC-style demo gene-set library."""
    human_sets = {
        "T_cell_signature": ["LTB", "IL32", "MALAT1", "LTB", "LDHB", "LTB", "MALAT1", "IL7R", "LTB", "MALAT1"],
        "Cytotoxic_NK_signature": ["NKG7", "GNLY", "PRF1", "GZMB", "CTSW", "CCL5", "KLRD1", "TRAC", "HCST", "TYROBP"],
        "B_cell_signature": ["MS4A1", "CD79A", "CD79B", "CD74", "HLA-DRA", "HLA-DPB1", "HLA-DQA1", "CD79A", "MS4A1", "CD74"],
        "Monocyte_inflammatory": ["S100A8", "S100A9", "FCN1", "LYZ", "TYROBP", "LST1", "FCER1G", "LGALS3", "CTSS", "SAT1"],
        "Antigen_presentation": ["HLA-DPA1", "HLA-DPB1", "HLA-DRA", "HLA-DRB1", "CD74", "CST3", "FCER1A", "HLA-DQA1", "HLA-DQB1", "CYBA"],
        "Platelet_signature": ["PPBP", "PF4", "SDPR", "GNG11", "NRGN", "GP9", "TUBB1", "ITM2B", "SPARC", "CLU"],
    }
    if species == "mouse":
        return {
            key: [_human_to_mouse_symbol(gene) for gene in genes]
            for key, genes in human_sets.items()
        }
    return human_sets


def read_gene_sets(path: str | Path) -> dict[str, list[str]]:
    """Load gene sets from GMT or JSON."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Gene-set file not found: {file_path}")
    if file_path.suffix.lower() == ".json":
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON gene-set file must map term -> gene list.")
        return {
            str(term): [str(gene) for gene in genes if str(gene).strip()]
            for term, genes in payload.items()
            if isinstance(genes, (list, tuple))
        }

    gene_sets: dict[str, list[str]] = {}
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        parts = raw_line.rstrip("\n").split("\t")
        if len(parts) < 3:
            continue
        term = str(parts[0]).strip()
        members = [str(item).strip() for item in parts[2:] if str(item).strip()]
        if term and members:
            gene_sets[term] = members
    if not gene_sets:
        raise ValueError(f"No valid gene sets parsed from {file_path}")
    return gene_sets


def write_gene_sets_gmt(gene_sets: dict[str, list[str]], output_path: str | Path) -> Path:
    """Write gene sets to GMT."""
    output = Path(output_path)
    lines = ["\t".join([name, "omicsclaw"] + list(dict.fromkeys(genes))) for name, genes in gene_sets.items()]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def _resolve_gene_set_library_name(gene_set_db: str, species: str) -> str:
    normalized_db = str(gene_set_db).strip().lower()
    normalized_species = str(species).strip().lower()
    alias = GENE_SET_DB_ALIASES.get(normalized_db)
    if alias:
        return alias.get(normalized_species, alias.get("human", gene_set_db))
    return str(gene_set_db).strip()


def fetch_gene_sets_from_library(gene_set_db: str, *, species: str) -> tuple[dict[str, list[str]], str]:
    """Resolve gene sets through GSEApy's library downloader."""
    gp = get_dependency("gseapy")
    if gp is None:
        raise ImportError("gseapy is required for `--gene-set-db` but is not installed.")

    organism = "Human" if species.lower().startswith("human") else "Mouse"
    resolved = _resolve_gene_set_library_name(gene_set_db, species)
    try:
        gene_sets = gp.get_library(name=resolved, organism=organism)
    except TypeError:
        gene_sets = gp.get_library(resolved, organism=organism)
    if not gene_sets:
        raise RuntimeError(f"Resolved library `{resolved}` returned no gene sets.")
    return {
        str(name): [str(gene) for gene in genes if str(gene).strip()]
        for name, genes in gene_sets.items()
        if genes
    }, resolved


def canonicalize_gene_sets(gene_sets: dict[str, list[str]], universe: pd.Index | list[str]) -> dict[str, list[str]]:
    """Restrict gene sets to the observed gene universe."""
    universe_set = {str(gene) for gene in universe}
    out: dict[str, list[str]] = {}
    for term, genes in gene_sets.items():
        overlap = list(dict.fromkeys(str(gene) for gene in genes if str(gene) in universe_set))
        if overlap:
            out[str(term)] = overlap
    return out


def auto_rank_markers(
    adata,
    *,
    groupby: str,
    method: str = "wilcoxon",
) -> pd.DataFrame:
    """Compute full cluster-vs-rest rankings from normalized expression."""
    if groupby not in adata.obs.columns:
        raise ValueError(f"groupby column `{groupby}` not found in `adata.obs`.")
    key = f"rank_genes_groups__sc_enrichment__{method.replace('-', '_')}"
    sc.tl.rank_genes_groups(
        adata,
        groupby=groupby,
        method=method,
        corr_method="benjamini-hochberg",
        use_raw=False,
        n_genes=adata.n_vars,
        pts=True,
        key_added=key,
    )
    frames: list[pd.DataFrame] = []
    for group in sorted(adata.obs[groupby].dropna().astype(str).unique().tolist(), key=str):
        df = sc.get.rank_genes_groups_df(adata, group=group, key=key)
        if df.empty:
            continue
        df.insert(0, "group", str(group))
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    for column in ("scores", "logfoldchanges", "pvals", "pvals_adj"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    return out


def normalize_ranking_table(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize markers/DE tables to a shared single-cell enrichment schema."""
    out = df.copy()
    rename_map = {}
    if "names" in out.columns and "gene" not in out.columns:
        rename_map["names"] = "gene"
    if "cell_type" in out.columns and "group" not in out.columns:
        rename_map["cell_type"] = "group"
    if "log2FoldChange" in out.columns and "logfoldchanges" not in out.columns:
        rename_map["log2FoldChange"] = "logfoldchanges"
    if "padj" in out.columns and "pvals_adj" not in out.columns:
        rename_map["padj"] = "pvals_adj"
    if "pvalue" in out.columns and "pvals" not in out.columns:
        rename_map["pvalue"] = "pvals"
    out = out.rename(columns=rename_map)
    if "group" not in out.columns:
        out["group"] = "all"
    if "gene" not in out.columns:
        raise ValueError("Ranking table must contain a gene column (`gene` or `names`).")
    for column in ("scores", "logfoldchanges", "pvals", "pvals_adj", "stat"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    out["group"] = out["group"].astype(str)
    out["gene"] = out["gene"].astype(str)
    return out


def resolve_ranking_metric(ranking_df: pd.DataFrame, requested: str = "auto") -> str:
    """Choose the ranking metric for preranked GSEA."""
    if requested != "auto" and requested in ranking_df.columns and pd.to_numeric(ranking_df[requested], errors="coerce").notna().any():
        return requested
    for metric in RANKING_METRIC_PREFERENCE:
        if metric in ranking_df.columns and pd.to_numeric(ranking_df[metric], errors="coerce").notna().any():
            return metric
    raise ValueError("Could not resolve a usable ranking metric for GSEA.")


def _benjamini_hochberg(pvalues: np.ndarray) -> np.ndarray:
    pv = np.asarray(pvalues, dtype=float)
    n = len(pv)
    if n == 0:
        return pv
    order = np.argsort(pv)
    sorted_p = pv[order]
    adjusted = np.empty(n, dtype=float)
    adjusted[-1] = sorted_p[-1]
    for i in range(n - 2, -1, -1):
        rank = i + 1
        adjusted[i] = min(sorted_p[i] * n / rank, adjusted[i + 1])
    adjusted = np.clip(adjusted, 0.0, 1.0)
    result = np.empty(n, dtype=float)
    result[order] = adjusted
    return result


def _run_hypergeometric_ora(
    gene_list: list[str],
    gene_sets: dict[str, list[str]],
    *,
    background_size: int,
) -> pd.DataFrame:
    """Local ORA fallback using a hypergeometric test."""
    query = set(gene_list)
    n = len(query)
    if n == 0:
        return pd.DataFrame()

    records: list[dict[str, object]] = []
    for term, pathway_genes in gene_sets.items():
        pathway = set(pathway_genes)
        overlap_genes = sorted(query & pathway)
        k = len(overlap_genes)
        K = len(pathway)
        if k == 0:
            continue
        pval = float(scipy_stats.hypergeom.sf(k - 1, background_size, K, n))
        expected = max(n * (K / max(background_size, 1)), 1e-9)
        odds_ratio = float(k / expected) if expected > 0 else np.nan
        combined_score = float(-np.log10(max(pval, 1e-300)) * odds_ratio)
        records.append(
            {
                "Term": term,
                "Overlap": f"{k}/{K}",
                "P-value": pval,
                "Adjusted P-value": np.nan,
                "Odds Ratio": odds_ratio,
                "Combined Score": combined_score,
                "Genes": ";".join(overlap_genes),
            }
        )
    df = pd.DataFrame(records)
    if df.empty:
        return df
    df["Adjusted P-value"] = _benjamini_hochberg(df["P-value"].to_numpy())
    return df.sort_values("Adjusted P-value", ascending=True).reset_index(drop=True)


def _fallback_prerank_gsea(
    ranking: pd.Series,
    gene_sets: dict[str, list[str]],
    *,
    min_size: int,
    max_size: int,
    permutation_num: int,
    seed: int,
) -> pd.DataFrame:
    """Lightweight rank-based GSEA fallback via permutation of mean scores."""
    ranking = ranking.dropna()
    ranking = ranking[~ranking.index.duplicated(keep="first")]
    if ranking.empty:
        return pd.DataFrame()

    genes = ranking.index.to_numpy()
    scores = ranking.to_numpy(dtype=float)
    gene_to_position = {gene: idx for idx, gene in enumerate(genes)}
    rng = np.random.default_rng(seed)
    records: list[dict[str, object]] = []

    for term, members in gene_sets.items():
        positions = [gene_to_position[g] for g in members if g in gene_to_position]
        if not (min_size <= len(positions) <= max_size):
            continue
        observed = float(scores[positions].mean())
        null = np.array(
            [
                float(scores[rng.choice(len(scores), size=len(positions), replace=False)].mean())
                for _ in range(max(10, int(permutation_num)))
            ]
        )
        null_mean = float(null.mean())
        null_std = float(null.std()) if float(null.std()) > 0 else 1.0
        es = observed - null_mean
        nes = es / null_std
        pval = float((np.sum(np.abs(null - null_mean) >= abs(es)) + 1) / (len(null) + 1))
        lead_genes = [gene for gene in ranking.sort_values(ascending=False).index.tolist() if gene in set(members)][:15]
        records.append(
            {
                "Term": term,
                "ES": es,
                "NES": nes,
                "NOM p-val": pval,
                "FDR q-val": np.nan,
                "Lead_genes": ";".join(lead_genes),
            }
        )
    df = pd.DataFrame(records)
    if df.empty:
        return df
    df["FDR q-val"] = _benjamini_hochberg(df["NOM p-val"].to_numpy())
    return df.sort_values("FDR q-val", ascending=True).reset_index(drop=True)


def _standardize_ora_results(
    df: pd.DataFrame,
    *,
    group: str,
    source: str,
    library_mode: str,
    engine: str,
    n_input_genes: int,
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    out = df.copy().rename(
        columns={
            "Term": "gene_set",
            "P-value": "pvalue",
            "Adjusted P-value": "pvalue_adj",
            "Combined Score": "score",
            "Odds Ratio": "odds_ratio",
            "Overlap": "overlap",
            "Genes": "genes",
        }
    )
    out["group"] = str(group)
    out["term"] = out.get("gene_set", "")
    out["source"] = source
    out["library_mode"] = library_mode
    out["engine"] = engine
    out["method_used"] = "ora"
    out["n_input_genes"] = int(n_input_genes)
    out["gene_count"] = out["overlap"].astype(str).str.split("/").str[0].astype(float) if "overlap" in out.columns else np.nan
    for column in ("pvalue", "pvalue_adj", "score", "odds_ratio", "gene_count"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    desired = [
        "group", "term", "gene_set", "source", "library_mode", "engine", "method_used",
        "score", "odds_ratio", "gene_count", "overlap", "pvalue", "pvalue_adj", "genes", "n_input_genes",
    ]
    for column in desired:
        if column not in out.columns:
            out[column] = np.nan
    return out[desired]


def _standardize_gsea_results(
    df: pd.DataFrame,
    *,
    group: str,
    source: str,
    library_mode: str,
    engine: str,
    ranking_metric: str,
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    out = df.copy().rename(
        columns={
            "Term": "gene_set",
            "NES": "nes",
            "ES": "es",
            "NOM p-val": "pvalue",
            "FDR q-val": "pvalue_adj",
            "Lead_genes": "leading_edge",
        }
    )
    out["group"] = str(group)
    out["term"] = out.get("gene_set", "")
    out["source"] = source
    out["library_mode"] = library_mode
    out["engine"] = engine
    out["method_used"] = "gsea"
    out["ranking_metric"] = ranking_metric
    out["score"] = pd.to_numeric(out["nes"], errors="coerce") if "nes" in out.columns else np.nan
    for column in ("pvalue", "pvalue_adj", "nes", "es", "score"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    desired = [
        "group", "term", "gene_set", "source", "library_mode", "engine", "method_used",
        "ranking_metric", "score", "nes", "es", "pvalue", "pvalue_adj", "leading_edge",
    ]
    for column in desired:
        if column not in out.columns:
            out[column] = np.nan
    return out[desired]


def run_ora(
    ranking_df: pd.DataFrame,
    *,
    source: str,
    library_mode: str,
    gene_sets: dict[str, list[str]],
    background_genes: list[str],
    ora_padj_cutoff: float,
    ora_log2fc_cutoff: float,
    ora_max_genes: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Run ORA per group on positive ranked genes."""
    all_records: list[pd.DataFrame] = []
    warnings: list[str] = []
    input_gene_counts: dict[str, int] = {}

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
        genes = filtered["gene"].astype(str).tolist()
        input_gene_counts[str(group)] = len(genes)
        if not genes:
            warnings.append(
                f"Group `{group}` had no positive genes after ORA filtering (`ora_padj_cutoff={ora_padj_cutoff}`, `ora_log2fc_cutoff={ora_log2fc_cutoff}`)."
            )
            continue

        res = _run_hypergeometric_ora(
            genes,
            gene_sets,
            background_size=max(len(background_genes), len(set(background_genes))),
        )
        engine = "hypergeometric_local"

        std = _standardize_ora_results(
            res,
            group=str(group),
            source=source,
            library_mode=library_mode,
            engine=engine,
            n_input_genes=len(genes),
        )
        all_records.append(std)

    enrich_df = pd.concat(all_records, ignore_index=True) if all_records else pd.DataFrame()
    return enrich_df, {"warnings": warnings, "n_input_genes_by_group": input_gene_counts}


def run_gsea(
    ranking_df: pd.DataFrame,
    *,
    source: str,
    library_mode: str,
    gene_sets: dict[str, list[str]],
    ranking_metric: str,
    gsea_min_size: int,
    gsea_max_size: int,
    gsea_permutation_num: int,
    gsea_weight: float,
    gsea_seed: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Run preranked GSEA per group."""
    gp = get_dependency("gseapy")
    all_records: list[pd.DataFrame] = []
    warnings: list[str] = []
    ranking_by_group: dict[str, pd.Series] = {}

    for group, group_df in ranking_df.groupby("group", sort=False):
        metric = resolve_ranking_metric(group_df, ranking_metric)
        ranked = (
            group_df[["gene", metric]]
            .dropna()
            .drop_duplicates(subset=["gene"], keep="first")
            .set_index("gene")[metric]
            .sort_values(ascending=False)
        )
        ranking_by_group[str(group)] = ranked
        if len(ranked) < 10:
            warnings.append(f"Group `{group}` had fewer than 10 ranked genes after filtering; skipping GSEA.")
            continue

        engine = "gseapy.prerank"
        try:
            if gp is None:
                raise ImportError("gseapy not installed")
            pre = gp.prerank(
                rnk=ranked,
                gene_sets=gene_sets,
                min_size=int(gsea_min_size),
                max_size=int(gsea_max_size),
                permutation_num=int(gsea_permutation_num),
                weight=float(gsea_weight),
                outdir=None,
                seed=int(gsea_seed),
                verbose=False,
            )
            if hasattr(pre, "res2d") and isinstance(pre.res2d, pd.DataFrame):
                res = pre.res2d.copy()
            else:
                raise RuntimeError("gseapy prerank returned no tabular result")
            if res.empty:
                raise RuntimeError("gseapy prerank returned an empty GSEA result table")
        except Exception as exc:
            warnings.append(f"Group `{group}` GSEA fell back to a local rank-based method: {exc}")
            res = _fallback_prerank_gsea(
                ranked,
                gene_sets,
                min_size=int(gsea_min_size),
                max_size=int(gsea_max_size),
                permutation_num=int(gsea_permutation_num),
                seed=int(gsea_seed),
            )
            engine = "rank_based_fallback"

        std = _standardize_gsea_results(
            res,
            group=str(group),
            source=source,
            library_mode=library_mode,
            engine=engine,
            ranking_metric=metric,
        )
        all_records.append(std)

    enrich_df = pd.concat(all_records, ignore_index=True) if all_records else pd.DataFrame()
    return enrich_df, {"warnings": warnings, "ranking_by_group": ranking_by_group}


def sort_results(df: pd.DataFrame) -> pd.DataFrame:
    """Sort enrichment results by significance or score."""
    if df.empty:
        return df
    out = df.copy()
    if "pvalue_adj" in out.columns and pd.to_numeric(out["pvalue_adj"], errors="coerce").notna().any():
        return out.sort_values("pvalue_adj", ascending=True, na_position="last", kind="mergesort")
    if "nes" in out.columns and pd.to_numeric(out["nes"], errors="coerce").notna().any():
        return out.sort_values("nes", key=lambda s: pd.to_numeric(s, errors="coerce").abs(), ascending=False, na_position="last", kind="mergesort")
    if "score" in out.columns and pd.to_numeric(out["score"], errors="coerce").notna().any():
        return out.sort_values("score", key=lambda s: pd.to_numeric(s, errors="coerce").abs(), ascending=False, na_position="last", kind="mergesort")
    return out


def select_top_terms(df: pd.DataFrame, *, top_terms: int, per_group: int = 3) -> pd.DataFrame:
    """Select a compact set of top terms without letting one group dominate."""
    if df.empty:
        return df
    ordered = sort_results(df)
    groups = ordered["group"].astype(str).dropna().unique().tolist() if "group" in ordered.columns else []
    rows: list[pd.DataFrame] = []
    used: set[tuple[str, str]] = set()
    for group in groups:
        group_df = ordered[ordered["group"].astype(str) == group].head(per_group)
        if not group_df.empty:
            rows.append(group_df)
            used.update((str(group), str(term)) for term in group_df["term"].astype(str))
    combined = pd.concat(rows, ignore_index=True) if rows else ordered.head(top_terms)
    if len(combined) < top_terms:
        remainder = ordered[
            ~ordered.apply(lambda row: (str(row.get("group", "")), str(row.get("term", ""))) in used, axis=1)
        ].head(max(top_terms - len(combined), 0))
        combined = pd.concat([combined, remainder], ignore_index=True)
    return combined.head(top_terms).reset_index(drop=True)


def sanitize_term_slug(text: str) -> str:
    """Convert a term or group into a filename-safe slug."""
    return re.sub(r"[^A-Za-z0-9_]+", "_", str(text)).strip("_")[:80]
