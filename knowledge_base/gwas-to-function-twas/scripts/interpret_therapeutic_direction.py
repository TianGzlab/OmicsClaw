"""
Interpret TWAS directionality for therapeutic strategy.

This module determines whether genes should be inhibited or activated
for therapeutic benefit based on the direction of expression-trait association.

Author: Claude Code (Anthropic)
Date: 2026-01-28
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Literal


def interpret_therapeutic_direction(
    gene: str,
    twas_z_or_beta: float,
    trait_direction: Literal["risk", "protective", "quantitative"] = "risk",
    trait_name: str = "Disease",
    confidence_level: str = "medium"
) -> Dict[str, str]:
    """
    Determine therapeutic strategy based on TWAS directionality.

    Parameters
    ----------
    gene : str
        Gene symbol
    twas_z_or_beta : float
        TWAS Z-score (FUSION) or effect size (S-PrediXcan)
        Positive: higher predicted expression → higher trait value
        Negative: higher predicted expression → lower trait value
    trait_direction : str
        "risk" (higher is bad, e.g., disease risk, LDL cholesterol)
        "protective" (higher is good)
        "quantitative" (neutral interpretation)
    trait_name : str
        Name of the trait for reporting
    confidence_level : str
        Confidence in the association ("high", "medium", "low")
        Based on colocalization, multi-layer consistency, etc.

    Returns
    -------
    dict
        Dictionary with therapeutic recommendation:
        - gene: Gene symbol
        - twas_effect: Direction of TWAS association
        - association: Human-readable association description
        - therapeutic_strategy: "INHIBIT" or "ACTIVATE"
        - drug_modality: Suggested drug types
        - rationale: Explanation for recommendation
        - confidence: Confidence level for the recommendation
        - caution: Any warnings or caveats

    Examples
    --------
    >>> # IL6R: higher expression increases CAD risk
    >>> interpret_therapeutic_direction("IL6R", twas_z_or_beta=4.5,
    ...                                   trait_direction="risk",
    ...                                   trait_name="Coronary Artery Disease")
    {'gene': 'IL6R',
     'therapeutic_strategy': 'INHIBIT',
     'association': 'Higher expression increases Coronary Artery Disease risk',
     'rationale': 'Reducing expression should reduce disease risk'}

    >>> # APOE: higher expression decreases AD risk (protective)
    >>> interpret_therapeutic_direction("APOE", twas_z_or_beta=-4.2,
    ...                                   trait_direction="risk",
    ...                                   trait_name="Alzheimer's Disease")
    {'gene': 'APOE',
     'therapeutic_strategy': 'ACTIVATE',
     'association': 'Higher expression decreases Alzheimer's Disease risk',
     'rationale': 'Increasing expression should reduce disease risk'}
    """

    result = {
        "gene": gene,
        "twas_effect": "positive" if twas_z_or_beta > 0 else "negative",
        "twas_z_or_beta": twas_z_or_beta,
        "trait_name": trait_name,
        "confidence": confidence_level
    }

    # Determine association and therapeutic strategy based on trait direction
    if trait_direction == "risk":
        if twas_z_or_beta > 0:
            # Positive TWAS: Higher expression → Higher risk
            result["association"] = f"Higher expression increases {trait_name} risk"
            result["therapeutic_strategy"] = "INHIBIT"
            result["drug_modality"] = "Inhibitor, antagonist, antibody, siRNA, antisense oligonucleotide"
            result["rationale"] = f"Reducing {gene} expression should reduce {trait_name} risk"
            result["mechanism"] = "Decrease gene expression to decrease disease risk"

        else:
            # Negative TWAS: Higher expression → Lower risk (protective)
            result["association"] = f"Higher expression decreases {trait_name} risk"
            result["therapeutic_strategy"] = "ACTIVATE"
            result["drug_modality"] = "Agonist, activator, gene therapy, overexpression"
            result["rationale"] = f"Increasing {gene} expression should reduce {trait_name} risk"
            result["mechanism"] = "Increase gene expression to decrease disease risk"

    elif trait_direction == "protective":
        if twas_z_or_beta > 0:
            # Positive TWAS: Higher expression → Higher protective outcome
            result["association"] = f"Higher expression increases {trait_name}"
            result["therapeutic_strategy"] = "ACTIVATE"
            result["drug_modality"] = "Agonist, activator, gene therapy, overexpression"
            result["rationale"] = f"Increasing {gene} expression should increase {trait_name}"
            result["mechanism"] = "Increase gene expression to increase protective outcome"

        else:
            # Negative TWAS: Higher expression → Lower protective outcome
            result["association"] = f"Higher expression decreases {trait_name}"
            result["therapeutic_strategy"] = "INHIBIT"
            result["drug_modality"] = "Inhibitor, antagonist, antibody, siRNA, antisense oligonucleotide"
            result["rationale"] = f"Reducing {gene} expression should increase {trait_name}"
            result["mechanism"] = "Decrease gene expression to increase protective outcome"

    elif trait_direction == "quantitative":
        # Neutral interpretation for quantitative traits (e.g., height, gene expression)
        direction_word = "increases" if twas_z_or_beta > 0 else "decreases"
        result["association"] = f"Higher expression {direction_word} {trait_name}"
        result["therapeutic_strategy"] = "CONTEXT-DEPENDENT"
        result["drug_modality"] = "Depends on desired outcome direction"
        result["rationale"] = f"Therapeutic strategy depends on whether increasing or decreasing {trait_name} is desired"
        result["mechanism"] = "Direction of intervention depends on clinical context"

    # Add cautions based on confidence level
    if confidence_level == "low":
        result["caution"] = "LOW CONFIDENCE: Association may be LD artifact. Requires colocalization validation."
    elif confidence_level == "medium":
        result["caution"] = "MEDIUM CONFIDENCE: Colocalization recommended to confirm shared causal variant."
    else:  # high
        result["caution"] = "HIGH CONFIDENCE: Association supported by colocalization and/or multi-layer analysis."

    # Add specific warnings for challenging drug modalities
    if result["therapeutic_strategy"] == "ACTIVATE":
        result["druggability_note"] = "Note: Activating gene expression is generally more challenging than inhibition. Consider agonists, gene therapy, or indirect pathway activation."

    return result


def batch_interpret_therapeutic_direction(
    twas_results: pd.DataFrame,
    gene_col: str = "GENE",
    z_col: str = "TWAS.Z",
    pval_col: str = "TWAS.P",
    coloc_pp4_col: str = "PP.H4",
    trait_direction: Literal["risk", "protective", "quantitative"] = "risk",
    trait_name: str = "Disease"
) -> pd.DataFrame:
    """
    Batch process multiple TWAS results for therapeutic interpretation.

    Parameters
    ----------
    twas_results : pd.DataFrame
        TWAS results dataframe with gene names and Z-scores
    gene_col : str
        Column name for gene symbols
    z_col : str
        Column name for TWAS Z-scores (or "effect" for S-PrediXcan beta)
    pval_col : str
        Column name for p-values (for significance filtering)
    coloc_pp4_col : str
        Column name for colocalization PP.H4 (optional)
    trait_direction : str
        "risk", "protective", or "quantitative"
    trait_name : str
        Name of the trait for reporting

    Returns
    -------
    pd.DataFrame
        DataFrame with therapeutic recommendations for each gene

    Examples
    --------
    >>> twas_df = pd.DataFrame({
    ...     'GENE': ['IL6R', 'PCSK9', 'SORT1'],
    ...     'TWAS.Z': [4.5, 3.8, -3.2],
    ...     'TWAS.P': [1e-6, 2e-5, 5e-4],
    ...     'PP.H4': [0.92, 0.88, 0.65]
    ... })
    >>> therapeutic_df = batch_interpret_therapeutic_direction(twas_df)
    """

    results = []

    for idx, row in twas_results.iterrows():
        gene = row[gene_col]
        twas_z = row[z_col]

        # Determine confidence level based on colocalization if available
        confidence = "medium"
        if coloc_pp4_col in row.index and pd.notna(row[coloc_pp4_col]):
            pp4 = row[coloc_pp4_col]
            if pp4 > 0.8:
                confidence = "high"
            elif pp4 < 0.5:
                confidence = "low"

        # Get therapeutic interpretation
        rec = interpret_therapeutic_direction(
            gene=gene,
            twas_z_or_beta=twas_z,
            trait_direction=trait_direction,
            trait_name=trait_name,
            confidence_level=confidence
        )

        # Add original TWAS statistics
        rec['twas_pvalue'] = row[pval_col] if pval_col in row.index else np.nan
        if coloc_pp4_col in row.index:
            rec['coloc_pp4'] = row[coloc_pp4_col] if pd.notna(row[coloc_pp4_col]) else np.nan

        results.append(rec)

    return pd.DataFrame(results)


def prioritize_targets(
    therapeutic_df: pd.DataFrame,
    weights: Dict[str, float] = None
) -> pd.DataFrame:
    """
    Prioritize drug targets based on genetic evidence and druggability.

    Parameters
    ----------
    therapeutic_df : pd.DataFrame
        DataFrame with therapeutic recommendations from batch_interpret_therapeutic_direction
    weights : dict, optional
        Weights for priority scoring. Default:
        {'twas_pvalue': 0.3, 'coloc_pp4': 0.3, 'mr_causal': 0.2, 'druggability': 0.2}

    Returns
    -------
    pd.DataFrame
        Sorted DataFrame with priority scores

    Examples
    --------
    >>> prioritized = prioritize_targets(therapeutic_df)
    >>> print(prioritized[['gene', 'therapeutic_strategy', 'priority_score']].head())
    """

    if weights is None:
        weights = {
            'twas_pvalue': 0.3,
            'coloc_pp4': 0.3,
            'mr_causal': 0.2,
            'druggability': 0.2
        }

    df = therapeutic_df.copy()

    # Calculate component scores (0-1 scale)

    # TWAS significance score
    if 'twas_pvalue' in df.columns:
        df['twas_score'] = -np.log10(df['twas_pvalue']) / 10  # Cap at -log10(p) = 10
        df['twas_score'] = df['twas_score'].clip(0, 1)
    else:
        df['twas_score'] = 0.5

    # Colocalization score (PP.H4 is already 0-1)
    if 'coloc_pp4' in df.columns:
        df['coloc_score'] = df['coloc_pp4'].fillna(0.5)
    else:
        df['coloc_score'] = 0.5

    # MR causal evidence score (if available)
    if 'mr_pvalue' in df.columns:
        df['mr_score'] = (-np.log10(df['mr_pvalue']) / 10).clip(0, 1)
    else:
        df['mr_score'] = 0.5  # Neutral if MR not performed

    # Druggability score (if available, should be 0-1)
    if 'druggability_score' in df.columns:
        df['drug_score'] = df['druggability_score']
    else:
        # Assign based on therapeutic strategy (inhibition easier than activation)
        df['drug_score'] = df['therapeutic_strategy'].map({
            'INHIBIT': 0.7,
            'ACTIVATE': 0.4,
            'CONTEXT-DEPENDENT': 0.3
        }).fillna(0.5)

    # Calculate weighted priority score
    df['priority_score'] = (
        df['twas_score'] * weights['twas_pvalue'] +
        df['coloc_score'] * weights['coloc_pp4'] +
        df['mr_score'] * weights['mr_causal'] +
        df['drug_score'] * weights['druggability']
    )

    # Sort by priority score (descending)
    df = df.sort_values('priority_score', ascending=False).reset_index(drop=True)

    # Assign priority rank
    df['priority_rank'] = range(1, len(df) + 1)

    return df


def export_therapeutic_summary(
    therapeutic_df: pd.DataFrame,
    output_file: str,
    top_n: int = 50
):
    """
    Export therapeutic recommendations to Excel with multiple sheets.

    Parameters
    ----------
    therapeutic_df : pd.DataFrame
        DataFrame with therapeutic recommendations and priority scores
    output_file : str
        Output Excel file path
    top_n : int
        Number of top targets to include in executive summary

    Examples
    --------
    >>> export_therapeutic_summary(prioritized_df,
    ...                             "CAD_Therapeutic_Targets.xlsx",
    ...                             top_n=20)
    """

    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        # Sheet 1: Executive Summary (Top N targets)
        exec_cols = ['priority_rank', 'gene', 'therapeutic_strategy',
                     'association', 'confidence', 'twas_pvalue',
                     'coloc_pp4', 'priority_score']
        available_cols = [col for col in exec_cols if col in therapeutic_df.columns]

        exec_summary = therapeutic_df.head(top_n)[available_cols]
        exec_summary.to_excel(writer, sheet_name='Executive_Summary', index=False)

        # Sheet 2: Full Results
        therapeutic_df.to_excel(writer, sheet_name='All_Targets', index=False)

        # Sheet 3: Inhibit targets only
        inhibit_targets = therapeutic_df[therapeutic_df['therapeutic_strategy'] == 'INHIBIT']
        inhibit_targets.to_excel(writer, sheet_name='Inhibit_Targets', index=False)

        # Sheet 4: Activate targets only
        activate_targets = therapeutic_df[therapeutic_df['therapeutic_strategy'] == 'ACTIVATE']
        activate_targets.to_excel(writer, sheet_name='Activate_Targets', index=False)

        # Sheet 5: High confidence only (if coloc data available)
        if 'confidence' in therapeutic_df.columns:
            high_conf = therapeutic_df[therapeutic_df['confidence'] == 'high']
            high_conf.to_excel(writer, sheet_name='High_Confidence', index=False)

    print(f"Therapeutic summary exported to {output_file}")
    print(f"  - Top {top_n} targets in Executive Summary sheet")
    print(f"  - {len(inhibit_targets)} INHIBIT targets")
    print(f"  - {len(activate_targets)} ACTIVATE targets")
    if 'confidence' in therapeutic_df.columns:
        print(f"  - {len(high_conf)} high-confidence targets")


if __name__ == "__main__":
    # Example usage
    print("Therapeutic Direction Interpretation Module")
    print("=" * 60)

    # Example 1: Single gene interpretation
    print("\nExample 1: IL6R (known CAD target)")
    il6r_rec = interpret_therapeutic_direction(
        gene="IL6R",
        twas_z_or_beta=4.52,
        trait_direction="risk",
        trait_name="Coronary Artery Disease",
        confidence_level="high"
    )

    print(f"Gene: {il6r_rec['gene']}")
    print(f"Association: {il6r_rec['association']}")
    print(f"Therapeutic Strategy: {il6r_rec['therapeutic_strategy']}")
    print(f"Rationale: {il6r_rec['rationale']}")
    print(f"Drug Modality: {il6r_rec['drug_modality']}")
    print(f"Confidence: {il6r_rec['confidence']}")

    # Example 2: Batch interpretation
    print("\n" + "=" * 60)
    print("Example 2: Batch interpretation of multiple genes")

    example_twas = pd.DataFrame({
        'GENE': ['IL6R', 'PCSK9', 'SORT1', 'APOE', 'LDLR'],
        'TWAS.Z': [4.52, 3.87, -3.21, -4.18, 3.56],
        'TWAS.P': [1.2e-6, 2.3e-5, 5.1e-4, 8.7e-6, 3.2e-5],
        'PP.H4': [0.92, 0.88, 0.65, 0.81, 0.73]
    })

    therapeutic_batch = batch_interpret_therapeutic_direction(
        example_twas,
        trait_direction="risk",
        trait_name="LDL Cholesterol"
    )

    print("\nTherapeutic recommendations:")
    print(therapeutic_batch[['gene', 'therapeutic_strategy',
                             'association', 'confidence']].to_string(index=False))

    # Example 3: Target prioritization
    print("\n" + "=" * 60)
    print("Example 3: Target prioritization")

    prioritized = prioritize_targets(therapeutic_batch)

    print("\nPrioritized targets:")
    print(prioritized[['priority_rank', 'gene', 'therapeutic_strategy',
                       'priority_score']].to_string(index=False))

