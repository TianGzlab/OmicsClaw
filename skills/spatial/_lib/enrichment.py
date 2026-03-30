"""Spatial pathway and gene-set enrichment utilities.

This module separates three enrichment modes:

- `enrichr`: ORA-style enrichment on positive cluster markers.
- `gsea`: preranked enrichment on full per-group marker rankings.
- `ssgsea`: single-sample enrichment on group-level mean expression profiles.

The wrapper prefers local execution:
- custom gene-set files and built-in OmicsClaw signature libraries work offline
- external Enrichr/MSigDB/GO libraries are attempted through GSEApy only when
  requested, with explicit fallback warnings if the remote library cannot be
  resolved
"""

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

SUPPORTED_METHODS = ("enrichr", "gsea", "ssgsea")
VALID_DE_METHODS = ("wilcoxon", "t-test")
VALID_DE_CORR_METHODS = ("benjamini-hochberg", "bonferroni")
VALID_SPECIES = ("human", "mouse")
VALID_RANKING_METRICS = ("auto", "scores", "logfoldchanges")
VALID_SSGSEA_SAMPLE_NORM_METHODS = ("rank", "log", "log_rank", "custom", "none")
VALID_SSGSEA_CORREL_NORM_TYPES = ("rank", "symrank", "zscore", "none")

_ONLINE_GENESET_LIBRARY_CANDIDATES: dict[str, tuple[str, ...]] = {
    "GO_Biological_Process": ("GO_Biological_Process_2025", "GO_Biological_Process_2023"),
    "GO_Molecular_Function": ("GO_Molecular_Function_2025", "GO_Molecular_Function_2023"),
    "GO_Cellular_Component": ("GO_Cellular_Component_2025", "GO_Cellular_Component_2023"),
    "KEGG_Pathways": ("KEGG_2021_Human",),
    "Reactome_Pathways": ("Reactome_Pathways_2024", "Reactome_2022"),
    "MSigDB_Hallmark": ("MSigDB_Hallmark_2020",),
    "MSigDB_Oncogenic": ("MSigDB_Oncogenic_Signatures",),
    "MSigDB_Immunologic": ("MSigDB_Immunologic_Signatures",),
}

METHOD_PARAM_DEFAULTS = {
    "common": {
        "groupby": "leiden",
        "source": "omicsclaw_core",
        "species": "human",
        "fdr_threshold": 0.05,
        "n_top_terms": 20,
        "de_method": "wilcoxon",
        "de_corr_method": "benjamini-hochberg",
    },
    "enrichr": {
        "enrichr_padj_cutoff": 0.05,
        "enrichr_log2fc_cutoff": 1.0,
        "enrichr_max_genes": 200,
    },
    "gsea": {
        "gsea_ranking_metric": "auto",
        "gsea_min_size": 15,
        "gsea_max_size": 500,
        "gsea_permutation_num": 100,
        "gsea_weight": 1.0,
        "gsea_ascending": False,
        "gsea_threads": 1,
        "gsea_seed": 123,
    },
    "ssgsea": {
        "ssgsea_sample_norm_method": "rank",
        "ssgsea_correl_norm_type": "rank",
        "ssgsea_min_size": 15,
        "ssgsea_max_size": 500,
        "ssgsea_weight": 0.25,
        "ssgsea_ascending": False,
        "ssgsea_threads": 1,
        "ssgsea_seed": 123,
    },
}


def _sanitize_name(text: str) -> str:
    """Convert a term name into a compact filesystem / column-safe slug."""
    return re.sub(r"[^A-Za-z0-9_]+", "_", str(text)).strip("_")[:80]


def _ensure_obs_string(adata, key: str) -> pd.Series:
    """Normalize a grouping column to string labels."""
    adata.obs[key] = adata.obs[key].astype(str)
    return adata.obs[key]


def _warn_if_scanpy_input_looks_like_counts(adata) -> None:
    """Warn if the marker-ranking input appears count-like rather than log-scale."""
    X = adata.X
    if hasattr(X, "toarray"):
        X = X.toarray()
    X = np.asarray(X)
    if X.size == 0:
        return
    flat = np.ravel(X)[: min(1000, X.size)]
    looks_integer = np.issubdtype(flat.dtype, np.integer) or np.allclose(flat, np.round(flat))
    if looks_integer and float(np.nanmax(flat)) > 50:
        logger.warning(
            "adata.X appears count-like; enrichment marker ranking assumes log-normalized expression."
        )


def _human_to_mouse_symbol(gene: str) -> str:
    """Naive but effective human-to-mouse casing for common alphanumeric symbols."""
    if not gene:
        return gene
    return gene[0].upper() + gene[1:].lower()


def _build_demo_gene_sets(var_names: pd.Index | list[str]) -> dict[str, list[str]]:
    """Create deterministic local demo pathways matching the synthetic demo genes."""
    genes = [str(g) for g in var_names]
    gene_set = set(genes)

    def _range(start: int, end: int) -> list[str]:
        candidates = [f"Gene_{i:03d}" for i in range(start, end)]
        return [g for g in candidates if g in gene_set]

    return {
        "Demo_Cluster0_Identity": _range(0, 10),
        "Demo_Cluster1_Identity": _range(10, 20),
        "Demo_Cluster2_Identity": _range(20, 30),
        "Demo_Stress_Response": _range(30, 40),
        "Demo_ECM_Remodeling": _range(40, 50),
        "Demo_Metabolic_Shift": _range(50, 60),
    }


def _build_core_gene_sets(species: str) -> dict[str, list[str]]:
    """Return a compact local gene-set library for offline enrichment fallback."""
    human_sets = {
        "OmicsClaw_Cell_Cycle": [
            "MKI67", "TOP2A", "CDK1", "CCNB1", "CCNB2", "PCNA", "TYMS", "BIRC5",
            "CENPF", "UBE2C", "MCM2", "MCM3", "AURKA", "AURKB", "CDC20",
        ],
        "OmicsClaw_Interferon_Response": [
            "IFIT1", "IFIT2", "IFIT3", "ISG15", "MX1", "MX2", "OAS1", "OAS2",
            "OAS3", "RSAD2", "STAT1", "IRF7", "CXCL10", "IFI6", "IFI44",
        ],
        "OmicsClaw_Hypoxia_Glycolysis": [
            "HIF1A", "VEGFA", "CA9", "EGLN3", "SLC2A1", "LDHA", "PDK1", "PGK1",
            "ALDOA", "ENO1", "BNIP3", "HK2", "PFKFB3",
        ],
        "OmicsClaw_EMT_ECM": [
            "VIM", "FN1", "COL1A1", "COL1A2", "TAGLN", "ACTA2", "SNAI1", "SNAI2",
            "ZEB1", "ITGA5", "MMP2", "SPARC", "COL3A1", "POSTN",
        ],
        "OmicsClaw_Angiogenesis_Endothelium": [
            "KDR", "FLT1", "PECAM1", "VWF", "EMCN", "ESAM", "ENG", "ANGPT2",
            "PGF", "KLF2", "CD34", "COL4A1", "COL4A2",
        ],
        "OmicsClaw_Inflammatory_NFkB": [
            "IL1B", "TNF", "NFKBIA", "CXCL8", "CXCL2", "CXCL3", "CCL2", "CCL3",
            "CCL4", "PTGS2", "ICAM1", "JUN", "FOS", "RELB",
        ],
        "OmicsClaw_Oxidative_Phosphorylation": [
            "NDUFA1", "NDUFB8", "NDUFS2", "UQCRC1", "UQCRC2", "COX4I1", "COX5A",
            "ATP5F1A", "ATP5F1B", "SDHA", "SDHB", "CYC1",
        ],
        "OmicsClaw_ER_Stress_UPR": [
            "ATF4", "DDIT3", "HSPA5", "XBP1", "HERPUD1", "DNAJB9", "PPP1R15A",
            "ASNS", "PDIA4", "CALR",
        ],
    }

    if species == "mouse":
        return {
            key: [_human_to_mouse_symbol(gene) for gene in genes]
            for key, genes in human_sets.items()
        }
    return human_sets


def _load_gene_set_file(path: str | Path) -> dict[str, list[str]]:
    """Load a local gene-set file from GMT or JSON."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Gene-set file not found: {file_path}")

    suffix = file_path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(file_path.read_text())
        if not isinstance(payload, dict):
            raise ValueError("JSON gene-set file must be a mapping: term -> gene list")
        return {
            str(term): [str(g) for g in genes if str(g)]
            for term, genes in payload.items()
            if isinstance(genes, (list, tuple))
        }

    if suffix == ".gmt":
        gene_sets: dict[str, list[str]] = {}
        with file_path.open() as handle:
            for line in handle:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 3:
                    continue
                term = parts[0]
                genes = [str(g) for g in parts[2:] if str(g)]
                if genes:
                    gene_sets[term] = genes
        return gene_sets

    raise ValueError("Unsupported gene-set file format. Use .json or .gmt")


def _looks_like_demo_genes(var_names: pd.Index | list[str]) -> bool:
    """Return True when the current dataset matches the synthetic demo gene naming."""
    genes = [str(g) for g in list(var_names)[: min(30, len(var_names))]]
    if not genes:
        return False
    return sum(bool(re.fullmatch(r"Gene_\d{3}", gene)) for gene in genes) >= max(5, len(genes) // 2)


def _resolve_gene_sets(
    *,
    source: str,
    species: str,
    gene_set: str | None,
    gene_set_file: str | None,
    var_names: pd.Index,
) -> tuple[dict[str, list[str]], dict[str, object]]:
    """Resolve the effective gene-set library and return metadata describing it."""
    requested_source = str(gene_set or source)
    warnings: list[str] = []

    if gene_set_file:
        gene_sets = _load_gene_set_file(gene_set_file)
        return gene_sets, {
            "requested_source": requested_source,
            "resolved_source": str(Path(gene_set_file).name),
            "library_mode": "local_file",
            "warnings": warnings,
        }

    if requested_source in {"omicsclaw_core", "builtin", "omicsclaw_builtin"}:
        gene_sets = (
            _build_demo_gene_sets(var_names)
            if _looks_like_demo_genes(var_names)
            else _build_core_gene_sets(species)
        )
        mode = "builtin_demo" if _looks_like_demo_genes(var_names) else "builtin_core"
        return gene_sets, {
            "requested_source": requested_source,
            "resolved_source": requested_source,
            "library_mode": mode,
            "warnings": warnings,
        }

    if requested_source == "omicsclaw_demo":
        gene_sets = _build_demo_gene_sets(var_names)
        return gene_sets, {
            "requested_source": requested_source,
            "resolved_source": requested_source,
            "library_mode": "builtin_demo",
            "warnings": warnings,
        }

    gp = get_dependency("gseapy")
    if gp is not None:
        candidates = _ONLINE_GENESET_LIBRARY_CANDIDATES.get(requested_source, (requested_source,))
        last_error: Exception | None = None
        for candidate in candidates:
            try:
                library = gp.get_library(candidate, organism=species)
                return library, {
                    "requested_source": requested_source,
                    "resolved_source": candidate,
                    "library_mode": "remote_library",
                    "warnings": warnings,
                }
            except Exception as exc:
                last_error = exc
        warnings.append(
            f"Could not resolve remote library '{requested_source}' for species '{species}'. "
            f"Falling back to a local OmicsClaw signature library. Last error: {last_error}"
        )
    else:
        warnings.append(
            "gseapy is not installed, so remote gene-set libraries are unavailable. "
            "Falling back to a local OmicsClaw signature library."
        )

    gene_sets = (
        _build_demo_gene_sets(var_names)
        if _looks_like_demo_genes(var_names)
        else _build_core_gene_sets(species)
    )
    mode = "builtin_demo_fallback" if _looks_like_demo_genes(var_names) else "builtin_core_fallback"
    return gene_sets, {
        "requested_source": requested_source,
        "resolved_source": "omicsclaw_demo" if _looks_like_demo_genes(var_names) else "omicsclaw_core",
        "library_mode": mode,
        "warnings": warnings,
    }


def _canonicalize_gene_sets(
    gene_sets: dict[str, list[str]],
    *,
    universe: pd.Index,
) -> dict[str, list[str]]:
    """Restrict gene sets to the observed gene universe."""
    universe_set = {str(g) for g in universe}
    out: dict[str, list[str]] = {}
    for term, genes in gene_sets.items():
        overlap = [str(g) for g in genes if str(g) in universe_set]
        if overlap:
            out[str(term)] = overlap
    return out


def _benjamini_hochberg(pvalues: np.ndarray) -> np.ndarray:
    """Simple Benjamini-Hochberg correction."""
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
    """Run a local ORA fallback using the hypergeometric test."""
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
        odds_ratio = float((k / expected)) if expected > 0 else np.nan
        combined_score = float(-np.log10(max(pval, 1e-300)) * odds_ratio)
        records.append(
            {
                "Gene_set": "local_ora",
                "Term": term,
                "Overlap": f"{k}/{K}",
                "P-value": pval,
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
    """Run a lightweight rank-based GSEA fallback using mean-rank permutations."""
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

        lead_genes = [
            gene
            for gene in ranking.sort_values(ascending=False).index.tolist()
            if gene in set(members)
        ][: min(15, len(positions))]

        records.append(
            {
                "Name": "fallback_prerank",
                "Term": term,
                "ES": es,
                "NES": nes,
                "NOM p-val": pval,
                "Lead_genes": ";".join(lead_genes),
            }
        )

    df = pd.DataFrame(records)
    if df.empty:
        return df
    df["FDR q-val"] = _benjamini_hochberg(df["NOM p-val"].to_numpy())
    return df.sort_values("FDR q-val", ascending=True).reset_index(drop=True)


def _fallback_ssgsea_scores(
    expr_df: pd.DataFrame,
    gene_sets: dict[str, list[str]],
    *,
    sample_norm_method: str | None,
    correl_norm_type: str | None,
) -> pd.DataFrame:
    """Minimal deterministic ssGSEA-like fallback based on normalized mean scores."""
    data = expr_df.copy()

    if sample_norm_method == "rank":
        data = data.rank(axis=0, method="average", na_option="bottom")
        data = 10000 * data / data.shape[0]
    elif sample_norm_method == "log_rank":
        data = data.rank(axis=0, method="average", na_option="bottom")
        data = np.log(10000 * data / data.shape[0] + np.exp(1))
    elif sample_norm_method == "log":
        data[data < 1] = 1
        data = np.log(data + np.exp(1))
    elif sample_norm_method in {None, "custom"}:
        pass

    if correl_norm_type == "zscore":
        data = data.apply(
            lambda col: (col - col.mean()) / (col.std(ddof=0) if col.std(ddof=0) > 0 else 1.0),
            axis=0,
        )
    elif correl_norm_type == "symrank":
        centered = data.rank(axis=0, method="average", na_option="bottom")
        centered = centered - (centered.shape[0] + 1) / 2.0
        denom = np.maximum(np.abs(centered).max(axis=0), 1.0)
        data = centered.divide(denom, axis=1)

    records: list[dict[str, object]] = []
    for sample in data.columns:
        column = data[sample]
        background_mean = float(column.mean())
        background_std = float(column.std(ddof=0)) if float(column.std(ddof=0)) > 0 else 1.0
        for term, members in gene_sets.items():
            overlap = [gene for gene in members if gene in column.index]
            if not overlap:
                continue
            es = float(column.loc[overlap].mean())
            nes = (es - background_mean) / background_std
            records.append({"Name": sample, "Term": term, "ES": es, "NES": nes})
    return pd.DataFrame(records)


def _extract_ranked_markers(
    adata,
    *,
    groupby: str,
    de_method: str,
    de_corr_method: str,
) -> tuple[pd.DataFrame, str]:
    """Compute or refresh Scanpy rank_genes_groups and return a long dataframe."""
    if groupby not in adata.obs.columns:
        raise ValueError(f"groupby column '{groupby}' not found in adata.obs")

    _ensure_obs_string(adata, groupby)
    _warn_if_scanpy_input_looks_like_counts(adata)

    key = f"rank_genes_groups__enrichment__{de_method.replace('-', '_')}"
    sc.tl.rank_genes_groups(
        adata,
        groupby=groupby,
        method=de_method,
        corr_method=de_corr_method,
        use_raw=False,
        key_added=key,
        n_genes=adata.n_vars,
    )

    frames: list[pd.DataFrame] = []
    groups = sorted(adata.obs[groupby].dropna().astype(str).unique().tolist(), key=str)
    for group in groups:
        df = sc.get.rank_genes_groups_df(adata, group=group, key=key)
        if df.empty:
            continue
        df.insert(0, "group", str(group))
        for col in ("scores", "logfoldchanges", "pvals", "pvals_adj"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        frames.append(df)

    marker_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return marker_df, key


def _resolve_ranking_metric(marker_df: pd.DataFrame, requested: str) -> str:
    """Choose the ranking metric used for prerank GSEA."""
    if requested != "auto" and requested in marker_df.columns:
        return requested
    for candidate in ("scores", "logfoldchanges"):
        if candidate in marker_df.columns:
            return candidate
    raise ValueError("Could not resolve a ranking metric for GSEA from the marker table.")


def _sort_results(df: pd.DataFrame) -> pd.DataFrame:
    """Sort enrichment results using adjusted significance or score fallbacks."""
    if df.empty:
        return df
    out = df.copy()
    if "pvalue_adj" in out.columns and out["pvalue_adj"].notna().any():
        return out.sort_values(["pvalue_adj", "pvalue"], ascending=[True, True], na_position="last")
    if "nes" in out.columns and out["nes"].notna().any():
        return out.sort_values("nes", key=lambda s: s.abs(), ascending=False, na_position="last")
    if "score" in out.columns and out["score"].notna().any():
        return out.sort_values("score", key=lambda s: s.abs(), ascending=False, na_position="last")
    return out


def _standardize_enrichr_results(
    df: pd.DataFrame,
    *,
    group: str,
    source: str,
    library_mode: str,
    engine: str,
    n_input_genes: int,
) -> pd.DataFrame:
    """Normalize ORA results to the shared output contract."""
    if df.empty:
        return pd.DataFrame()

    out = df.copy()
    rename_map = {
        "Term": "gene_set",
        "P-value": "pvalue",
        "Adjusted P-value": "pvalue_adj",
        "Combined Score": "score",
        "Odds Ratio": "odds_ratio",
        "Overlap": "overlap",
        "Genes": "genes",
    }
    out = out.rename(columns={k: v for k, v in rename_map.items() if k in out.columns})
    out["group"] = str(group)
    out["term"] = out.get("gene_set", "")
    out["source"] = source
    out["library_mode"] = library_mode
    out["engine"] = engine
    out["method_used"] = "enrichr"
    out["n_input_genes"] = int(n_input_genes)
    out["gene_count"] = out["overlap"].astype(str).str.split("/").str[0].astype(float) if "overlap" in out.columns else np.nan
    for col in ("pvalue", "pvalue_adj", "score", "odds_ratio", "gene_count"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    cols = [
        "group", "term", "gene_set", "source", "library_mode", "engine", "method_used",
        "score", "odds_ratio", "gene_count", "overlap", "pvalue", "pvalue_adj",
        "genes", "n_input_genes",
    ]
    for col in cols:
        if col not in out.columns:
            out[col] = np.nan
    return out[cols]


def _standardize_gsea_results(
    df: pd.DataFrame,
    *,
    group: str,
    source: str,
    library_mode: str,
    engine: str,
    ranking_metric: str,
) -> pd.DataFrame:
    """Normalize prerank GSEA results to the shared output contract."""
    if df.empty:
        return pd.DataFrame()

    out = df.copy()
    rename_map = {
        "Term": "gene_set",
        "NES": "nes",
        "ES": "es",
        "NOM p-val": "pvalue",
        "FDR q-val": "pvalue_adj",
        "Lead_genes": "leading_edge",
    }
    out = out.rename(columns={k: v for k, v in rename_map.items() if k in out.columns})
    out["group"] = str(group)
    out["term"] = out.get("gene_set", "")
    out["source"] = source
    out["library_mode"] = library_mode
    out["engine"] = engine
    out["method_used"] = "gsea"
    out["ranking_metric"] = ranking_metric
    out["score"] = pd.to_numeric(out["nes"], errors="coerce") if "nes" in out.columns else np.nan
    for col in ("pvalue", "pvalue_adj", "nes", "es", "score"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    cols = [
        "group", "term", "gene_set", "source", "library_mode", "engine", "method_used",
        "ranking_metric", "score", "nes", "es", "pvalue", "pvalue_adj", "leading_edge",
    ]
    for col in cols:
        if col not in out.columns:
            out[col] = np.nan
    return out[cols]


def _standardize_ssgsea_results(
    df: pd.DataFrame,
    *,
    source: str,
    library_mode: str,
    engine: str,
) -> pd.DataFrame:
    """Normalize ssGSEA results to the shared output contract."""
    if df.empty:
        return pd.DataFrame()

    out = df.copy()
    rename_map = {"Name": "group", "Term": "gene_set", "NES": "nes", "ES": "es"}
    out = out.rename(columns={k: v for k, v in rename_map.items() if k in out.columns})
    out["group"] = out["group"].astype(str)
    out["term"] = out.get("gene_set", "")
    out["source"] = source
    out["library_mode"] = library_mode
    out["engine"] = engine
    out["method_used"] = "ssgsea"
    out["score"] = pd.to_numeric(out["nes"], errors="coerce") if "nes" in out.columns else np.nan
    for col in ("nes", "es", "score"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    out["pvalue"] = np.nan
    out["pvalue_adj"] = np.nan
    cols = [
        "group", "term", "gene_set", "source", "library_mode", "engine", "method_used",
        "score", "nes", "es", "pvalue", "pvalue_adj",
    ]
    for col in cols:
        if col not in out.columns:
            out[col] = np.nan
    return out[cols]


def run_enrichr(
    adata,
    *,
    groupby: str,
    source: str,
    library_mode: str,
    gene_sets: dict[str, list[str]],
    fdr_threshold: float,
    de_method: str,
    de_corr_method: str,
    enrichr_padj_cutoff: float,
    enrichr_log2fc_cutoff: float,
    enrichr_max_genes: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Run ORA-style enrichment on positive marker genes per group."""
    marker_df, _ = _extract_ranked_markers(
        adata, groupby=groupby, de_method=de_method, de_corr_method=de_corr_method
    )
    if marker_df.empty:
        return pd.DataFrame(), marker_df, {"warnings": ["No marker genes were available for enrichment."]}

    gp = get_dependency("gseapy")
    all_records: list[pd.DataFrame] = []
    warnings: list[str] = []
    n_input_genes_by_group: dict[str, int] = {}

    for group, group_df in marker_df.groupby("group", sort=False):
        filtered = group_df[
            group_df["pvals_adj"].fillna(np.inf).le(float(enrichr_padj_cutoff))
            & group_df["logfoldchanges"].fillna(-np.inf).ge(float(enrichr_log2fc_cutoff))
        ].copy()
        filtered = filtered.dropna(subset=["names"]).head(int(enrichr_max_genes))
        genes = filtered["names"].astype(str).tolist()
        n_input_genes_by_group[str(group)] = len(genes)
        if not genes:
            warnings.append(
                f"Group '{group}' had no positive markers after enrichr_padj_cutoff={enrichr_padj_cutoff} "
                f"and enrichr_log2fc_cutoff={enrichr_log2fc_cutoff}."
            )
            continue

        engine = "gseapy.enrich" if gp is not None else "hypergeometric_fallback"
        try:
            if gp is None:
                raise ImportError("gseapy not installed")
            enr = gp.enrich(
                gene_list=genes,
                gene_sets=gene_sets,
                background=list(adata.var_names.astype(str)),
                outdir=None,
                cutoff=float(fdr_threshold),
                no_plot=True,
                verbose=False,
            )
            res = enr.results.copy() if hasattr(enr, "results") else enr.res2d.copy()
        except Exception as exc:
            warnings.append(f"Group '{group}' ORA fell back to local hypergeometric testing: {exc}")
            res = _run_hypergeometric_ora(
                genes,
                gene_sets,
                background_size=int(adata.n_vars),
            )
            engine = "hypergeometric_fallback"

        std = _standardize_enrichr_results(
            res,
            group=str(group),
            source=source,
            library_mode=library_mode,
            engine=engine,
            n_input_genes=len(genes),
        )
        if not std.empty:
            all_records.append(std)

    enrich_df = pd.concat(all_records, ignore_index=True) if all_records else pd.DataFrame()
    enrich_df = _sort_results(enrich_df)
    return enrich_df, marker_df, {
        "warnings": warnings,
        "n_input_genes_by_group": n_input_genes_by_group,
        "ranking_metric": None,
    }


def run_gsea(
    adata,
    *,
    groupby: str,
    source: str,
    library_mode: str,
    gene_sets: dict[str, list[str]],
    de_method: str,
    de_corr_method: str,
    gsea_ranking_metric: str,
    gsea_min_size: int,
    gsea_max_size: int,
    gsea_permutation_num: int,
    gsea_weight: float,
    gsea_ascending: bool,
    gsea_threads: int,
    gsea_seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Run preranked GSEA per group."""
    marker_df, _ = _extract_ranked_markers(
        adata, groupby=groupby, de_method=de_method, de_corr_method=de_corr_method
    )
    if marker_df.empty:
        return pd.DataFrame(), marker_df, {"warnings": ["No marker rankings were available for GSEA."]}

    ranking_metric = _resolve_ranking_metric(marker_df, gsea_ranking_metric)
    gp = get_dependency("gseapy")

    all_records: list[pd.DataFrame] = []
    warnings: list[str] = []
    n_ranked_genes_by_group: dict[str, int] = {}

    for group, group_df in marker_df.groupby("group", sort=False):
        grp = group_df.dropna(subset=["names", ranking_metric]).copy()
        grp = grp.drop_duplicates(subset=["names"], keep="first")
        ranking = grp.set_index("names")[ranking_metric].sort_values(ascending=bool(gsea_ascending))
        n_ranked_genes_by_group[str(group)] = int(len(ranking))
        if len(ranking) < 10:
            warnings.append(f"Group '{group}' had < 10 ranked genes after filtering; skipping GSEA.")
            continue

        engine = "gseapy.prerank" if gp is not None else "rank_based_fallback"
        try:
            if gp is None:
                raise ImportError("gseapy not installed")
            pre = gp.prerank(
                rnk=ranking,
                gene_sets=gene_sets,
                outdir=None,
                min_size=int(gsea_min_size),
                max_size=int(gsea_max_size),
                permutation_num=int(gsea_permutation_num),
                weight=float(gsea_weight),
                ascending=bool(gsea_ascending),
                threads=int(gsea_threads),
                no_plot=True,
                seed=int(gsea_seed),
                verbose=False,
            )
            res = pre.res2d.copy()
        except Exception as exc:
            warnings.append(f"Group '{group}' GSEA fell back to a local rank-based method: {exc}")
            res = _fallback_prerank_gsea(
                ranking,
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
            ranking_metric=ranking_metric,
        )
        if not std.empty:
            all_records.append(std)

    enrich_df = pd.concat(all_records, ignore_index=True) if all_records else pd.DataFrame()
    enrich_df = _sort_results(enrich_df)
    return enrich_df, marker_df, {
        "warnings": warnings,
        "n_ranked_genes_by_group": n_ranked_genes_by_group,
        "ranking_metric": ranking_metric,
    }


def _compute_group_mean_expression(adata, *, groupby: str) -> pd.DataFrame:
    """Compute genes x groups mean expression from adata.X."""
    _ensure_obs_string(adata, groupby)
    groups = sorted(adata.obs[groupby].dropna().astype(str).unique().tolist(), key=str)
    series_list: list[pd.Series] = []
    for group in groups:
        mask = adata.obs[groupby].astype(str) == str(group)
        X_sub = adata.X[mask]
        if hasattr(X_sub, "toarray"):
            X_sub = X_sub.toarray()
        mean_expr = np.asarray(X_sub.mean(axis=0)).ravel()
        series_list.append(pd.Series(mean_expr, index=adata.var_names.astype(str), name=str(group)))
    return pd.concat(series_list, axis=1)


def _attach_ssgsea_scores_to_obs(
    adata,
    *,
    groupby: str,
    enrich_df: pd.DataFrame,
    n_top_terms: int,
) -> list[str]:
    """Project top group-level ssGSEA scores back onto obs for plotting."""
    if enrich_df.empty:
        return []

    top_terms = (
        enrich_df.groupby("gene_set", sort=False)["score"]
        .apply(lambda s: float(np.nanmax(np.abs(pd.to_numeric(s, errors="coerce").fillna(0.0)))))
        .sort_values(ascending=False)
        .head(int(n_top_terms))
        .index.tolist()
    )

    score_columns: list[str] = []
    for term in top_terms:
        term_df = enrich_df[enrich_df["gene_set"] == term].copy()
        if term_df.empty:
            continue
        mapping = term_df.set_index("group")["score"].to_dict()
        col = f"ssgsea_{_sanitize_name(str(term))}"
        adata.obs[col] = adata.obs[groupby].astype(str).map(mapping).astype(float)
        score_columns.append(col)
    if score_columns:
        adata.uns["enrichment_score_columns"] = score_columns
    return score_columns


def run_ssgsea(
    adata,
    *,
    groupby: str,
    source: str,
    library_mode: str,
    gene_sets: dict[str, list[str]],
    n_top_terms: int,
    ssgsea_sample_norm_method: str,
    ssgsea_correl_norm_type: str,
    ssgsea_min_size: int,
    ssgsea_max_size: int,
    ssgsea_weight: float,
    ssgsea_ascending: bool,
    ssgsea_threads: int,
    ssgsea_seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Run ssGSEA on group-level mean expression profiles."""
    expr_df = _compute_group_mean_expression(adata, groupby=groupby)
    gp = get_dependency("gseapy")
    sample_norm = None if ssgsea_sample_norm_method == "none" else ssgsea_sample_norm_method
    correl_norm = None if ssgsea_correl_norm_type == "none" else ssgsea_correl_norm_type

    warnings: list[str] = []
    engine = "gseapy.ssgsea" if gp is not None else "score_fallback"
    try:
        if gp is None:
            raise ImportError("gseapy not installed")
        ss = gp.ssgsea(
            data=expr_df,
            gene_sets=gene_sets,
            outdir=None,
            sample_norm_method=sample_norm,
            correl_norm_type=correl_norm,
            min_size=int(ssgsea_min_size),
            max_size=int(ssgsea_max_size),
            weight=float(ssgsea_weight),
            ascending=bool(ssgsea_ascending),
            threads=int(ssgsea_threads),
            no_plot=True,
            seed=int(ssgsea_seed),
            verbose=False,
        )
        res = ss.res2d.copy()
    except Exception as exc:
        warnings.append(f"ssGSEA fell back to a simplified local score because gseapy failed: {exc}")
        res = _fallback_ssgsea_scores(
            expr_df,
            gene_sets,
            sample_norm_method=sample_norm,
            correl_norm_type=correl_norm,
        )
        engine = "score_fallback"

    enrich_df = _standardize_ssgsea_results(
        res,
        source=source,
        library_mode=library_mode,
        engine=engine,
    )
    enrich_df = _sort_results(enrich_df)
    score_columns = _attach_ssgsea_scores_to_obs(
        adata,
        groupby=groupby,
        enrich_df=enrich_df,
        n_top_terms=n_top_terms,
    )
    return enrich_df, pd.DataFrame(), {
        "warnings": warnings,
        "score_columns": score_columns,
        "ranking_metric": None,
    }


def run_enrichment(
    adata,
    *,
    method: str = "enrichr",
    groupby: str = METHOD_PARAM_DEFAULTS["common"]["groupby"],
    source: str = METHOD_PARAM_DEFAULTS["common"]["source"],
    species: str = METHOD_PARAM_DEFAULTS["common"]["species"],
    gene_set: str | None = None,
    gene_set_file: str | None = None,
    fdr_threshold: float = METHOD_PARAM_DEFAULTS["common"]["fdr_threshold"],
    n_top_terms: int = METHOD_PARAM_DEFAULTS["common"]["n_top_terms"],
    de_method: str = METHOD_PARAM_DEFAULTS["common"]["de_method"],
    de_corr_method: str = METHOD_PARAM_DEFAULTS["common"]["de_corr_method"],
    enrichr_padj_cutoff: float = METHOD_PARAM_DEFAULTS["enrichr"]["enrichr_padj_cutoff"],
    enrichr_log2fc_cutoff: float = METHOD_PARAM_DEFAULTS["enrichr"]["enrichr_log2fc_cutoff"],
    enrichr_max_genes: int = METHOD_PARAM_DEFAULTS["enrichr"]["enrichr_max_genes"],
    gsea_ranking_metric: str = METHOD_PARAM_DEFAULTS["gsea"]["gsea_ranking_metric"],
    gsea_min_size: int = METHOD_PARAM_DEFAULTS["gsea"]["gsea_min_size"],
    gsea_max_size: int = METHOD_PARAM_DEFAULTS["gsea"]["gsea_max_size"],
    gsea_permutation_num: int = METHOD_PARAM_DEFAULTS["gsea"]["gsea_permutation_num"],
    gsea_weight: float = METHOD_PARAM_DEFAULTS["gsea"]["gsea_weight"],
    gsea_ascending: bool = METHOD_PARAM_DEFAULTS["gsea"]["gsea_ascending"],
    gsea_threads: int = METHOD_PARAM_DEFAULTS["gsea"]["gsea_threads"],
    gsea_seed: int = METHOD_PARAM_DEFAULTS["gsea"]["gsea_seed"],
    ssgsea_sample_norm_method: str = METHOD_PARAM_DEFAULTS["ssgsea"]["ssgsea_sample_norm_method"],
    ssgsea_correl_norm_type: str = METHOD_PARAM_DEFAULTS["ssgsea"]["ssgsea_correl_norm_type"],
    ssgsea_min_size: int = METHOD_PARAM_DEFAULTS["ssgsea"]["ssgsea_min_size"],
    ssgsea_max_size: int = METHOD_PARAM_DEFAULTS["ssgsea"]["ssgsea_max_size"],
    ssgsea_weight: float = METHOD_PARAM_DEFAULTS["ssgsea"]["ssgsea_weight"],
    ssgsea_ascending: bool = METHOD_PARAM_DEFAULTS["ssgsea"]["ssgsea_ascending"],
    ssgsea_threads: int = METHOD_PARAM_DEFAULTS["ssgsea"]["ssgsea_threads"],
    ssgsea_seed: int = METHOD_PARAM_DEFAULTS["ssgsea"]["ssgsea_seed"],
) -> dict:
    """Run pathway enrichment analysis with a stable local-first fallback strategy."""
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unknown method '{method}'. Choose from: {SUPPORTED_METHODS}")
    if groupby not in adata.obs.columns:
        raise ValueError(f"groupby column '{groupby}' not found in adata.obs")
    if de_method not in VALID_DE_METHODS:
        raise ValueError(f"de_method must be one of {VALID_DE_METHODS}")
    if de_corr_method not in VALID_DE_CORR_METHODS:
        raise ValueError(f"de_corr_method must be one of {VALID_DE_CORR_METHODS}")
    if species not in VALID_SPECIES:
        raise ValueError(f"species must be one of {VALID_SPECIES}")

    gene_sets, gene_set_meta = _resolve_gene_sets(
        source=source,
        species=species,
        gene_set=gene_set,
        gene_set_file=gene_set_file,
        var_names=adata.var_names,
    )
    gene_sets = _canonicalize_gene_sets(gene_sets, universe=adata.var_names)
    if not gene_sets:
        raise ValueError(
            "No gene sets overlapped the dataset gene universe. "
            "Check gene symbols, species, and the selected source / gene-set file."
        )

    logger.info(
        "Dispatching %s enrichment (requested_source=%s, resolved_source=%s, library_mode=%s)",
        method.upper(),
        gene_set_meta["requested_source"],
        gene_set_meta["resolved_source"],
        gene_set_meta["library_mode"],
    )

    if method == "enrichr":
        enrich_df, marker_df, method_meta = run_enrichr(
            adata,
            groupby=groupby,
            source=str(gene_set_meta["resolved_source"]),
            library_mode=str(gene_set_meta["library_mode"]),
            gene_sets=gene_sets,
            fdr_threshold=float(fdr_threshold),
            de_method=de_method,
            de_corr_method=de_corr_method,
            enrichr_padj_cutoff=float(enrichr_padj_cutoff),
            enrichr_log2fc_cutoff=float(enrichr_log2fc_cutoff),
            enrichr_max_genes=int(enrichr_max_genes),
        )
    elif method == "gsea":
        enrich_df, marker_df, method_meta = run_gsea(
            adata,
            groupby=groupby,
            source=str(gene_set_meta["resolved_source"]),
            library_mode=str(gene_set_meta["library_mode"]),
            gene_sets=gene_sets,
            de_method=de_method,
            de_corr_method=de_corr_method,
            gsea_ranking_metric=gsea_ranking_metric,
            gsea_min_size=int(gsea_min_size),
            gsea_max_size=int(gsea_max_size),
            gsea_permutation_num=int(gsea_permutation_num),
            gsea_weight=float(gsea_weight),
            gsea_ascending=bool(gsea_ascending),
            gsea_threads=int(gsea_threads),
            gsea_seed=int(gsea_seed),
        )
    else:
        enrich_df, marker_df, method_meta = run_ssgsea(
            adata,
            groupby=groupby,
            source=str(gene_set_meta["resolved_source"]),
            library_mode=str(gene_set_meta["library_mode"]),
            gene_sets=gene_sets,
            n_top_terms=int(n_top_terms),
            ssgsea_sample_norm_method=ssgsea_sample_norm_method,
            ssgsea_correl_norm_type=ssgsea_correl_norm_type,
            ssgsea_min_size=int(ssgsea_min_size),
            ssgsea_max_size=int(ssgsea_max_size),
            ssgsea_weight=float(ssgsea_weight),
            ssgsea_ascending=bool(ssgsea_ascending),
            ssgsea_threads=int(ssgsea_threads),
            ssgsea_seed=int(ssgsea_seed),
        )

    warnings = list(gene_set_meta.get("warnings", [])) + list(method_meta.get("warnings", []))
    n_significant = (
        int(enrich_df["pvalue_adj"].dropna().lt(float(fdr_threshold)).sum())
        if not enrich_df.empty and "pvalue_adj" in enrich_df.columns
        else 0
    )

    if method == "ssgsea":
        adata.uns["enrichment_results"] = enrich_df
        adata.uns["ssgsea_results"] = enrich_df
    else:
        adata.uns["enrichment_results"] = enrich_df
        adata.uns[f"{method}_results"] = enrich_df

    summary = {
        "n_cells": int(adata.n_obs),
        "n_genes": int(adata.n_vars),
        "n_groups": int(adata.obs[groupby].nunique()),
        "groups": sorted(adata.obs[groupby].dropna().astype(str).unique().tolist(), key=str),
        "method": method,
        "requested_source": gene_set_meta["requested_source"],
        "resolved_source": gene_set_meta["resolved_source"],
        "library_mode": gene_set_meta["library_mode"],
        "groupby": groupby,
        "species": species,
        "gene_set": gene_set,
        "gene_set_file": gene_set_file,
        "de_method": de_method,
        "de_corr_method": de_corr_method,
        "ranking_metric": method_meta.get("ranking_metric"),
        "n_gene_sets_available": int(len(gene_sets)),
        "n_terms_tested": int(len(enrich_df)),
        "n_significant": n_significant,
        "n_groups_with_hits": int(enrich_df["group"].nunique()) if not enrich_df.empty and "group" in enrich_df.columns else 0,
        "fdr_threshold": float(fdr_threshold),
        "n_top_terms": int(n_top_terms),
        "warnings": warnings,
        "score_columns": method_meta.get("score_columns", []),
        "marker_df": marker_df,
        "enrich_df": enrich_df,
    }
    summary.update({k: v for k, v in method_meta.items() if k not in {"warnings"}})
    return summary
