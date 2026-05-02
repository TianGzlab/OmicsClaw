"""Verify pyproject's pip layer is thin: heavy hubs must live in environment.yml."""
from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]

# Packages that MUST be installed via conda/mamba, NOT listed in pyproject.
# cellphonedb is intentionally absent — it's marked `unknown` in the Task 0
# audit and stays in pyproject pending network re-verification.
CONDA_OWNED = {
    "scanpy", "anndata", "squidpy", "numpy", "pandas", "scipy",
    "scikit-learn", "matplotlib", "seaborn", "pillow", "scikit-misc",
    "igraph", "leidenalg", "louvain", "umap-learn", "pydantic",
    "nbformat", "jupyter-client", "ipykernel", "rich", "greenlet",
    "prompt-toolkit", "questionary", "pyyaml", "aiosqlite", "sqlalchemy",
    "fastapi", "uvicorn", "cryptography", "requests", "openai",
    "python-dotenv", "httpx", "torch", "scvi-tools", "scvelo", "cellrank",
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
