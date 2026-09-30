"""How much the spatial panel favours fewer labels, before and after chance correction.

Purely spatial label metrics reward coarse partitions: two big halves have
almost no boundary, so "fraction of neighbours with the same label" is high
for them whatever the tissue looks like. The panel corrects every metric
against a size-preserving permutation of the labels. That removes the part of
the bias that comes from the chance level moving with the number of labels,
but it cannot make a purely spatial metric recognise the *true* number of
regions: cutting a real region into two spatially contiguous halves still
scores well after correction. Telling over-splitting apart needs evidence from
expression, which is why this study reports the silhouette diagnostic beside
the spatial metrics.

Corrected PAS is still expected to lean towards K=2 on clean data. PAS only
counts observations with six or more other-label neighbours out of ten. Along a
straight boundary each side sees about half and half, so on clean data almost
all observed PAS comes from junctions of several regions and from narrow
regions, whose number grows with K. The chance level ``E[PAS]`` is about 0.38
at K=2, 0.79 at K=3 and 0.97 at K=5 and barely moves after that, so
``1 - PAS / E[PAS]`` is closest to 1 at K=2. That is a property of the PAS
definition, not of the correction; the report quantifies it rather than
asserting it away.

The fast tests assert only the direction of the correction: random
permutations centre on zero, and the true labels beat a permutation of
themselves. The full report (``-m slow``) prints, per configuration, the
argmax-K *sets* of the new and old panels (differences of 1e-9 or less are
ties), each metric's Spearman correlation with K, the corrected values of
random permutations, the spatial-Leiden AMI's own argmax and the cluster counts
of its reference partitions, the CHAOS permutation standard error, and a
candidate with many tiny labels.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from omicsclaw.ensemble.metrics.spatial import (
    ReferenceCache,
    chaos_metric,
    compute_panel,
    encode,
    global_nn_distance,
    knn_agreement_metric,
    pas_metric,
    spatial_knn,
    standardise,
)

TIE = 1e-9
NOISE_LEVELS = (0.0, 0.05, 0.15)


# ---- synthetic tissue ---------------------------------------------------------------


def layout(kind: str, n: int = 5000, seed: int = 0) -> np.ndarray:
    """Observation coordinates in the unit square: a regular grid or Poisson points."""
    if kind == "grid":
        side = int(round(np.sqrt(n)))
        axis = (np.arange(side) + 0.5) / side
        xx, yy = np.meshgrid(axis, axis)
        return np.c_[xx.ravel(), yy.ravel()]
    return np.random.default_rng(seed).uniform(size=(n, 2))


def regions(coords: np.ndarray, geometry: str, k: int, seed: int = 0) -> np.ndarray:
    """True region of each observation: vertical stripes or Voronoi cells."""
    if geometry == "stripes":
        return np.minimum((coords[:, 0] * k).astype(int), k - 1)
    rng = np.random.default_rng(seed + 100 * k)
    seeds = rng.uniform(0.05, 0.95, size=(k, 2))
    distance = ((coords[:, None, :] - seeds[None, :, :]) ** 2).sum(-1)
    return distance.argmin(axis=1)


def _relabel(labels: np.ndarray) -> np.ndarray:
    return np.unique(labels, return_inverse=True)[1]


def merged(labels: np.ndarray, knn: np.ndarray, k: int) -> np.ndarray:
    """Merge adjacent regions until *k* remain: the smallest into its most-bordering neighbour."""
    labels = _relabel(labels.copy())
    while np.unique(labels).size > k:
        sizes = np.bincount(labels)
        present = np.flatnonzero(sizes)
        smallest = present[np.argmin(sizes[present])]
        members = labels == smallest
        neighbours = labels[knn[members]].ravel()
        neighbours = neighbours[neighbours != smallest]
        target = np.bincount(neighbours).argmax()
        labels[members] = target
        labels = _relabel(labels)
    return labels


def resplit(labels: np.ndarray, coords: np.ndarray, k: int) -> np.ndarray:
    """Split the largest region at the median of its longer axis until *k* remain."""
    labels = _relabel(labels.copy())
    while np.unique(labels).size < k:
        largest = np.bincount(labels).argmax()
        members = np.flatnonzero(labels == largest)
        span = coords[members].max(axis=0) - coords[members].min(axis=0)
        axis = int(np.argmax(span))
        cut = np.median(coords[members, axis])
        labels[members[coords[members, axis] > cut]] = labels.max() + 1
    return _relabel(labels)


def noisy(labels: np.ndarray, rate: float, seed: int) -> np.ndarray:
    """Move a fraction *rate* of observations to another random label of the candidate."""
    if rate == 0:
        return labels.copy()
    rng = np.random.default_rng(seed)
    out = labels.copy()
    k = np.unique(labels).size
    chosen = rng.choice(labels.size, size=int(round(rate * labels.size)), replace=False)
    shift = rng.integers(1, k, size=chosen.size)
    out[chosen] = (labels[chosen] + shift) % k
    return out


@dataclass
class Candidate:
    kind: str
    k: int
    labels: np.ndarray


def candidates(coords, truth, knn, k_true, noise, *, permutations=3, seed=0) -> list[Candidate]:
    """Merges, the truth, contiguous re-splits and permutations, with noise on all but the last."""
    clean: list[Candidate] = []
    for k in range(2, k_true):
        clean.append(Candidate("merge", k, merged(truth, knn, k)))
    clean.append(Candidate("truth", k_true, _relabel(truth)))
    for k in range(k_true + 1, 2 * k_true + 1):
        clean.append(Candidate("resplit", k, resplit(truth, coords, k)))
    rng = np.random.default_rng(seed + 1)
    out = [Candidate(c.kind, c.k, noisy(c.labels, noise, seed + 7)) for c in clean]
    for c in clean:
        for _ in range(permutations):
            out.append(Candidate("random", c.k, rng.permutation(c.labels)))
    return out


def old_panel(document: dict) -> float:
    """The panel before chance correction: 0.4 kNN agreement, 0.2 (1 - PAS), 0.4 AMI, clipped."""

    def clip(value):
        return min(1.0, max(0.0, value))

    parts = {
        "knn_agreement": (0.4, document["raw"].get("knn_agreement")),
        "pas": (0.2, None if document["raw"].get("pas") is None else 1 - document["raw"]["pas"]),
        "spatial_leiden_ami": (0.4, document["raw"].get("spatial_leiden_ami")),
    }
    usable = {name: (w, v) for name, (w, v) in parts.items() if v is not None}
    total = sum(w for w, _ in usable.values())
    return sum(w * clip(v) for w, v in usable.values()) / total


def argmax_set(scores: dict[int, float]) -> list[int]:
    best = max(scores.values())
    return sorted(k for k, value in scores.items() if best - value <= TIE)


# ---- fast, directional assertions ---------------------------------------------------------


@pytest.fixture(scope="module")
def grid_stripes():
    coords = layout("grid", 2500)
    truth = regions(coords, "stripes", 5)
    return coords, truth, spatial_knn(coords, 10)


def _corrected(labels, coords, knn):
    codes, sizes = encode(labels)
    std = standardise(coords)
    return {
        "chaos": chaos_metric(codes, sizes, std, global_nn_distance(std)).adjusted,
        "pas": pas_metric(codes, sizes, knn).adjusted,
        "knn_agreement": knn_agreement_metric(codes, sizes, knn).adjusted,
    }


@pytest.mark.parametrize("geometry", ["stripes", "voronoi"])
def test_random_permutations_centre_on_zero(geometry):
    coords = layout("poisson", 2500)
    truth = regions(coords, geometry, 5)
    knn = spatial_knn(coords, 10)
    rng = np.random.default_rng(11)
    draws = [_corrected(rng.permutation(truth), coords, knn) for _ in range(8)]
    for name in ("chaos", "pas", "knn_agreement"):
        assert abs(float(np.mean([d[name] for d in draws]))) < 0.05, name


@pytest.mark.parametrize("noise", NOISE_LEVELS)
def test_the_truth_beats_a_permutation_of_itself(grid_stripes, noise):
    coords, truth, knn = grid_stripes
    observed = _corrected(noisy(truth, noise, 7), coords, knn)
    shuffled = _corrected(np.random.default_rng(3).permutation(truth), coords, knn)
    for name, value in observed.items():
        assert value > shuffled[name], name


def test_merging_and_resplitting_keep_regions_contiguous(grid_stripes):
    coords, truth, knn = grid_stripes
    two = merged(truth, knn, 2)
    assert np.unique(two).size == 2
    ten = resplit(truth, coords, 10)
    assert np.unique(ten).size == 10
    assert _corrected(ten, coords, knn)["knn_agreement"] > 0.5


# ---- the full report --------------------------------------------------------------------------


def bias_report(
    *,
    layouts=("grid", "poisson"),
    geometries=("stripes", "voronoi"),
    k_true=(4, 7, 10),
    n=5000,
    permutations=3,
    cache_root: Path | None = None,
) -> str:
    """The full bias study as Markdown tables."""
    from scipy.stats import spearmanr

    lines: list[str] = []
    for layout_kind in layouts:
        coords = layout(layout_kind, n)
        knn = spatial_knn(coords, 10)
        cache = ReferenceCache(cache_root / layout_kind if cache_root else None)
        for geometry in geometries:
            for k_star in k_true:
                truth = regions(coords, geometry, k_star)
                expression = np.random.default_rng(5).normal(size=(coords.shape[0], 10))
                expression += 2.0 * np.eye(10)[truth % 10]
                reference = {"coords": coords, "expression": expression}
                for noise in NOISE_LEVELS:
                    rows = []
                    for candidate in candidates(coords, truth, knn, k_star, noise, permutations=permutations):
                        document = compute_panel(candidate.labels, reference, cache)
                        rows.append((candidate, document))
                    lines += _section(layout_kind, geometry, k_star, noise, rows, spearmanr)
                tiny = truth.copy()
                rng = np.random.default_rng(9)
                chosen = rng.choice(tiny.size, size=int(0.02 * tiny.size), replace=False)
                tiny[chosen] = tiny.max() + 1 + np.arange(chosen.size) // 2
                document = compute_panel(tiny, reference, cache)
                lines.append(
                    f"- tiny-label candidate (2% of observations in 2-member labels): "
                    f"n_labels={document['n_labels']}, chaos_skipped_spots={document['chaos_skipped_spots']}, "
                    f"adjusted chaos={_fmt(document['adjusted']['chaos'])}, pas={_fmt(document['adjusted']['pas'])}, "
                    f"score={_fmt(document['score'])}"
                )
                lines.append("")
    return "\n".join(lines)


def _fmt(value) -> str:
    return "—" if value is None else f"{value:.3f}"


def _section(layout_kind, geometry, k_star, noise, rows, spearmanr) -> list[str]:
    coherent = [(c, d) for c, d in rows if c.kind != "random"]
    random = [(c, d) for c, d in rows if c.kind == "random"]
    new = {c.k: d["score"] for c, d in coherent}
    old = {c.k: old_panel(d) for c, d in coherent}
    ami = {c.k: d["raw"].get("spatial_leiden_ami") for c, d in coherent}
    ks = [c.k for c, _ in coherent]
    out = [
        f"### {layout_kind} / {geometry} / K*={k_star} / noise={noise:.0%}",
        "",
        f"- argmax K, new panel: {argmax_set(new)}; old panel: {argmax_set(old)}",
    ]
    if all(v is not None for v in ami.values()):
        reference = coherent[0][1]["diagnostics"]["spatial_leiden_ami"]["reference_n_clusters"]
        out.append(
            f"- spatial_leiden_ami argmax K: {argmax_set(ami)}; reference Leiden clusters at "
            f"resolutions 0.1/0.55/1.0: {reference}"
        )
    stderr = [d["diagnostics"]["chaos"]["expected_stderr"] for _, d in coherent]
    adjusted_chaos = [abs(d["adjusted"]["chaos"] or 0) for _, d in coherent]
    out.append(
        f"- CHAOS permutation stderr: median {np.median(stderr):.2e}, "
        f"relative to |adjusted| median {np.median(np.array(stderr) / np.maximum(adjusted_chaos, 1e-12)):.2e}"
    )
    out += ["", "| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |", "|---|---|---|---|"]
    for name in ("chaos", "pas", "spatial_leiden_ami", "knn_agreement", "silhouette_pca"):
        raw = [d["raw"].get(name) for _, d in coherent]
        adj = [d["adjusted"].get(name) for _, d in coherent]
        rnd = [d["adjusted"].get(name) for _, d in random if d["adjusted"].get(name) is not None]
        if any(v is None for v in raw):
            out.append(f"| {name} | — | — | — |")
            continue
        out.append(
            f"| {name} | {spearmanr(ks, raw)[0]:+.2f} | {spearmanr(ks, adj)[0]:+.2f} | "
            f"{np.mean(rnd):+.3f} ± {np.std(rnd):.3f} |"
        )
    out += ["", "| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |", "|---|---|---|---|---|---|---|---|"]
    for c, d in coherent:
        out.append(
            f"| {c.k} | {c.kind} | {_fmt(d['score'])} | {_fmt(old_panel(d))} | {_fmt(d['adjusted']['chaos'])} | "
            f"{_fmt(d['adjusted']['pas'])} | {_fmt(d['adjusted'].get('spatial_leiden_ami'))} | "
            f"{_fmt(d['adjusted'].get('silhouette_pca'))} |"
        )
    out.append("")
    return out


@pytest.mark.slow
def test_full_bias_report(request, tmp_path):
    """Writes the report to ``$OMICSCLAW_PANEL_BIAS_REPORT`` (or prints it) under ``-m slow``."""
    if "slow" not in (request.config.getoption("markexpr") or "") or "not slow" in (
        request.config.getoption("markexpr") or ""
    ):
        pytest.skip("the full bias report runs only under -m slow")
    pytest.importorskip("igraph")
    report = bias_report(cache_root=tmp_path)
    target = os.environ.get("OMICSCLAW_PANEL_BIAS_REPORT")
    if target:
        Path(target).write_text(report, encoding="utf-8")
    print(report)
    assert "argmax K" in report
