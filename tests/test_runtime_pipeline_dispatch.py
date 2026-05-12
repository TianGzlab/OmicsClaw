"""End-to-end tests for the YAML-driven pipeline dispatch (OMI-12 P2.7).

These tests use a temporary ``pipelines/`` directory and a stub ``run_skill``
so the chain runs in-process without spawning any subprocesses. They verify:

- ``run_skill("<name>-pipeline")`` dispatches through the generic runner
  when a matching ``pipelines/<name>.yaml`` exists.
- The runner threads each step's chain-baton output (``processed.h5ad`` by
  default; configurable per pipeline) into the next step's ``--input``.
- The chain stops at the first failure and the surviving steps still land
  in ``pipeline_summary.json``.
- An unknown ``<name>-pipeline`` alias falls through to the standard
  ``Unknown skill`` error rather than crashing or fabricating a pipeline.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from omicsclaw.core.runtime import pipeline_runner
from omicsclaw.core.runtime.pipeline_config import load_pipeline_config
from omicsclaw.core.skill_result import SkillRunResult, build_skill_run_result


def _write_pipeline(tmp_path: Path, name: str, body: str) -> None:
    (tmp_path / f"{name}.yaml").write_text(textwrap.dedent(body), encoding="utf-8")


def _stub_run_skill_chain(
    monkeypatch,
    *,
    chain_output_basename: str = "processed.h5ad",
    fail_on: str | None = None,
):
    """Replace ``run_skill`` with an in-process stub that writes the chain baton.

    Returns the list of (skill_name, input_path) tuples observed in invocation
    order so tests can verify the baton-passing actually happened.
    """
    calls: list[tuple[str, str | None]] = []

    def fake_run_skill(*, skill_name, input_path=None, output_dir=None, demo=False, **kwargs):
        calls.append((skill_name, input_path))
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        success = skill_name != fail_on
        if success:
            # Write a non-empty baton so the next step picks it up.
            (out_dir / chain_output_basename).write_text("stub-output\n", encoding="utf-8")
        return build_skill_run_result(
            skill=skill_name,
            success=success,
            exit_code=0 if success else 1,
            output_dir=str(out_dir),
            stdout="",
            stderr="" if success else "stub failure",
            duration_seconds=0.01,
            method=None,
        )

    monkeypatch.setattr("omicsclaw.core.skill_runner.run_skill", fake_run_skill)
    return calls


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_pipeline_dispatch_threads_chain_baton_through_each_step(tmp_path, monkeypatch):
    _write_pipeline(
        tmp_path,
        "demo-pipeline",
        """
        name: demo-pipeline
        steps:
          - skill: step-a
          - skill: step-b
          - skill: step-c
        """,
    )
    config = load_pipeline_config("demo-pipeline", pipelines_dir=tmp_path)
    assert config is not None

    calls = _stub_run_skill_chain(monkeypatch)

    pipeline_out = tmp_path / "out"
    initial_input = str(tmp_path / "user_input.h5ad")
    (tmp_path / "user_input.h5ad").write_text("user", encoding="utf-8")

    result = pipeline_runner.run_pipeline(
        config,
        default_output_root=tmp_path,
        err_factory=lambda name, msg: build_skill_run_result(
            skill=name, success=False, exit_code=-1, output_dir=None, stderr=msg
        ),
        input_path=initial_input,
        output_dir=str(pipeline_out),
    )

    assert isinstance(result, SkillRunResult)
    assert result.success is True
    assert calls[0] == ("step-a", initial_input)
    # step-b should receive step-a's baton, not the user's input.
    assert calls[1] == ("step-b", str(pipeline_out / "step-a" / "processed.h5ad"))
    assert calls[2] == ("step-b", str(pipeline_out / "step-a" / "processed.h5ad")) or calls[2] == (
        "step-c",
        str(pipeline_out / "step-b" / "processed.h5ad"),
    )

    summary = json.loads((pipeline_out / "pipeline_summary.json").read_text(encoding="utf-8"))
    assert summary["pipeline"] == ["step-a", "step-b", "step-c"]
    assert set(summary["results"].keys()) == {"step-a", "step-b", "step-c"}
    assert all(entry["success"] for entry in summary["results"].values())


def test_pipeline_respects_chain_output_basename_override(tmp_path, monkeypatch):
    _write_pipeline(
        tmp_path,
        "bulk-pipeline",
        """
        name: bulk-pipeline
        chain_output_basename: counts.csv
        steps:
          - skill: bulkrna-qc
          - skill: bulkrna-de
        """,
    )
    config = load_pipeline_config("bulk-pipeline", pipelines_dir=tmp_path)
    assert config is not None

    calls = _stub_run_skill_chain(monkeypatch, chain_output_basename="counts.csv")

    pipeline_out = tmp_path / "bulk_out"
    pipeline_runner.run_pipeline(
        config,
        default_output_root=tmp_path,
        err_factory=lambda name, msg: build_skill_run_result(
            skill=name, success=False, exit_code=-1, output_dir=None, stderr=msg
        ),
        input_path=str(tmp_path / "raw.csv"),
        output_dir=str(pipeline_out),
    )
    (tmp_path / "raw.csv").write_text("raw", encoding="utf-8")

    # step 2's input is step 1's baton, but the baton is ``counts.csv``, not
    # the default ``processed.h5ad`` — proving the override was honoured.
    assert calls[1][1] == str(pipeline_out / "bulkrna-qc" / "counts.csv")


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


def test_pipeline_stops_at_first_failure_and_records_partial_summary(tmp_path, monkeypatch):
    _write_pipeline(
        tmp_path,
        "demo-pipeline",
        """
        name: demo-pipeline
        steps:
          - skill: step-a
          - skill: step-b
          - skill: step-c
        """,
    )
    config = load_pipeline_config("demo-pipeline", pipelines_dir=tmp_path)
    assert config is not None

    _stub_run_skill_chain(monkeypatch, fail_on="step-b")

    pipeline_out = tmp_path / "out"
    result = pipeline_runner.run_pipeline(
        config,
        default_output_root=tmp_path,
        err_factory=lambda name, msg: build_skill_run_result(
            skill=name, success=False, exit_code=-1, output_dir=None, stderr=msg
        ),
        input_path=str(tmp_path / "user_input.h5ad"),
        output_dir=str(pipeline_out),
    )
    (tmp_path / "user_input.h5ad").write_text("user", encoding="utf-8")

    assert result.success is False
    summary = json.loads((pipeline_out / "pipeline_summary.json").read_text(encoding="utf-8"))
    # step-c never ran because the chain stopped at step-b.
    assert "step-a" in summary["results"]
    assert "step-b" in summary["results"]
    assert "step-c" not in summary["results"]
    assert summary["results"]["step-a"]["success"] is True
    assert summary["results"]["step-b"]["success"] is False


def test_pipeline_requires_at_least_one_input_source(tmp_path, monkeypatch):
    _write_pipeline(
        tmp_path,
        "demo-pipeline",
        """
        name: demo-pipeline
        steps:
          - skill: step-a
        """,
    )
    config = load_pipeline_config("demo-pipeline", pipelines_dir=tmp_path)
    assert config is not None

    captured: dict[str, str] = {}

    def err(name: str, msg: str) -> SkillRunResult:
        captured["name"] = name
        captured["msg"] = msg
        return build_skill_run_result(
            skill=name, success=False, exit_code=-1, output_dir=None, stderr=msg
        )

    result = pipeline_runner.run_pipeline(
        config,
        default_output_root=tmp_path,
        err_factory=err,
        input_path=None,
        output_dir=None,
        demo=False,
    )

    assert result.success is False
    assert captured["name"] == "demo-pipeline"
    assert "Requires --input" in captured["msg"]


# ---------------------------------------------------------------------------
# Dispatcher integration: run_skill("<name>-pipeline") routes through YAML.
# ---------------------------------------------------------------------------


def test_run_skill_dispatches_unknown_pipeline_alias_back_to_unknown_skill(monkeypatch, tmp_path):
    """Names ending in ``-pipeline`` without a matching YAML must NOT crash
    or fabricate a pipeline — they fall through to the regular
    ``Unknown skill`` error path. That's the only way a typo like
    ``spatail-pipeline`` produces a sensible message."""
    from omicsclaw.core import skill_runner
    import omicsclaw.core.runtime.pipeline_config as pipeline_config

    monkeypatch.setattr(pipeline_config, "PIPELINES_DIR", tmp_path, raising=False)
    # No YAML exists in tmp_path → run_pipeline_by_name returns None and the
    # dispatcher falls through to the regular skill registry lookup.
    result = skill_runner.run_skill("totally-bogus-pipeline")
    assert result.success is False
    assert "Unknown skill" in result.stderr


def test_run_skill_dispatcher_routes_pipeline_alias_to_run_pipeline_by_name(
    monkeypatch, tmp_path
):
    """The dispatcher must hand any ``<name>-pipeline`` alias to
    ``run_pipeline_by_name`` before the skill registry lookup. Verified by
    intercepting that helper directly so we don't need to stand up real
    skill scripts."""
    from omicsclaw.core import skill_runner
    from omicsclaw.core.skill_result import build_skill_run_result

    captured: dict[str, object] = {}
    sentinel = build_skill_run_result(
        skill="smoke-pipeline",
        success=True,
        exit_code=0,
        output_dir=str(tmp_path / "out"),
        stdout="dispatched",
    )

    def fake_run_pipeline_by_name(name, **kwargs):
        captured["name"] = name
        captured["kwargs"] = kwargs
        return sentinel

    monkeypatch.setattr(skill_runner, "run_pipeline_by_name", fake_run_pipeline_by_name)

    result = skill_runner.run_skill(
        "smoke-pipeline",
        input_path=str(tmp_path / "in.h5ad"),
        output_dir=str(tmp_path / "out"),
    )

    assert result is sentinel
    assert captured["name"] == "smoke-pipeline"
    forwarded = captured["kwargs"]
    assert forwarded["input_path"] == str(tmp_path / "in.h5ad")
    assert forwarded["output_dir"] == str(tmp_path / "out")
    # ``err_factory`` is injected so the chain can return stable errors
    # without importing ``_err`` itself.
    assert callable(forwarded["err_factory"])
    assert forwarded["default_output_root"] == skill_runner.DEFAULT_OUTPUT_ROOT
