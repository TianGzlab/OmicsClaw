"""The scoring subprocess, as the runner invokes it.

Scoring runs in its own process under the skill interpreter, so it is tested
the same way: ``python -m omicsclaw.ensemble.metrics.score`` on a synthetic
``.h5ad``. The label set must equal the input's observation set exactly — a
method that silently dropped observations would otherwise be scored on an
easier subset. The coordinate-only reference is cached per input, so the
second trial on the same input must hit the cache.
"""

from __future__ import annotations

import gzip
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

anndata = pytest.importorskip("anndata")
pd = pytest.importorskip("pandas")

REPO = Path(__file__).resolve().parents[2]


def _h5ad(path: Path, n: int = 300, *, pca: bool = True) -> list[str]:
    rng = np.random.default_rng(0)
    coords = rng.uniform(0, 30, size=(n, 2))
    adata = anndata.AnnData(X=np.zeros((n, 3), dtype=np.float32))
    adata.obs_names = [f"bead{i}" for i in range(n)]
    adata.obs["batch"] = "sample1"
    adata.obsm["spatial"] = coords
    if pca:
        adata.obsm["X_pca"] = rng.normal(size=(n, 4)) + (coords[:, :1] // 10)
    adata.write_h5ad(path)
    return list(adata.obs_names), coords


def _labels(trial: Path, ids, labels) -> None:
    trial.mkdir(parents=True, exist_ok=True)
    with gzip.open(trial / "labels.csv.gz", "wt") as sink:
        pd.DataFrame({"obs_id": ids, "label": labels}).to_csv(sink, index=False)


def _score(trial: Path, source: Path, cache: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable, "-m", "omicsclaw.ensemble.metrics.score",
            "--trial", str(trial), "--input", str(source), "--analysis", "spatial_domains",
            "--cache", str(cache),
            "--reference-json", json.dumps({"coords_obsm": "spatial", "expression_obsm": "X_pca"}),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=300,
        env={"PYTHONPATH": str(REPO), "PATH": "/usr/bin:/bin", "HOME": "/tmp"},
    )


def test_a_trial_is_scored_and_the_reference_is_cached(tmp_path):
    source = tmp_path / "input.h5ad"
    ids, coords = _h5ad(source)
    labels = (coords[:, 0] // 10).astype(int).astype(str)
    cache = tmp_path / "cache"

    first = tmp_path / "t0001"
    _labels(first, ids[::-1], labels[::-1])
    done = _score(first, source, cache)
    assert done.returncode == 0, done.stderr
    metrics = json.loads((first / "metrics.json").read_text())
    assert metrics["n_obs"] == 300 and metrics["n_labels"] == 3
    assert metrics["score"] is not None
    assert metrics["panel_version"] == "spatial_domains/3"
    assert "global_nn" in metrics["cache"]["misses"]
    for name in ("ari", "nmi"):
        assert name not in json.dumps(metrics)

    second = tmp_path / "t0002"
    _labels(second, ids, labels)
    done = _score(second, source, cache)
    assert done.returncode == 0, done.stderr
    again = json.loads((second / "metrics.json").read_text())
    assert {"global_nn", "spatial_knn"} <= set(again["cache"]["hits"])
    assert again["raw"]["pas"] == metrics["raw"]["pas"]


def test_labels_that_miss_an_observation_fail_the_trial(tmp_path):
    source = tmp_path / "input.h5ad"
    ids, coords = _h5ad(source)
    trial = tmp_path / "t0001"
    _labels(trial, ids[:-1], ["a"] * 150 + ["b"] * 149)
    done = _score(trial, source, tmp_path / "cache")
    assert done.returncode == 2
    assert "1 missing" in done.stderr
    assert not (trial / "metrics.json").exists()


def test_an_unregistered_analysis_fails(tmp_path):
    source = tmp_path / "input.h5ad"
    ids, _ = _h5ad(source)
    trial = tmp_path / "t0001"
    _labels(trial, ids, ["a"] * 300)
    done = subprocess.run(
        [sys.executable, "-m", "omicsclaw.ensemble.metrics.score", "--trial", str(trial),
         "--input", str(source), "--analysis", "nope"],
        cwd=REPO, capture_output=True, text=True, timeout=120,
        env={"PYTHONPATH": str(REPO), "PATH": "/usr/bin:/bin", "HOME": "/tmp"},
    )
    assert done.returncode == 2 and "no panel" in done.stderr


def test_an_input_without_x_pca_is_refused_rather_than_scored_on_space_alone(tmp_path):
    """A panel half made of expression coherence must not quietly become a
    purely spatial score: it would then rank methods by smoothness alone."""
    source = tmp_path / "input.h5ad"
    ids, coords = _h5ad(source, pca=False)
    trial = tmp_path / "t0001"
    _labels(trial, ids, (coords[:, 0] // 10).astype(int).astype(str))
    done = _score(trial, source, tmp_path / "cache")
    assert done.returncode == 2
    assert "X_pca" in done.stderr
    assert not (trial / "metrics.json").exists()


def test_describe_input_reports_obsm_keys_and_the_gene_count(tmp_path):
    source = tmp_path / "input.h5ad"
    _h5ad(source)
    done = subprocess.run(
        [sys.executable, "-m", "omicsclaw.ensemble.metrics.score", "--describe-input", str(source)],
        cwd=REPO, capture_output=True, text=True, timeout=120,
        env={"PYTHONPATH": str(REPO), "PATH": "/usr/bin:/bin", "HOME": "/tmp"},
    )
    assert done.returncode == 0, done.stderr
    line = next(l for l in done.stdout.splitlines() if l.startswith("DESCRIBE="))
    described = json.loads(line[len("DESCRIBE="):])
    assert described == {
        "n_obs": 300, "n_vars": 3, "obs_columns": ["batch"], "obsm_keys": ["X_pca", "spatial"],
    }
