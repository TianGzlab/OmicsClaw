from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "literature" / "literature_parse.py"


def test_literature_demo_writes_standard_outputs(tmp_path):
    output_dir = tmp_path / "literature-demo"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--demo",
            "--output",
            str(output_dir),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert (output_dir / "report.md").exists()
    assert (output_dir / "extracted_metadata.json").exists()
    assert (output_dir / "result.json").exists()

    metadata = json.loads((output_dir / "extracted_metadata.json").read_text(encoding="utf-8"))
    assert metadata["geo_accessions"]["gse"]

    payload = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
    assert payload["skill"] == "literature"
    assert payload["success"] is True
