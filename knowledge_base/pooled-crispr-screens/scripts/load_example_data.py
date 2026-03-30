"""
Load Example Perturb-seq Data

Provides the Papalexi & Satija 2021 ECCITE-seq CRISPRi dataset for testing.
Source: scPerturb (Peidli et al. 2024, Nature Methods) via Zenodo.

Dataset: THP-1 cells (human monocytic leukemia) with CRISPRi targeting
immune checkpoint genes. ~20,700 cells, 99 perturbations, 107 guides.

Reference: Papalexi et al. (2021) "Characterizing the molecular regulation
of inhibitory immune checkpoints with multimodal single-cell screens"
Nature Genetics 53:322-331.
"""

import os
import re
import scanpy as sc
import pandas as pd
import numpy as np
from pathlib import Path


# Zenodo download URL for scPerturb-formatted h5ad
_ZENODO_URL = (
    "https://zenodo.org/records/13350497/files/"
    "PapalexiSatija2021_eccite_RNA.h5ad?download=1"
)
_EXPECTED_SIZE_MB = 140  # Approximate file size


def load_example_data(dataset='papalexi2021', download_dir='data'):
    """
    Load example Perturb-seq data for testing workflow.

    Parameters
    ----------
    dataset : str
        Which dataset to load:
        - 'papalexi2021': Papalexi & Satija 2021 CRISPRi ECCITE-seq (~140MB download)
        - 'demo': Small synthetic dataset for quick offline testing (~2 min)
    download_dir : str
        Directory to cache downloaded data

    Returns
    -------
    dict
        Dictionary with:
        - 'adata_list': List of AnnData objects (one per library/batch)
        - 'mapping_files': List of sgRNA mapping file paths
        - 'metadata': Dictionary with dataset information

    Examples
    --------
    >>> data = load_example_data()
    >>> adata_list = data['adata_list']
    >>> mapping_files = data['mapping_files']
    """

    if dataset == 'papalexi2021':
        return _load_papalexi2021(download_dir)
    elif dataset == 'demo':
        print("Generating synthetic demo dataset (offline fallback)...")
        return _generate_demo_data()
    else:
        raise ValueError(
            f"Unknown dataset: {dataset}. Choose 'papalexi2021' or 'demo'."
        )


def _download_if_needed(download_dir):
    """Download Papalexi 2021 h5ad from Zenodo if not cached."""
    download_dir = Path(download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)

    h5ad_path = download_dir / "papalexi2021_eccite_rna.h5ad"

    if h5ad_path.exists():
        size_mb = h5ad_path.stat().st_size / (1024 * 1024)
        if size_mb > 100:  # Sanity check: file should be ~140MB
            print(f"Using cached dataset: {h5ad_path} ({size_mb:.0f} MB)")
            return h5ad_path
        else:
            print(f"Cached file too small ({size_mb:.0f} MB), re-downloading...")

    print(f"Downloading Papalexi 2021 ECCITE-seq dataset (~{_EXPECTED_SIZE_MB} MB)...")
    print(f"Source: scPerturb / Zenodo")

    import urllib.request
    try:
        urllib.request.urlretrieve(_ZENODO_URL, str(h5ad_path))
        size_mb = h5ad_path.stat().st_size / (1024 * 1024)
        print(f"  Downloaded: {h5ad_path} ({size_mb:.0f} MB)")
        return h5ad_path
    except Exception as e:
        if h5ad_path.exists():
            h5ad_path.unlink()
        raise RuntimeError(
            f"Download failed: {e}\n"
            f"Manual download: visit https://zenodo.org/records/13350497\n"
            f"  File: PapalexiSatija2021_eccite_RNA.h5ad\n"
            f"  Save to: {h5ad_path}"
        )


def _parse_perturbation(pert_id):
    """
    Extract gene name and guide number from scPerturb perturbation ID.

    In this dataset, the 'perturbation' column contains guide-level IDs
    (e.g., "ATF2g1", "IFNGR2g2") not gene-level names.

    Returns (gene_name, guide_number_str).

    Examples:
        'ATF2g1'    → ('ATF2', '1')
        'IFNGR2g2'  → ('IFNGR2', '2')
        'STAT5Ag3'  → ('STAT5A', '3')
        'NFKBIAg1'  → ('NFKBIA', '1')
        'control'   → ('non-targeting', '0')
    """
    if pert_id == 'control':
        return 'non-targeting', '0'
    match = re.match(r'(.+?)g(\d+)$', pert_id)
    if match:
        return match.group(1), match.group(2)
    return pert_id, '1'


def _reformat_sgrna(pert_id, guide_id):
    """
    Reformat to GENE_sgRNAn format expected by the workflow.

    Examples:
        ('ATF2g1', 'ATF2g1')     → 'ATF2_sgRNA1'
        ('IFNGR2g2', 'IFNGR2g2') → 'IFNGR2_sgRNA2'
        ('control', 'NTg7')      → 'non-targeting_sgRNA7'
    """
    if pert_id == 'control':
        match = re.search(r'g(\d+)$', guide_id)
        guide_num = match.group(1) if match else '0'
        return f"non-targeting_sgRNA{guide_num}"

    gene, num = _parse_perturbation(pert_id)
    return f"{gene}_sgRNA{num}"


def _load_papalexi2021(download_dir):
    """
    Load Papalexi & Satija 2021 ECCITE-seq CRISPRi screen.

    Dataset details:
    - Cell type: THP-1 (human acute monocytic leukemia)
    - Screen: CRISPRi targeting immune checkpoint regulators
    - ~20,700 cells x 18,649 genes
    - 25 target genes with ~4 guides each (98 guide-level perturbations + control)
    - 5 batches (rep1-tx, rep2-tx, rep2-ctrl, rep3-tx, rep4-tx)
    """
    h5ad_path = _download_if_needed(download_dir)

    print("\nLoading and formatting Papalexi 2021 dataset...")
    adata_full = sc.read_h5ad(str(h5ad_path))

    # Validate expected columns
    required_cols = ['perturbation', 'guide_id']
    missing = [c for c in required_cols if c not in adata_full.obs.columns]
    if missing:
        raise ValueError(
            f"Missing expected columns: {missing}. "
            f"Available: {list(adata_full.obs.columns)}"
        )

    # Determine batch column (hto or similar)
    batch_col = None
    for candidate in ['hto', 'batch', 'replicate', 'library']:
        if candidate in adata_full.obs.columns:
            batch_col = candidate
            break

    if batch_col is None:
        # Use single batch if no batch column found
        adata_full.obs['_batch'] = 'lib1'
        batch_col = '_batch'

    batches = sorted(adata_full.obs[batch_col].unique())
    print(f"  Cells: {adata_full.n_obs:,}")
    print(f"  Genes: {adata_full.n_vars:,}")
    print(f"  Perturbations: {adata_full.obs['perturbation'].nunique()}")
    print(f"  Guides: {adata_full.obs['guide_id'].nunique()}")
    print(f"  Batches ({batch_col}): {len(batches)}")

    # Reformat sgRNA names for workflow compatibility
    print("  Reformatting sgRNA names (GENE_sgRNAn format)...")
    adata_full.obs['_sgRNA_formatted'] = [
        _reformat_sgrna(p, g)
        for p, g in zip(adata_full.obs['perturbation'], adata_full.obs['guide_id'])
    ]

    # Extract gene names from guide-level perturbation IDs
    # e.g., "ATF2g1" → "ATF2", "control" → "non-targeting"
    adata_full.obs['_gene_formatted'] = [
        _parse_perturbation(p)[0]
        for p in adata_full.obs['perturbation']
    ]

    # Count controls
    n_control = (adata_full.obs['_gene_formatted'] == 'non-targeting').sum()
    n_target = adata_full.n_obs - n_control
    print(f"  Control cells: {n_control:,}")
    print(f"  Perturbed cells: {n_target:,}")

    # Split by batch into per-library AnnData objects
    # Skip tiny batches (<50 cells) that would fail downstream QC
    min_cells_per_batch = 50
    valid_batches = [
        b for b in batches
        if (adata_full.obs[batch_col] == b).sum() >= min_cells_per_batch
    ]
    skipped = set(batches) - set(valid_batches)
    if skipped:
        print(f"  Skipping small batches (<{min_cells_per_batch} cells): {sorted(skipped)}")

    output_dir = Path(download_dir) / 'papalexi2021_split'
    output_dir.mkdir(parents=True, exist_ok=True)

    adata_list = []
    mapping_files = []
    batch_labels = []

    for i, batch in enumerate(valid_batches):
        batch_mask = adata_full.obs[batch_col] == batch
        adata_batch = adata_full[batch_mask].copy()

        # Create clean AnnData without scPerturb metadata columns
        # (the workflow will add gene/sgRNA from mapping files)
        adata_clean = sc.AnnData(
            X=adata_batch.X.copy(),
            obs=pd.DataFrame(index=adata_batch.obs_names.copy()),
            var=pd.DataFrame(index=adata_batch.var_names.copy()),
        )

        # Add basic QC metrics
        if hasattr(adata_batch.X, 'toarray'):
            X_dense = adata_batch.X.toarray()
        else:
            X_dense = np.asarray(adata_batch.X)
        adata_clean.obs['n_counts'] = X_dense.sum(axis=1)
        adata_clean.obs['n_genes'] = (X_dense > 0).sum(axis=1)

        # Mitochondrial fraction
        mito_mask = adata_clean.var_names.str.startswith('MT-')
        if mito_mask.sum() > 0:
            mito_counts = X_dense[:, mito_mask].sum(axis=1)
            adata_clean.obs['percent_mito'] = mito_counts / (adata_clean.obs['n_counts'] + 1e-6)
        else:
            adata_clean.obs['percent_mito'] = 0.0

        adata_list.append(adata_clean)

        # Generate sgRNA mapping file
        batch_label = f"lib{i + 1}"
        batch_labels.append(batch_label)
        mapping_file = output_dir / f"mapped_sgRNA_to_cell_{batch_label}.txt"

        mapping_df = pd.DataFrame({
            'cell_barcode': adata_batch.obs_names,
            'sgRNA': adata_batch.obs['_sgRNA_formatted'].values,
        })
        mapping_df.to_csv(mapping_file, sep='\t', index=False, header=False)
        mapping_files.append(str(mapping_file))

        n_cells = adata_clean.n_obs
        n_perts = adata_batch.obs['_gene_formatted'].nunique()
        print(f"  {batch_label} ({batch}): {n_cells:,} cells, {n_perts} perturbations")

    # Build metadata
    all_genes = sorted(adata_full.obs['_gene_formatted'].unique())
    target_genes = [g for g in all_genes if g != 'non-targeting']
    n_guides = adata_full.obs['guide_id'].nunique()

    metadata = {
        'dataset': 'papalexi2021',
        'description': 'Papalexi & Satija 2021 ECCITE-seq CRISPRi screen',
        'cell_type': 'THP-1 (human acute monocytic leukemia)',
        'screen_type': 'CRISPRi',
        'organism': 'human',
        'n_libraries': len(adata_list),
        'n_cells_total': adata_full.n_obs,
        'n_genes_expression': adata_full.n_vars,
        'n_target_genes': len(target_genes),
        'n_guides': n_guides,
        'guides_per_gene': round(n_guides / max(len(target_genes), 1), 1),
        'n_controls': 1,  # single "non-targeting" group
        'control_group': 'non-targeting',
        'expected_direction': 'down',  # CRISPRi = knockdown
        'batch_labels': batch_labels,
        'original_batches': list(batches),
        'target_genes': target_genes,
        'reference': 'Papalexi et al. (2021) Nature Genetics 53:322-331',
        'source': 'scPerturb (Peidli et al. 2024) via Zenodo',
    }

    print(f"\n✓ Papalexi 2021 dataset loaded successfully!")
    print(f"  {len(adata_list)} libraries, {adata_full.n_obs:,} total cells")
    print(f"  {len(target_genes)} target genes ({n_guides} guides) + non-targeting controls")
    print(f"  Screen type: CRISPRi (expected direction: down)")
    print(f"  Cell type: THP-1 (use immune cell QC thresholds)")

    return {
        'adata_list': adata_list,
        'mapping_files': mapping_files,
        'metadata': metadata,
    }


def _generate_demo_data():
    """
    Generate small synthetic Perturb-seq dataset for offline testing.

    Creates 2 libraries with:
    - 500 cells per library (1000 total)
    - 5000 genes
    - 20 perturbations (15 targets + 5 controls)
    - Quick runtime: ~1-2 minutes
    """
    np.random.seed(42)

    output_dir = Path('data/example_demo')
    output_dir.mkdir(parents=True, exist_ok=True)

    n_cells_per_lib = 500
    n_genes = 5000
    n_targets = 15
    n_controls = 5

    gene_names = [f"GENE{i:05d}" for i in range(n_genes)]

    # Define perturbations
    strong_hits = [f"TARGET{i:02d}" for i in range(5)]
    moderate_hits = [f"TARGET{i:02d}" for i in range(5, 10)]
    weak_hits = [f"TARGET{i:02d}" for i in range(10, 15)]
    control_genes = [f"non-targeting" for _ in range(n_controls)]
    control_sgrna_labels = [f"non-targeting_sgRNA{i+1}" for i in range(n_controls)]

    all_perturbations = strong_hits + moderate_hits + weak_hits + ['non-targeting']
    all_sgrnas = {}
    for gene in strong_hits + moderate_hits + weak_hits:
        all_sgrnas[gene] = [f"{gene}_sgRNA{j+1}" for j in range(2)]
    all_sgrnas['non-targeting'] = control_sgrna_labels

    adata_list = []
    mapping_files = []

    for lib_idx in range(2):
        X = np.random.negative_binomial(5, 0.5, size=(n_cells_per_lib, n_genes))

        cell_barcodes = [f"LIB{lib_idx+1}_{i:04d}" for i in range(n_cells_per_lib)]
        cell_perturbations = np.random.choice(all_perturbations, size=n_cells_per_lib)

        # Inject effects
        for pert in all_perturbations:
            cells = np.where(cell_perturbations == pert)[0]
            if len(cells) == 0 or pert == 'non-targeting':
                continue

            if pert in strong_hits:
                n_de = np.random.randint(50, 100)
                effect = 2.0
            elif pert in moderate_hits:
                n_de = np.random.randint(10, 30)
                effect = 1.0
            else:
                n_de = np.random.randint(0, 5)
                effect = 0.5

            if n_de > 0:
                de_idx = np.random.choice(n_genes, size=n_de, replace=False)
                for gi in de_idx:
                    direction = -1 if np.random.random() < 0.6 else 1
                    fc = 2 ** (direction * effect * np.random.uniform(0.7, 1.3))
                    X[cells, gi] = (X[cells, gi] * fc).astype(int)

        adata = sc.AnnData(
            X=X,
            obs=pd.DataFrame(index=cell_barcodes),
            var=pd.DataFrame(index=gene_names),
        )
        adata.obs['n_counts'] = adata.X.sum(axis=1)
        adata.obs['n_genes'] = (adata.X > 0).sum(axis=1)
        adata_list.append(adata)

        # Mapping file
        mapping_file = output_dir / f"mapped_sgRNA_to_cell_lib{lib_idx+1}.txt"
        rows = []
        for bc, pert in zip(cell_barcodes, cell_perturbations):
            sgrna = np.random.choice(all_sgrnas[pert])
            rows.append([bc, sgrna])
        pd.DataFrame(rows).to_csv(mapping_file, sep='\t', index=False, header=False)
        mapping_files.append(str(mapping_file))

    print("✓ Demo dataset generated successfully!")
    print(f"  2 libraries, {n_cells_per_lib * 2} total cells, {len(all_perturbations)} perturbations")

    return {
        'adata_list': adata_list,
        'mapping_files': mapping_files,
        'metadata': {
            'dataset': 'demo',
            'n_libraries': 2,
            'n_cells_total': n_cells_per_lib * 2,
            'n_genes': n_genes,
            'n_perturbations': len(all_perturbations),
            'control_group': 'non-targeting',
            'expected_direction': 'down',
        },
    }


if __name__ == '__main__':
    print("Testing example data loading...")
    print("=" * 60)
    data = load_example_data(dataset='papalexi2021')
    print(f"\nLoaded {len(data['adata_list'])} libraries")
    print(f"Mapping files: {len(data['mapping_files'])}")
    print(f"Metadata keys: {list(data['metadata'].keys())}")

