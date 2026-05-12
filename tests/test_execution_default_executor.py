"""Contract tests for the default ``SkillRunnerExecutor`` wiring used by /jobs."""

from __future__ import annotations

import sys
from pathlib import Path

from omicsclaw.execution.executors import (
    JobContext,
    SkillRunnerExecutor,
    build_default_executor,
    default_command_factory,
)


def _make_ctx(
    *,
    tmp_path: Path,
    skill: str = "bulkrna-qc",
    inputs: dict | None = None,
    params: dict | None = None,
) -> JobContext:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    artifact_root = tmp_path / "artifacts"
    stdout_log = tmp_path / "stdout.log"
    return JobContext(
        job_id="job-abc",
        workspace=workspace,
        skill=skill,
        inputs=inputs or {},
        params=params or {},
        artifact_root=artifact_root,
        stdout_log=stdout_log,
    )


def test_default_command_factory_invokes_omicsclaw_run(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path=tmp_path, skill="bulkrna-qc")
    argv = default_command_factory(ctx)

    assert argv[0] == sys.executable, "must use current interpreter, not shell PATH"
    # Entry point must be an absolute, existing path.
    entry = Path(argv[1])
    assert entry.is_absolute()
    assert entry.name == "omicsclaw.py"
    assert entry.is_file()
    # Positional args match the CLI contract: `run <skill>`.
    assert argv[2] == "run"
    assert argv[3] == "bulkrna-qc"


def test_default_command_factory_sets_output_to_artifact_root(tmp_path: Path) -> None:
    """Every skill uses ``--output <dir>`` as its standard CLI flag."""
    ctx = _make_ctx(tmp_path=tmp_path)
    argv = default_command_factory(ctx)
    assert "--output" in argv
    output_value = argv[argv.index("--output") + 1]
    assert Path(output_value) == ctx.artifact_root


def test_default_command_factory_passes_demo_flag_when_requested(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path=tmp_path, inputs={"demo": True})
    argv = default_command_factory(ctx)
    assert "--demo" in argv


def test_default_command_factory_passes_input_path_when_provided(tmp_path: Path) -> None:
    data_file = tmp_path / "dataset.h5ad"
    data_file.write_bytes(b"")
    ctx = _make_ctx(tmp_path=tmp_path, inputs={"input": str(data_file)})
    argv = default_command_factory(ctx)
    assert "--input" in argv
    value = argv[argv.index("--input") + 1]
    assert Path(value) == data_file


def test_default_command_factory_prefers_path_key_as_alias_for_input(tmp_path: Path) -> None:
    data_file = tmp_path / "dataset.h5ad"
    data_file.write_bytes(b"")
    ctx = _make_ctx(tmp_path=tmp_path, inputs={"path": str(data_file)})
    argv = default_command_factory(ctx)
    assert "--input" in argv
    assert argv[argv.index("--input") + 1] == str(data_file)


def test_default_command_factory_forwards_params_as_long_flags(tmp_path: Path) -> None:
    ctx = _make_ctx(
        tmp_path=tmp_path,
        inputs={"demo": True},
        params={"method": "harmony", "batch_key": "sample"},
    )
    argv = default_command_factory(ctx)
    # Params become ``--method harmony --batch-key sample`` (snake→kebab).
    assert "--method" in argv
    assert argv[argv.index("--method") + 1] == "harmony"
    assert "--batch-key" in argv
    assert argv[argv.index("--batch-key") + 1] == "sample"


def test_default_command_factory_omits_falsy_boolean_params(tmp_path: Path) -> None:
    """``False`` params must NOT generate a flag; only ``True`` does."""
    ctx = _make_ctx(tmp_path=tmp_path, params={"verbose": True, "dry_run": False})
    argv = default_command_factory(ctx)
    assert "--verbose" in argv
    # Standalone flag: no value follows
    idx = argv.index("--verbose")
    # Next token must be another flag, or end of argv
    assert idx + 1 == len(argv) or argv[idx + 1].startswith("--")
    assert "--dry-run" not in argv


def test_default_command_factory_ignores_none_param_values(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path=tmp_path, params={"method": None, "threshold": 0.5})
    argv = default_command_factory(ctx)
    assert "--method" not in argv
    assert "--threshold" in argv
    assert argv[argv.index("--threshold") + 1] == "0.5"


def test_default_command_factory_serialises_list_and_dict_params(tmp_path: Path) -> None:
    """Non-scalar params (list/dict) must round-trip through ``json.dumps`` —
    pre-fix the helper called ``json.dumps`` without importing ``json`` and
    raised ``NameError`` whenever an LLM forwarded a list-typed argument like
    ``--resolutions [0.4, 0.6, 0.8]``."""
    import json as _json

    ctx = _make_ctx(
        tmp_path=tmp_path,
        params={
            "resolutions": [0.4, 0.6, 0.8],
            "labels": {"control": "ctrl", "treatment": "trt"},
        },
    )
    argv = default_command_factory(ctx)

    assert "--resolutions" in argv
    assert _json.loads(argv[argv.index("--resolutions") + 1]) == [0.4, 0.6, 0.8]
    assert "--labels" in argv
    assert _json.loads(argv[argv.index("--labels") + 1]) == {"control": "ctrl", "treatment": "trt"}


def test_build_default_executor_returns_skill_runner_executor() -> None:
    executor = build_default_executor()
    assert isinstance(executor, SkillRunnerExecutor)


def test_jobs_router_default_executor_is_skill_runner_executor() -> None:
    from omicsclaw.remote.routers import jobs as jobs_module

    assert isinstance(jobs_module._DEFAULT_EXECUTOR, SkillRunnerExecutor)


def test_skill_runner_executor_maps_job_context_to_run_skill(monkeypatch, tmp_path: Path) -> None:
    import asyncio
    import threading

    from omicsclaw.execution.executors import JobOutcome
    from omicsclaw.execution.executors.default import SkillRunnerExecutor

    captured: dict[str, object] = {}

    from omicsclaw.core.skill_result import build_skill_run_result

    def fake_run_skill(skill, **kwargs):
        captured["skill"] = skill
        captured.update(kwargs)
        return build_skill_run_result(
            skill=skill,
            success=True,
            exit_code=0,
            output_dir=str(tmp_path / "artifacts"),
            stdout="runner-ok",
            stderr="",
        )

    monkeypatch.setattr("omicsclaw.core.skill_runner.run_skill", fake_run_skill)

    ctx = _make_ctx(
        tmp_path=tmp_path,
        skill="literature",
        inputs={"demo": True},
        params={"method": "metadata-extraction", "unused": None},
    )
    outcome = asyncio.run(SkillRunnerExecutor().run(ctx))

    assert isinstance(outcome, JobOutcome)
    assert outcome.exit_code == 0
    assert outcome.error is None
    assert "runner-ok" in outcome.stdout_text
    assert ctx.stdout_log.read_text(encoding="utf-8") == "runner-ok"

    cancel_event = captured.pop("cancel_event")
    assert isinstance(cancel_event, threading.Event)
    assert not cancel_event.is_set()
    assert captured == {
        "skill": "literature",
        "input_path": None,
        "input_paths": None,
        "output_dir": str(ctx.artifact_root),
        "demo": True,
        "session_path": None,
        "extra_args": ["--method", "metadata-extraction"],
    }


def test_skill_runner_executor_sets_cancel_event_on_asyncio_cancel(monkeypatch, tmp_path: Path) -> None:
    """If the asyncio task running the executor is cancelled, the executor must
    forward that cancellation to the runner by setting the ``cancel_event`` it
    passed in. Otherwise the ``run_skill`` worker thread (and its subprocess)
    would keep running after the user disconnected."""
    import asyncio
    import threading

    from omicsclaw.execution.executors.default import SkillRunnerExecutor

    captured_events: list[threading.Event] = []

    from omicsclaw.core.skill_result import build_skill_run_result

    def fake_run_skill(skill, **kwargs):
        cancel_event = kwargs["cancel_event"]
        captured_events.append(cancel_event)
        # Block until the executor signals cancellation, with a safety timeout.
        signaled = cancel_event.wait(timeout=10.0)
        return build_skill_run_result(
            skill=skill,
            success=not signaled,
            exit_code=137 if signaled else 0,
            output_dir=str(tmp_path / "artifacts"),
            stdout="",
            stderr="cancelled" if signaled else "",
        )

    monkeypatch.setattr("omicsclaw.core.skill_runner.run_skill", fake_run_skill)

    ctx = _make_ctx(tmp_path=tmp_path, skill="literature", inputs={"demo": True})

    async def driver() -> None:
        task = asyncio.create_task(SkillRunnerExecutor().run(ctx))
        # Give the worker thread time to enter run_skill and capture the event.
        for _ in range(50):
            if captured_events:
                break
            await asyncio.sleep(0.02)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(driver())

    assert captured_events, "fake_run_skill was never invoked"
    assert captured_events[0].is_set(), (
        "cancel_event was not set when the executor's asyncio task was cancelled — "
        "the underlying worker thread / subprocess would leak"
    )


def test_skill_runner_executor_normalizes_failed_zero_exit(monkeypatch, tmp_path: Path) -> None:
    import asyncio

    from omicsclaw.execution.executors.default import SkillRunnerExecutor

    from omicsclaw.core.skill_result import build_skill_run_result

    def fake_run_skill(_skill, **_kwargs):
        return build_skill_run_result(
            skill=_skill,
            success=False,
            exit_code=0,
            output_dir=str(tmp_path / "artifacts"),
            stdout="",
            stderr="missing dependency",
        )

    monkeypatch.setattr("omicsclaw.core.skill_runner.run_skill", fake_run_skill)

    ctx = _make_ctx(tmp_path=tmp_path, skill="literature", inputs={"demo": True})
    outcome = asyncio.run(SkillRunnerExecutor().run(ctx))

    assert outcome.exit_code == 1
    assert outcome.error == "missing dependency"
    assert ctx.stdout_log.read_text(encoding="utf-8") == "missing dependency"
