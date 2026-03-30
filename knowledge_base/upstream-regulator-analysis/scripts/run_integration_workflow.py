"""
Main orchestrator for upstream regulator analysis.

Integrates ChIP-Atlas TF binding (epigenomics) with DE results (transcriptomics)
to identify transcription factors driving differential expression.

Workflow:
1. Submit up/down gene lists to ChIP-Atlas Peak Enrichment API
2. Identify top enriched TFs
3. Download target gene lists for top TFs
4. Score regulons (Fisher's exact test + concordance)

Reuses API code from sibling skills:
- chip-atlas-peak-enrichment (enrichment API)
- chip-atlas-target-genes (target gene downloads)
"""

import os
import sys
import time

import numpy as np
import pandas as pd

# --- Import from sibling skills ---
_skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_repo_root = os.path.dirname(_skill_root)

# Import enrichment workflow from chip-atlas-peak-enrichment
_peak_enrichment_scripts = os.path.join(_repo_root, "chip-atlas-peak-enrichment", "scripts")
if not os.path.isdir(_peak_enrichment_scripts):
    raise ImportError(
        f"Sibling skill not found: {_peak_enrichment_scripts}\n"
        "This skill requires chip-atlas-peak-enrichment to be installed alongside it."
    )
sys.path.insert(0, _peak_enrichment_scripts)

try:
    from run_enrichment_workflow import run_enrichment_workflow as _run_peak_enrichment
except ImportError:
    from query_chipatlas_api import (
        submit_enrichment_job, poll_job_status, retrieve_results, parse_api_results,
    )
    _run_peak_enrichment = None

# Import target gene download from chip-atlas-target-genes
_target_genes_scripts = os.path.join(_repo_root, "chip-atlas-target-genes", "scripts")
if not os.path.isdir(_target_genes_scripts):
    raise ImportError(
        f"Sibling skill not found: {_target_genes_scripts}\n"
        "This skill requires chip-atlas-target-genes to be installed alongside it."
    )
sys.path.insert(0, _target_genes_scripts)

from download_target_genes import check_antigen_available, download_target_genes

# Import local scoring module
try:
    from scripts.score_regulons import score_regulons
except ImportError:
    from score_regulons import score_regulons

# Restore sys.path (avoid polluting for other imports)
if _peak_enrichment_scripts in sys.path:
    sys.path.remove(_peak_enrichment_scripts)
if _target_genes_scripts in sys.path:
    sys.path.remove(_target_genes_scripts)


def run_integration_workflow(
    de_data,
    genome="hg38",
    antigen_class="TFs and others",
    cell_class="All cell types",
    threshold=50,
    distance=5,
    max_tfs=10,
    min_enrichment_qvalue=0.05,
    min_targets_overlap=3,
    output_dir="regulator_results",
):
    """
    Run the complete upstream regulator integration workflow.

    Parameters
    ----------
    de_data : dict
        Output from load_de_results() or load_example_data().
    genome : str
        Genome assembly (default: "hg38").
    antigen_class : str
        ChIP-Atlas antigen class filter (default: "TFs and others").
    cell_class : str
        ChIP-Atlas cell type class filter (default: "All cell types").
    threshold : int
        MACS2 peak threshold: 50, 100, 200, or 500 (default: 50).
    distance : int
        Distance from TSS in kb for target genes: 1, 5, or 10 (default: 5).
    max_tfs : int
        Maximum TFs to retrieve target gene lists for (default: 10).
    min_enrichment_qvalue : float
        Q-value cutoff for considering a TF enriched (default: 0.05).
    min_targets_overlap : int
        Minimum DE genes overlapping TF targets to score (default: 3).
    output_dir : str
        Output directory for results.

    Returns
    -------
    dict
        - regulon_scores: pd.DataFrame
        - enrichment_results_up: dict (peak enrichment for upregulated genes)
        - enrichment_results_down: dict (peak enrichment for downregulated genes)
        - target_gene_data: dict[str, pd.DataFrame]
        - de_data: dict (passed through)
        - parameters: dict
        - metadata: dict
    """
    os.makedirs(output_dir, exist_ok=True)

    print("\n" + "=" * 60)
    print("  UPSTREAM REGULATOR ANALYSIS")
    print("  Integrating ChIP-Atlas binding × DE results")
    print("=" * 60)

    # =====================================================================
    # STEP 2A: Submit upregulated genes to ChIP-Atlas Peak Enrichment
    # =====================================================================
    enrichment_up = None
    enrichment_down = None

    if len(de_data["de_up"]) >= 3:
        print(f"\n--- Peak Enrichment: {len(de_data['de_up'])} upregulated genes ---")
        try:
            enrichment_up = _run_peak_enrichment(
                gene_list=de_data["de_up"],
                genome=genome,
                antigen_class=antigen_class,
                cell_class=cell_class,
                threshold=threshold,
                output_dir=os.path.join(output_dir, "_enrichment_up"),
            )
        except Exception as e:
            print(f"   WARNING: Enrichment for upregulated genes failed: {e}")
    else:
        print(f"\n   Skipping upregulated enrichment: only {len(de_data['de_up'])} genes (need ≥3)")

    # Brief delay between API calls
    if enrichment_up is not None:
        time.sleep(5)

    # =====================================================================
    # STEP 2B: Submit downregulated genes to ChIP-Atlas Peak Enrichment
    # =====================================================================
    if len(de_data["de_down"]) >= 3:
        print(f"\n--- Peak Enrichment: {len(de_data['de_down'])} downregulated genes ---")
        try:
            enrichment_down = _run_peak_enrichment(
                gene_list=de_data["de_down"],
                genome=genome,
                antigen_class=antigen_class,
                cell_class=cell_class,
                threshold=threshold,
                output_dir=os.path.join(output_dir, "_enrichment_down"),
            )
        except Exception as e:
            print(f"   WARNING: Enrichment for downregulated genes failed: {e}")
    else:
        print(f"\n   Skipping downregulated enrichment: only {len(de_data['de_down'])} genes (need ≥3)")

    if enrichment_up is None and enrichment_down is None:
        raise RuntimeError(
            "Both enrichment analyses failed. Cannot identify upstream regulators. "
            "Check gene list size (need ≥3 genes per direction) and network connectivity."
        )

    # =====================================================================
    # STEP 2C: Aggregate enriched TFs from both directions
    # =====================================================================
    print("\n--- Aggregating enriched TFs ---")
    top_tfs = _aggregate_enriched_tfs(
        enrichment_up, enrichment_down,
        max_tfs=max_tfs,
        min_qvalue=min_enrichment_qvalue,
    )

    if len(top_tfs) == 0:
        raise RuntimeError(
            f"No TFs passed enrichment threshold (q < {min_enrichment_qvalue}). "
            "Try relaxing the threshold or using more DE genes."
        )

    print(f"   Found {len(top_tfs)} enriched TFs to investigate")
    for _, row in top_tfs.head(5).iterrows():
        print(f"     {row['antigen']:12s}  q={row['best_qvalue']:.2e}  FE={row['best_fe']:.1f}  ({row['source']})")
    if len(top_tfs) > 5:
        print(f"     ... and {len(top_tfs) - 5} more")

    # =====================================================================
    # STEP 3: Download target gene lists for top TFs
    # =====================================================================
    print(f"\n--- Downloading target genes for {len(top_tfs)} TFs ---")
    print(f"   (Each download may take 1-2 min for popular TFs)")

    target_gene_data = {}
    for i, (_, tf_row) in enumerate(top_tfs.iterrows()):
        tf_name = tf_row["antigen"]
        print(f"\n   [{i+1}/{len(top_tfs)}] {tf_name}...")

        # Check availability
        if not check_antigen_available(tf_name, genome=genome, distance=distance):
            print(f"   Skipping {tf_name}: no target gene data available")
            continue

        try:
            summary_df, _ = download_target_genes(tf_name, genome=genome, distance=distance)
            target_gene_data[tf_name] = summary_df
        except Exception as e:
            print(f"   WARNING: Failed to download targets for {tf_name}: {e}")
            continue

    if len(target_gene_data) == 0:
        raise RuntimeError(
            "Could not download target gene data for any enriched TF. "
            "Check network connectivity and genome/distance parameters."
        )

    print(f"\n   Successfully downloaded targets for {len(target_gene_data)}/{len(top_tfs)} TFs")

    # =====================================================================
    # STEP 4: Score regulons (novel integration logic)
    # =====================================================================
    print("\n--- Scoring TF regulons ---")
    regulon_scores = score_regulons(
        top_tfs=top_tfs,
        target_gene_data=target_gene_data,
        de_data=de_data,
        min_targets_overlap=min_targets_overlap,
    )

    if len(regulon_scores) == 0:
        print("   WARNING: No TFs passed the scoring threshold.")
        print("   This may indicate low overlap between TF targets and DE genes.")

    # =====================================================================
    # Assemble results
    # =====================================================================
    parameters = {
        "genome": genome,
        "antigen_class": antigen_class,
        "cell_class": cell_class,
        "threshold": threshold,
        "distance_kb": distance,
        "max_tfs": max_tfs,
        "min_enrichment_qvalue": min_enrichment_qvalue,
        "min_targets_overlap": min_targets_overlap,
        "padj_threshold": de_data["thresholds"]["padj_threshold"],
        "log2fc_threshold": de_data["thresholds"]["log2fc_threshold"],
    }

    metadata = {
        "n_de_up": de_data["n_up"],
        "n_de_down": de_data["n_down"],
        "n_de_total": de_data["n_up"] + de_data["n_down"],
        "n_background": de_data["n_total"],
        "n_tfs_enriched": len(top_tfs),
        "n_tfs_with_targets": len(target_gene_data),
        "n_tfs_scored": len(regulon_scores),
    }

    results = {
        "regulon_scores": regulon_scores,
        "enrichment_results_up": enrichment_up,
        "enrichment_results_down": enrichment_down,
        "top_tfs": top_tfs,
        "target_gene_data": target_gene_data,
        "de_data": de_data,
        "parameters": parameters,
        "metadata": metadata,
    }

    print("\n✓ Integration analysis completed successfully!")
    print(f"  {len(regulon_scores)} TFs scored as upstream regulators")
    if len(regulon_scores) > 0:
        top = regulon_scores.iloc[0]
        print(f"  Top regulator: {top['tf']} (score={top['regulatory_score']:.1f}, {top['direction']})")

    return results


def _aggregate_enriched_tfs(enrichment_up, enrichment_down, max_tfs=10, min_qvalue=0.05):
    """
    Aggregate enriched TFs from up and down enrichment results.

    Takes the best q-value per unique TF across both directions.

    Returns
    -------
    pd.DataFrame
        Columns: antigen, best_qvalue, best_fe, source
    """
    records = []

    for source, enrichment in [("up", enrichment_up), ("down", enrichment_down)]:
        if enrichment is None:
            continue

        er = enrichment.get("enrichment_results")
        if er is None or len(er) == 0:
            continue

        # Group by antigen, take best (lowest) q-value per TF
        for antigen, group in er.groupby("antigen"):
            best_idx = group["q_value"].idxmin()
            records.append({
                "antigen": antigen,
                "best_qvalue": group.loc[best_idx, "q_value"],
                "best_fe": group.loc[best_idx, "fold_enrichment"],
                "source": source,
            })

    if not records:
        return pd.DataFrame(columns=["antigen", "best_qvalue", "best_fe", "source"])

    df = pd.DataFrame(records)

    # If a TF appears in both up and down, keep the better q-value but mark source as "both"
    if len(df) > 0:
        merged = []
        for antigen, group in df.groupby("antigen"):
            best_idx = group["best_qvalue"].idxmin()
            row = group.loc[best_idx].copy()
            if len(group) > 1:
                row["source"] = "both"
            merged.append(row)
        df = pd.DataFrame(merged)

    # Filter by q-value and take top N
    df = df[df["best_qvalue"] < min_qvalue]
    df = df.sort_values("best_qvalue").head(max_tfs).reset_index(drop=True)

    return df

