"""An in-process stand-in for :class:`EnsembleRunner`, for fast pipeline tests.

Trials of the ``fake-domains`` methods are computed in this process: labels
are coordinate bins and the panel members are simple functions of the
parameters, so a test controls which settings win. Helper modules
(subsample, stability, markers) still run as real subprocesses.
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np

from omicsclaw.ensemble.execution import LocalExecutor
from omicsclaw.ensemble.runner import Limits, TrialResult, TrialSpec
from omicsclaw.ensemble.resources import ResourceRequest
from omicsclaw.ensemble.space import TuningCatalog, validate_params
from omicsclaw.ensemble.store import RunStore
from omicsclaw.skills import load_skills

REPO = Path(__file__).resolve().parents[3]
FAKE_SKILLS = REPO / "tests" / "ensemble" / "fake_skills"


def write_input(path: Path, n: int = 240, genes: int = 24) -> Path:
    import anndata

    rng = np.random.default_rng(0)
    coords = np.column_stack([rng.uniform(0, 60, n), rng.uniform(0, 20, n)])
    band = np.minimum((coords[:, 0] // 12).astype(int), 4)
    x = rng.poisson(0.5, size=(n, genes)).astype(np.float32)
    for b in range(5):
        x[band == b, b * 4:(b + 1) * 4] += 4
    adata = anndata.AnnData(X=np.log1p(x))
    adata.obs_names = [f"s{i}" for i in range(n)]
    adata.var_names = [f"GENE{j}" for j in range(genes)]
    adata.obs["batch"] = "b0"
    adata.obsm["spatial"] = coords
    adata.obsm["X_pca"] = np.column_stack([band + rng.normal(0, 0.3, n), rng.normal(size=(n, 3))])
    adata.uns["neighbors"] = {"params": {"n_neighbors": 10, "n_pcs": 4, "random_state": 0}}
    adata.uns["spatialclaw_spatial-preprocess"] = {"params": {"species": "human", "max_mt_pct": 100.0}}
    path.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(path)
    return path


def default_behaviour(method: str, params: Mapping[str, Any]) -> dict[str, Any]:
    """Number of labels and panel members for one fake trial."""
    if method == "cal":
        n = max(1, min(30, int(round(params["resolution"] * 6))))
        smooth = params.get("smooth", 0.3)
        return {"n": n, "pas": 0.9 - abs(smooth - 0.45), "sil": 0.2 - 0.1 * abs(smooth - 0.45)}
    if method == "twod":
        alpha, beta = params.get("alpha", 0.5), params.get("beta", 100)
        return {"n": params["n"], "pas": 0.9 - 0.5 * abs(alpha - 0.7), "sil": 0.2 - 0.05 * abs(math.log(beta / 100))}
    if method == "grid1":
        layers = params.get("layers", 3)
        return {"n": params["n"], "pas": 0.8 - 0.05 * abs(layers - 4), "sil": 0.1}
    if method == "flaky":
        if params.get("n", 0) > 5:
            return {"fail": True}
        if params.get("n", 0) == 5:
            return {"n": 4, "pas": 0.5, "sil": 0.0}
        return {"n": params["n"], "pas": 0.5, "sil": 0.0}
    return {"n": params.get("n", 3), "pas": 0.5, "sil": 0.0}


@dataclass
class FakeRunner:
    root: Path
    behaviour: Callable[[str, Mapping[str, Any]], dict[str, Any]] = default_behaviour
    delay_s: float = 0.0
    catalog: TuningCatalog = field(default_factory=lambda: TuningCatalog.from_skills(load_skills(FAKE_SKILLS)))
    runs: list[tuple[str, str, dict]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.store = RunStore(self.root / "ensemble_runs")
        self.executor = LocalExecutor(python=sys.executable)
        self.repo_root = REPO
        self._obs: dict[str, tuple[list[str], np.ndarray]] = {}

    def input_sha256(self, path: Path) -> str:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def prepare(self, *, skill, method, input, params=None, run_id=None, timeout_s=None) -> TrialSpec:
        spec = self.catalog.get(skill)
        values = validate_params(spec, method, params or {})
        return TrialSpec(skill=skill, method=method, input=Path(input), params=values, run_id=run_id,
                         limits=Limits(timeout_s=60, memory_gb=1), resources=ResourceRequest("none", 1, 1))

    def _obs_of(self, path: Path):
        key = str(path)
        if key not in self._obs:
            import anndata

            adata = anndata.read_h5ad(path, backed="r")
            self._obs[key] = ([str(x) for x in adata.obs_names], np.asarray(adata.obsm["spatial"])[:, 0])
            adata.file.close()
        return self._obs[key]

    async def fan_out(self, specs):
        return list(await asyncio.gather(*(self.run(spec) for spec in specs)))

    async def run(self, spec: TrialSpec, *, backstop_s=None) -> TrialResult:
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        self.runs.append((spec.run_id, spec.method, dict(spec.params)))
        await self.store.bind_run(spec.run_id, {
            "run_id": spec.run_id, "skill": spec.skill, "input": str(spec.input),
            "input_sha256": self.input_sha256(spec.input), "panel_version": "spatial_domains/3",
        })
        trial_dir = await self.store.allocate_trial(spec.run_id, spec.method)
        outcome = self.behaviour(spec.method, spec.params)
        result = TrialResult(status="failed", stage="run", run_id=spec.run_id, method=spec.method,
                             trial=trial_dir.name, output_dir=str(trial_dir), params=dict(spec.params),
                             wall_s=1.0)
        if outcome.get("fail"):
            result.error = "fake failure"
            await self.store.record_trial(spec.run_id, trial_dir, result.to_dict())
            return result
        ids, x = self._obs_of(spec.input)
        n = int(outcome["n"])
        span = (x.max() - x.min()) or 1.0
        labels = [str(min(int((v - x.min()) / span * n), n - 1)) for v in x]
        with gzip.open(trial_dir / "labels.csv.gz", "wt") as sink:
            sink.write("obs_id,label\n")
            for name, label in zip(ids, labels):
                sink.write(f"{name},{label}\n")
        n_labels = len(set(labels))
        pas, sil = float(outcome["pas"]), float(outcome["sil"])
        result.metrics = {
            "n_labels": n_labels, "panel_version": "spatial_domains/3",
            "score": 0.5 * min(1, max(0, pas)) + 0.5 * min(1, max(0, sil)),
            "adjusted": {"pas": pas, "silhouette_pca": sil}, "raw": {"pas": 0.1, "silhouette_pca": sil},
            "diagnostics": {"pas": {"se_adjusted": 0.005, "n": len(ids)},
                            "silhouette_pca": {"sd": 0.1, "sample_size": len(ids), "se": 0.1 / math.sqrt(len(ids))}},
        }
        result.score = result.metrics["score"]
        result.status, result.stage = "ok", "score"
        (trial_dir / "metrics.json").write_text(json.dumps(result.metrics))
        await self.store.record_trial(spec.run_id, trial_dir, result.to_dict())
        return result
