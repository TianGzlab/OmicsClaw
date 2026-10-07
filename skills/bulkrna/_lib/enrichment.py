"""Enrichment calculations with explicit gene sets and local random state."""
import logging
import warnings
import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
logger = logging.getLogger(__name__)
SUPPORTED_METHODS = ("ora", "gsea")
RANKING_METRIC_PREFERENCE = ("stat", "scores", "logfoldchanges", "log2FoldChange")

def _resolve_ranking_metric(de_df: pd.DataFrame, requested: str | None = None) -> tuple[str, pd.Series]:
    """Resolve the best ranking metric for GSEA.

    Preference order: stat > scores > logfoldchanges > log2FoldChange.
    Fallback: signed_pvalue = -log10(pvalue) * sign(log2FC).

    Returns (metric_name, ranked_series indexed by gene).
    """
    if requested and requested in de_df.columns:
        logger.info("Using requested ranking metric: '%s'", requested)
        return requested, de_df.set_index("gene")[requested].sort_values(ascending=False)

    for metric in RANKING_METRIC_PREFERENCE:
        if metric in de_df.columns:
            logger.info("Auto-detected ranking metric: '%s'", metric)
            return metric, de_df.set_index("gene")[metric].sort_values(ascending=False)

    if "pvalue" in de_df.columns and "log2FoldChange" in de_df.columns:
        signed_p = -np.log10(de_df["pvalue"].clip(lower=1e-300)) * np.sign(de_df["log2FoldChange"])
        logger.info("Using computed ranking metric: signed -log10(pvalue)")
        return "signed_pvalue", pd.Series(signed_p.values, index=de_df["gene"]).sort_values(ascending=False)

    logger.warning("No suitable ranking metric found; using log2FoldChange")
    return "log2FoldChange", de_df.set_index("gene")["log2FoldChange"].sort_values(ascending=False)


def _build_demo_gene_sets() -> dict[str, list[str]]:
    """Create synthetic pathway gene sets using GENE_XXX names from demo data."""
    return {
        "Cell_Cycle": [f"GENE_{i:03d}" for i in range(51, 61)],
        "Apoptosis": [f"GENE_{i:03d}" for i in range(61, 71)],
        "Immune_Response": [f"GENE_{i:03d}" for i in range(71, 81)],
        "Metabolism": [f"GENE_{i:03d}" for i in range(81, 91)],
        "Signal_Transduction": [f"GENE_{i:03d}" for i in range(91, 101)],
        "DNA_Repair": [f"GENE_{i:03d}" for i in range(101, 111)],
        "Transcription": [f"GENE_{i:03d}" for i in range(111, 121)],
        "Translation": [f"GENE_{i:03d}" for i in range(121, 131)],
        "Transport": [f"GENE_{i:03d}" for i in range(131, 141)],
        "Cytoskeleton": [f"GENE_{i:03d}" for i in range(141, 151)],
        "Extracellular_Matrix": [f"GENE_{i:03d}" for i in range(151, 161)],
        "Lipid_Metabolism": [f"GENE_{i:03d}" for i in range(161, 171)],
        "Amino_Acid_Metabolism": [f"GENE_{i:03d}" for i in range(171, 181)],
        "Oxidative_Phosphorylation": [f"GENE_{i:03d}" for i in range(181, 191)],
        "mRNA_Processing": [f"GENE_{i:03d}" for i in range(191, 201)],
    }


def _generate_demo_de_results() -> pd.DataFrame:
    """Create a synthetic DE results table for demonstration.

    Returns a DataFrame with columns: gene, log2FoldChange, pvalue, padj.
    - GENE_051-100: upregulated (log2FC ~ N(2.5, 0.5), padj < 0.05)
    - GENE_101-150: downregulated (log2FC ~ N(-2.5, 0.5), padj < 0.05)
    - GENE_001-050, GENE_151-200: not significant (log2FC ~ N(0, 0.3), padj > 0.1)
    """
    rng = np.random.RandomState(42)

    records: list[dict] = []

    # Not significant: GENE_001-050
    for i in range(1, 51):
        lfc = rng.normal(0, 0.3)
        pval = rng.uniform(0.1, 1.0)
        records.append({
            "gene": f"GENE_{i:03d}",
            "log2FoldChange": round(float(lfc), 4),
            "pvalue": round(float(pval), 6),
            "padj": round(float(rng.uniform(0.1, 1.0)), 6),
        })

    # Upregulated: GENE_051-100
    for i in range(51, 101):
        lfc = rng.normal(2.5, 0.5)
        pval = float(10 ** rng.uniform(-10, -2))
        padj = float(pval * rng.uniform(1.0, 5.0))
        padj = min(padj, 0.049)
        records.append({
            "gene": f"GENE_{i:03d}",
            "log2FoldChange": round(float(lfc), 4),
            "pvalue": pval,
            "padj": padj,
        })

    # Downregulated: GENE_101-150
    for i in range(101, 151):
        lfc = rng.normal(-2.5, 0.5)
        pval = float(10 ** rng.uniform(-10, -2))
        padj = float(pval * rng.uniform(1.0, 5.0))
        padj = min(padj, 0.049)
        records.append({
            "gene": f"GENE_{i:03d}",
            "log2FoldChange": round(float(lfc), 4),
            "pvalue": pval,
            "padj": padj,
        })

    # Not significant: GENE_151-200
    for i in range(151, 201):
        lfc = rng.normal(0, 0.3)
        pval = rng.uniform(0.1, 1.0)
        records.append({
            "gene": f"GENE_{i:03d}",
            "log2FoldChange": round(float(lfc), 4),
            "pvalue": round(float(pval), 6),
            "padj": round(float(rng.uniform(0.1, 1.0)), 6),
        })

    return pd.DataFrame(records)


def _benjamini_hochberg(pvalues: np.ndarray) -> np.ndarray:
    """Manual Benjamini-Hochberg FDR correction."""
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
    background_size: int,
) -> pd.DataFrame:
    """Run over-representation analysis using the hypergeometric test.

    For each pathway, compute the probability of observing at least k
    overlapping genes by chance.

    Parameters
    ----------
    gene_list : list[str]
        Significant genes to test for enrichment.
    gene_sets : dict[str, list[str]]
        Pathway name to gene list mapping.
    background_size : int
        Total number of genes in the background (N).

    Returns
    -------
    pd.DataFrame with columns: term, overlap, term_size, pvalue, padj, genes.
    """
    gene_set_query = set(gene_list)
    n = len(gene_list)
    records: list[dict] = []

    for term, pathway_genes in gene_sets.items():
        pathway_set = set(pathway_genes)
        overlap_genes = gene_set_query & pathway_set
        k = len(overlap_genes)
        K = len(pathway_set)

        # P(X >= k) using hypergeometric survival function
        # sf(k-1, N, K, n) = P(X >= k)
        pval = float(scipy_stats.hypergeom.sf(k - 1, background_size, K, n))

        records.append({
            "term": term,
            "overlap": k,
            "term_size": K,
            "pvalue": pval,
            "genes": ",".join(sorted(overlap_genes)) if overlap_genes else "",
        })

    df = pd.DataFrame(records)
    if len(df) > 0:
        df["padj"] = _benjamini_hochberg(df["pvalue"].values)
    else:
        df["padj"] = pd.Series(dtype=float)
    return df.sort_values("pvalue").reset_index(drop=True)


def _run_gsea_fallback(
    de_df: pd.DataFrame,
    gene_sets: dict[str, list[str]],
    *, random_state: int = 42,
) -> pd.DataFrame:
    """Simple rank-based enrichment via permutation testing.

    Ranks genes by log2FC * -log10(pvalue), then for each gene set computes
    the mean rank versus the distribution of mean ranks from random gene sets
    of the same size (100 permutations).

    Parameters
    ----------
    de_df : pd.DataFrame
        DE results with columns: gene, log2FoldChange, pvalue.
    gene_sets : dict[str, list[str]]
        Pathway name to gene list mapping.

    Returns
    -------
    pd.DataFrame with columns: term, es, nes, pvalue, padj, n_genes.
    """
    rng = np.random.RandomState(random_state)

    # Compute ranking score: log2FC * -log10(pvalue)
    df = de_df.copy()
    df["rank_score"] = df["log2FoldChange"] * (-np.log10(df["pvalue"].clip(lower=1e-300)))
    df = df.sort_values("rank_score", ascending=False).reset_index(drop=True)
    df["rank"] = np.arange(len(df))

    gene_to_rank = dict(zip(df["gene"], df["rank"]))
    n_genes_total = len(df)
    n_perms = 100

    records: list[dict] = []
    for term, pathway_genes in gene_sets.items():
        # Get ranks for genes in this set that are in the DE results
        ranks = [gene_to_rank[g] for g in pathway_genes if g in gene_to_rank]
        n_in_set = len(ranks)
        if n_in_set == 0:
            continue

        observed_mean_rank = float(np.mean(ranks))

        # Permutation test: sample random gene sets of same size
        null_means = np.array([
            float(np.mean(rng.choice(n_genes_total, size=n_in_set, replace=False)))
            for _ in range(n_perms)
        ])

        null_std = float(np.std(null_means))
        null_mean = float(np.mean(null_means))

        # Enrichment score: negative because lower rank = higher score
        es = null_mean - observed_mean_rank
        nes = es / null_std if null_std > 0 else 0.0

        # Two-sided p-value from permutation
        n_extreme = int(np.sum(np.abs(null_means - null_mean) >= abs(es)))
        pval = (n_extreme + 1) / (n_perms + 1)

        records.append({
            "term": term,
            "es": round(float(es), 4),
            "nes": round(float(nes), 4),
            "pvalue": float(pval),
            "n_genes": n_in_set,
        })

    df_result = pd.DataFrame(records, columns=["term", "es", "nes", "pvalue", "n_genes"])
    if len(df_result) > 0:
        df_result["padj"] = _benjamini_hochberg(df_result["pvalue"].values)
    else:
        df_result["padj"] = pd.Series(dtype=float)
    return df_result.sort_values("pvalue").reset_index(drop=True)


def core_analysis(
    de_df: pd.DataFrame,
    *,
    method: str = "ora",
    gene_sets: dict[str, list[str]] | None = None,
    padj_cutoff: float = 0.05,
    lfc_cutoff: float = 1.0,
    random_state: int = 42,
) -> dict:
    """Run pathway enrichment analysis on DE results.

    Parameters
    ----------
    de_df : pd.DataFrame
        DE results with columns: gene, log2FoldChange, pvalue, padj.
    method : str
        ``"ora"`` for over-representation analysis, ``"gsea"`` for
        rank-based gene set enrichment.
    gene_sets : dict or None
        Pathway name to gene list mapping. If None, uses built-in demo sets.
    padj_cutoff : float
        Adjusted p-value cutoff for filtering significant genes (ORA).
    lfc_cutoff : float
        Absolute log2FC cutoff for filtering significant genes (ORA).

    Returns
    -------
    dict with keys: n_input_genes, n_significant, method_used,
        n_terms_tested, n_enriched_terms, enrichment_df.
    """
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unknown method '{method}'. Choose from: {SUPPORTED_METHODS}")

    if not gene_sets:
        raise ValueError("gene_sets must be an explicit nonempty mapping")
    fallback_reason = None

    n_input = len(de_df)
    method_used = method
    background_gene_count: int | None = None
    query_genes_in_background: int | None = None

    if method == "ora":
        # Filter significant genes
        sig = de_df.dropna(subset=["padj"])
        sig = sig[(sig["padj"] < padj_cutoff) & (sig["log2FoldChange"].abs() > lfc_cutoff)]
        sig_genes = sig["gene"].tolist()
        n_significant = len(sig_genes)

        background_genes = sorted(
            {
                str(gene)
                for pathway_genes in gene_sets.values()
                for gene in pathway_genes
                if str(gene)
            }
        )
        background_set = set(background_genes)
        background_size = len(background_genes)
        sig_genes_in_background = [
            gene for gene in sig_genes if gene in background_set
        ]
        background_gene_count = background_size
        query_genes_in_background = len(set(sig_genes_in_background))
        logger.info(
            "ORA: %d significant genes (%d in the %d-gene pathway universe; "
            "padj < %s, |log2FC| > %s).",
            n_significant,
            query_genes_in_background,
            background_size,
            padj_cutoff,
            lfc_cutoff,
        )

        # Separate up/down gene lists (from Biomni run_ora.R)
        sig_up = sig[sig["log2FoldChange"] > 0]["gene"].tolist()
        sig_down = sig[sig["log2FoldChange"] < 0]["gene"].tolist()
        logger.info("  Up-regulated: %d, Down-regulated: %d", len(sig_up), len(sig_down))

        # Try gseapy first, fall back to built-in hypergeometric
        try:
            import gseapy as gp
            logger.info("Using gseapy for ORA (Enrichr).")
            enr = gp.enrichr(
                gene_list=sig_genes,
                gene_sets=gene_sets,
                organism="human",
                background=background_genes,
                outdir=None,
                no_plot=True,
            )
            enrichment_df = enr.results.copy() if hasattr(enr, "results") else enr.res2d.copy()
            col_map = {
                "Term": "term",
                "Adjusted P-value": "padj",
                "P-value": "pvalue",
                "Genes": "genes",
                "Overlap": "overlap",
            }
            enrichment_df = enrichment_df.rename(
                columns={k: v for k, v in col_map.items() if k in enrichment_df.columns}
            )
            if "term_size" not in enrichment_df.columns:
                enrichment_df["term_size"] = enrichment_df.get("overlap", 0)
            method_used = "ora_gseapy"
        except Exception as exc:
            fallback_reason = str(exc)
            warnings.warn(f"{method} backend failed: {exc}; using a built-in calculation", RuntimeWarning, stacklevel=2)
            if isinstance(exc, ImportError):
                logger.info("gseapy not available; using built-in hypergeometric ORA.")
            else:
                logger.warning("gseapy ORA failed (%s); using built-in fallback.", exc)
            enrichment_df = _run_hypergeometric_ora(
                sig_genes_in_background,
                gene_sets,
                background_size,
            )
            method_used = "ora_builtin"

    else:  # gsea
        n_significant = 0  # GSEA uses all genes, not pre-filtered
        logger.info("GSEA: ranking %d genes.", n_input)

        # Resolve ranking metric (from Biomni prepare_gene_lists.R)
        metric_name, rnk = _resolve_ranking_metric(de_df)

        # Try gseapy first, fall back to built-in rank-based method
        try:
            import gseapy as gp
            logger.info("Using gseapy for pre-ranked GSEA (metric: %s).", metric_name)
            pre_res = gp.prerank(
                rnk=rnk,
                gene_sets=gene_sets,
                min_size=3,
                max_size=1000,
                permutation_num=100,
                outdir=None,
                seed=random_state,
                verbose=False,
            )
            enrichment_df = pre_res.res2d.copy()
            enrichment_df = enrichment_df.rename(columns={
                "Term": "term",
                "NES": "nes",
                "NOM p-val": "pvalue",
                "FDR q-val": "padj",
            })
            if "es" not in enrichment_df.columns:
                enrichment_df["es"] = enrichment_df.get("ES", 0.0)
            if "n_genes" not in enrichment_df.columns:
                enrichment_df["n_genes"] = enrichment_df.get("Tag %", "").apply(
                    lambda x: int(str(x).split("/")[0]) if "/" in str(x) else 0
                )
            method_used = "gsea_gseapy"
        except Exception as exc:
            fallback_reason = str(exc)
            warnings.warn(f"{method} backend failed: {exc}; using a built-in calculation", RuntimeWarning, stacklevel=2)
            if isinstance(exc, ImportError):
                logger.info("gseapy not available; using built-in rank-based GSEA.")
            else:
                logger.warning("gseapy GSEA failed (%s); using built-in fallback.", exc)
            enrichment_df = _run_gsea_fallback(de_df, gene_sets, random_state=random_state)
            method_used = "rank_permutation"

    # Count enriched terms
    n_enriched = 0
    if not enrichment_df.empty and "padj" in enrichment_df.columns:
        n_enriched = int(enrichment_df["padj"].dropna().lt(padj_cutoff).sum())

    logger.info(
        "Enrichment complete: %d terms tested, %d enriched (padj < %s).",
        len(enrichment_df), n_enriched, padj_cutoff,
    )

    return {
        "requested_method": method,
        "executed_method": method_used,
        "fallback_reason": fallback_reason,
        "n_input_genes": n_input,
        "n_significant": n_significant,
        "method_used": method_used,
        "n_terms_tested": len(enrichment_df),
        "n_enriched_terms": n_enriched,
        "background_genes": background_gene_count,
        "query_genes_in_background": query_genes_in_background,
        "enrichment_df": enrichment_df,
    }
