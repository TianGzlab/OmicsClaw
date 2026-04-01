"""Subprocess-based R script execution with file exchange.

Provides process-isolated R execution — R crashes never bring down Python.
Data is exchanged via CSV/h5ad files on the shared filesystem.

Modeled after the Biomni timeax_r_wrapper.py and glmGamPoi patterns.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default location for OmicsClaw R scripts
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "r_scripts"


class RScriptError(Exception):
    """An R subprocess call failed."""

    def __init__(
        self,
        script: str,
        returncode: int,
        stdout: str = "",
        stderr: str = "",
    ):
        self.script = script
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        # Show last 500 chars of stderr for readability
        stderr_tail = stderr[-500:] if stderr else "(empty)"
        super().__init__(
            f"R script '{script}' failed (exit code {returncode}).\n"
            f"stderr: {stderr_tail}"
        )


class RScriptTimeoutError(RScriptError):
    """R subprocess exceeded its timeout."""

    def __init__(self, script: str, timeout: int):
        super().__init__(
            script=script,
            returncode=-1,
            stderr=f"Timed out after {timeout}s",
        )
        self.timeout = timeout


@dataclass
class RScriptResult:
    """Result of an R script execution."""

    returncode: int
    stdout: str
    stderr: str
    output_dir: Optional[Path] = None
    elapsed_seconds: float = 0.0
    skipped: bool = False

    @property
    def success(self) -> bool:
        return self.returncode == 0 or self.skipped


class RScriptRunner:
    """Execute R scripts via subprocess with file exchange.

    Parameters
    ----------
    scripts_dir : Path, optional
        Directory containing R scripts.  Defaults to ``omicsclaw/r_scripts/``.
    timeout : int
        Default timeout in seconds for each R call.
    r_executable : str
        Name or path of the Rscript binary.
    verbose : bool
        Print R stdout/stderr lines as they arrive.
    """

    def __init__(
        self,
        scripts_dir: Path | None = None,
        timeout: int = 600,
        r_executable: str = "Rscript",
        verbose: bool = True,
    ):
        self.scripts_dir = Path(scripts_dir) if scripts_dir else _SCRIPTS_DIR
        self.timeout = timeout
        self.r_executable = r_executable
        self.verbose = verbose

    # ------------------------------------------------------------------
    # Environment checks
    # ------------------------------------------------------------------

    def check_r_available(self) -> bool:
        """Return True if Rscript is found on PATH."""
        try:
            result = subprocess.run(
                [self.r_executable, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                env=self._build_r_env(),
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def check_r_packages(self, packages: list[str]) -> dict[str, bool]:
        """Check which R packages are installed.

        Returns a dict mapping package name → bool (installed or not).
        """
        status: dict[str, bool] = {}
        if not packages:
            return status

        # Build a single R expression that checks all packages
        checks = "; ".join(
            f'cat("{pkg}:", requireNamespace("{pkg}", quietly=TRUE), "\\n")'
            for pkg in packages
        )

        try:
            result = subprocess.run(
                [self.r_executable, "-e", checks],
                capture_output=True,
                text=True,
                timeout=30,
                env=self._build_r_env(),
            )
            for line in result.stdout.strip().splitlines():
                line = line.strip()
                if ":" in line:
                    parts = line.split(":", 1)
                    pkg = parts[0].strip()
                    val = parts[1].strip().upper()
                    status[pkg] = val == "TRUE"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # R not available — mark all as missing
            for pkg in packages:
                status[pkg] = False

        # Fill in any packages not reported
        for pkg in packages:
            if pkg not in status:
                status[pkg] = False

        return status

    def get_missing_packages(self, packages: list[str]) -> list[str]:
        """Return the subset of *packages* that are not installed in R."""
        status = self.check_r_packages(packages)
        return [pkg for pkg, ok in status.items() if not ok]

    # ------------------------------------------------------------------
    # Script execution
    # ------------------------------------------------------------------

    def run_script(
        self,
        script: str | Path,
        args: list[str] | None = None,
        *,
        expected_outputs: list[str] | None = None,
        output_dir: Path | None = None,
        timeout: int | None = None,
        skip_if_exists: bool = False,
        env: dict[str, str] | None = None,
    ) -> RScriptResult:
        """Execute an R script via subprocess.

        Parameters
        ----------
        script : str or Path
            Script filename (resolved relative to *scripts_dir*) or absolute path.
        args : list[str]
            Command-line arguments passed to the R script.
        expected_outputs : list[str]
            Filenames expected in *output_dir* after the script completes.
            A ``FileNotFoundError`` is raised if any are missing.
        output_dir : Path, optional
            Directory where R writes its output files.  Only used for
            the *skip_if_exists* and *expected_outputs* checks.
        timeout : int, optional
            Override the default timeout for this call.
        skip_if_exists : bool
            If True and all *expected_outputs* already exist in *output_dir*,
            skip execution and return immediately.
        env : dict, optional
            Extra environment variables for the subprocess.

        Returns
        -------
        RScriptResult
        """
        script_path = self._resolve_script(script)
        timeout = timeout or self.timeout

        # Idempotency: skip if all expected outputs already exist
        if skip_if_exists and expected_outputs and output_dir:
            if all((Path(output_dir) / f).exists() for f in expected_outputs):
                logger.info("Skipping R script %s — outputs already exist", script_path.name)
                return RScriptResult(
                    returncode=0,
                    stdout="",
                    stderr="",
                    output_dir=Path(output_dir),
                    skipped=True,
                )

        cmd = [self.r_executable, str(script_path)] + [str(a) for a in (args or [])]

        if self.verbose:
            logger.info("Running: %s", " ".join(cmd))

        run_env = self._build_r_env()
        if env:
            run_env.update(env)

        t0 = time.time()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=run_env,
            )
        except subprocess.TimeoutExpired:
            raise RScriptTimeoutError(str(script_path), timeout)
        except FileNotFoundError:
            raise RScriptError(
                str(script_path),
                returncode=-1,
                stderr=f"Rscript binary not found: {self.r_executable}",
            )
        elapsed = time.time() - t0

        # Log R output
        if self.verbose and proc.stdout:
            for line in proc.stdout.strip().splitlines():
                logger.info("  [R] %s", line)
        if proc.stderr:
            for line in proc.stderr.strip().splitlines():
                line_s = line.strip()
                if line_s and not line_s.startswith("Loading required"):
                    logger.warning("  [R warn] %s", line_s)

        # Check return code
        if proc.returncode != 0:
            # Save debug log if output_dir is available
            if output_dir:
                self._save_debug_log(
                    Path(output_dir), script_path, args or [], proc.stdout, proc.stderr
                )
            raise RScriptError(
                str(script_path),
                proc.returncode,
                proc.stdout,
                proc.stderr,
            )

        # Validate expected output files
        if expected_outputs and output_dir:
            missing = [
                f for f in expected_outputs if not (Path(output_dir) / f).exists()
            ]
            if missing:
                raise FileNotFoundError(
                    f"R script '{script_path.name}' succeeded but output files missing: "
                    f"{missing}\nR stdout (last 300 chars): {proc.stdout[-300:]}"
                )

        return RScriptResult(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            output_dir=Path(output_dir) if output_dir else None,
            elapsed_seconds=elapsed,
        )

    def _build_r_env(self) -> dict[str, str]:
        """Build a subprocess environment that stays inside the active conda env.

        This keeps reticulate/zellkonverter from silently pulling a managed Python
        runtime that differs from the current OmicsClaw environment.
        """
        env = os.environ.copy()
        conda_prefix = env.get("CONDA_PREFIX")

        python_candidates: list[str] = []
        if conda_prefix:
            python_candidates.append(str(Path(conda_prefix) / "bin" / "python"))
        python_candidates.append(sys.executable)

        for candidate in python_candidates:
            if candidate and Path(candidate).exists():
                env.setdefault("RETICULATE_PYTHON", candidate)
                env.setdefault("PYTHON_BIN", candidate)
                break

        if conda_prefix:
            r_libs_user = Path(conda_prefix) / "lib" / "R" / "omicsclaw-library"
            r_libs_user.mkdir(parents=True, exist_ok=True)
            env.setdefault("OMICSCLAW_R_LIBS", str(r_libs_user))
            env.setdefault("R_LIBS_USER", str(r_libs_user))

        # Disable reticulate's managed ephemeral Python selection when possible.
        env.setdefault("RETICULATE_USE_MANAGED_VENV", "no")
        return env

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_script(self, script: str | Path) -> Path:
        """Resolve a script name to an absolute path."""
        p = Path(script)
        if p.is_absolute() and p.exists():
            return p
        # Try relative to scripts_dir
        candidate = self.scripts_dir / p
        if candidate.exists():
            return candidate
        raise FileNotFoundError(
            f"R script not found: {script} (searched {self.scripts_dir})"
        )

    @staticmethod
    def _save_debug_log(
        output_dir: Path,
        script_path: Path,
        args: list[str],
        stdout: str,
        stderr: str,
    ) -> None:
        """Write a debug log on R failure for post-mortem analysis."""
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            log_path = output_dir / "r_debug.log"
            with open(log_path, "w") as f:
                f.write(f"Script: {script_path}\n")
                f.write(f"Args: {args}\n")
                f.write(f"\n=== STDOUT ===\n{stdout}\n")
                f.write(f"\n=== STDERR ===\n{stderr}\n")
            logger.info("R debug log saved to %s", log_path)
        except Exception:
            pass  # Best-effort — don't fail the error path
