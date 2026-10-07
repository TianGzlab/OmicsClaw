"""Run the public demo and help entrypoints for each genomic skill."""
from pathlib import Path
import json
import subprocess
import sys
import pytest

pytestmark = pytest.mark.cli_subprocess
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = sorted(path for path in ROOT.glob("genomics-*/*.py") if not path.name.startswith("_"))


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda path: path.parent.name)
def test_demo_and_help_remain_usable(script, tmp_path):
    help_result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True, timeout=30)
    assert help_result.returncode == 0, help_result.stderr
    result = subprocess.run([sys.executable, str(script), "--demo", "--output", str(tmp_path)],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert json.loads((tmp_path / "result.json").read_text())["summary"]
    assert list((tmp_path / "tables").glob("*.csv"))
    assert (tmp_path / "report.md").is_file()
