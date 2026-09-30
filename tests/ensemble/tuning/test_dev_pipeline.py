"""The whole pipeline on a real development slice, with a scripted model (``-m slow``).

Needs ``OMICSCLAW_TUNING_DEV_DATA`` (the directory holding ``151673.h5ad``)
and ``OMICSCLAW_ENSEMBLE_PYTHON`` (an interpreter with the skill's
dependencies). Preprocesses 151673 with the plan's settings, strips ``obs`` to
``batch``, and runs probe, evidence, K (scripted, K=7) and tuning on the five
runnable methods. It asserts structure, not quality: the probe's size, the
curves and bands over the whole grid, compact markers for every K, each
method's strategy and dimensions, a valid ``selection.json`` and the per-method
caps.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

DATA = os.environ.get("OMICSCLAW_TUNING_DEV_DATA")
PYTHON = os.environ.get("OMICSCLAW_ENSEMBLE_PYTHON")
REPO = Path(__file__).resolve().parents[3]
RUNNABLE = ("leiden", "louvain", "spagcn", "graphst", "cellcharter")


@pytest.mark.skipif(not DATA or not PYTHON, reason="needs OMICSCLAW_TUNING_DEV_DATA and OMICSCLAW_ENSEMBLE_PYTHON")
def test_the_pipeline_on_151673(tmp_path):
    from omicsclaw.ensemble.execution import LocalExecutor
    from omicsclaw.ensemble.resources import ResourcePool, detect_gpus
    from omicsclaw.ensemble.runner import EnsembleRunner
    from omicsclaw.ensemble.space import TuningCatalog
    from omicsclaw.ensemble.tuning.ledger import load_selection
    from omicsclaw.ensemble.tuning.llm import LLMSettings, ScriptedChatModel
    from omicsclaw.ensemble.tuning.pipeline import TuningPipeline, TuningRequest
    from omicsclaw.ensemble.tuning.tools import skill_text_loader
    from omicsclaw.skills import load_skills

    env = {**os.environ, "PYTHONPATH": str(REPO)}
    pre = tmp_path / "pre"
    subprocess.run([PYTHON, str(REPO / "skills/spatial/spatial-preprocess/spatial_preprocess.py"),
                    "--input", str(Path(DATA) / "151673.h5ad"), "--output", str(pre), "--data-type", "visium",
                    "--species", "human", "--max-mt-pct", "100"], check=True, env=env, capture_output=True)
    ws = tmp_path / "ws"
    source = ws / "data" / "input.h5ad"
    source.parent.mkdir(parents=True)
    subprocess.run([PYTHON, "-c", "import anndata, pandas as pd, sys; a = anndata.read_h5ad(sys.argv[1]);"
                    "a.obs = pd.DataFrame({'batch': ['b0'] * a.n_obs}, index=a.obs_names); a.write_h5ad(sys.argv[2])",
                    str(pre / "processed.h5ad"), str(source)], check=True, env=env)
    skills = load_skills(REPO / "skills")
    gpus = asyncio.run(detect_gpus(""))
    runner = EnsembleRunner(
        catalog=TuningCatalog.from_skills(skills),
        pool=ResourcePool(gpu_ids=gpus.ids, slots_per_gpu=2, memory_gb=512, cpus=max(8, (os.cpu_count() or 8) - 4)),
        executor=LocalExecutor(python=PYTHON), runs_root=ws / "ensemble_runs", repo_root=REPO,
    )
    decision = json.dumps({"chosen_k": 7, "rationale": "scripted", "confidence": "low",
                           "evidence": [{"k": 7, "kind": "curve", "curve": "f", "reading": "scripted"}]})
    model = ScriptedChatModel({"k_decision": [decision], "propose:*": ["not json"] * 12})
    pipeline = TuningPipeline(runner, model=model, llm_settings=LLMSettings(model="scripted", provider="test"),
                              skill_text=skill_text_loader(skills), obs_allowlist=("batch",))
    request = TuningRequest(skill="spatial-domains", input=source, run_id="dev", methods=RUNNABLE,
                            tissue="human dorsolateral prefrontal cortex", context={"data_type": "visium"})
    selection = asyncio.run(pipeline.run(request))

    evidence = ws / "ensemble_runs" / "dev-probe" / "evidence"
    probe = json.loads((evidence / "probe_done.json").read_text())
    kinds = [t["kind"] for t in probe["trials"]]
    assert (kinds.count("exact"), kinds.count("full"), kinds.count("sub")) == (42, 78, 1560)
    stability = json.loads((evidence / "stability.json").read_text())
    assert [int(k) for k in sorted(stability["per_k"], key=int)] == list(range(3, 17))
    for row in stability["per_k"].values():
        assert {"f_lo", "f_hi", "c_lo", "c_hi", "a_lo", "a_hi"} <= set(row)
    markers = json.loads((evidence / "markers.json").read_text())
    assert len(markers["compact"]) >= 12
    strategies = {m: e["strategy"] for m, e in selection.methods.items()}
    assert strategies == {"leiden": "grid", "louvain": "grid", "cellcharter": "grid",
                          "spagcn": "two_stage", "graphst": "two_stage"}
    load_selection(ws / "ensemble_runs" / "dev" / "tuning" / "selection.json")
    for method, used in selection.budget["used"].items():
        assert used <= selection.budget["caps"][method]
