"""The ``spatial_domains`` panel: PAS and silhouette scored, CHAOS and AMI reported.

Every chance-corrected metric is reported as a raw value, its expectation
under a random permutation of the labels that keeps every label's size, and
the corrected value ``adjusted`` (1 perfect, 0 chance level, negative below
it). The silhouette is not chance-corrected: its ``adjusted`` equals ``raw``.
The two scored metrics also report what a standard error needs: PAS its
observation count and ``se_adjusted``, the silhouette the standard deviation
and number of its per-observation values.

- **CHAOS** (diagnostic; SpatialPCA; SDMBench's Python port): coordinates
  standardised per axis with the population standard deviation; for every label with more than
  two observations, the distance from each observation to its nearest
  neighbour of the same label; the sum over labels divided by the number of
  observations. Lower is better. Observations of labels with two or fewer
  members contribute 0 and still count in the denominator. The expectation is
  estimated from permutations; the lower bound is the same sum taken over each
  observation's nearest neighbour of any label.
- **PAS** (SpatialPCA): fraction of observations whose label differs from more
  than half of their 10 nearest spatial neighbours on raw coordinates. Lower is
  better. The expectation is exact under the hypergeometric distribution.
  ``se_adjusted = sqrt(PAS (1 - PAS) / n) / E[PAS]``.
- **spatial_leiden_ami** (diagnostic): the largest adjusted mutual information
  between the labels and a Leiden partition of the spatial kNN graph at three
  resolutions.
- **knn_agreement** (diagnostic): mean fraction of the 10 nearest spatial
  neighbours sharing the label.
- **silhouette_pca**: mean silhouette on the input ``X_pca`` over a fixed
  random sample of at most 5000 observations, with ``sd`` and ``m`` of the
  per-observation values and ``se = sd / sqrt(m)``.

Runs in the scoring subprocess under the skill interpreter (Python 3.11+).

The spatial-Leiden AMI code is adapted from NicheCompass
(``src/nichecompass/benchmarking/mlami.py``), distributed under this licence::

  Copyright (c) 2024, Sebastian Birk, Carlos Talavera-López, Mohammad Lotfollahi
  All rights reserved.

  Redistribution and use in source and binary forms, with or without
  modification, are permitted provided that the following conditions are met:

  1. Redistributions of source code must retain the above copyright notice,
     this list of conditions and the following disclaimer.
  2. Redistributions in binary form must reproduce the above copyright notice,
     this list of conditions and the following disclaimer in the documentation
     and/or other materials provided with the distribution.
  3. Neither the name of the copyright holder nor the names of its contributors
     may be used to endorse or promote products derived from this software
     without specific prior written permission.

  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
  AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
  IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
  ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
  LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
  CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
  SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
  INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
  CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
  ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
  POSSIBILITY OF SUCH DAMAGE.
"""

from __future__ import annotations

import functools
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from omicsclaw.ensemble.metrics import SPATIAL_DOMAINS
from omicsclaw.ensemble.metrics.panel import MetricResult, combine, to_json

PAS_K = 10
KNN_AGREEMENT_K = 10
CHAOS_MIN_CLUSTER = 3
CHAOS_PERMUTATIONS = 10
PERMUTATION_SEED = 0
LEIDEN_NEIGHBORS = 15
LEIDEN_RESOLUTIONS = (0.1, 0.55, 1.0)
LEIDEN_SEED = 0
SILHOUETTE_SAMPLE_SIZE = 5000
SILHOUETTE_SEED = 0


# ---- helpers ------------------------------------------------------------------


def encode(labels: Sequence[Any]) -> Tuple[np.ndarray, np.ndarray]:
    """Integer codes of *labels* and the size of each code."""
    _, codes = np.unique(np.asarray(labels).astype(str), return_inverse=True)
    codes = codes.astype(np.int64)
    return codes, np.bincount(codes)


def standardise(coords: np.ndarray) -> np.ndarray:
    """Each axis centred and divided by its population standard deviation."""
    coords = np.asarray(coords, dtype=np.float64)
    std = coords.std(axis=0)
    std[std == 0] = 1.0
    return (coords - coords.mean(axis=0)) / std


def spatial_knn(coords: np.ndarray, k: int) -> np.ndarray:
    """``(n, k)`` indices of each observation's *k* nearest other observations."""
    from scipy.spatial import cKDTree

    coords = np.asarray(coords, dtype=np.float64)
    n = coords.shape[0]
    k = min(k, n - 1)
    _, idx = cKDTree(coords).query(coords, k=k + 1)
    idx = np.asarray(idx).reshape(n, k + 1)
    is_self = idx == np.arange(n)[:, None]
    missing = ~is_self.any(axis=1)
    is_self[missing, -1] = True
    return idx[~is_self].reshape(n, k)


def global_nn_distance(coords_std: np.ndarray) -> np.ndarray:
    """Distance from each observation to its nearest other observation."""
    from scipy.spatial import cKDTree

    dist, _ = cKDTree(coords_std).query(coords_std, k=2)
    return np.asarray(dist)[:, 1]


# ---- CHAOS ---------------------------------------------------------------------


def chaos_raw(codes: np.ndarray, coords_std: np.ndarray, *, min_cluster: int = CHAOS_MIN_CLUSTER) -> Tuple[float, int]:
    """CHAOS of integer labels on standardised coordinates, and the skipped count."""
    from scipy.spatial import cKDTree

    n = codes.shape[0]
    total = 0.0
    skipped = 0
    order = np.argsort(codes, kind="stable")
    boundaries = np.flatnonzero(np.diff(codes[order])) + 1
    for members in np.split(order, boundaries):
        if members.size < min_cluster:
            skipped += members.size
            continue
        points = coords_std[members]
        dist, _ = cKDTree(points).query(points, k=2)
        total += float(np.asarray(dist)[:, 1].sum())
    return total / n, skipped


def chaos_lower_bound(codes: np.ndarray, sizes: np.ndarray, nn_distance: np.ndarray, *, min_cluster: int = CHAOS_MIN_CLUSTER) -> float:
    """CHAOS when every same-label nearest neighbour is the global nearest neighbour."""
    kept = sizes[codes] >= min_cluster
    return float(nn_distance[kept].sum()) / codes.shape[0]


def chaos_metric(
    codes: np.ndarray,
    sizes: np.ndarray,
    coords_std: np.ndarray,
    nn_distance: np.ndarray,
    *,
    permutations: int = CHAOS_PERMUTATIONS,
    seed: int = PERMUTATION_SEED,
) -> MetricResult:
    """CHAOS with its permutation expectation and ``(E - CHAOS) / (E - d_min)``."""
    observed, skipped = chaos_raw(codes, coords_std)
    rng = np.random.default_rng(seed)
    draws = np.array([chaos_raw(rng.permutation(codes), coords_std)[0] for _ in range(permutations)])
    expected = float(draws.mean())
    stderr = float(draws.std(ddof=1) / math.sqrt(permutations)) if permutations > 1 else float("nan")
    lower = chaos_lower_bound(codes, sizes, nn_distance)
    extra = {
        "skipped_spots": skipped,
        "expected_stderr": stderr if math.isfinite(stderr) else None,
        "lower_bound": lower,
        "permutations": permutations,
    }
    denominator = expected - lower
    if denominator <= 0:
        return MetricResult(raw=observed, expected=expected, degenerate=True, extra=extra)
    return MetricResult(
        raw=observed,
        expected=expected,
        adjusted=(expected - observed) / denominator,
        extra=extra,
    )


# ---- PAS and kNN agreement ---------------------------------------------------------


def same_label_counts(codes: np.ndarray, knn: np.ndarray) -> np.ndarray:
    """How many of each observation's neighbours share its label."""
    return (codes[knn] == codes[:, None]).sum(axis=1)


def pas_raw(codes: np.ndarray, knn: np.ndarray) -> float:
    """Fraction of observations with more than ``k/2`` neighbours of another label."""
    k = knn.shape[1]
    different = k - same_label_counts(codes, knn)
    return float((different > k / 2).mean())


def pas_expected(sizes: np.ndarray, k: int) -> float:
    """``E[PAS]`` under a size-preserving permutation, exactly.

    For an observation of label ``c`` the number of same-label neighbours is
    hypergeometric: ``k`` draws from the other ``N - 1`` observations, of which
    ``n_c - 1`` carry ``c``.
    """
    from scipy.stats import hypergeom

    total = int(sizes.sum())
    threshold = k - math.floor(k / 2) - 1
    expectation = 0.0
    for size in sizes:
        if size == 0:
            continue
        p_abnormal = float(hypergeom(total - 1, int(size) - 1, k).cdf(threshold))
        expectation += (size / total) * p_abnormal
    return expectation


def pas_metric(codes: np.ndarray, sizes: np.ndarray, knn: np.ndarray) -> MetricResult:
    """PAS, its exact expectation, ``(E - PAS) / E`` and the standard error of that."""
    observed = pas_raw(codes, knn)
    expected = pas_expected(sizes, knn.shape[1])
    n = int(codes.shape[0])
    extra: Dict[str, object] = {"n": n}
    if expected <= 0:
        return MetricResult(raw=observed, expected=expected, degenerate=True, extra=extra)
    extra["se_adjusted"] = math.sqrt(observed * (1 - observed) / n) / expected
    return MetricResult(
        raw=observed, expected=expected, adjusted=(expected - observed) / expected, extra=extra
    )


def knn_agreement_raw(codes: np.ndarray, knn: np.ndarray) -> float:
    return float(same_label_counts(codes, knn).mean() / knn.shape[1])


def knn_agreement_expected(sizes: np.ndarray) -> float:
    """``sum_c p_c (n_c - 1) / (N - 1)``."""
    total = float(sizes.sum())
    return float(np.sum((sizes / total) * (sizes - 1) / (total - 1)))


def knn_agreement_metric(codes: np.ndarray, sizes: np.ndarray, knn: np.ndarray) -> MetricResult:
    observed = knn_agreement_raw(codes, knn)
    expected = knn_agreement_expected(sizes)
    if expected >= 1:
        return MetricResult(raw=observed, expected=expected, degenerate=True)
    return MetricResult(raw=observed, expected=expected, adjusted=(observed - expected) / (1 - expected))


# ---- spatial-Leiden AMI (adapted from NicheCompass MLAMI) ---------------------------


def reference_partitions(
    coords: np.ndarray,
    *,
    n_neighbors: int = LEIDEN_NEIGHBORS,
    resolutions: Sequence[float] = LEIDEN_RESOLUTIONS,
    seed: int = LEIDEN_SEED,
) -> List[np.ndarray]:
    """Leiden partitions of the spatial kNN graph, one per resolution.

    :raises ImportError: ``igraph`` is not installed; checked before any work.
    """
    import igraph  # noqa: F401  (the Leiden flavour used below)
    import scanpy as sc
    from anndata import AnnData

    n = coords.shape[0]
    adata = AnnData(X=np.zeros((n, 1), dtype=np.float32))
    adata.obsm["spatial"] = np.asarray(coords, dtype=np.float32)
    sc.pp.neighbors(adata, n_neighbors=min(n_neighbors, n - 1), use_rep="spatial", random_state=seed)
    partitions = []
    for resolution in resolutions:
        sc.tl.leiden(
            adata,
            resolution=float(resolution),
            random_state=seed,
            key_added="_spatial_leiden",
            flavor="igraph",
            n_iterations=2,
            directed=False,
        )
        partitions.append(adata.obs["_spatial_leiden"].astype(int).to_numpy())
    return partitions


def spatial_leiden_ami_metric(codes: np.ndarray, partitions: Sequence[np.ndarray]) -> MetricResult:
    """Largest AMI between the labels and any reference partition."""
    from sklearn.metrics import adjusted_mutual_info_score

    per_resolution = [float(adjusted_mutual_info_score(codes, partition)) for partition in partitions]
    best = max(per_resolution)
    return MetricResult(
        raw=best,
        expected=0.0,
        adjusted=best,
        extra={
            "ami_per_resolution": per_resolution,
            "resolutions": list(LEIDEN_RESOLUTIONS),
            "reference_n_clusters": [int(np.unique(p).size) for p in partitions],
        },
    )


# ---- silhouette ---------------------------------------------------------------------


def silhouette_metric(codes: np.ndarray, expression: np.ndarray) -> MetricResult:
    """Mean silhouette over the same sample ``sklearn.metrics.silhouette_score`` draws.

    ``adjusted`` equals ``raw``; ``extra`` holds ``sample_size`` (``m``), the
    standard deviation ``sd`` of the per-observation values and ``se``.
    """
    from sklearn.metrics import silhouette_samples
    from sklearn.utils import check_random_state

    n = codes.shape[0]
    size = min(SILHOUETTE_SAMPLE_SIZE, n)
    chosen = check_random_state(SILHOUETTE_SEED).permutation(n)[:size]
    values = silhouette_samples(np.asarray(expression)[chosen], codes[chosen])
    value = float(values.mean())
    sd = float(values.std(ddof=1)) if size > 1 else 0.0
    return MetricResult(
        raw=value,
        expected=None,
        adjusted=value,
        extra={"sample_size": size, "sd": sd, "se": sd / math.sqrt(size)},
    )


# ---- reference cache -----------------------------------------------------------------


class ReferenceCache:
    """Coordinate-only intermediate results, stored as ``.npz`` in one directory.

    Keys are hashed from the panel version and the parameters; files are written
    to a temporary name and renamed into place, so concurrent writers never
    leave a partial file.
    """

    def __init__(self, directory: Optional[Path]) -> None:
        self.directory = Path(directory) if directory is not None else None
        self.hits: List[str] = []
        self.misses: List[str] = []

    def _path(self, name: str, params: Mapping[str, Any]) -> Optional[Path]:
        if self.directory is None:
            return None
        digest = hashlib.sha256(
            json.dumps({"version": SPATIAL_DOMAINS.version, "name": name, **params}, sort_keys=True).encode()
        ).hexdigest()[:16]
        return self.directory / f"{name}-{digest}.npz"

    def load(self, name: str, params: Mapping[str, Any]) -> Optional[Dict[str, np.ndarray]]:
        path = self._path(name, params)
        if path is None or not path.is_file():
            self.misses.append(name)
            return None
        try:
            with np.load(path, allow_pickle=False) as data:
                arrays = {key: data[key] for key in data.files}
        except (OSError, ValueError):
            self.misses.append(name)
            return None
        self.hits.append(name)
        return arrays

    def store(self, name: str, params: Mapping[str, Any], arrays: Mapping[str, np.ndarray]) -> None:
        path = self._path(name, params)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(handle, "wb") as sink:
                np.savez(sink, **arrays)
            os.replace(temporary, path)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise


def _cached(cache: ReferenceCache, name: str, params: Mapping[str, Any], build) -> Dict[str, np.ndarray]:
    arrays = cache.load(name, params)
    if arrays is None:
        arrays = build()
        cache.store(name, params, arrays)
    return arrays


# ---- the panel -------------------------------------------------------------------------


def compute_panel(
    labels: Sequence[Any],
    reference: Mapping[str, Any],
    cache: Optional[ReferenceCache] = None,
) -> Dict[str, Any]:
    """Score *labels* (aligned to the reference observations) with the panel.

    :param labels: One label per observation, in the reference's order.
    :param reference: ``coords`` (required, ``(n, d)``) and ``expression``
        (optional, the input ``X_pca``).
    :param cache: Where coordinate-only results are kept between trials.
    :returns: The ``metrics.json`` document.
    """
    cache = cache or ReferenceCache(None)
    coords = np.asarray(reference["coords"], dtype=np.float64)
    codes, sizes = encode(labels)
    n = int(codes.shape[0])
    if coords.shape[0] != n:
        raise ValueError(f"{n} labels for {coords.shape[0]} coordinates")
    n_labels = int(sizes.size)
    document: Dict[str, Any] = {
        "analysis": SPATIAL_DOMAINS.analysis,
        "panel_version": SPATIAL_DOMAINS.version,
        "n_obs": n,
        "n_labels": n_labels,
        "largest_label_frac": float(sizes.max() / n) if n else None,
        "weights": SPATIAL_DOMAINS.weights,
    }
    if n_labels < 2:
        document.update(
            degenerate=True,
            score=0.0,
            weights_used={},
            dropped={},
            raw={},
            expected={},
            adjusted={},
            errors={"panel": "fewer than two labels"},
            degenerate_metrics=[],
            diagnostics={},
        )
        return document

    results: Dict[str, MetricResult] = {}
    coords_std = standardise(coords)

    def run(name: str, function) -> None:
        try:
            results[name] = function()
        except Exception as exc:  # a failed metric is dropped and reported, never fatal
            results[name] = MetricResult(error=f"{type(exc).__name__}: {exc}")

    knn_params = {"k": PAS_K}
    nn_params = {"standardised": True}

    @functools.lru_cache(maxsize=None)
    def knn() -> np.ndarray:
        return _cached(cache, "spatial_knn", knn_params, lambda: {"idx": spatial_knn(coords, PAS_K)})["idx"]

    @functools.lru_cache(maxsize=None)
    def nn_distance() -> np.ndarray:
        return _cached(
            cache, "global_nn", nn_params, lambda: {"distance": global_nn_distance(coords_std)}
        )["distance"]

    def partitions() -> List[np.ndarray]:
        params = {"n_neighbors": LEIDEN_NEIGHBORS, "resolutions": list(LEIDEN_RESOLUTIONS), "seed": LEIDEN_SEED}
        arrays = _cached(
            cache,
            "spatial_leiden",
            params,
            lambda: {f"p{i}": p for i, p in enumerate(reference_partitions(coords))},
        )
        return [arrays[f"p{i}"] for i in range(len(LEIDEN_RESOLUTIONS))]

    run("chaos", lambda: chaos_metric(codes, sizes, coords_std, nn_distance()))
    run("pas", lambda: pas_metric(codes, sizes, knn()))
    run("spatial_leiden_ami", lambda: spatial_leiden_ami_metric(codes, partitions()))
    run("knn_agreement", lambda: knn_agreement_metric(codes, sizes, knn()))
    expression = reference.get("expression")
    if expression is not None:
        run("silhouette_pca", lambda: silhouette_metric(codes, expression))
    else:
        results["silhouette_pca"] = MetricResult(error="the input has no expression embedding")

    combined = combine(results, SPATIAL_DOMAINS.weights)
    document.update(to_json(results))
    document.update(
        degenerate=False,
        score=combined["score"],
        weights_used=combined["weights_used"],
        dropped=combined["dropped"],
        chaos_skipped_spots=results["chaos"].extra.get("skipped_spots") if "chaos" in results else None,
        cache={"hits": sorted(set(cache.hits)), "misses": sorted(set(cache.misses))},
    )
    return document


__all__ = [
    "ReferenceCache",
    "chaos_metric",
    "chaos_raw",
    "compute_panel",
    "encode",
    "global_nn_distance",
    "knn_agreement_expected",
    "knn_agreement_metric",
    "pas_expected",
    "pas_metric",
    "pas_raw",
    "reference_partitions",
    "spatial_knn",
    "spatial_leiden_ami_metric",
    "standardise",
]
