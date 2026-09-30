"""A fixture registry in the shape of skills/_sdk/deps.py, read by AST only."""

DEPENDENCIES: dict[str, dict] = {
    "pybanksy": {
        "module": "banksy",
        "kind": "git",
        "alt_env": "omicsclaw_banksy",
        "install": "pip install git+https://github.com/prabhakarlab/Banksy_py.git",
        "description": "BANKSY",
    },
    "xcms": {
        "module": "xcms",
        "kind": "r",
        "install": "Rscript -e 'BiocManager::install(\"xcms\")'",
        "description": "XCMS",
    },
}
