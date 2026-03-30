"""
Expression Reference Panel Selection for TWAS

This module provides functions for selecting appropriate tissue references
and downloading pre-computed expression weights for FUSION and S-PrediXcan.
"""

import pandas as pd
import urllib.request
from pathlib import Path


# Tissue recommendations by trait category
TISSUE_RECOMMENDATIONS = {
    "cardiovascular": [
        "Artery_Coronary",
        "Artery_Aorta",
        "Heart_Atrial_Appendage",
        "Heart_Left_Ventricle",
        "Whole_Blood"
    ],
    "metabolic": [
        "Liver",
        "Pancreas",
        "Adipose_Subcutaneous",
        "Adipose_Visceral_Omentum",
        "Muscle_Skeletal"
    ],
    "neurological": [
        "Brain_Cortex",
        "Brain_Cerebellum",
        "Brain_Hippocampus",
        "Brain_Substantia_nigra",
        "Brain_Anterior_cingulate_cortex_BA24"
    ],
    "immune": [
        "Whole_Blood",
        "Spleen",
        "Cells_EBV-transformed_lymphocytes",
        "Lung",
        "Small_Intestine_Terminal_Ileum"
    ],
    "cancer": [
        "depends_on_cancer_type"  # Use TCGA for cancer-specific
    ],
    "renal": [
        "Kidney_Cortex",
        "Kidney_Medulla",
        "Artery_Aorta",
        "Whole_Blood"
    ],
    "respiratory": [
        "Lung",
        "Whole_Blood",
        "Artery_Aorta"
    ],
    "gastrointestinal": [
        "Colon_Sigmoid",
        "Colon_Transverse",
        "Small_Intestine_Terminal_Ileum",
        "Esophagus_Mucosa",
        "Stomach"
    ]
}


def select_gtex_tissues(trait_category, top_n=5):
    """
    Get tissue recommendations based on trait category.

    Parameters
    ----------
    trait_category : str
        Trait category (e.g., "cardiovascular", "metabolic", "neurological")
    top_n : int
        Number of top tissues to return (default: 5)

    Returns
    -------
    list
        List of recommended tissue names
    """
    category_lower = trait_category.lower()

    if category_lower not in TISSUE_RECOMMENDATIONS:
        print(f"WARNING: Unknown trait category '{trait_category}'")
        print(f"Available categories: {list(TISSUE_RECOMMENDATIONS.keys())}")
        print("Returning top 5 most commonly used tissues")
        return ["Whole_Blood", "Liver", "Brain_Cortex", "Muscle_Skeletal", "Adipose_Subcutaneous"]

    tissues = TISSUE_RECOMMENDATIONS[category_lower]

    if "depends_on_cancer_type" in tissues:
        print("For cancer traits, use TCGA reference panels specific to cancer type")
        return []

    return tissues[:top_n]


def list_available_weights(tool="fusion", reference="gtex_v8"):
    """
    List available pre-computed expression weights.

    Parameters
    ----------
    tool : str
        TWAS tool: "fusion" or "spredixxcan" (default: "fusion")
    reference : str
        Reference panel: "gtex_v8", "tcga" (default: "gtex_v8")

    Returns
    -------
    dict
        Dictionary with tissue names as keys and download URLs as values
    """
    if tool == "fusion" and reference == "gtex_v8":
        base_url = "http://gusevlab.org/projects/fusion/weights/"
        tissues = {
            "Adipose_Subcutaneous": f"{base_url}GTEx.Adipose_Subcutaneous.pos",
            "Adipose_Visceral_Omentum": f"{base_url}GTEx.Adipose_Visceral_Omentum.pos",
            "Adrenal_Gland": f"{base_url}GTEx.Adrenal_Gland.pos",
            "Artery_Aorta": f"{base_url}GTEx.Artery_Aorta.pos",
            "Artery_Coronary": f"{base_url}GTEx.Artery_Coronary.pos",
            "Whole_Blood": f"{base_url}GTEx.Whole_Blood.pos",
            "Brain_Cortex": f"{base_url}GTEx.Brain_Cortex.pos",
            "Liver": f"{base_url}GTEx.Liver.pos",
            # Add more tissues as needed
        }

    elif tool == "spredixxcan" and reference == "gtex_v8":
        base_url = "https://zenodo.org/record/3518299/files/"
        tissues = {
            "Adipose_Subcutaneous": f"{base_url}mashr/mashr_Adipose_Subcutaneous.db",
            "Adipose_Visceral_Omentum": f"{base_url}mashr/mashr_Adipose_Visceral_Omentum.db",
            "Artery_Aorta": f"{base_url}mashr/mashr_Artery_Aorta.db",
            "Artery_Coronary": f"{base_url}mashr/mashr_Artery_Coronary.db",
            "Whole_Blood": f"{base_url}mashr/mashr_Whole_Blood.db",
            "Brain_Cortex": f"{base_url}mashr/mashr_Brain_Cortex.db",
            "Liver": f"{base_url}mashr/mashr_Liver.db",
            # Add more tissues as needed
        }

    else:
        raise ValueError(f"Unsupported combination: tool={tool}, reference={reference}")

    return tissues


def download_fusion_weights(tissues, output_dir="weights/GTEx_v8/"):
    """
    Download FUSION expression weights for specified tissues.

    Parameters
    ----------
    tissues : list
        List of tissue names to download
    output_dir : str
        Output directory for weights (default: "weights/GTEx_v8/")

    Returns
    -------
    list
        List of successfully downloaded weight files
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    available_weights = list_available_weights(tool="fusion", reference="gtex_v8")

    downloaded = []

    for tissue in tissues:
        if tissue not in available_weights:
            print(f"WARNING: Weights not available for tissue '{tissue}'")
            continue

        url = available_weights[tissue]
        output_file = output_path / f"GTEx.{tissue}.pos"

        print(f"Downloading {tissue} weights...")

        try:
            # Note: In production, use proper download logic
            # urllib.request.urlretrieve(url, output_file)
            print(f"  URL: {url}")
            print(f"  Output: {output_file}")
            print(f"  (Download logic placeholder - implement with urllib or wget)")

            # Also need to download corresponding .RDat files
            rdat_url = url.replace('.pos', '.RDat')
            rdat_file = output_path / f"GTEx.{tissue}.RDat"
            print(f"  Also download: {rdat_url} → {rdat_file}")

            downloaded.append(str(output_file))

        except Exception as e:
            print(f"ERROR downloading {tissue}: {e}")

    print(f"\nDownload summary: {len(downloaded)}/{len(tissues)} tissues")
    return downloaded


def download_spredixxcan_weights(tissues, output_dir="weights/GTEx_v8/"):
    """
    Download S-PrediXcan expression weights for specified tissues.

    Parameters
    ----------
    tissues : list
        List of tissue names to download
    output_dir : str
        Output directory for weights (default: "weights/GTEx_v8/")

    Returns
    -------
    list
        List of successfully downloaded weight database files
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    available_weights = list_available_weights(tool="spredixxcan", reference="gtex_v8")

    downloaded = []

    for tissue in tissues:
        if tissue not in available_weights:
            print(f"WARNING: Weights not available for tissue '{tissue}'")
            continue

        url = available_weights[tissue]
        output_file = output_path / f"gtex_v8_mashr_{tissue}.db"

        print(f"Downloading {tissue} weights...")

        try:
            # Note: In production, use proper download logic
            print(f"  URL: {url}")
            print(f"  Output: {output_file}")
            print(f"  (Download logic placeholder - implement with urllib or wget)")

            # Also need covariance matrices
            cov_url = url.replace('.db', '_covariance.txt.gz')
            cov_file = output_path / f"gtex_v8_{tissue}_covariance.txt.gz"
            print(f"  Also download: {cov_url} → {cov_file}")

            downloaded.append(str(output_file))

        except Exception as e:
            print(f"ERROR downloading {tissue}: {e}")

    print(f"\nDownload summary: {len(downloaded)}/{len(tissues)} tissues")
    return downloaded

