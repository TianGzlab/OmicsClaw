"""Scanning a tree for ``SKILL.md`` files."""

from __future__ import annotations

import os
import pathlib

import pytest

from omicsclaw.skills import SkillLoadError, SkipReason, load_skills


def write_skill(directory: pathlib.Path, name: str, description: str = "d", **extra):
    """Create ``directory/SKILL.md`` with a minimal generated-style header."""
    directory.mkdir(parents=True, exist_ok=True)
    lines = [f"name: {name}", f"description: {description}"]
    lines.extend(f"{key}: {value}" for key, value in extra.items())
    body = "\n".join(lines)
    (directory / "SKILL.md").write_text(
        f"---\n{body}\n---\n\n# {name}\n\nInstructions for {name}.\n",
        encoding="utf-8",
    )
    return directory / "SKILL.md"


def test_a_missing_root_is_an_empty_index_and_not_an_error(tmp_path):
    """Zero configuration: nothing has to be installed for the agent to run."""
    index = load_skills(tmp_path / "nothing-here")

    assert index.is_empty
    assert index.names() == ()
    assert index.skipped == ()


def test_an_empty_root_is_an_empty_index(tmp_path):
    assert load_skills(tmp_path).is_empty


def test_a_root_that_is_a_file_is_an_error(tmp_path):
    """A named root that cannot be scanned must not read as "no skills"."""
    root = tmp_path / "skills"
    root.write_text("not a directory", encoding="utf-8")

    with pytest.raises(SkillLoadError):
        load_skills(root)


def refuse_scandir(monkeypatch, blocked: pathlib.Path):
    """Make :func:`os.scandir` raise :exc:`PermissionError` for *blocked*.

    Driven this way rather than with ``chmod`` so the test means the same
    thing for a privileged user, who is not stopped by the mode bits.
    """
    real = os.scandir

    def scandir(path=".", *args, **kwargs):
        if pathlib.Path(path) == blocked:
            raise PermissionError(13, "Permission denied", str(blocked))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os, "scandir", scandir)


def test_an_unreadable_root_is_an_error(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    root.mkdir()
    refuse_scandir(monkeypatch, root)

    with pytest.raises(SkillLoadError):
        load_skills(root)


def test_every_valid_skill_in_the_tree_is_loaded(tmp_path):
    write_skill(tmp_path / "alpha", "alpha", "does alpha")
    write_skill(tmp_path / "beta", "beta", "does beta")

    index = load_skills(tmp_path)

    assert index.names() == ("alpha", "beta")
    assert index.get("alpha").description == "does alpha"
    assert index.skipped == ()


def test_a_subdirectory_without_a_skill_file_is_not_a_skill(tmp_path):
    write_skill(tmp_path / "real", "real")
    (tmp_path / "empty").mkdir()
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "README.md").write_text("hi", encoding="utf-8")

    index = load_skills(tmp_path)

    assert index.names() == ("real",)
    assert index.skipped == ()


def test_a_loose_file_in_the_root_is_not_a_skill(tmp_path):
    write_skill(tmp_path / "real", "real")
    (tmp_path / "catalog.json").write_text("{}", encoding="utf-8")

    assert load_skills(tmp_path).names() == ("real",)


def test_skills_are_found_at_every_depth(tmp_path):
    """The corpus has skills one, two and three directories down."""
    write_skill(tmp_path / "literature", "literature")
    write_skill(tmp_path / "spatial" / "spatial-de", "spatial-de")
    write_skill(tmp_path / "singlecell" / "scrna" / "sc-de", "sc-de")

    index = load_skills(tmp_path)

    assert set(index.names()) == {"literature", "spatial-de", "sc-de"}


def test_a_skill_directory_may_itself_contain_skills(tmp_path):
    """``skills/orchestrator/`` is a skill and the parent of another one."""
    write_skill(tmp_path / "orchestrator", "orchestrator")
    write_skill(tmp_path / "orchestrator" / "builder", "omics-skill-builder")

    index = load_skills(tmp_path)

    assert set(index.names()) == {"orchestrator", "omics-skill-builder"}


def test_dot_directories_and_caches_are_not_descended_into(tmp_path):
    write_skill(tmp_path / "real", "real")
    write_skill(tmp_path / ".git" / "hooks", "from-git")
    write_skill(tmp_path / "__pycache__" / "x", "from-cache")
    write_skill(tmp_path / "node_modules" / "pkg", "from-node-modules")

    assert load_skills(tmp_path).names() == ("real",)


def test_a_header_missing_its_name_is_skipped_with_a_reason(tmp_path):
    write_skill(tmp_path / "good", "good")
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "SKILL.md").write_text(
        "---\ndescription: has no name\n---\nbody", encoding="utf-8"
    )

    index = load_skills(tmp_path)

    assert index.names() == ("good",)
    assert [s.reason for s in index.skipped] == [SkipReason.MISSING_NAME]
    assert index.skipped[0].path == tmp_path / "bad" / "SKILL.md"


def test_a_header_missing_its_description_is_skipped_with_its_own_reason(tmp_path):
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "SKILL.md").write_text(
        "---\nname: nameless-description\n---\nbody", encoding="utf-8"
    )

    index = load_skills(tmp_path)

    assert index.is_empty
    assert index.skipped[0].reason == SkipReason.MISSING_DESCRIPTION
    assert index.skipped[0].detail == "nameless-description"


def test_a_file_with_no_frontmatter_is_skipped(tmp_path):
    (tmp_path / "bare").mkdir()
    (tmp_path / "bare" / "SKILL.md").write_text("# just prose\n", encoding="utf-8")

    index = load_skills(tmp_path)

    assert index.is_empty
    assert index.skipped[0].reason == SkipReason.NO_FRONTMATTER


def test_an_undecodable_file_is_skipped_rather_than_raising(tmp_path):
    (tmp_path / "binary").mkdir()
    (tmp_path / "binary" / "SKILL.md").write_bytes(b"---\nname: \xff\xfe\n---\n")

    index = load_skills(tmp_path)

    assert index.is_empty
    assert index.skipped[0].reason == SkipReason.UNREADABLE
    assert index.skipped[0].detail


def test_one_bad_skill_does_not_cost_the_others(tmp_path):
    write_skill(tmp_path / "a", "a")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "SKILL.md").write_text("no header", encoding="utf-8")
    write_skill(tmp_path / "c", "c")

    index = load_skills(tmp_path)

    assert index.names() == ("a", "c")
    assert len(index.skipped) == 1


def test_a_duplicate_name_keeps_the_first_and_records_the_second(tmp_path):
    """A name the model is shown but cannot load is worse than one it is not."""
    write_skill(tmp_path / "a-first", "twin", "the one that wins")
    write_skill(tmp_path / "z-second", "twin", "the one that loses")

    index = load_skills(tmp_path)

    assert index.names() == ("twin",)
    assert index.get("twin").description == "the one that wins"
    assert index.skipped[0].reason == SkipReason.DUPLICATE_NAME
    assert index.skipped[0].path == tmp_path / "z-second" / "SKILL.md"
    assert "a-first" in index.skipped[0].detail


def test_an_unreadable_subdirectory_is_recorded_and_the_scan_continues(
    tmp_path, monkeypatch
):
    write_skill(tmp_path / "reachable", "reachable")
    blocked = tmp_path / "blocked"
    write_skill(blocked / "hidden", "hidden")
    refuse_scandir(monkeypatch, blocked)

    index = load_skills(tmp_path)

    assert index.names() == ("reachable",)
    assert index.skipped[0].reason == SkipReason.UNREADABLE
    assert index.skipped[0].path == blocked


def test_a_symlinked_directory_is_not_followed(tmp_path):
    """A cycle in the tree must not hang the scan."""
    write_skill(tmp_path / "real", "real")
    (tmp_path / "loop").symlink_to(tmp_path, target_is_directory=True)

    assert load_skills(tmp_path).names() == ("real",)


def test_the_order_is_the_sorted_relative_path(tmp_path):
    """The index order is the prompt's order, so it must not vary by host.

    ``a-b`` against ``a/c`` is the case where sorting whole paths and
    sorting each directory's entries disagree: ``-`` precedes ``/``, so
    the path order puts ``a-b`` first, while a per-directory walk visits
    ``a`` first. The stated rule is the path order.
    """
    write_skill(tmp_path / "a-b", "dash-directory")
    write_skill(tmp_path / "a" / "c", "nested-directory")

    index = load_skills(tmp_path)

    assert [str(s.relative_path) for s in index.skills] == [
        "a-b/SKILL.md",
        "a/c/SKILL.md",
    ]
    assert index.names() == ("dash-directory", "nested-directory")


def test_two_loads_of_one_tree_render_the_same_bytes(tmp_path):
    for name in ("delta", "alpha", "charlie", "bravo"):
        write_skill(tmp_path / "domain" / name, name)

    first = load_skills(tmp_path)
    second = load_skills(tmp_path)

    assert first.summary() == second.summary()
    assert first.names() == second.names()


def test_a_relative_root_gives_relative_skill_paths(tmp_path, monkeypatch):
    write_skill(tmp_path / "spatial" / "spatial-de", "spatial-de")
    monkeypatch.chdir(tmp_path)

    index = load_skills(".")
    skill = index.get("spatial-de")

    assert not skill.path.is_absolute()
    assert str(skill.directory) == os.path.join("spatial", "spatial-de")


def test_metadata_beyond_name_and_description_is_carried(tmp_path):
    directory = tmp_path / "spatial" / "spatial-de"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        "---\nname: spatial-de\ndescription: d\ntrigger: /de\n"
        "tags:\n- spatial\n- de\n---\nbody",
        encoding="utf-8",
    )

    skill = load_skills(tmp_path).get("spatial-de")

    assert skill.trigger == "/de"
    assert skill.tags == ("spatial", "de")
    assert skill.domain == "spatial"
    assert skill.root == tmp_path


def test_the_bodies_are_not_read_at_load_time(tmp_path, monkeypatch):
    """Progressive disclosure: loading costs headers, not instructions."""
    write_skill(tmp_path / "a", "a")
    index = load_skills(tmp_path)

    reads: list[str] = []
    original = pathlib.Path.read_text

    def spy(self, *args, **kwargs):
        reads.append(str(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_text", spy)
    load_skills(tmp_path)
    at_load = len(reads)
    index.get_full_content("a")

    assert at_load == 1, "the header read"
    assert len(reads) == 2, "and exactly one more when the body is asked for"
