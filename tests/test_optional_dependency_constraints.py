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


def test_singlecell_upstream_constraints_avoid_multiqc_leaf_backtracking():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    upstream = {
        Requirement(dependency).name: Requirement(dependency)
        for dependency in pyproject["project"]["optional-dependencies"]["singlecell-upstream"]
    }

    multiqc = upstream["multiqc"]
    assert multiqc.specifier.contains(Version("1.33"))
    assert not multiqc.specifier.contains(Version("1.32"))
    assert not multiqc.specifier.contains(Version("2.0"))

    coloredlogs = upstream["coloredlogs"]
    assert coloredlogs.specifier.contains(Version("15.0.1"))
    assert not coloredlogs.specifier.contains(Version("14.0"))
    assert not coloredlogs.specifier.contains(Version("16.0"))

    humanfriendly = upstream["humanfriendly"]
    assert humanfriendly.specifier.contains(Version("10.0"))
    assert not humanfriendly.specifier.contains(Version("9.2"))
    assert not humanfriendly.specifier.contains(Version("11.0"))


def test_cellrank_constraints_skip_python312_only_releases():
    requirements = _optional_requirements_by_name("cellrank")

    assert requirements
    for extra_name, requirement in requirements:
        assert requirement.specifier.contains(Version("2.0.7")), extra_name
        assert not requirement.specifier.contains(Version("2.0.6")), extra_name
        assert not requirement.specifier.contains(Version("2.1.0")), extra_name
        assert not requirement.specifier.contains(Version("2.2.0")), extra_name


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
