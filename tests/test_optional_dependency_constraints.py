from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version


ROOT = Path(__file__).resolve().parents[1]


def _optional_requirements_by_name(package_name: str) -> list[tuple[str, Requirement]]:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    matches: list[tuple[str, Requirement]] = []
    for extra_name, dependencies in pyproject["project"]["optional-dependencies"].items():
        for dependency in dependencies:
            requirement = Requirement(dependency)
            if requirement.name == package_name:
                matches.append((extra_name, requirement))
    return matches


def test_scvi_tools_no_longer_in_pyproject_pip_layer():
    """scvi-tools is now mamba-owned (environment.yml Tier 4)."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    for extra, deps in pyproject["project"]["optional-dependencies"].items():
        for dep in deps:
            req = Requirement(dep)
            assert req.name != "scvi-tools", (
                f"scvi-tools must live in environment.yml only, found in [{extra}]"
            )


def test_cell2location_constraint_avoids_old_scvi_tools_floor():
    requirements = _optional_requirements_by_name("cell2location")

    assert requirements
    for extra_name, requirement in requirements:
        assert requirement.specifier.contains(Version("0.1.5")), extra_name
        assert not requirement.specifier.contains(Version("0.1.4")), extra_name
        assert not requirement.specifier.contains(Version("0.2.0")), extra_name


def test_singlecell_upstream_resolver_leaves_no_longer_in_pyproject():
    """multiqc, coloredlogs, humanfriendly, kb-python are all in env.yml now."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    moved = {"multiqc", "coloredlogs", "humanfriendly", "kb-python"}
    for extra, deps in pyproject["project"]["optional-dependencies"].items():
        for dep in deps:
            req = Requirement(dep)
            assert req.name not in moved, (
                f"{req.name} moved to environment.yml; remove from [{extra}]"
            )


def test_cellrank_no_longer_in_pyproject_pip_layer():
    """cellrank is now mamba-owned (environment.yml Tier 4)."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    for extra, deps in pyproject["project"]["optional-dependencies"].items():
        for dep in deps:
            assert Requirement(dep).name != "cellrank", (
                f"cellrank must live in environment.yml only, found in [{extra}]"
            )


def test_full_extra_excludes_oauth_to_avoid_trajectory_ccproxy_resolver_conflict():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    full_requirements = [
        Requirement(dependency)
        for dependency in pyproject["project"]["optional-dependencies"]["full"]
    ]

    assert "oauth" in pyproject["project"]["optional-dependencies"]
    assert len(full_requirements) == 1
    assert full_requirements[0].name == "omicsclaw"
    assert "spatial-trajectory" in full_requirements[0].extras
    assert "singlecell-pseudotime" in full_requirements[0].extras
    assert "oauth" not in full_requirements[0].extras
