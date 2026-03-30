"""
Load gene lists from user files (TXT, CSV, TSV, or DE results).

Supports multiple formats:
- Plain text (one gene per line)
- CSV/TSV with gene column (auto-detects column)
- DE results files (DESeq2, edgeR, limma formats)
"""

import pandas as pd
import os


def load_user_data(file_path, column_name=None):
    """
    Load gene list from user file.

    Parameters:
    -----------
    file_path : str
        Path to file containing gene list
    column_name : str or None
        Column name for genes (auto-detects if None)

    Returns:
    --------
    list of str: Gene symbols

    Supported formats:
    ------------------
    - Plain text: one gene per line
    - CSV/TSV: with gene column
    - DE results: DESeq2, edgeR, limma output files

    Auto-detection:
    ---------------
    If column_name is None, tries common column names:
    - 'gene', 'Gene', 'GENE'
    - 'gene_name', 'gene_symbol', 'symbol'
    - 'GeneName', 'GeneSymbol'

    Examples:
    ---------
    >>> genes = load_user_data("my_genes.txt")
    >>> genes = load_user_data("deseq2_results.csv", column_name="gene")
    """

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # Detect file type by extension
    file_ext = os.path.splitext(file_path)[1].lower()

    if file_ext == '.txt':
        # Plain text file: one gene per line
        return _load_plain_text(file_path)

    elif file_ext in ['.csv', '.tsv', '.tab']:
        # Delimited file
        sep = ',' if file_ext == '.csv' else '\t'
        return _load_delimited(file_path, sep=sep, column_name=column_name)

    else:
        # Try to infer format
        try:
            # Try CSV first
            return _load_delimited(file_path, sep=',', column_name=column_name)
        except Exception:
            try:
                # Try TSV
                return _load_delimited(file_path, sep='\t', column_name=column_name)
            except Exception:
                # Fall back to plain text
                return _load_plain_text(file_path)


def _load_plain_text(file_path):
    """Load genes from plain text file (one per line)."""
    genes = []

    with open(file_path, 'r') as f:
        for line in f:
            gene = line.strip()

            # Skip empty lines and comments
            if not gene or gene.startswith('#'):
                continue

            genes.append(gene)

    if len(genes) == 0:
        raise ValueError(f"No genes found in {file_path}")

    print(f"✓ Data loaded successfully: {len(genes)} genes")

    return genes


def _load_delimited(file_path, sep=',', column_name=None):
    """Load genes from delimited file (CSV/TSV)."""

    # Read file
    df = pd.read_csv(file_path, sep=sep)

    # Auto-detect gene column if not specified
    if column_name is None:
        # Try common column names
        possible_names = [
            'gene', 'Gene', 'GENE',
            'gene_name', 'gene_symbol', 'symbol',
            'GeneName', 'GeneSymbol', 'Symbol',
            'id', 'ID', 'gene_id'
        ]

        for name in possible_names:
            if name in df.columns:
                column_name = name
                break

        # If still None, use first column
        if column_name is None:
            column_name = df.columns[0]
            print(f"   Auto-detected gene column: '{column_name}'")

    # Extract gene list
    if column_name not in df.columns:
        raise ValueError(f"Column '{column_name}' not found. Available: {list(df.columns)}")

    genes = df[column_name].astype(str).tolist()

    # Remove NaN values
    genes = [g for g in genes if g != 'nan' and g.strip() != '']

    if len(genes) == 0:
        raise ValueError(f"No genes found in column '{column_name}'")

    print(f"✓ Data loaded successfully: {len(genes)} genes")

    return genes


if __name__ == "__main__":
    # Test with mock files
    import tempfile

    print("Testing load_user_data...\n")

    # Test 1: Plain text file
    print("Test 1: Plain text file")
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        test_txt = f.name
        f.write("TP53\nMYC\nCDKN1A\nBAX\nBBC3\n")

    genes1 = load_user_data(test_txt)
    print(f"   Loaded: {genes1}\n")
    os.unlink(test_txt)

    # Test 2: CSV file with gene column
    print("Test 2: CSV file with gene column")
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
        test_csv = f.name
        f.write("gene,log2FC,padj\n")
        f.write("TP53,2.5,0.001\n")
        f.write("MYC,3.2,0.0001\n")
        f.write("CDKN1A,1.8,0.01\n")

    genes2 = load_user_data(test_csv)
    print(f"   Loaded: {genes2}\n")
    os.unlink(test_csv)

    # Test 3: TSV file (auto-detect)
    print("Test 3: TSV file with custom column")
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv') as f:
        test_tsv = f.name
        f.write("GeneSymbol\tpvalue\tFC\n")
        f.write("TP53\t0.001\t2.5\n")
        f.write("MYC\t0.0001\t3.2\n")

    genes3 = load_user_data(test_tsv, column_name='GeneSymbol')
    print(f"   Loaded: {genes3}\n")
    os.unlink(test_tsv)

    print("All tests completed successfully!")

