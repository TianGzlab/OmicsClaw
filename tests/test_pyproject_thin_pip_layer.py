"""Verify pyproject's pip layer is thin: heavy hubs must live in environment.yml."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]

# Packages that MUST be installed via conda/mamba, NOT listed in pyproject.
# Pip-only packages (no conda recipe) stay in pyproject: SpaGCN, GraphST,
# cellcharter, paste-bio, flashdeconv, fastccc, pyVIA, pybanksy, tangram-sc,
# torch_geometric, phate. The deliberate exceptions among conda-available
# packages are pydantic (ADR 0037) and PIP_CORE_STARTUP below, which are
# declared in both files.
# Post-merge follow-up audit (2026-05-02) confirmed cell2location, cellphonedb,
# infercnvpy, and SpatialDE return HTTP 404 on both bioconda and conda-forge —
# they are genuinely pip-only and stay in pyproject.
CONDA_OWNED = {
    "scanpy",
    "anndata",
    "squidpy",
    "numpy",
    "pandas",
    "scipy",
    "scikit-learn",
    "matplotlib",
    "seaborn",
    "pillow",
    "scikit-misc",
    "igraph",
    "python-igraph",
    "leidenalg",
    "louvain",
    "umap-learn",
    "nbformat",
    "nbclient",
    "jupyter-client",
    "ipykernel",
    "greenlet",
    "prompt-toolkit",
    "questionary",
    "pyyaml",
    "aiosqlite",
    "sqlalchemy",
    "fastapi",
    "uvicorn",
    "cryptography",
    "requests",
    "python-dotenv",
    "httpx",
    "torch",
    "pytorch",
    "pytorch-cpu",
    "jinja2",
    "nbconvert",
    "beautifulsoup4",
    "scvi-tools",
    "scvelo",
    "cellrank",
    "harmonypy",
    "bbknn",
    "scanorama",
    "celltypist",
    "liana",
    "gseapy",
    "pydeseq2",
    "scrublet",
    "doubletdetection",
    "arboreto",
    "palantir",
    "multiqc",
    "kb-python",
    "esda",
    "libpysal",
    "pysal",
    "pot",
    "coloredlogs",
    "humanfriendly",
    "pypdf",
}

# What `oc cli` imports to start and to reach a model. A plain `pip install .`
# must bring these, and the conda environment must carry the same floors.
PIP_CORE_STARTUP = {"rich", "openai", "anthropic"}


def test_pyproject_thin_pip_layer_excludes_conda_owned_packages():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    seen: set[str] = set()
    for dep in pyproject["project"].get("dependencies", []):
        seen.add(Requirement(dep).name.lower())
    for extra, deps in pyproject["project"]["optional-dependencies"].items():
        for dep in deps:
            req = Requirement(dep)
            if req.name == "omicsclaw":
                continue  # self-extras references are fine
            seen.add(req.name.lower())
    leaked = seen & CONDA_OWNED
    assert not leaked, (
        f"these packages must be installed via mamba (environment.yml) only, "
        f"but still appear in pyproject: {sorted(leaked)}"
    )


def test_pydantic_verified_floor_matches_pip_and_conda_sources():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pip_requirement = next(
        Requirement(value)
        for value in pyproject["project"]["dependencies"]
        if Requirement(value).name.lower() == "pydantic"
    )
    environment_lines = (
        (ROOT / "environment.yml").read_text(encoding="utf-8").splitlines()
    )
    conda_requirement = Requirement(
        next(
            line.strip()[2:]
            for line in environment_lines
            if line.strip().startswith("- pydantic")
        )
    )

    for requirement in (pip_requirement, conda_requirement):
        assert requirement.specifier.contains("2.1.0")
        assert not requirement.specifier.contains("2.0.9")
        assert not requirement.specifier.contains("3.0.0")


def test_channels_extra_installs_authoritative_channel_sdks():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    optional_dependencies = pyproject["project"]["optional-dependencies"]

    assert "channels" in optional_dependencies
    assert "python-telegram-bot>=21.0" in optional_dependencies["channels"]
    assert "lark-oapi>=1.3.0" in optional_dependencies["channels"]


def test_startup_packages_are_core_deps_with_the_conda_floor():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    core = {
        Requirement(value).name.lower(): Requirement(value)
        for value in pyproject["project"]["dependencies"]
    }
    environment = yaml.safe_load(
        (ROOT / "environment.yml").read_text(encoding="utf-8")
    )
    conda = {}
    for entry in environment["dependencies"]:
        if not isinstance(entry, str):
            continue
        name = re.split(r"[<>=!\s]", entry, maxsplit=1)[0].lower()
        if name in PIP_CORE_STARTUP:
            conda[name] = Requirement(entry)

    for name in sorted(PIP_CORE_STARTUP):
        assert name in core, f"{name} is imported at startup but not a core dep"
        assert name in conda, f"{name} is a core dep but missing from environment.yml"
        assert core[name].specifier == conda[name].specifier, name
