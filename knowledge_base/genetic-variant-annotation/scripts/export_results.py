"""
Export Results Module

This module provides functions for exporting annotated variants in multiple formats.
"""

import sys
from pathlib import Path

try:
    import pandas as pd
    import xlsxwriter
    from openpyxl import load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment
except ImportError as e:
    print(f"Error: Missing required package: {e}")
    print("Install with: pip install pandas xlsxwriter openpyxl")
    sys.exit(1)


def export_to_excel(output_file, sheets, format_columns=True, freeze_panes=(1, 2)):
    """
    Export data to Excel with multiple sheets and formatting.

    Parameters
    ----------
    output_file : str
        Output Excel file path
    sheets : dict
        Dictionary mapping sheet names to DataFrames
    format_columns : bool
        Apply conditional formatting (default: True)
    freeze_panes : tuple
        Row and column to freeze (default: (1, 2) for header + 2 columns)
    """
    # Create Excel writer
    with pd.ExcelWriter(output_file, engine='xlsxwriter') as writer:
        workbook = writer.book

        # Define formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#D9E1F2',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter'
        })

        high_impact_format = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
        moderate_impact_format = workbook.add_format({'bg_color': '#FFEB9C', 'font_color': '#9C6500'})
        pathogenic_format = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})

        # Write each sheet
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=0)
            worksheet = writer.sheets[sheet_name]

            # Format header
            for col_num, column_name in enumerate(df.columns):
                worksheet.write(0, col_num, column_name, header_format)

            # Auto-fit columns
            for col_num, column_name in enumerate(df.columns):
                column_data = df[column_name].astype(str)
                max_length = max(
                    column_data.apply(len).max(),
                    len(column_name)
                ) + 2
                worksheet.set_column(col_num, col_num, min(max_length, 50))

            # Freeze panes
            if freeze_panes:
                worksheet.freeze_panes(freeze_panes[0], freeze_panes[1])

            # Conditional formatting
            if format_columns and 'IMPACT' in df.columns:
                impact_col = df.columns.get_loc('IMPACT')
                worksheet.conditional_format(
                    1, impact_col, len(df), impact_col,
                    {
                        'type': 'text',
                        'criteria': 'containing',
                        'value': 'HIGH',
                        'format': high_impact_format
                    }
                )
                worksheet.conditional_format(
                    1, impact_col, len(df), impact_col,
                    {
                        'type': 'text',
                        'criteria': 'containing',
                        'value': 'MODERATE',
                        'format': moderate_impact_format
                    }
                )

            if format_columns and 'CLIN_SIG' in df.columns:
                clinsig_col = df.columns.get_loc('CLIN_SIG')
                worksheet.conditional_format(
                    1, clinsig_col, len(df), clinsig_col,
                    {
                        'type': 'text',
                        'criteria': 'containing',
                        'value': 'Pathogenic',
                        'format': pathogenic_format
                    }
                )

    print(f"Exported {len(sheets)} sheets to {output_file}")


def export_to_csv(df, output_file, columns=None):
    """
    Export DataFrame to CSV with optional column selection.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame to export
    output_file : str
        Output CSV file path
    columns : list, optional
        List of columns to include (default: all)
    """
    if columns:
        # Keep only requested columns that exist
        existing_columns = [col for col in columns if col in df.columns]
        df_export = df[existing_columns]
    else:
        df_export = df

    df_export.to_csv(output_file, index=False)
    print(f"Exported {len(df_export)} variants to {output_file}")


def export_to_vcf(df, original_vcf, output_file, add_filter_tag=None, compress=True, index=True):
    """
    Export filtered variants back to VCF format.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with filtered variants
    original_vcf : str
        Path to original VCF file (for header)
    output_file : str
        Output VCF file path
    add_filter_tag : str, optional
        Add FILTER tag to passing variants (e.g., 'PASS_PRIORITY')
    compress : bool
        Compress output with bgzip (default: True)
    index : bool
        Create tabix index (default: True)
    """
    import cyvcf2
    import subprocess

    # Read original VCF
    vcf_in = cyvcf2.VCF(str(original_vcf))

    # Create variant set from DataFrame
    variant_set = set()
    for _, row in df.iterrows():
        var_id = (row['CHROM'], row['POS'], row['REF'], row['ALT'])
        variant_set.add(var_id)

    # Open output VCF
    output_path = Path(output_file)

    if compress and not output_file.endswith('.gz'):
        temp_vcf = str(output_path.with_suffix('.vcf'))
    else:
        temp_vcf = output_file

    vcf_out = cyvcf2.Writer(temp_vcf, vcf_in)

    # Write filtered variants
    n_written = 0
    for variant in cyvcf2.VCF(str(original_vcf)):
        # Check if variant is in filtered set
        for alt in variant.ALT:
            var_id = (variant.CHROM, variant.POS, variant.REF, alt)
            if var_id in variant_set:
                # Optionally add FILTER tag
                if add_filter_tag:
                    variant.FILTER = add_filter_tag

                vcf_out.write_record(variant)
                n_written += 1
                break

    vcf_out.close()
    vcf_in.close()

    # Compress if requested
    if compress and temp_vcf != output_file:
        subprocess.run(['bgzip', '-f', temp_vcf], check=True)
        compressed_file = temp_vcf + '.gz'

        # Rename to final name
        if compressed_file != output_file:
            Path(compressed_file).rename(output_file)

    # Index if requested
    if index and output_file.endswith('.gz'):
        subprocess.run(['tabix', '-p', 'vcf', '-f', output_file], check=True)

    print(f"Exported {n_written} variants to {output_file}")


def export_summary_report(
    df,
    gene_df,
    output_file,
    include_plots=False
):
    """
    Generate a comprehensive summary report in Excel format.

    Parameters
    ----------
    df : pd.DataFrame
        Variant annotations DataFrame
    gene_df : pd.DataFrame
        Gene summary DataFrame
    output_file : str
        Output Excel file path
    include_plots : bool
        Include plot images in report (default: False)
    """
    # Calculate summary statistics
    summary_stats = {
        'Metric': [
            'Total Variants',
            'High Impact',
            'Moderate Impact',
            'Low Impact',
            'Rare Variants (AF < 0.01)',
            'Genes Affected',
            'Average Variants per Gene'
        ],
        'Value': [
            len(df),
            len(df[df['IMPACT'] == 'HIGH']) if 'IMPACT' in df.columns else 0,
            len(df[df['IMPACT'] == 'MODERATE']) if 'IMPACT' in df.columns else 0,
            len(df[df['IMPACT'] == 'LOW']) if 'IMPACT' in df.columns else 0,
            len(df[pd.to_numeric(df.get('gnomAD_AF'), errors='coerce') < 0.01]),
            len(gene_df) if gene_df is not None else 0,
            len(df) / len(gene_df) if gene_df is not None and len(gene_df) > 0 else 0
        ]
    }

    summary_df = pd.DataFrame(summary_stats)

    # Top consequence types
    if 'Consequence' in df.columns:
        consequences = []
        for cons in df['Consequence'].dropna():
            consequences.extend(str(cons).split('&'))
        cons_df = pd.DataFrame({'Consequence': consequences})
        top_consequences = cons_df['Consequence'].value_counts().head(10).reset_index()
        top_consequences.columns = ['Consequence', 'Count']
    else:
        top_consequences = pd.DataFrame()

    # Prepare sheets
    sheets = {
        'Summary': summary_df,
        'Top_Consequences': top_consequences,
    }

    if gene_df is not None and len(gene_df) > 0:
        sheets['Top_Genes'] = gene_df.head(20)

    sheets['All_Variants'] = df.head(1000)  # Limit to first 1000

    # Export
    export_to_excel(output_file, sheets, format_columns=True)
    print(f"Summary report saved to {output_file}")


def export_all(
    df,
    gene_df=None,
    original_vcf=None,
    output_dir="results",
    tool_name="vep"
):
    """
    Export all results in all formats (COMPLETE EXPORT FOR DOWNSTREAM USE).

    This function exports annotated variants in multiple formats and saves
    analysis objects for downstream skills. Called as Step 4 in Standard Workflow.

    Parameters
    ----------
    df : pd.DataFrame
        Annotated variants DataFrame
    gene_df : pd.DataFrame, optional
        Gene summary DataFrame (default: None)
    original_vcf : str, optional
        Path to original VCF for filtered VCF export (default: None)
    output_dir : str
        Output directory path (default: "results")
    tool_name : str
        Annotation tool used ("vep" or "snpeff") for output naming

    Outputs
    -------
    Creates the following files in output_dir:
    - analysis_object.pkl: Pickled analysis object for downstream use
    - all_variants.csv: All annotated variants
    - high_impact_variants.csv: HIGH impact variants only
    - moderate_impact_variants.csv: MODERATE impact variants only
    - rare_variants.csv: Rare variants (AF < 0.01)
    - gene_summary.csv: Gene-level summaries (if gene_df provided)
    - summary_report.xlsx: Excel report with multiple sheets
    - filtered_high_impact.vcf.gz: Filtered VCF (if original_vcf provided)

    Examples
    --------
    >>> from scripts.export_results import export_all
    >>> export_all(annotated_df, gene_df, "input.vcf.gz", "results", "vep")
    ✓ Export completed successfully!
    """
    import pickle
    from pathlib import Path

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True, parents=True)

    print("\n" + "="*70)
    print("EXPORTING RESULTS")
    print("="*70 + "\n")

    # 1. Save analysis objects (CRITICAL for downstream skills)
    print("1. Saving analysis objects for downstream use...")
    analysis_object = {
        'variants': df,
        'genes': gene_df,
        'tool': tool_name,
        'n_variants': len(df),
        'n_genes': len(gene_df) if gene_df is not None else 0
    }

    pickle_path = output_path / "analysis_object.pkl"
    with open(pickle_path, 'wb') as f:
        pickle.dump(analysis_object, f)
    print(f"   Saved: {pickle_path}")
    print(f"   (Load with: import pickle; obj = pickle.load(open('{pickle_path}', 'rb')))")

    # 2. Export all variants to CSV
    print("\n2. Exporting all variants...")
    all_variants_path = output_path / "all_variants.csv"
    export_to_csv(df, all_variants_path)

    # 3. Export filtered variants (high impact)
    print("\n3. Exporting filtered variants...")
    if 'IMPACT' in df.columns:
        high_impact = df[df['IMPACT'] == 'HIGH']
        if len(high_impact) > 0:
            high_impact_path = output_path / "high_impact_variants.csv"
            export_to_csv(high_impact, high_impact_path)

        moderate_impact = df[df['IMPACT'].isin(['HIGH', 'MODERATE'])]
        if len(moderate_impact) > 0:
            moderate_path = output_path / "moderate_impact_variants.csv"
            export_to_csv(moderate_impact, moderate_path)

    # 4. Export rare variants (AF < 0.01)
    if 'gnomAD_AF' in df.columns or 'AF' in df.columns:
        af_col = 'gnomAD_AF' if 'gnomAD_AF' in df.columns else 'AF'
        rare = df[pd.to_numeric(df[af_col], errors='coerce') < 0.01]
        if len(rare) > 0:
            rare_path = output_path / "rare_variants.csv"
            export_to_csv(rare, rare_path)
            print(f"   Exported {len(rare)} rare variants (AF < 0.01)")

    # 5. Export gene summary
    if gene_df is not None and len(gene_df) > 0:
        print("\n4. Exporting gene summaries...")
        gene_path = output_path / "gene_summary.csv"
        export_to_csv(gene_df, gene_path)

    # 6. Export Excel summary report
    print("\n5. Generating summary report...")
    summary_path = output_path / "summary_report.xlsx"
    export_summary_report(df, gene_df, summary_path)

    # 7. Export filtered VCF (if original provided)
    if original_vcf and 'IMPACT' in df.columns:
        print("\n6. Exporting filtered VCF...")
        high_impact = df[df['IMPACT'] == 'HIGH']
        if len(high_impact) > 0:
            try:
                filtered_vcf = output_path / "filtered_high_impact.vcf.gz"
                export_to_vcf(high_impact, original_vcf, filtered_vcf)
            except Exception as e:
                print(f"   Warning: Could not export VCF: {e}")

    print("\n" + "="*70)
    print("=== Export Complete ===")
    print("="*70)
    print(f"\nAll results saved to: {output_dir}/")
    print(f"  - analysis_object.pkl (for downstream skills)")
    print(f"  - all_variants.csv ({len(df)} variants)")
    if 'IMPACT' in df.columns:
        print(f"  - high_impact_variants.csv ({len(df[df['IMPACT'] == 'HIGH'])} variants)")
    if gene_df is not None:
        print(f"  - gene_summary.csv ({len(gene_df)} genes)")
    print(f"  - summary_report.xlsx (multi-sheet Excel)")
    print("\n✓ Export completed successfully!\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Export annotated variants')
    parser.add_argument('input_csv', help='Input CSV file')
    parser.add_argument('--excel', help='Output Excel file')
    parser.add_argument('--csv', help='Output CSV file')
    parser.add_argument('--summary', help='Output summary report Excel file')
    parser.add_argument('--gene-summary', help='Gene summary CSV for report')

    args = parser.parse_args()

    # Load data
    df = pd.read_csv(args.input_csv)
    print(f"Loaded {len(df)} variants")

    # Load gene summary if provided
    gene_df = None
    if args.gene_summary:
        gene_df = pd.read_csv(args.gene_summary)

    # Export Excel
    if args.excel:
        sheets = {'Variants': df}
        if gene_df is not None:
            sheets['Gene_Summary'] = gene_df
        export_to_excel(args.excel, sheets)

    # Export CSV
    if args.csv:
        export_to_csv(df, args.csv)

    # Export summary report
    if args.summary:
        export_summary_report(df, gene_df, args.summary)

