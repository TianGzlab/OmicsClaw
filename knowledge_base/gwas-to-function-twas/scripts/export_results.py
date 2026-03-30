"""
TWAS Results Export and Reporting

This module provides functions for generating comprehensive target reports
with genetic evidence, directionality, causality, and druggability.
"""

import pandas as pd
from pathlib import Path


def generate_target_report(twas_results, coloc_results, therapeutic_df,
                           mr_results=None, druggability_scores=None,
                           output_file="reports/target_report.xlsx"):
    """
    Generate comprehensive Excel report for biopharma target prioritization.

    Parameters
    ----------
    twas_results : pandas.DataFrame
        Full TWAS results
    coloc_results : pandas.DataFrame
        Colocalization results
    therapeutic_df : pandas.DataFrame
        Therapeutic directionality recommendations
    mr_results : pandas.DataFrame, optional
        Mendelian Randomization results
    druggability_scores : pandas.DataFrame, optional
        Druggability assessment
    output_file : str
        Output Excel file path

    Returns
    -------
    str
        Path to generated report
    """
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Generating comprehensive target report...")

    # Create Excel writer
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:

        # Sheet 1: Executive Summary
        executive_summary = create_executive_summary(
            therapeutic_df, coloc_results, druggability_scores, mr_results
        )
        executive_summary.to_excel(writer, sheet_name='Executive Summary', index=False)
        print("  ✓ Executive Summary")

        # Sheet 2: Full TWAS Results
        twas_results.to_excel(writer, sheet_name='TWAS Results', index=False)
        print("  ✓ TWAS Results")

        # Sheet 3: Colocalization Details
        coloc_results.to_excel(writer, sheet_name='Colocalization', index=False)
        print("  ✓ Colocalization")

        # Sheet 4: Therapeutic Directionality
        therapeutic_df.to_excel(writer, sheet_name='Directionality', index=False)
        print("  ✓ Therapeutic Directionality")

        # Sheet 5: Mendelian Randomization (if available)
        if mr_results is not None and not mr_results.empty:
            mr_results.to_excel(writer, sheet_name='Mendelian Randomization', index=False)
            print("  ✓ Mendelian Randomization")

        # Sheet 6: Druggability Assessment (if available)
        if druggability_scores is not None and not druggability_scores.empty:
            druggability_scores.to_excel(writer, sheet_name='Druggability', index=False)
            print("  ✓ Druggability")

    print(f"\nReport saved: {output_file}")
    return str(output_file)


def create_executive_summary(therapeutic_df, coloc_results, druggability_scores, mr_results):
    """
    Create executive summary sheet with top 20 prioritized targets.

    Parameters
    ----------
    therapeutic_df : pandas.DataFrame
        Therapeutic directionality
    coloc_results : pandas.DataFrame
        Colocalization results
    druggability_scores : pandas.DataFrame or None
        Druggability scores
    mr_results : pandas.DataFrame or None
        MR results

    Returns
    -------
    pandas.DataFrame
        Executive summary table
    """
    # Merge all data
    summary = therapeutic_df.copy()

    # Add colocalization
    if not coloc_results.empty:
        coloc_subset = coloc_results[['GENE', 'PP.H4']].rename(columns={'PP.H4': 'coloc_pp4'})
        summary = summary.merge(coloc_subset, left_on='gene', right_on='GENE', how='left')
        summary = summary.drop('GENE', axis=1, errors='ignore')

    # Add druggability
    if druggability_scores is not None and not druggability_scores.empty:
        summary = summary.merge(
            druggability_scores[['gene', 'druggability_score', 'druggability_tier', 'known_drugs']],
            on='gene',
            how='left'
        )

    # Add MR evidence
    if mr_results is not None and not mr_results.empty:
        mr_subset = mr_results[['gene', 'ivw_beta', 'ivw_pval']].rename(
            columns={'ivw_beta': 'mr_effect', 'ivw_pval': 'mr_pval'}
        )
        summary = summary.merge(mr_subset, on='gene', how='left')

    # Calculate priority score
    summary['priority_score'] = calculate_priority_score(summary)

    # Sort by priority and take top 20
    summary = summary.sort_values('priority_score', ascending=False).head(20)

    # Reorder columns
    column_order = [
        'gene', 'priority_score', 'therapeutic_strategy',
        'twas_pval', 'coloc_pp4', 'confidence',
        'druggability_tier', 'known_drugs'
    ]

    # Include only columns that exist
    column_order = [col for col in column_order if col in summary.columns]

    summary = summary[column_order]

    return summary


def calculate_priority_score(summary_df):
    """
    Calculate composite priority score for target ranking.

    Scoring components:
    - TWAS significance: 30%
    - Colocalization: 30%
    - Druggability: 25%
    - MR causal evidence: 15%

    Parameters
    ----------
    summary_df : pandas.DataFrame
        Summary dataframe with evidence columns

    Returns
    -------
    pandas.Series
        Priority scores (0-100)
    """
    scores = pd.Series(0.0, index=summary_df.index)

    # TWAS significance (30 points)
    if 'twas_pval' in summary_df.columns:
        twas_score = -pd.Series(summary_df['twas_pval']).apply(lambda x: min(-np.log10(x) / 10, 1))
        scores += twas_score * 30

    # Colocalization (30 points)
    if 'coloc_pp4' in summary_df.columns:
        scores += summary_df['coloc_pp4'].fillna(0) * 30

    # Druggability (25 points)
    if 'druggability_score' in summary_df.columns:
        scores += summary_df['druggability_score'].fillna(0.1) * 25

    # MR causal evidence (15 points)
    if 'mr_pval' in summary_df.columns:
        mr_score = summary_df['mr_pval'].apply(lambda x: 1 if pd.notna(x) and x < 0.05 else 0)
        scores += mr_score * 15

    return scores


def export_csv_summary(twas_results, output_file="results/twas_summary.csv"):
    """
    Export simplified CSV summary of TWAS results.

    Parameters
    ----------
    twas_results : pandas.DataFrame
        TWAS results
    output_file : str
        Output CSV file

    Returns
    -------
    str
        Path to CSV file
    """
    # Select key columns
    summary_cols = ['GENE', 'CHR', 'TISSUE', 'TWAS.Z', 'TWAS.P']
    summary_cols = [col for col in summary_cols if col in twas_results.columns]

    summary = twas_results[summary_cols].copy()

    # Add significance flag
    summary['Significant'] = summary['TWAS.P'] < (0.05 / len(twas_results))

    # Save
    summary.to_csv(output_file, index=False)
    print(f"CSV summary saved: {output_file}")

    return output_file


# Import numpy for priority score calculation
import numpy as np

