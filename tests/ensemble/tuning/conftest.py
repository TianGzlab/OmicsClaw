from __future__ import annotations

from pathlib import Path

import pytest

from omicsclaw.ensemble.space import TuningCatalog
from omicsclaw.skills import load_skills

REPO = Path(__file__).resolve().parents[3]
FAKE_SKILLS = REPO / "tests" / "ensemble" / "fake_skills"


@pytest.fixture(scope="session")
def domains_spec():
    return TuningCatalog.from_skills(load_skills(REPO / "skills")).get("spatial-domains")


@pytest.fixture(scope="session")
def fake_spec():
    return TuningCatalog.from_skills(load_skills(FAKE_SKILLS)).get("fake-domains")
