"""Over-representation calculations for supplied metabolite pathways."""
import logging
import numpy as np
import pandas as pd
from scipy import stats as sp_stats
logger = logging.getLogger(__name__)

DEMO_METABOLIC_PATHWAYS = {
    "Glycolysis / Gluconeogenesis": {
        "kegg_id": "map00010",
        "metabolites": [
            "glucose", "glucose-6-phosphate", "fructose-6-phosphate",
            "glyceraldehyde-3-phosphate", "pyruvate", "lactate",
        ],
    },
    "Citrate cycle (TCA cycle)": {
        "kegg_id": "map00020",
        "metabolites": [
            "citrate", "isocitrate", "alpha-ketoglutarate", "succinate",
            "fumarate", "malate", "oxaloacetate",
        ],
    },
    "Fatty acid biosynthesis": {
        "kegg_id": "map00061",
        "metabolites": [
            "acetyl-CoA", "malonyl-CoA", "palmitate", "stearate", "oleate",
        ],
    },
    "Purine metabolism": {
        "kegg_id": "map00230",
        "metabolites": [
            "adenine", "guanine", "hypoxanthine", "xanthine",
            "uric_acid", "inosine", "adenosine",
        ],
    },
    "Pyrimidine metabolism": {
        "kegg_id": "map00240",
        "metabolites": ["uracil", "cytosine", "thymine", "uridine", "thymidine"],
    },
    "Alanine, aspartate and glutamate metabolism": {
        "kegg_id": "map00250",
        "metabolites": [
            "alanine", "aspartate", "glutamate", "glutamine",
            "asparagine", "oxaloacetate",
        ],
    },
    "Glycine, serine and threonine metabolism": {
        "kegg_id": "map00260",
        "metabolites": ["glycine", "serine", "threonine", "pyruvate"],
    },
    "Tryptophan metabolism": {
        "kegg_id": "map00380",
        "metabolites": [
            "tryptophan", "serotonin", "kynurenine", "indole",
            "5-hydroxyindoleacetate",
        ],
    },
    "Primary bile acid biosynthesis": {
        "kegg_id": "map00120",
        "metabolites": [
            "cholesterol", "cholate", "chenodeoxycholate",
            "taurocholate", "glycocholate",
        ],
    },
}

# Total background metabolite set (union of all pathways)
_ALL_PATHWAY_METABOLITES = set()
for _info in DEMO_METABOLIC_PATHWAYS.values():
    _ALL_PATHWAY_METABOLITES.update(m.lower() for m in _info["metabolites"])


# ---------------------------------------------------------------------------
# Hypergeometric ORA
# ---------------------------------------------------------------------------

def _benjamini_hochberg(pvalues: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg FDR correction."""
    pv = np.asarray(pvalues, dtype=float)
    n = len(pv)
    if n == 0:
        return pv
    order = np.argsort(pv)
    sorted_p = pv[order]
    adjusted = np.empty(n)
    adjusted[-1] = sorted_p[-1]
    for i in range(n - 2, -1, -1):
        adjusted[i] = min(sorted_p[i] * n / (i + 1), adjusted[i + 1])
    adjusted = np.clip(adjusted, 0, 1)
    result = np.empty(n)
    result[order] = adjusted
    return result


def pathway_enrichment(
    metabolite_list: list[str],
    method: str = "ora",
    pathways=None,
) -> pd.DataFrame:
    """Over-representation analysis using the hypergeometric test.

    For each pathway, the p-value is computed as::

        P(X >= k) = 1 - hypergeom.cdf(k-1, N, K, n)

    where

    - N = total metabolites in the background (all pathway members)
    - K = number of metabolites in the current pathway
    - n = number of query (significant) metabolites that are in the background
    - k = number of query metabolites that overlap with the pathway

    Parameters
    ----------
    metabolite_list : list[str]
        Query metabolite names (e.g., significant metabolites).
    method : str
        Analysis method label (informational).

    Returns
    -------
    DataFrame with enrichment results, sorted by p-value, with FDR column.
    """
    logger.info(
        "Pathway analysis: %d metabolites, method=%s",
        len(metabolite_list), method,
    )

    reference = DEMO_METABOLIC_PATHWAYS if pathways is None else pathways
    background = {m.lower() for info in reference.values() for m in info["metabolites"]}
    query = set(m.lower() for m in metabolite_list)
    N = len(background)  # background size
    n = len(query.intersection(background))  # query hits in background

    records: list[dict] = []

    for pathway, info in reference.items():
        members = set(m.lower() for m in info["metabolites"])
        K = len(members)  # pathway size
        overlap = query.intersection(members)
        k = len(overlap)  # hits

        if k == 0:
            continue

        # Hypergeometric test: P(X >= k)
        pval = float(sp_stats.hypergeom.sf(k - 1, N, K, n))

        records.append({
            "pathway": pathway,
            "kegg_id": info["kegg_id"],
            "hits": k,
            "pathway_size": K,
            "background_size": N,
            "query_in_background": n,
            "hit_metabolites": ";".join(sorted(overlap)),
            "pvalue": pval,
            "impact": round(k / K, 4),
        })

    df = pd.DataFrame(records, columns=["pathway", "kegg_id", "hits", "pathway_size", "background_size", "query_in_background", "hit_metabolites", "pvalue", "impact"])
    if not df.empty:
        df = df.sort_values("pvalue").reset_index(drop=True)
        df["fdr"] = _benjamini_hochberg(df["pvalue"].values)

    if "fdr" not in df:
        df["fdr"] = pd.Series(dtype=float)
    return df
