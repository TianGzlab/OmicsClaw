"""The environment a ``run_skill`` trial records, as the entry layer builds it (plan 0061 P3, cases 25, 25b).

``omicsclaw.ensemble`` may not import ``omicsclaw.skillenv`` (plan 0056 §3.1),
so the entry layer builds the ``describe_environment`` callback and hands it
to ``EnsembleRunner``. It is always injected when the ensemble is mounted: the
switch that leaves it out for frozen benchmark runs belongs to plan 0059
(plan 0061 §4.12, requirement 5 on 0059), which does not exist yet.

The callback runs the same fixed probe as the ``use_skill`` note, as an
argument vector through ``executor.capture`` — never a shell string — starting
with ``executor.python``, in the skill's directory, with the environment the
trial inherits (``env=None``). What it records is names, paths and version
strings only; owner ruling D6 rejected per-trial content hashes, so no value
may look like a sha256 digest.

Also here: the start-up warning compares ``bash``'s ``python`` with the
interpreter the mounted runner actually uses, not only with an explicitly
configured ``ensemble_python``.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

import pytest

from omicsclaw.ensemble.execution import CommandResult
from omicsclaw.ensemble.resources import GpuDetection
from omicsclaw.entry import assembly
from omicsclaw.entry.config import AppConfig
from omicsclaw.entry.ensemble import build_ensemble
from omicsclaw.entry.sandbox import SandboxBinding
from omicsclaw.entry.skill_env import describe_trial_environment

from .conftest import FIXTURE_SKILLS

REPO = Path(__file__).resolve().parents[2]
FAKE_SKILLS = REPO / "tests" / "ensemble" / "fake_skills"
_DIGEST = re.compile(r"\b[0-9a-f]{64}\b")


class _Recording:
    """An executor whose ``capture`` really runs the argv and records how it was called."""

    location = "local"

    def __init__(self, python: str = sys.executable, *, fail: bool = False) -> None:
        self.python = python
        self.fail = fail
        self.calls: list[dict] = []

    async def capture(self, argv, *, cwd, timeout, env=None):
        self.calls.append({"argv": list(argv), "cwd": Path(cwd), "timeout": timeout, "env": env})
        if self.fail:
            return CommandResult(exit_code=127, output="python: not found")
        process = await asyncio.create_subprocess_exec(
            *argv, cwd=str(cwd), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        output, _ = await process.communicate()
        return CommandResult(exit_code=process.returncode or 0, output=output.decode())


def _skills():
    config = AppConfig(workspace=FIXTURE_SKILLS, skills_dir=FIXTURE_SKILLS, ensemble=False)
    return assembly.build_skill_index(config)


def test_the_probe_is_an_argv_starting_with_the_executor_python():
    skills = _skills()
    executor = _Recording()
    described = asyncio.run(describe_trial_environment(skills)(executor, "demo-skill"))
    (call,) = executor.calls
    argv = call["argv"]
    assert argv[0] == executor.python and argv[1:3] == ["-B", "-c"] and len(argv) == 5
    assert not any(arg in ("bash", "sh", "-lc") for arg in argv[:1])
    assert call["cwd"] == skills.get("demo-skill").directory
    assert call["env"] is None
    assert set(described) == {"executable", "version", "prefix", "packages", "missing"}
    assert Path(described["executable"]).resolve() == Path(sys.executable).resolve()


def test_it_records_declared_package_versions_and_what_is_missing():
    described = asyncio.run(describe_trial_environment(_skills())(_Recording(), "demo-skill"))
    # demo-skill declares json, oc-missing-pkg, pybanksy (git) and xcms (an R package, not probed).
    assert set(described["packages"]) == {"json", "oc-missing-pkg", "pybanksy"}
    assert described["packages"]["oc-missing-pkg"] is None
    assert described["missing"] == ["oc-missing-pkg", "pybanksy"]


def test_nothing_recorded_looks_like_a_content_hash():
    described = asyncio.run(describe_trial_environment(_skills())(_Recording(), "demo-skill"))
    assert not _DIGEST.search(json.dumps(described))
    for value in described["packages"].values():
        assert value is None or isinstance(value, str)


def test_a_failing_probe_is_an_error_entry():
    described = asyncio.run(describe_trial_environment(_skills())(_Recording(fail=True), "demo-skill"))
    assert set(described) == {"error"}
    assert "127" in described["error"]


def test_a_skill_without_a_dependencies_section_still_describes_the_interpreter():
    skills = assembly.build_skill_index(AppConfig(workspace=FAKE_SKILLS, skills_dir=FAKE_SKILLS, ensemble=False))
    described = asyncio.run(describe_trial_environment(skills)(_Recording(), "fake-domains"))
    assert described["packages"] == {} and described["missing"] == []
    assert "## Dependencies" in described["declared_error"]
    assert described["executable"]


def _golden_runner(tmp_path: Path):
    config = AppConfig(workspace=tmp_path, skills_dir=FAKE_SKILLS, ensemble=True, ensemble_gpus="none")
    skills = assembly.build_skill_index(config)
    return build_ensemble(config, skills, SandboxBinding(), gpus=GpuDetection((), "none"))


def test_build_ensemble_always_injects_the_callback(tmp_path):
    runner = _golden_runner(tmp_path)
    assert runner is not None and runner.describe_environment is not None


def test_a_real_trial_records_its_interpreter(tmp_path):
    """End to end: the fake skill, the real local executor, the entry-built callback."""
    anndata = pytest.importorskip("anndata")
    import numpy as np

    runner = _golden_runner(tmp_path)
    # The fake skills live under tests/ensemble, so the config's repo root
    # is that directory; the trial needs the real one for the seed and PYTHONPATH.
    runner.repo_root = REPO
    source = tmp_path / "data" / "in.h5ad"
    source.parent.mkdir()
    adata = anndata.AnnData(X=np.zeros((50, 2), dtype=np.float32))
    adata.obs_names = [f"b{i}" for i in range(50)]
    adata.obsm["spatial"] = np.random.default_rng(0).uniform(0, 30, size=(50, 2))
    adata.write_h5ad(source)
    spec = runner.prepare(skill="fake-domains", method="split", input=source, run_id="env1")
    result = asyncio.run(asyncio.wait_for(runner.run(spec), 240))
    record = json.loads((Path(result.output_dir) / "trial.json").read_text())
    environment = record["provenance"]["environment"]
    assert Path(environment["executable"]).resolve() == Path(runner.executor.python).resolve()
    assert environment["version"].count(".") == 2
    assert not _DIGEST.search(json.dumps(environment))


def test_the_startup_warning_compares_the_runner_interpreter(tmp_path, monkeypatch):
    """``_swept`` hands ``log_skill_env`` the python the runner uses, even when none was configured."""
    from tests.entry.test_ensemble_golden import _Offline

    monkeypatch.setattr(assembly, "provider_from_env", lambda provider, model: _Offline())
    config = AppConfig(workspace=tmp_path, skills_dir=FAKE_SKILLS, ensemble=True, ensemble_gpus="none",
                       memory=False)
    runner = build_ensemble(config, assembly.build_skill_index(config), SandboxBinding(),
                            gpus=GpuDetection((), "none"))
    app = assembly.build_app(config, ensemble=runner)
    seen = {}

    async def fake_log(binding, cfg, *, ensemble_python):
        seen["ensemble_python"] = ensemble_python

    monkeypatch.setattr(assembly, "log_skill_env", fake_log)
    asyncio.run(assembly._swept(app))
    assert config.ensemble_python == ""
    assert seen["ensemble_python"] == runner.executor.python == sys.executable
