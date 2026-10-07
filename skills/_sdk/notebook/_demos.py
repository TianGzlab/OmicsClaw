"""Deterministic demo generators used by the notebook dataset registry.

Add a generator here when a skill example needs it, and name it in
``_io.DEMOS``. Generators return AnnData; ``load_demo`` caches the file and
records its hash. Keep optional backend imports inside the generator.
"""


def velocity_simulation():
    """Seeded scVelo kinetic simulation with genuine simulated splicing dynamics."""
    import scvelo as scv

    return scv.datasets.simulation(n_vars=40, random_seed=0)


def perturbseq_synthetic():
    """Two downregulated KO gene blocks, matched controls and a WNT-name decoy."""
    import anndata as ad
    import numpy as np

    rng = np.random.default_rng(0)
    base = rng.gamma(2., 1., size=80)
    rows, targets, replicates = [], [], []
    for target, block in [('NT', None), ('KO_A', slice(0, 10)), ('WNT3', slice(10, 20))]:
        profile = base.copy()
        if block is not None:
            profile[block] *= .05
        for replicate in ('r1', 'r2'):
            for _ in range(30):
                library = rng.integers(1500, 3200)
                rows.append(rng.poisson(np.clip(profile / profile.sum() * library, .05, None)))
                targets.append(target)
                replicates.append(replicate)
    result = ad.AnnData(np.asarray(rows, dtype=float))
    result.obs_names = [f'cell_{i}' for i in range(result.n_obs)]
    genes = ['KO_A', 'NTRK1', 'NT5E'] + [f'Gene{i}' for i in range(3, 80)]
    genes[10] = 'WNT3'
    result.var_names = genes
    result.obs['perturbation'] = targets
    result.obs['perturbation'] = result.obs['perturbation'].astype('category')
    result.obs['target_gene'] = targets
    result.obs['sgRNA'] = [target + '_sg1' for target in targets]
    result.obs['replicate'] = replicates
    result.obs['replicate'] = result.obs['replicate'].astype('category')
    result.layers['counts'] = result.X.copy()
    result.uns['synthetic_effect_targets'] = ['KO_A', 'WNT3']
    result.uns['synthetic_downregulated_gene_sets'] = {'KO_A': genes[:10], 'WNT3': genes[10:20]}
    mapping = result.obs[['sgRNA', 'target_gene']].copy()
    mapping.insert(0, 'barcode', result.obs_names)
    result.uns['guide_mapping'] = mapping
    return result


def atac_synthetic():
    """Three groups with distinct accessible-peak blocks and six low-depth cells."""
    import anndata as ad
    import numpy as np

    rng = np.random.default_rng(7)
    matrix = rng.binomial(1, 0.006, size=(180, 2000)).astype(np.float32)
    labels = []
    for group in range(3):
        rows = slice(group * 60, (group + 1) * 60)
        peaks = slice(group * 500, (group + 1) * 500)
        matrix[rows, peaks] = np.maximum(matrix[rows, peaks], rng.binomial(1, 0.38, size=(60, 500)).astype(np.float32))
        matrix[rows, 1500:1650] = np.maximum(matrix[rows, 1500:1650], rng.binomial(1, 0.16, size=(60, 150)).astype(np.float32))
        labels.extend([f"cluster_{group + 1}"] * 60)
    low_quality = rng.choice(180, size=6, replace=False)
    matrix[low_quality] = rng.binomial(1, 0.01, size=(6, 2000)).astype(np.float32)
    result = ad.AnnData(matrix)
    result.obs_names = [f"cell_{index:04d}" for index in range(180)]
    result.var_names = [f"chr1:{1000 + index * 50}-{1049 + index * 50}" for index in range(2000)]
    result.obs["demo_group"] = labels
    result.obs["demo_group"] = result.obs["demo_group"].astype("category")
    return result


def multisample_synthetic():
    """Eight samples with a threefold increase in one cell type after treatment."""
    import anndata as ad
    import numpy as np

    rng = np.random.default_rng(0)
    sample_ids, conditions, cell_types = [], [], []
    for condition, enriched_counts in [('control', [28, 31, 33, 29]), ('treated', [88, 92, 95, 90])]:
        for replicate, enriched in enumerate(enriched_counts, 1):
            counts = [enriched, 100, 300 - enriched - 100]
            for cell_type, count in zip(['Enriched', 'Stable', 'Other'], counts):
                sample_ids.extend([f'{condition}_{replicate}'] * count)
                conditions.extend([condition] * count)
                cell_types.extend([cell_type] * count)
    result = ad.AnnData(rng.poisson(2, size=(len(sample_ids), 40)).astype('float32'))
    result.obs_names = [f'cell_{i}' for i in range(result.n_obs)]
    result.var_names = [f'gene_{i}' for i in range(result.n_vars)]
    result.obs['sample'] = sample_ids
    result.obs['condition'] = conditions
    result.obs['cell_type'] = cell_types
    result.layers['counts'] = result.X.copy()
    result.uns['synthetic_enriched_cell_type'] = 'Enriched'
    return result
