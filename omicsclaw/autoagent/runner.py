"""Trial runner — executes a single optimization trial as a subprocess.

Mirrors AutoAgent's Harbor runner.  Calls the OmicsClaw CLI as a subprocess
to run one trial with a specific parameter set, keeping the same execution
model as ``run_skill()`` in ``omicsclaw.py``.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from omicsclaw.autoagent.errors import OptimizationCancelled
from omicsclaw.autoagent.search_space import SearchSpace


@dataclass
class TrialExecution:
    """Result of executing a single trial."""

    success: bool
    output_dir: str
    duration_seconds: float
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""


def execute_trial(
    skill_name: str,
    input_path: str,
    output_dir: Path,
    params: dict[str, Any],
    search_space: SearchSpace,
    demo: bool = False,
    cancel_event: threading.Event | None = None,
) -> TrialExecution:
    """Execute a single optimization trial by calling ``omicsclaw.py run``.

    Converts the ``params`` dict to CLI arguments using the search space's
    CLI flag mapping, then runs the skill as a subprocess.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find the omicsclaw.py CLI script
    omicsclaw_dir = Path(__file__).resolve().parents[2]
    cli_script = omicsclaw_dir / "omicsclaw.py"

    python = sys.executable
    cmd = [python, str(cli_script), "run", skill_name]

    if demo:
        cmd.append("--demo")
    elif input_path:
        cmd.extend(["--input", str(Path(input_path).resolve())])

    cmd.extend(["--output", str(output_dir)])
    cmd.extend(["--method", search_space.method])

    # Add tunable params
    cmd.extend(_params_to_cli_args(params, search_space))

    # Add fixed params
    for pname, pvalue in search_space.fixed.items():
        flag = "--" + pname.replace("_", "-")
        if isinstance(pvalue, bool):
            if pvalue:
                cmd.append(flag)
        else:
            cmd.extend([flag, str(pvalue)])

    if cancel_event and cancel_event.is_set():
        raise OptimizationCancelled("Optimization cancelled before trial start")

    # Execute
    env = os.environ.copy()
    env["PYTHONPATH"] = str(omicsclaw_dir) + os.pathsep + env.get("PYTHONPATH", "")

    t0 = time.time()
    creationflags = 0
    popen_kwargs: dict[str, Any] = {}
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(omicsclaw_dir),
            env=env,
            creationflags=creationflags,
            **popen_kwargs,
        )
        stdout, stderr = _wait_for_process(
            proc,
            timeout_seconds=3600,
            started_at=t0,
            cancel_event=cancel_event,
        )
    except OptimizationCancelled:
        raise
    except subprocess.TimeoutExpired:
        return TrialExecution(
            success=False,
            output_dir=str(output_dir),
            duration_seconds=time.time() - t0,
            exit_code=-1,
            stderr="Trial timed out after 3600s",
        )
    except Exception as e:
        return TrialExecution(
            success=False,
            output_dir=str(output_dir),
            duration_seconds=time.time() - t0,
            exit_code=-1,
            stderr=str(e),
        )

    duration = time.time() - t0

    # The run command may rename the output dir — check result for actual path
    actual_output = str(output_dir)
    # Look for result.json in the output dir or any subdirectory
    if not (output_dir / "result.json").exists():
        for sub in output_dir.iterdir():
            if sub.is_dir() and (sub / "result.json").exists():
                actual_output = str(sub)
                break

    return TrialExecution(
        success=proc.returncode == 0,
        output_dir=actual_output,
        duration_seconds=round(duration, 2),
        exit_code=proc.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _params_to_cli_args(
    params: dict[str, Any],
    search_space: SearchSpace,
) -> list[str]:
    """Convert a parameter dict to CLI arguments."""
    args: list[str] = []
    param_lookup = {p.name: p for p in search_space.tunable}

    for pname, pvalue in params.items():
        pdef = param_lookup.get(pname)
        from omicsclaw.autoagent.constants import param_to_cli_flag
        flag = pdef.cli_flag if pdef else param_to_cli_flag(pname)

        if isinstance(pvalue, bool):
            if pvalue:
                args.append(flag)
        else:
            args.extend([flag, str(pvalue)])

    return args


def _wait_for_process(
    proc: subprocess.Popen[str],
    timeout_seconds: float,
    started_at: float,
    cancel_event: threading.Event | None,
    poll_interval_seconds: float = 0.25,
) -> tuple[str, str]:
    while True:
        if cancel_event and cancel_event.is_set():
            _terminate_process_tree(proc)
            raise OptimizationCancelled("Optimization cancelled")

        elapsed = time.time() - started_at
        remaining = timeout_seconds - elapsed
        if remaining <= 0:
            _terminate_process_tree(proc)
            raise subprocess.TimeoutExpired(proc.args, timeout_seconds)

        try:
            return proc.communicate(timeout=min(poll_interval_seconds, remaining))
        except subprocess.TimeoutExpired:
            continue


def _terminate_process_tree(proc: subprocess.Popen[str], kill_timeout_seconds: float = 5.0) -> None:
    if proc.poll() is not None:
        _collect_terminated_output(proc)
        return

    try:
        if os.name == "nt":
            proc.terminate()
        else:
            os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        _collect_terminated_output(proc)
        return
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass

    try:
        proc.wait(timeout=kill_timeout_seconds)
    except subprocess.TimeoutExpired:
        try:
            if os.name == "nt":
                proc.kill()
            else:
                os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass

    _collect_terminated_output(proc)


def _collect_terminated_output(proc: subprocess.Popen[str]) -> tuple[str, str]:
    try:
        return proc.communicate(timeout=1)
    except Exception:
        return "", ""
