"""
Load example DE results for the upstream regulator analysis.

Three real datasets available (all from EBI Expression Atlas, pre-computed DESeq2):
- "estrogen" (default): Estradiol-treated MCF7 breast cancer cells (GSE51403).
  Expected top regulator: ESR1 (estrogen receptor alpha).
  ~58K genes, single contrast, 7 biological replicates.
- "airway": Dexamethasone-treated airway smooth muscle cells (GSE52778).
  Expected top regulator: NR3C1 (glucocorticoid receptor).
  ~58K genes, 3 contrasts (we use dexamethasone vs untreated).
- "synthetic": Offline TP53-driven synthetic data (~200 genes, no network needed).
"""

import io
import os

import numpy as np
import pandas as pd
import requests


# --- EBI Expression Atlas FTP URLs (stable, public) ---
# Note: The web app URL pattern (gxa/experiments-content/...) returns HTTP 500.
# The FTP server serves identical analytics files reliably.
_ATLAS_FTP_BASE = (
    "https://ftp.ebi.ac.uk/pub/databases/microarray/data/atlas/experiments"
)

# Dataset configurations: accession, contrast ID, description
_DATASETS = {
    "estrogen": {
        "accession": "E-GEOD-51403",
        "contrast": "g2_g1",
        "description": "Estradiol (10nM) vs vehicle in MCF7 breast cancer cells",
        "reference": "Miano et al. 2016, GSE51403",
        "expected_tf": "ESR1",
    },
    "airway": {
        "accession": "E-GEOD-52778",
        "contrast": "g4_g3",
        "description": "Dexamethasone vs untreated in airway smooth muscle cells",
        "reference": "Himes et al. 2014, GSE52778",
        "expected_tf": "NR3C1",
    },
}


def load_example_data(source="estrogen", padj_threshold=0.05, log2fc_threshold=1.0):
    """
    Load example DE results for upstream regulator demo.

    Parameters
    ----------
    source : str
        "estrogen" (default) — ESR1-driven DE from MCF7 cells (real data).
        "airway" — dexamethasone-driven DE from airway cells (real data).
        "synthetic" — synthetic TP53-driven data (fast, offline).
    padj_threshold : float
        Significance threshold (default: 0.05).
    log2fc_threshold : float
        Minimum absolute log2FC (default: 1.0).

    Returns
    -------
    dict
        - de_all: pd.DataFrame
        - de_up, de_down, de_significant, background_genes: list[str]
        - n_total, n_up, n_down: int
        - thresholds: dict
    """
    if source in _DATASETS:
        return _load_atlas_de(source, padj_threshold, log2fc_threshold)
    elif source == "synthetic":
        return _load_synthetic(padj_threshold, log2fc_threshold)
    else:
        valid = list(_DATASETS.keys()) + ["synthetic"]
        raise ValueError(f"Unknown source '{source}'. Use one of: {valid}")


# =========================================================================
# Expression Atlas dataset loader (generic for any dataset)
# =========================================================================

def _load_atlas_de(source, padj_threshold=0.05, log2fc_threshold=1.0):
    """
    Download real DE results from EBI Expression Atlas FTP server.

    Works for any dataset configured in _DATASETS dict.
    """
    config = _DATASETS[source]
    accession = config["accession"]
    contrast = config["contrast"]

    print(f"   Downloading {source} DE results from EBI Expression Atlas...")
    print(f"   Source: {accession} ({config['description']})")
    print(f"   Expected top regulator: {config['expected_tf']}")

    url = f"{_ATLAS_FTP_BASE}/{accession}/{accession}-analytics.tsv"

    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"   WARNING: Download failed ({e}). Falling back to synthetic data.")
        return _load_synthetic(padj_threshold, log2fc_threshold)

    print(f"   Downloaded {len(resp.content) / 1024:.0f} KB")

    # Parse TSV
    df = pd.read_csv(io.StringIO(resp.text), sep="\t")

    # Find the correct contrast columns
    pval_col = f"{contrast}.p-value"
    lfc_col = f"{contrast}.log2foldchange"

    if pval_col not in df.columns or lfc_col not in df.columns:
        print(f"   WARNING: Expected columns not found ({pval_col}, {lfc_col}).")
        print(f"   Available contrasts: {[c.replace('.p-value', '') for c in df.columns if '.p-value' in c]}")
        print(f"   Falling back to synthetic data.")
        return _load_synthetic(padj_threshold, log2fc_threshold)

    # Standardize to our format
    de_all = pd.DataFrame({
        "gene": df["Gene Name"].astype(str),
        "ensembl_id": df["Gene ID"].astype(str),
        "log2FoldChange": pd.to_numeric(df[lfc_col], errors="coerce"),
        "padj": pd.to_numeric(df[pval_col], errors="coerce"),
    })

    # Drop rows without gene symbol or p-value
    de_all = de_all.dropna(subset=["gene", "padj"])
    de_all = de_all[
        (de_all["gene"] != "nan")
        & (de_all["gene"] != "")
        & (de_all["gene"] != "None")
    ].reset_index(drop=True)

    # Remove duplicates (keep first occurrence)
    de_all = de_all.drop_duplicates(subset="gene", keep="first").reset_index(drop=True)

    # Split into significant sets
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


# =========================================================================
# Synthetic dataset (offline, fast, TP53-driven)
# =========================================================================

def _load_synthetic(padj_threshold=0.05, log2fc_threshold=1.0):
    """
    Generate synthetic DE results with known TP53 activation.

    ~200 genes, designed so TP53 emerges as top upstream regulator.
    Fast (<1 second), no network dependencies.
    """
    print("   Generating synthetic TP53-driven DE results...")

    np.random.seed(42)

    # --- Upregulated genes (TP53 targets + DNA damage response) ---
    up_genes = {
        "CDKN1A": (3.2, 1e-12), "BAX": (2.8, 5e-10), "MDM2": (2.5, 1e-9),
        "BBC3": (3.0, 2e-11), "GADD45A": (2.1, 3e-8), "SERPINE1": (1.5, 2e-5),
        "FAS": (1.8, 8e-7), "SESN1": (1.7, 5e-6), "TIGAR": (1.3, 4e-4),
        "DDB2": (1.6, 1e-5), "PMAIP1": (2.2, 7e-9), "FDXR": (1.9, 2e-7),
        "RRM2B": (1.4, 1e-4), "ZMAT3": (1.8, 4e-7), "PLK3": (1.5, 6e-5),
        "DDIT3": (2.0, 1e-6), "ATF3": (1.6, 3e-5), "GADD45B": (1.4, 5e-4),
        "BTG2": (1.9, 7e-7), "TNFRSF10B": (1.7, 2e-6), "PERP": (1.3, 8e-4),
        "CYFIP2": (1.2, 2e-3), "TP53INP1": (2.1, 4e-8), "PHLDA3": (1.6, 7e-5),
        "AEN": (1.4, 3e-4), "IL6": (2.4, 3e-8), "CXCL8": (1.8, 6e-6),
        "IL1B": (1.5, 4e-5), "CCL2": (1.3, 9e-4), "ICAM1": (1.2, 3e-3),
        "GDF15": (2.6, 8e-10), "ACTA2": (1.4, 2e-4), "THBS1": (1.3, 7e-4),
        "IGFBP3": (1.5, 5e-5), "CKAP2": (1.1, 8e-3), "PLK2": (1.6, 9e-6),
        "CCNG1": (1.8, 3e-7), "SFN": (2.0, 5e-8), "TRIAP1": (1.2, 4e-3),
        "POLK": (1.1, 9e-3), "XPC": (1.3, 6e-4), "POLH": (1.2, 2e-3),
        "PCNA": (1.1, 7e-3), "RPS27L": (1.4, 1e-4),
    }

    # --- Downregulated genes (MYC/E2F targets + cell cycle) ---
    down_genes = {
        "CDK4": (-2.1, 4e-8), "CCND1": (-1.8, 2e-6), "CDC25A": (-1.5, 3e-5),
        "TERT": (-2.3, 1e-9), "NME1": (-1.7, 8e-7), "NPM1": (-1.4, 2e-4),
        "LDHA": (-1.3, 7e-4), "CCNA2": (-1.9, 5e-7), "CDC25C": (-1.2, 3e-3),
        "MCM7": (-1.6, 4e-5), "E2F1": (-1.5, 6e-5), "CCNB1": (-1.8, 3e-6),
        "CDK1": (-2.0, 8e-8), "CDK2": (-1.4, 1e-4), "RB1": (-1.1, 5e-3),
        "MCM3": (-1.3, 9e-4), "TOP2A": (-2.2, 2e-8), "AURKA": (-1.6, 7e-5),
        "BUB1": (-1.3, 6e-4), "KIF11": (-1.5, 2e-5), "CENPA": (-1.1, 8e-3),
        "BIRC5": (-1.7, 5e-6), "PLK1": (-1.9, 1e-7), "TTK": (-1.4, 3e-4),
    }

    # --- Non-significant background genes ---
    background_ns = [
        "ACTB", "GAPDH", "TUBB", "TUBA1A", "RPL13A", "RPS18", "B2M",
        "HPRT1", "TBP", "PPIA", "YWHAZ", "SDHA", "HMBS", "UBC",
        "GUSB", "ALAS1", "PGK1", "TFRC", "RPLP0", "RPL19",
        "EEF1A1", "EEF2", "RPS3", "RPL4", "RPS6", "RPL10",
        "ATP5F1B", "NDUFA4", "COX7C", "UQCR10", "ATP5MG",
        "CALM1", "CALM2", "CFL1", "PFN1", "ARPC2", "ARPC3",
        "HSP90AA1", "HSPA8", "HSPA1A", "HSPA5", "HSP90AB1",
        "PARK7", "SOD1", "SOD2", "CAT", "GPX1", "PRDX1",
        "LMNA", "VIM", "KRT8", "KRT18", "DES", "GFAP",
        "TGFB1", "VEGFA", "FGF2", "EGF", "PDGFB", "IGF1",
        "STAT3", "JAK1", "JAK2", "SRC", "ABL1", "MAPK1",
        "AKT1", "MTOR", "PIK3CA", "PTEN", "TSC1", "TSC2",
        "BRCA1", "BRCA2", "ATM", "ATR", "CHEK1", "CHEK2",
        "RAD51", "XRCC1", "ERCC1", "MSH2", "MLH1", "PMS2",
        "HDAC1", "HDAC2", "KAT2A", "EP300", "CREBBP", "SIRT1",
        "DNMT1", "DNMT3A", "DNMT3B", "TET1", "TET2", "TET3",
        "MYH9", "MYH10", "MYO1C", "DYNC1H1", "KIF5B", "TUBB3",
        "SLC2A1", "SLC7A5", "ABCB1", "ABCC1", "SLC1A5", "SLC3A2",
        "NOTCH1", "HES1", "DLL1", "JAG1", "WNT3A", "CTNNB1",
        "SMAD2", "SMAD3", "SMAD4", "TGFBR1", "TGFBR2", "BMP4",
        "HIF1A", "EPAS1", "ARNT", "PHD2", "VHL", "FIH1",
        "NFKB1", "RELA", "NFKBIA", "IKBKB", "IKBKG", "TRAF6",
    ]

    rows = []
    for gene, (lfc, padj) in up_genes.items():
        rows.append({
            "gene": gene, "log2FoldChange": lfc, "padj": padj,
            "baseMean": round(np.random.uniform(200, 5000), 1),
        })
    for gene, (lfc, padj) in down_genes.items():
        rows.append({
            "gene": gene, "log2FoldChange": lfc, "padj": padj,
            "baseMean": round(np.random.uniform(200, 5000), 1),
        })
    for gene in background_ns:
        rows.append({
            "gene": gene,
            "log2FoldChange": round(np.random.normal(0, 0.3), 3),
            "padj": round(np.random.uniform(0.1, 1.0), 4),
            "baseMean": round(np.random.uniform(50, 3000), 1),
        })

    de_all = pd.DataFrame(rows)

    sig_mask = (de_all["padj"] < padj_threshold) & (de_all["log2FoldChange"].abs() > log2fc_threshold)
    up_mask = sig_mask & (de_all["log2FoldChange"] > 0)
    down_mask = sig_mask & (de_all["log2FoldChange"] < 0)

    result = {
        "de_all": de_all,
        "de_up": de_all.loc[up_mask, "gene"].tolist(),
        "de_down": de_all.loc[down_mask, "gene"].tolist(),
        "de_significant": de_all.loc[sig_mask, "gene"].tolist(),
        "background_genes": de_all["gene"].tolist(),
        "n_total": len(de_all),
        "n_up": int(up_mask.sum()),
        "n_down": int(down_mask.sum()),
        "thresholds": {
            "padj_threshold": padj_threshold,
            "log2fc_threshold": log2fc_threshold,
        },
    }

    print(
        f"✓ Data loaded successfully: {len(de_all)} total genes, "
        f"{len(result['de_significant'])} DE genes ({result['n_up']} up, {result['n_down']} down)"
    )

    return result

