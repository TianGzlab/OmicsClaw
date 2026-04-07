from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import threading

import pytest


def test_execute_trial_cancellation_terminates_active_process(monkeypatch, tmp_path):
    from omicsclaw.autoagent.errors import OptimizationCancelled
    from omicsclaw.autoagent import runner
    from omicsclaw.autoagent.runner import execute_trial
    from omicsclaw.autoagent.search_space import ParameterDef, SearchSpace

    cancel_event = threading.Event()
    killed_signals: list[int] = []

    class FakeProc:
        def __init__(self, *args, **kwargs):
            self.args = args[0]
            self.pid = 4321
            self.returncode: int | None = None
            self.communicate_calls = 0

        def communicate(self, timeout=None):
            if self.returncode is not None:
                return ("", "")
            self.communicate_calls += 1
            cancel_event.set()
            raise subprocess.TimeoutExpired(self.args, timeout)

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            if self.returncode is None:
                self.returncode = -15
            return self.returncode

        def terminate(self):
            self.returncode = -15

        def kill(self):
            self.returncode = -9

    fake_proc = FakeProc(["python", "omicsclaw.py"])

    monkeypatch.setattr(
        "omicsclaw.autoagent.runner.subprocess.Popen",
        lambda *args, **kwargs: fake_proc,
    )

    if hasattr(runner.os, "killpg"):
        monkeypatch.setattr(
            "omicsclaw.autoagent.runner.os.killpg",
            lambda _pid, sig: killed_signals.append(sig) or setattr(fake_proc, "returncode", -sig),
        )

    search_space = SearchSpace(
        skill_name="test-skill",
        method="method",
        tunable=[
            ParameterDef(
                name="alpha",
                param_type="float",
                default=1.0,
                low=0.1,
                high=5.0,
                cli_flag="--alpha",
            )
        ],
    )

    with pytest.raises(OptimizationCancelled, match="cancelled"):
        execute_trial(
            skill_name="test-skill",
            input_path="",
            output_dir=tmp_path / "trial_0000",
            params={"alpha": 2.0},
            search_space=search_space,
            cancel_event=cancel_event,
        )

    assert fake_proc.communicate_calls >= 1
    if killed_signals:
        assert killed_signals[0] in {15, 9}
    else:
        assert fake_proc.returncode in {-15, -9}


def test_params_to_cli_args_ignores_unknown_params(caplog):
    from omicsclaw.autoagent.runner import _params_to_cli_args
    from omicsclaw.autoagent.search_space import ParameterDef, SearchSpace

    search_space = SearchSpace(
        skill_name="test-skill",
        method="method",
        tunable=[
            ParameterDef(
                name="alpha",
                param_type="float",
                default=1.0,
                low=0.1,
                high=5.0,
                cli_flag="--alpha",
            )
        ],
    )

    with caplog.at_level(logging.WARNING):
        args = _params_to_cli_args(
            {"alpha": 2.0, "hallucinated_knob": 9},
            search_space,
        )

    assert args == ["--alpha", "2.0"]
    assert "Ignoring unknown trial param hallucinated_knob" in caplog.text


def test_build_reproduce_command_quotes_values_and_omits_false_boolean_flags():
    from omicsclaw.autoagent.reproduce import build_reproduce_command

    command = build_reproduce_command(
        skill_name="sc-batch-integration",
        method="harmony",
        input_path="/tmp/demo data/input file.h5ad",
        params={
            "no_gpu": False,
            "refine": True,
            "batch_key": "sample group",
            "reference_cat": ["T cell", "B cell"],
        },
        fixed_params={
            "n_epochs": 10,
            "use_gpu": False,
        },
    )

    assert "--refine" in command
    assert "--no-gpu" not in command
    assert "--use-gpu" not in command
    assert "'/tmp/demo data/input file.h5ad'" in command
    assert "--batch-key 'sample group'" in command
    assert "--reference-cat 'T cell' 'B cell'" in command
    assert "--n-epochs 10" in command


def test_ask_llm_returns_real_error_message(monkeypatch, tmp_path):
    from omicsclaw.autoagent.evaluator import Evaluator
    from omicsclaw.autoagent.metrics_registry import MetricDef
    from omicsclaw.autoagent.optimization_loop import OptimizationLoop
    from omicsclaw.autoagent.search_space import ParameterDef, SearchSpace

    metrics = {
        "score": MetricDef(
            source="result.json:summary.score",
            direction="maximize",
        )
    }
    search_space = SearchSpace(
        skill_name="test-skill",
        method="method",
        tunable=[
            ParameterDef(
                name="alpha",
                param_type="float",
                default=1.0,
                low=0.1,
                high=5.0,
                cli_flag="--alpha",
            )
        ],
    )
    loop = OptimizationLoop(
        skill_name="test-skill",
        method="method",
        input_path="",
        output_root=tmp_path / "optimize-llm-error",
        search_space=search_space,
        evaluator=Evaluator(metrics),
        metrics=metrics,
        max_trials=2,
    )

    def raise_key_error(_directive: str) -> str:
        raise RuntimeError("No LLM API key found")

    monkeypatch.setattr(loop, "_call_llm", raise_key_error)

    suggestion, error = loop._ask_llm("test directive")

    assert suggestion is None
    assert error == "LLM call failed: No LLM API key found"


def test_run_trial_preserves_evaluator_diagnostics(monkeypatch, tmp_path):
    from omicsclaw.autoagent.evaluator import EvaluationResult, Evaluator
    from omicsclaw.autoagent.metrics_registry import MetricDef
    from omicsclaw.autoagent.optimization_loop import OptimizationLoop
    from omicsclaw.autoagent.runner import TrialExecution
    from omicsclaw.autoagent.search_space import ParameterDef, SearchSpace

    metrics = {
        "score": MetricDef(
            source="result.json:summary.score",
            direction="maximize",
        ),
        "batch_asw": MetricDef(
            source="result.json:summary.batch_asw",
            direction="maximize",
        ),
    }
    search_space = SearchSpace(
        skill_name="test-skill",
        method="method",
        tunable=[
            ParameterDef(
                name="alpha",
                param_type="float",
                default=1.0,
                low=0.1,
                high=5.0,
                cli_flag="--alpha",
            )
        ],
    )
    loop = OptimizationLoop(
        skill_name="test-skill",
        method="method",
        input_path="",
        output_root=tmp_path / "optimize-eval-diagnostics",
        search_space=search_space,
        evaluator=Evaluator(metrics),
        metrics=metrics,
        max_trials=2,
    )

    monkeypatch.setattr(
        "omicsclaw.autoagent.optimization_loop.execute_trial",
        lambda **_kwargs: TrialExecution(
            success=True,
            output_dir=str(tmp_path / "trial_0000"),
            duration_seconds=1.25,
        ),
    )
    monkeypatch.setattr(
        loop.evaluator,
        "evaluate",
        lambda *_args, **_kwargs: EvaluationResult(
            composite_score=float("-inf"),
            raw_metrics={},
            success=False,
            missing_metrics=["score", "batch_asw"],
        ),
    )

    trial = loop._run_trial(
        trial_id=0,
        params={"alpha": 1.0},
        description="baseline",
    )

    assert trial.status == "pending"
    assert trial.composite_score == float("-inf")
    assert trial.evaluation_success is False
    assert trial.missing_metrics == ["score", "batch_asw"]


def test_call_llm_reuses_active_provider_runtime(monkeypatch, tmp_path):
    from omicsclaw.autoagent.evaluator import Evaluator
    from omicsclaw.autoagent.metrics_registry import MetricDef
    from omicsclaw.autoagent.optimization_loop import OptimizationLoop
    from omicsclaw.autoagent.search_space import ParameterDef, SearchSpace
    from omicsclaw.core.provider_runtime import (
        clear_active_provider_runtime,
        set_active_provider_runtime,
    )

    metrics = {
        "score": MetricDef(
            source="result.json:summary.score",
            direction="maximize",
        )
    }
    search_space = SearchSpace(
        skill_name="test-skill",
        method="method",
        tunable=[
            ParameterDef(
                name="alpha",
                param_type="float",
                default=1.0,
                low=0.1,
                high=5.0,
                cli_flag="--alpha",
            )
        ],
    )
    loop = OptimizationLoop(
        skill_name="test-skill",
        method="method",
        input_path="",
        output_root=tmp_path / "optimize-active-runtime",
        search_space=search_space,
        evaluator=Evaluator(metrics),
        metrics=metrics,
        max_trials=2,
    )

    captured: dict[str, str | None] = {}

    class FakeOpenAI:
        def __init__(self, *, api_key: str, base_url: str | None = None):
            captured["api_key"] = api_key
            captured["base_url"] = base_url
            self.chat = self
            self.completions = self

        def create(self, **kwargs):
            captured["model"] = kwargs["model"]
            return type(
                "FakeResponse",
                (),
                {
                    "choices": [
                        type(
                            "FakeChoice",
                            (),
                            {
                                "message": type(
                                    "FakeMessage",
                                    (),
                                    {"content": '{"alpha": 2.0}'},
                                )()
                            },
                        )()
                    ]
                },
            )()

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    set_active_provider_runtime(
        provider="deepseek",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        api_key="runtime-secret",
    )

    try:
        response = loop._call_llm("Suggest params")
    finally:
        clear_active_provider_runtime()

    assert response == '{"alpha": 2.0}'
    assert captured == {
        "api_key": "runtime-secret",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    }


def test_run_trial_records_stderr_for_crashed_trials(monkeypatch, tmp_path):
    from omicsclaw.autoagent.evaluator import Evaluator
    from omicsclaw.autoagent.metrics_registry import MetricDef
    from omicsclaw.autoagent.optimization_loop import OptimizationLoop
    from omicsclaw.autoagent.runner import TrialExecution
    from omicsclaw.autoagent.search_space import ParameterDef, SearchSpace

    metrics = {
        "score": MetricDef(
            source="result.json:summary.score",
            direction="maximize",
        )
    }
    search_space = SearchSpace(
        skill_name="test-skill",
        method="method",
        tunable=[
            ParameterDef(
                name="alpha",
                param_type="float",
                default=1.0,
                low=0.1,
                high=5.0,
                cli_flag="--alpha",
            )
        ],
    )
    loop = OptimizationLoop(
        skill_name="test-skill",
        method="method",
        input_path="",
        output_root=tmp_path / "optimize-stderr",
        search_space=search_space,
        evaluator=Evaluator(metrics),
        metrics=metrics,
        max_trials=2,
    )

    monkeypatch.setattr(
        "omicsclaw.autoagent.optimization_loop.execute_trial",
        lambda **kwargs: TrialExecution(
            success=False,
            output_dir=str(tmp_path / "trial_0001"),
            duration_seconds=0.12,
            exit_code=2,
            stdout="stdout text\n",
            stderr="ValueError: bad param\n",
        ),
    )

    trial = loop._run_trial(
        trial_id=1,
        params={"alpha": 9.0},
        description="boom",
    )

    assert trial.status == "crash"
    assert trial.error_output == "ValueError: bad param"


def test_validate_and_clamp_params_parses_bool_strings_rejects_invalid_categories_and_drops_unknown_params(
    tmp_path,
    caplog,
):
    from omicsclaw.autoagent.evaluator import Evaluator
    from omicsclaw.autoagent.metrics_registry import MetricDef
    from omicsclaw.autoagent.optimization_loop import OptimizationLoop
    from omicsclaw.autoagent.search_space import ParameterDef, SearchSpace

    metrics = {
        "score": MetricDef(
            source="result.json:summary.score",
            direction="maximize",
        )
    }
    search_space = SearchSpace(
        skill_name="test-skill",
        method="method",
        tunable=[
            ParameterDef(
                name="use_gpu",
                param_type="bool",
                default=True,
                choices=[True, False],
                cli_flag="--use-gpu",
            ),
            ParameterDef(
                name="mode",
                param_type="categorical",
                default="safe",
                choices=["safe", "fast"],
                cli_flag="--mode",
            ),
        ],
    )
    loop = OptimizationLoop(
        skill_name="test-skill",
        method="method",
        input_path="",
        output_root=tmp_path / "optimize-params",
        search_space=search_space,
        evaluator=Evaluator(metrics),
        metrics=metrics,
        max_trials=2,
    )

    with caplog.at_level(logging.WARNING):
        params = loop._validate_and_clamp_params({
            "use_gpu": "false",
            "mode": "turbo",
            "hallucinated_knob": 123,
        })

    assert params == {"use_gpu": False, "mode": "safe"}
    assert "Discarding unknown LLM-suggested params" in caplog.text
    assert "hallucinated_knob" in caplog.text


def test_optimization_loop_fails_when_llm_suggests_only_unknown_params(monkeypatch, tmp_path):
    from omicsclaw.autoagent.evaluator import Evaluator
    from omicsclaw.autoagent.experiment_ledger import TrialRecord
    from omicsclaw.autoagent.metrics_registry import MetricDef
    from omicsclaw.autoagent.optimization_loop import OptimizationLoop
    from omicsclaw.autoagent.search_space import ParameterDef, SearchSpace

    metrics = {
        "score": MetricDef(
            source="result.json:summary.score",
            direction="maximize",
        )
    }
    search_space = SearchSpace(
        skill_name="test-skill",
        method="method",
        tunable=[
            ParameterDef(
                name="alpha",
                param_type="float",
                default=1.0,
                low=0.1,
                high=5.0,
                cli_flag="--alpha",
            )
        ],
    )
    loop = OptimizationLoop(
        skill_name="test-skill",
        method="method",
        input_path="",
        output_root=tmp_path / "optimize-unknown-only",
        search_space=search_space,
        evaluator=Evaluator(metrics),
        metrics=metrics,
        max_trials=2,
    )

    def fake_run_trial(
        trial_id: int,
        params: dict[str, object],
        description: str = "",
        on_event=None,
    ) -> TrialRecord:
        assert trial_id == 0
        return TrialRecord(
            trial_id=trial_id,
            params=params,
            composite_score=1.0,
            raw_metrics={"score": 1.0},
            status="pending",
            reasoning=description,
        )

    monkeypatch.setattr(loop, "_run_trial", fake_run_trial)
    monkeypatch.setattr(
        loop,
        "_ask_llm",
        lambda directive: {
            "params": {"hallucinated_knob": 9},
            "reasoning": "try a made-up parameter",
        },
    )

    events: list[tuple[str, dict[str, object]]] = []
    result = loop.run(on_event=lambda event_type, data: events.append((event_type, data)))

    assert result.success is False
    assert (
        result.error_message
        == "LLM suggestion contained no valid tunable parameters for test-skill/method. "
        "Allowed params: alpha."
    )
    assert [event_type for event_type, _data in events].count("trial_start") == 0
    assert len(result.ledger.all_trials()) == 1
    assert result.ledger.all_trials()[0].params == {"alpha": 1.0}


@pytest.mark.asyncio
async def test_optimize_runtime_emit_is_safe_from_worker_threads():
    from omicsclaw.autoagent.api import OptimizeSessionRuntime

    loop = asyncio.get_running_loop()
    runtime = OptimizeSessionRuntime(session_id="sess-threadsafe", loop=loop)
    producer_errors: list[Exception] = []

    def producer() -> None:
        try:
            runtime.emit("trial_start", {"trial_id": 1, "params": {"alpha": 2.0}})
            runtime.emit("progress", {"completed": 1, "total": 3})
            runtime.mark_done({"success": True, "best_params": {"alpha": 2.0}})
        except Exception as exc:  # pragma: no cover - defensive assertion aid
            producer_errors.append(exc)

    thread = threading.Thread(target=producer, name="optimize-test-producer")
    thread.start()

    events: list[dict[str, object]] = []
    while True:
        event = await asyncio.wait_for(runtime.queue.get(), timeout=1)
        events.append(event)
        if event["type"] == "_finished":
            break

    thread.join(timeout=1)

    assert producer_errors == []
    assert [event["type"] for event in events] == ["trial_start", "progress", "_finished"]
    assert runtime.snapshot() == ("done", {"success": True, "best_params": {"alpha": 2.0}}, None)


@pytest.mark.asyncio
async def test_optimize_abort_preserves_session_and_reports_cancelled(monkeypatch):
    pytest.importorskip("fastapi")

    import omicsclaw.autoagent as autoagent_pkg
    from fastapi import HTTPException
    from omicsclaw.autoagent import api
    from omicsclaw.autoagent.errors import OptimizationCancelled

    api._sessions.clear()

    started = threading.Event()

    def fake_run_optimization(**kwargs):
        cancel_event = kwargs["cancel_event"]
        started.set()
        while not cancel_event.is_set():
            cancel_event.wait(0.01)
        raise OptimizationCancelled("Optimization cancelled")

    monkeypatch.setattr(autoagent_pkg, "run_optimization", fake_run_optimization)

    response = await api.optimize_start(
        api.OptimizeRequest(
            session_id="sess-cancel",
            skill="sc-batch-integration",
            method="harmony",
        )
    )

    body_iterator = response.body_iterator
    try:
        first_chunk = await anext(body_iterator)
        if isinstance(first_chunk, bytes):
            first_chunk = first_chunk.decode("utf-8")
        assert "sess-cancel" in str(first_chunk)

        assert started.wait(1), "optimization worker did not start"

        running_status = await api.optimize_status("sess-cancel")
        assert running_status.status == "running"

        abort_payload = await api.optimize_abort("sess-cancel")
        assert abort_payload == {"status": "cancelling", "session_id": "sess-cancel"}

        cancelled_status = None
        for _ in range(100):
            candidate = await api.optimize_status("sess-cancel")
            if candidate.status == "cancelled":
                cancelled_status = candidate
                break
            await asyncio.sleep(0.01)

        assert cancelled_status is not None
        assert cancelled_status.status == "cancelled"
        assert cancelled_status.error == "Optimization cancelled"
        assert api._sessions["sess-cancel"].cancel_event.is_set() is True

        with pytest.raises(HTTPException) as excinfo:
            await api.optimize_results("sess-cancel")
        assert excinfo.value.status_code == 409
    finally:
        await body_iterator.aclose()
        api._sessions.clear()


@pytest.mark.asyncio
async def test_optimize_status_and_results_reap_expired_sessions(monkeypatch):
    pytest.importorskip("fastapi")

    from fastapi import HTTPException
    from omicsclaw.autoagent import api

    loop = asyncio.get_running_loop()
    api._sessions.clear()

    runtime = api.OptimizeSessionRuntime(session_id="sess-expired", loop=loop)
    runtime.status = "done"
    runtime.result = {"success": True}
    runtime.finished_at = 1.0
    api._sessions["sess-expired"] = runtime

    monkeypatch.setattr(
        api.time,
        "monotonic",
        lambda: 1.0 + api._SESSION_TTL_SECONDS + 10,
    )

    try:
        status = await api.optimize_status("sess-expired")
        assert status.status == "not_found"
        assert "sess-expired" not in api._sessions

        with pytest.raises(HTTPException) as excinfo:
            await api.optimize_results("sess-expired")
        assert excinfo.value.status_code == 404
    finally:
        api._sessions.clear()


@pytest.mark.asyncio
async def test_optimize_start_streams_worker_thread_events(monkeypatch):
    pytest.importorskip("fastapi")

    import omicsclaw.autoagent as autoagent_pkg
    from omicsclaw.autoagent import api

    api._sessions.clear()
    captured: dict[str, object] = {}

    def fake_run_optimization(**kwargs):
        captured.update(kwargs)
        on_event = kwargs["on_event"]
        on_event("trial_start", {"trial_id": 0, "params": {"alpha": 1.0}})
        on_event("progress", {"completed": 1, "total": 2, "best_score": 0.75})
        on_event("done", {
            "best_trial": {"trial_id": 0, "params": {"alpha": 1.0}},
            "improvement_pct": 12.5,
            "total_trials": 2,
            "converged": False,
        })
        return {
            "success": True,
            "best_params": {"alpha": 1.0},
            "best_score": 0.75,
            "output_dir": "output/test-session",
        }

    monkeypatch.setattr(autoagent_pkg, "run_optimization", fake_run_optimization)

    response = await api.optimize_start(
        api.OptimizeRequest(
            session_id="sess-stream",
            skill="sc-batch-integration",
            method="harmony",
            cwd="/tmp/project-alpha",
            output_dir="/tmp/project-alpha/output/optimize_sc-batch-integration_harmony_custom",
            provider_id="deepseek",
            llm_model="deepseek-chat",
        )
    )

    body_iterator = response.body_iterator
    chunks: list[str] = []
    try:
        async for chunk in body_iterator:
            if isinstance(chunk, bytes):
                chunk = chunk.decode("utf-8")
            chunks.append(str(chunk))
            if "event: done" in str(chunk):
                break

        event_types: list[str] = []
        event_payloads: dict[str, dict[str, object]] = {}
        for raw_chunk in chunks:
            event_type: str | None = None
            data_line: str | None = None
            for line in raw_chunk.splitlines():
                if line.startswith("event: "):
                    event_type = line[7:].strip()
                elif line.startswith("data: "):
                    data_line = line[6:]
            if not event_type or data_line is None:
                continue
            payload = json.loads(data_line) if data_line else {}
            event_types.append(event_type)
            if isinstance(payload, dict):
                event_payloads[event_type] = payload

        assert event_types == ["status", "trial_start", "progress", "done"]
        assert event_payloads["trial_start"]["trial_id"] == 0
        assert event_payloads["progress"]["best_score"] == 0.75
        assert event_payloads["done"]["improvement_pct"] == 12.5
        assert captured["cwd"] == "/tmp/project-alpha"
        assert captured["output_dir"] == "/tmp/project-alpha/output/optimize_sc-batch-integration_harmony_custom"
        assert captured["llm_provider"] == "deepseek"
        assert captured["llm_model"] == "deepseek-chat"

        final_status = None
        for _ in range(100):
            candidate = await api.optimize_status("sess-stream")
            if candidate.status == "done":
                final_status = candidate
                break
            await asyncio.sleep(0.01)

        assert final_status is not None
        assert final_status.result is not None
        assert final_status.result["best_params"] == {"alpha": 1.0}
    finally:
        await body_iterator.aclose()
        api._sessions.clear()


def test_optimization_loop_reports_llm_failure_without_done(monkeypatch, tmp_path):
    from omicsclaw.autoagent.evaluator import Evaluator
    from omicsclaw.autoagent.experiment_ledger import TrialRecord
    from omicsclaw.autoagent.metrics_registry import MetricDef
    from omicsclaw.autoagent.optimization_loop import OptimizationLoop
    from omicsclaw.autoagent.search_space import ParameterDef, SearchSpace

    metrics = {
        "score": MetricDef(
            source="result.json:summary.score",
            direction="maximize",
        )
    }
    search_space = SearchSpace(
        skill_name="test-skill",
        method="method",
        tunable=[
            ParameterDef(
                name="alpha",
                param_type="float",
                default=1.0,
                low=0.1,
                high=5.0,
                cli_flag="--alpha",
            )
        ],
    )
    loop = OptimizationLoop(
        skill_name="test-skill",
        method="method",
        input_path="",
        output_root=tmp_path / "optimize-no-suggestion",
        search_space=search_space,
        evaluator=Evaluator(metrics),
        metrics=metrics,
        max_trials=4,
    )

    def fake_run_trial(
        trial_id: int,
        params: dict[str, object],
        description: str = "",
        on_event=None,
    ) -> TrialRecord:
        assert trial_id == 0
        return TrialRecord(
            trial_id=trial_id,
            params=params,
            composite_score=1.0,
            raw_metrics={"score": 1.0},
            status="pending",
            reasoning=description,
        )

    monkeypatch.setattr(loop, "_run_trial", fake_run_trial)
    monkeypatch.setattr(loop, "_ask_llm", lambda directive: None)

    event_types: list[str] = []
    result = loop.run(on_event=lambda event_type, _data: event_types.append(event_type))

    assert result.success is False
    assert result.error_message == "LLM returned no suggestion"
    assert result.total_trials == 1
    assert "done" not in event_types


def test_optimization_loop_emits_missing_metrics_in_trial_complete_and_done(monkeypatch, tmp_path):
    from omicsclaw.autoagent.evaluator import Evaluator
    from omicsclaw.autoagent.experiment_ledger import TrialRecord
    from omicsclaw.autoagent.metrics_registry import MetricDef
    from omicsclaw.autoagent.optimization_loop import OptimizationLoop
    from omicsclaw.autoagent.search_space import ParameterDef, SearchSpace

    metrics = {
        "score": MetricDef(
            source="result.json:summary.score",
            direction="maximize",
        )
    }
    search_space = SearchSpace(
        skill_name="test-skill",
        method="method",
        tunable=[
            ParameterDef(
                name="alpha",
                param_type="float",
                default=1.0,
                low=0.1,
                high=5.0,
                cli_flag="--alpha",
            )
        ],
    )
    loop = OptimizationLoop(
        skill_name="test-skill",
        method="method",
        input_path="",
        output_root=tmp_path / "optimize-missing-metrics-events",
        search_space=search_space,
        evaluator=Evaluator(metrics),
        metrics=metrics,
        max_trials=1,
    )

    def fake_run_trial(
        trial_id: int,
        params: dict[str, object],
        description: str = "",
        on_event=None,
    ) -> TrialRecord:
        assert trial_id == 0
        return TrialRecord(
            trial_id=trial_id,
            params=params,
            composite_score=float("-inf"),
            raw_metrics={},
            status="pending",
            reasoning=description,
            evaluation_success=False,
            missing_metrics=["score"],
        )

    monkeypatch.setattr(loop, "_run_trial", fake_run_trial)

    events: list[tuple[str, dict[str, object]]] = []
    result = loop.run(on_event=lambda event_type, data: events.append((event_type, data)))

    # A baseline with -inf score means metrics extraction failed entirely.
    # The loop now stops immediately with success=False rather than
    # continuing with meaningless comparisons.
    assert result.success is False
    assert "non-finite baseline" in (result.error_message or "")

    trial_complete_payload = next(
        data for event_type, data in events if event_type == "trial_complete"
    )
    assert trial_complete_payload["evaluation_success"] is False
    assert trial_complete_payload["missing_metrics"] == ["score"]

    # An error event is emitted instead of a done event.
    error_payload = next(data for event_type, data in events if event_type == "error")
    assert "non-finite baseline" in error_payload["message"]


def test_optimization_loop_stops_after_three_consecutive_crashes_without_done(monkeypatch, tmp_path):
    from omicsclaw.autoagent.evaluator import Evaluator
    from omicsclaw.autoagent.experiment_ledger import TrialRecord
    from omicsclaw.autoagent.metrics_registry import MetricDef
    from omicsclaw.autoagent.optimization_loop import OptimizationLoop
    from omicsclaw.autoagent.search_space import ParameterDef, SearchSpace

    metrics = {
        "score": MetricDef(
            source="result.json:summary.score",
            direction="maximize",
        )
    }
    search_space = SearchSpace(
        skill_name="test-skill",
        method="method",
        tunable=[
            ParameterDef(
                name="alpha",
                param_type="float",
                default=1.0,
                low=0.1,
                high=5.0,
                cli_flag="--alpha",
            )
        ],
    )
    loop = OptimizationLoop(
        skill_name="test-skill",
        method="method",
        input_path="",
        output_root=tmp_path / "optimize-crashes",
        search_space=search_space,
        evaluator=Evaluator(metrics),
        metrics=metrics,
        max_trials=5,
    )

    suggestions = iter([
        {"params": {"alpha": 1.1}, "reasoning": "first crash"},
        {"params": {"alpha": 1.2}, "reasoning": "second crash"},
        {"params": {"alpha": 1.3}, "reasoning": "third crash"},
    ])

    def fake_run_trial(
        trial_id: int,
        params: dict[str, object],
        description: str = "",
        on_event=None,
    ) -> TrialRecord:
        if trial_id == 0:
            return TrialRecord(
                trial_id=trial_id,
                params=params,
                composite_score=1.0,
                raw_metrics={"score": 1.0},
                status="pending",
                reasoning="baseline",
            )
        return TrialRecord(
            trial_id=trial_id,
            params=params,
            composite_score=float("-inf"),
            raw_metrics={},
            status="crash",
            reasoning=description,
        )

    monkeypatch.setattr(loop, "_run_trial", fake_run_trial)
    monkeypatch.setattr(loop, "_ask_llm", lambda directive: next(suggestions))

    events: list[tuple[str, dict[str, object]]] = []
    result = loop.run(on_event=lambda event_type, data: events.append((event_type, data)))

    assert result.success is False
    assert result.error_message == "3 consecutive crashes — stopping."
    assert result.total_trials == 4
    assert [event_type for event_type, _data in events].count("done") == 0
    crash_statuses = [
        str(data["status"])
        for event_type, data in events
        if event_type == "trial_complete" and int(data["trial_id"]) > 0
    ]
    assert crash_statuses == ["crash", "crash", "crash"]


def test_optimization_loop_progress_tracks_completed_trials(monkeypatch, tmp_path):
    from omicsclaw.autoagent.evaluator import Evaluator
    from omicsclaw.autoagent.experiment_ledger import TrialRecord
    from omicsclaw.autoagent.metrics_registry import MetricDef
    from omicsclaw.autoagent.optimization_loop import OptimizationLoop
    from omicsclaw.autoagent.search_space import ParameterDef, SearchSpace

    metrics = {
        "score": MetricDef(
            source="result.json:summary.score",
            direction="maximize",
        )
    }
    search_space = SearchSpace(
        skill_name="test-skill",
        method="method",
        tunable=[
            ParameterDef(
                name="alpha",
                param_type="float",
                default=1.0,
                low=0.1,
                high=5.0,
                cli_flag="--alpha",
            )
        ],
    )
    loop = OptimizationLoop(
        skill_name="test-skill",
        method="method",
        input_path="",
        output_root=tmp_path / "optimize-progress",
        search_space=search_space,
        evaluator=Evaluator(metrics),
        metrics=metrics,
        max_trials=3,
    )

    suggestions = iter([
        {"params": {"alpha": 2.0}, "reasoning": "increase alpha"},
        {"params": {"alpha": 0.5}, "reasoning": "try a smaller alpha"},
    ])

    def fake_run_trial(
        trial_id: int,
        params: dict[str, object],
        description: str = "",
        on_event=None,
    ) -> TrialRecord:
        scores = {
            0: 1.0,
            1: 2.0,
            2: 1.5,
        }
        return TrialRecord(
            trial_id=trial_id,
            params=params,
            composite_score=scores[trial_id],
            raw_metrics={"score": scores[trial_id]},
            status="pending",
            reasoning=description,
        )

    monkeypatch.setattr(loop, "_run_trial", fake_run_trial)
    monkeypatch.setattr(loop, "_ask_llm", lambda directive: next(suggestions))

    events: list[tuple[str, dict[str, object]]] = []
    result = loop.run(on_event=lambda event_type, data: events.append((event_type, data)))

    progress_events = [
        data
        for event_type, data in events
        if event_type == "progress"
    ]
    assert result.success is True
    assert [int(data["completed"]) for data in progress_events] == [0, 1, 2, 3]
    assert [int(data["total"]) for data in progress_events] == [3, 3, 3, 3]
    assert [float(data.get("best_score", 0.0)) for data in progress_events[1:]] == [1.0, 2.0, 2.0]
    assert [event_type for event_type, _data in events].count("done") == 1


def test_optimization_loop_emits_terminal_progress_when_converged_early(monkeypatch, tmp_path):
    from omicsclaw.autoagent.evaluator import Evaluator
    from omicsclaw.autoagent.experiment_ledger import TrialRecord
    from omicsclaw.autoagent.metrics_registry import MetricDef
    from omicsclaw.autoagent.optimization_loop import OptimizationLoop
    from omicsclaw.autoagent.search_space import ParameterDef, SearchSpace

    metrics = {
        "score": MetricDef(
            source="result.json:summary.score",
            direction="maximize",
        )
    }
    search_space = SearchSpace(
        skill_name="test-skill",
        method="method",
        tunable=[
            ParameterDef(
                name="alpha",
                param_type="float",
                default=1.0,
                low=0.1,
                high=5.0,
                cli_flag="--alpha",
            )
        ],
    )
    loop = OptimizationLoop(
        skill_name="test-skill",
        method="method",
        input_path="",
        output_root=tmp_path / "optimize-converged",
        search_space=search_space,
        evaluator=Evaluator(metrics),
        metrics=metrics,
        max_trials=4,
    )

    def fake_run_trial(
        trial_id: int,
        params: dict[str, object],
        description: str = "",
        on_event=None,
    ) -> TrialRecord:
        assert trial_id == 0
        return TrialRecord(
            trial_id=trial_id,
            params=params,
            composite_score=1.0,
            raw_metrics={"score": 1.0},
            status="pending",
            reasoning=description,
        )

    monkeypatch.setattr(loop, "_run_trial", fake_run_trial)
    monkeypatch.setattr(
        loop,
        "_ask_llm",
        lambda directive: {"converged": True, "reasoning": "baseline is already optimal"},
    )

    events: list[tuple[str, dict[str, object]]] = []
    result = loop.run(on_event=lambda event_type, data: events.append((event_type, data)))

    progress_events = [
        data
        for event_type, data in events
        if event_type == "progress"
    ]
    done_events = [data for event_type, data in events if event_type == "done"]

    assert result.success is True
    assert result.converged is True
    assert [
        (str(data["phase"]), int(data["completed"]), int(data["total"]))
        for data in progress_events
    ] == [
        ("baseline", 0, 4),
        ("baseline", 1, 4),
        ("complete", 1, 1),
    ]
    assert len(done_events) == 1
    assert int(done_events[0]["total_trials"]) == 1


def test_run_optimization_returns_failure_summary_when_loop_fails(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import omicsclaw.autoagent as autoagent_pkg
    from omicsclaw.autoagent.experiment_ledger import ExperimentLedger, TrialRecord
    from omicsclaw.autoagent.metrics_registry import MetricDef
    from omicsclaw.autoagent.optimization_loop import OptimizationResult

    monkeypatch.setattr(
        "omicsclaw.autoagent.metrics_registry.get_metrics_for_skill",
        lambda *_args, **_kwargs: {
            "score": MetricDef(
                source="result.json:summary.score",
                direction="maximize",
            )
        },
    )

    fake_registry = SimpleNamespace(
        load_all=lambda: None,
        skills={
            "test-skill": {
                "param_hints": {
                    "method": {
                        "params": ["alpha"],
                        "defaults": {"alpha": 1.0},
                    }
                }
            }
        },
    )
    monkeypatch.setattr("omicsclaw.core.registry.registry", fake_registry)

    class FakeLoop:
        def __init__(self, *args, **kwargs):
            self.output_root = kwargs["output_root"]

        def run(self, on_event=None):
            ledger = ExperimentLedger(self.output_root / "experiment_ledger.jsonl")
            best_trial = TrialRecord(
                trial_id=0,
                params={"alpha": 1.0},
                composite_score=1.0,
                raw_metrics={"score": 1.0},
                status="baseline",
            )
            ledger.append(best_trial)
            # Real _finalize_result emits error event on failure;
            # simulate that here so the mock matches real behavior.
            if on_event:
                on_event("error", {"message": "LLM returned no suggestion"})
            return OptimizationResult(
                best_trial=best_trial,
                ledger=ledger,
                improvement_pct=0.0,
                total_trials=1,
                converged=False,
                success=False,
                error_message="LLM returned no suggestion",
            )

    monkeypatch.setattr("omicsclaw.autoagent.optimization_loop.OptimizationLoop", FakeLoop)

    events: list[tuple[str, dict[str, object]]] = []
    result = autoagent_pkg.run_optimization(
        skill_name="test-skill",
        method="method",
        cwd=str(tmp_path),
        on_event=lambda event_type, data: events.append((event_type, data)),
    )

    assert result["success"] is False
    assert result["error"] == "LLM returned no suggestion"
    assert result["output_dir"].startswith(str(tmp_path))
    assert result["best_params"] == {"alpha": 1.0}
    assert result["best_trial"]["params"] == {"alpha": 1.0}
    assert [event_type for event_type, _data in events] == ["error"]


@pytest.mark.asyncio
async def test_optimize_start_keeps_single_error_terminal_when_worker_returns_failure(monkeypatch):
    pytest.importorskip("fastapi")

    import omicsclaw.autoagent as autoagent_pkg
    from omicsclaw.autoagent import api

    api._sessions.clear()

    def fake_run_optimization(**kwargs):
        on_event = kwargs["on_event"]
        on_event("progress", {"completed": 1, "total": 3})
        on_event("error", {"message": "LLM returned no suggestion"})
        return {
            "success": False,
            "error": "LLM returned no suggestion",
        }

    monkeypatch.setattr(autoagent_pkg, "run_optimization", fake_run_optimization)

    response = await api.optimize_start(
        api.OptimizeRequest(
            session_id="sess-terminal-error",
            skill="sc-batch-integration",
            method="harmony",
        )
    )

    body_iterator = response.body_iterator
    chunks: list[str] = []
    try:
        async for chunk in body_iterator:
            if isinstance(chunk, bytes):
                chunk = chunk.decode("utf-8")
            chunks.append(str(chunk))
            if "event: error" in str(chunk):
                break

        event_types: list[str] = []
        for raw_chunk in chunks:
            current_type: str | None = None
            for line in raw_chunk.splitlines():
                if line.startswith("event: "):
                    current_type = line[7:].strip()
            if current_type:
                event_types.append(current_type)

        assert event_types == ["status", "progress", "error"]

        final_status = None
        for _ in range(100):
            candidate = await api.optimize_status("sess-terminal-error")
            if candidate.status == "error":
                final_status = candidate
                break
            await asyncio.sleep(0.01)

        assert final_status is not None
        assert final_status.error == "LLM returned no suggestion"
    finally:
        await body_iterator.aclose()
        api._sessions.clear()
