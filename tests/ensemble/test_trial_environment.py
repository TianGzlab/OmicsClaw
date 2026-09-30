"""What a trial records about the environment it ran in (plan 0061 P3, cases 25 and 26).

``EnsembleRunner`` takes an optional ``describe_environment`` callback. The
entry layer builds it from ``omicsclaw.skillenv``; the ensemble package never
imports that package (plan 0056 §3.1, checked by ``test_ensemble_is_a_layer``),
so these tests drive the runner with a hand-written callback and a fake
executor. What the callback returns lands in ``trial.json`` under
``provenance.environment``; a callback that raises or hangs is recorded as
``{"error": …}`` and the trial runs on regardless, because a failed probe is
no reason to lose a trial.

Case 26: the four variables of the retired adaptive-environment runner are no
longer passed to local trials — nothing reads them (plan 0061 F17, F18, Q16).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from omicsclaw.ensemble import runner as runner_module
from omicsclaw.ensemble.execution import ENV_WHITELIST, CommandResult
from omicsclaw.ensemble.resources import ResourcePool
from omicsclaw.ensemble.runner import EnsembleRunner
from omicsclaw.ensemble.space import TuningCatalog
from omicsclaw.skills import load_skills

REPO = Path(__file__).resolve().parents[2]
FAKE_SKILLS = Path(__file__).resolve().parent / "fake_skills"


class _FakeExecutor:
    """Records calls; the supervised run reports nothing, so a trial ends at stage ``run``."""

    location = "local"
    python = "/fake/bin/python"

    def __init__(self) -> None:
        self.runs: list[list[str]] = []

    async def run(self, argv, *, cwd, env, log, timeout):
        self.runs.append(list(argv))
        return CommandResult(exit_code=1)

    async def capture(self, argv, *, cwd, timeout, env=None):
        return CommandResult(exit_code=0, output='DESCRIBE={"n_obs": 3, "obs_columns": []}')


def _runner(tmp_path: Path, executor, **kwargs) -> EnsembleRunner:
    catalog = TuningCatalog.from_skills(load_skills(FAKE_SKILLS))
    return EnsembleRunner(
        catalog=catalog,
        pool=ResourcePool(gpu_ids=(), memory_gb=64.0, cpus=8, gpu_detail="none in this test"),
        executor=executor,
        runs_root=tmp_path / "ws" / "ensemble_runs",
        repo_root=REPO,
        **kwargs,
    )


def _trial(runner: EnsembleRunner, tmp_path: Path):
    source = tmp_path / "in.h5ad"
    source.write_bytes(b"not read by the fake executor")
    spec = runner.prepare(skill="fake-domains", method="split", input=source, run_id="r1")
    result = asyncio.run(asyncio.wait_for(runner.run(spec), 60))
    record = json.loads((Path(result.output_dir) / "trial.json").read_text())
    return result, record


def test_the_described_environment_is_recorded_in_trial_json(tmp_path):
    described = {
        "executable": "/fake/bin/python",
        "version": "3.11.15",
        "prefix": "/fake",
        "packages": {"numpy": "2.0.2", "oc-missing": None},
        "missing": ["oc-missing"],
    }
    calls = []

    async def describe(executor, skill):
        calls.append((executor, skill))
        return described

    executor = _FakeExecutor()
    runner = _runner(tmp_path, executor, describe_environment=describe)
    result, record = _trial(runner, tmp_path)
    assert record["provenance"]["environment"] == described
    assert result.provenance["environment"] == described
    assert calls == [(executor, "fake-domains")]


def test_without_a_callback_no_environment_is_recorded(tmp_path):
    runner = _runner(tmp_path, _FakeExecutor())
    _, record = _trial(runner, tmp_path)
    assert "environment" not in record["provenance"]
    assert record["provenance"]["python"] == "/fake/bin/python"


def test_a_failing_callback_is_recorded_and_does_not_stop_the_trial(tmp_path):
    async def describe(executor, skill):
        raise RuntimeError("the probe could not start")

    executor = _FakeExecutor()
    result, record = _trial(_runner(tmp_path, executor, describe_environment=describe), tmp_path)
    assert record["provenance"]["environment"] == {"error": "RuntimeError: the probe could not start"}
    assert executor.runs, "the trial must still be run"
    assert result.stage == "run"


def test_a_callback_that_hangs_is_cut_off(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_module, "ENVIRONMENT_TIMEOUT_S", 0.2)

    async def describe(executor, skill):
        await asyncio.sleep(30)
        return {}

    executor = _FakeExecutor()
    result, record = _trial(_runner(tmp_path, executor, describe_environment=describe), tmp_path)
    assert "timed out" in record["provenance"]["environment"]["error"]
    assert executor.runs and result.stage == "run"


def test_a_cancelled_description_still_records_the_trial(tmp_path):
    started = asyncio.Event()

    async def describe(executor, skill):
        started.set()
        await asyncio.sleep(30)
        return {}

    runner = _runner(tmp_path, _FakeExecutor(), describe_environment=describe)
    source = tmp_path / "in.h5ad"
    source.write_bytes(b"x")
    spec = runner.prepare(skill="fake-domains", method="split", input=source, run_id="r1")

    async def main():
        task = asyncio.ensure_future(runner.run(spec))
        await asyncio.wait_for(started.wait(), 10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(main())
    trials = (runner.store.run_dir("r1") / "trials.jsonl").read_text().splitlines()
    assert json.loads(trials[-1])["status"] == "cancelled"


@pytest.mark.parametrize(
    "name",
    ["OMICSCLAW_ADAPTIVE_ENV", "OMICSCLAW_SKIP_ADAPTIVE_ENV", "OMICSCLAW_ENV_DIR", "OMICSCLAW_RUN_PYTHON"],
)
def test_the_retired_runner_variables_are_not_passed_to_trials(name):
    assert name not in ENV_WHITELIST
