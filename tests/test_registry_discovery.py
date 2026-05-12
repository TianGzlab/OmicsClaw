"""Negative + edge-case loader tests for ``OmicsRegistry`` discovery.

These cover behaviors that don't show up in the snapshot tests:

- ``_looks_like_skill_dir`` heuristic boundaries (positive *and* negative).
- ``skills_dir`` cache key — re-loading from a different directory must
  invalidate the previous snapshot instead of silently returning it.
- ``invalidate`` / ``reload`` semantics.
- Hot-loading a synthetic fixture skill so we exercise the same paths the
  bundled 89 skills use, without depending on those snapshots.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omicsclaw.core.registry import OmicsRegistry


def _write_skill(
    skill_dir: Path,
    *,
    skill_name: str,
    description: str = "Test skill",
    domain_in_yaml: str | None = None,
) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    frontmatter = [
        "---",
        f"name: {skill_name}",
        f"description: {description}",
        "---",
        "",
        f"# {skill_name}",
    ]
    (skill_dir / "SKILL.md").write_text("\n".join(frontmatter), encoding="utf-8")
    sidecar_lines = [f"script: {skill_name.replace('-', '_')}.py"]
    if domain_in_yaml is not None:
        sidecar_lines.append(f"domain: {domain_in_yaml}")
    (skill_dir / "parameters.yaml").write_text("\n".join(sidecar_lines), encoding="utf-8")
    (skill_dir / f"{skill_name.replace('-', '_')}.py").write_text(
        "if __name__ == '__main__':\n    pass\n",
        encoding="utf-8",
    )


def test_looks_like_skill_dir_rejects_empty_directory(tmp_path):
    empty = tmp_path / "empty-container"
    empty.mkdir()
    assert OmicsRegistry._looks_like_skill_dir(empty) is False


def test_looks_like_skill_dir_rejects_multi_script_subdomain(tmp_path):
    """A subdomain container with multiple top-level scripts (but no SKILL.md
    and no matching ``<dir>.py``) must NOT be classified as a skill.
    """
    container = tmp_path / "scrna"
    container.mkdir()
    (container / "helper_a.py").write_text("x = 1\n", encoding="utf-8")
    (container / "helper_b.py").write_text("y = 2\n", encoding="utf-8")
    assert OmicsRegistry._looks_like_skill_dir(container) is False


def test_looks_like_skill_dir_accepts_skill_md(tmp_path):
    skill = tmp_path / "fake-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    assert OmicsRegistry._looks_like_skill_dir(skill) is True


def test_looks_like_skill_dir_accepts_single_top_level_script(tmp_path):
    """One top-level .py with no SKILL.md is still a valid layout (legacy)."""
    skill = tmp_path / "lone-script"
    skill.mkdir()
    (skill / "lone_script.py").write_text("x = 1\n", encoding="utf-8")
    assert OmicsRegistry._looks_like_skill_dir(skill) is True


def test_load_all_uses_fixture_skills_dir(tmp_path):
    """``load_all`` must respect a custom ``skills_dir`` and not fall back to
    the repo default. Verifies the fixture isolation contract."""
    fixtures = tmp_path / "skills"
    _write_skill(fixtures / "spatial" / "fake-foo", skill_name="fake-foo")

    registry = OmicsRegistry()
    registry.load_all(fixtures)

    assert "fake-foo" in registry.skills
    # No real skills leaked in.
    assert "spatial-preprocess" not in registry.skills


def test_load_all_with_different_skills_dir_invalidates_previous_snapshot(tmp_path):
    """Re-calling ``load_all`` with a different directory must rescan, not
    silently return the previous snapshot."""
    fixtures_a = tmp_path / "skills_a"
    fixtures_b = tmp_path / "skills_b"
    _write_skill(fixtures_a / "spatial" / "fake-a", skill_name="fake-a")
    _write_skill(fixtures_b / "spatial" / "fake-b", skill_name="fake-b")

    registry = OmicsRegistry()
    registry.load_all(fixtures_a)
    assert "fake-a" in registry.skills
    assert "fake-b" not in registry.skills

    registry.load_all(fixtures_b)
    assert "fake-b" in registry.skills
    assert "fake-a" not in registry.skills


def test_invalidate_and_reload_round_trip(tmp_path):
    fixtures = tmp_path / "skills"
    _write_skill(fixtures / "spatial" / "fake-x", skill_name="fake-x")

    registry = OmicsRegistry()
    registry.load_all(fixtures)
    assert "fake-x" in registry.skills

    # Add a second skill on disk; without invalidate the cache is sticky.
    _write_skill(fixtures / "spatial" / "fake-y", skill_name="fake-y")
    registry.load_all(fixtures)
    assert "fake-y" not in registry.skills, "snapshot should be sticky until invalidated"

    registry.reload(fixtures)
    assert "fake-y" in registry.skills
    assert "fake-x" in registry.skills


def test_parameters_yaml_domain_overrides_directory_parent(tmp_path):
    """If a skill's parameters.yaml declares a ``domain:`` it wins over the
    parent directory name. This locks the current precedence so changing it
    requires an explicit test update."""
    fixtures = tmp_path / "skills"
    _write_skill(
        fixtures / "orchestrator" / "stray-spatial",
        skill_name="stray-spatial",
        domain_in_yaml="spatial",
    )

    registry = OmicsRegistry()
    registry.load_all(fixtures)
    info = registry.skills["stray-spatial"]
    assert info["domain"] == "spatial"


def test_skill_count_refreshed_from_disk(tmp_path):
    """Domain ``skill_count`` must be derived from the loaded skills, not from
    a stale literal in ``_HARDCODED_DOMAINS``."""
    fixtures = tmp_path / "skills"
    _write_skill(fixtures / "spatial" / "fake-1", skill_name="fake-1")
    _write_skill(fixtures / "spatial" / "fake-2", skill_name="fake-2")

    registry = OmicsRegistry()
    registry.load_all(fixtures)
    assert registry.domains["spatial"]["skill_count"] == 2


def test_invalidate_resets_state(tmp_path):
    fixtures = tmp_path / "skills"
    _write_skill(fixtures / "spatial" / "fake-z", skill_name="fake-z")

    registry = OmicsRegistry()
    registry.load_all(fixtures)
    assert registry.skills

    registry.invalidate()
    assert registry.skills == {}
    assert registry.lazy_skills == {}
    assert registry._loaded is False
