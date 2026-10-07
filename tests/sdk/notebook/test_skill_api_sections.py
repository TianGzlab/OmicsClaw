"""Every function library's ``## API`` section in SKILL.md matches its ``_api.py``.

Rendering and checking use ``ast`` only, so this runs without the libraries'
own dependencies.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skills._sdk.notebook import _apidoc

REPO = Path(__file__).resolve().parents[3]

LIBRARIES = sorted(
    p.parent for p in (REPO / "skills").rglob("_api.py")
    if "__pycache__" not in p.parts and (p.parent / "SKILL.md").is_file()
)
TEMPLATE = REPO / "templates" / "skill"

CLI_ONLY = {
    "sc-count": "Runs external counting tools against reference indexes; steps use run_cli.",
    "sc-velocity-prep": "Runs external BAM/FASTQ tools to build spliced layers; steps use run_cli.",
    "sc-fastq-qc": "Samples FASTQ files and runs optional FastQC/MultiQC; steps use run_cli.",
}


def _ids(path: Path) -> str:
    return path.name


@pytest.mark.parametrize("skill_dir", LIBRARIES, ids=_ids)
def test_the_api_section_matches_the_library(skill_dir):
    assert _apidoc.check(skill_dir) == []


def test_the_template_api_section_matches_its_library():
    if not (TEMPLATE / "_api.py").is_file():
        pytest.skip("the skill template has no _api.py yet")
    assert _apidoc.check(TEMPLATE) == []


def test_every_singlecell_skill_has_a_library_or_an_explicit_disposition():
    directories = {p.parent.name: p.parent for p in (REPO / "skills" / "singlecell").rglob("SKILL.md")}
    libraries = {name for name, path in directories.items() if (path / "_api.py").is_file()}
    cli_only = set(CLI_ONLY)
    assert not libraries & cli_only
    assert set(directories) == libraries | cli_only
    assert all(reason.strip() for reason in CLI_ONLY.values())
