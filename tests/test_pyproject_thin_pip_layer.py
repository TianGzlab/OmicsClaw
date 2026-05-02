"""Verify pyproject's pip layer is thin: heavy hubs must live in environment.yml."""
from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]

# Packages that MUST be installed via conda/mamba, NOT listed in pyproject.
# Pip-only packages (no conda recipe at Task 0 audit) are NOT in CONDA_OWNED
# and stay in pyproject: SpaGCN, GraphST, cellcharter, paste-bio, flashdeconv,
# fastccc, pyVIA, pybanksy, ccproxy-api, tangram-sc, deepagents,
# opendataloader-pdf, torch_geometric, liana, phate, python-multipart, langchain*,
# langgraph*, tavily-python, markdownify, pypdf, textual.
# 'unknown' packages (Task 0 audit could not classify): cell2location,
# cellphonedb, infercnvpy, SpatialDE — also absent from CONDA_OWNED, pending
# network re-audit.
CONDA_OWNED = {
    "scanpy", "anndata", "squidpy", "numpy", "pandas", "scipy",
    "scikit-learn", "matplotlib", "seaborn", "pillow", "scikit-misc",
    "igraph", "python-igraph", "leidenalg", "louvain", "umap-learn", "pydantic",
    "nbformat", "jupyter-client", "ipykernel", "rich", "greenlet",
    "prompt-toolkit", "questionary", "pyyaml", "aiosqlite", "sqlalchemy",
    "fastapi", "uvicorn", "cryptography", "requests", "openai",
    "python-dotenv", "httpx",
    "torch", "pytorch", "pytorch-cpu",
    "jinja2", "nbconvert", "beautifulsoup4",
    "scvi-tools", "scvelo", "cellrank",
    "harmonypy", "bbknn", "scanorama", "celltypist",
    "gseapy", "pydeseq2", "scrublet", "doubletdetection", "arboreto",
    "palantir", "multiqc", "kb-python", "esda", "libpysal", "pysal",
    "pot",
    "coloredlogs", "humanfriendly",
}


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
