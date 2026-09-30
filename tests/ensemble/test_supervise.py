"""``_supervise.py``: time and memory limits on a whole process group.

The supervisor is what makes "this trial may use 32 GB for 30 minutes" true.
It counts the memory of every process the skill starts (a joblib pool, a
torch DataLoader worker), not only the first one, and kills all of them when
a limit is crossed; a limit enforced on one pid would let the workers outlive
the trial. Memory is measured as PSS so that forked workers sharing pages are
not counted several times; where ``smaps_rollup`` cannot be read the
supervisor falls back to RSS and says so. Whether a GPU was really used is
observed from ``nvidia-smi``'s per-process list, not assumed from the lease.

It is run by file path under a plain interpreter with no repository on the
path, which is how the sandbox runs it.
"""

from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

SUPERVISE = Path(__file__).resolve().parents[2] / "omicsclaw" / "ensemble" / "_supervise.py"

pytestmark = pytest.mark.skipif(not os.path.isdir("/proc"), reason="reads /proc")


def _module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("_supervise_under_test", SUPERVISE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _supervise(tmp_path: Path, *command: str, timeout=30.0, max_mem_mb=4096.0, extra=(), env=None):
    status = tmp_path / "supervisor.json"
    completed = subprocess.run(
        [sys.executable, str(SUPERVISE), "--timeout", str(timeout), "--max-mem-mb", str(max_mem_mb),
         "--status", str(status), "--poll", "0.1", "--grace", "1", *extra, "--", *command],
        capture_output=True, text=True, timeout=120, start_new_session=True,
        env=env,
    )
    return completed, json.loads(status.read_text())


def _alive(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/stat") as handle:
            return handle.read().split(")")[-1].split()[0] != "Z"
    except OSError:
        return False


def test_the_exit_code_passes_through(tmp_path):
    completed, report = _supervise(tmp_path, sys.executable, "-c", "import sys; sys.exit(3)")
    assert report["status"] == "failed" and report["exit_code"] == 3
    assert completed.returncode == 3
    completed, report = _supervise(tmp_path, sys.executable, "-c", "print('hi')")
    assert report["status"] == "ok" and report["exit_code"] == 0 and completed.returncode == 0
    assert "hi" in completed.stdout


def test_a_sleep_past_the_limit_is_a_timeout(tmp_path):
    began = time.monotonic()
    completed, report = _supervise(tmp_path, "sleep", "30", timeout=0.5)
    assert report["status"] == "timeout"
    assert completed.returncode == 124
    assert time.monotonic() - began < 10


def test_allocating_past_the_limit_is_memory_exceeded(tmp_path):
    code = "import time\nblocks = []\nfor _ in range(400):\n    blocks.append(bytearray(10 * 1024 * 1024))\n    time.sleep(0.01)\ntime.sleep(30)\n"
    completed, report = _supervise(tmp_path, sys.executable, "-c", code, max_mem_mb=300)
    assert report["status"] == "memory_exceeded"
    assert completed.returncode == 137
    assert report["peak_mem_mb"] > 300


def test_the_peak_memory_counts_the_whole_group(tmp_path):
    code = (
        "import subprocess, sys, time\n"
        "child = 'import time; b = bytearray(150 * 1024 * 1024); b[::4096] = b\"x\" * len(b[::4096]); time.sleep(1.5)'\n"
        "procs = [subprocess.Popen([sys.executable, '-c', child]) for _ in range(2)]\n"
        "[p.wait() for p in procs]\n"
    )
    _, report = _supervise(tmp_path, sys.executable, "-c", code)
    assert report["status"] == "ok"
    assert report["peak_mem_mb"] > 250
    assert report["mem_metric"] in ("pss", "rss")


def test_killing_the_supervisor_leaves_nothing_behind(tmp_path):
    pidfile = tmp_path / "grandchild.pid"
    code = (
        "import subprocess, time\n"
        f"p = subprocess.Popen(['sleep', '60'])\nopen({str(pidfile)!r}, 'w').write(str(p.pid))\n"
        "time.sleep(60)\n"
    )
    process = subprocess.Popen(
        [sys.executable, str(SUPERVISE), "--timeout", "60", "--max-mem-mb", "4096",
         "--status", str(tmp_path / "s.json"), "--poll", "0.1", "--", sys.executable, "-c", code],
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 10
        while not pidfile.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        grandchild = int(pidfile.read_text())
        assert _alive(grandchild)
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=10)
        deadline = time.monotonic() + 5
        while _alive(grandchild) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not _alive(grandchild)
        assert json.loads((tmp_path / "s.json").read_text())["status"] == "cancelled"
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def test_a_command_that_cannot_start_is_failed_127(tmp_path):
    completed, report = _supervise(tmp_path, "/nonexistent/binary")
    assert report["status"] == "failed" and report["exit_code"] == 127
    assert completed.returncode == 127


# ---- memory accounting, with an injected /proc ------------------------------------------


def _fake_proc(root: Path, pid: int, *, pss_kb=None, rss_kb=None):
    directory = root / str(pid)
    directory.mkdir(parents=True)
    (directory / "stat").write_text(f"{pid} (python) S 1 777 777 0 0\n")
    if pss_kb is not None:
        (directory / "smaps_rollup").write_text(f"Rss: {pss_kb * 2} kB\nPss: {pss_kb} kB\n")
    if rss_kb is not None:
        (directory / "status").write_text(f"Name: python\nVmRSS:\t{rss_kb} kB\n")


def test_pss_is_used_where_smaps_rollup_is_readable(tmp_path):
    supervise = _module()
    _fake_proc(tmp_path, 10, pss_kb=1000, rss_kb=5000)
    _fake_proc(tmp_path, 11, pss_kb=500, rss_kb=5000)
    assert supervise.group_members(777, str(tmp_path)) and set(supervise.group_members(777, str(tmp_path))) == {10, 11}
    assert supervise.group_memory_kb([10, 11], str(tmp_path)) == (1500, "pss")


def test_rss_is_the_fallback_and_is_reported(tmp_path):
    supervise = _module()
    _fake_proc(tmp_path, 10, pss_kb=1000, rss_kb=5000)
    _fake_proc(tmp_path, 12, rss_kb=3000)
    assert supervise.group_memory_kb([10, 12], str(tmp_path)) == (4000, "rss")


# ---- GPU observation ------------------------------------------------------------------------


def test_gpu_apps_are_parsed():
    supervise = _module()
    output = "1234, 2048\n5678, 100\nNo running processes found\n"
    assert supervise.parse_gpu_apps(output) == {1234: 2048.0, 5678: 100.0}


def _fake_nvidia_smi(directory: Path, body: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "nvidia-smi"
    script.write_text(f"#!/bin/sh\n{body}\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def test_gpu_use_is_observed_for_a_pid_of_the_group(tmp_path):
    # The fake reports the supervised command's pid, which it wrote to a file, as a GPU user.
    fake = _fake_nvidia_smi(tmp_path / "bin", 'echo "$(cat ' + str(tmp_path / "pid") + '), 512"')
    code = f"import os, time; open({str(tmp_path / 'pid')!r}, 'w').write(str(os.getpid())); time.sleep(1.0)"
    _, report = _supervise(tmp_path, sys.executable, "-c", code, extra=("--gpu-poll", "0.2", "--nvidia-smi", str(fake)))
    assert report["gpu_probe"] == "ok"
    assert report["gpu_used"] is True
    assert report["gpu_mem_peak_mb"] == 512


def test_gpu_use_by_another_process_is_not_ours(tmp_path):
    fake = _fake_nvidia_smi(tmp_path / "bin", 'echo "1, 4096"')  # pid 1 exists in this /proc
    _, report = _supervise(
        tmp_path, sys.executable, "-c", "import time; time.sleep(0.8)",
        extra=("--gpu-poll", "0.2", "--nvidia-smi", str(fake)),
    )
    assert report["gpu_probe"] == "ok" and report["gpu_used"] is False


def test_no_nvidia_smi_is_reported_as_unavailable(tmp_path):
    _, report = _supervise(
        tmp_path, sys.executable, "-c", "import time; time.sleep(0.5)",
        extra=("--gpu-poll", "0.2", "--nvidia-smi", "/nonexistent/nvidia-smi"),
    )
    assert report["gpu_probe"] == "unavailable" and report["gpu_used"] is False


def test_pids_from_another_namespace_make_gpu_use_unattributable(tmp_path):
    """In a container ``nvidia-smi`` reports host pids, which match nothing
    here; reporting ``cpu`` then would be a guess, so the probe says it
    could not attribute and the runner falls back to what the skill reported."""
    fake = _fake_nvidia_smi(tmp_path / "bin", 'echo "4194000, 2048"')
    _, report = _supervise(
        tmp_path, sys.executable, "-c", "import time; time.sleep(0.8)",
        extra=("--gpu-poll", "0.2", "--nvidia-smi", str(fake)),
    )
    assert report["gpu_probe"] == "unattributable" and report["gpu_used"] is False
