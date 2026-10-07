"""FastQC receives the input path before changing working directory."""

from pathlib import Path
import sys

from skills.singlecell._lib.upstream import run_fastqc


def test_fastqc_resolves_relative_inputs_before_entering_artifacts(tmp_path, monkeypatch):
    tools = tmp_path / "tools"
    tools.mkdir()
    executable = tools / "fastqc"
    executable.write_text(
        f"#!{sys.executable}\nimport pathlib, sys\n"
        "source = pathlib.Path(sys.argv[-1])\n"
        "assert source.is_absolute() and source.is_file(), str(source)\n"
        "print(source.read_text())\n"
    )
    executable.chmod(0o755)
    source = tmp_path / "reads.fastq"
    source.write_text("@read\nAC\n+\nII\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", str(tools))
    result = run_fastqc([Path("reads.fastq")], "artifacts/fastqc")
    assert result.returncode == 0 and "@read" in result.stdout
    assert result.command[-1] == str(source)
