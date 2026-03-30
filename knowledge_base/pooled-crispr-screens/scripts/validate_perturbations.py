"""
Validate that perturbations affected their target genes

This is a critical QC step to filter out ineffective sgRNAs and ensure
perturbation quality before downstream analysis.
"""

import pandas as pd
import numpy as np
from typing import Dict, Literal
from pathlib import Path


def validate_target_effect(
    de_results: Dict[str, pd.DataFrame],
    expected_direction: Literal['down', 'up'] = 'down',
    min_log2fc: float = -0.5,
    max_pval: float = 0.05,
    verbose: bool = True
) -> pd.DataFrame:
    """
    Check if target gene was modulated in expected direction

    Parameters
    ----------
    de_results : dict
        Dictionary of DE results from screen_all_perturbations
        Keys are perturbation names, values are DE DataFrames
    expected_direction : str
        Expected direction of target effect:
        - 'down' for CRISPRi (knockdown)
        - 'up' for CRISPRa (activation)
    min_log2fc : float
        Minimum log2 fold-change threshold
        - For CRISPRi (down): negative value, e.g., -0.5 for 50% reduction
        - For CRISPRa (up): positive value, e.g., 0.5 for 1.4x increase
    max_pval : float
        Maximum p-value for target gene effect
    verbose : bool
        Print validation statistics

    Returns
    -------
    pd.DataFrame
        Validation results with columns:
        - perturbation: perturbation name
        - target_affected: bool, whether target was modulated
        - target_log2fc: log2FC of target gene
        - target_pval: p-value for target gene
        - reason: explanation (valid, target_not_measured, insufficient_effect, wrong_direction)
    """

    validation = []

    for gene, de_df in de_results.items():
        # Check if target gene is measured
        if gene not in de_df['gene'].values:
            validation.append({
                'perturbation': gene,
                'target_affected': False,
                'target_log2fc': np.nan,
                'target_pval': np.nan,
                'reason': 'target_not_measured'
            })
            continue

        # Get target gene DE results
        target_row = de_df[de_df['gene'] == gene].iloc[0]
        log2fc = target_row['log2fc']
        pval = target_row['pval']

        # Check if effect is significant and in expected direction
        if expected_direction == 'down':
            # For CRISPRi, expect negative log2FC
            effect_significant = (log2fc < min_log2fc) and (pval < max_pval)
            if not effect_significant:
                if log2fc >= 0:
                    reason = 'wrong_direction_upregulated'
                elif pval >= max_pval:
                    reason = 'not_significant'
                else:
                    reason = 'insufficient_effect'
            else:
                reason = 'valid'

        elif expected_direction == 'up':
            # For CRISPRa, expect positive log2FC
            effect_significant = (log2fc > min_log2fc) and (pval < max_pval)
            if not effect_significant:
                if log2fc <= 0:
                    reason = 'wrong_direction_downregulated'
                elif pval >= max_pval:
                    reason = 'not_significant'
                else:
                    reason = 'insufficient_effect'
            else:
                reason = 'valid'
        else:
            raise ValueError(f"Invalid direction: {expected_direction}. Must be 'down' or 'up'")

        validation.append({
            'perturbation': gene,
            'target_affected': effect_significant,
            'target_log2fc': log2fc,
            'target_pval': pval,
            'reason': reason
        })

    validation_df = pd.DataFrame(validation)

    # Print summary statistics
    if verbose:
        n_total = len(validation_df)
        n_valid = (validation_df['target_affected']).sum()
        n_not_measured = (validation_df['reason'] == 'target_not_measured').sum()
        n_insufficient = (validation_df['reason'] == 'insufficient_effect').sum()
        n_not_sig = (validation_df['reason'] == 'not_significant').sum()
        n_wrong_dir = validation_df['reason'].str.startswith('wrong_direction').sum()

        print(f"\n{'='*60}")
        print(f"Target Gene Validation Summary")
        print(f"{'='*60}")
        print(f"Screen type: CRISPRi" if expected_direction == 'down' else f"Screen type: CRISPRa")
        print(f"Total perturbations: {n_total}")
        print(f"\nValidation results:")
        print(f"  ✓ Valid (target affected): {n_valid} ({n_valid/n_total*100:.1f}%)")
        print(f"  ✗ Target not measured: {n_not_measured} ({n_not_measured/n_total*100:.1f}%)")
        print(f"  ✗ Insufficient effect: {n_insufficient} ({n_insufficient/n_total*100:.1f}%)")
        print(f"  ✗ Not significant: {n_not_sig} ({n_not_sig/n_total*100:.1f}%)")
        print(f"  ✗ Wrong direction: {n_wrong_dir} ({n_wrong_dir/n_total*100:.1f}%)")

        print(f"\nValidation rate: {n_valid/n_total*100:.1f}%")

        # Interpret validation rate
        validation_rate = n_valid/n_total*100
        if validation_rate >= 60:
            print("  ✓ Good library quality")
        elif validation_rate >= 50:
            print("  ⚠ Acceptable library quality")
        else:
            print("  ✗ Poor library quality - check sgRNA design, MOI, or selection")

        # Statistics on target log2FC (for valid perturbations only)
        valid_df = validation_df[validation_df['target_affected']]
        if len(valid_df) > 0:
            print(f"\nTarget gene log2FC distribution (valid perturbations):")
            print(f"  Median: {valid_df['target_log2fc'].median():.2f}")
            print(f"  Mean: {valid_df['target_log2fc'].mean():.2f}")
            print(f"  Range: [{valid_df['target_log2fc'].min():.2f}, {valid_df['target_log2fc'].max():.2f}]")

            if expected_direction == 'down':
                print(f"\n  Strong knockdown (log2FC < -1.0): {(valid_df['target_log2fc'] < -1.0).sum()}")
                print(f"  Moderate knockdown (-1.0 < log2FC < -0.5): {((valid_df['target_log2fc'] >= -1.0) & (valid_df['target_log2fc'] < -0.5)).sum()}")
            else:
                print(f"\n  Strong activation (log2FC > 2.0): {(valid_df['target_log2fc'] > 2.0).sum()}")
                print(f"  Moderate activation (1.0 < log2FC < 2.0): {((valid_df['target_log2fc'] >= 1.0) & (valid_df['target_log2fc'] < 2.0)).sum()}")

        print(f"{'='*60}\n")

    return validation_df


def filter_to_validated_perturbations(
    de_results: Dict[str, pd.DataFrame],
    validation_df: pd.DataFrame,
    output_dir: str = 'results/validated_perturbations/'
) -> Dict[str, pd.DataFrame]:
    """
    Filter DE results to only validated perturbations

    Parameters
    ----------
    de_results : dict
        Dictionary of DE results from screen_all_perturbations
    validation_df : pd.DataFrame
        Validation results from validate_target_effect
    output_dir : str
        Directory to save filtered results

    Returns
    -------
    dict
        Filtered dictionary containing only validated perturbations
    """

    # Get list of validated perturbations
    validated_genes = validation_df[validation_df['target_affected']]['perturbation'].tolist()

    # Filter DE results
    filtered_results = {gene: de_results[gene] for gene in validated_genes if gene in de_results}

    print(f"Filtered from {len(de_results)} to {len(filtered_results)} validated perturbations")

    # Save filtered results
    if output_dir:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        for gene, de_df in filtered_results.items():
            output_file = Path(output_dir) / f"{gene}_validated.csv"
            de_df.to_csv(output_file, index=False)

    return filtered_results


def generate_validation_report(
    validation_df: pd.DataFrame,
    output_file: str = 'results/validation_report.txt'
):
    """
    Generate detailed validation report

    Parameters
    ----------
    validation_df : pd.DataFrame
        Validation results from validate_target_effect
    output_file : str
        Path to save report
    """

    # Create detailed report
    report = f"""
CRISPR Screen Target Gene Validation Report
============================================

Total perturbations: {len(validation_df)}

Validation Status:
------------------
"""

    for reason, count in validation_df['reason'].value_counts().items():
        pct = count / len(validation_df) * 100
        report += f"  {reason}: {count} ({pct:.1f}%)\n"

    # List perturbations by category
    report += "\n\nValid Perturbations (target affected):\n"
    report += "-" * 40 + "\n"
    valid = validation_df[validation_df['target_affected']].sort_values('target_log2fc')
    for _, row in valid.iterrows():
        report += f"  {row['perturbation']:20s}  log2FC = {row['target_log2fc']:6.2f}  p = {row['target_pval']:.2e}\n"

    report += "\n\nFailed Validation (by reason):\n"
    report += "-" * 40 + "\n"
    failed = validation_df[~validation_df['target_affected']]
    for reason in failed['reason'].unique():
        reason_perts = failed[failed['reason'] == reason]['perturbation'].tolist()
        report += f"\n{reason} ({len(reason_perts)}):\n"
        for pert in reason_perts[:20]:  # Limit to first 20
            report += f"  - {pert}\n"
        if len(reason_perts) > 20:
            report += f"  ... and {len(reason_perts) - 20} more\n"

    # Save report
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w') as f:
        f.write(report)

    print(f"Validation report saved to: {output_file}")


if __name__ == "__main__":
    # Example usage
    import argparse
    from screen_all_perturbations import screen_all_perturbations
    import scanpy as sc

    parser = argparse.ArgumentParser(description='Validate target gene perturbations')
    parser.add_argument('--adata', help='Path to AnnData h5ad file (if running full pipeline)')
    parser.add_argument('--de-results-dir', help='Directory with DE results CSVs')
    parser.add_argument('--direction', choices=['down', 'up'], required=True,
                        help='Expected direction (down=CRISPRi, up=CRISPRa)')
    parser.add_argument('--min-log2fc', type=float, help='Minimum |log2FC| threshold')
    parser.add_argument('--output-dir', default='results/', help='Output directory')

    args = parser.parse_args()

    # Set default log2FC threshold based on direction
    if args.min_log2fc is None:
        args.min_log2fc = -0.5 if args.direction == 'down' else 0.5

    # Load DE results
    if args.de_results_dir:
        # Load from saved CSV files
        de_results = {}
        for csv_file in Path(args.de_results_dir).glob("*_ttest.csv"):
            gene = csv_file.stem.replace('_ttest', '')
            de_results[gene] = pd.read_csv(csv_file)
        print(f"Loaded DE results for {len(de_results)} perturbations")

    elif args.adata:
        # Run full screening pipeline
        print(f"Loading data from {args.adata}...")
        adata = sc.read_h5ad(args.adata)
        de_results = screen_all_perturbations(adata)
    else:
        raise ValueError("Must provide either --adata or --de-results-dir")

    # Validate target effects
    validation_df = validate_target_effect(
        de_results,
        expected_direction=args.direction,
        min_log2fc=args.min_log2fc
    )

    # Save validation results
    output_file = Path(args.output_dir) / "validation_results.csv"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    validation_df.to_csv(output_file, index=False)
    print(f"Validation results saved to: {output_file}")

    # Generate detailed report
    generate_validation_report(
        validation_df,
        output_file=Path(args.output_dir) / "validation_report.txt"
    )

