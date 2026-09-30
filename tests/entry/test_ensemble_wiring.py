"""How ``open_app`` decides whether ``run_skill`` is mounted.

The execution environment is checked before the tool is offered: a model
shown ``run_skill`` in a deployment whose interpreter cannot score a trial
would spend every call on the same import error. What a failed check does
depends on who asked for the ensemble. Left unset, the deployment starts
without the tool and says why in a warning, because most deployments never
asked for it and must not fail to start over it. Explicitly enabled, the
failure refuses start-up, because a benchmark that believes it has
``run_skill`` must not silently run without it.

The fake interpreters are shell scripts: one exits 0 (a passing check), one
prints an import error and exits 1.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import stat
from pathlib import Path

import pytest

from omicsclaw.entry import assembly, open_app
from omicsclaw.entry.config import AppConfig, AppConfigError, SkillsIndex
from omicsclaw.entry.ensemble import SELF_CHECK_IMPORTS, self_check
from omicsclaw.ensemble.execution import CommandResult
from omicsclaw.ensemble.space import TuningCatalog
from omicsclaw.skills import load_skills
from tests.entry.test_ensemble_golden import _Offline

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(assembly, "provider_from_env", lambda provider, model: _Offline())


def _script(directory: Path, body: str) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "python"
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def _config(tmp_path: Path, **overrides) -> AppConfig:
    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)
    values = {"workspace": workspace, "skills_dir": REPO / "skills", "ensemble_gpus": "none",
              "memory": False, **overrides}
    return AppConfig(**values)


def _open(config: AppConfig):
    async def main():
        app = await open_app(config)
        names = [d.name for d in app.tools_snapshot]
        await app.aclose()
        return app, names

    return asyncio.run(asyncio.wait_for(main(), 120))


def test_a_passing_self_check_mounts_run_skill(tmp_path, offline):
    passing = _script(tmp_path / "ok", "exit 0")
    app, names = _open(_config(tmp_path, ensemble_python=passing))
    assert "run_skill" in names
    assert names[-5:] == ["run_skill", "inspect_trials", "select_result", "optimize_params", "task"]
    assert names[-6] == "plan_write"
    assert app.ensemble is not None and app.ensemble.catalog.get("spatial-domains") is not None


def test_a_failing_check_by_default_warns_and_starts_without_run_skill(tmp_path, offline, caplog):
    failing = _script(tmp_path / "bad", "echo \"ModuleNotFoundError: No module named 'igraph'\"; exit 1")
    with caplog.at_level(logging.WARNING, logger="omicsclaw.entry"):
        app, names = _open(_config(tmp_path, ensemble_python=failing))
    assert "run_skill" not in names
    assert {"bash", "use_skill", "task"} <= set(names)
    assert app.ensemble is None
    warning = "\n".join(record.getMessage() for record in caplog.records)
    assert "run_skill is not mounted" in warning and "igraph" in warning
    assert "--ensemble false" in warning


def test_a_failing_check_refuses_start_up_when_explicitly_enabled(tmp_path, offline):
    failing = _script(tmp_path / "bad", "echo 'no scanpy here'; exit 1")
    with pytest.raises(AppConfigError, match="self-check failed.*no scanpy here"):
        _open(_config(tmp_path, ensemble=True, ensemble_python=failing))


def test_ensemble_false_never_runs_the_check(tmp_path, offline):
    marker = tmp_path / "ran"
    probe = _script(tmp_path / "probe", f"touch {marker}; exit 0")
    app, names = _open(_config(tmp_path, ensemble=False, ensemble_python=probe))
    assert "run_skill" not in names and not marker.exists()


def test_skills_index_off_means_no_ensemble(tmp_path, offline):
    passing = _script(tmp_path / "ok", "exit 0")
    app, names = _open(_config(tmp_path, ensemble_python=passing, skills_index=SkillsIndex.OFF))
    assert "run_skill" not in names


def test_a_short_turn_timeout_is_warned_about(tmp_path, offline, caplog):
    passing = _script(tmp_path / "ok", "exit 0")
    with caplog.at_level(logging.WARNING, logger="omicsclaw.entry"):
        _open(_config(tmp_path, ensemble_python=passing, turn_timeout_s=600.0))
    assert any("turn_timeout_s=600" in record.getMessage() for record in caplog.records)


def test_the_self_check_imports_exactly_what_scoring_uses():
    """The list is the scoring path's imports; dropping one (``igraph``, say)
    would let a deployment mount a tool whose every trial fails at scoring."""
    assert SELF_CHECK_IMPORTS == (
        "numpy", "scipy.spatial", "scipy.stats", "pandas", "h5py", "anndata",
        "sklearn.neighbors", "sklearn.metrics", "scanpy", "igraph",
    )


class _Recorder:
    location = "local"
    python = "python3.11"

    def __init__(self, fail_on: str = ""):
        self.fail_on = fail_on
        self.calls: list[list[str]] = []

    async def capture(self, argv, *, cwd, timeout, env=None):
        self.calls.append(list(argv))
        joined = " ".join(argv)
        if self.fail_on and self.fail_on in joined:
            return CommandResult(exit_code=1, output="missing")
        return CommandResult(exit_code=0)


def _catalog():
    return TuningCatalog.from_skills(load_skills(REPO / "skills"))


def test_the_probe_imports_every_listed_module_and_the_scorer(tmp_path):
    recorder = _Recorder()
    assert asyncio.run(self_check(_config(tmp_path), recorder, _catalog())) == ""
    code = recorder.calls[0][2]
    for module in SELF_CHECK_IMPORTS:
        assert module in code
    assert "import omicsclaw.ensemble.metrics.score" in code
    assert "sys.version_info >= (3, 11)" in code
    checked = [call[-1] for call in recorder.calls[1:]]
    assert str(REPO / "omicsclaw" / "ensemble" / "_supervise.py") in checked
    assert str(REPO / "skills" / "spatial" / "spatial-domains" / "spatial_domains.py") in checked


def test_a_missing_supervisor_fails_the_check(tmp_path):
    recorder = _Recorder(fail_on="_supervise.py")
    failure = asyncio.run(self_check(_config(tmp_path), recorder, _catalog()))
    assert "_supervise.py is not visible" in failure
