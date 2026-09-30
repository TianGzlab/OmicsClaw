"""Environment handed to R children by the shared runner (plan 0062 case 7).

``_sdk`` does not filter the environment: credential scrubbing is the
framework's job at its launch boundary (plan 0062 D4, §3.7). The runner's
own base environment, the caller's overrides and the ``R_LIBS_USER`` probe
all carry a sentinel variable set in this process.
"""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

from skills._sdk import r_script_runner as runner_module
from skills._sdk.r_script_runner import R_SCRIPTS_DIR, RScriptRunner
from tests.sdk._scan import REPO_ROOT


def test_r_runner_passes_the_environment_through(monkeypatch, tmp_path):
    monkeypatch.setenv("OMICSCLAW_REMOTE_AUTH_TOKEN", "inherited-as-is")
    monkeypatch.setenv("OMICSCLAW_R_RUNNER_TEST_KEEP", "ordinary-value")
    monkeypatch.delenv("R_LIBS_USER", raising=False)

    rscript = tmp_path / "bin" / "Rscript"
    rscript.parent.mkdir()
    rscript.write_text("", encoding="utf-8")
    script = tmp_path / "analysis.R"
    script.write_text("", encoding="utf-8")
    observed: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(cmd, **kwargs):
        observed.append((list(cmd), kwargs["env"]))
        if "path.expand" in " ".join(str(part) for part in cmd):
            return SimpleNamespace(returncode=0, stdout=str(tmp_path / "r-user-library"), stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(runner_module.subprocess, "run", fake_run)
    runner = RScriptRunner(r_executable=str(rscript), verbose=False)

    built_env = runner._build_r_env()
    assert built_env["OMICSCLAW_R_RUNNER_TEST_KEEP"] == "ordinary-value"
    assert built_env["OMICSCLAW_REMOTE_AUTH_TOKEN"] == "inherited-as-is"

    result = runner.run_script(script, env={"OMICSCLAW_R_CALLER_TEST_KEEP": "caller-value"})

    assert result.success is True
    assert len(observed) >= 3
    for _cmd, child_env in observed:
        assert child_env["OMICSCLAW_R_RUNNER_TEST_KEEP"] == "ordinary-value"
        assert child_env["OMICSCLAW_REMOTE_AUTH_TOKEN"] == "inherited-as-is"
    assert observed[-1][1]["OMICSCLAW_R_CALLER_TEST_KEEP"] == "caller-value"


def test_default_scripts_dir_is_the_sdk_copy():
    assert R_SCRIPTS_DIR == REPO_ROOT / "skills" / "_sdk" / "r_scripts"
    assert RScriptRunner(verbose=False).scripts_dir == R_SCRIPTS_DIR
