"""
Python wrapper for glmGamPoi batch-corrected differential expression

This script provides a Python interface to run glmGamPoi (R package) for
rigorous differential expression analysis with donor/batch correction.
"""

import subprocess
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional
import tempfile
import scanpy as sc


def run_glmgampoi_batch(
    adata,
    perturbations: List[str],
    control_group: str = 'non-targeting',
    donor_col: str = 'donor',
    gene_col: str = 'gene',
    min_expression: int = 100,
    output_dir: str = 'results/glmgampoi/',
    r_script_path: Optional[str] = None,
    verbose: bool = True
) -> Dict[str, pd.DataFrame]:
    """
    Run glmGamPoi via R subprocess for batch-corrected DE

    Parameters
    ----------
    adata : AnnData
        Annotated data object with RAW counts (not log-normalized)
    perturbations : list of str
        List of perturbations to test
    control_group : str
        Name of non-targeting control group
    donor_col : str
        Column in adata.obs containing donor/batch information
    gene_col : str
        Column in adata.obs containing perturbation identities
    min_expression : int
        Minimum total counts across all cells for gene to be included
    output_dir : str
        Directory to save results
    r_script_path : str, optional
        Path to run_glmgampoi.R script. If None, uses default location.
    verbose : bool
        Print progress messages

    Returns
    -------
    dict
        Dictionary mapping perturbation name to glmGamPoi results DataFrame
        Each DataFrame contains: gene, log2fc, pval, adj_pval, mean_expression
    """

    # Check for donor column
    if donor_col not in adata.obs.columns:
        raise ValueError(f"Donor column '{donor_col}' not found in adata.obs")

    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Set default R script path
    if r_script_path is None:
        script_dir = Path(__file__).parent
        r_script_path = script_dir / "run_glmgampoi.R"

    if not Path(r_script_path).exists():
        raise FileNotFoundError(f"R script not found: {r_script_path}")

    if verbose:
        print(f"Running glmGamPoi for {len(perturbations)} perturbations")
        print(f"Using donor/batch column: {donor_col}")
        print(f"Control group: {control_group}")

    # Save subset of adata for R to read (only relevant perturbations + controls)
    relevant_perts = perturbations + [control_group]
    adata_sub = adata[adata.obs[gene_col].isin(relevant_perts)].copy()

    # Create temporary file for data transfer
    with tempfile.NamedTemporaryFile(suffix='.h5ad', delete=False) as tmp:
        temp_h5ad = tmp.name
        if verbose:
            print(f"Saving temporary data to: {temp_h5ad}")
        adata_sub.write(temp_h5ad)

    try:
        # Call R script
        cmd = [
            'Rscript',
            str(r_script_path),
            temp_h5ad,
            ','.join(perturbations),
            control_group,
            gene_col,
            donor_col,
            str(min_expression),
            output_dir
        ]

        if verbose:
            print(f"Calling R script: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True
        )

        if verbose and result.stdout:
            print("R script output:")
            print(result.stdout)

        if result.stderr:
            print("R script warnings/errors:")
            print(result.stderr)

    except subprocess.CalledProcessError as e:
        print(f"Error running R script:")
        print(f"Return code: {e.returncode}")
        print(f"stdout: {e.stdout}")
        print(f"stderr: {e.stderr}")
        raise

    finally:
        # Clean up temporary file
        Path(temp_h5ad).unlink(missing_ok=True)

    # Read results
    results = {}
    for gene in perturbations:
        result_file = Path(output_dir) / f"{gene}_glmgampoi.csv"
        if result_file.exists():
            results[gene] = pd.read_csv(result_file)
            if verbose:
                n_sig = (results[gene]['adj_pval'] < 0.05).sum()
                print(f"  {gene}: {n_sig} significant genes")
        else:
            if verbose:
                print(f"  {gene}: No results file found (may have failed)")

    if verbose:
        print(f"\nCompleted: {len(results)} / {len(perturbations)} perturbations")

    return results


def run_glmgampoi_single(
    adata,
    perturbation: str,
    control_group: str = 'non-targeting',
    donor_col: str = 'donor',
    gene_col: str = 'gene',
    min_expression: int = 100,
    output_file: Optional[str] = None
) -> pd.DataFrame:
    """
    Run glmGamPoi for a single perturbation (convenience wrapper)

    Parameters
    ----------
    adata : AnnData
        Annotated data object with RAW counts
    perturbation : str
        Perturbation to test
    control_group : str
        Name of non-targeting control group
    donor_col : str
        Column containing donor/batch information
    gene_col : str
        Column containing perturbation identities
    min_expression : int
        Minimum total counts for gene inclusion
    output_file : str, optional
        Path to save results

    Returns
    -------
    pd.DataFrame
        glmGamPoi results for this perturbation
    """

    results = run_glmgampoi_batch(
        adata,
        perturbations=[perturbation],
        control_group=control_group,
        donor_col=donor_col,
        gene_col=gene_col,
        min_expression=min_expression,
        output_dir=Path(output_file).parent if output_file else 'results/glmgampoi/',
        verbose=False
    )

    de_df = results[perturbation]

    if output_file:
        de_df.to_csv(output_file, index=False)

    return de_df


def compare_ttest_vs_glmgampoi(
    ttest_results: Dict[str, pd.DataFrame],
    glmgampoi_results: Dict[str, pd.DataFrame],
    fdr_threshold: float = 0.05,
    output_file: str = 'results/method_comparison.csv'
):
    """
    Compare DE results from t-test vs glmGamPoi

    Parameters
    ----------
    ttest_results : dict
        DE results from t-test screening
    glmgampoi_results : dict
        DE results from glmGamPoi
    fdr_threshold : float
        FDR threshold for calling significance
    output_file : str
        Path to save comparison

    Returns
    -------
    pd.DataFrame
        Comparison summary
    """

    comparison = []

    for gene in glmgampoi_results.keys():
        if gene not in ttest_results:
            continue

        ttest_df = ttest_results[gene]
        glm_df = glmgampoi_results[gene]

        # Count significant genes in each method
        n_sig_ttest = (ttest_df['qval'] < fdr_threshold).sum()
        n_sig_glm = (glm_df['adj_pval'] < fdr_threshold).sum()

        # Find overlap
        sig_ttest = set(ttest_df[ttest_df['qval'] < fdr_threshold]['gene'])
        sig_glm = set(glm_df[glm_df['adj_pval'] < fdr_threshold]['gene'])
        n_overlap = len(sig_ttest & sig_glm)

        # Calculate agreement
        if n_sig_ttest > 0 and n_sig_glm > 0:
            agreement = n_overlap / max(n_sig_ttest, n_sig_glm)
        else:
            agreement = np.nan

        comparison.append({
            'perturbation': gene,
            'n_sig_ttest': n_sig_ttest,
            'n_sig_glmgampoi': n_sig_glm,
            'n_overlap': n_overlap,
            'agreement': agreement
        })

    comparison_df = pd.DataFrame(comparison)

    # Print summary
    print(f"\n{'='*60}")
    print(f"t-test vs glmGamPoi Comparison")
    print(f"{'='*60}")
    print(f"Perturbations compared: {len(comparison_df)}")
    print(f"\nMedian DE genes:")
    print(f"  t-test: {comparison_df['n_sig_ttest'].median():.0f}")
    print(f"  glmGamPoi: {comparison_df['n_sig_glmgampoi'].median():.0f}")
    print(f"\nMedian overlap: {comparison_df['n_overlap'].median():.0f}")
    print(f"Mean agreement: {comparison_df['agreement'].mean():.2%}")
    print(f"{'='*60}\n")

    # Save comparison
    comparison_df.to_csv(output_file, index=False)
    print(f"Comparison saved to: {output_file}")

    return comparison_df


if __name__ == "__main__":
    # Example usage
    import argparse

    parser = argparse.ArgumentParser(description='Run glmGamPoi batch-corrected DE')
    parser.add_argument('--adata', required=True, help='Path to AnnData h5ad file (RAW counts)')
    parser.add_argument('--perturbations', required=True, help='Comma-separated list of perturbations')
    parser.add_argument('--control', default='non-targeting', help='Control group name')
    parser.add_argument('--donor-col', default='donor', help='Donor/batch column')
    parser.add_argument('--gene-col', default='gene', help='Perturbation column')
    parser.add_argument('--min-expression', type=int, default=100, help='Min total expression')
    parser.add_argument('--output-dir', default='results/glmgampoi/', help='Output directory')
    parser.add_argument('--r-script', help='Path to run_glmgampoi.R')

    args = parser.parse_args()

    # Load data
    print(f"Loading data from {args.adata}...")
    adata = sc.read_h5ad(args.adata)

    # Parse perturbations list
    perturbations = [p.strip() for p in args.perturbations.split(',')]

    # Run glmGamPoi
    results = run_glmgampoi_batch(
        adata,
        perturbations=perturbations,
        control_group=args.control,
        donor_col=args.donor_col,
        gene_col=args.gene_col,
        min_expression=args.min_expression,
        output_dir=args.output_dir,
        r_script_path=args.r_script
    )

    print(f"\nglmGamPoi analysis complete for {len(results)} perturbations")

