"""Smoke test for the sc-integrate-cluster member skill (artifact contract).

Runs the skill as a real subprocess (the production fan-out path) for the
``none`` baseline — no external integration deps, fast — and asserts the
artifact schema the consensus reader + driver panel depend on. Harmony /
Scanorama / scVI backends are exercised by the end-to-end smoke, not here.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

_HERE = Path(__file__).resolve().parent
_SKILL = _HERE.parent / "sc_integrate_cluster.py"


def _load_synth():
    """The ``_synth`` helper next to this file, loaded by path."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("sc_integrate_cluster_synth", _HERE / "_synth.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_multibatch_adata(**kwargs):
    """Build the synthetic multi-batch AnnData; skips when scanpy is missing."""
    pytest.importorskip("scanpy")
    return _load_synth().make_multibatch_adata(**kwargs)


def test_none_baseline_emits_reader_and_panel_artifacts(tmp_path: Path) -> None:
    pytest.importorskip("igraph")  # Leiden clustering in the skill needs it
    adata = make_multibatch_adata(n_per_group=20, n_batches=2, n_types=2, n_genes=100, seed=0)
    inp = tmp_path / "synth.h5ad"
    adata.write_h5ad(inp)
    out = tmp_path / "member_none"

    proc = subprocess.run(
        [sys.executable, str(_SKILL), "--input", str(inp), "--output", str(out),
         "--method", "none", "--batch-key", "batch", "--resolution", "1.0", "--seed", "0"],
        capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 0, f"skill failed:\n{proc.stdout}\n{proc.stderr}"

    # Labels artifact the ScClusteringArtifactReader reads.
    points = pd.read_csv(out / "figure_data" / "embedding_points.csv")
    assert {"cell_id", "leiden"}.issubset(points.columns)
    assert len(points) == adata.n_obs

    # Summary the driver's k-report / panel keying reads.
    summary = pd.read_csv(out / "figure_data" / "clustering_summary.csv")
    rep = dict(zip(summary["metric"], summary["value"]))
    assert rep["representation_used"] == "X_pca"  # unintegrated baseline
    assert int(rep["n_clusters"]) >= 1
    assert int(rep["n_batches"]) == 2

    # Member processed.h5ad carries the embedding + X_pca baseline for the panel.
    import anndata as ad

    member_adata = ad.read_h5ad(out / "processed.h5ad")
    assert "X_pca" in member_adata.obsm
    assert "batch" in member_adata.obs.columns


def test_harmony_reuses_capped_pca_instead_of_recomputing(monkeypatch) -> None:
    """Regression (codex review [P2]): when the data has fewer usable PCs than
    ``--n-pcs``, ``_ensure_pca`` builds a *capped* ``X_pca``; Harmony must REUSE
    it (``use_pca=False``) rather than recompute PCA at the uncapped ``n_pcs`` —
    which Scanpy rejects, silently dropping the Harmony member from the default
    consensus. We assert the call contract (no harmonypy needed)."""
    pytest.importorskip("scanpy")
    import importlib.util as u

    spec = u.spec_from_file_location("sic_p2_regression", _SKILL)
    mod = u.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._load_runtime()  # real scanpy for _ensure_pca

    import anndata as ad
    import numpy as np

    rng = np.random.default_rng(0)
    n_per, n_genes = 30, 40  # 60 cells x 40 genes -> n_vars-1 = 39 < n_pcs
    X = np.vstack([rng.poisson(3.0, (n_per, n_genes)) + b for b in (0, 2)]).astype(float)
    adata = ad.AnnData(X=np.log1p(X), obs=pd.DataFrame({"batch": ["b0"] * n_per + ["b1"] * n_per}))
    adata.obs_names = [f"c{i}" for i in range(2 * n_per)]

    captured: dict = {}

    def _fake_harmony(adata_, batch_key, **kwargs):
        captured.update(kwargs)
        adata_.obsm["X_harmony"] = adata_.obsm["X_pca"].copy()
        return adata_

    monkeypatch.setattr(mod, "run_harmony_integration", _fake_harmony)

    n_pcs = 50
    mod._ensure_pca(adata, n_pcs=n_pcs, seed=0)
    assert adata.obsm["X_pca"].shape[1] < n_pcs, "test setup must produce a capped X_pca"

    key = mod._produce_representation(
        adata, method="harmony", batch_key="batch", n_pcs=n_pcs, seed=0, n_top_genes=30
    )
    assert key == "X_harmony"
    # The fix: reuse the existing capped X_pca. With the old call (default
    # use_pca=True) this would be absent/True and Scanpy would raise upstream.
    assert captured.get("use_pca") is False


@pytest.mark.parametrize("missing_batch", [True])
def test_integration_method_requires_batches(tmp_path: Path, missing_batch: bool) -> None:
    # A single-batch input must make a real integration method fail loudly
    # (the member is then dropped by fan-out, consensus proceeds on survivors).
    adata = make_multibatch_adata(n_per_group=20, n_batches=1, n_types=2, n_genes=100, seed=1)
    inp = tmp_path / "one_batch.h5ad"
    adata.write_h5ad(inp)
    out = tmp_path / "member_harmony"

    proc = subprocess.run(
        [sys.executable, str(_SKILL), "--input", str(inp), "--output", str(out),
         "--method", "harmony", "--batch-key", "batch", "--seed", "0"],
        capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode != 0
    assert "batch" in (proc.stdout + proc.stderr).lower()
