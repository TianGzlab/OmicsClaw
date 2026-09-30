"""``optimize_params``, ``inspect_trials`` and ``select_result``.

``optimize_params`` is the deterministic pipeline in one call; the other two,
with ``run_skill``, are what the free-orchestration arm works with. All three
are ``AUTO`` (a deployment can require approval by rule); the read-only mode
refuses the two that write. Tool descriptions are fixed at mount time and do
not depend on the tissue, budget or image switches, so the arms of a
benchmark see the same text.
"""

from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("anndata")
pytest.importorskip("scanpy")

from omicsclaw.ensemble.tuning.budget import RunBudget  # noqa: E402
from omicsclaw.ensemble.tuning.ledger import load_selection  # noqa: E402
from omicsclaw.ensemble.tuning.llm import LLMSettings, ScriptedChatModel  # noqa: E402
from omicsclaw.ensemble.tuning.tools import (  # noqa: E402
    INSPECT_TRIALS_POLICY,
    OPTIMIZE_PARAMS_POLICY,
    OPTIMIZE_PARAMS_SCHEMA,
    SELECT_RESULT_POLICY,
    TuningToolkit,
)
from omicsclaw.skills import load_skills  # noqa: E402
from omicsclaw.tools._workspace import Workspace  # noqa: E402
from omicsclaw.tools.base import ApprovalMode, RiskLevel, ToolPolicy  # noqa: E402
from omicsclaw.tools.context import use_tool_context  # noqa: E402
from omicsclaw.tools.function_tool import ToolArgumentError  # noqa: E402
from tests.ensemble.tuning.fake_runner import FAKE_SKILLS, FakeRunner, write_input  # noqa: E402
from tests.ensemble.tuning.test_pipeline import PROPOSALS, SMALL, _decision  # noqa: E402


def test_the_schema_and_policies_are_as_specified():
    assert OPTIMIZE_PARAMS_SCHEMA["required"] == ["skill", "input"]
    assert set(OPTIMIZE_PARAMS_SCHEMA["properties"]) == {"skill", "input", "methods", "tissue", "k", "run_id", "images"}
    assert OPTIMIZE_PARAMS_POLICY == ToolPolicy(
        risk_level=RiskLevel.MEDIUM, approval_mode=ApprovalMode.AUTO, read_only=False, concurrency_safe=False,
        writes_workspace=True, touches_network=True, allowed_in_background=False,
        tags=frozenset({"skills", "ensemble", "tuning"}),
    )
    assert INSPECT_TRIALS_POLICY.read_only and INSPECT_TRIALS_POLICY.concurrency_safe
    assert INSPECT_TRIALS_POLICY.risk_level is RiskLevel.LOW
    assert not SELECT_RESULT_POLICY.read_only and not SELECT_RESULT_POLICY.concurrency_safe


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    root = tmp_path_factory.mktemp("tools")
    write_input(root / "data" / "in.h5ad")
    return root


def _toolkit(root, model=None, **kwargs):
    runner = FakeRunner(root)
    return TuningToolkit(
        runner=runner, workspace=Workspace(root), skills=load_skills(FAKE_SKILLS), model=model,
        llm_settings=LLMSettings(model="scripted-1", provider="test"), settings=SMALL, **kwargs,
    ), runner


def _call(tool, session="s1", **arguments):
    async def main():
        with use_tool_context(values={"session_id": session}):
            return await tool.execute(json.dumps(arguments))
    return asyncio.run(asyncio.wait_for(main(), 600))


def test_descriptions_do_not_depend_on_the_switches(env):
    plain, _ = _toolkit(env)
    other, _ = _toolkit(env, budget=RunBudget({"twod": 1}), tissue_enabled=False)
    for mode in ("all", "free", "tuning"):
        a = [t.definition() for t in plain.tools(mode, run_skill=_stub())]
        b = [t.definition() for t in other.tools(mode, run_skill=_stub())]
        assert a == b


def _stub():
    from omicsclaw.tools.function_tool import FunctionTool

    return FunctionTool("run_skill", "stub", lambda: "")


def test_modes_mount_the_documented_tools(env):
    toolkit, _ = _toolkit(env)
    names = lambda mode: [t.name for t in toolkit.tools(mode, run_skill=_stub())]  # noqa: E731
    assert names("all") == ["run_skill", "inspect_trials", "select_result", "optimize_params"]
    assert names("free") == ["run_skill", "inspect_trials", "select_result"]
    assert names("tuning") == ["optimize_params"]


@pytest.fixture(scope="module")
def optimized(env):
    model = ScriptedChatModel({"k_decision": [_decision(5)], "propose:*": [PROPOSALS]})
    toolkit, runner = _toolkit(env, model)
    body = json.loads(_call(toolkit.optimize_params_tool(), skill="fake-domains", input="data/in.h5ad",
                            methods=["twod", "grid1"], tissue="human cortex", run_id="opt1", images=True))
    return body, toolkit, runner


def test_optimize_params_returns_a_compact_answer(optimized, env):
    body, _, _ = optimized
    assert body["status"] == "ok" and body["chosen_k"]["k"] == 5 and body["chosen_k"]["source"] == "llm"
    assert body["chosen_k"]["rationale"] == "curves and markers"
    assert set(body["methods"]) == {"twod", "grid1"} and body["final"]["method"] in ("twod", "grid1")
    assert body["llm_calls"] == 2 and any("images were not used" in n for n in body["notes"])
    assert load_selection(body["selection"]).k["chosen"] == 5


def test_a_count_in_the_tissue_is_refused_before_anything_runs(env):
    model = ScriptedChatModel({})
    toolkit, runner = _toolkit(env, model)
    with pytest.raises(ToolArgumentError, match="number of regions"):
        _call(toolkit.optimize_params_tool(), skill="fake-domains", input="data/in.h5ad", tissue="cortex, 6 layers")
    assert runner.runs == [] and model.calls == []


def test_a_withheld_tissue_never_reaches_the_model(env):
    model = ScriptedChatModel({"k_decision": [_decision(5)], "propose:*": [PROPOSALS]})
    toolkit, _ = _toolkit(env, model, tissue_enabled=False)
    body = json.loads(_call(toolkit.optimize_params_tool(), skill="fake-domains", input="data/in.h5ad",
                            methods=["twod"], tissue="human cortex", run_id="wh1"))
    assert all("human cortex" not in m.content for _, msgs in model.calls for m in msgs)
    assert any("withholds" in n for n in body["notes"])
    assert load_selection(body["selection"]).provenance["tissue_withheld"] is True


def test_inspect_trials_reports_scores_and_agreement(optimized):
    body, toolkit, _ = optimized
    run_id = body["run_id"]
    twod = body["methods"]["twod"]["trial"]
    grid = body["methods"]["grid1"]["trial"]
    result = json.loads(_call(toolkit.inspect_trials_tool(), run_id=run_id,
                              trials=[{"method": "twod", "trial": twod}, {"method": "grid1", "trial": grid}],
                              markers_for={"method": "twod", "trial": twod}, top_n=2))
    assert [t["n_labels"] for t in result["trials"]] == [5, 5]
    assert result["trials"][0]["fixed_k_score"] == pytest.approx(body["methods"]["twod"]["fixed_k_score"])
    assert result["ami"][0]["ami"] == pytest.approx(1.0)
    assert len(next(iter(result["markers"]["domains"].values()))) == 2
    with pytest.raises(ToolArgumentError):
        _call(toolkit.inspect_trials_tool(), run_id=run_id, trials=[{"method": "twod", "trial": "t9999"}])


def test_select_result_checks_k_and_writes_the_selection(optimized):
    body, toolkit, _ = optimized
    run_id = body["run_id"]
    twod = body["methods"]["twod"]["trial"]
    written = json.loads(_call(toolkit.select_result_tool(), run_id=run_id, k=5,
                               final={"method": "twod", "trial": twod}, per_method={"twod": twod},
                               rationale="best"))
    selection = load_selection(written["selection"])
    assert selection.arm == "free" and selection.k["source"] == "agent" and selection.final["trial"] == twod
    with pytest.raises(ToolArgumentError, match="clusters"):
        _call(toolkit.select_result_tool(), run_id=run_id, k=4, final={"method": "twod", "trial": twod},
              per_method={"twod": twod}, rationale="x")


def test_optimize_params_draws_from_the_session_budget(env):
    budget = RunBudget({"twod": 4})
    model = ScriptedChatModel({"k_decision": [_decision(5)], "propose:*": [PROPOSALS]})
    toolkit, _ = _toolkit(env, model, budget=budget)
    body = json.loads(_call(toolkit.optimize_params_tool(), session="s9", skill="fake-domains",
                            input="data/in.h5ad", methods=["twod"], run_id="bud9"))
    assert budget.used("s9", "twod") == 4 and body["methods"]["twod"]["new_runs"] == 4


def test_the_obs_allowlist_refuses_inputs(env):
    toolkit, _ = _toolkit(env, ScriptedChatModel({}), obs_allowlist=("cell_type",))
    with pytest.raises(ToolArgumentError, match="obs"):
        _call(toolkit.optimize_params_tool(), skill="fake-domains", input="data/in.h5ad")
    with pytest.raises(Exception, match="obs"):
        asyncio.run(toolkit.input_check(env / "data" / "in.h5ad", "fake-domains"))
