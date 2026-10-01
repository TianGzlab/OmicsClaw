"""The recorded fixtures still match the repository they were recorded from."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from omicsclaw.evals import StubResult
from omicsclaw.evals.runner import skill_index

FIXTURES = Path(__file__).resolve().parent / "fixtures"
STUBS = sorted((FIXTURES / "skill_runs").glob("*.json"))
STUB_MODULES = sorted((FIXTURES / "skill_stubs").glob("*.py"))
_ABSOLUTE = re.compile(r"(?<![\w{}])/(?:workspace|root|home|tmp|opt|Users|var|private)/")

CHECK_LINES = {
    "spatial-preprocess": "Preprocessing complete: 200 cells, 3 clusters",
    "sc-clustering": "Running Leiden clustering (resolution=1.00, key=leiden)",
    "bulkrna-de": "DE genes: 100 (up=50, down=50)",
    "genomics-variant-calling": "Variant calling complete: 500 variants (453 SNPs, Ti/Tv=2.10)",
    "proteomics-quantification": "Quantification complete: 99 proteins (lfq)",
    "metabolomics-de": "Differential analysis complete: 0 significant features (FDR<0.05)",
    "literature": "Found 1 GEO datasets: GSE123456",
}
"""A line each recorded run printed; the live eval and the dataset cases look for these."""


def test_every_stub_is_used_by_the_live_eval_or_a_dataset_case():
    """The live eval loads every recorded run as a stub; a dataset case names the ones it uses."""
    live = (Path(__file__).resolve().parent / "live" / "conftest.py").read_text(encoding="utf-8")
    dataset = (Path(__file__).resolve().parent / "dataset" / "test_skill_routing.py").read_text(encoding="utf-8")
    assert 'FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "skill_runs"' in live
    assert '"skill_runs" / "bulkrna-de.json"' in dataset
    assert {path.stem for path in STUBS} == set(CHECK_LINES)


@pytest.mark.parametrize("path", STUB_MODULES, ids=lambda p: p.stem)
def test_a_stub_module_names_only_functions_the_real_library_has(path):
    """A stub module stands in for a skill's ``_api.py``; ``load_skill`` refuses names the library lacks."""
    import ast

    real = skill_index().get(path.stem).directory / "_api.py"
    declared = next(
        ast.literal_eval(node.value)
        for node in ast.parse(real.read_text(encoding="utf-8")).body
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "__all__" for t in node.targets)
    )
    stubbed = [node.name for node in ast.parse(path.read_text(encoding="utf-8")).body
               if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")]
    assert stubbed and set(stubbed) <= set(declared)


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
    for skill, line in CHECK_LINES.items():
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


def test_every_seed_names_its_inputs_and_its_expected_args_exist():
    """``inputs`` is explicit on every seed; each expected argument appears in the skill's ``SKILL.md``.

    A skill with a function library may name it as a keyword argument
    (``method="celltypist"``) instead of a CLI flag.
    """
    seed = json.loads((FIXTURES / "live_routing_seed.json").read_text(encoding="utf-8"))
    index = skill_index()
    assert seed["schema_version"] == 2
    for case in seed["cases"]:
        assert "inputs" in case, case["id"]
        assert bool(case["inputs"]) == (case["decision"] == "route"), case["id"]
        for flag, value in case.get("expected_args", {}).items():
            (name,) = case["expected_skills"]
            text = index.get(name).path.read_text(encoding="utf-8")
            keyword = flag.lstrip("-").replace("-", "_")
            spellings = (f"{flag} {value}", f'{keyword}="{value}"', f"{keyword}='{value}'")
            assert any(s in text for s in spellings), f"{case['id']}: {flag} {value} not in {name}'s SKILL.md"
