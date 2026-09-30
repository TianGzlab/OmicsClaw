"""The trial runner, driven through real subprocesses by a fake skill.

``fake-domains`` (under ``tests/ensemble/fake_skills``) labels observations by
a coordinate split and can be told to fail, sleep, allocate memory, omit its
outputs or write a label for an observation that does not exist. Each failure
must surface as a result with the right ``status`` and ``stage`` — never as an
exception — because a benchmark reads these results to decide which methods
ran, and because one broken method must not take its siblings down.

Retention is part of the contract: a run directory holds labels, metrics and
``result.json`` for every trial but a processed ``.h5ad`` only for the best
trial of each method, since dozens of trials of a 40k-bead dataset would
otherwise fill the disk.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import sys
from pathlib import Path

import numpy as np
import pytest

anndata = pytest.importorskip("anndata")

from omicsclaw.ensemble.execution import LocalExecutor
from omicsclaw.ensemble.resources import ResourcePool
from omicsclaw.ensemble.runner import EnsembleRunner, InsufficientSurvivors
from omicsclaw.ensemble.space import SpecError, TuningCatalog
from omicsclaw.ensemble.store import write_json
from omicsclaw.skills import load_skills

REPO = Path(__file__).resolve().parents[2]
FAKE_SKILLS = Path(__file__).resolve().parent / "fake_skills"


def _input(path: Path, n: int = 200, *, spatial: bool = True) -> Path:
    rng = np.random.default_rng(0)
    adata = anndata.AnnData(X=np.zeros((n, 2), dtype=np.float32))
    adata.obs_names = [f"bead{i}" for i in range(n)]
    adata.obs["batch"] = "sample1"
    if spatial:
        adata.obsm["spatial"] = rng.uniform(0, 30, size=(n, 2))
    adata.obsm["X_pca"] = rng.normal(size=(n, 3))
    path.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(path)
    return path


def _runner(tmp_path: Path, *, gpus=(), memory=64.0, cpus=8, **kwargs) -> EnsembleRunner:
    catalog = TuningCatalog.from_skills(load_skills(FAKE_SKILLS))
    assert catalog.names() == ("fake-domains",), catalog.skipped
    return EnsembleRunner(
        catalog=catalog,
        pool=ResourcePool(gpu_ids=gpus, memory_gb=memory, cpus=cpus, gpu_detail="none in this test"),
        executor=LocalExecutor(python=sys.executable),
        runs_root=tmp_path / "ws" / "ensemble_runs",
        repo_root=REPO,
        **kwargs,
    )


def _run(runner: EnsembleRunner, source: Path, method: str, params=None, run_id="r1", **kwargs):
    spec = runner.prepare(skill="fake-domains", method=method, input=source, params=params or {},
                          run_id=run_id, **kwargs)
    return asyncio.run(asyncio.wait_for(runner.run(spec), 240))


@pytest.fixture(scope="module")
def one_run(tmp_path_factory):
    """Two ``split`` trials of one run: the layout and retention after both."""
    tmp_path = tmp_path_factory.mktemp("runner")
    source = _input(tmp_path / "ws" / "data" / "in.h5ad")
    runner = _runner(tmp_path)
    first = _run(runner, source, "split", {"n": 3})
    second = _run(runner, source, "split", {"n": 2, "id_column": "barcode"})
    return runner, source, first, second


def test_an_ok_trial_leaves_the_documented_files(one_run):
    runner, source, first, _ = one_run
    assert first.status == "ok", first.error
    trial = Path(first.output_dir)
    assert trial.name == "t0001" and trial.parent.name == "split"
    kept = {p.name for p in trial.iterdir()}
    assert kept == {"trial.json", "labels.csv.gz", "metrics.json", "supervisor.json", "run.log", "output"}
    assert not (trial / "tmp").exists()
    record = json.loads((trial / "trial.json").read_text())
    assert record["status"] == "ok" and record["stage"] == "score"
    assert record["provenance"]["input_sha256"] == runner.input_sha256(source)
    assert first.metrics["panel_version"] == "spatial_domains/3"
    assert first.score is not None
    assert first.mem_metric in ("pss", "rss") and first.peak_mem_gb > 0
    with gzip.open(trial / "labels.csv.gz", "rt") as handle:
        lines = handle.read().splitlines()
    assert lines[0] == "obs_id,label" and len(lines) == 201


def test_the_command_renders_every_default(one_run):
    _, source, first, _ = one_run
    assert first.command[-6:] == ["--method", "split", "--n", "3", "--id-column", "observation"]
    assert first.command[first.command.index("--input") + 1] == str(source)


def test_run_json_binds_the_skill_input_and_obs_columns(one_run):
    runner, source, _, _ = one_run
    run = json.loads((runner.store.run_dir("r1") / "run.json").read_text())
    assert run["skill"] == "fake-domains"
    assert run["input_sha256"] == runner.input_sha256(source)
    assert run["input_obs_columns"] == ["batch"]
    assert run["input_n_obs"] == 200
    lines = (runner.store.run_dir("r1") / "trials.jsonl").read_text().splitlines()
    assert [json.loads(line)["trial"] for line in lines] == ["t0001", "t0002"]


def test_the_id_column_falls_back_to_the_first_column(one_run):
    _, _, first, second = one_run
    assert first.id_column_used == "observation"
    assert second.status == "ok", second.error
    assert second.id_column_used == "barcode"


def test_only_the_best_trial_keeps_its_h5ad(one_run):
    runner, _, first, second = one_run
    method_dir = runner.store.method_dir("r1", "split")
    best = json.loads((method_dir / "best.json").read_text())
    winner, loser = (first, second) if best["trial"] == "t0001" else (second, first)
    assert best["score"] == pytest.approx(max(first.score, second.score))
    h5ads = sorted(method_dir.glob("t*/output/*.h5ad"))
    assert h5ads == [Path(winner.output_dir) / "output" / "processed.h5ad"]
    for result in (first, second):
        outputs = {p.name for p in (Path(result.output_dir) / "output").iterdir()}
        assert outputs <= {"result.json", "processed.h5ad"}
    assert winner.h5ad is not None or best["trial"] != winner.trial


def test_a_tie_keeps_the_earlier_trial(tmp_path):
    source = _input(tmp_path / "ws" / "in.h5ad")
    runner = _runner(tmp_path)
    first = _run(runner, source, "split", {"n": 3})
    second = _run(runner, source, "split", {"n": 3})
    assert first.score == second.score
    best = json.loads((runner.store.method_dir("r1", "split") / "best.json").read_text())
    assert best["trial"] == "t0001"
    assert second.h5ad is None
    assert (Path(first.output_dir) / "output" / "processed.h5ad").exists()


def test_keep_all_keeps_everything(tmp_path):
    source = _input(tmp_path / "ws" / "in.h5ad")
    runner = _runner(tmp_path, keep_all=True)
    result = _run(runner, source, "split")
    trial = Path(result.output_dir)
    assert (trial / "tmp").is_dir()
    assert {"figures", "report.md", "processed.h5ad", "result.json", "tables"} <= {
        p.name for p in (trial / "output").iterdir()
    }


def test_a_run_id_is_bound_to_its_input_and_skill(tmp_path):
    source = _input(tmp_path / "ws" / "in.h5ad")
    other = _input(tmp_path / "ws" / "other.h5ad", n=150)
    runner = _runner(tmp_path)
    _run(runner, source, "split")
    with pytest.raises(SpecError, match="another input"):
        runner.prepare(skill="fake-domains", method="split", input=other, run_id="r1")
    write_json(runner.store.run_dir("r1") / "run.json", {"skill": "spatial-domains", "input_sha256": "x"})
    with pytest.raises(SpecError, match="belongs to skill 'spatial-domains'"):
        runner.prepare(skill="fake-domains", method="split", input=source, run_id="r1")


@pytest.mark.parametrize("run_id", ["R1", "-x", "a" * 65, "a/b", "a b", "abc\n", "abc\r\n"])
def test_a_malformed_run_id_is_refused(tmp_path, run_id):
    source = _input(tmp_path / "ws" / "in.h5ad")
    with pytest.raises(SpecError, match="run_id"):
        _runner(tmp_path).prepare(skill="fake-domains", method="split", input=source, run_id=run_id)


def test_a_generated_run_id_has_the_documented_shape(tmp_path):
    source = _input(tmp_path / "ws" / "in.h5ad")
    spec = _runner(tmp_path).prepare(skill="fake-domains", method="split", input=source)
    assert spec.run_id.startswith("r") and len(spec.run_id) == len("r20260924-120000-abcd")


def test_concurrent_trials_get_distinct_numbers(tmp_path):
    source = _input(tmp_path / "ws" / "in.h5ad")
    runner = _runner(tmp_path)
    specs = [runner.prepare(skill="fake-domains", method="split", input=source, run_id="r1",
                            params={"n": n}) for n in (2, 3, 4, 5)]
    results = asyncio.run(asyncio.wait_for(runner.fan_out(specs), 240))
    assert sorted(r.trial for r in results) == ["t0001", "t0002", "t0003", "t0004"]
    assert [r.params["n"] for r in results] == [2, 3, 4, 5]
    lines = (runner.store.run_dir("r1") / "trials.jsonl").read_text().splitlines()
    assert len(lines) == 4
    assert len(list(runner.store.method_dir("r1", "split").glob("t*/output/*.h5ad"))) == 1


# ---- failures, one per stage -------------------------------------------------------------


def test_a_required_gpu_without_one_fails_at_admission(tmp_path):
    source = _input(tmp_path / "ws" / "in.h5ad")
    result = _run(_runner(tmp_path), source, "needsgpu")
    assert (result.status, result.stage) == ("failed", "admission")
    assert "requires a GPU" in result.error and "none in this test" in result.error
    assert not (Path(result.output_dir) / "supervisor.json").exists()
    assert json.loads((Path(result.output_dir) / "trial.json").read_text())["stage"] == "admission"


def test_more_memory_than_the_pool_fails_at_admission(tmp_path):
    source = _input(tmp_path / "ws" / "in.h5ad")
    result = _run(_runner(tmp_path, memory=1.0), source, "split")
    assert (result.status, result.stage) == ("failed", "admission")
    assert "1 GB in total" in result.error


def test_a_preferred_gpu_without_one_degrades_to_cpu(tmp_path):
    source = _input(tmp_path / "ws" / "in.h5ad")
    result = _run(_runner(tmp_path), source, "gpu")
    assert result.status == "ok", result.error
    assert result.degraded == "no_gpu"
    assert result.lease_gpu is None
    assert "CUDA_VISIBLE_DEVICES=''" in Path(result.log).read_text()
    assert result.device == "cpu" and result.device_source in ("observed", "inferred_no_lease")


def test_a_preferred_gpu_with_one_is_leased(tmp_path):
    source = _input(tmp_path / "ws" / "in.h5ad")
    result = _run(_runner(tmp_path, gpus=("3",)), source, "gpu")
    assert result.status == "ok", result.error
    assert result.lease_gpu == "3" and result.degraded == ""
    assert "CUDA_VISIBLE_DEVICES='3'" in Path(result.log).read_text()
    if result.device_source == "observed":
        assert result.device == "cpu", "the fake never touches the GPU, so the lease is not the device"


def test_a_non_zero_exit_fails_at_run_with_the_log_tail(tmp_path):
    source = _input(tmp_path / "ws" / "in.h5ad")
    result = _run(_runner(tmp_path), source, "fail", {"exit_code": 4})
    assert (result.status, result.stage, result.exit_code) == ("failed", "run", 4)
    assert "failing on purpose" in result.error
    assert len(result.error.encode()) <= 2048 + 200


def test_a_trial_past_its_time_limit_is_a_timeout(tmp_path):
    source = _input(tmp_path / "ws" / "in.h5ad")
    result = _run(_runner(tmp_path), source, "sleep", {"seconds": 30.0})
    assert (result.status, result.stage) == ("timeout", "run")
    assert result.wall_s < 20


def test_a_trial_past_its_memory_limit_is_memory_exceeded(tmp_path):
    source = _input(tmp_path / "ws" / "in.h5ad")
    result = _run(_runner(tmp_path), source, "eat", {"memory_mb": 1000})
    assert (result.status, result.stage) == ("memory_exceeded", "run")
    assert "0.3 GB memory limit" in result.error


@pytest.mark.parametrize("method, fragment", [("nolabels", "domain_assignments.csv"), ("noresult", "result.json")])
def test_missing_outputs_fail_at_collect(tmp_path, method, fragment):
    source = _input(tmp_path / "ws" / "in.h5ad")
    result = _run(_runner(tmp_path), source, method)
    assert (result.status, result.stage) == ("failed", "collect")
    assert fragment in result.error
    assert not list((Path(result.output_dir) / "output").glob("*.h5ad"))


def test_labels_for_unknown_observations_fail_at_score(tmp_path):
    source = _input(tmp_path / "ws" / "in.h5ad")
    result = _run(_runner(tmp_path), source, "extra")
    assert (result.status, result.stage) == ("failed", "score")
    assert "not in the input" in result.error


def test_waiting_past_the_queue_limit_fails_at_admission(tmp_path):
    source = _input(tmp_path / "ws" / "in.h5ad")
    runner = _runner(tmp_path, cpus=1, max_queue_s=0.5)
    holder = runner.prepare(skill="fake-domains", method="sleep", input=source, run_id="r1", params={"seconds": 1.5})
    late = runner.prepare(skill="fake-domains", method="split", input=source, run_id="r1")
    started = runner.store.method_dir("r1", "sleep") / "t0001" / "run.log"

    async def main():
        first = asyncio.ensure_future(runner.run(holder))
        for _ in range(600):
            if started.exists() and "method=sleep" in started.read_text():
                break
            await asyncio.sleep(0.05)
        second = await runner.run(late)
        await first
        return second

    result = asyncio.run(asyncio.wait_for(main(), 240))
    assert result.status == "failed" and result.stage == "admission"
    assert "queued longer than 0.5 s" in result.error


def test_fan_out_reports_too_few_survivors(tmp_path):
    source = _input(tmp_path / "ws" / "in.h5ad")
    runner = _runner(tmp_path)
    specs = [
        runner.prepare(skill="fake-domains", method="split", input=source, run_id="r1"),
        runner.prepare(skill="fake-domains", method="fail", input=source, run_id="r1"),
    ]
    with pytest.raises(InsufficientSurvivors) as raised:
        asyncio.run(asyncio.wait_for(runner.fan_out(specs, required_survivors=2), 240))
    assert [r.status for r in raised.value.results] == ["ok", "failed"]


def test_cancelling_a_trial_records_it_and_propagates(tmp_path):
    source = _input(tmp_path / "ws" / "in.h5ad")
    runner = _runner(tmp_path)
    spec = runner.prepare(skill="fake-domains", method="sleep", input=source, run_id="r1", params={"seconds": 30.0})

    started = runner.store.method_dir("r1", "sleep") / "t0001" / "run.log"

    async def main():
        task = asyncio.ensure_future(runner.run(spec))
        for _ in range(600):
            if started.exists() and "method=sleep" in started.read_text():
                break
            await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(asyncio.wait_for(main(), 60))
    record = json.loads((runner.store.method_dir("r1", "sleep") / "t0001" / "trial.json").read_text())
    assert record["status"] == "cancelled"
    lines = (runner.store.run_dir("r1") / "trials.jsonl").read_text().splitlines()
    assert json.loads(lines[-1])["status"] == "cancelled"


def test_timeout_s_is_bounded_by_the_ceiling(tmp_path):
    source = _input(tmp_path / "ws" / "in.h5ad")
    runner = _runner(tmp_path, max_trial_s=100)
    with pytest.raises(SpecError, match="ceiling of 100"):
        runner.prepare(skill="fake-domains", method="split", input=source, timeout_s=101)
    spec = runner.prepare(skill="fake-domains", method="split", input=source, timeout_s=30)
    assert spec.limits.timeout_s == 30


def test_the_memory_cap_lowers_every_method(tmp_path):
    source = _input(tmp_path / "ws" / "in.h5ad")
    spec = _runner(tmp_path, memory_cap_gb=1.5).prepare(skill="fake-domains", method="split", input=source)
    assert spec.limits.memory_gb == 1.5 and spec.resources.memory_gb == 1.5


# ---- the device field ------------------------------------------------------------------------


def _device_of(tmp_path, *, lease, report, summary=None):
    from omicsclaw.ensemble.runner import TrialResult

    result = TrialResult(status="ok", stage="run", run_id="r1", method="m", trial="t0001",
                         output_dir=str(tmp_path), params={}, lease_gpu=lease)
    envelope = tmp_path / "result.json"
    envelope.write_text(json.dumps({"summary": summary or {}}))
    _runner(tmp_path)._device(result, report, envelope)
    return result.device, result.device_source


def test_an_unleased_trial_is_inferred_cpu_when_gpu_use_cannot_be_attributed(tmp_path):
    """No lease means ``CUDA_VISIBLE_DEVICES=""``: the trial cannot have used a GPU,
    whatever the skill claims, so ``unknown`` would understate what is known."""
    for probe in ("unattributable", "unavailable"):
        assert _device_of(tmp_path, lease=None, report={"gpu_probe": probe},
                          summary={"device": "cuda"}) == ("cpu", "inferred_no_lease")


@pytest.mark.parametrize("reported", ["cuda", "gpu", "GPU", "cuda:0", "cuda:3"])
def test_a_skill_reported_cuda_device_is_written_with_the_lease(tmp_path, reported):
    """Inside the trial the leased card is ``cuda:0`` whatever its host index;
    the lease is the index that identifies it."""
    assert _device_of(tmp_path, lease="2", report={"gpu_probe": "unattributable"},
                      summary={"device": reported}) == ("cuda:2", "skill")


def test_a_leased_trial_keeps_a_cpu_report_and_is_unknown_without_one(tmp_path):
    assert _device_of(tmp_path, lease="1", report={"gpu_probe": "unattributable"},
                      summary={"device": "cpu"}) == ("cpu", "skill")
    assert _device_of(tmp_path, lease="1", report={"gpu_probe": "unattributable"}) == ("unknown", "unknown")


def test_an_observed_probe_wins(tmp_path):
    assert _device_of(tmp_path, lease="1", report={"gpu_probe": "ok", "gpu_used": True},
                      summary={"device": "cpu"}) == ("cuda:1", "observed")
