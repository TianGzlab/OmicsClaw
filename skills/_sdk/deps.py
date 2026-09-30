"""Optional dependencies of OmicsClaw skills: one registry and the functions that read it.

``DEPENDENCIES`` maps a PyPI project name to a pure-literal entry, so tools
outside this package can read it with ``ast.literal_eval`` without importing
it. Every entry has:

* ``module`` — the import name probed for ``pip``/``git`` entries (it may be a
  representative module, e.g. ``NaiveDE`` for ``SpatialDE``), or the R package
  name for ``r`` entries;
* ``kind`` — ``"pip"``, ``"git"`` (installed from a repository) or ``"r"``;
* ``install`` — the full install command; for ``pip`` entries always
  ``"pip install " + " ".join([key, *also])``;
* ``description``.

Optional fields: ``also`` (further PyPI projects a ``pip`` entry installs
together with its key) and ``alt_env`` (a conda environment whose presence
also counts as available).

A name is resolved in a fixed order: exact key, PEP 503-normalised key,
exact ``module``, and finally a fallback that treats the name as its own
PyPI project and import name.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import re
import subprocess
import sys
import warnings
from functools import lru_cache
from typing import Any

from skills._sdk import external_env

__all__ = [
    "DEPENDENCIES",
    "require",
    "get",
    "is_available",
    "install_hint",
    "validate_r_environment",
]

DEPENDENCIES: dict[str, dict] = {
    "arboreto": {
        "module": "arboreto",
        "kind": "pip",
        "install": "pip install arboreto",
        "description": "GRNBoost2 inference",
    },
    "bbknn": {
        "module": "bbknn",
        "kind": "pip",
        "install": "pip install bbknn",
        "description": "Batch balanced k-nearest neighbours (BBKNN)",
    },
    "cell2location": {
        "module": "cell2location",
        "kind": "pip",
        "install": "pip install cell2location",
        "description": "Probabilistic cell type deconvolution (Cell2Location)",
    },
    "cellbender": {
        "module": "cellbender",
        "kind": "pip",
        "install": "pip install cellbender",
        "description": "CellBender ambient RNA removal",
    },
    "cellcharter": {
        "module": "cellcharter",
        "kind": "pip",
        "install": "pip install cellcharter",
        "description": "Spatial domain identification and auto-K selection (CellCharter)",
    },
    "cellphonedb": {
        "module": "cellphonedb",
        "kind": "pip",
        "install": "pip install cellphonedb",
        "description": "Statistical cell-cell communication (CellPhoneDB)",
    },
    "cellrank": {
        "module": "cellrank",
        "kind": "pip",
        "install": "pip install cellrank",
        "description": "Trajectory inference using RNA velocity (CellRank)",
    },
    "celltypist": {
        "module": "celltypist",
        "kind": "pip",
        "install": "pip install celltypist",
        "description": "CellTypist annotation",
    },
    "cnmf": {
        "module": "cnmf",
        "kind": "pip",
        "install": "pip install cnmf",
        "description": "Consensus NMF gene programs (cNMF)",
    },
    "doubletdetection": {
        "module": "doubletdetection",
        "kind": "pip",
        "install": "pip install doubletdetection",
        "description": "DoubletDetection consensus doublet calling",
    },
    "esda": {
        "module": "esda",
        "kind": "pip",
        "install": "pip install esda",
        "description": "Exploratory spatial data analysis (esda)",
    },
    "fastccc": {
        "module": "fastccc",
        "kind": "pip",
        "install": "pip install fastccc",
        "description": "FFT-based cell communication without permutation (FastCCC)",
    },
    "flashdeconv": {
        "module": "flashdeconv",
        "kind": "pip",
        "install": "pip install flashdeconv",
        "description": "Ultra-fast spatial deconvolution (FlashDeconv)",
    },
    "flashs": {
        "module": "flashs",
        "kind": "pip",
        "install": "pip install flashs",
        "description": "Ultra-fast Python-native spatial gene detection (FlashS)",
    },
    "GraphST": {
        "module": "GraphST",
        "kind": "pip",
        "install": "pip install GraphST",
        "description": "Graph self-supervised contrastive learning (GraphST)",
    },
    "gseapy": {
        "module": "gseapy",
        "kind": "pip",
        "install": "pip install gseapy",
        "description": "Gene set enrichment analysis (GSEApy)",
    },
    "harmonypy": {
        "module": "harmonypy",
        "kind": "pip",
        "install": "pip install harmonypy",
        "description": "Harmony batch integration",
    },
    "igraph": {
        "module": "igraph",
        "kind": "pip",
        "install": "pip install igraph",
        "description": "igraph graph backend",
    },
    "infercnvpy": {
        "module": "infercnvpy",
        "kind": "pip",
        "install": "pip install infercnvpy",
        "description": "Copy number variation inference (inferCNVpy)",
    },
    "leidenalg": {
        "module": "leidenalg",
        "kind": "pip",
        "install": "pip install leidenalg",
        "description": "Leiden clustering backend",
    },
    "liana": {
        "module": "liana",
        "kind": "pip",
        "install": "pip install liana",
        "description": "Ligand-receptor analysis (LIANA+)",
    },
    "libpysal": {
        "module": "libpysal",
        "kind": "pip",
        "install": "pip install libpysal",
        "description": "Python spatial analysis library (libpysal)",
    },
    "louvain": {
        "module": "louvain",
        "kind": "pip",
        "install": "pip install louvain",
        "description": "Louvain graph clustering",
    },
    "metaboanalyst": {
        "module": "MetaboAnalystR",
        "kind": "r",
        "install": 'Rscript -e \'install.packages("MetaboAnalystR")\'',
        "description": "MetaboAnalyst via native R scripts",
    },
    "mllmcelltype": {
        "module": "mllmcelltype",
        "kind": "pip",
        "install": "pip install mllmcelltype",
        "description": "LLM-assisted cell type annotation (mLLMCelltype)",
    },
    "mofapy2": {
        "module": "mofapy2",
        "kind": "pip",
        "install": "pip install mofapy2",
        "description": "MOFA+ factor analysis",
    },
    "mokapot": {
        "module": "mokapot",
        "kind": "pip",
        "install": "pip install mokapot",
        "description": "PSM rescoring",
    },
    "ms-entropy": {
        "module": "ms_entropy",
        "kind": "pip",
        "install": "pip install ms-entropy",
        "description": "Spectral entropy",
    },
    "ms2pip": {
        "module": "ms2pip",
        "kind": "pip",
        "install": "pip install ms2pip",
        "description": "Peptide fragmentation prediction",
    },
    "muon": {
        "module": "muon",
        "kind": "pip",
        "install": "pip install muon",
        "description": "Multi-omics analysis",
    },
    "omicverse": {
        "module": "omicverse",
        "kind": "pip",
        "install": "pip install omicverse",
        "description": "OmicVerse multi-omics analysis toolkit",
    },
    "palantir": {
        "module": "palantir",
        "kind": "pip",
        "install": "pip install palantir",
        "description": "Diffusion-based trajectory inference (Palantir)",
    },
    "paste-bio": {
        "module": "paste",
        "kind": "pip",
        "install": "pip install paste-bio",
        "description": "Probabilistic alignment of spatial transcriptomics (PASTE)",
    },
    "pertpy": {
        "module": "pertpy",
        "kind": "pip",
        "install": "pip install pertpy",
        "description": "Perturbation analysis (Augur, Milo, Mixscape, ...)",
    },
    "phate": {
        "module": "phate",
        "kind": "pip",
        "install": "pip install phate",
        "description": "PHATE nonlinear embedding",
    },
    "popv": {
        "module": "popv",
        "kind": "pip",
        "install": "pip install popv",
        "description": "PopV consensus cell-type annotation",
    },
    "POT": {
        "module": "ot",
        "kind": "pip",
        "install": "pip install POT",
        "description": "Python Optimal Transport library (POT)",
    },
    "pybanksy": {
        "module": "banksy",
        "kind": "git",
        "alt_env": "omicsclaw_banksy",
        "install": "pip install git+https://github.com/prabhakarlab/Banksy_py.git",
        "description": "Spatial domain identification (BANKSY; in-process or omicsclaw_banksy sub-env)",
    },
    "pydeseq2": {
        "module": "pydeseq2",
        "kind": "pip",
        "install": "pip install pydeseq2",
        "description": "Python implementation of DESeq2 (PyDESeq2)",
    },
    "pymzml": {
        "module": "pymzml",
        "kind": "pip",
        "install": "pip install pymzml",
        "description": "mzML parsing",
    },
    "pyscenic": {
        "module": "pyscenic",
        "kind": "pip",
        "install": "pip install pyscenic",
        "description": "SCENIC gene-regulatory-network inference",
    },
    "pyteomics": {
        "module": "pyteomics",
        "kind": "pip",
        "install": "pip install pyteomics",
        "description": "MS data parsing",
    },
    "pyVIA": {
        "module": "pyVIA",
        "kind": "pip",
        "install": "pip install pyVIA",
        "description": "VIA pseudotime",
    },
    "scanorama": {
        "module": "scanorama",
        "kind": "pip",
        "install": "pip install scanorama",
        "description": "Scanorama batch integration",
    },
    "sccoda": {
        "module": "sccoda",
        "kind": "pip",
        "install": "pip install sccoda",
        "description": "scCODA Bayesian compositional analysis",
    },
    "scrublet": {
        "module": "scrublet",
        "kind": "pip",
        "install": "pip install scrublet",
        "description": "Scrublet doublet detection",
    },
    "scvelo": {
        "module": "scvelo",
        "kind": "pip",
        "install": "pip install scvelo",
        "description": "RNA velocity (scVelo)",
    },
    "scvi-tools": {
        "module": "scvi",
        "kind": "pip",
        "install": "pip install scvi-tools",
        "description": "Single-cell variational inference",
    },
    "seaborn": {
        "module": "seaborn",
        "kind": "pip",
        "install": "pip install seaborn",
        "description": "Statistical plotting",
    },
    "SEACells": {
        "module": "SEACells",
        "kind": "pip",
        "install": "pip install SEACells",
        "description": "SEACells metacell inference",
    },
    "simba-bio": {
        "module": "simba",
        "kind": "pip",
        "install": "pip install simba-bio",
        "description": "SIMBA single-cell graph embedding",
    },
    "singler": {
        "module": "singler",
        "kind": "pip",
        "also": ["singlecellexperiment"],
        "install": "pip install singler singlecellexperiment",
        "description": "Reference-based cell type annotation (SingleR/singler)",
    },
    "SpaGCN": {
        "module": "SpaGCN",
        "kind": "pip",
        "install": "pip install SpaGCN",
        "description": "Spatial domain identification (SpaGCN)",
    },
    "SpatialDE": {
        "module": "NaiveDE",
        "kind": "pip",
        "install": "pip install SpatialDE",
        "description": "Gaussian process spatial gene detection (SpatialDE)",
    },
    "squidpy": {
        "module": "squidpy",
        "kind": "pip",
        "install": "pip install squidpy",
        "description": "Spatial single-cell analysis",
    },
    "STAGATE-pyG": {
        "module": "STAGATE_pyG",
        "kind": "git",
        "install": "pip install git+https://github.com/RucDongLab/STAGATE_pyG.git",
        "description": "Spatial domain identification (STAGATE; GitHub-only, needs PyTorch Geometric)",
    },
    "STalign": {
        "module": "STalign",
        "kind": "git",
        "install": "pip install git+https://github.com/JEFworks-Lab/STalign.git",
        "description": "Spatial transcriptomics alignment (STalign; GitHub-only)",
    },
    "tangram-sc": {
        "module": "tangram",
        "kind": "pip",
        "install": "pip install tangram-sc",
        "description": "Spatial mapping of single-cell data (Tangram)",
    },
    "torch": {
        "module": "torch",
        "kind": "pip",
        "install": "pip install torch",
        "description": "PyTorch deep learning framework",
    },
    "velovi": {
        "module": "velovi",
        "kind": "pip",
        "install": "pip install velovi",
        "description": "Variational inference for RNA velocity (VELOVI)",
    },
    "xcms": {
        "module": "xcms",
        "kind": "r",
        "install": 'Rscript -e \'BiocManager::install("xcms")\'',
        "description": "XCMS via native R scripts",
    },
}


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


_BY_NORMALISED = {_normalise(key): key for key in DEPENDENCIES}
_BY_MODULE = {entry["module"]: key for key, entry in DEPENDENCIES.items()}


def _resolve(name: str) -> tuple[str | None, dict[str, Any]]:
    """The registry key and entry for *name*; ``(None, fallback entry)`` when unregistered."""
    if name in DEPENDENCIES:
        return name, DEPENDENCIES[name]
    key = _BY_NORMALISED.get(_normalise(name)) or _BY_MODULE.get(name)
    if key is not None:
        return key, DEPENDENCIES[key]
    return None, {"module": name, "kind": "pip", "install": f"pip install {name}", "description": ""}


@lru_cache(maxsize=256)
def _try_import(module_name: str) -> Any | None:
    try:
        return importlib.import_module(module_name)
    except ImportError:
        return None


@lru_cache(maxsize=256)
def _check_spec(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


@lru_cache(maxsize=64)
def _r_package_available(package: str) -> bool:
    try:
        if not _check_r_available():
            return False
        from skills._sdk import r_script_runner

        return not r_script_runner.RScriptRunner(verbose=False).get_missing_packages([package])
    except Exception:
        return False


def _python_module(name: str) -> tuple[str, dict[str, Any]]:
    _key, entry = _resolve(name)
    if entry["kind"] == "r":
        raise TypeError(f"{name} is an R package; use validate_r_environment")
    return entry["module"], entry


def is_available(name: str) -> bool:
    """Whether the dependency *name* is usable here; never raises.

    ``pip``/``git`` entries: the module can be found without importing it
    (cached per module); if not and the entry has ``alt_env``, whether that
    conda environment exists (not cached; a failing probe counts as absent).
    ``r`` entries: R is available and the R package is installed (cached per
    package; any failure, including a missing ``Rscript``, gives ``False``).

    :param name: A registry key, any spelling that normalises to one, an
        import name, or an unregistered name.
    """
    _key, entry = _resolve(name)
    if entry["kind"] == "r":
        return _r_package_available(entry["module"])
    if _check_spec(entry["module"]):
        return True
    if "alt_env" in entry:
        try:
            return bool(external_env.is_env_available(entry["alt_env"]))
        except Exception:
            return False
    return False


def get(name: str, *, warn_if_missing: bool = False) -> Any | None:
    """The imported module for *name*, or ``None`` when it cannot be imported.

    :param warn_if_missing: Emit a ``UserWarning`` with the install command when missing.
    :raises TypeError: If *name* is an R package.
    """
    module_name, entry = _python_module(name)
    module = _try_import(module_name)
    if module is None and warn_if_missing:
        warnings.warn(f"{name} not available. Install with: {entry['install']}", stacklevel=2)
    return module


def require(name: str, *, feature: str = "") -> Any:
    """The imported module for *name*.

    :param feature: What the caller needs it for, shown in the error message.
    :raises ImportError: If the module cannot be imported; the message gives
        the install command and *feature*.
    :raises TypeError: If *name* is an R package.
    """
    module_name, entry = _python_module(name)
    module = _try_import(module_name)
    if module is not None:
        return module
    context = f" for {feature}" if feature else ""
    raise ImportError(
        f"'{name}' is required{context} but is not installed.\n\n"
        f"Install:     {entry['install']}\n"
        f"Description: {entry['description'] or name}"
    )


def install_hint(name: str) -> str:
    """A one-line, human-readable install hint for *name*."""
    _key, entry = _resolve(name)
    return f"{entry['description'] or name}: install with `{entry['install']}`"


def _check_r_available() -> bool:
    """Whether an ``Rscript`` (the active conda env's first, then ``PATH``) runs."""
    candidates = []
    conda_prefix = os.environ.get("CONDA_PREFIX", "").strip()
    if conda_prefix:
        candidates.append(os.path.join(conda_prefix, "bin", "Rscript"))
    if sys.prefix:
        candidates.append(os.path.join(sys.prefix, "bin", "Rscript"))
    candidates.append("Rscript")

    try:
        for rscript in dict.fromkeys(candidates):
            try:
                result = subprocess.run(
                    [rscript, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except FileNotFoundError:
                continue
            if result.returncode == 0:
                return True
        return False
    except subprocess.TimeoutExpired:
        return False


def validate_r_environment(
    required_r_packages: list[str] | None = None,
) -> bool:
    """Check that R is available and *required_r_packages* are installed.

    :returns: ``True`` when every check passes.
    :raises ImportError: If R is not available or packages are missing; the
        message says how to install them.
    """
    if not _check_r_available():
        raise ImportError(
            "[OmicsClaw] R is not available.\n"
            "Install R (>= 4.3) and ensure 'Rscript' is on your PATH.\n"
            "The recommended path is `bash 0_setup_env.sh` which provisions\n"
            "R 4.3 and all required packages via mamba/conda."
        )

    if required_r_packages:
        from .r_script_runner import RScriptRunner

        runner = RScriptRunner(verbose=False)
        missing = runner.get_missing_packages(required_r_packages)
        if missing:
            raise ImportError(
                f"[OmicsClaw] Missing R packages: {', '.join(missing)}.\n"
                f"The recommended path is `bash 0_setup_env.sh` which provisions\n"
                f"R 4.3 and all required packages via mamba/conda.\n"
                f"Or manually: Rscript -e 'BiocManager::install(c({', '.join(repr(p) for p in missing)}))'"
            )

    return True
