"""
SNPEff Output Parser Module

This module provides functions for parsing SNPEff-annotated VCF files into pandas DataFrames.
"""

import sys
from collections import defaultdict

try:
    import pandas as pd
    import cyvcf2
except ImportError as e:
    print(f"Error: Missing required package: {e}")
    print("Install with: pip install pandas cyvcf2")
    sys.exit(1)


def parse_snpeff_ann_header(vcf):
    """
    Parse SNPEff ANN field format from VCF header.

    Parameters
    ----------
    vcf : cyvcf2.VCF
        VCF object with SNPEff annotations

    Returns
    -------
    list
        List of ANN field names
    """
    # Find ANN INFO field in header
    ann_info = vcf.get_header_type('ANN')

    if not ann_info:
        raise ValueError("VCF does not contain SNPEff ANN annotations")

    # Standard ANN format (SNPEff 4.0+)
    # Format: Allele | Annotation | Annotation_Impact | Gene_Name | Gene_ID | Feature_Type |
    #         Feature_ID | Transcript_BioType | Rank | HGVS.c | HGVS.p | cDNA_pos | CDS_pos |
    #         AA_pos | Distance | ERRORS / WARNINGS / INFO

    # Parse from description if available
    description = ann_info.get('Description', '')

    if 'Functional annotations:' in description:
        # Extract format from description
        format_start = description.find("'")
        format_end = description.find("'", format_start + 1)
        if format_start != -1 and format_end != -1:
            format_str = description[format_start + 1:format_end]
            field_names = [f.strip() for f in format_str.split('|')]
            return field_names

    # Default ANN field names (SNPEff standard)
    default_fields = [
        'Allele',
        'Annotation',
        'Annotation_Impact',
        'Gene_Name',
        'Gene_ID',
        'Feature_Type',
        'Feature_ID',
        'Transcript_BioType',
        'Rank',
        'HGVS.c',
        'HGVS.p',
        'cDNA_pos',
        'CDS_pos',
        'AA_pos',
        'Distance',
        'ERRORS'
    ]

    return default_fields


def parse_snpeff_vcf(vcf_path, most_severe_only=False):
    """
    Parse SNPEff-annotated VCF into pandas DataFrame.

    Parameters
    ----------
    vcf_path : str
        Path to SNPEff-annotated VCF file
    most_severe_only : bool
        Extract only most severe consequence per variant (default: False)

    Returns
    -------
    pd.DataFrame
        DataFrame with variant annotations
    """
    vcf = cyvcf2.VCF(str(vcf_path))

    # Parse ANN field format
    try:
        ann_fields = parse_snpeff_ann_header(vcf)
    except ValueError as e:
        raise ValueError(f"Cannot parse SNPEff annotations: {e}")

    # Parse variants
    records = []

    for variant in vcf:
        # Base variant info
        base_info = {
            'CHROM': variant.CHROM,
            'POS': variant.POS,
            'ID': variant.ID if variant.ID else '.',
            'REF': variant.REF,
            'ALT': ','.join(str(a) for a in variant.ALT),
            'QUAL': variant.QUAL,
            'FILTER': variant.FILTER or 'PASS'
        }

        # Get ANN annotations
        ann_data = variant.INFO.get('ANN')

        if not ann_data:
            # No ANN annotation for this variant
            records.append(base_info)
            continue

        # Parse ANN entries (one per transcript/effect)
        ann_entries = ann_data.split(',') if isinstance(ann_data, str) else ann_data

        if most_severe_only:
            # Get most severe annotation only (first entry)
            ann_entry = ann_entries[0]
            fields = ann_entry.split('|')

            ann_info = {}
            for i, field_name in enumerate(ann_fields):
                value = fields[i] if i < len(fields) else ''
                ann_info[field_name] = value if value else None

            record = {**base_info, **ann_info}
            records.append(record)

        else:
            # Get all transcript annotations
            for ann_entry in ann_entries:
                fields = ann_entry.split('|')

                ann_info = {}
                for i, field_name in enumerate(ann_fields):
                    value = fields[i] if i < len(fields) else ''
                    ann_info[field_name] = value if value else None

                record = {**base_info, **ann_info}
                records.append(record)

    vcf.close()

    # Create DataFrame
    df = pd.DataFrame(records)

    # Rename columns for consistency with VEP
    rename_map = {
        'Annotation': 'Consequence',
        'Annotation_Impact': 'IMPACT',
        'Gene_Name': 'SYMBOL',
        'Gene_ID': 'Gene'
    }

    df = df.rename(columns=rename_map)

    return df


def extract_snpeff_consequences(df, most_severe_only=True):
    """
    Extract consequences from SNPEff DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame from parse_snpeff_vcf()
    most_severe_only : bool
        Keep only most severe consequence per variant

    Returns
    -------
    pd.DataFrame
        DataFrame with extracted consequences
    """
    if most_severe_only:
        # Group by variant and take first (most severe)
        groupby_cols = ['CHROM', 'POS', 'REF', 'ALT']
        df_grouped = df.groupby(groupby_cols, dropna=False).first().reset_index()
        return df_grouped
    else:
        return df


def parse_lof_field(df):
    """
    Parse LOF (Loss of Function) predictions from SNPEff.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame from parse_snpeff_vcf()

    Returns
    -------
    pd.DataFrame
        DataFrame with parsed LOF columns
    """
    if 'LOF' not in df.columns:
        # Check if we need to extract LOF from VCF INFO field
        return df

    # LOF format: (Gene_Name | Gene_ID | Number_of_transcripts_in_gene | Percent_of_transcripts_affected)
    def parse_lof_entry(lof_str):
        if pd.isna(lof_str) or not lof_str:
            return None, None, None, None

        parts = lof_str.strip('()').split('|')
        if len(parts) >= 4:
            return parts[0], parts[1], parts[2], parts[3]
        return None, None, None, None

    df[['LOF_Gene_Name', 'LOF_Gene_ID', 'LOF_Num_Transcripts', 'LOF_Percent_Affected']] = \
        df['LOF'].apply(lambda x: pd.Series(parse_lof_entry(x)))

    return df


def annotate_impact_severity(df):
    """
    Add numeric severity score for IMPACT field.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame from parse_snpeff_vcf()

    Returns
    -------
    pd.DataFrame
        DataFrame with IMPACT_SCORE column
    """
    impact_scores = {
        'HIGH': 4,
        'MODERATE': 3,
        'LOW': 2,
        'MODIFIER': 1
    }

    if 'IMPACT' in df.columns:
        df['IMPACT_SCORE'] = df['IMPACT'].map(impact_scores).fillna(0)

    return df


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Parse SNPEff-annotated VCF file')
    parser.add_argument('vcf', help='SNPEff-annotated VCF file')
    parser.add_argument('--output', help='Output CSV file (default: print to stdout)')
    parser.add_argument('--most-severe', action='store_true', help='Extract most severe consequence only')

    args = parser.parse_args()

    # Parse VCF
    df = parse_snpeff_vcf(args.vcf, most_severe_only=args.most_severe)

    # Add impact scores
    df = annotate_impact_severity(df)

    # Parse LOF if present
    df = parse_lof_field(df)

    # Output
    if args.output:
        df.to_csv(args.output, index=False)
        print(f"Wrote {len(df)} records to {args.output}")
    else:
        print(df.to_csv(index=False))

