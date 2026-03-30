"""
VEP Output Parser Module

This module provides functions for parsing VEP-annotated VCF files into pandas DataFrames.
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


def parse_vep_csq_header(vcf):
    """
    Parse VEP CSQ field format from VCF header.

    Parameters
    ----------
    vcf : cyvcf2.VCF
        VCF object with VEP annotations

    Returns
    -------
    list
        List of CSQ field names
    """
    # Find CSQ INFO field in header
    csq_info = vcf.get_header_type('CSQ')

    if not csq_info:
        raise ValueError("VCF does not contain VEP CSQ annotations")

    # Parse format from description
    # Format: "Consequence annotations from Ensembl VEP. Format: Allele|Consequence|..."
    description = csq_info['Description']

    if 'Format:' not in description:
        raise ValueError("Cannot parse CSQ format from VCF header")

    format_str = description.split('Format:')[1].strip()
    field_names = [f.strip() for f in format_str.split('|')]

    return field_names


def parse_vep_vcf(vcf_path, extract_fields=None, most_severe_only=False):
    """
    Parse VEP-annotated VCF into pandas DataFrame.

    Parameters
    ----------
    vcf_path : str
        Path to VEP-annotated VCF file
    extract_fields : list, optional
        List of CSQ fields to extract (default: all)
    most_severe_only : bool
        Extract only most severe consequence per variant (default: False)

    Returns
    -------
    pd.DataFrame
        DataFrame with variant annotations
    """
    vcf = cyvcf2.VCF(str(vcf_path))

    # Parse CSQ field format
    try:
        csq_fields = parse_vep_csq_header(vcf)
    except ValueError as e:
        raise ValueError(f"Cannot parse VEP annotations: {e}")

    # Determine which fields to extract
    if extract_fields:
        # Validate requested fields
        invalid_fields = set(extract_fields) - set(csq_fields)
        if invalid_fields:
            print(f"Warning: Requested fields not in VCF: {invalid_fields}")
        fields_to_extract = [f for f in extract_fields if f in csq_fields]
    else:
        fields_to_extract = csq_fields

    # Get field indices
    field_indices = {field: csq_fields.index(field) for field in fields_to_extract}

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

        # Get CSQ annotations
        csq_data = variant.INFO.get('CSQ')

        if not csq_data:
            # No CSQ annotation for this variant
            records.append(base_info)
            continue

        # Parse CSQ entries (one per transcript)
        csq_entries = csq_data.split(',') if isinstance(csq_data, str) else csq_data

        if most_severe_only:
            # Get most severe consequence only
            csq_entry = csq_entries[0]  # VEP orders by severity
            fields = csq_entry.split('|')

            csq_info = {}
            for field_name, field_idx in field_indices.items():
                value = fields[field_idx] if field_idx < len(fields) else ''
                csq_info[field_name] = value if value else None

            record = {**base_info, **csq_info}
            records.append(record)

        else:
            # Get all transcript consequences
            for csq_entry in csq_entries:
                fields = csq_entry.split('|')

                csq_info = {}
                for field_name, field_idx in field_indices.items():
                    value = fields[field_idx] if field_idx < len(fields) else ''
                    csq_info[field_name] = value if value else None

                record = {**base_info, **csq_info}
                records.append(record)

    vcf.close()

    # Create DataFrame
    df = pd.DataFrame(records)

    return df


def extract_vep_consequences(df, most_severe_only=True):
    """
    Extract consequences from VEP DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame from parse_vep_vcf()
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


def get_canonical_transcripts(df):
    """
    Filter to canonical transcripts only.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame from parse_vep_vcf()

    Returns
    -------
    pd.DataFrame
        DataFrame filtered to canonical transcripts
    """
    if 'CANONICAL' not in df.columns:
        print("Warning: CANONICAL field not found in DataFrame")
        return df

    # CANONICAL is 'YES' for canonical transcripts
    canonical = df[df['CANONICAL'] == 'YES'].copy()

    if len(canonical) == 0:
        print("Warning: No canonical transcripts found")
        return df

    return canonical


def annotate_impact_severity(df):
    """
    Add numeric severity score for IMPACT field.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame from parse_vep_vcf()

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

    parser = argparse.ArgumentParser(description='Parse VEP-annotated VCF file')
    parser.add_argument('vcf', help='VEP-annotated VCF file')
    parser.add_argument('--output', help='Output CSV file (default: print to stdout)')
    parser.add_argument('--most-severe', action='store_true', help='Extract most severe consequence only')
    parser.add_argument('--canonical', action='store_true', help='Extract canonical transcripts only')

    args = parser.parse_args()

    # Parse VCF
    df = parse_vep_vcf(args.vcf, most_severe_only=args.most_severe)

    # Filter to canonical if requested
    if args.canonical:
        df = get_canonical_transcripts(df)

    # Add impact scores
    df = annotate_impact_severity(df)

    # Output
    if args.output:
        df.to_csv(args.output, index=False)
        print(f"Wrote {len(df)} records to {args.output}")
    else:
        print(df.to_csv(index=False))

