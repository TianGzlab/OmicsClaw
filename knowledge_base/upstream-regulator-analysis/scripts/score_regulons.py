"""
Score TF regulons by integrating ChIP-Atlas binding data with DE results.

For each enriched TF:
1. Intersect ChIP-Atlas target genes with DE gene lists
2. Fisher's exact test: are TF targets enriched among DE genes?
3. Directional concordance: do TF targets move in a consistent direction?
4. Combined regulatory score ranking TFs by evidence strength

This is the novel integration logic that bridges epigenomics and transcriptomics.
"""

import numpy as np
import pandas as pd
from scipy.stats import fisher_exact


def score_regulons(
    top_tfs,
    target_gene_data,
    de_data,
    min_targets_overlap=3,
):
    """
    Score TF regulons by integrating ChIP-Atlas targets with DE results.

    Parameters
    ----------
    top_tfs : pd.DataFrame
        Top enriched TFs with columns: antigen, best_qvalue, best_fe, source.
    target_gene_data : dict[str, pd.DataFrame]
        TF name -> target genes summary DataFrame (from download_target_genes).
        Each DataFrame has columns: gene, avg_score, ...
    de_data : dict
        Output from load_de_results() or load_example_data().
    min_targets_overlap : int
        Minimum DE genes overlapping TF targets to score (default: 3).

    Returns
    -------
    pd.DataFrame
        Columns: tf, regulatory_score, fisher_pvalue, fisher_odds_ratio,
        concordance, direction, chip_best_qvalue, chip_best_fe,
        n_targets_de_up, n_targets_de_down, n_targets_de_total,
        n_targets_in_background, pct_targets_de, n_background, source.
    """
    de_up_set = set(de_data["de_up"])
    de_down_set = set(de_data["de_down"])
    de_sig_set = de_up_set | de_down_set
    background_set = set(de_data["background_genes"])
    n_background = len(background_set)
    n_de = len(de_sig_set)

    results = []

    for _, tf_row in top_tfs.iterrows():
        tf_name = tf_row["antigen"]
        chip_q = tf_row["best_qvalue"]
        chip_fe = tf_row["best_fe"]
        source = tf_row.get("source", "both")

        # Get target gene list for this TF
        if tf_name not in target_gene_data:
            continue

        target_df = target_gene_data[tf_name]
        if target_df is None or len(target_df) == 0:
            continue

        # Extract gene symbols from target data
        gene_col = "gene" if "gene" in target_df.columns else target_df.columns[0]
        tf_targets = set(target_df[gene_col].astype(str).tolist())

        # Intersect with background (only count genes we actually measured)
        tf_targets_in_bg = tf_targets & background_set
        if len(tf_targets_in_bg) == 0:
            continue

        # Count overlaps
        n_targets_up = len(tf_targets_in_bg & de_up_set)
        n_targets_down = len(tf_targets_in_bg & de_down_set)
        n_targets_de = n_targets_up + n_targets_down

        if n_targets_de < min_targets_overlap:
            continue

        # --- Fisher's exact test ---
        # 2x2 contingency: (TF-bound vs not) x (DE vs not-DE)
        a = n_targets_de                                    # bound & DE
        b = len(tf_targets_in_bg) - n_targets_de            # bound & not-DE
        c = n_de - n_targets_de                             # not-bound & DE
        d = n_background - len(tf_targets_in_bg) - c        # not-bound & not-DE

        # Ensure no negative values (can happen with set overlaps)
        d = max(d, 0)

        contingency = [[a, b], [c, d]]
        odds_ratio, fisher_p = fisher_exact(contingency, alternative="greater")

        # --- Directional concordance ---
        dominant = max(n_targets_up, n_targets_down)
        concordance = dominant / n_targets_de if n_targets_de > 0 else 0

        if n_targets_up > n_targets_down:
            direction = "activator"
        elif n_targets_down > n_targets_up:
            direction = "repressor"
        else:
            direction = "mixed"

        if concordance <= 0.6:
            direction = "mixed"

        # --- Combined regulatory score ---
        # Higher = stronger evidence across all three axes
        log_fisher = -np.log10(fisher_p + 1e-300)
        log_chip = -np.log10(chip_q + 1e-300)
        regulatory_score = log_fisher * concordance * log_chip

        results.append({
            "tf": tf_name,
            "regulatory_score": round(regulatory_score, 2),
            "fisher_pvalue": fisher_p,
            "fisher_odds_ratio": round(odds_ratio, 2),
            "concordance": round(concordance, 3),
            "direction": direction,
            "chip_best_qvalue": chip_q,
            "chip_best_fe": round(chip_fe, 2),
            "n_targets_de_up": n_targets_up,
            "n_targets_de_down": n_targets_down,
            "n_targets_de_total": n_targets_de,
            "n_targets_in_background": len(tf_targets_in_bg),
            "pct_targets_de": round(n_targets_de / len(tf_targets_in_bg), 4),
            "n_background": n_background,
            "source": source,
        })

    if not results:
        print("   Warning: No TFs passed the minimum overlap threshold.")
        return pd.DataFrame()

    df = pd.DataFrame(results).sort_values("regulatory_score", ascending=False).reset_index(drop=True)

    print(f"   Scored {len(df)} TF regulons")
    n_act = (df["direction"] == "activator").sum()
    n_rep = (df["direction"] == "repressor").sum()
    n_mix = (df["direction"] == "mixed").sum()
    print(f"   Directions: {n_act} activators, {n_rep} repressors, {n_mix} mixed")

    return df

