"""R steps execute without an interactive kernel or extra R packages."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from skills._sdk.notebook import _runners
from skills._sdk.notebook._percent import to_notebook
from skills._sdk.r_script_runner import _preferred_rscript_executable


@pytest.fixture
def rscript():
    executable = shutil.which(_preferred_rscript_executable())
    if not executable:
        pytest.skip("Rscript is not installed")
    return executable


@pytest.mark.requires_r
def test_r_cells_share_state_and_keep_failure_in_its_cell(tmp_path, rscript):
    notebook = to_notebook(
        '# %% [markdown]\n# R example\n# %%\nx <- 7\nx\nmessage("hello")\nplot(1:3)\n'
        '# %%\nstop(paste("bad", x))\n# %%\nwriteLines("never", "after.txt")\n',
        step={"file": "01_r.R"}, language="r",
    )
    outcome = _runners.RscriptRunner(rscript).run(notebook, env=dict(os.environ), cwd=tmp_path)
    assert outcome.status == "failed"
    assert outcome.error["cell"] == 3
    assert outcome.error["evalue"] == "bad 7"
    assert "[1] 7" in notebook.cells[1].outputs[0].text
    assert "hello" in notebook.cells[1].outputs[0].text
    assert notebook.cells[2].outputs[-1].output_type == "error"
    assert notebook.cells[3].outputs == []
    assert not (tmp_path / "after.txt").exists()
    assert not (tmp_path / "Rplots.pdf").exists()
    assert outcome.r_session["r_version"].startswith("R version")
    assert "base" in outcome.r_session["packages"]


@pytest.mark.requires_r
def test_r_step_reads_and_writes_with_provenance_and_stales_on_input_change(project, rscript):
    import json

    import nbformat

    from skills._sdk.notebook import _executor, _hashing, _ledger

    module = project.new("mixed")
    data = project.root / "data" / "counts.csv"
    data.write_text("gene,count\nA,3\nB,5\n")
    project.step(module, "01_sum.R", '''
        # %% [markdown]
        # Sum counts with base R.
        # %%
        source(file.path(Sys.getenv("OMICSCLAW_SDK_DIR"), "notebook", "step.R"))
        counts <- read_input("data/counts.csv")
        write_output(data.frame(total = sum(counts$count)), "tables/total.csv")
    ''')
    code = _executor.run_targets(project.root, [module], out=project.out)
    assert code == 0, project.text
    result = project.root / "results" / module
    assert (result / "tables/total.csv").read_text().splitlines() == ['"total"', "8"]
    record = _ledger.read_run(next((result / "provenance/runs/01_sum").glob("*.jsonl")))
    assert record.start["kind"] == "r"
    assert record.inputs[0]["path"] == "data/counts.csv"
    assert record.inputs[0]["sha256"] == _hashing.sha256_file(data)
    assert record.inputs[0]["outside_contract"] is False
    assert record.outputs[0]["path"] == "tables/total.csv"
    assert record.r_sessions[0]["packages"]["base"]
    assert record.end["status"] == "ok"
    manifest = json.loads((result / "provenance/manifest.json").read_text())
    assert manifest["steps"][0]["kind"] == "r"
    assert manifest["rscript"]["path"] == rscript
    combined = nbformat.read(result / "notebooks/M01_mixed.ipynb", as_version=4)
    assert all(cell.cell_type == "markdown" for cell in combined.cells)
    assert any("```r" in cell.source for cell in combined.cells)
    data.write_text("gene,count\nA,4\nB,5\n")
    assert "input changed" in project.status(module)


@pytest.mark.requires_r
def test_mixed_replay_validates_r_outputs_and_warns_on_an_rscript_change(project, rscript):
    import json

    from skills._sdk.notebook import _executor

    module = project.new("mixed")
    project.step(module, "01_r.R", '''
        # %% [markdown]
        # Generate a table in base R to check the IO path.
        # %%
        source(file.path(Sys.getenv("OMICSCLAW_SDK_DIR"), "notebook", "step.R"))
        write_output(data.frame(a = 2), "tables/r.csv")
    ''')
    project.step(module, "02_validate.py", '''
        # %%
        from skills._sdk.notebook import read_input
        from skills._sdk.notebook.checks import check_files
        check_files("tables/r.csv")
        assert read_input("results/01_mixed/tables/r.csv").iloc[0, 0] == 2
    ''')
    kwargs = {"runner": project.runner, "out": project.out}
    assert _executor.replay(project.root, module, **kwargs) == 0, project.text
    result = project.root / "results" / module
    brief = (result / "provenance/review_brief.md").read_text()
    assert "none (R step)" in brief and "R step: Rscript" in brief
    assert "packages: " in brief and "base=" in brief
    path = result / "provenance/manifest.json"
    for command in ("run", "replay"):
        manifest = json.loads(path.read_text())
        manifest["rscript"]["path"] = "/previous/Rscript"
        path.write_text(json.dumps(manifest))
        project.lines.clear()
        code = (_executor.run_targets(project.root, [module], force=True, **kwargs) if command == "run"
                else _executor.replay(project.root, module, **kwargs))
        assert code == 0, project.text
        assert "Rscript changed" in project.lines[0]
    assert "Rscript changed" in project.lines[-1]


@pytest.mark.requires_r
def test_standalone_r_io_is_atomic_and_ignores_user_profile(project, rscript, tmp_path):
    module = project.new("standalone")
    (project.root / "data" / "in.csv").write_text("a\n4\n")
    sdk = Path(_runners.__file__).resolve().parents[1]
    profile = tmp_path / "profile.R"
    profile.write_text('stop("user profile ran")\n')
    step = project.step(module, "01_io.R", '''
        source(file.path(Sys.getenv("OMICSCLAW_SDK_DIR"), "notebook", "step.R"))
        frame <- read_input("data/in.csv")
        write_output(frame, "tables/out.csv")
        write_output(frame, "intermediate/out.rds")
        restored <- read_input("results/01_standalone/intermediate/out.rds")
        stopifnot(identical(frame, restored))
        write_output(function() plot(1:3), "figures/test.png")
        tryCatch(write_output("bad", "tables/out.csv", writer = function(obj, path) {
            writeLines(obj, path)
            stop("writer failed")
        }), error = function(e) NULL)
    ''')
    env = {key: value for key, value in os.environ.items() if not key.startswith("OMICSCLAW_STEP_")}
    env.update(OMICSCLAW_SDK_DIR=str(sdk), R_PROFILE_USER=str(profile))
    process = subprocess.run([rscript, "--no-init-file", str(step)], cwd=project.root, env=env,
                             capture_output=True, text=True, timeout=30)
    assert process.returncode == 0, process.stdout + process.stderr
    result = project.root / "results" / module
    assert (result / "tables/out.csv").read_text() == '"a"\n4\n'
    assert (result / "figures/test.png").read_bytes().startswith(b"\x89PNG")
    assert not list(result.rglob(".tmp-*"))
    assert process.stderr.count("not running under the step runner") == 1


@pytest.mark.requires_r
@pytest.mark.parametrize("operation,message", [
    ('write_output("bad", "../outside.txt")', "inside figures/"),
    ('write_output("bad", "/tmp/outside.txt")', "inside figures/"),
    ('write_output("bad", "provenance/data.txt")', "inside figures/"),
    ('read_input("data/a.h5ad")', "Matrix Market plus CSV"),
    ('write_output(list(a = 1), "tables/unknown.csv")', "supply writer"),
])
def test_r_io_rejects_invalid_paths_and_unsupported_formats(project, rscript, operation, message):
    from skills._sdk.notebook import _executor

    module = project.new("io")
    (project.root / "data" / "a.h5ad").write_text("not a real h5ad")
    project.step(module, "01_bad.R", 'source(file.path(Sys.getenv("OMICSCLAW_SDK_DIR"), "notebook", "step.R"))\n' + operation)
    assert _executor.run_targets(project.root, [module], out=project.out) == 1
    assert message in project.text


@pytest.mark.requires_r
def test_standalone_r_cannot_write_to_a_frozen_module(project, rscript):
    module = project.new("frozen")
    result = project.root / "results" / module
    (result / "provenance/manifest.json").write_text('{"frozen": true}')
    step = project.step(module, "01_write.R", '''
        source(file.path(Sys.getenv("OMICSCLAW_SDK_DIR"), "notebook", "step.R"))
        write_output("bad", "tables/new.txt")
    ''')
    env = {**os.environ, "OMICSCLAW_SDK_DIR": str(Path(_runners.__file__).resolve().parents[1])}
    process = subprocess.run([rscript, "--no-init-file", str(step)], cwd=project.root, env=env,
                             capture_output=True, text=True, timeout=30)
    assert process.returncode == 1
    assert "accepted and frozen" in process.stderr
    assert not (result / "tables/new.txt").exists()


@pytest.mark.requires_r
def test_r_runner_skips_user_profile_and_records_outside_inputs(project, rscript, tmp_path, monkeypatch):
    from skills._sdk.notebook import _executor, _ledger

    profile = tmp_path / "profile.R"
    profile.write_text('stop("user profile ran")\n')
    monkeypatch.setenv("R_PROFILE_USER", str(profile))
    outside = tmp_path / "outside.txt"
    outside.write_text("text")
    module = project.new("profile")
    project.step(module, "01_r.R", 'source(file.path(Sys.getenv("OMICSCLAW_SDK_DIR"), "notebook", "step.R"))\n'
                 + f'read_input("{outside}")\n!FALSE\n')
    assert _executor.run_targets(project.root, [module], out=project.out) == 0, project.text
    record = _ledger.read_run(next((project.root / "results" / module / "provenance/runs/01_r").glob("*.jsonl")))
    assert record.inputs[0]["outside_contract"] is True


@pytest.mark.requires_r
def test_rscript_stops_when_the_outer_shell_dies(project, rscript):
    import shlex
    import signal
    import sys
    import time

    from skills._sdk.notebook import _ledger
    from skills._sdk.notebook._lock import hold

    module = project.new("watch")
    project.step(module, "01_sleep.R", 'writeLines(as.character(Sys.getpid()), "r.pid")\nSys.sleep(120)\n')
    run = Path(_runners.__file__).with_name("run.py")
    command = f'{shlex.quote(sys.executable)} {shlex.quote(str(run))} run {module} > runner.log 2>&1; echo done'
    shell = subprocess.Popen(["bash", "-c", command], cwd=project.root,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    pid = None

    def alive(number):
        try:
            return Path(f"/proc/{number}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
        except FileNotFoundError:
            return False

    try:
        deadline = time.monotonic() + 30
        pidfile = project.root / "r.pid"
        while (not pidfile.exists() or not pidfile.read_text()) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert pidfile.exists(), (project.root / "runner.log").read_text()
        pid = int(pidfile.read_text())
        shell.kill()
        shell.wait(timeout=5)
        deadline = time.monotonic() + 10
        while alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not alive(pid), "Rscript outlived the shell by more than 10 seconds"
        result = project.root / "results" / module
        with hold(result / "provenance/.lock", command="test", wait=2):
            records = _ledger.runs_of(result / "provenance/runs", "01_sleep")
            assert records[-1].end["reason"] == "parent exited"
    finally:
        if shell.poll() is None:
            shell.kill()
            shell.wait(timeout=5)
        if pid is not None and alive(pid):
            os.killpg(pid, signal.SIGKILL)


@pytest.mark.requires_r
def test_missing_journaled_file_fails_the_run_without_losing_its_ledger(project, rscript):
    from skills._sdk.notebook import _executor, _ledger

    module = project.new("removed")
    project.step(module, "01_write.R", '''
        source(file.path(Sys.getenv("OMICSCLAW_SDK_DIR"), "notebook", "step.R"))
        path <- write_output("temporary", "tables/gone.txt")
        unlink(path)
    ''')
    assert _executor.run_targets(project.root, [module], out=project.out) == 1
    records = _ledger.runs_of(project.root / "results" / module / "provenance/runs", "01_write")
    assert records[-1].end["status"] == "failed"
    assert "gone.txt" in records[-1].end["error"]["evalue"]


@pytest.mark.requires_r
def test_switching_an_input_symlink_marks_the_r_step_stale(project, rscript):
    from skills._sdk.notebook import _executor, _ledger

    module = project.new("linked")
    data = project.root / "data"
    (data / "a.csv").write_text("value\n1\n")
    (data / "b.csv").write_text("value\n2\n")
    link = data / "current.csv"
    link.symlink_to("a.csv")
    project.step(module, "01_read.R", '''
        source(file.path(Sys.getenv("OMICSCLAW_SDK_DIR"), "notebook", "step.R"))
        write_output(read_input("data/current.csv"), "tables/value.csv")
    ''')
    assert _executor.run_targets(project.root, [module], out=project.out) == 0
    result = project.root / "results" / module
    record = _ledger.runs_of(result / "provenance/runs", "01_read")[-1]
    assert record.inputs[0]["path"] == "data/current.csv"
    link.unlink()
    link.symlink_to("b.csv")
    assert "input changed" in project.status(module)
    assert _executor.run_targets(project.root, [module], out=project.out) == 0
    assert (result / "tables/value.csv").read_text().splitlines() == ['"value"', "2"]


@pytest.mark.requires_r
def test_r_output_paths_use_the_same_normalization_as_python(project, rscript):
    import json

    from skills._sdk.notebook import _executor, _ledger

    module = project.new("paths")
    project.step(module, "01_write.R", '''
        source(file.path(Sys.getenv("OMICSCLAW_SDK_DIR"), "notebook", "step.R"))
        write_output("value", "tables/./value.txt")
    ''')
    project.step(module, "02_validate.py", '''
        from skills._sdk.notebook.checks import check_files
        check_files("tables/value.txt")
    ''')
    assert _executor.replay(project.root, module, runner=project.runner, out=project.out) == 0, project.text
    result = project.root / "results" / module
    record = _ledger.runs_of(result / "provenance/runs", "01_write")[-1]
    assert record.outputs[0]["path"] == "tables/value.txt"
    manifest = json.loads((result / "provenance/manifest.json").read_text())
    assert manifest["replay"]["orphan_outputs"] == []
    assert "tables/value.txt" in manifest["replay"]["changed_outputs"]


@pytest.mark.requires_r
@pytest.mark.parametrize("signal_name", ["SIGINT", "SIGTERM"])
def test_cancellation_reaps_r_before_unlocking_and_records_failure(project, rscript, signal_name):
    import signal
    import sys
    import time

    from skills._sdk.notebook import _ledger

    if os.name != "posix" or not Path("/proc").is_dir():
        pytest.skip("requires POSIX signals and /proc process state")

    def alive(pid):
        try:
            return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
        except FileNotFoundError:
            return False

    module = project.new("interrupt")
    project.step(module, "01_sleep.R", '''
        source(file.path(Sys.getenv("OMICSCLAW_SDK_DIR"), "notebook", "step.R"))
        writeLines(as.character(Sys.getpid()), "r.pid")
        Sys.sleep(30)
        write_output("late", "tables/late.txt")
    ''')
    command = Path(__file__).resolve().parents[3] / "skills/_sdk/notebook/run.py"
    process = subprocess.Popen([sys.executable, str(command), "run", module],
                               cwd=project.root, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, start_new_session=True)
    pid = None
    try:
        pidfile = project.root / "r.pid"
        deadline = time.monotonic() + 15
        while (not pidfile.exists() or not pidfile.read_text().strip()) and time.monotonic() < deadline:
            time.sleep(.03)
        assert pidfile.exists(), "R did not start"
        pid = int(pidfile.read_text())
        process.send_signal(getattr(signal, signal_name))
        process.wait(timeout=5)
        assert not alive(pid), "R outlived its interrupted runner"
        output, _ = process.communicate(timeout=5)
        assert process.returncode != 0, output
        result = project.root / "results" / module
        assert not (result / "tables/late.txt").exists()
        record = _ledger.runs_of(result / "provenance/runs", "01_sleep")[-1]
        assert record.end["status"] == "failed"
        expected = "KeyboardInterrupt" if signal_name == "SIGINT" else "RunnerStopped"
        assert record.end["error"]["ename"] == expected
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if pid is not None and alive(pid):
            os.killpg(pid, signal.SIGKILL)
        process.communicate(timeout=5)
