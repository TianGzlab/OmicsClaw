"""
Load differential expression results from CSV/TSV files.

Supports output from DESeq2, edgeR, limma, and generic DE results.
Standardizes column names and splits genes into up/down/background sets.
"""

import os
import pandas as pd
import numpy as np


# Column name mappings for auto-detection
_GENE_COLUMNS = [
    "gene", "Gene", "GENE",
    "gene_name", "gene_symbol", "symbol",
    "GeneName", "GeneSymbol", "Symbol",
    "id", "ID", "gene_id",
]

_LOG2FC_COLUMNS = [
    "log2FoldChange",  # DESeq2
    "logFC",           # edgeR / limma
    "log2FC",
    "lfc",
    "Log2FC",
]

_PADJ_COLUMNS = [
    "padj",            # DESeq2
    "FDR",             # edgeR
    "adj.P.Val",       # limma
    "p_adjusted",
    "qvalue",
    "q_value",
    "p.adjust",
]


def _detect_column(df, candidates, label):
    """Auto-detect a column from a list of candidate names."""
    for name in candidates:
        if name in df.columns:
            return name
    return None


def load_de_results(
    file_path,
    gene_col=None,
    log2fc_col=None,
    padj_col=None,
    padj_threshold=0.05,
    log2fc_threshold=1.0,
):
    """
    Load and standardize DE results from CSV/TSV.

    Parameters
    ----------
    file_path : str
        Path to DE results file (CSV or TSV).
    gene_col : str or None
        Column name for gene symbols. Auto-detects if None.
    log2fc_col : str or None
        Column name for log2 fold change. Auto-detects if None.
    padj_col : str or None
        Column name for adjusted p-value. Auto-detects if None.
    padj_threshold : float
        Significance threshold (default: 0.05).
    log2fc_threshold : float
        Minimum absolute log2FC for significance (default: 1.0).

    Returns
    -------
    dict
        - de_all: pd.DataFrame (all genes, standardized columns)
        - de_up: list[str] (upregulated gene symbols)
        - de_down: list[str] (downregulated gene symbols)
        - de_significant: list[str] (all significant genes)
        - background_genes: list[str] (all genes = Fisher's test background)
        - n_total: int
        - n_up: int
        - n_down: int
        - thresholds: dict
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # Detect delimiter
    ext = os.path.splitext(file_path)[1].lower()
    sep = "\t" if ext in [".tsv", ".tab"] else ","

    df = pd.read_csv(file_path, sep=sep)

    # If gene IDs are in the index (row names), promote to column
    if gene_col is None and _detect_column(df, _GENE_COLUMNS, "gene") is None:
        # Check if index looks like gene names (not numeric)
        if not pd.api.types.is_numeric_dtype(df.index):
            df = df.reset_index()
            df.rename(columns={df.columns[0]: "gene"}, inplace=True)

    # Auto-detect columns
    gene_col = gene_col or _detect_column(df, _GENE_COLUMNS, "gene") or df.columns[0]
    log2fc_col = log2fc_col or _detect_column(df, _LOG2FC_COLUMNS, "log2FC")
    padj_col = padj_col or _detect_column(df, _PADJ_COLUMNS, "padj")

    if log2fc_col is None:
        raise ValueError(
            f"Could not detect log2FC column. Available: {list(df.columns)}. "
            f"Specify with log2fc_col= parameter."
        )
    if padj_col is None:
        raise ValueError(
            f"Could not detect adjusted p-value column. Available: {list(df.columns)}. "
            f"Specify with padj_col= parameter."
        )

    print(f"   Detected columns: gene='{gene_col}', log2FC='{log2fc_col}', padj='{padj_col}'")

    # Standardize
    de_all = pd.DataFrame({
        "gene": df[gene_col].astype(str),
        "log2FoldChange": pd.to_numeric(df[log2fc_col], errors="coerce"),
        "padj": pd.to_numeric(df[padj_col], errors="coerce"),
    })

    # Preserve additional columns if present
    for col in ["baseMean", "stat", "pvalue"]:
        candidates = [col, col.lower(), col.upper()]
        for c in candidates:
            if c in df.columns:
                de_all[col] = pd.to_numeric(df[c], errors="coerce")
                break

    # Drop rows with missing gene or padj
    de_all = de_all.dropna(subset=["gene", "padj"])
    de_all = de_all[de_all["gene"] != "nan"].reset_index(drop=True)

    # Split into up/down
    sig_mask = (de_all["padj"] < padj_threshold) & (de_all["log2FoldChange"].abs() > log2fc_threshold)
    up_mask = sig_mask & (de_all["log2FoldChange"] > 0)
    down_mask = sig_mask & (de_all["log2FoldChange"] < 0)

    de_up = de_all.loc[up_mask, "gene"].tolist()
    de_down = de_all.loc[down_mask, "gene"].tolist()
    de_significant = de_all.loc[sig_mask, "gene"].tolist()
    background_genes = de_all["gene"].tolist()

    result = {
        "de_all": de_all,
        "de_up": de_up,
        "de_down": de_down,
        "de_significant": de_significant,
        "background_genes": background_genes,
        "n_total": len(de_all),
        "n_up": len(de_up),
        "n_down": len(de_down),
        "thresholds": {
            "padj_threshold": padj_threshold,
            "log2fc_threshold": log2fc_threshold,
        },
    }

    print(
        f"✓ Data loaded successfully: {len(de_all)} total genes, "
        f"{len(de_significant)} DE genes ({len(de_up)} up, {len(de_down)} down)"
    )

    return result

