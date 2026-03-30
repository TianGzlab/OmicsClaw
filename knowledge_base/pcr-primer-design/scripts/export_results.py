"""
Export primers in multiple formats.

This module provides functions to export primer designs in various formats
for ordering, documentation, and analysis.
"""

import json
import csv
from typing import Dict, List
from datetime import datetime


def export_primers(
    primers: Dict,
    format: str = "csv",
    output_file: str = None,
    include_validation: bool = True,
    validation_results: Dict = None
) -> str:
    """
    Export primers to various formats.

    Parameters
    ----------
    primers : dict
        Primer design results
    format : str
        Export format: "csv", "excel", "json", "idt_order", "miqe_checklist"
    output_file : str, optional
        Output file path. If None, returns string.
    include_validation : bool
        Include validation results if available. Default: True
    validation_results : dict, optional
        Validation results to include

    Returns
    -------
    str
        Exported data (if output_file is None) or file path

    Example
    -------
    >>> export_primers(
    ...     primers=primer_results,
    ...     format="csv",
    ...     output_file="primers.csv"
    ... )
    """

    if format == "csv":
        return _export_csv(primers, output_file, include_validation, validation_results)
    elif format == "excel":
        return _export_excel(primers, output_file, include_validation, validation_results)
    elif format == "json":
        return _export_json(primers, output_file, include_validation, validation_results)
    elif format == "idt_order":
        return _export_idt_order(primers, output_file)
    elif format == "miqe_checklist":
        return _export_miqe_checklist(primers, output_file)
    else:
        raise ValueError(f"Unknown export format: {format}")


def _export_csv(
    primers: Dict,
    output_file: str = None,
    include_validation: bool = True,
    validation_results: Dict = None
) -> str:
    """Export to CSV format."""

    rows = []

    # Header
    header = [
        'Pair_ID', 'Forward_Sequence', 'Reverse_Sequence',
        'Amplicon_Size_bp', 'Forward_Tm_C', 'Reverse_Tm_C', 'Tm_Diff_C',
        'Forward_GC_%', 'Reverse_GC_%',
        'Forward_Length', 'Reverse_Length',
        'Forward_Position', 'Reverse_Position',
        'Design_Quality_Score'
    ]

    # Add validation columns if available
    if include_validation and validation_results:
        header.extend(['Specificity', 'Has_Dimers', 'Has_Secondary_Structures'])

    rows.append(header)

    # Data rows
    for pair in primers.get('primers', []):
        row = [
            pair.get('pair_id', ''),
            pair['forward_seq'],
            pair['reverse_seq'],
            pair['amplicon_size'],
            pair['forward_tm'],
            pair['reverse_tm'],
            pair['tm_diff'],
            pair['forward_gc'],
            pair['reverse_gc'],
            pair['forward_length'],
            pair['reverse_length'],
            pair['forward_pos'],
            pair['reverse_pos'],
            pair['penalty'],
        ]

        # Add validation data
        if include_validation and validation_results:
            row.extend([
                validation_results.get('specificity', {}).get('is_specific', 'N/A'),
                validation_results.get('dimers', {}).get('has_issues', 'N/A'),
                validation_results.get('secondary_structures', {}).get('has_issues', 'N/A'),
            ])

        rows.append(row)

    # Write to file or return string
    if output_file:
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(rows)
        return output_file
    else:
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(rows)
        return output.getvalue()


def _export_excel(
    primers: Dict,
    output_file: str,
    include_validation: bool = True,
    validation_results: Dict = None
) -> str:
    """Export to Excel format with multiple sheets."""

    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas required for Excel export. Install with: pip install pandas openpyxl")

    # Prepare primers dataframe
    primer_data = []
    for pair in primers.get('primers', []):
        primer_data.append({
            'Pair_ID': pair.get('pair_id', ''),
            'Forward_Sequence': pair['forward_seq'],
            'Reverse_Sequence': pair['reverse_seq'],
            'Amplicon_Size_bp': pair['amplicon_size'],
            'Forward_Tm_C': pair['forward_tm'],
            'Reverse_Tm_C': pair['reverse_tm'],
            'Tm_Diff_C': pair['tm_diff'],
            'Forward_GC_%': pair['forward_gc'],
            'Reverse_GC_%': pair['reverse_gc'],
            'Forward_Length': pair['forward_length'],
            'Reverse_Length': pair['reverse_length'],
            'Design_Quality': pair['penalty'],
        })

    df_primers = pd.DataFrame(primer_data)

    # Write to Excel with multiple sheets
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        df_primers.to_excel(writer, sheet_name='Primers', index=False)

        # Add parameters sheet
        params = primers.get('parameters', {})
        df_params = pd.DataFrame([params])
        df_params.to_excel(writer, sheet_name='Parameters', index=False)

        # Add validation sheet if available
        if include_validation and validation_results:
            val_data = []
            for key, value in validation_results.items():
                if isinstance(value, dict):
                    for subkey, subvalue in value.items():
                        val_data.append({
                            'Category': key,
                            'Check': subkey,
                            'Result': str(subvalue)
                        })

            if val_data:
                df_validation = pd.DataFrame(val_data)
                df_validation.to_excel(writer, sheet_name='Validation', index=False)

    return output_file


def _export_json(
    primers: Dict,
    output_file: str = None,
    include_validation: bool = True,
    validation_results: Dict = None
) -> str:
    """Export to JSON format."""

    export_data = {
        'metadata': {
            'generated': datetime.now().isoformat(),
            'sequence_length': primers.get('sequence_length'),
            'num_primers': primers.get('num_primers_found'),
        },
        'parameters': primers.get('parameters', {}),
        'primers': primers.get('primers', []),
    }

    if include_validation and validation_results:
        export_data['validation'] = validation_results

    # Write to file or return string
    if output_file:
        with open(output_file, 'w') as f:
            json.dump(export_data, f, indent=2)
        return output_file
    else:
        return json.dumps(export_data, indent=2)


def _export_idt_order(primers: Dict, output_file: str = None) -> str:
    """
    Export in IDT (Integrated DNA Technologies) order format.

    Format: Name, Sequence, Scale, Purification
    """

    lines = []
    lines.append("Name\tSequence\tScale\tPurification")

    for i, pair in enumerate(primers.get('primers', []), 1):
        # Forward primer
        fwd_name = f"Primer_Pair{i}_Forward"
        lines.append(f"{fwd_name}\t{pair['forward_seq']}\t25nm\tSTD")

        # Reverse primer
        rev_name = f"Primer_Pair{i}_Reverse"
        lines.append(f"{rev_name}\t{pair['reverse_seq']}\t25nm\tSTD")

        # Probe if present
        if 'probe_seq' in pair:
            probe_name = f"Primer_Pair{i}_Probe"
            lines.append(f"{probe_name}\t{pair['probe_seq']}\t25nm\tHPLC")

    content = "\n".join(lines)

    if output_file:
        with open(output_file, 'w') as f:
            f.write(content)
        return output_file
    else:
        return content


def _export_miqe_checklist(primers: Dict, output_file: str) -> str:
    """
    Export MIQE compliance checklist.

    Creates an Excel file with MIQE checklist pre-filled where possible.
    """

    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas required for MIQE checklist. Install with: pip install pandas openpyxl")

    # MIQE essential information
    miqe_items = [
        # Experimental Design
        ('Experimental Design', 'qPCR purpose', '', 'Essential'),
        ('Experimental Design', 'Experimental design', '', 'Essential'),
        ('Experimental Design', 'Sample nature', '', 'Essential'),

        # Sample
        ('Sample', 'Description', '', 'Essential'),
        ('Sample', 'Volume/mass', '', 'Essential'),
        ('Sample', 'Storage conditions', '', 'Essential'),
        ('Sample', 'RNA/DNA quality', '', 'Essential'),

        # Primers
        ('Primers', 'Primer sequences', 'See Primers sheet', 'Essential'),
        ('Primers', 'Location on target', f"{primers.get('primers', [{}])[0].get('forward_pos', 'N/A')} - {primers.get('primers', [{}])[0].get('reverse_pos', 'N/A')}", 'Essential'),
        ('Primers', 'Amplicon length', f"{primers.get('primers', [{}])[0].get('amplicon_size', 'N/A')} bp", 'Essential'),
        ('Primers', 'In silico specificity check', 'Performed', 'Essential'),
        ('Primers', 'Empirical specificity check', '', 'Essential'),

        # Protocol
        ('Protocol', 'Complete reaction conditions', '', 'Essential'),
        ('Protocol', 'Reaction volume', '', 'Essential'),
        ('Protocol', 'Primer concentration', '', 'Essential'),
        ('Protocol', 'Cycling conditions', '', 'Essential'),

        # Validation
        ('Validation', 'Evidence of optimization', '', 'Essential'),
        ('Validation', 'Specificity (melt curve)', '', 'Essential'),
        ('Validation', 'Standard curve slope', '', 'Essential'),
        ('Validation', 'PCR efficiency', '', 'Essential'),
        ('Validation', 'R²', '', 'Essential'),
        ('Validation', 'Linear dynamic range', '', 'Essential'),
        ('Validation', 'Cq variation at LOD', '', 'Essential'),

        # Data Analysis
        ('Data Analysis', 'Cq method', '', 'Essential'),
        ('Data Analysis', 'Outlier identification', '', 'Essential'),
        ('Data Analysis', 'Results of NTCs', '', 'Essential'),
        ('Data Analysis', 'Normalization method', '', 'Essential'),
        ('Data Analysis', 'Number and description of reference genes', '', 'Essential'),
        ('Data Analysis', 'Statistical methods', '', 'Essential'),
    ]

    df_miqe = pd.DataFrame(miqe_items, columns=['Category', 'Item', 'Value', 'MIQE Level'])

    # Also include primer details
    primer_data = []
    for i, pair in enumerate(primers.get('primers', []), 1):
        primer_data.append({
            'Pair': i,
            'Forward': pair['forward_seq'],
            'Reverse': pair['reverse_seq'],
            'Amplicon_bp': pair['amplicon_size'],
            'Tm_F': pair['forward_tm'],
            'Tm_R': pair['reverse_tm'],
        })

    df_primers = pd.DataFrame(primer_data)

    # Write to Excel
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        df_miqe.to_excel(writer, sheet_name='MIQE_Checklist', index=False)
        df_primers.to_excel(writer, sheet_name='Primers', index=False)

    return output_file


def export_for_benchling(primers: Dict, output_file: str = None) -> str:
    """
    Export in Benchling-compatible format.

    Parameters
    ----------
    primers : dict
        Primer design results
    output_file : str, optional
        Output CSV file path

    Returns
    -------
    str
        File path or CSV content
    """

    rows = []
    rows.append(['Name', 'Bases', 'Description'])

    for i, pair in enumerate(primers.get('primers', []), 1):
        rows.append([
            f"Pair{i}_Forward",
            pair['forward_seq'],
            f"Forward primer, Tm={pair['forward_tm']}°C, GC={pair['forward_gc']}%"
        ])

        rows.append([
            f"Pair{i}_Reverse",
            pair['reverse_seq'],
            f"Reverse primer, Tm={pair['reverse_tm']}°C, GC={pair['reverse_gc']}%"
        ])

    if output_file:
        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(rows)
        return output_file
    else:
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(rows)
        return output.getvalue()

