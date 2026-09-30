"""Tests for the subprocess-based R script runner and utilities."""

import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from skills._sdk.r_script_runner import (
    RScriptError,
    RScriptRunner,
    RScriptTimeoutError,
)
from skills._sdk.r_utils import (
    csv_to_dataframe,
    dataframe_to_csv,
    read_r_result_csv,
)

# All tests that invoke Rscript require R to be installed
pytestmark = pytest.mark.requires_r


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner():
    return RScriptRunner(verbose=False)


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory(prefix="omicsclaw_test_") as d:
        yield Path(d)


# ---------------------------------------------------------------------------
# RScriptRunner — environment checks
# ---------------------------------------------------------------------------


class TestREnvironment:
    def test_check_r_available(self, runner):
        """Rscript should be found on PATH in test environment."""
        assert runner.check_r_available() is True

    def test_check_r_packages_base(self, runner):
        """Base R packages like 'stats' should always be available."""
        status = runner.check_r_packages(["stats", "utils"])
        assert status["stats"] is True
        assert status["utils"] is True

    def test_check_r_packages_missing(self, runner):
        """A nonsense package name should be reported as missing."""
        status = runner.check_r_packages(["nonexistent_pkg_12345"])
        assert status["nonexistent_pkg_12345"] is False

    def test_get_missing_packages(self, runner):
        missing = runner.get_missing_packages(["stats", "nonexistent_pkg_12345"])
        assert "nonexistent_pkg_12345" in missing
        assert "stats" not in missing


# ---------------------------------------------------------------------------
# RScriptRunner — script execution
# ---------------------------------------------------------------------------


class TestRunScript:
    def test_run_trivial_script(self, runner, tmp_dir):
        """Execute a trivial R script that writes a file."""
        script = tmp_dir / "hello.R"
        script.write_text(
            'args <- commandArgs(trailingOnly = TRUE)\n'
            'output_dir <- args[1]\n'
            'write.csv(data.frame(x = 1:3, y = c("a","b","c")), '
            'file.path(output_dir, "result.csv"), row.names = FALSE)\n'
            'cat("done\\n")\n'
        )
        out_dir = tmp_dir / "output"
        out_dir.mkdir()

        result = runner.run_script(
            script,
            args=[str(out_dir)],
            expected_outputs=["result.csv"],
            output_dir=out_dir,
        )

        assert result.success
        assert result.returncode == 0
        assert (out_dir / "result.csv").exists()

        df = pd.read_csv(out_dir / "result.csv")
        assert list(df.columns) == ["x", "y"]
        assert len(df) == 3

    def test_run_script_error(self, runner, tmp_dir):
        """A failing R script should raise RScriptError."""
        script = tmp_dir / "fail.R"
        script.write_text('stop("intentional failure")\n')

        with pytest.raises(RScriptError) as exc_info:
            runner.run_script(script)

        assert exc_info.value.returncode != 0
        assert "intentional failure" in exc_info.value.stderr

    def test_run_script_timeout(self, runner, tmp_dir):
        """A long-running R script should raise RScriptTimeoutError."""
        script = tmp_dir / "slow.R"
        script.write_text("Sys.sleep(60)\n")

        with pytest.raises(RScriptTimeoutError):
            runner.run_script(script, timeout=1)

    def test_run_script_missing_output(self, runner, tmp_dir):
        """If expected output files are missing, raise FileNotFoundError."""
        script = tmp_dir / "noop.R"
        script.write_text('cat("ok\\n")\n')
        out_dir = tmp_dir / "output"
        out_dir.mkdir()

        with pytest.raises(FileNotFoundError, match="output files missing"):
            runner.run_script(
                script,
                expected_outputs=["does_not_exist.csv"],
                output_dir=out_dir,
            )

    def test_skip_if_exists(self, runner, tmp_dir):
        """If all expected outputs exist, the script should be skipped."""
        out_dir = tmp_dir / "output"
        out_dir.mkdir()
        (out_dir / "result.csv").write_text("x\n1\n")

        # This script would fail if actually run
        script = tmp_dir / "would_fail.R"
        script.write_text('stop("should not run")\n')

        result = runner.run_script(
            script,
            expected_outputs=["result.csv"],
            output_dir=out_dir,
            skip_if_exists=True,
        )

        assert result.success
        assert result.skipped

    def test_script_not_found(self, runner):
        """A missing script path should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="R script not found"):
            runner.run_script("/nonexistent/path/to/script.R")

    def test_debug_log_on_failure(self, runner, tmp_dir):
        """On failure, a debug log should be written to output_dir."""
        script = tmp_dir / "fail.R"
        script.write_text('cat("some output\\n")\nstop("debug me")\n')
        out_dir = tmp_dir / "output"
        out_dir.mkdir()

        with pytest.raises(RScriptError):
            runner.run_script(script, output_dir=out_dir)

        log_path = out_dir / "r_debug.log"
        assert log_path.exists()
        content = log_path.read_text()
        assert "fail.R" in content
        assert "STDERR" in content


# ---------------------------------------------------------------------------
# check_packages.R integration
# ---------------------------------------------------------------------------


class TestCheckPackagesScript:
    def test_check_packages_r_script(self, runner, tmp_dir):
        """The check_packages.R utility script should output valid JSON."""
        import json

        result = runner.run_script(
            "check_packages.R",
            args=["stats", "nonexistent_pkg_999"],
        )
        assert result.success

        data = json.loads(result.stdout.strip())
        assert data["stats"] is True
        assert data["nonexistent_pkg_999"] is False


# ---------------------------------------------------------------------------
# r_utils — CSV helpers
# ---------------------------------------------------------------------------


class TestRUtils:
    def test_dataframe_round_trip(self, tmp_dir):
        """Write and read a DataFrame preserving index."""
        df = pd.DataFrame(
            {"gene": ["TP53", "BRCA1"], "log2fc": [1.5, -2.3]},
            index=["g1", "g2"],
        )
        path = dataframe_to_csv(df, tmp_dir / "test.csv")
        assert path.exists()

        result = csv_to_dataframe(path)
        assert list(result.index) == ["g1", "g2"]
        assert list(result.columns) == ["gene", "log2fc"]
        assert result.loc["g1", "log2fc"] == pytest.approx(1.5)

    def test_read_r_result_csv(self, tmp_dir):
        """read_r_result_csv should handle typical R output."""
        csv_content = '"","gene","pvalue","padj"\n"1","TP53",0.001,0.01\n"2","BRCA1",0.05,0.1\n'
        path = tmp_dir / "r_output.csv"
        path.write_text(csv_content)

        df = read_r_result_csv(path)
        assert len(df) == 2
        assert "gene" in df.columns


# ---------------------------------------------------------------------------
# validate_r_environment (subprocess-based)
# ---------------------------------------------------------------------------


class TestValidateREnvironment:
    def test_validate_basic(self):
        """validate_r_environment should succeed with no package requirements."""
        from skills._sdk.deps import validate_r_environment

        assert validate_r_environment() is True

    def test_validate_with_base_packages(self):
        """Should pass when requiring base R packages."""
        from skills._sdk.deps import validate_r_environment

        assert validate_r_environment(required_r_packages=["stats"]) is True

    def test_validate_missing_package(self):
        """Should raise ImportError for nonexistent R packages."""
        from skills._sdk.deps import validate_r_environment

        with pytest.raises(ImportError, match="Missing R packages"):
            validate_r_environment(required_r_packages=["nonexistent_pkg_99999"])
