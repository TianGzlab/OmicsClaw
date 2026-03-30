"""
Complete pySCENIC GRN inference workflow.

This script runs the full SCENIC pipeline:
1. GRN inference with GRNBoost2
2. Module creation
3. cisTarget motif pruning
4. AUCell activity scoring

All steps are integrated with proper verification messages.
"""

import os
import glob
import pickle
import pandas as pd
from arboreto.algo import grnboost2
from arboreto.utils import load_tf_names
from pyscenic.utils import modules_from_adjacencies
from pyscenic.prune import prune2df, df2regulons
from pyscenic.aucell import aucell
from ctxcore.rnkdb import FeatherRankingDatabase as RankingDatabase


def run_complete_grn_workflow(ex_matrix, tf_list_file, database_glob,
                               motif_annotations_file, output_dir="scenic_results",
                               n_workers=4, seed=42):
    """
    Run complete pySCENIC workflow from expression matrix to regulon activities.

    This function integrates all SCENIC steps:
    - GRNBoost2 for co-expression inference
    - Module creation
    - cisTarget motif-based pruning
    - AUCell activity scoring

    Parameters:
    -----------
    ex_matrix : pd.DataFrame
        Expression matrix (cells x genes)
    tf_list_file : str
        Path to TF list file (one TF per line)
    database_glob : str
        Glob pattern for cisTarget ranking databases (e.g., "databases/*.feather")
    motif_annotations_file : str
        Path to motif annotations (.tbl file)
    output_dir : str
        Directory to save intermediate and final results
    n_workers : int
        Number of parallel workers (default: 4)
    seed : int
        Random seed for reproducibility (default: 42)

    Returns:
    --------
    dict with keys:
        - 'adjacencies': Raw TF-target adjacencies from GRNBoost2
        - 'modules': Modules before motif pruning
        - 'regulons': Final regulons after motif pruning
        - 'auc_matrix': AUCell activity matrix (cells x regulons)
        - 'auc_summary': Summary statistics per regulon
        - 'motif_enrichment': Motif enrichment details

    Examples:
    ---------
    >>> results = run_complete_grn_workflow(
    ...     ex_matrix=ex_matrix,
    ...     tf_list_file="allTFs_hg38.txt",
    ...     database_glob="databases/*.feather",
    ...     motif_annotations_file="motifs.tbl",
    ...     output_dir="scenic_results"
    ... )
    """
    os.makedirs(output_dir, exist_ok=True)

    # Step 1: GRN Inference with GRNBoost2
    print("\n=== Step 1: GRN Inference (GRNBoost2) ===")
    print(f"Loading TF list from: {tf_list_file}")

    tf_names = load_tf_names(tf_list_file)
    tf_names = [tf for tf in tf_names if tf in ex_matrix.columns]
    print(f"  Using {len(tf_names)} TFs present in expression data")

    print("  Running GRNBoost2 (this may take 10-60 minutes)...")
    adjacencies = grnboost2(
        expression_data=ex_matrix,
        tf_names=tf_names,
        verbose=True,
        seed=seed
    )

    adjacencies_file = os.path.join(output_dir, "adjacencies.csv")
    adjacencies.to_csv(adjacencies_file, index=False)
    print(f"  Saved: {adjacencies_file}")
    print(f"✓ GRN inference completed: {len(adjacencies)} TF-target pairs")

    # Step 2: Create Modules
    print("\n=== Step 2: Module Creation ===")
    print("  Creating modules from adjacencies...")
    modules = list(modules_from_adjacencies(adjacencies, ex_matrix))

    modules_file = os.path.join(output_dir, "modules.pkl")
    with open(modules_file, "wb") as f:
        pickle.dump(modules, f)
    print(f"  Saved: {modules_file}")
    print(f"✓ Module creation completed: {len(modules)} modules")

    # Step 3: cisTarget Motif Pruning
    print("\n=== Step 3: cisTarget Motif Pruning ===")
    db_fnames = glob.glob(database_glob)
    if not db_fnames:
        raise ValueError(f"No databases found matching pattern: {database_glob}")

    print(f"  Loading {len(db_fnames)} ranking databases...")
    dbs = [RankingDatabase(fname=fname, name=os.path.basename(fname))
           for fname in db_fnames]

    print(f"  Loading motif annotations from: {motif_annotations_file}")
    print("  Running cisTarget motif enrichment (this may take 30-120 minutes)...")

    motif_df = prune2df(dbs, modules, motif_annotations_file)
    regulons = df2regulons(motif_df)

    regulons_file = os.path.join(output_dir, "regulons.pkl")
    with open(regulons_file, "wb") as f:
        pickle.dump(regulons, f)
    print(f"  Saved: {regulons_file}")

    # Save human-readable format
    regulon_data = []
    for regulon in regulons:
        for target, weight in regulon.gene2weight.items():
            regulon_data.append({
                'TF': regulon.transcription_factor,
                'target': target,
                'weight': weight,
                'regulon_name': regulon.name
            })

    regulon_df = pd.DataFrame(regulon_data)
    regulons_csv = os.path.join(output_dir, "regulons.csv")
    regulon_df.to_csv(regulons_csv, index=False)
    print(f"  Saved: {regulons_csv}")
    print(f"✓ cisTarget pruning completed: {len(regulons)} regulons")

    # Step 4: AUCell Scoring
    print("\n=== Step 4: AUCell Activity Scoring ===")
    print(f"  Calculating AUCell scores for {len(regulons)} regulons...")

    auc_matrix = aucell(ex_matrix, regulons, num_workers=n_workers)

    auc_matrix_file = os.path.join(output_dir, "aucell_matrix.csv")
    auc_matrix.to_csv(auc_matrix_file)
    print(f"  Saved: {auc_matrix_file}")

    # Calculate summary statistics
    auc_summary = pd.DataFrame({
        'regulon': auc_matrix.columns,
        'mean_activity': auc_matrix.mean(),
        'std_activity': auc_matrix.std(),
        'max_activity': auc_matrix.max(),
        'n_active_cells': (auc_matrix > auc_matrix.mean()).sum()
    })
    auc_summary = auc_summary.sort_values('mean_activity', ascending=False)

    auc_summary_file = os.path.join(output_dir, "aucell_summary.csv")
    auc_summary.to_csv(auc_summary_file, index=False)
    print(f"  Saved: {auc_summary_file}")
    print(f"✓ AUCell scoring completed")

    print("\n=== pySCENIC Workflow Complete ===")
    print(f"Results saved to: {output_dir}")
    print(f"  - {len(regulons)} regulons identified")
    print(f"  - {auc_matrix.shape[0]} cells scored")
    print(f"  - {auc_matrix.shape[1]} regulon activities calculated")

    return {
        'adjacencies': adjacencies,
        'modules': modules,
        'regulons': regulons,
        'auc_matrix': auc_matrix,
        'auc_summary': auc_summary,
        'motif_enrichment': motif_df
    }

