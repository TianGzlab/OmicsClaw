"""Helpers for gene program discovery."""

from __future__ import annotations

import logging
import tempfile
from typing import Any

import numpy as np
import pandas as pd
import scanpy as sc
from anndata import AnnData
from sklearn.decomposition import NMF

logger = logging.getLogger(__name__)


def make_demo_gene_program_adata(seed: int = 0) -> AnnData:
    rng = np.random.default_rng(seed)
    n_cells, n_genes = 150, 90
    genes = [f"Gene{i}" for i in range(n_genes)]
    base = rng.gamma(2.0, 1.0, size=(3, n_genes))
    base[0, :10] += 5
    base[1, 10:20] += 5
    base[2, 20:30] += 5
    rows = []
    labels = []
    for i in range(n_cells):
        state = i % 3
        lib = rng.integers(1800, 4200)
        mu = base[state] / base[state].sum() * lib
        rows.append(rng.poisson(np.clip(mu, 0.05, None)))
        labels.append(f"state_{state+1}")
    adata = AnnData(np.asarray(rows, dtype=float))
    adata.var_names = genes
    adata.obs_names = [f"cell_{i}" for i in range(adata.n_obs)]
    adata.obs["state"] = pd.Categorical(labels)
    adata.layers["counts"] = adata.X.copy()
    sc.pp.normalize_total(adata)
    sc.pp.log1p(adata)
    return adata


def _matrix_from_adata(adata: AnnData, layer: str | None = None) -> np.ndarray:
    mat = adata.layers[layer] if layer else adata.X
    if hasattr(mat, "toarray"):
        mat = mat.toarray()
    mat = np.asarray(mat, dtype=float)
    mat = np.clip(mat, 0.0, None)
    return mat


def run_nmf_programs(
    adata: AnnData,
    *,
    n_programs: int = 6,
    seed: int = 0,
    max_iter: int = 400,
    layer: str | None = None,
    top_genes: int = 30,
) -> dict[str, Any]:
    X = _matrix_from_adata(adata, layer=layer)
    model = NMF(n_components=n_programs, init="nndsvda", random_state=seed, max_iter=max_iter)
    usage = model.fit_transform(X)
    weights = model.components_
    usage_df = pd.DataFrame(usage, index=adata.obs_names, columns=[f"program_{i+1}" for i in range(n_programs)])
    genes = []
    for i in range(n_programs):
        idx = np.argsort(weights[i])[::-1][:top_genes]
        for rank, gi in enumerate(idx, start=1):
            genes.append({
                "program": f"program_{i+1}",
                "rank": rank,
                "gene": str(adata.var_names[gi]),
                "weight": float(weights[i, gi]),
            })
    top_df = pd.DataFrame(genes)
    return {
        "method": "nmf",
        "model": model,
        "usage": usage_df,
        "weights": pd.DataFrame(weights, columns=adata.var_names, index=[f"program_{i+1}" for i in range(n_programs)]),
        "top_genes": top_df,
        "reconstruction_err": float(model.reconstruction_err_),
    }


def run_cnmf_programs(
    adata: AnnData,
    *,
    n_programs: int = 6,
    seed: int = 0,
    max_iter: int = 200,
    layer: str | None = None,
    top_genes: int = 30,
) -> dict[str, Any]:
    try:
        from cnmf import cNMF  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ImportError("cNMF backend requires the `cnmf` package. Use `--method nmf` or install `cnmf`.") from exc

    source_layer = layer
    if source_layer is None and "counts" in adata.layers:
        source_layer = "counts"

    counts = _matrix_from_adata(adata, layer=source_layer)
    counts_adata = AnnData(counts.copy())
    counts_adata.obs_names = adata.obs_names.copy()
    counts_adata.var_names = adata.var_names.copy()
    counts_adata.obs = adata.obs.copy()
    counts_adata.var = adata.var.copy()

    n_replicates = max(8, min(24, max(8, n_programs * 3)))
    n_highvar = min(2000, counts_adata.n_vars)
    density_threshold = 10.0
    local_neighborhood_size = 0.5

    with tempfile.TemporaryDirectory(prefix="omicsclaw_cnmf_") as tmpdir:
        counts_path = f"{tmpdir}/counts.h5ad"
        counts_adata.write_h5ad(counts_path)

        cnmf_obj = cNMF(output_dir=tmpdir, name="omicsclaw_cnmf")
        cnmf_obj.prepare(
            counts_fn=counts_path,
            components=[n_programs],
            n_iter=n_replicates,
            seed=seed,
            num_highvar_genes=n_highvar,
            max_NMF_iter=max_iter,
        )
        cnmf_obj.factorize(worker_i=0, total_workers=1)
        cnmf_obj.combine(components=[n_programs])
        cnmf_obj.consensus(
            k=n_programs,
            density_threshold=density_threshold,
            local_neighborhood_size=local_neighborhood_size,
            show_clustering=False,
            close_clustergram_fig=True,
        )
        usage, spectra_scores, spectra_tpm, ranked_genes = cnmf_obj.load_results(
            K=n_programs,
            density_threshold=density_threshold,
        )

    program_names = [f"program_{i+1}" for i in range(n_programs)]
    usage_df = pd.DataFrame(usage).copy()
    usage_df.index = adata.obs_names.copy()
    usage_df.columns = program_names

    score_df = pd.DataFrame(spectra_scores).copy()
    score_df.columns = program_names
    weights_df = score_df.T
    weights_df.index = program_names
    weights_df.columns = score_df.index.astype(str)

    ranked_df = pd.DataFrame(ranked_genes).copy()
    ranked_df.columns = program_names
    rows: list[dict[str, Any]] = []
    for program in program_names:
        genes = ranked_df[program].dropna().astype(str).tolist()[:top_genes]
        for rank, gene in enumerate(genes, start=1):
            rows.append(
                {
                    "program": program,
                    "rank": rank,
                    "gene": gene,
                    "weight": float(weights_df.loc[program, gene]) if gene in weights_df.columns else np.nan,
                }
            )
    top_df = pd.DataFrame(rows)

    tpm_df = pd.DataFrame(spectra_tpm).copy()
    tpm_df.columns = program_names

    return {
        "method": "cnmf",
        "usage": usage_df,
        "weights": weights_df,
        "top_genes": top_df,
        "spectra_tpm": tpm_df,
        "reconstruction_err": float("nan"),
        "cnmf_replicates": int(n_replicates),
        "density_threshold": float(density_threshold),
        "source_layer": source_layer,
    }
