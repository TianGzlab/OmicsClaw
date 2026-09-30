"""Write subsampled copies of an input: ``python -m omicsclaw.ensemble.tuning.subsample``.

Each copy keeps a fixed fraction of the observations, drawn without
replacement with its own seed, and gets a new expression neighbour graph
built from the input's ``X_pca`` (not recomputed) with the neighbour count the
input's graph was built with (15 when not recorded). Everything else is the
input's, subset.

Prints ``SUBSAMPLE=`` and a JSON object ``{"files": [{"seed", "path", "n_obs"}]}``.
Runs under the skill interpreter.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

__all__ = ["draw", "main", "write_subsamples"]

DEFAULT_NEIGHBOURS = 15


def draw(n_obs: int, fraction: float, seed: int):
    """Sorted indices of ``round(fraction * n_obs)`` observations drawn with *seed*."""
    import numpy as np

    size = int(round(fraction * n_obs))
    rng = np.random.default_rng(seed)
    return np.sort(rng.choice(n_obs, size=size, replace=False))


def _neighbour_params(adata) -> dict[str, Any]:
    params = dict((adata.uns.get("neighbors") or {}).get("params") or {})
    n_neighbors = int(params.get("n_neighbors") or DEFAULT_NEIGHBOURS)
    n_pcs = params.get("n_pcs")
    return {"n_neighbors": n_neighbors, "n_pcs": int(n_pcs) if n_pcs else None,
            "random_state": int(params.get("random_state", 0) or 0)}


def write_subsamples(input_path: Path, output_dir: Path, seeds: Sequence[int], fraction: float) -> list[dict[str, Any]]:
    """Write ``sub01.h5ad``, ``sub02.h5ad``, … (one per seed, in order) and describe them.

    :raises ValueError: The input has no ``X_pca``.
    """
    import anndata
    import scanpy as sc

    adata = anndata.read_h5ad(input_path)
    if "X_pca" not in adata.obsm:
        raise ValueError(f"{input_path} has no obsm['X_pca']")
    neighbours = _neighbour_params(adata)
    output_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for index, seed in enumerate(seeds, start=1):
        chosen = draw(adata.n_obs, fraction, int(seed))
        sub = adata[chosen].copy()
        for key in ("connectivities", "distances"):
            sub.obsp.pop(key, None)
        n_pcs = neighbours["n_pcs"]
        if n_pcs is not None:
            n_pcs = min(n_pcs, sub.obsm["X_pca"].shape[1])
        sc.pp.neighbors(
            sub,
            n_neighbors=min(neighbours["n_neighbors"], sub.n_obs - 1),
            n_pcs=n_pcs,
            use_rep="X_pca",
            random_state=neighbours["random_state"],
        )
        path = output_dir / f"sub{index:02d}.h5ad"
        sub.write_h5ad(path)
        files.append({"seed": int(seed), "path": str(path), "n_obs": int(sub.n_obs)})
    return files


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write subsampled copies of an .h5ad.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seeds", required=True, help="comma-separated integers")
    parser.add_argument("--fraction", type=float, default=0.8)
    args = parser.parse_args(argv)
    seeds = [int(item) for item in args.seeds.split(",") if item.strip()]
    try:
        files = write_subsamples(args.input, args.output_dir, seeds, args.fraction)
    except ValueError as exc:
        print(f"subsample: {exc}", file=sys.stderr)
        return 2
    print("SUBSAMPLE=" + json.dumps({"files": files}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
