"""The generated ``## API`` section: rendering, checking and rewriting."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from skills._sdk.notebook import _apidoc

RUN = Path(__file__).resolve().parents[3] / "skills" / "_sdk" / "notebook" / "run.py"

API = textwrap.dedent('''
    """Toy library."""

    from __future__ import annotations

    __all__ = ["cluster", "summary"]


    def cluster(adata, *, resolution: float = 1.0, method: str = "leiden", key_added: str | None = None) -> "AnnData":
        """Cluster the cells.

        :param resolution: Leiden resolution; scanpy's default.
            Raise it for finer clusters.
        :returns: The same AnnData.
        """
        return adata


    def summary(adata, *, key="leiden"):
        """Count cells per cluster."""
        return {}


    def _private():
        return None
''')


@pytest.fixture
def skill(tmp_path):
    folder = tmp_path / "sc-toy"
    folder.mkdir()
    (folder / "_api.py").write_text(API)
    (folder / "SKILL.md").write_text("# sc-toy\n\n## API\n\n## Methods and parameters\n\nText.\n")
    return folder


def test_the_signature_is_rendered_as_written(skill):
    text = _apidoc.render(skill / "_api.py")
    assert (
        "### `cluster(adata, *, resolution: float=1.0, method: str='leiden', key_added: str | None=None) -> 'AnnData'`"
        in text
    )
    assert "### `summary(adata, *, key='leiden')`" in text
    assert text.index("cluster(") < text.index("summary(")
    assert "_private" not in text


def test_the_docstring_is_kept_verbatim_and_dedented(skill):
    text = _apidoc.render(skill / "_api.py")
    assert ":param resolution: Leiden resolution; scanpy's default.\n    Raise it for finer clusters.\n:returns: The same AnnData." in text


def test_write_inserts_the_section_after_the_heading_and_check_passes(skill):
    assert _apidoc.check(skill) != []
    assert _apidoc.write(skill) is True
    text = (skill / "SKILL.md").read_text()
    assert text.index("## API") < text.index(_apidoc.BEGIN) < text.index(_apidoc.END) < text.index("## Methods")
    assert _apidoc.check(skill) == []
    assert _apidoc.write(skill) is False


def test_check_finds_a_changed_default(skill):
    _apidoc.write(skill)
    path = skill / "SKILL.md"
    path.write_text(path.read_text().replace("resolution: float=1.0", "resolution: float=0.8"))
    assert any("differs from _api.py" in p for p in _apidoc.check(skill))


def test_check_wants_documented_functions_in_all(skill):
    api = skill / "_api.py"
    api.write_text(api.read_text().replace('"""Count cells per cluster."""\n', "").replace(
        '__all__ = ["cluster", "summary"]', '__all__ = ["cluster", "summary", "CONSTANT"]\nCONSTANT = 1'))
    problems = _apidoc.check(skill)
    assert "summary has no docstring" in problems
    assert "CONSTANT is in __all__ but is not a top-level function" in problems


def test_two_sections_are_an_error(skill):
    _apidoc.write(skill)
    path = skill / "SKILL.md"
    path.write_text(path.read_text() + "\n" + _apidoc.render(skill / "_api.py") + "\n")
    assert any("expected one API section" in p for p in _apidoc.check(skill))


def test_the_api_subcommand_checks_and_writes(skill):
    def api(*flags):
        return subprocess.run([sys.executable, str(RUN), "api", str(skill), *flags], capture_output=True, text=True)

    assert api("--check").returncode == 1
    assert api("--write").returncode == 0
    checked = api("--check")
    assert checked.returncode == 0 and "matches _api.py" in checked.stdout
