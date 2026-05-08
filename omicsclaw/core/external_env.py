"""Cross-environment subprocess helpers.

OmicsClaw runs the bulk of its skills inside the primary conda env
(`OmicsClaw`). Some tools have hard dependency conflicts with the primary
env (e.g. pybanksy requires numpy<2.0 while scvi-tools requires numpy>=2.0).
For those, we maintain dedicated sub-envs named `omicsclaw_<tool>` and
shell out via `mamba run -n omicsclaw_<tool> python ...`.

This module provides three call shapes:
  - run_python_in_env(env, code)             # one-shot eval
  - run_script_in_env(env, script, args)     # IO-bearing script
  - run_anndata_op_in_env(env, runner, adata, params)
                                             # AnnData bridge via .h5ad
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Sequence

DEFAULT_TIMEOUT_SECONDS: float = 1800.0  # 30 min — banksy on a large slide
                                          # can take many minutes; longer than
                                          # this almost always means a hang.

__all__ = [
    "EnvNotFoundError",
    "is_env_available",
    "run_python_in_env",
    "run_script_in_env",
    "run_anndata_op_in_env",
]


class EnvNotFoundError(RuntimeError):
    """Raised when the requested conda env is not registered."""


def _runner() -> str:
    if shutil.which("mamba"):
        return "mamba"
    if shutil.which("conda"):
        return "conda"
    raise RuntimeError("neither mamba nor conda is on PATH")


def _available_runners() -> list[str]:
    """Return conda-compatible runners in preferred order."""
    runners: list[str] = []
    if shutil.which("mamba"):
        runners.append("mamba")
    if shutil.which("conda"):
        runners.append("conda")
    if not runners:
        raise RuntimeError("neither mamba nor conda is on PATH")
    return runners


def _env_list_lines() -> list[str]:
    """Return lines from the first working env-list command."""
    for runner in _available_runners():
        res = subprocess.run(
            [runner, "env", "list"], capture_output=True, text=True, check=False
        )
        if res.returncode == 0:
            return res.stdout.splitlines()
    return []


def is_env_available(env: str) -> bool:
    """Return True if a conda env named `env` exists."""
    for line in _env_list_lines():
        if line.strip().startswith("#") or not line.strip():
            continue
        first = line.split()[0]
        if first == env:
            return True
    return False


def run_python_in_env(env: str, code: str, *, timeout: float | None = None) -> str:
    """Run a Python one-liner in another conda env, return stdout.

    Args:
        env: conda environment name.
        code: Python source to evaluate.
        timeout: seconds before the subprocess is killed.  If None, defaults
            to DEFAULT_TIMEOUT_SECONDS (30 min).

    Raises:
        EnvNotFoundError: if `env` does not exist.
        subprocess.CalledProcessError: if the subprocess exits non-zero.
            The exception's ``stderr`` attribute contains the captured output.
    """
    if not is_env_available(env):
        raise EnvNotFoundError(f"conda env not found: {env!r}")
    runner = _runner()
    cmd = [runner, "run", "-n", env, "--no-capture-output", "python", "-c", code]
    effective_timeout = DEFAULT_TIMEOUT_SECONDS if timeout is None else timeout
    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=effective_timeout
        )
    except subprocess.CalledProcessError as exc:
        stderr_tail = (exc.stderr or "").rstrip()
        raise subprocess.CalledProcessError(
            exc.returncode,
            exc.cmd,
            output=exc.stdout,
            stderr=(
                f"sub-env subprocess failed (env={env}, exit={exc.returncode}):\n"
                f"--- stderr ---\n{stderr_tail}"
            ),
        ) from exc
    return res.stdout


def run_script_in_env(
    env: str,
    script: str | Path,
    args: Sequence[str] = (),
    *,
    timeout: float | None = None,
) -> str:
    """Run a Python script in another env. `script` must be readable from both envs.

    Args:
        env: conda environment name.
        script: path to the Python script.
        args: extra CLI arguments forwarded to the script.
        timeout: seconds before the subprocess is killed.  If None, defaults
            to DEFAULT_TIMEOUT_SECONDS (30 min).

    Raises:
        EnvNotFoundError: if `env` does not exist.
        subprocess.CalledProcessError: if the subprocess exits non-zero.
            The exception's ``stderr`` attribute contains the captured output.
    """
    if not is_env_available(env):
        raise EnvNotFoundError(f"conda env not found: {env!r}")
    runner = _runner()
    cmd = [runner, "run", "-n", env, "--no-capture-output", "python", str(script), *args]
    effective_timeout = DEFAULT_TIMEOUT_SECONDS if timeout is None else timeout
    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=effective_timeout
        )
    except subprocess.CalledProcessError as exc:
        stderr_tail = (exc.stderr or "").rstrip()
        raise subprocess.CalledProcessError(
            exc.returncode,
            exc.cmd,
            output=exc.stdout,
            stderr=(
                f"sub-env subprocess failed (env={env}, exit={exc.returncode}):\n"
                f"--- stderr ---\n{stderr_tail}"
            ),
        ) from exc
    return res.stdout


def run_anndata_op_in_env(
    env: str,
    runner_script: str | Path,
    adata: "Any",  # AnnData; not imported here to keep this module dep-light
    params: dict | None = None,
    *,
    timeout: float | None = None,
) -> "Any":
    """Bridge an AnnData object into a sub-env, run a script, get AnnData back.

    The `runner_script` is invoked in `env` with two args:
        --input <tmp_in.h5ad>  --output <tmp_out.h5ad>
    plus `--params <json>` if `params` is non-empty. The script is responsible
    for loading the input, doing its work, and writing the output.

    Args:
        env: conda environment name.
        runner_script: path to a script that accepts --input/--output/--params.
        adata: AnnData object to pass through the bridge.
        params: JSON-serialisable dict forwarded as ``--params``.
        timeout: seconds before the subprocess is killed.  If None, defaults
            to DEFAULT_TIMEOUT_SECONDS (30 min).
    """
    import anndata  # local import — main env has anndata, sub-env may not yet

    if not is_env_available(env):
        raise EnvNotFoundError(f"conda env not found: {env!r}")

    with tempfile.TemporaryDirectory(prefix="omicsclaw_xenv_") as tmp:
        tmp_in = Path(tmp) / "in.h5ad"
        tmp_out = Path(tmp) / "out.h5ad"
        adata.write_h5ad(tmp_in, compression="gzip")

        args = ["--input", str(tmp_in), "--output", str(tmp_out)]
        if params:
            args.extend(["--params", json.dumps(params)])

        run_script_in_env(env, runner_script, args, timeout=timeout)

        if not tmp_out.exists():
            raise RuntimeError(
                f"sub-env runner did not write output: {runner_script} in {env}"
            )
        return anndata.read_h5ad(tmp_out)
