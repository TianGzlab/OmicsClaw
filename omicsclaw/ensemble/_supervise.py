"""Run one command under a time and memory limit, and report how it ended.

Standard library only, and run by file path under whatever interpreter the
execution environment has::

    python _supervise.py --timeout 1800 --max-mem-mb 32768 --status supervisor.json -- CMD ARGS...

The supervisor makes itself a process-group leader when it can and starts the
command in the same group, so everything the command starts is counted and
killed together. Every ``--poll`` seconds it sums the memory of the group's
other processes: PSS from ``/proc/<pid>/smaps_rollup`` (shared pages divided
between the processes that map them), or RSS from ``/proc/<pid>/status`` for a
process whose ``smaps_rollup`` cannot be read, in which case the whole run is
reported as ``rss``. Every ``--gpu-poll`` seconds it asks ``nvidia-smi`` which
processes use a GPU and records whether one of the group's did. When every
process ``nvidia-smi`` lists is absent from this ``/proc`` — the supervisor
runs in another PID namespace than the driver reports, as in most
containers — GPU use cannot be attributed and ``gpu_probe`` is
``unattributable`` for the rest of the run.

Outcomes, written to ``--status`` as JSON (``status``, ``exit_code``,
``wall_s``, ``peak_mem_mb``, ``mem_metric``, ``gpu_used``, ``gpu_mem_peak_mb``,
``gpu_probe``):

- ``ok`` / ``failed``: the command exited 0 / non-zero by itself.
- ``memory_exceeded``: the group went over ``--max-mem-mb``; it was SIGKILLed.
- ``timeout``: ``--timeout`` passed; the group got SIGTERM, then SIGKILL after
  ``--grace`` seconds.
- ``cancelled``: the supervisor got SIGTERM or SIGINT; the group was killed.

When the supervisor cannot lead a group of its own, the command is started in
a new session instead and that session's group is the one watched and killed,
so the supervisor never signals a group it does not own.

On Linux the command gets ``PR_SET_PDEATHSIG`` (SIGKILL), so it dies with the
supervisor, and the supervisor gets SIGTERM when its own parent dies, so a
killed launcher still leads to the group being cleaned up. The supervisor's
own exit status is the command's, or 124 for a timeout, 137 for a memory kill
and 143 for a cancellation.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time

GPU_QUERY = ["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"]


def group_members(pgid, proc_root="/proc", exclude=()):
    """Pids whose process group is *pgid*, minus *exclude*."""
    members = []
    try:
        entries = os.listdir(proc_root)
    except OSError:
        return members
    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid in exclude:
            continue
        try:
            with open(os.path.join(proc_root, entry, "stat"), "rb") as handle:
                data = handle.read().decode("utf-8", "replace")
        except OSError:
            continue
        fields = data[data.rfind(")") + 2:].split()
        if len(fields) > 2 and fields[2] == str(pgid):
            members.append(pid)
    return members


def process_memory_kb(pid, proc_root="/proc"):
    """``(kB, "pss")`` from ``smaps_rollup``, ``(kB, "rss")`` from ``status``, or ``(0, None)``."""
    try:
        with open(os.path.join(proc_root, str(pid), "smaps_rollup"), "r") as handle:
            for line in handle:
                if line.startswith("Pss:"):
                    return int(line.split()[1]), "pss"
    except (OSError, ValueError, IndexError):
        pass
    try:
        with open(os.path.join(proc_root, str(pid), "status"), "r") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]), "rss"
    except (OSError, ValueError, IndexError):
        pass
    return 0, None


def group_memory_kb(pids, proc_root="/proc"):
    """Total memory of *pids* in kB, and ``"pss"`` unless any process fell back to RSS."""
    total = 0
    metric = "pss"
    for pid in pids:
        kb, kind = process_memory_kb(pid, proc_root)
        total += kb
        if kind == "rss":
            metric = "rss"
    return total, metric


def parse_gpu_apps(output):
    """``{pid: used MiB}`` from ``nvidia-smi --query-compute-apps`` CSV output."""
    apps = {}
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2 or not parts[0].isdigit():
            continue
        try:
            used = float(parts[1].split()[0])
        except (ValueError, IndexError):
            used = 0.0
        apps[int(parts[0])] = apps.get(int(parts[0]), 0.0) + used
    return apps


def query_gpu_apps(command=GPU_QUERY, timeout=10.0):
    """``{pid: MiB}`` of processes using a GPU, or ``None`` when ``nvidia-smi`` cannot answer."""
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            start_new_session=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return parse_gpu_apps(completed.stdout)


def _set_pdeathsig(sig):
    """Ask Linux to send *sig* to this process when its parent dies."""
    try:
        import ctypes

        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(1, sig)
    except Exception:
        pass


def _pdeathsig():
    _set_pdeathsig(signal.SIGKILL)


class Supervisor:
    """One supervised run; see the module docstring."""

    def __init__(self, args):
        self.args = args
        self.me = os.getpid()
        self.status = None
        self.peak_kb = 0
        self.metric = "pss"
        self.gpu_used = False
        self.gpu_peak_mb = 0.0
        self.gpu_probe = "unavailable"
        self.stop_signal = None

    def _signalled(self, signum, frame):
        self.stop_signal = signum

    def _kill_group(self, sig):
        for pid in group_members(self.pgid, self.args.proc_root, exclude={self.me}):
            try:
                os.kill(pid, sig)
            except (ProcessLookupError, PermissionError):
                pass

    def _terminate(self, grace):
        if grace > 0:
            self._kill_group(signal.SIGTERM)
            deadline = time.monotonic() + grace
            while time.monotonic() < deadline and self.child.poll() is None:
                time.sleep(0.05)
        for _ in range(50):
            self._kill_group(signal.SIGKILL)
            if self.child.poll() is not None and not group_members(
                self.pgid, self.args.proc_root, exclude={self.me}
            ):
                break
            time.sleep(0.05)
        self.child.wait()

    def _sample_memory(self):
        pids = group_members(self.pgid, self.args.proc_root, exclude={self.me})
        kb, metric = group_memory_kb(pids, self.args.proc_root)
        if metric == "rss":
            self.metric = "rss"
        self.peak_kb = max(self.peak_kb, kb)
        return kb, pids

    def _sample_gpu(self, pids):
        apps = query_gpu_apps(self.args.nvidia_smi.split() + GPU_QUERY[1:])
        if apps is None or self.gpu_probe == "unattributable":
            return
        ours = [pid for pid in apps if pid in pids]
        if apps and not ours and not any(
            os.path.exists(os.path.join(self.args.proc_root, str(pid))) for pid in apps
        ):
            self.gpu_probe = "unattributable"
            return
        self.gpu_probe = "ok"
        used = sum(apps[pid] for pid in ours)
        if ours:
            self.gpu_used = True
        self.gpu_peak_mb = max(self.gpu_peak_mb, used)

    def run(self):
        args = self.args
        try:
            os.setpgid(0, 0)
        except OSError:
            pass
        self.pgid = os.getpgid(0)
        own_group = self.pgid == self.me
        signal.signal(signal.SIGTERM, self._signalled)
        signal.signal(signal.SIGINT, self._signalled)
        linux = sys.platform.startswith("linux")
        if linux:
            _set_pdeathsig(signal.SIGTERM)
        started = time.monotonic()
        try:
            self.child = subprocess.Popen(
                args.command,
                preexec_fn=_pdeathsig if linux else None,
                start_new_session=not own_group,
            )
        except OSError as exc:
            print(f"supervise: cannot start {args.command[0]!r}: {exc}", file=sys.stderr, flush=True)
            write_status(args.status, {
                "status": "failed", "exit_code": 127, "wall_s": 0.0, "peak_mem_mb": 0.0,
                "mem_metric": self.metric, "gpu_used": False, "gpu_mem_peak_mb": 0.0,
                "gpu_probe": self.gpu_probe,
            })
            return 127
        if not own_group:
            self.pgid = self.child.pid
        limit_kb = args.max_mem_mb * 1024
        next_gpu = started
        exit_code = None
        while True:
            exit_code = self.child.poll()
            now = time.monotonic()
            if exit_code is not None:
                self.status = "ok" if exit_code == 0 else "failed"
                break
            if self.stop_signal is not None:
                self.status = "cancelled"
                self._terminate(0)
                break
            kb, pids = self._sample_memory()
            if kb > limit_kb:
                self.status = "memory_exceeded"
                self._terminate(0)
                break
            if now - started > args.timeout:
                self.status = "timeout"
                self._terminate(args.grace)
                break
            if args.gpu_poll > 0 and now >= next_gpu:
                self._sample_gpu(set(pids) | {self.child.pid})
                next_gpu = now + args.gpu_poll
            try:
                self.child.wait(timeout=args.poll)
            except subprocess.TimeoutExpired:
                pass
        self._kill_group(signal.SIGKILL)
        wall = time.monotonic() - started
        code = self.child.returncode
        report = {
            "status": self.status,
            "exit_code": code,
            "wall_s": round(wall, 3),
            "peak_mem_mb": round(self.peak_kb / 1024, 1),
            "mem_metric": self.metric,
            "gpu_used": self.gpu_used,
            "gpu_mem_peak_mb": round(self.gpu_peak_mb, 1),
            "gpu_probe": self.gpu_probe,
        }
        write_status(args.status, report)
        return {"ok": 0, "timeout": 124, "memory_exceeded": 137, "cancelled": 143}.get(
            self.status, code if code and code > 0 else 1
        )


def write_status(path, report):
    directory = os.path.dirname(os.path.abspath(path))
    handle, temporary = tempfile.mkstemp(dir=directory, suffix=".tmp")
    with os.fdopen(handle, "w") as sink:
        json.dump(report, sink, indent=1, sort_keys=True)
    os.replace(temporary, path)


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Supervise one command.")
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("--max-mem-mb", type=float, required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--grace", type=float, default=5.0)
    parser.add_argument("--poll", type=float, default=1.0)
    parser.add_argument("--gpu-poll", type=float, default=5.0)
    parser.add_argument("--nvidia-smi", default="nvidia-smi")
    parser.add_argument("--proc-root", default="/proc")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("no command after --")
    return args


def main(argv=None):
    return Supervisor(parse_args(sys.argv[1:] if argv is None else argv)).run()


if __name__ == "__main__":
    sys.exit(main())
