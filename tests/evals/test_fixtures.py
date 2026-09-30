"""The recorded fixtures still match the repository they were recorded from."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from omicsclaw.evals import StubResult
from omicsclaw.evals.runner import skill_index
from tests.evals.dataset.test_skill_routing import ROUTES

FIXTURES = Path(__file__).resolve().parent / "fixtures"
STUBS = sorted((FIXTURES / "skill_runs").glob("*.json"))
_ABSOLUTE = re.compile(r"(?<![\w{}])/(?:workspace|root|home|tmp|opt|Users|var|private)/")


def test_there_is_a_stub_for_every_routing_case():
    assert {path.stem for path in STUBS} == {route[1] for route in ROUTES}


@pytest.mark.parametrize("path", STUBS, ids=lambda p: p.stem)
def test_a_stub_names_a_skill_that_still_exists(path):
    stub = StubResult.load(path)
    assert stub.provenance["skill"] == path.stem
    assert skill_index().get(stub.provenance["skill"]) is not None


@pytest.mark.parametrize("path", STUBS, ids=lambda p: p.stem)
def test_a_stub_carries_no_machine_paths(path):
    text = path.read_text(encoding="utf-8")
    assert not _ABSOLUTE.findall(text), _ABSOLUTE.findall(text)[:5]
    assert str(Path(__file__).resolve().parents[2]) not in text


def test_every_check_line_is_in_its_fixture():
    for _, skill, _, _, _, line in ROUTES:
        assert line in StubResult.load(FIXTURES / "skill_runs" / f"{skill}.json").stdout, skill


def test_the_routing_seed_names_skills_that_still_exist():
    seed = json.loads((FIXTURES / "live_routing_seed.json").read_text(encoding="utf-8"))
    index = skill_index()
    assert len(seed["cases"]) == 26
    for case in seed["cases"]:
        if not case["expected_skills"]:
            assert case["decision"] == "no_skill", case["id"]
            continue
        for name in case["expected_skills"]:
            assert index.get(name) is not None, f"{case['id']}: {name}"
