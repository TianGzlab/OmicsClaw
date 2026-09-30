"""The whole pipeline on the fake skill, with a scripted model.

``twod`` has two dimensions left once K is fixed (alpha, beta) and goes
through both stages; ``grid1`` (layers) and ``cal`` (smooth; resolution
calibrates K) have one and get a grid with no model call; ``flaky`` returns
four labels when asked for five and fails above five, so at K=5 it has no
trial at K and falls back to its default, and at K=6 it fails entirely.
Trials run in-process (see ``fake_runner``) so the branches are cheap; one
test at the end drives the real runner.
"""

from __future__ import annotations

import asyncio
import json
import random
import shutil
from pathlib import Path

import pytest

pytest.importorskip("anndata")
pytest.importorskip("scanpy")

from omicsclaw.ensemble.tuning.budget import RunBudget  # noqa: E402
from omicsclaw.ensemble.tuning.ledger import Ledger, load_selection  # noqa: E402
from omicsclaw.ensemble.tuning.llm import CassetteChatModel, LLMSettings, ScriptedChatModel  # noqa: E402
from omicsclaw.ensemble.tuning.pipeline import TuningPipeline, TuningRequest, TuningSettings  # noqa: E402
from omicsclaw.ensemble.tuning.prompts import SkillText  # noqa: E402
from omicsclaw.ensemble.tuning.scoring import KReference, score_trial  # noqa: E402
from tests.ensemble.tuning.fake_runner import FakeRunner, default_behaviour, write_input  # noqa: E402

SMALL = TuningSettings(
    grid=(3, 4, 5, 6), resolutions=(0.3, 0.5, 0.7, 0.9, 1.0, 1.2), n_sub=3,
    subsample_seeds=(5701, 5702, 5703), boot_fc=20, boot_a=10, stability_processes=1,
)
METHODS = ("twod", "grid1", "cal", "flaky")
SETTINGS = LLMSettings(model="scripted-1", provider="test", temperature=0.3)


def _skill(_name):
    return SkillText("# fake-domains\nA fixture that labels observations by coordinate bins.", "")


def _decision(k):
    return json.dumps({"chosen_k": k, "rationale": "curves and markers",
                       "evidence": [{"k": k, "kind": "curve", "curve": "f", "reading": "present"}],
                       "confidence": "low"})


PROPOSALS = json.dumps({"proposals": [
    {"params": {"alpha": 0.7}, "why": "a"},
    {"params": {"alpha": 0.65, "beta": 120}, "why": "b"},
    {"params": {"beta": 200}, "why": "c"},
]})


@pytest.fixture(scope="module")
def workspace(tmp_path_factory):
    root = tmp_path_factory.mktemp("pipeline")
    source = write_input(root / "data" / "in.h5ad")
    return root, source


def _pipeline(root, model=None, *, runner=None, settings=SMALL, **kwargs):
    runner = runner or FakeRunner(root)
    return TuningPipeline(runner, model=model, llm_settings=SETTINGS, skill_text=_skill, settings=settings,
                          **kwargs), runner


def _request(source, run_id, **kwargs):
    values = dict(skill="fake-domains", input=source, run_id=run_id, methods=METHODS, tissue="human cortex")
    values.update(kwargs)
    values.setdefault("probe_base", "unit" if values["methods"] == METHODS else "p-" + "_".join(values["methods"]))
    return TuningRequest(**values)


def _run(pipeline, request):
    return asyncio.run(asyncio.wait_for(pipeline.run(request), 600))


@pytest.fixture(scope="module")
def main_run(workspace):
    root, source = workspace
    model = ScriptedChatModel({"k_decision": [_decision(5)], "propose:*": [PROPOSALS]})
    pipeline, runner = _pipeline(root, model)
    selection = _run(pipeline, _request(source, "det1"))
    return selection, model, runner, root


def test_the_probe_runs_every_design_trial_once(main_run):
    _, _, runner, root = main_run
    probe = [r for r in runner.runs if r[0].startswith("unit-")]
    exact = [r for r in probe if r[0] == "unit-probe" and r[1] != "cal"]
    assert len(exact) == 3 * 4
    assert len([r for r in probe if r[0] == "unit-probe" and r[1] == "cal"]) == 6
    assert len([r for r in probe if r[0].startswith("unit-sub")]) == 3 * 6
    evidence = root / "ensemble_runs" / "unit-probe" / "evidence"
    stability = json.loads((evidence / "stability.json").read_text())
    assert set(stability["per_k"]) == {"3", "4", "5", "6"}
    for row in stability["per_k"].values():
        assert {"f_lo", "f_hi", "c_lo", "c_hi", "a_lo", "a_hi", "peak_frequency"} <= set(row)
    markers = json.loads((evidence / "markers.json").read_text())
    assert set(markers["compact"]) == {"3", "4", "5", "6"}


def test_one_dimensional_methods_use_a_grid_and_no_model(main_run):
    selection, model, _, _ = main_run
    assert [p for p, _ in model.calls] == ["k_decision", "propose:twod"]
    assert selection.methods["grid1"]["strategy"] == "grid"
    assert selection.methods["grid1"]["new_runs"] == 4
    assert selection.methods["cal"]["strategy"] == "grid"
    assert selection.methods["cal"]["evaluated"] == 13


def test_the_two_stage_method_follows_the_model_then_refines(main_run):
    selection, _, _, root = main_run
    twod = selection.methods["twod"]
    assert twod["strategy"] == "two_stage" and twod["stage2_skipped"] is False
    assert twod["params"]["alpha"] == 0.7 and twod["source"] == "llm"
    assert twod["new_runs"] <= 12 and twod["evaluated"] <= 13
    ledger = Ledger(root / "ensemble_runs" / "det1" / "tuning")
    stages = {(e["method"], e["stage"]) for e in ledger.events("stage")}
    assert ("twod", "stage1") in stages and ("twod", "stage2") in stages
    sources = [e["source"] for e in ledger.events("trial") if e["method"] == "twod"]
    assert sources.count("sweep") == 3 and sources.count("llm") == 3 and sources.count("neighbourhood") >= 4


def test_k_and_the_final_answer(main_run):
    selection, _, _, _ = main_run
    assert selection.k["chosen"] == 5 and selection.k["source"] == "llm"
    assert selection.final["method"] in ("twod", "grid1", "cal")
    assert selection.methods["flaky"]["status"] == "fallback_default"
    assert selection.methods["flaky"]["n_labels"] == 4
    assert selection.status == "ok"


def test_the_selection_file_and_the_record(main_run):
    selection, _, _, root = main_run
    tuning = root / "ensemble_runs" / "det1" / "tuning"
    loaded = load_selection(tuning / "selection.json")
    assert loaded.k["chosen"] == 5 and loaded.provenance["model"] == "scripted-1"
    record = json.loads((tuning / "tuning.json").read_text())["tuning_record"]
    assert record["schema"] == "omicsclaw.ensemble.tuning_record/1"
    assert set(record["methods"]) == set(METHODS)
    assert "ari" not in json.dumps(record).lower().replace("variance", "")
    kinds = {e["kind"] for e in Ledger(tuning).events()}
    assert {"start", "probe_trial", "trial", "stability", "llm_call", "k_decision", "stage", "select", "end"} <= kinds


def test_fixed_k_scores_can_be_recomputed_from_the_reference(main_run):
    selection, _, _, root = main_run
    tuning = root / "ensemble_runs" / "det1" / "tuning"
    reference = json.loads((tuning / "reference.json").read_text())["per_k"]["5"]
    twod = selection.methods["twod"]
    record = json.loads((tuning / "tuning.json").read_text())["tuning_record"]["methods"]["twod"]
    chosen = next(e for e in record["evaluated"] if e["trial"] == twod["trial"])
    assert chosen["fixed_k_score"] == twod["fixed_k_score"]
    ref = KReference.from_json(reference)
    pas = 0.9 - 0.5 * abs(0.7 - 0.7)
    doc = {"adjusted": {"pas": pas}, "raw": {"silhouette_pca": 0.2},
           "diagnostics": {"pas": {"se_adjusted": 0.005}, "silhouette_pca": {"se": 0.1 / 240 ** 0.5}}}
    assert score_trial(doc, ref).score == pytest.approx(twod["fixed_k_score"], abs=1e-6)


def test_the_probe_is_reused_by_a_second_arm(workspace, main_run):
    root, source = workspace
    runner = FakeRunner(root)
    pipeline, _ = _pipeline(root, runner=runner)
    selection = _run(pipeline, _request(source, "rand1", arm="random", random_index=1))
    assert not any(r[0].startswith("unit-") for r in runner.runs)
    assert selection.provenance["probe_reused"] is True
    assert selection.k["source"] == "fallback" and selection.k["chosen"] == selection.k["fallback_k"]
    ledger = Ledger(root / "ensemble_runs" / "rand1" / "tuning")
    assert ledger.events("llm_call") == []
    sources = {e["source"] for e in ledger.events("trial") if e["method"] == "twod"}
    assert "random" in sources and "llm" not in sources


def test_stage2_is_skipped_when_stage1_does_not_beat_the_default(workspace, main_run):
    root, source = workspace

    def behaviour(method, params):
        out = default_behaviour(method, params)
        if method == "twod" and "fail" not in out:
            out["pas"] = 0.9 - 0.5 * abs(params.get("alpha", 0.5) - 0.5) - 0.05 * abs(params.get("beta", 100) - 100) / 300
        return out

    model = ScriptedChatModel({"k_decision": [_decision(5)], "propose:*": [PROPOSALS]})
    pipeline, _ = _pipeline(root, model, runner=FakeRunner(root, behaviour=behaviour))
    selection = _run(pipeline, _request(source, "skip1", methods=("twod",)))
    twod = selection.methods["twod"]
    assert twod["stage2_skipped"] is True and twod["new_runs"] == 6
    assert twod["params"]["alpha"] == 0.5


def test_a_marker_request_a_non_peak_k_and_a_fallback(workspace, main_run):
    root, source = workspace
    model = ScriptedChatModel({"k_decision": ['{"request_markers": [3]}', _decision(3)],
                               "propose:*": [PROPOSALS]})
    pipeline, _ = _pipeline(root, model)
    selection = _run(pipeline, _request(source, "req1", methods=("twod",)))
    assert selection.k["requested_markers"] in ([3], [])
    assert selection.k["chosen"] == 3
    bad = ScriptedChatModel({"k_decision": ["no", "no", "no"], "propose:*": [PROPOSALS]})
    pipeline, _ = _pipeline(root, bad)
    fallen = _run(pipeline, _request(source, "fb1", methods=("twod",)))
    assert fallen.k["source"] == "fallback" and fallen.k["failure"]
    assert fallen.provenance["fallbacks"] >= 1


def test_bad_proposals_are_topped_up_by_random_search(workspace, main_run):
    root, source = workspace
    partly = json.dumps({"proposals": [{"params": {"alpha": 5.0}}, {"params": {"n": 9}},
                                       {"params": {"beta": 60}}]})
    model = ScriptedChatModel({"k_decision": [_decision(5)], "propose:*": [partly]})
    pipeline, _ = _pipeline(root, model)
    _run(pipeline, _request(source, "top1", methods=("twod",)))
    ledger = Ledger(root / "ensemble_runs" / "top1" / "tuning")
    stage1 = [e for e in ledger.events("trial") if e["stage"] == "stage1"]
    assert sorted(e["source"] for e in stage1).count("random_fallback") == 2
    assert sorted(e["source"] for e in stage1).count("llm") == 1
    broken = ScriptedChatModel({"k_decision": [_decision(5)], "propose:*": ["x", "y", "z"]})
    pipeline, _ = _pipeline(root, broken)
    _run(pipeline, _request(source, "top2", methods=("twod",)))
    stage1 = [e for e in Ledger(root / "ensemble_runs" / "top2" / "tuning").events("trial") if e["stage"] == "stage1"]
    assert sorted(e["source"] for e in stage1).count("random_fallback") == 3


def test_a_method_that_always_fails_is_failed(workspace, main_run):
    root, source = workspace
    pipeline, _ = _pipeline(root)
    selection = _run(pipeline, _request(source, "user6", k=6, methods=("flaky", "twod")))
    assert selection.arm == "user" and selection.k["source"] == "user"
    assert selection.methods["flaky"]["status"] == "failed"
    assert selection.status == "partial"


def test_a_degenerate_reference_gives_no_fixed_k_score(workspace, main_run):
    root, source = workspace
    pipeline, _ = _pipeline(root)
    selection = _run(pipeline, _request(source, "user5", k=5, methods=("twod",), probe_base="solo"))
    reference = json.loads((root / "ensemble_runs" / "user5" / "tuning" / "reference.json").read_text())
    assert reference["per_k"]["5"]["degenerate"] == ["pas", "silhouette_pca"]
    assert selection.methods["twod"]["status"] == "fallback_default"
    assert selection.final is None and selection.status == "partial"


def test_the_wall_clock_limit_stops_the_run(workspace, main_run):
    root, source = workspace
    settings = TuningSettings(**{**SMALL.__dict__, "max_s": 0.5})
    pipeline, _ = _pipeline(root, settings=settings, runner=FakeRunner(root, delay_s=2.0))
    selection = _run(pipeline, _request(source, "slow1", arm="random", probe_base="slowprobe"))
    assert selection.status == "failed"
    assert any("wall-clock" in note for note in selection.provenance["notes"])


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_caps_hold_under_random_failures(workspace, main_run, seed):
    """Whatever fails, no method spends more new runs than its cap or
    evaluates more than 12 new parameter sets."""
    root, source = workspace
    rng = random.Random(seed)
    failures = {}

    def behaviour(method, params):
        key = json.dumps([method, sorted(params.items())])
        if key not in failures:
            failures[key] = rng.random() < 0.3
        if failures[key]:
            return {"fail": True}
        return default_behaviour(method, params)

    runner = FakeRunner(root, behaviour=behaviour)
    model = ScriptedChatModel({"k_decision": [_decision(4)], "propose:*": [PROPOSALS]})
    pipeline, _ = _pipeline(root, model, runner=runner, budget=RunBudget(None))
    selection = _run(pipeline, _request(source, f"prop{seed}"))
    for method, entry in selection.methods.items():
        cap = selection.budget["caps"][method]
        assert selection.budget["used"][method] <= cap
        new_sets = [e for e in Ledger(root / "ensemble_runs" / f"prop{seed}" / "tuning").events("trial")
                    if e["method"] == method and e["new_run"] and e["source"] != "calibration"]
        assert len(new_sets) <= 12, method


def test_a_session_budget_is_shared_with_run_skill(workspace, main_run):
    root, source = workspace
    budget = RunBudget({"twod": 5})
    model = ScriptedChatModel({"k_decision": [_decision(5)], "propose:*": [PROPOSALS]})
    pipeline, _ = _pipeline(root, model, budget=budget, session="s1")
    selection = _run(pipeline, _request(source, "bud1", methods=("twod",)))
    assert budget.used("s1", "twod") == 5 and selection.methods["twod"]["new_runs"] == 5


def test_replaying_the_cassette_reproduces_the_selection(workspace, main_run):
    root, source = workspace
    model = ScriptedChatModel({"k_decision": [_decision(5)], "propose:*": [PROPOSALS]})
    pipeline, _ = _pipeline(root, model)
    first = _run(pipeline, _request(source, "rep1", methods=("twod", "grid1")))
    tuning = root / "ensemble_runs" / "rep1" / "tuning"
    saved = tuning.parent.parent / "rep1-ledger"
    shutil.copytree(tuning, saved)
    shutil.rmtree(tuning.parent)
    cassette = CassetteChatModel.from_ledger(saved)
    pipeline, _ = _pipeline(root, cassette)
    second = _run(pipeline, _request(source, "rep1", methods=("twod", "grid1")))

    def stripped(selection):
        document = selection.to_json()
        document.pop("written_at")
        document["provenance"].pop("date")
        document["provenance"].pop("probe_reused")
        return json.dumps(document, sort_keys=True)

    a, b = stripped(first), stripped(second)
    if a != b:
        index = next(i for i, (x, y) in enumerate(zip(a, b)) if x != y)
        pytest.fail(f"differs at {index}: {a[index - 300:index + 200]!r} vs {b[index - 300:index + 200]!r}")


def test_an_input_without_x_pca_or_with_extra_obs_is_refused(workspace, tmp_path):
    import anndata

    from omicsclaw.ensemble.space import SpecError

    root, source = workspace
    adata = anndata.read_h5ad(source)
    del adata.obsm["X_pca"]
    bare = tmp_path / "bare.h5ad"
    adata.write_h5ad(bare)
    pipeline, _ = _pipeline(root)
    with pytest.raises(SpecError, match="X_pca"):
        _run(pipeline, _request(source=bare, run_id="bare1", arm="random"))
    pipeline, _ = _pipeline(root, obs_allowlist=["cell_type"])
    with pytest.raises(SpecError, match="batch"):
        _run(pipeline, _request(source, "obs1", arm="random"))
