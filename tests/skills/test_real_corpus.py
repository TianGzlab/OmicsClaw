"""The loader against this repository's own ``skills/`` tree.

A hand-written parser's real risk is not crashing, it is being quietly
wrong on the corpus it was written for. These tests run it over every
real ``SKILL.md`` and, where PyYAML is installed, compare it key by key
against a real YAML parser.
"""

from __future__ import annotations

import pathlib

import pytest

from omicsclaw.skills import load_skills
from omicsclaw.skills.frontmatter import parse_frontmatter

try:
    import yaml
except ImportError:  # pragma: no cover - depends on the environment
    yaml = None

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SKILLS_ROOT = REPO_ROOT / "skills"

pytestmark = pytest.mark.skipif(
    not SKILLS_ROOT.is_dir(), reason="the skills corpus is not present"
)

requires_yaml = pytest.mark.skipif(yaml is None, reason="PyYAML is not installed")


def skill_files() -> list[pathlib.Path]:
    """Every ``SKILL.md`` in the repository, found independently of the loader."""
    if not SKILLS_ROOT.is_dir():
        return []
    return sorted(SKILLS_ROOT.rglob("SKILL.md"))


def header_text(path: pathlib.Path) -> str | None:
    """The raw YAML between the delimiters, or ``None`` if there is none."""
    lines = path.read_text(encoding="utf-8").split("\n")
    if not lines or lines[0] != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index] == "---":
            return "\n".join(lines[1:index])
    return None


def test_the_corpus_is_there_to_check():
    """A test that vacuously passes over an empty tree is not a test."""
    assert len(skill_files()) > 50


def test_every_skill_file_in_the_tree_is_indexed():
    index = load_skills(SKILLS_ROOT)

    assert len(index) == len(skill_files())
    assert index.skipped == (), [
        (str(s.path), s.reason, s.detail) for s in index.skipped
    ]


def test_every_skill_name_is_unique():
    """Duplicates would be listed in the prompt and unreachable by name."""
    index = load_skills(SKILLS_ROOT)

    assert len(set(index.names())) == len(index.names())


def test_every_skill_has_a_domain_and_a_real_description():
    index = load_skills(SKILLS_ROOT)

    without_domain = [s.name for s in index.skills if not s.domain]
    short = [s.name for s in index.skills if len(s.description) < 20]

    assert without_domain == []
    assert short == []


def test_the_folded_descriptions_survive_whole():
    """Cutting a description at its first line drops the "Skip when" half."""
    index = load_skills(SKILLS_ROOT)
    skill = index.get("spatial-preprocess")

    assert skill is not None
    assert skill.description.startswith("Load when running the foundational")
    assert "Skip when" in skill.description
    assert "spatial-raw-processing" in skill.description
    assert "\n" not in skill.description


def test_a_skill_directory_that_holds_another_skill_yields_both():
    """``skills/orchestrator/`` is a skill and the parent of one."""
    names = load_skills(SKILLS_ROOT).names()

    assert "orchestrator" in names
    assert "omics-skill-builder" in names


def test_loading_the_corpus_twice_renders_the_same_bytes():
    """The index sits in the prompt prefix, so its bytes must not drift."""
    first = load_skills(SKILLS_ROOT)
    second = load_skills(SKILLS_ROOT)

    assert first.summary() == second.summary()
    assert first.domain_summary() == second.domain_summary()


def test_the_two_summaries_cost_what_the_docstrings_claim():
    """Roughly 8.5k tokens against roughly 600, at ~3.5 characters a token."""
    index = load_skills(SKILLS_ROOT)

    assert 20_000 < len(index.summary()) < 60_000
    assert len(index.domain_summary()) < len(index.summary()) / 8


def test_the_index_costs_a_fraction_of_the_bodies():
    """What Progressive Disclosure is for, measured on the real corpus."""
    index = load_skills(SKILLS_ROOT)
    bodies = sum(len(index.get_full_content(name)) for name in index.names())

    assert bodies > 300_000
    assert len(index.summary()) < bodies / 8


def test_every_body_loads_and_none_leaks_its_header():
    index = load_skills(SKILLS_ROOT)

    empty = []
    leaked = []
    for name in index.names():
        content = index.get_full_content(name)
        if not content:
            empty.append(name)
        if content.startswith("---") or "\ndescription:" in content[:400]:
            leaked.append(name)

    assert empty == []
    assert leaked == []


@requires_yaml
@pytest.mark.parametrize("path", skill_files(), ids=lambda p: p.parent.name)
def test_the_subset_parser_agrees_with_pyyaml(path: pathlib.Path):
    """Every scalar and sequence this module reports must match PyYAML.

    Keys PyYAML reads as a mapping are exempt: the subset drops those by
    design, and the test asserts they were dropped rather than mangled.
    """
    raw = header_text(path)
    assert raw is not None, f"{path} has no frontmatter"
    expected = yaml.safe_load(raw)
    parsed = parse_frontmatter(path.read_text(encoding="utf-8"))

    for key, value in expected.items():
        if isinstance(value, dict):
            assert key not in parsed.fields, f"{key} is a mapping and was kept"
        elif isinstance(value, list):
            assert parsed.items(key) == tuple(str(item) for item in value), key
        elif value is None:
            assert parsed.text(key) == "", key
        else:
            assert parsed.text(key) == str(value), key


@requires_yaml
@pytest.mark.parametrize("path", skill_files(), ids=lambda p: p.parent.name)
def test_the_subset_parser_invents_no_keys(path: pathlib.Path):
    raw = header_text(path)
    assert raw is not None
    parsed = parse_frontmatter(path.read_text(encoding="utf-8"))

    assert set(parsed.fields) <= set(yaml.safe_load(raw))


@pytest.mark.parametrize("path", skill_files(), ids=lambda p: p.parent.name)
def test_the_body_is_exactly_the_text_after_the_header(path: pathlib.Path):
    content = path.read_text(encoding="utf-8")
    raw = header_text(path)
    parsed = parse_frontmatter(content)

    assert parsed.has_frontmatter
    assert content.endswith(parsed.body), "the body must be a suffix of the file"
    assert raw not in parsed.body
    assert parsed.body.lstrip().startswith("#")
