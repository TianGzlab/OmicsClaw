"""The seed set can grow but not shrink, and every case is well formed.

``BASELINE`` is raised when cases are added. Deleting a case makes this
fail, so a case cannot disappear from the PR gate unnoticed.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from collections import Counter
from pathlib import Path

BASELINE = 26
CATEGORIES = {
    "tool_calling",
    "planning",
    "context",
    "error_handling",
    "memory",
    "compaction",
    "skill_routing",
    "safety",
}
DATASET = Path(__file__).resolve().parent / "dataset"


def _all_cases():
    cases = []
    for path in sorted(DATASET.glob("test_*.py")):
        module = importlib.import_module(f"tests.evals.dataset.{path.stem}")
        cases.extend(module.CASES)
    return cases


def test_there_are_at_least_baseline_cases():
    assert len(_all_cases()) >= BASELINE


def test_case_ids_are_unique():
    counts = Counter(case.id for case in _all_cases())
    assert not [case_id for case_id, n in counts.items() if n > 1]


def test_every_category_is_known_matches_its_id_and_has_a_case():
    cases = _all_cases()
    for case in cases:
        assert case.category in CATEGORIES, case.id
        assert case.id.split("/", 1)[0] == case.category
    assert {case.category for case in cases} == CATEGORIES


def test_each_category_file_holds_only_its_category():
    for path in sorted(DATASET.glob("test_*.py")):
        module = importlib.import_module(f"tests.evals.dataset.{path.stem}")
        assert {case.category for case in module.CASES} == {path.stem.removeprefix("test_")}


def _collect(marker: str) -> str:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--co", "-q", "-p", "no:randomly", "-p", "no:cacheprovider",
         str(DATASET), "-m", marker],
        capture_output=True,
        text=True,
        cwd=DATASET.parents[2],
    )
    return completed.stdout


def test_every_dataset_item_is_marked_scripted_eval():
    """The dataset conftest marks items by path; check the marker really lands.

    Collected in a subprocess so the ``-m`` filtering runs exactly as it
    does in CI, after the conftest hook has added the marker.
    """
    total = len(_all_cases())
    assert f"{total} deselected / 0 selected" in _collect("not scripted_eval")
    assert f"{total} tests collected" in _collect("scripted_eval")
