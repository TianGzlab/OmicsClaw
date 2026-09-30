"""The hold-out driver: what it records, how it reports progress, and truth extraction.

The hold-out run is not gated by a technical freeze (owner ruling): the
settings it runs with are recorded in the run directory — the settings file,
model, trial seed, git state and a code digest — so the run can be traced,
and each step writes its result when it finishes so an interrupted run
resumes without redoing finished steps.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

VALIDATION = Path(__file__).resolve().parents[3] / "docs" / "plans" / "0057-validation"
sys.path.insert(0, str(VALIDATION))

import run_holdout  # noqa: E402


def test_the_run_record_holds_settings_model_seed_and_git_state(tmp_path):
    directory = run_holdout.record_run(tmp_path, {"model": "m", "provider": "p"})
    record = json.loads((directory / "run.json").read_text())
    assert record["llm"] == {"model": "m", "provider": "p"} and record["trial_seed"] == 0
    assert len(record["git"]["head"]) == 40 and isinstance(record["git"]["status"], list)
    assert "omicsclaw/ensemble/_seed/sitecustomize.py" in record["code_digest"]["files"]
    assert (directory / "frozen_settings.json").is_file()


def test_status_counts_finished_steps(tmp_path):
    (tmp_path / "units.json").write_text(json.dumps({"u01": {}, "u02": {}}))
    for step in ("probe", "a0k", "A1/r1"):
        (tmp_path / "u01" / step).mkdir(parents=True)
        (tmp_path / "u01" / step / "result.json").write_text("{}")
    (tmp_path / "errors.jsonl").write_text(json.dumps({"at": "t", "uid": "u02", "step": "probe", "error": "x"}) + "\n")
    state = run_holdout.status(tmp_path)
    assert state["per_unit"] == {"u01": "3/13", "u02": "0/13"}
    assert state["units_complete"] == "0/2" and state["n_errors"] == 1


def test_truth_extraction_reads_the_layer_column_per_slice(tmp_path):
    """On a synthetic SingleCellExperiment; the real object is opened only after the hold-out."""
    import shutil
    import subprocess

    import prepare_dlpfc

    if not Path(prepare_dlpfc.RSCRIPT).exists():
        pytest.skip("Rscript is not installed")
    rdata = tmp_path / "sce.Rdata"
    make = (
        "suppressMessages(library(SingleCellExperiment));"
        "sce <- SingleCellExperiment(assays=list(counts=matrix(0, 2, 4)));"
        "colData(sce)$sample_name <- c('151507','151507','151508','151508');"
        "colData(sce)$barcode <- c('A-1','B-1','A-1','C-1');"
        "colData(sce)$layer_guess <- c('Layer1', NA, 'WM', 'Layer3');"
        f"save(sce, file='{rdata}')"
    )
    done = subprocess.run([prepare_dlpfc.RSCRIPT, "-e", make], capture_output=True, text=True)
    if done.returncode != 0:
        pytest.skip(f"SingleCellExperiment unavailable: {done.stderr[-200:]}")
    mapping = {"u01": {"dataset": "DLPFC", "slice": "151507"}, "u02": {"dataset": "DLPFC", "slice": "151508"},
               "c01": {"dataset": "CosMx"}}
    truth_map = prepare_dlpfc.extract_truth(rdata, tmp_path / "truth", mapping)
    assert set(truth_map) == {"u01", "u02"} and truth_map["u01"]["holdout"] is True
    assert (tmp_path / "truth" / "u01.csv").read_text().splitlines() == ["obs_id,label", "A-1,Layer1"]
    assert (tmp_path / "truth" / "u02.csv").read_text().splitlines() == ["obs_id,label", "A-1,WM", "C-1,Layer3"]


# ---- model outages ------------------------------------------------------------------------------


class _Flaky:
    name = "flaky"

    def __init__(self, failures, exc):
        self.failures = failures
        self.exc = exc
        self.calls = 0

    async def generate(self, messages, tools=None):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.exc
        return "ok"


def _no_sleep(_):
    import asyncio

    return asyncio.sleep(0)


def test_transient_model_failures_are_retried_with_back_off():
    import asyncio

    from common import RetryingModel

    inner = _Flaky(3, RuntimeError("ProviderError: streaming chat completion failed: APIConnectionError: Connection error."))
    waits = []

    async def sleep(seconds):
        waits.append(seconds)

    model = RetryingModel(inner, attempts=5, base=5, cap=12, sleep=sleep)
    assert asyncio.run(model.generate([])) == "ok"
    assert inner.calls == 4 and waits == [5, 10, 12]
    hard = RetryingModel(_Flaky(1, ValueError("bad request")), sleep=sleep)
    with pytest.raises(ValueError):
        asyncio.run(hard.generate([]))


def test_a_step_that_fails_transiently_is_retried_then_left_for_the_next_resume(tmp_path):
    import asyncio

    calls = []

    async def make():
        calls.append(1)
        raise RuntimeError("APITimeoutError: Request timed out.")

    assert asyncio.run(run_holdout._step(tmp_path, "u01", "A3r1", make, retries=2, backoff_s=0)) is None
    assert len(calls) == 3
    assert len((tmp_path / "errors.jsonl").read_text().splitlines()) == 3


def test_arm_results_with_provider_failures_are_set_aside(tmp_path):
    for name, error in (("A1/r1", "APIConnectionError"), ("A1/r2", "")):
        tuning = tmp_path / "u01" / name / "ws" / "tuning"
        tuning.mkdir(parents=True)
        (tuning / "ledger.jsonl").write_text(json.dumps({"kind": "llm_call", "provider_error": error, "usage": {}}) + "\n")
        (tmp_path / "u01" / name / "result.json").write_text(json.dumps({"selection": str(tuning / "selection.json")}))
    assert run_holdout.invalidate_provider_failures(tmp_path) == ["u01/A1/r1"]
    assert (tmp_path / "u01" / "A1" / "r1" / "result.provider_error.json").exists()
    assert (tmp_path / "u01" / "A1" / "r2" / "result.json").exists()
