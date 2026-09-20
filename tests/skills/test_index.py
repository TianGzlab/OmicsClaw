"""The index: what goes into the prompt, and what is fetched on demand."""

from __future__ import annotations

import pathlib

import pytest

from omicsclaw.skills import Skill, SkillIndex, SkillNotFound, load_skills

from .test_loader import write_skill


def make(name: str, description: str, directory: str = "domain") -> Skill:
    """A skill whose path is plausible but never read."""
    root = pathlib.Path("skills")
    return Skill(
        name=name,
        description=description,
        path=root / directory / name / "SKILL.md",
        root=root,
    )


def test_an_empty_index_reports_itself_empty():
    index = SkillIndex()

    assert index.is_empty
    assert len(index) == 0
    assert index.names() == ()


def test_an_index_with_skills_is_not_empty():
    index = SkillIndex(skills=(make("a", "does a"),))

    assert not index.is_empty
    assert len(index) == 1


def test_an_empty_index_summarises_to_nothing():
    """An empty string is what makes the whole prompt section disappear."""
    index = SkillIndex()

    assert index.summary() == ""
    assert index.domain_summary() == ""
    assert index.prompt_body() == ""
    assert index.prompt_body(compact=True) == ""


def test_the_summary_is_one_line_per_skill():
    index = SkillIndex(
        skills=(make("alpha", "does alpha"), make("beta", "does beta"))
    )

    assert index.summary() == "- alpha: does alpha\n- beta: does beta\n"


def test_the_domain_summary_groups_names_and_drops_descriptions():
    index = SkillIndex(
        skills=(
            make("spatial-de", "x", "spatial"),
            make("spatial-genes", "y", "spatial"),
            make("sc-de", "z", "singlecell"),
        )
    )

    assert index.domain_summary() == (
        "- spatial (2 skills): spatial-de, spatial-genes\n"
        "- singlecell (1 skills): sc-de\n"
    )


def test_a_skill_with_no_domain_groups_under_a_label():
    root = pathlib.Path("skills")
    index = SkillIndex(skills=(Skill("loose", "d", root / "SKILL.md", root),))

    assert index.domain_summary() == "- (ungrouped) (1 skills): loose\n"


def test_the_prompt_body_names_the_tool_and_carries_the_index():
    index = SkillIndex(skills=(make("alpha", "does alpha"),))

    body = index.prompt_body()

    assert "`use_skill`" in body
    assert body.endswith("- alpha: does alpha\n")


def test_the_prompt_body_carries_no_heading():
    """The heading belongs to the Section, so a caller can retitle it."""
    index = SkillIndex(skills=(make("alpha", "does alpha"),))

    assert not index.prompt_body().lstrip().startswith("#")


def test_the_compact_prompt_body_uses_the_domain_summary():
    index = SkillIndex(skills=(make("alpha", "a long description", "spatial"),))

    assert "a long description" in index.prompt_body()
    assert "a long description" not in index.prompt_body(compact=True)
    assert "- spatial (1 skills): alpha" in index.prompt_body(compact=True)


def test_the_bound_prompt_body_is_a_zero_argument_source():
    """It has to be usable directly as a context-layer SectionSource."""
    index = SkillIndex(skills=(make("alpha", "does alpha"),))
    source = index.prompt_body

    assert source() == index.prompt_body()


def test_names_are_returned_in_index_order():
    index = SkillIndex(skills=(make("z", "d"), make("a", "d")))

    assert index.names() == ("z", "a")


def test_get_returns_the_skill_or_none():
    alpha = make("alpha", "d")
    index = SkillIndex(skills=(alpha,))

    assert index.get("alpha") is alpha
    assert index.get("nope") is None


def test_get_full_content_returns_the_body_without_its_header(tmp_path):
    write_skill(tmp_path / "alpha", "alpha")
    index = load_skills(tmp_path)

    content = index.get_full_content("alpha")

    assert content == "# alpha\n\nInstructions for alpha."
    assert "description:" not in content


def test_get_full_content_reads_the_file_again_every_call(tmp_path):
    """A SKILL.md written mid-run must be visible on the next load."""
    path = write_skill(tmp_path / "alpha", "alpha")
    index = load_skills(tmp_path)
    assert "first" not in index.get_full_content("alpha")

    path.write_text("---\nname: alpha\ndescription: d\n---\nfirst edit", "utf-8")

    assert index.get_full_content("alpha") == "first edit"


def test_an_unknown_name_raises_with_the_closest_matches():
    index = SkillIndex(
        skills=(
            make("spatial-de", "d"),
            make("spatial-deconv", "d"),
            make("genomics-qc", "d"),
        )
    )

    with pytest.raises(SkillNotFound) as caught:
        index.get_full_content("spatial-dee")

    message = str(caught.value)
    assert "spatial-de" in message
    assert "genomics-qc" not in message, "only near misses are worth suggesting"
    assert "all 3" in message


def test_an_unknown_name_with_no_near_miss_still_points_at_the_index():
    index = SkillIndex(skills=(make("spatial-de", "d"),))

    with pytest.raises(SkillNotFound) as caught:
        index.get_full_content("zzzzzzzz")

    assert caught.value.suggestions == ()
    assert "lists all 1" in str(caught.value)


def test_a_name_that_looks_like_a_path_finds_nothing(tmp_path):
    """A lookup is a lookup; nothing concatenates the argument onto a directory."""
    write_skill(tmp_path / "alpha", "alpha")
    (tmp_path / "secret.md").write_text("---\nname: s\n---\ntop secret", "utf-8")
    index = load_skills(tmp_path)

    for attempt in ("../secret.md", "/etc/passwd", "alpha/../../secret.md"):
        with pytest.raises(SkillNotFound):
            index.get_full_content(attempt)


def test_an_indexed_file_that_disappeared_raises_the_os_error(tmp_path):
    """The machine's problem, reported as itself rather than as a bad name."""
    path = write_skill(tmp_path / "alpha", "alpha")
    index = load_skills(tmp_path)
    path.unlink()

    with pytest.raises(FileNotFoundError):
        index.get_full_content("alpha")


def test_by_domain_keeps_index_order_within_each_group():
    index = SkillIndex(
        skills=(
            make("a1", "d", "alpha"),
            make("b1", "d", "beta"),
            make("a2", "d", "alpha"),
        )
    )

    assert index.by_domain() == (
        ("alpha", (index.skills[0], index.skills[2])),
        ("beta", (index.skills[1],)),
    )
