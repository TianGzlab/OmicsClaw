"""The real kernel runner: interpreter, isolation, failures and clean-up."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("nbclient")
pytest.importorskip("ipykernel")

REPO = Path(__file__).resolve().parents[3]
RUN = REPO / "skills" / "_sdk" / "notebook" / "run.py"


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    home = tmp_path / "home"
    root.mkdir()
    home.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("OMICSCLAW_", "JUPYTER", "IPYTHON"))}
    env.update(HOME=str(home), PYTHONDONTWRITEBYTECODE="1", XDG_CACHE_HOME=str(home / ".cache"),
               XDG_DATA_HOME=str(home / ".local/share"), XDG_CONFIG_HOME=str(home / ".config"),
               MPLCONFIGDIR=str(tmp_path / "mpl"))

    def runner(*args, timeout=180):
        return subprocess.run([sys.executable, str(RUN), *args], cwd=root, env=env,
                              capture_output=True, text=True, timeout=timeout)

    assert runner("new", "k").returncode == 0
    return root, home, env, runner


def _step(root, name, body):
    path = root / "analysis" / "01_k" / name
    path.write_text(body, encoding="utf-8")
    return path


def test_the_kernel_runs_the_runner_interpreter(project):
    root, _home, _env, runner = project
    _step(root, "01_which.py",
          "# %%\nimport sys\nfrom skills._sdk.notebook import write_output\n"
          "write_output({'exe': sys.executable, 'prefix': sys.prefix}, 'tables/which.json')\n")
    proc = runner("run", "analysis/01_k")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    which = json.loads((root / "results/01_k/tables/which.json").read_text())
    assert which == {"exe": sys.executable, "prefix": sys.prefix}


def test_the_kernel_writes_nothing_under_home(project):
    root, home, _env, runner = project
    _step(root, "01_hello.py", "# %%\nprint('hello')\nimport IPython\nIPython.get_ipython().run_line_magic('who', '')\n")
    proc = runner("run", "analysis/01_k")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert sorted(p.relative_to(home).as_posix() for p in home.rglob("*")) == []


def test_user_ipython_startup_files_do_not_run(project, tmp_path):
    root, _home, env, runner = project
    startup = tmp_path / "home" / ".ipython" / "profile_default" / "startup"
    startup.mkdir(parents=True)
    (startup / "00-x.py").write_text("INJECTED = 1\n")
    _step(root, "01_check.py", "# %%\nassert 'INJECTED' not in globals()\n")
    proc = runner("run", "analysis/01_k")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_a_failing_cell_keeps_the_partial_notebook(project):
    import nbformat

    root, _home, _env, runner = project
    _step(root, "01_fail.py", "# %%\nprint('before')\n\n# %%\nraise KeyError('gene_x')\n\n# %%\nprint('after')\n")
    proc = runner("run", "analysis/01_k")
    assert proc.returncode == 1
    assert "error:    cell 2: KeyError: 'gene_x'" in proc.stdout
    nb = nbformat.read(str(root / "results/01_k/notebooks/01_fail.ipynb"), as_version=4)
    assert nb.cells[0].outputs[0]["text"] == "before\n"
    assert nb.cells[1].outputs[0]["output_type"] == "error"
    assert nb.cells[2].outputs == []
    end = [json.loads(line) for line in next((root / "results/01_k/provenance/runs/01_fail").glob("*.jsonl")).read_text().splitlines()][-1]
    assert end["event"] == "run_end" and end["status"] == "failed" and end["error"]["cell"] == 2


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        with open(f"/proc/{pid}/stat") as handle:
            return handle.read().split()[2] != "Z"
    except OSError:
        return True


def test_the_kernel_exits_after_the_runner_is_killed(project):
    root, _home, env, _runner = project
    _step(root, "01_sleep.py",
          "# %%\nimport os, pathlib, time\n"
          "pathlib.Path('kernel.pid').write_text(str(os.getpid()))\n"
          "time.sleep(120)\n")
    proc = subprocess.Popen([sys.executable, str(RUN), "run", "analysis/01_k"], cwd=root, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    pid_file = root / "kernel.pid"
    deadline = time.monotonic() + 60
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.2)
    assert pid_file.exists(), "the kernel never started the step"
    kernel = int(pid_file.read_text())
    os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()
    deadline = time.monotonic() + 10
    while _alive(kernel) and time.monotonic() < deadline:
        time.sleep(0.2)
    alive = _alive(kernel)
    if alive:
        os.kill(kernel, signal.SIGKILL)
    assert not alive, "the kernel outlived the runner by more than 10 s"


def test_no_kernel_is_left_running_after_a_step(project):
    root, _home, _env, runner = project
    _step(root, "01_pid.py", "# %%\nimport os, pathlib\npathlib.Path('kernel.pid').write_text(str(os.getpid()))\n")
    proc = runner("run", "analysis/01_k")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    kernel = int((root / "kernel.pid").read_text())
    deadline = time.monotonic() + 5
    while _alive(kernel) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not _alive(kernel)
    assert "Parent appears to have exited" not in proc.stderr


def _lines_step(index):
    return f"# %%\nfor i in range(30):\n    print('step {index} line', i)\n"


def test_a_closed_pipe_does_not_stop_the_run(project):
    root, _home, env, _runner = project
    for index in (1, 2, 3):
        _step(root, f"0{index}_lines.py", _lines_step(index))
    proc = subprocess.run(
        ["bash", "-c", f'"{sys.executable}" "{RUN}" run analysis/01_k | head -5; echo "exit=${{PIPESTATUS[0]}}"'],
        cwd=root, env=env, capture_output=True, text=True, timeout=300,
    )
    assert proc.stdout.splitlines()[-1] == "exit=0", proc.stdout + proc.stderr
    assert "BrokenPipeError" not in proc.stderr
    manifest = json.loads((root / "results/01_k/provenance/manifest.json").read_text())
    assert [(s["file"], s["state"]) for s in manifest["steps"]] == [
        ("01_lines.py", "ok"), ("02_lines.py", "ok"), ("03_lines.py", "ok"),
    ]
    assert (root / "results/01_k/notebooks/M01_k.ipynb").is_file()


def test_the_runner_stops_when_its_parent_shell_is_killed(project):
    from skills._sdk.notebook import _ledger
    from skills._sdk.notebook._lock import LockBusy, hold

    root, _home, env, _runner = project
    _step(root, "01_sleep.py",
          "# %%\nimport os, pathlib, time\n"
          "pathlib.Path('pids.txt').write_text(f'{os.getppid()} {os.getpid()}')\n"
          "time.sleep(120)\n")
    shell = subprocess.Popen(
        ["bash", "-c", f'"{sys.executable}" "{RUN}" run analysis/01_k > runner.log 2>&1; echo done'],
        cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    pids = root / "pids.txt"
    deadline = time.monotonic() + 60
    while not (pids.exists() and pids.read_text()) and time.monotonic() < deadline:
        time.sleep(0.2)
    runner_pid, kernel = (int(value) for value in pids.read_text().split())
    shell.kill()
    shell.wait()
    deadline = time.monotonic() + 10
    while (_alive(runner_pid) or _alive(kernel)) and time.monotonic() < deadline:
        time.sleep(0.2)
    left = [pid for pid in (runner_pid, kernel) if _alive(pid)]
    for pid in left:
        os.kill(pid, signal.SIGKILL)
    assert left == [], "the runner or its kernel outlived the parent shell by more than 10 s"
    try:
        with hold(root / "results/01_k/provenance/.lock", command="test"):
            pass
    except LockBusy:
        pytest.fail("the module lock is still held")
    run = _ledger.runs_of(root / "results/01_k/provenance/runs", "01_sleep")[-1]
    assert run.status == "failed"
    assert run.end["error"]["evalue"] == "parent exited" and run.end["reason"] == "parent exited"
    assert "parent exited; stopped 01_k/01_sleep.py" in (root / "runner.log").read_text()
