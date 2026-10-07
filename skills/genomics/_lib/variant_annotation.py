"""Parsing and calculations for variant-annotation."""
from __future__ import annotations
import pandas as pd


def compute_annotation_stats(df: pd.DataFrame) -> dict:
    """Compute annotation summary statistics."""
    impact_counts = df["impact"].value_counts().to_dict()
    consequence_counts = df["consequence"].value_counts().to_dict()

    stats = {
        "n_variants": len(df),
        "n_high_impact": int(impact_counts.get("HIGH", 0)),
        "n_moderate_impact": int(impact_counts.get("MODERATE", 0)),
        "n_low_impact": int(impact_counts.get("LOW", 0)),
        "n_modifier_impact": int(impact_counts.get("MODIFIER", 0)),
        "top_consequences": dict(
            sorted(consequence_counts.items(), key=lambda x: -x[1])[:10]
        ),
        "n_genes_affected": int(df[df["gene"] != "."]["gene"].nunique()),
    }

    # SIFT/PolyPhen stats for missense variants
    missense = df[df["consequence"] == "missense_variant"]
    if len(missense) > 0:
        sift_del = (missense["sift_prediction"] == "deleterious").sum()
        pp_dam = missense["polyphen_prediction"].isin(
            ["probably_damaging", "possibly_damaging"]
        ).sum()
        stats["n_missense"] = len(missense)
        stats["n_sift_deleterious"] = int(sift_del)
        stats["n_polyphen_damaging"] = int(pp_dam)
    else:
        stats["n_missense"] = 0
        stats["n_sift_deleterious"] = 0
        stats["n_polyphen_damaging"] = 0

    # CADD summary
    cadd_vals = pd.to_numeric(df["cadd_phred"], errors="coerce").dropna()
    if len(cadd_vals) > 0:
        stats["mean_cadd_phred"] = round(float(cadd_vals.mean()), 1)
        stats["n_cadd_above_20"] = int((cadd_vals >= 20).sum())
        stats["n_cadd_above_30"] = int((cadd_vals >= 30).sum())

    return stats
