"""LIANA on PBMC expression with explicitly simulated coordinates."""
from pathlib import Path


def input_data(path: Path):
    import numpy as np
    from skills._sdk.notebook import load_demo
    data = load_demo('pbmc3k_processed').raw.to_adata()
    keep = data.obs.groupby('louvain', observed=True).head(30).index
    data = data[keep].copy()
    data.obs['leiden'] = data.obs['louvain'].copy()
    data.obsm['spatial'] = np.column_stack((np.arange(data.n_obs) % 20, np.arange(data.n_obs) // 20)).astype(float)
    data.uns['synthetic_coordinates'] = True
    path.parent.mkdir(parents=True, exist_ok=True)
    data.write_h5ad(path)


def register(Case, Skill):
    environment = {key: '1' for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMBA_NUM_THREADS')}
    environment['PYTHONHASHSEED'] = '0'
    return {'spatial-communication': Skill('skills/spatial/spatial-communication/spatial_communication.py',
        'tests.parity.spatial_communication:api_communication', {
            'liana': Case(('--liana-n-perms', '10'), input=input_data, environment=environment),
        })}


def api_communication(case, *, input_path):
    import scanpy as sc
    from skills._sdk.notebook import load_skill
    data = sc.read_h5ad(input_path)
    library = load_skill('spatial-communication')
    library.communicate(data, n_perms=10)
    return {'adata': data, 'tables': {'lr_interactions.csv': library.interactions(data)}}
