"""
Variant Filtering Module

This module provides functions for filtering annotated variants by consequence,
frequency, quality, and pathogenicity.
"""

import sys

try:
    import pandas as pd
    import numpy as np
except ImportError as e:
    print(f"Error: Missing required package: {e}")
    print("Install with: pip install pandas numpy")
    sys.exit(1)


# Consequence severity definitions (Sequence Ontology)
HIGH_IMPACT_CONSEQUENCES = {
    'transcript_ablation',
    'splice_acceptor_variant',
    'splice_donor_variant',
    'stop_gained',
    'frameshift_variant',
    'stop_lost',
    'start_lost',
    'transcript_amplification'
}

MODERATE_IMPACT_CONSEQUENCES = {
    'inframe_insertion',
    'inframe_deletion',
    'missense_variant',
    'protein_altering_variant'
}

LOW_IMPACT_CONSEQUENCES = {
    'splice_region_variant',
    'incomplete_terminal_codon_variant',
    'start_retained_variant',
    'stop_retained_variant',
    'synonymous_variant'
}


def filter_by_consequence(df, impact=None, consequence_types=None):
    """
    Filter variants by consequence severity or specific consequence types.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with variant annotations
    impact : list, optional
        List of impact levels to keep: ['HIGH', 'MODERATE', 'LOW', 'MODIFIER']
    consequence_types : list, optional
        List of specific consequence types to keep

    Returns
    -------
    pd.DataFrame
        Filtered DataFrame
    """
    filtered = df.copy()

    # Filter by IMPACT
    if impact:
        if 'IMPACT' not in df.columns:
            print("Warning: IMPACT column not found")
            return filtered

        filtered = filtered[filtered['IMPACT'].isin(impact)]

    # Filter by specific consequence types
    if consequence_types:
        if 'Consequence' not in df.columns:
            print("Warning: Consequence column not found")
            return filtered

        # Consequence can be multi-valued (e.g., "missense_variant&splice_region_variant")
        def has_consequence(cons_str, target_consequences):
            if pd.isna(cons_str):
                return False
            consequences = set(c.strip() for c in str(cons_str).split('&'))
            return bool(consequences.intersection(target_consequences))

        target_set = set(consequence_types)
        mask = filtered['Consequence'].apply(lambda x: has_consequence(x, target_set))
        filtered = filtered[mask]

    return filtered


def filter_by_frequency(df, max_af=0.01, population='gnomAD_AF', missing_as_rare=True):
    """
    Filter variants by population allele frequency.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with variant annotations
    max_af : float
        Maximum allele frequency threshold (default: 0.01 = 1%)
    population : str
        Population frequency field name (default: 'gnomAD_AF')
    missing_as_rare : bool
        Treat variants with missing frequency as rare (default: True)

    Returns
    -------
    pd.DataFrame
        Filtered DataFrame with rare variants
    """
    if population not in df.columns:
        print(f"Warning: {population} column not found")
        return df

    filtered = df.copy()

    # Convert frequency to numeric
    filtered[population] = pd.to_numeric(filtered[population], errors='coerce')

    if missing_as_rare:
        # Keep variants with freq <= max_af OR missing freq
        mask = (filtered[population] <= max_af) | (filtered[population].isna())
    else:
        # Keep only variants with freq <= max_af (drop missing)
        mask = filtered[population] <= max_af

    filtered = filtered[mask]

    return filtered


def filter_by_pathogenicity(
    df,
    sift=None,
    polyphen=None,
    cadd_threshold=None,
    revel_threshold=None,
    clinvar=None,
    require_all=False
):
    """
    Filter variants by pathogenicity predictions.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with variant annotations
    sift : str, optional
        SIFT prediction: 'deleterious' or 'tolerated'
    polyphen : str, optional
        PolyPhen prediction: 'probably_damaging', 'possibly_damaging', 'benign'
    cadd_threshold : float, optional
        Minimum CADD score (typically > 20 for pathogenic)
    revel_threshold : float, optional
        Minimum REVEL score (typically > 0.5 for pathogenic)
    clinvar : list, optional
        ClinVar significance values: ['Pathogenic', 'Likely_pathogenic']
    require_all : bool
        Require ALL pathogenicity criteria (AND logic) vs ANY (OR logic)

    Returns
    -------
    pd.DataFrame
        Filtered DataFrame with potentially pathogenic variants
    """
    masks = []

    # SIFT filter
    if sift and 'SIFT' in df.columns:
        if sift == 'deleterious':
            # SIFT score < 0.05 or prediction contains 'deleterious'
            sift_mask = df['SIFT'].str.contains('deleterious', case=False, na=False)
        else:
            sift_mask = df['SIFT'].str.contains('tolerated', case=False, na=False)
        masks.append(sift_mask)

    # PolyPhen filter
    if polyphen and 'PolyPhen' in df.columns:
        polyphen_mask = df['PolyPhen'].str.contains(polyphen, case=False, na=False)
        masks.append(polyphen_mask)

    # CADD filter
    if cadd_threshold and 'CADD_PHRED' in df.columns:
        df['CADD_PHRED'] = pd.to_numeric(df['CADD_PHRED'], errors='coerce')
        cadd_mask = df['CADD_PHRED'] >= cadd_threshold
        masks.append(cadd_mask)

    # REVEL filter
    if revel_threshold and 'REVEL' in df.columns:
        df['REVEL'] = pd.to_numeric(df['REVEL'], errors='coerce')
        revel_mask = df['REVEL'] >= revel_threshold
        masks.append(revel_mask)

    # ClinVar filter
    if clinvar and 'CLIN_SIG' in df.columns:
        clinvar_mask = df['CLIN_SIG'].isin(clinvar)
        masks.append(clinvar_mask)

    # Combine masks
    if not masks:
        return df

    if require_all:
        # AND logic: all criteria must be met
        combined_mask = masks[0]
        for mask in masks[1:]:
            combined_mask = combined_mask & mask
    else:
        # OR logic: any criterion can be met
        combined_mask = masks[0]
        for mask in masks[1:]:
            combined_mask = combined_mask | mask

    return df[combined_mask]


def filter_by_quality(df, min_qual=30, require_pass=True):
    """
    Filter variants by quality metrics.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with variant annotations
    min_qual : float
        Minimum QUAL score (default: 30)
    require_pass : bool
        Require FILTER = PASS (default: True)

    Returns
    -------
    pd.DataFrame
        Filtered DataFrame
    """
    filtered = df.copy()

    # Filter by QUAL
    if 'QUAL' in df.columns and min_qual:
        filtered['QUAL'] = pd.to_numeric(filtered['QUAL'], errors='coerce')
        filtered = filtered[filtered['QUAL'] >= min_qual]

    # Filter by FILTER field
    if require_pass and 'FILTER' in df.columns:
        filtered = filtered[filtered['FILTER'].isin(['PASS', '.'])]

    return filtered


def filter_coding_variants(df):
    """
    Filter to coding variants only (exonic + splice sites).

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with variant annotations

    Returns
    -------
    pd.DataFrame
        Filtered DataFrame with coding variants only
    """
    coding_consequences = (
        HIGH_IMPACT_CONSEQUENCES |
        MODERATE_IMPACT_CONSEQUENCES |
        LOW_IMPACT_CONSEQUENCES |
        {'splice_region_variant'}
    )

    return filter_by_consequence(df, consequence_types=list(coding_consequences))


def filter_high_confidence(
    df,
    max_af=0.01,
    min_cadd=20,
    impact_levels=['HIGH', 'MODERATE']
):
    """
    Apply high-confidence filtering for clinical analysis.

    Combines multiple filters:
    - Rare variants (gnomAD AF < 1%)
    - High or moderate impact
    - CADD score > 20

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with variant annotations
    max_af : float
        Maximum allele frequency (default: 0.01)
    min_cadd : float
        Minimum CADD score (default: 20)
    impact_levels : list
        Impact levels to keep (default: ['HIGH', 'MODERATE'])

    Returns
    -------
    pd.DataFrame
        Filtered DataFrame
    """
    # Start with all variants
    filtered = df.copy()

    # Filter by impact
    filtered = filter_by_consequence(filtered, impact=impact_levels)

    # Filter by frequency
    if 'gnomAD_AF' in filtered.columns:
        filtered = filter_by_frequency(filtered, max_af=max_af, population='gnomAD_AF')

    # Filter by CADD
    if 'CADD_PHRED' in filtered.columns:
        filtered = filter_by_pathogenicity(filtered, cadd_threshold=min_cadd)

    return filtered


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Filter annotated variants')
    parser.add_argument('input_csv', help='Input CSV file with annotations')
    parser.add_argument('output_csv', help='Output CSV file with filtered variants')
    parser.add_argument('--impact', nargs='+', choices=['HIGH', 'MODERATE', 'LOW', 'MODIFIER'],
                        help='Filter by impact levels')
    parser.add_argument('--max-af', type=float, default=0.01,
                        help='Maximum allele frequency (default: 0.01)')
    parser.add_argument('--min-cadd', type=float,
                        help='Minimum CADD score')
    parser.add_argument('--high-confidence', action='store_true',
                        help='Apply high-confidence filtering preset')

    args = parser.parse_args()

    # Load data
    df = pd.read_csv(args.input_csv)
    print(f"Loaded {len(df)} variants")

    # Apply filters
    if args.high_confidence:
        filtered = filter_high_confidence(df)
    else:
        filtered = df.copy()

        if args.impact:
            filtered = filter_by_consequence(filtered, impact=args.impact)
            print(f"After impact filter: {len(filtered)} variants")

        if args.max_af:
            filtered = filter_by_frequency(filtered, max_af=args.max_af)
            print(f"After frequency filter: {len(filtered)} variants")

        if args.min_cadd:
            filtered = filter_by_pathogenicity(filtered, cadd_threshold=args.min_cadd)
            print(f"After CADD filter: {len(filtered)} variants")

    # Save filtered variants
    filtered.to_csv(args.output_csv, index=False)
    print(f"\nWrote {len(filtered)} filtered variants to {args.output_csv}")

