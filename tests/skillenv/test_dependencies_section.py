"""The package-name line of every ``## Dependencies`` section (plan 0061 case 5).

The section's prose may change freely; the contract is that it holds exactly
one line of back-quoted, comma-separated PyPI-style names. That line is what
the environment check reads, and the character set is also the input check
before any name reaches a shell command. The tests below pin the number of
indexed skills and distinct dependency names.
"""

from __future__ import annotations

import pytest

from omicsclaw.skillenv.registry import DependencyFormatError, parse_dependencies

from .conftest import REPO

SKILL_FILES = sorted((REPO / "skills").rglob("SKILL.md"))

_HEAD = "# x\n\nSome text.\n\n## Dependencies\n\n"
_PROSE = "Python packages this skill's script needs.\n\n"


def test_there_are_88_skill_files():
    assert len(SKILL_FILES) == 88


@pytest.mark.parametrize("path", SKILL_FILES, ids=lambda p: p.parent.name)
def test_every_package_line_parses(path):
    names = parse_dependencies(path.read_text(encoding="utf-8"), source=path)
    assert names and len(set(names)) == len(names)


def test_the_declared_names_number_68():
    names = {
        name
        for path in SKILL_FILES
        for name in parse_dependencies(path.read_text(encoding="utf-8"), source=path)
    }
    # Spatial preprocessing adds scikit-misc and umap-learn to the 0074 declarations.
    assert len(names) == 68
    assert "cellcharter" in names


def test_the_prose_may_change():
    text = _HEAD + "Anything at all can be written here.\nOn two lines.\n\n`numpy`, `scikit-learn`\n\nMore prose.\n"
    assert parse_dependencies(text, source="x.md") == ("numpy", "scikit-learn")


def test_the_section_ends_at_the_next_heading():
    text = _HEAD + _PROSE + "`numpy`\n\n## Outputs\n\n`pandas`\n"
    assert parse_dependencies(text, source="x.md") == ("numpy",)


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("# x\n\nNo section at all.\n", "no `## Dependencies` section"),
        (_HEAD + _PROSE + "Nothing but prose.\n", "no package-name line"),
        (_HEAD + _PROSE + "`numpy`\n`pandas`\n", "2 package-name lines"),
        (_HEAD + _PROSE + "`numpy`, pandas\n", "no package-name line"),
        (_HEAD + _PROSE + "`numpy`, `pan das`\n", "no package-name line"),
        (_HEAD + _PROSE + "`numpy`, `pandas;rm`\n", "no package-name line"),
    ],
    ids=["no-section", "no-line", "two-lines", "unquoted", "space", "semicolon"],
)
def test_malformed_sections_are_refused_with_the_file(text, fragment):
    with pytest.raises(DependencyFormatError) as info:
        parse_dependencies(text, source="skills/demo/SKILL.md")
    assert "skills/demo/SKILL.md" in str(info.value)
    assert fragment in str(info.value)
