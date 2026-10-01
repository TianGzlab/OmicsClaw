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


def _ids(path: Path) -> str:
    return path.name


@pytest.mark.parametrize("skill_dir", LIBRARIES, ids=_ids)
def test_the_api_section_matches_the_library(skill_dir):
    assert _apidoc.check(skill_dir) == []


def test_the_template_api_section_matches_its_library():
    if not (TEMPLATE / "_api.py").is_file():
        pytest.skip("the skill template has no _api.py yet")
    assert _apidoc.check(TEMPLATE) == []


def test_every_pilot_skill_has_a_library():
    names = {p.name for p in LIBRARIES}
    assert {"sc-qc", "sc-preprocessing", "sc-clustering", "sc-cell-annotation", "sc-de"} <= names
