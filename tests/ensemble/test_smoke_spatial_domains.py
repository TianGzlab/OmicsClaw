"""End-to-end smoke test: seven ``spatial-domains`` methods in one turn, on real data.

Runs only with ``-m slow`` and ``OMICSCLAW_ENSEMBLE_SMOKE_DATA`` pointing at the
development dataset (Slide-seqV2 mouse hippocampus). It rebuilds the input the
way a benchmark must: ``X`` from ``layers['counts']``, and ``obs`` reduced to
``batch`` so that no ground-truth column (``cell_type``) can reach a trial; the
original file stays outside the workspace. The data are preprocessed with
``spatial-preprocess`` at its defaults (``slide_seq``, ``mouse``).

Then a real ``open_app`` deployment, with GPUs detected rather than configured,
runs one turn of seven ``run_skill`` calls through the engine's scheduler. A
method whose package is missing fails and says why; the test asserts honesty,
not success. Two more batches check the GPU rules on real processes: with
``ensemble_gpus=none`` the GPU methods fall back to CPU and say so, and with a
single GPU three GPU trials must queue for it rather than share it.

``OMICSCLAW_ENSEMBLE_SMOKE_REPORT`` names a JSON file for the per-trial numbers.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from omicsclaw.engine.executor import execute_tool_calls
from omicsclaw.entry import assembly, open_app
from omicsclaw.entry.config import AppConfig
from omicsclaw.schema import ToolCall
from tests.entry.test_ensemble_golden import _Offline

pytestmark = pytest.mark.slow

REPO = Path(__file__).resolve().parents[2]
DATA = os.environ.get("OMICSCLAW_ENSEMBLE_SMOKE_DATA", "")
SKILL_PYTHON = os.environ.get("OMICSCLAW_SKILL_PYTHON", "/opt/conda/envs/OmicsClaw/bin/python")
METHODS = ("leiden", "louvain", "spagcn", "stagate", "graphst", "banksy", "cellcharter")
GPU_METHODS = ("stagate", "graphst", "cellcharter")


def _requirements(request):
    if not DATA:
        pytest.skip("set OMICSCLAW_ENSEMBLE_SMOKE_DATA to the development .h5ad")
    markexpr = request.config.getoption("markexpr") or ""
    if "slow" not in markexpr or "not slow" in markexpr:
        pytest.skip("the smoke test runs only under -m slow")
    if not Path(SKILL_PYTHON).exists():
        pytest.skip(f"skill interpreter {SKILL_PYTHON} is missing")


@pytest.fixture(scope="module")
def prepared(request, tmp_path_factory):
    _requirements(request)
    workspace = Path(os.environ.get("OMICSCLAW_ENSEMBLE_SMOKE_WORKSPACE") or tmp_path_factory.mktemp("smoke"))
    workspace.mkdir(parents=True, exist_ok=True)
    data = workspace / "data" / "slideseqv2_hippocampus_counts.h5ad"
    data.parent.mkdir(exist_ok=True)
    assert workspace.resolve() not in Path(DATA).resolve().parents, "the original dataset must stay outside"
    code = (
        "import anndata as ad, numpy as np, sys\n"
        f"a = ad.read_h5ad({DATA!r})\n"
        "counts = a.layers['counts']\n"
        "b = ad.AnnData(X=counts.astype(np.float32), obs=a.obs[['batch']].copy(), var=a.var[[]].copy())\n"
        "b.obsm['spatial'] = np.asarray(a.obsm['spatial'])\n"
        f"b.write_h5ad({str(data)!r})\n"
        "print(b.n_obs, list(b.obs.columns))\n"
    )
    done = subprocess.run([SKILL_PYTHON, "-c", code], capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr
    beads_before = int(done.stdout.split()[0])
    out = workspace / "preprocess"
    began = time.monotonic()
    done = subprocess.run(
        [SKILL_PYTHON, str(REPO / "skills/spatial/spatial-preprocess/spatial_preprocess.py"),
         "--input", str(data), "--output", str(out), "--data-type", "slide_seq", "--species", "mouse"],
        capture_output=True, text=True, timeout=3600, cwd=workspace,
        env={"PATH": os.environ["PATH"], "HOME": "/tmp", "PYTHONPATH": str(REPO), "MPLBACKEND": "Agg"},
    )
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-3000:]
    processed = out / "processed.h5ad"
    code = f"import anndata as ad; a = ad.read_h5ad({str(processed)!r}, backed='r'); print(a.n_obs, list(a.obs.columns))"
    after = subprocess.run([SKILL_PYTHON, "-c", code], capture_output=True, text=True, timeout=600)
    beads_after = int(after.stdout.split()[0])
    return {
        "workspace": workspace,
        "input": processed,
        "beads_before": beads_before,
        "beads_after": beads_after,
        "obs_columns_after_preprocess": after.stdout.split(" ", 1)[1].strip(),
        "preprocess_s": round(time.monotonic() - began, 1),
    }


def _config(prepared, **overrides) -> AppConfig:
    values = {
        "workspace": prepared["workspace"],
        "skills_dir": REPO / "skills",
        "ensemble": True,
        "ensemble_python": SKILL_PYTHON,
        "memory": False,
    }
    values.update(overrides)
    return AppConfig(**values)


def _turn(config: AppConfig, arguments: list[dict]):
    async def main():
        real = assembly.provider_from_env
        assembly.provider_from_env = lambda provider, model: _Offline()
        try:
            app = await open_app(config)
        finally:
            assembly.provider_from_env = real
        try:
            calls = [ToolCall(id=str(i), name="run_skill", arguments=json.dumps(a)) for i, a in enumerate(arguments)]
            results: list = []
            began = time.monotonic()
            async for _ in execute_tool_calls(app.registry, calls, config.engine_config(), results):
                pass
            return app, results, time.monotonic() - began
        finally:
            await app.aclose()

    return asyncio.run(main())


def _interval(record: dict) -> tuple[float, float]:
    from datetime import datetime

    start = datetime.fromisoformat(record["started_at"]).timestamp() + float(record["queued_s"] or 0)
    return (start, datetime.fromisoformat(record["ended_at"]).timestamp())


def _report(key: str, value) -> None:
    target = os.environ.get("OMICSCLAW_ENSEMBLE_SMOKE_REPORT")
    if not target:
        return
    path = Path(target)
    document = json.loads(path.read_text()) if path.exists() else {}
    document[key] = value
    path.write_text(json.dumps(document, indent=1, default=str))


def test_seven_methods_in_one_turn(prepared):
    loss = 1 - prepared["beads_after"] / prepared["beads_before"]
    _report("preprocess", {k: v for k, v in prepared.items() if k not in ("workspace", "input")} | {"loss": loss})
    config = _config(prepared)
    arguments = [
        {"skill": "spatial-domains", "method": m, "input": str(prepared["input"]), "run_id": "smoke",
         "params": {"data_type": "slide_seq"}}
        for m in METHODS
    ]
    app, results, wall = _turn(config, arguments)
    assert app.ensemble is not None
    assert len(app.ensemble.pool.gpu_ids) == 4, "all four GPUs should be detected"
    bodies = [json.loads(r.output) for r in results]
    _report("seven", {"wall_s": wall, "trials": bodies})
    assert [b["method"] for b in bodies] == list(METHODS)
    run_dir = prepared["workspace"] / "ensemble_runs" / "smoke"
    run = json.loads((run_dir / "run.json").read_text())
    assert "cell_type" not in run["input_obs_columns"]
    records = [json.loads(line) for line in (run_dir / "trials.jsonl").read_text().splitlines()]
    for body in bodies:
        assert body["status"] in ("ok", "failed", "timeout", "memory_exceeded")
        trial = Path(body["output_dir"])
        assert not (trial / "tmp").exists()
        if body["status"] == "ok":
            assert (trial / "metrics.json").exists() and (trial / "labels.csv.gz").exists()
            metrics = json.loads((trial / "metrics.json").read_text())
            assert metrics["panel_version"] == "spatial_domains/3"
            assert set(metrics["weights_used"]) == {"pas", "silhouette_pca"}
            assert metrics["diagnostics"]["silhouette_pca"]["se"] > 0
        else:
            assert body["error"]
        if body["device"].startswith("cuda"):
            assert body["device"] == f"cuda:{body['lease_gpu']}"
        if body["lease_gpu"] is None and body["status"] == "ok":
            assert body["device"] == "cpu"
    intervals = {r["method"]: _interval(r) for r in records if r["stage"] != "admission"}
    gpu_leases = [(r["lease_gpu"], _interval(r)) for r in records if r["lease_gpu"] is not None]
    for i, (gpu_a, a) in enumerate(gpu_leases):
        for gpu_b, b in gpu_leases[i + 1:]:
            if a[0] < b[1] and b[0] < a[1]:
                assert gpu_a != gpu_b
    spans = list(intervals.values())
    assert any(a[0] < b[1] and b[0] < a[1] for i, a in enumerate(spans) for b in spans[i + 1:])
    assert wall < sum(b["wall_s"] for b in bodies)
    for method in METHODS:
        h5ads = list((run_dir / method).glob("t*/output/*.h5ad"))
        assert len(h5ads) <= 1


def test_without_gpus_the_gpu_methods_degrade(prepared):
    config = _config(prepared, ensemble_gpus="none")
    methods = [m for m in GPU_METHODS]
    arguments = [
        {"skill": "spatial-domains", "method": m, "input": str(prepared["input"]), "run_id": "smoke-cpu",
         "params": {"data_type": "slide_seq"}}
        for m in methods
    ]
    _, results, wall = _turn(config, arguments)
    bodies = [json.loads(r.output) for r in results]
    _report("no_gpu", {"wall_s": wall, "trials": bodies})
    for body in bodies:
        assert body["degraded"] == "no_gpu"
        assert body["lease_gpu"] is None
        if body["status"] == "ok":
            assert body["device"] == "cpu"


def test_one_gpu_makes_gpu_trials_queue(prepared):
    config = _config(prepared, ensemble_gpus="0")
    arguments = []
    for method, params in (
        ("graphst", {"epochs": 50}), ("graphst", {"epochs": 60}),
        ("cellcharter", {"n_domains": 6}), ("cellcharter", {"n_domains": 8}),
    ):
        arguments.append({"skill": "spatial-domains", "method": method, "input": str(prepared["input"]),
                          "run_id": "smoke-1gpu", "params": {"data_type": "slide_seq", **params}})
    _, results, wall = _turn(config, arguments)
    bodies = [json.loads(r.output) for r in results]
    _report("one_gpu", {"wall_s": wall, "trials": bodies})
    run_dir = prepared["workspace"] / "ensemble_runs" / "smoke-1gpu"
    records = [json.loads(line) for line in (run_dir / "trials.jsonl").read_text().splitlines()]
    leased = [r for r in records if r["lease_gpu"] is not None]
    assert all(r["lease_gpu"] == "0" for r in leased)
    assert any(r["queued_s"] > 0 for r in records)
    spans = sorted(_interval(r) for r in leased)
    for (start_a, end_a), (start_b, _) in zip(spans, spans[1:]):
        assert end_a <= start_b + 0.5, "trials holding the one GPU must not overlap"
