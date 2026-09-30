"""sc-integrate-cluster — one self-contained "integrate + cluster" unit.

A consensus *member* skill for ``sc-consensus-integration`` (ADR 0016 / 0029).
It mirrors how ``spatial-domains --method spagcn`` is a self-contained domain
member: ``sc-integrate-cluster --method harmony`` produces a batch-correction
representation **and** clusters on it, emitting the standard ``sc-clustering``
artifact schema so ``ScClusteringArtifactReader`` reads it unchanged.

Why a dedicated skill rather than a flag on ``sc-clustering``: integration is a
separate responsibility (it lives in ``sc-batch-integration`` / ``_lib``) and
coupling it into the clustering skill would make that skill much heavier. Here
the member *composes* the two — integration backends from ``_lib.integration``
plus a fixed-resolution Leiden — which is exactly the consensus member's job.

Members run in a parallel fan-out, so each writes its own ``processed.h5ad``
carrying the representation it clustered on; the consensus driver reads that
per-member embedding (recorded as ``representation_used``) to compute the
integration intrinsic panel. The shared input AnnData does **not** contain
``X_harmony``/``X_scvi`` — those exist only inside each member's output.

Methods:
  - ``none``      cluster the unintegrated ``X_pca`` baseline (reveals which
                  clusters are batch artifacts once integration is applied).
  - ``harmony``   Harmony (CPU, fast, deterministic) → ``X_harmony``.
  - ``scanorama`` Scanorama (CPU) → ``X_scanorama``.
  - ``scvi``      scVI VAE (GPU, **stochastic** — reproducible within tolerance,
                  not bit-identical) → ``X_scvi``. Opt-in; serialise GPU members.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Bootstrap sys.path so `omicsclaw`/`skills` resolve on direct invocation
# (`python sc_integrate_cluster.py --help`) without an editable install. MUST run
# before the OmicsClaw/skills imports below.
_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))

from skills._sdk.checksums import sha256_file  # noqa: E402
from skills._sdk.result import write_result_json  # noqa: E402

# Heavy Scanpy + integration `_lib` imports are deferred to `_load_runtime()`
# (called after argparse) so the direct `--help` contract stays import-light
# even where Scanpy is absent/broken. Populated as module globals on first run.
sc = None
run_harmony_integration = run_scvi_integration = setup_for_integration = None

logger = logging.getLogger(__name__)


def _load_runtime() -> None:
    """Import the Scanpy-based runtime AFTER argument parsing (keeps `--help` light)."""
    global sc, run_harmony_integration, run_scvi_integration, setup_for_integration
    import scanpy as _sc
    from skills.singlecell._lib.integration import (
        run_harmony_integration as _harmony,
        run_scvi_integration as _scvi,
        setup_for_integration as _setup,
    )

    sc = _sc
    run_harmony_integration = _harmony
    run_scvi_integration = _scvi
    setup_for_integration = _setup

SKILL_NAME = "sc-integrate-cluster"
SKILL_VERSION = "0.1.0"

#: obsm key each method writes its representation into.
_REP_KEY = {
    "none": "X_pca",
    "harmony": "X_harmony",
    "scanorama": "X_scanorama",
    "scvi": "X_scvi",
}


def _ensure_pca(adata, *, n_pcs: int, seed: int) -> None:
    """Guarantee an ``X_pca`` baseline (the panel's structure reference)."""
    if "X_pca" not in adata.obsm:
        logger.info("Computing PCA (%d comps) for the X_pca baseline ...", n_pcs)
        sc.tl.pca(adata, n_comps=min(n_pcs, adata.n_vars - 1, adata.n_obs - 1), random_state=seed)


def _integrate_scanorama(adata, batch_key: str, knn: int = 20) -> None:
    """Scanorama integration → ``obsm['X_scanorama']``.

    Uses ``integrate_scanpy``, which populates ``obsm['X_scanorama']`` in place on
    each batch. ``correct_scanpy`` (the path sc-batch-integration historically
    used) returns *corrected expression* with an EMPTY ``obsm``, so reading
    ``X_scanorama`` off it always raised and dropped the scanorama member.
    """
    import scanorama  # noqa: F401 — fail loud (member fails) if unavailable

    batches = [adata[adata.obs[batch_key] == b].copy() for b in adata.obs[batch_key].unique()]
    scanorama.integrate_scanpy(batches, knn=int(knn))
    frames = []
    for cb in batches:
        emb = cb.obsm.get("X_scanorama")
        if emb is None:
            raise RuntimeError("Scanorama did not produce 'X_scanorama' embeddings")
        frames.append(pd.DataFrame(emb, index=cb.obs_names))
    combined = pd.concat(frames, axis=0).loc[adata.obs_names]
    adata.obsm["X_scanorama"] = combined.to_numpy(dtype=float)


def _produce_representation(adata, *, method: str, batch_key: str, n_pcs: int, seed: int,
                            n_top_genes: int) -> str:
    """Run the chosen integration backend; return the obsm key clustered on."""
    if method == "none":
        return "X_pca"
    if batch_key not in adata.obs.columns:
        raise ValueError(f"--batch-key '{batch_key}' not found in adata.obs")
    if adata.obs[batch_key].nunique() < 2:
        raise ValueError(
            f"integration method '{method}' needs >=2 batches in obs['{batch_key}'] "
            f"(found {adata.obs[batch_key].nunique()})"
        )
    if method == "harmony":
        # Reuse the capped ``X_pca`` that ``_ensure_pca`` already built (it clamps
        # n_comps to n_obs-1 / n_vars-1). ``use_pca=True`` would recompute PCA at the
        # uncapped ``n_pcs`` and Scanpy would raise on small datasets, dropping the
        # Harmony member from the default consensus.
        run_harmony_integration(adata, batch_key, use_pca=False, random_state=seed)
    elif method == "scanorama":
        _integrate_scanorama(adata, batch_key)
    elif method == "scvi":
        # scVI trains a VAE on raw counts; HVG setup first. Stochastic/GPU.
        setup_for_integration(adata, batch_key, n_top_genes=n_top_genes)
        run_scvi_integration(adata, batch_key, random_state=seed)
    else:  # pragma: no cover — argparse choices guard this
        raise ValueError(f"unknown method {method!r}")
    key = _REP_KEY[method]
    if key not in adata.obsm:
        raise RuntimeError(f"integration method '{method}' did not produce obsm['{key}']")
    return key


def _cluster(adata, *, rep_key: str, cluster_method: str, resolution: float,
             n_neighbors: int, seed: int) -> None:
    sc.pp.neighbors(adata, n_neighbors=n_neighbors, use_rep=rep_key, random_state=seed)
    kwargs = {"resolution": resolution, "random_state": seed, "key_added": cluster_method}
    cluster_fn = sc.tl.leiden if cluster_method == "leiden" else sc.tl.louvain
    try:
        cluster_fn(adata, flavor="igraph", n_iterations=2, directed=False, **kwargs)
    except TypeError:
        cluster_fn(adata, **kwargs)


def _synthesise_demo_adata(seed: int = 0):
    """Small deterministic multi-batch AnnData for ``--demo`` (smoke only).

    2 batches x 3 cell types x 40 cells over 120 genes, with a per-batch additive
    shift (the technical effect integration should remove). Carries raw
    ``layers['counts']``, a log-normalised ``X``, and ``obs['batch']`` — enough
    for ``--method none`` (X_pca baseline) to integrate + cluster end to end.
    """
    import anndata as ad

    rng = np.random.default_rng(seed)
    n_types, n_per, n_batches, n_genes = 3, 40, 2, 120
    programs = rng.gamma(shape=1.0, scale=1.0, size=(n_types, n_genes)) * 3.0
    rows: list[np.ndarray] = []
    batches: list[str] = []
    types: list[str] = []
    for b in range(n_batches):
        shift = rng.normal(b * 1.5, 0.2, size=n_genes)
        for t in range(n_types):
            mean = np.clip(programs[t] + shift, 0.0, None)
            rows.append(rng.poisson(mean, size=(n_per, n_genes)))
            batches.extend([f"batch{b}"] * n_per)
            types.extend([f"type{t}"] * n_per)
    counts = np.vstack(rows).astype(np.float32)
    adata = ad.AnnData(counts.copy())
    adata.obs_names = [f"cell{i}" for i in range(adata.n_obs)]
    adata.var_names = [f"gene{j}" for j in range(n_genes)]
    adata.obs["batch"] = batches
    adata.obs["cell_type"] = types
    adata.layers["counts"] = counts
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    return adata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Integrate + cluster (consensus member).")
    parser.add_argument("--input", required=False, help="Preprocessed AnnData (.h5ad) with a batch key")
    parser.add_argument("--output", required=True, help="Member output directory")
    parser.add_argument(
        "--demo", action="store_true",
        help="Run on a small synthetic multi-batch AnnData instead of --input.",
    )
    parser.add_argument(
        "--method", choices=["none", "harmony", "scanorama", "scvi"], default="none",
        help="Integration backend (none = unintegrated X_pca baseline)",
    )
    parser.add_argument("--batch-key", default="batch", help="obs column with batch labels")
    parser.add_argument("--cluster-method", choices=["leiden", "louvain"], default="leiden")
    parser.add_argument("--resolution", type=float, default=1.0, help="Fixed clustering resolution")
    parser.add_argument("--n-neighbors", type=int, default=15)
    parser.add_argument("--n-pcs", type=int, default=50)
    parser.add_argument("--n-top-genes", type=int, default=2000, help="HVGs for scVI setup")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    if not args.demo and not args.input:
        parser.error("provide --input <file> or --demo")

    _load_runtime()  # heavy Scanpy import deferred until after argparse
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    output_dir = Path(args.output)
    figure_dir = output_dir / "figure_data"
    figure_dir.mkdir(parents=True, exist_ok=True)

    adata = _synthesise_demo_adata(seed=args.seed) if args.demo else sc.read_h5ad(args.input)
    _ensure_pca(adata, n_pcs=args.n_pcs, seed=args.seed)

    rep_key = _produce_representation(
        adata, method=args.method, batch_key=args.batch_key,
        n_pcs=args.n_pcs, seed=args.seed, n_top_genes=args.n_top_genes,
    )
    _cluster(
        adata, rep_key=rep_key, cluster_method=args.cluster_method,
        resolution=args.resolution, n_neighbors=args.n_neighbors, seed=args.seed,
    )

    cluster_key = args.cluster_method
    labels = adata.obs[cluster_key].astype(str)
    n_clusters = int(labels.nunique())
    n_batches = int(adata.obs[args.batch_key].nunique()) if args.batch_key in adata.obs else 1
    rep = np.asarray(adata.obsm[rep_key])

    # --- artifacts the reader (labels) + driver panel (embedding) consume ----
    points = pd.DataFrame(
        {
            "cell_id": adata.obs_names.astype(str),
            "embedding_key": rep_key,
            "coord1": rep[:, 0],
            "coord2": rep[:, 1] if rep.shape[1] > 1 else 0.0,
            cluster_key: labels.to_numpy(),
        }
    )
    if args.batch_key in adata.obs:
        points["batch"] = adata.obs[args.batch_key].astype(str).to_numpy()
    points.to_csv(figure_dir / "embedding_points.csv", index=False)

    pd.DataFrame(
        [
            {"metric": "method", "value": args.method},
            {"metric": "representation_used", "value": rep_key},
            {"metric": "cluster_method", "value": cluster_key},
            {"metric": "n_cells", "value": int(adata.n_obs)},
            {"metric": "n_clusters", "value": n_clusters},
            {"metric": "resolution", "value": args.resolution},
            {"metric": "batch_key", "value": args.batch_key},
            {"metric": "n_batches", "value": n_batches},
        ]
    ).to_csv(figure_dir / "clustering_summary.csv", index=False)

    adata.write_h5ad(output_dir / "processed.h5ad")

    summary = {
        "method": args.method,
        "representation_used": rep_key,
        "cluster_method": cluster_key,
        "n_clusters": n_clusters,
        "n_cells": int(adata.n_obs),
        "n_batches": n_batches,
        "resolution": args.resolution,
    }
    data = {"params": {k: getattr(args, k) for k in (
        "method", "batch_key", "cluster_method", "resolution", "n_neighbors", "n_pcs", "seed",
    )}}
    try:
        checksum = sha256_file(args.input)
    except Exception:  # noqa: BLE001 — checksum is best-effort provenance
        checksum = ""
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, data, checksum)

    print(f"Success: {SKILL_NAME}")
    print(f"  Method: {args.method}  ->  {rep_key}")
    print(f"  Clusters: {n_clusters}  (resolution={args.resolution}, batches={n_batches})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
