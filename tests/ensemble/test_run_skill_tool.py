"""``run_skill``: schema, policy, argument checking, and how it runs in a turn.

The policy is declared field by field because the defaults of
:class:`~omicsclaw.tools.ToolPolicy` are the guarded ones, and each departure
is a decision: ``AUTO`` so a batch of trials does not wait on a person (and
does not hang on the Desktop surface, which cannot ask), ``concurrency_safe``
so several calls in one turn run together, not ``read_only`` so the
read-only mode refuses it.

A trial that fails is an Observation like a non-zero ``bash`` exit, not a
tool error; only arguments the model can correct are errors. The whole call
runs with the engine's per-tool timeout paused, because trials legitimately
run for hours; the tool bounds itself instead, from admission onward, so a
hung trial still ends.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from omicsclaw.engine.config import EngineConfig
from omicsclaw.engine.executor import execute_tool_calls
from omicsclaw.ensemble.execution import CommandResult
from omicsclaw.ensemble.resources import ResourcePool
from omicsclaw.ensemble.runner import EnsembleRunner, Limits, TrialResult, TrialSpec
from omicsclaw.ensemble.resources import ResourceRequest
from omicsclaw.ensemble.space import SpecError, TuningCatalog
from omicsclaw.ensemble.tool import RUN_SKILL_POLICY, RUN_SKILL_SCHEMA, run_skill_tool
from omicsclaw.schema import ToolCall
from omicsclaw.skills import load_skills
from omicsclaw.tools import ToolRegistry
from omicsclaw.tools._workspace import Workspace
from omicsclaw.tools.base import ApprovalMode, RiskLevel, ToolPolicy
from omicsclaw.tools.context import use_timeout_pause
from omicsclaw.tools.function_tool import FunctionTool, ToolArgumentError

REPO = Path(__file__).resolve().parents[2]
FAKE_SKILLS = Path(__file__).resolve().parent / "fake_skills"


def _catalog() -> TuningCatalog:
    return TuningCatalog.from_skills(load_skills(FAKE_SKILLS))


@dataclass
class _FakeRunner:
    """Validates like the real runner's front half; runs by sleeping and recording."""

    delay: float = 0.3
    catalog: TuningCatalog = field(default_factory=_catalog)
    max_queue_s: float = 7200.0
    max_trial_s: float = 7200.0
    score_timeout_s: float = 120.0
    status: str = "ok"
    intervals: list = field(default_factory=list)
    paused_during_run: list = field(default_factory=list)
    pause_probe: object = None

    @property
    def call_ceiling_s(self) -> float:
        return 300 + 300 + self.max_queue_s + self.max_trial_s + self.score_timeout_s + 60

    def prepare(self, *, skill, method, input, params, run_id, timeout_s):
        spec = self.catalog.get(skill)
        if spec is None:
            raise SpecError(f"skill {skill!r} cannot be run by run_skill")
        from omicsclaw.ensemble.space import validate_params

        values = validate_params(spec, method, params)
        if run_id is not None and not run_id.islower():
            raise SpecError(f"run_id {run_id!r} must match the pattern")
        if timeout_s is not None and timeout_s > self.max_trial_s:
            raise SpecError("timeout_s exceeds this deployment's ceiling")
        return TrialSpec(skill, method, Path(input), values, run_id or "r1",
                         Limits(60, 1), ResourceRequest("none", 1, 1))

    async def run(self, spec, *, backstop_s=None):
        began = time.monotonic()
        if self.pause_probe is not None:
            self.paused_during_run.append(self.pause_probe())
        await asyncio.sleep(self.delay)
        self.intervals.append((began, time.monotonic()))
        return TrialResult(
            status=self.status, stage="score" if self.status == "ok" else "admission",
            run_id=spec.run_id, method=spec.method, trial="t0001", output_dir="/ws/ensemble_runs/r1",
            params=dict(spec.params), degraded="no_gpu" if spec.method == "gpu" else "",
            metrics={"score": 0.5, "n_labels": 3, "raw": {"chaos": 0.1}, "adjusted": {"chaos": 0.9}}
            if self.status == "ok" else None,
            score=0.5 if self.status == "ok" else None,
            error="" if self.status == "ok" else "method requires a GPU; none detected",
        )


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "in.h5ad").write_bytes(b"not really")
    return Workspace(tmp_path)


def _call(tool, **arguments):
    return asyncio.run(tool.execute(json.dumps(arguments)))


# ---- the declaration ---------------------------------------------------------------------


def test_the_schema_puts_skill_first_for_rule_matching(workspace):
    tool = run_skill_tool(_FakeRunner(), workspace)
    schema = tool.definition().input_schema
    assert schema == RUN_SKILL_SCHEMA
    assert schema["required"][0] == "skill"
    assert schema["properties"]["skill"]["type"] == "string"
    assert schema["additionalProperties"] is False


def test_the_policy_is_declared_field_by_field(workspace):
    assert run_skill_tool(_FakeRunner(), workspace).policy == ToolPolicy(
        risk_level=RiskLevel.MEDIUM,
        approval_mode=ApprovalMode.AUTO,
        read_only=False,
        concurrency_safe=True,
        writes_workspace=True,
        writes_config=False,
        touches_network=False,
        prompts_for_itself=False,
        allowed_in_background=False,
        tags=frozenset({"skills", "ensemble", "execution"}),
    )
    assert RUN_SKILL_POLICY.concurrency_safe


def test_the_description_is_stable_and_names_the_ceiling(workspace):
    first = run_skill_tool(_FakeRunner(), workspace).definition().description
    second = run_skill_tool(_FakeRunner(), workspace).definition().description
    assert first == second
    assert "fake-domains: split" in first
    assert "15180 s" in first
    assert "turn timeout" in first
    assert "bash" in first


# ---- arguments the model can correct ------------------------------------------------------


@pytest.mark.parametrize(
    "arguments, fragment",
    [
        ({"skill": "nope", "method": "split", "input": "data/in.h5ad"}, "cannot be run"),
        ({"skill": "fake-domains", "method": "zzz", "input": "data/in.h5ad"}, "no method 'zzz'"),
        ({"skill": "fake-domains", "method": "split", "input": "data/in.h5ad", "params": {"n": 99}}, "outside"),
        ({"skill": "fake-domains", "method": "split", "input": "missing.h5ad"}, "not a file"),
        ({"skill": "fake-domains", "method": "split", "input": "/etc/passwd"}, "outside"),
        ({"skill": "fake-domains", "method": "split", "input": "data/in.h5ad", "run_id": "BAD"}, "run_id"),
        ({"skill": "fake-domains", "method": "split", "input": "data/in.h5ad", "timeout_s": 1e9}, "ceiling"),
        ({"skill": "fake-domains", "method": "split"}, "input"),
        ({"skill": "fake-domains", "method": "split", "input": "data/in.h5ad", "extra": 1}, "extra"),
    ],
)
def test_invalid_arguments_are_tool_errors(workspace, arguments, fragment):
    tool = run_skill_tool(_FakeRunner(), workspace)
    with pytest.raises(ToolArgumentError, match=fragment):
        _call(tool, **arguments)


def test_invalid_arguments_become_is_error_observations(workspace):
    registry = ToolRegistry()
    registry.register(run_skill_tool(_FakeRunner(), workspace))
    result = asyncio.run(registry.execute(ToolCall(
        id="1", name="run_skill", arguments=json.dumps({"skill": "nope", "method": "x", "input": "data/in.h5ad"})
    )))
    assert result.is_error


# ---- results -------------------------------------------------------------------------------


def test_a_failed_trial_is_an_ordinary_observation(workspace):
    registry = ToolRegistry()
    registry.register(run_skill_tool(_FakeRunner(status="failed"), workspace))
    result = asyncio.run(registry.execute(ToolCall(
        id="1", name="run_skill",
        arguments=json.dumps({"skill": "fake-domains", "method": "needsgpu", "input": "data/in.h5ad"}),
    )))
    assert not result.is_error
    body = json.loads(result.output)
    assert (body["status"], body["stage"]) == ("failed", "admission")
    assert "requires a GPU" in body["error"]


def test_the_result_carries_the_documented_fields(workspace):
    body = json.loads(_call(run_skill_tool(_FakeRunner(), workspace),
                            skill="fake-domains", method="gpu", input="data/in.h5ad"))
    assert set(body) == {
        "status", "stage", "run_id", "method", "trial", "output_dir", "params", "metrics",
        "fixed_k_score", "fixed_k_se", "wall_s",
        "queued_s", "peak_mem_gb", "mem_metric", "lease_gpu", "device", "device_source", "degraded",
        "h5ad", "error", "log",
    }
    assert body["degraded"] == "no_gpu"
    assert body["metrics"] == {"score": 0.5, "n_labels": 3, "components": {"chaos": {"raw": 0.1, "adjusted": 0.9}}}
    assert "ari" not in json.dumps(body) and "nmi" not in json.dumps(body)


# ---- the engine's timeout is paused for the whole call ------------------------------------------


def test_the_whole_call_runs_inside_the_timeout_pause(workspace):
    state = {"depth": 0, "entered": 0, "exited": 0}

    @contextlib.contextmanager
    def pause():
        state["depth"] += 1
        state["entered"] += 1
        try:
            yield
        finally:
            state["depth"] -= 1
            state["exited"] += 1

    runner = _FakeRunner(pause_probe=lambda: state["depth"])
    tool = run_skill_tool(runner, workspace)

    async def main():
        with use_timeout_pause(pause):
            return await tool.execute(json.dumps({"skill": "fake-domains", "method": "split", "input": "data/in.h5ad"}))

    asyncio.run(main())
    assert runner.paused_during_run == [1]
    assert (state["entered"], state["exited"], state["depth"]) == (1, 1, 0)


# ---- the tool bounds itself --------------------------------------------------------------------


class _HangingExecutor:
    """Never returns: stands in for a trial whose processes hang past every limit."""

    location = "local"
    python = sys.executable

    async def run(self, argv, *, cwd, env, log, timeout):
        await asyncio.sleep(3600)

    async def capture(self, argv, *, cwd, timeout, env=None):
        return CommandResult(exit_code=0, output='DESCRIBE={"n_obs": 1, "obs_columns": ["batch"]}')


def test_a_hung_trial_is_ended_by_the_tools_own_budget(tmp_path):
    (tmp_path / "in.h5ad").write_bytes(b"x")
    runner = EnsembleRunner(
        catalog=_catalog(),
        pool=ResourcePool(gpu_ids=(), memory_gb=8, cpus=2),
        executor=_HangingExecutor(),
        runs_root=tmp_path / "ensemble_runs",
        repo_root=REPO,
        score_timeout_s=0.1,
    )
    tool = run_skill_tool(runner, Workspace(tmp_path), backstop_margin_s=0.2)
    began = time.monotonic()

    async def bounded():
        arguments = {"skill": "fake-domains", "method": "split", "input": "in.h5ad", "timeout_s": 0.5}
        return await asyncio.wait_for(tool.execute(json.dumps(arguments)), 30)

    body = json.loads(asyncio.run(bounded()))
    assert body["status"] == "timeout"
    assert "budget" in body["error"]
    assert time.monotonic() - began < 10
    record = json.loads((Path(body["output_dir"]) / "trial.json").read_text())
    assert record["status"] == "timeout"


# ---- engine-level parallelism --------------------------------------------------------------------


def _barrier_tool(intervals):
    async def run(command: str) -> str:
        began = time.monotonic()
        await asyncio.sleep(0.2)
        intervals.append((began, time.monotonic()))
        return "done"

    return FunctionTool(
        "bash", "a stand-in barrier", run,
        parameters={"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
        policy=ToolPolicy(approval_mode=ApprovalMode.AUTO, concurrency_safe=False),
    )


def _drive(registry, calls):
    results: list = []

    async def main():
        async for _ in execute_tool_calls(registry, calls, EngineConfig(tool_timeout=30), results):
            pass

    asyncio.run(main())
    return results


def _run_call(index: int) -> ToolCall:
    return ToolCall(id=str(index), name="run_skill", arguments=json.dumps(
        {"skill": "fake-domains", "method": "split", "input": "data/in.h5ad", "params": {"n": 2 + index}}
    ))


def _overlap(a, b) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def test_three_calls_in_one_turn_run_together(workspace):
    runner = _FakeRunner(delay=0.4)
    registry = ToolRegistry()
    registry.register(run_skill_tool(runner, workspace))
    began = time.monotonic()
    results = _drive(registry, [_run_call(i) for i in range(3)])
    assert all(not r.is_error for r in results)
    a, b, c = runner.intervals
    assert _overlap(a, b) and _overlap(b, c) and _overlap(a, c)
    assert time.monotonic() - began < 3 * 0.4


def test_bash_between_two_calls_is_a_barrier(workspace):
    runner = _FakeRunner(delay=0.2)
    bash_intervals: list = []
    registry = ToolRegistry()
    registry.register(run_skill_tool(runner, workspace))
    registry.register(_barrier_tool(bash_intervals))
    calls = [_run_call(0), ToolCall(id="b", name="bash", arguments='{"command": "true"}'), _run_call(1)]
    _drive(registry, calls)
    first, second = runner.intervals
    (bash,) = bash_intervals
    assert first[1] <= bash[0] and bash[1] <= second[0]


def test_the_ceiling_counts_hashing_and_describing_the_input(tmp_path):
    from omicsclaw.ensemble.runner import DESCRIBE_TIMEOUT_S, HASH_TIMEOUT_S

    runner = EnsembleRunner(
        catalog=_catalog(), pool=ResourcePool(gpu_ids=(), memory_gb=8, cpus=2),
        executor=_HangingExecutor(), runs_root=tmp_path / "runs", repo_root=REPO,
    )
    assert runner.call_ceiling_s == HASH_TIMEOUT_S + DESCRIBE_TIMEOUT_S + 7200 + 7200 + 120 + 60 == 15180
    assert "15180 s" in run_skill_tool(runner, Workspace(tmp_path)).definition().description


# ---- the session budget, the fixed-K score and the input check ----------------------------


def test_the_budget_is_taken_per_session_and_method_before_the_run(workspace):
    """A budget checked after the run would let parallel calls overshoot it;
    one call past the cap is refused as an argument error and runs nothing."""
    from omicsclaw.ensemble.tuning.budget import RunBudget
    from omicsclaw.tools.context import use_tool_context

    runner = _FakeRunner(delay=0.0)
    budget = RunBudget({"split": 2})
    tool = run_skill_tool(runner, workspace, budget=budget)

    async def calls(session):
        with use_tool_context(values={"session_id": session}):
            return await asyncio.gather(*(
                tool.execute(json.dumps({"skill": "fake-domains", "method": "split", "input": "data/in.h5ad"}))
                for _ in range(3)
            ), return_exceptions=True)

    outcomes = asyncio.run(calls("s1"))
    refused = [o for o in outcomes if isinstance(o, ToolArgumentError)]
    assert len(refused) == 1 and "budget" in str(refused[0])
    assert len(runner.intervals) == 2
    assert budget.used("s1", "split") == 2
    other = asyncio.run(calls("s2"))
    assert sum(isinstance(o, ToolArgumentError) for o in other) == 1


def test_a_failed_trial_still_counts(workspace):
    from omicsclaw.ensemble.tuning.budget import RunBudget

    budget = RunBudget({"needsgpu": 1})
    tool = run_skill_tool(_FakeRunner(status="failed", delay=0.0), workspace, budget=budget)
    _call(tool, skill="fake-domains", method="needsgpu", input="data/in.h5ad")
    with pytest.raises(ToolArgumentError):
        _call(tool, skill="fake-domains", method="needsgpu", input="data/in.h5ad")


def test_a_refused_argument_costs_nothing(workspace):
    from omicsclaw.ensemble.tuning.budget import RunBudget

    budget = RunBudget({"split": 1})
    tool = run_skill_tool(_FakeRunner(delay=0.0), workspace, budget=budget)
    with pytest.raises(ToolArgumentError):
        _call(tool, skill="fake-domains", method="split", input="data/in.h5ad", params={"n": 99})
    assert budget.used("", "split") == 0


def test_the_input_check_refuses_before_anything_runs(workspace):
    runner = _FakeRunner(delay=0.0)

    async def check(path, skill):
        raise SpecError("the input has no obsm['X_pca']")

    tool = run_skill_tool(runner, workspace, input_check=check)
    with pytest.raises(ToolArgumentError, match="X_pca"):
        _call(tool, skill="fake-domains", method="split", input="data/in.h5ad")
    assert runner.intervals == []


def test_fixed_k_score_is_computed_against_the_reference_of_the_same_k():
    from omicsclaw.ensemble.tool import compact_result

    result = TrialResult(
        status="ok", stage="score", run_id="r", method="m", trial="t1", output_dir="/x", params={},
        metrics={"n_labels": 3, "adjusted": {"pas": 0.75}, "raw": {"silhouette_pca": 0.125},
                 "diagnostics": {"pas": {"se_adjusted": 0.03}, "silhouette_pca": {"se": 0.03}}},
    )
    reference = {"per_k": {"3": {"k": 3, "n_trials": 3, "ranges": {
        "pas": {"lo": 0.6, "hi": 0.9}, "silhouette_pca": {"lo": 0.05, "hi": 0.2}}}}}
    body = compact_result(result, reference)
    assert body["fixed_k_score"] == pytest.approx(0.5)
    other = {"per_k": {"4": reference["per_k"]["3"]}}
    assert compact_result(result, other)["fixed_k_score"] is None
