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


def test_scvi_tools_constraints_avoid_legacy_jax_resolver_backtracking():
    requirements = _optional_requirements_by_name("scvi-tools")

    assert requirements
    for extra_name, requirement in requirements:
        assert requirement.specifier.contains(Version("1.4.0")), extra_name
        assert not requirement.specifier.contains(Version("1.3.3")), extra_name
        assert not requirement.specifier.contains(Version("2.0.0")), extra_name


def test_cell2location_constraint_avoids_old_scvi_tools_floor():
    requirements = _optional_requirements_by_name("cell2location")

    assert requirements
    for extra_name, requirement in requirements:
        assert requirement.specifier.contains(Version("0.1.5")), extra_name
        assert not requirement.specifier.contains(Version("0.1.4")), extra_name
        assert not requirement.specifier.contains(Version("0.2.0")), extra_name
