"""The velocity CLI must return to a real notebook kernel without orphan workers."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.cli_subprocess]
REPO = Path(__file__).resolve().parents[5]
RUNNER = REPO / "skills/_sdk/notebook/run.py"


def _bounded(command, *, cwd, timeout):
    """Track PID identities across kernel sessions and always clean the entire tree."""
    psutil = pytest.importorskip("psutil")
    env = dict(os.environ, PYTHONPATH=str(REPO), PYTHONDONTWRITEBYTECODE="1")
    env.update({key: "2" for key in
                ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS")})
    env.pop("NUMBA_DISABLE_JIT", None)
    env.pop("OMICSCLAW_SKILL_STUBS", None)
    process = subprocess.Popen(command, cwd=cwd, env=env, start_new_session=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    descendants = {}
    stop = threading.Event()

    def remember():
        while not stop.wait(0.03):
            # A kernel may outlive its runner after creating a separate session.
            try:
                parents = [psutil.Process(process.pid)]
            except psutil.NoSuchProcess:
                parents = []
            parents.extend(list(descendants.values()))
            for parent in parents:
                try:
                    children = parent.children(recursive=True)
                except psutil.NoSuchProcess:
                    continue
                for child in children:
                    try:
                        descendants[(child.pid, child.create_time())] = child
                    except psutil.NoSuchProcess:
                        pass

    tracking = threading.Thread(target=remember, daemon=True)
    tracking.start()
    timed_out = False
    output = ""
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        output = exc.output.decode() if isinstance(exc.output, bytes) else (exc.output or "")
    finally:
        stop.set()
        tracking.join()
        live = []
        for child in descendants.values():
            try:
                if child.is_running() and child.status() != psutil.STATUS_ZOMBIE:
                    live.append(child)
                    child.kill()
            except psutil.NoSuchProcess:
                pass
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        psutil.wait_procs(live, timeout=10)
        process.stdout.close()
        survivors = []
        for child in descendants.values():
            try:
                if child.is_running() and child.status() != psutil.STATUS_ZOMBIE:
                    survivors.append(child.pid)
            except psutil.NoSuchProcess:
                pass
        assert not survivors, f"Leaked descendants: {survivors}"
    return process.returncode, output, timed_out, list(descendants)


def test_run_cli_returns_to_its_notebook_kernel(tmp_path):
    pytest.importorskip("scvelo")
    result = subprocess.run([sys.executable, str(RUNNER), "new", "velocity"], cwd=tmp_path,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    step = tmp_path / "analysis/01_velocity/01_velocity.py"
    step.write_text(
        '# %%\nfrom skills._sdk.notebook import run_cli, write_output\n'
        'import pandas as pd\n'
        'output = run_cli("sc-velocity", "--demo", timeout=90)\n'
        'assert (output / "result.json").is_file()\n'
        'write_output(pd.DataFrame({"kernel_alive": [True]}), "tables/alive.csv")\n'
    )
    code, output, timed_out, descendants = _bounded(
        [sys.executable, str(RUNNER), "run", "analysis/01_velocity"], cwd=tmp_path, timeout=150,
    )
    assert not timed_out, output[-4000:]
    assert code == 0, output[-4000:]
    assert descendants, "the tracker did not observe the kernel and CLI"
    assert (tmp_path / "results/01_velocity/tables/alive.csv").is_file()


def test_cleanup_releases_inherited_pipe_from_other_session_child(tmp_path):
    launcher = tmp_path / "owner.py"
    script = REPO / "skills/singlecell/scrna/sc-velocity/sc_velocity.py"
    launcher.write_text(
        'import importlib.util, os, subprocess, sys, time\n'
        f'spec = importlib.util.spec_from_file_location("velocity_cli", {str(script)!r})\n'
        'module = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(module)\n'
        'child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"], start_new_session=True)\n'
        'print("child", child.pid, flush=True)\n'
        'time.sleep(0.2)\n'
        'module._close_cli_workers()\n'
        'print("cleanup complete", flush=True)\nos._exit(0)\n'
    )
    code, output, timed_out, _ = _bounded([sys.executable, str(launcher)], cwd=tmp_path, timeout=30)
    assert not timed_out, output[-4000:]
    assert code == 0 and "cleanup complete" in output, output[-4000:]
