"""``tests/ci_known_failures.txt`` names tests that exist, each with a reason."""

from __future__ import annotations

import ast
from pathlib import Path

from tests.conftest import KNOWN_FAILURES_FILE, load_known_failures

ROOT = Path(__file__).resolve().parents[2]


def _functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_every_entry_names_an_existing_test_and_gives_a_reason():
    entries = load_known_failures()
    assert entries
    for node, (reason, _) in entries.items():
        path, _, name = node.partition("::")
        assert (ROOT / path).is_file(), node
        assert name.split("[", 1)[0] in _functions(ROOT / path), node
        assert reason and reason != "known failure", node


def test_env_entries_are_non_strict(tmp_path):
    listing = tmp_path / "known.txt"
    listing.write_text("# comment\n\na::b | why\nc::d | why too | env\n", encoding="utf-8")
    assert load_known_failures(listing) == {"a::b": ("why", True), "c::d": ("why too", False)}
    assert KNOWN_FAILURES_FILE.name == "ci_known_failures.txt"
