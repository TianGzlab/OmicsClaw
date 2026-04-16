"""Contract tests for the default ``SubprocessExecutor`` wiring used by /jobs."""

from __future__ import annotations

import sys
from pathlib import Path

from omicsclaw.execution.executors import (
    JobContext,
    SubprocessExecutor,
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


def test_build_default_executor_returns_subprocess_executor() -> None:
    executor = build_default_executor()
    assert isinstance(executor, SubprocessExecutor)


def test_jobs_router_default_executor_is_subprocess_executor() -> None:
    from omicsclaw.remote.routers import jobs as jobs_module

    assert isinstance(jobs_module._DEFAULT_EXECUTOR, SubprocessExecutor)
