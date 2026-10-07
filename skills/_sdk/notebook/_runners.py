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
import shutil
import subprocess
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
    r_session: dict | None = None


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


def rscript_executable() -> str | None:
    """Locate Rscript using the same precedence as skill R methods."""
    from skills._sdk.r_script_runner import _preferred_rscript_executable

    return shutil.which(_preferred_rscript_executable())


def rscript_environment(executable: str, env: Mapping[str, str]) -> dict[str, str]:
    """Select existing R libraries without creating directories in the installation."""
    values = dict(env)
    prefix = Path(executable).absolute().parent.parent
    libraries = prefix / "lib" / "R" / "omicsclaw-library"
    if libraries.is_dir():
        existing = values.get("R_LIBS_USER", "")
        values["R_LIBS_USER"] = os.pathsep.join(filter(None, (str(libraries), existing)))
    python = prefix / "bin" / "python"
    values.setdefault("RETICULATE_PYTHON", str(python) if python.is_file() else sys.executable)
    values.setdefault("PYTHON_BIN", values["RETICULATE_PYTHON"])
    values.setdefault("RETICULATE_USE_MANAGED_VENV", "no")
    return values


class RscriptRunner:
    """Execute percent-format R cells in one isolated Rscript process."""

    def __init__(self, rscript: str | None = None) -> None:
        self.rscript = rscript or rscript_executable()
        self._process: subprocess.Popen | None = None

    def kill(self) -> None:
        """Stop the R process and the children in its process group."""
        process = self._process
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            process.wait()

    def run(self, notebook: Any, *, env: Mapping[str, str], cwd: Path) -> StepOutcome:
        from nbformat import v4

        if not self.rscript:
            raise FileNotFoundError("Rscript is not installed")
        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="omicsclaw-rstep-") as directory:
            scratch = Path(directory)
            for number, cell in enumerate(notebook.cells, start=1):
                if cell.cell_type == "code":
                    (scratch / f"cell_{number:06d}.R").write_text(cell.source, encoding="utf-8")
            command = [self.rscript, "--no-init-file", "--no-save", "--no-restore",
                       str(Path(__file__).with_name("_rdriver.R")), str(scratch)]
            interrupted = False
            try:
                self._process = subprocess.Popen(
                    command, cwd=cwd, env=rscript_environment(self.rscript, env),
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                    start_new_session=True,
                )
                output, _ = self._process.communicate()
                returncode = self._process.returncode
            except KeyboardInterrupt:
                self.kill()
                if self._process is None:
                    raise
                output, _ = self._process.communicate()
                returncode = self._process.returncode
                interrupted = True
            except BaseException:
                self.kill()
                if self._process is not None:
                    self._process.wait()
                raise
            finally:
                self._process = None
            current = None
            preamble = []
            streams: dict[int, list[str]] = {}
            for line in output.splitlines(keepends=True):
                marker = re.fullmatch(r"##omicsclaw-cell (\d+)##\s*", line)
                if marker:
                    current = int(marker.group(1))
                    streams.setdefault(current, [])
                elif current is not None:
                    streams[current].append(line)
                else:
                    preamble.append(line)
            for number, lines in streams.items():
                cell = notebook.cells[number - 1]
                cell.execution_count = list(streams).index(number) + 1
                cell.outputs = [v4.new_output("stream", name="stdout", text="".join(lines))] if lines else []
            error = None
            error_file = scratch / "error.tsv"
            if error_file.exists():
                number, name, message = error_file.read_text().rstrip("\n").split("\t", 2)
                error = {"cell": int(number), "ename": name, "evalue": message, "traceback": ""}
                notebook.cells[int(number) - 1].outputs.append(v4.new_output(
                    "error", ename=name, evalue=message, traceback=[f"{name}: {message}"],
                ))
            elif interrupted:
                error = {"cell": current, "ename": "KeyboardInterrupt",
                         "evalue": "R step interrupted", "traceback": ""}
                if current is not None:
                    notebook.cells[current - 1].outputs.append(v4.new_output(
                        "error", ename=error["ename"], evalue=error["evalue"], traceback=[],
                    ))
            elif returncode:
                error = {"cell": current, "ename": "RscriptError",
                         "evalue": f"Rscript exited with status {returncode}", "traceback": ""}
            session = {"rscript": self.rscript, "r_version": "unknown", "packages": {}}
            session_file = scratch / "session.tsv"
            if session_file.exists():
                for line in session_file.read_text().splitlines():
                    name, version = line.split("\t", 1)
                    if name == "R":
                        session["r_version"] = version
                    else:
                        session["packages"][name] = version
            return StepOutcome(
                status="failed" if error else "ok", notebook=notebook,
                seconds=time.perf_counter() - started, error=error,
                stream="".join(preamble) + stream_text(notebook), r_session=session,
            )
