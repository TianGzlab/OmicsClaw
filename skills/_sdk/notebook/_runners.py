"""Running one step's notebook.

:class:`StepRunner` is the seam: it executes a notebook node with a given
environment and working directory and reports a :class:`StepOutcome`.
:class:`PythonKernelRunner` does it in a fresh IPython kernel through
nbclient, started from a temporary kernelspec whose ``argv`` is this
interpreter, so the kernel runs exactly the interpreter the runner was
started with. IPython and Jupyter directories point into a temporary
folder, which keeps the user's IPython startup files out of the kernel and
keeps the kernel from writing under ``$HOME``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import signal
import sys
import tempfile
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
KERNEL_NAME = "omicsclaw-step"


@dataclass
class StepOutcome:
    """What running one step produced."""

    status: str
    notebook: Any
    seconds: float
    error: dict | None = None
    stream: str = ""
    notes: list[str] = field(default_factory=list)


class StepRunner(Protocol):
    def run(self, notebook: Any, *, env: Mapping[str, str], cwd: Path) -> StepOutcome:
        """Execute *notebook* with *env* as the environment and *cwd* as the working directory."""


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def stream_text(notebook: Any) -> str:
    """Every stream output and error traceback of an executed notebook, in cell order."""
    parts: list[str] = []
    for cell in getattr(notebook, "cells", []):
        if cell.get("cell_type") != "code":
            continue
        for output in cell.get("outputs", []):
            kind = output.get("output_type")
            if kind == "stream":
                parts.append(output.get("text", ""))
            elif kind == "error":
                parts.append(strip_ansi("\n".join(output.get("traceback", []))) + "\n")
    return "".join(parts)


def first_error(notebook: Any) -> dict | None:
    """The first error output of a notebook: cell number (1-based), name, value and traceback."""
    for number, cell in enumerate(getattr(notebook, "cells", []), start=1):
        if cell.get("cell_type") != "code":
            continue
        for output in cell.get("outputs", []):
            if output.get("output_type") == "error":
                return {
                    "cell": number,
                    "ename": output.get("ename", ""),
                    "evalue": strip_ansi(str(output.get("evalue", ""))),
                    "traceback": strip_ansi("\n".join(output.get("traceback", []))),
                }
    return None


def missing_kernel_packages() -> list[str]:
    """The packages the kernel runner needs that this interpreter lacks."""
    return [name for name in ("nbclient", "nbformat", "ipykernel", "jupyter_client")
            if importlib.util.find_spec(name) is None]


@contextmanager
def _environ(values: Mapping[str, str]) -> Iterator[None]:
    saved = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class PythonKernelRunner:
    """Executes a step notebook cell by cell in a new IPython kernel."""

    def __init__(self, python: str | None = None, *, startup_timeout: int = 120) -> None:
        self.python = python or sys.executable
        self.startup_timeout = int(startup_timeout)
        self._manager: Any = None

    def kill(self) -> None:
        """Kill the running kernel and its process group at once; callable from another thread."""
        provisioner = getattr(self._manager, "provisioner", None)
        pid = getattr(provisioner, "pid", None)
        pgid = getattr(provisioner, "pgid", None)
        try:
            if pgid and pgid != os.getpgrp():
                os.killpg(pgid, signal.SIGKILL)
            elif pid:
                os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    def _attempt(self, notebook: Any, env: Mapping[str, str], cwd: Path, scratch: Path) -> StepOutcome:
        from jupyter_client.kernelspec import KernelSpecManager
        from jupyter_client.manager import KernelManager
        from nbclient import NotebookClient
        from nbclient.exceptions import CellExecutionError, DeadKernelError

        spec_dir = scratch / "kernels" / KERNEL_NAME
        spec_dir.mkdir(parents=True, exist_ok=True)
        (spec_dir / "kernel.json").write_text(json.dumps({
            "argv": [self.python, "-m", "ipykernel_launcher", "-f", "{connection_file}",
                     "--HistoryManager.enabled=False"],
            "display_name": "OmicsClaw step",
            "language": "python",
        }), encoding="utf-8")
        isolated = {
            "IPYTHONDIR": str(scratch / "ipython"),
            "JUPYTER_RUNTIME_DIR": str(scratch / "runtime"),
            "JUPYTER_DATA_DIR": str(scratch / "data"),
            "JUPYTER_CONFIG_DIR": str(scratch / "config"),
        }
        for folder in isolated.values():
            Path(folder).mkdir(parents=True, exist_ok=True)
        kernel_env = {**env, **isolated}
        spec_manager = KernelSpecManager(kernel_dirs=[str(scratch / "kernels")], ensure_native_kernel=False)
        manager = KernelManager(
            kernel_name=KERNEL_NAME,
            kernel_spec_manager=spec_manager,
            connection_file=str(scratch / "runtime" / "kernel-step.json"),
        )
        client = NotebookClient(
            notebook,
            km=manager,
            kernel_name=KERNEL_NAME,
            timeout=None,
            startup_timeout=self.startup_timeout,
            allow_errors=False,
            shutdown_kernel="immediate",
            record_timing=True,
            resources={"metadata": {"path": str(cwd)}},
        )
        started = time.perf_counter()
        self._manager = manager
        with _environ(isolated):
            try:
                client.execute(cwd=str(cwd), env=kernel_env, cleanup_kc=True)
                status, error = "ok", None
            except CellExecutionError:
                status, error = "failed", first_error(notebook)
            except DeadKernelError as exc:
                status = "failed"
                error = first_error(notebook) or {
                    "cell": None, "ename": "DeadKernelError", "evalue": str(exc), "traceback": "",
                }
            finally:
                self._manager = None
                if manager.has_kernel:
                    manager.shutdown_kernel(now=True)
        seconds = time.perf_counter() - started
        if status == "failed" and error is None:
            error = {"cell": None, "ename": "RuntimeError", "evalue": "the step failed", "traceback": ""}
        return StepOutcome(status=status, notebook=notebook, seconds=seconds, error=error,
                           stream=stream_text(notebook))

    def run(self, notebook: Any, *, env: Mapping[str, str], cwd: Path) -> StepOutcome:
        notes: list[str] = []
        for attempt in (1, 2):
            with tempfile.TemporaryDirectory(prefix="omicsclaw-step-") as scratch:
                pristine = json.loads(json.dumps(notebook))
                try:
                    outcome = self._attempt(notebook, env, cwd, Path(scratch))
                except Exception as exc:
                    executed = any(c.get("outputs") or c.get("execution_count")
                                   for c in notebook.cells if c.get("cell_type") == "code")
                    if attempt == 1 and not executed:
                        notes.append(f"the kernel failed to start ({type(exc).__name__}: {exc}); retried once")
                        _reset(notebook, pristine)
                        continue
                    return StepOutcome(
                        status="failed", notebook=notebook, seconds=0.0,
                        error={"cell": None, "ename": type(exc).__name__, "evalue": str(exc), "traceback": ""},
                        stream=stream_text(notebook), notes=notes,
                    )
                outcome.notes = notes + outcome.notes
                return outcome
        raise AssertionError("unreachable")


def _reset(notebook: Any, pristine: dict) -> None:
    import nbformat

    fresh = nbformat.from_dict(pristine)
    notebook.cells = fresh.cells
    notebook.metadata = fresh.metadata
