"""Unified optional-dependency management for SpatialClaw skills.

Adapted from ChatSpatial's dependency_manager with ToolContext removed
so it works in SpatialClaw's sync CLI environment.

Usage::

    from skills.spatial._lib.dependency_manager import require, get, is_available

    # Require a dependency — raises ImportError with install instructions if missing
    scvi = require("scvi-tools", feature="cell type annotation")

    # Optional dependency — returns None if missing
    torch = get("torch")

    # Lightweight availability check (no import, cached)
    if is_available("squidpy"):
        import squidpy
"""

from __future__ import annotations

import importlib
import importlib.util
import warnings
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Optional


@dataclass(frozen=True)
class DependencyInfo:
    """Metadata for an optional dependency."""

    module_name: str      # Python import name (e.g. "scvi" for scvi-tools)
    install_cmd: str      # pip install command
    description: str = ""


# ---------------------------------------------------------------------------
# Central registry: canonical name → install info
# ---------------------------------------------------------------------------

DEPENDENCY_REGISTRY: dict[str, DependencyInfo] = {
    # ── Deep learning ────────────────────────────────────────────────────────
    "scvi-tools": DependencyInfo(
        "scvi", "pip install scvi-tools", "Single-cell variational inference"
    ),
    "torch": DependencyInfo(
        "torch", "pip install torch", "PyTorch deep learning framework"
    ),
    "cell2location": DependencyInfo(
        "cell2location", "pip install cell2location",
        "Probabilistic cell type deconvolution (Cell2Location)"
    ),
    "flashdeconv": DependencyInfo(
        "flashdeconv", "pip install flashdeconv",
        "Ultra-fast spatial deconvolution (FlashDeconv)"
    ),
    # ── Spatial analysis ─────────────────────────────────────────────────────
    "tangram-sc": DependencyInfo(
        "tangram", "pip install tangram-sc",
        "Spatial mapping of single-cell data (Tangram)"
    ),
    "squidpy": DependencyInfo(
        "squidpy", "pip install squidpy", "Spatial single-cell analysis"
    ),
    "SpaGCN": DependencyInfo(
        "SpaGCN", "pip install SpaGCN",
        "Spatial domain identification (SpaGCN)"
    ),
    "STAGATE-pyG": DependencyInfo(
        "STAGATE_pyG", "pip install STAGATE-pyG",
        "Spatial domain identification (STAGATE)"
    ),
    "GraphST": DependencyInfo(
        "GraphST", "pip install GraphST",
        "Graph self-supervised contrastive learning (GraphST)"
    ),
    "pybanksy": DependencyInfo(
        "banksy", "pip install pybanksy",
        "Spatial domain identification (BANKSY)"
    ),
    "cellcharter": DependencyInfo(
        "cellcharter", "pip install cellcharter",
        "Spatial domain identification and auto-K selection (CellCharter)"
    ),
    "paste-bio": DependencyInfo(
        "paste", "pip install paste-bio",
        "Probabilistic alignment of spatial transcriptomics (PASTE)"
    ),
    "STalign": DependencyInfo(
        "STalign", "pip install STalign",
        "Spatial transcriptomics alignment (STalign)"
    ),
    # ── Cell communication ───────────────────────────────────────────────────
    "liana": DependencyInfo(
        "liana", "pip install liana",
        "Ligand-receptor analysis (LIANA+)"
    ),
    "cellphonedb": DependencyInfo(
        "cellphonedb", "pip install cellphonedb",
        "Statistical cell-cell communication (CellPhoneDB)"
    ),
    "fastccc": DependencyInfo(
        "fastccc", "pip install fastccc",
        "FFT-based cell communication without permutation (FastCCC)"
    ),
    # ── RNA velocity ─────────────────────────────────────────────────────────
    "scvelo": DependencyInfo(
        "scvelo", "pip install scvelo", "RNA velocity (scVelo)"
    ),
    "velovi": DependencyInfo(
        "velovi", "pip install velovi",
        "Variational inference for RNA velocity (VELOVI)"
    ),
    "cellrank": DependencyInfo(
        "cellrank", "pip install cellrank",
        "Trajectory inference using RNA velocity (CellRank)"
    ),
    "palantir": DependencyInfo(
        "palantir", "pip install palantir",
        "Diffusion-based trajectory inference (Palantir)"
    ),
    # ── Cell type annotation ─────────────────────────────────────────────────
    "singler": DependencyInfo(
        "singler", "pip install singler singlecellexperiment",
        "Reference-based cell type annotation (SingleR/singler)"
    ),
    "mllmcelltype": DependencyInfo(
        "mllmcelltype", "pip install mllmcelltype",
        "LLM-assisted cell type annotation (mLLMCelltype)"
    ),
    # ── Enrichment ───────────────────────────────────────────────────────────
    "gseapy": DependencyInfo(
        "gseapy", "pip install gseapy",
        "Gene set enrichment analysis (GSEApy)"
    ),
    # ── Spatially variable genes ─────────────────────────────────────────────
    "spatialde": DependencyInfo(
        "NaiveDE", "pip install SpatialDE",
        "Gaussian process spatial gene detection (SpatialDE)"
    ),
    "flashs": DependencyInfo(
        "flashs", "pip install flashs",
        "Ultra-fast Python-native spatial gene detection (FlashS)"
    ),
    # ── CNV ──────────────────────────────────────────────────────────────────
    "infercnvpy": DependencyInfo(
        "infercnvpy", "pip install infercnvpy",
        "Copy number variation inference (inferCNVpy)"
    ),
    # ── Integration ──────────────────────────────────────────────────────────
    "harmonypy": DependencyInfo(
        "harmonypy", "pip install harmonypy",
        "Harmony batch integration"
    ),
    "scanorama": DependencyInfo(
        "scanorama", "pip install scanorama",
        "Scanorama batch integration"
    ),
    "bbknn": DependencyInfo(
        "bbknn", "pip install bbknn",
        "Batch balanced k-nearest neighbours (BBKNN)"
    ),
    # ── Spatial statistics ───────────────────────────────────────────────────
    "esda": DependencyInfo(
        "esda", "pip install esda",
        "Exploratory spatial data analysis (esda)"
    ),
    "libpysal": DependencyInfo(
        "libpysal", "pip install libpysal",
        "Python spatial analysis library (libpysal)"
    ),
    # ── Condition comparison ─────────────────────────────────────────────────
    "pydeseq2": DependencyInfo(
        "pydeseq2", "pip install pydeseq2",
        "Python implementation of DESeq2 (PyDESeq2)"
    ),
    # ── Optimal transport / registration ─────────────────────────────────────
    "POT": DependencyInfo(
        "ot", "pip install POT",
        "Python Optimal Transport library (POT)"
    ),
}


# ---------------------------------------------------------------------------
# Internal helpers (all results are LRU-cached for performance)
# ---------------------------------------------------------------------------

def _get_info(name: str) -> DependencyInfo:
    """Return DependencyInfo for *name*, falling back to defaults if unknown."""
    if name in DEPENDENCY_REGISTRY:
        return DEPENDENCY_REGISTRY[name]
    # Search by module_name in case the caller used the import name directly
    for info in DEPENDENCY_REGISTRY.values():
        if info.module_name == name:
            return info
    # Unknown dependency — build a sensible default
    return DependencyInfo(name, f"pip install {name}", f"Optional: {name}")


@lru_cache(maxsize=256)
def _try_import(module_name: str) -> Optional[Any]:
    """Import *module_name* with caching. Returns ``None`` if unavailable."""
    try:
        return importlib.import_module(module_name)
    except ImportError:
        return None


@lru_cache(maxsize=256)
def _check_spec(module_name: str) -> bool:
    """Fast availability check via ``importlib.util.find_spec`` (no import)."""
    return importlib.util.find_spec(module_name) is not None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_available(name: str) -> bool:
    """Return ``True`` if *name* can be imported (fast, no side effects).

    Parameters
    ----------
    name:
        Registry key (e.g. ``"scvi-tools"``) or Python import name.
    """
    return _check_spec(_get_info(name).module_name)


def get(name: str, *, warn_if_missing: bool = False) -> Optional[Any]:
    """Return the imported module for *name*, or ``None`` if unavailable.

    Parameters
    ----------
    name:
        Registry key or Python import name.
    warn_if_missing:
        Emit a :class:`UserWarning` when the package is missing.
    """
    info = _get_info(name)
    module = _try_import(info.module_name)
    if module is None and warn_if_missing:
        warnings.warn(
            f"{name} not available. Install with: {info.install_cmd}",
            stacklevel=2,
        )
    return module


def require(name: str, *, feature: str = "") -> Any:
    """Return the imported module for *name*, raising if unavailable.

    Parameters
    ----------
    name:
        Registry key (e.g. ``"scvi-tools"``) or Python import name.
    feature:
        Human-readable context shown in the error message
        (e.g. ``"RNA velocity"``).

    Raises
    ------
    ImportError
        With clear install instructions if the package is missing.
    """
    info = _get_info(name)
    module = _try_import(info.module_name)
    if module is not None:
        return module
    context = f" for {feature}" if feature else ""
    raise ImportError(
        f"'{name}' is required{context} but is not installed.\n\n"
        f"Install:     {info.install_cmd}\n"
        f"Description: {info.description}\n\n"
        "For all optional methods, run:\n"
        "    pip install -e \".[full]\""
    )


# ---------------------------------------------------------------------------
# R environment helpers
# ---------------------------------------------------------------------------

def validate_r_environment(
    required_r_packages: Optional[list[str]] = None,
) -> bool:
    """Validate that R is available and required packages are installed.

    Uses subprocess (not rpy2) — consistent with the native R script approach.

    Returns True if R and all required packages are available.
    Raises ImportError if R or required packages are missing.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["Rscript", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            raise ImportError("Rscript not found or returned an error.")
    except FileNotFoundError:
        raise ImportError(
            "R is not installed or Rscript is not on PATH.\n"
            "Install R from https://cran.r-project.org/"
        )

    if required_r_packages:
        checks = "; ".join(
            f'cat("{pkg}:", requireNamespace("{pkg}", quietly=TRUE), "\\n")'
            for pkg in required_r_packages
        )
        result = subprocess.run(
            ["Rscript", "-e", checks],
            capture_output=True, text=True, timeout=30,
        )
        missing = []
        for line in result.stdout.strip().splitlines():
            if ":" in line:
                parts = line.split(":", 1)
                pkg = parts[0].strip()
                val = parts[1].strip().upper()
                if val != "TRUE":
                    missing.append(pkg)
        if missing:
            pkg_list = ", ".join(f"'{p}'" for p in missing)
            raise ImportError(
                f"Missing R packages: {pkg_list}\n"
                "Install with:\n"
                "  Rscript -e 'install.packages(c(\"pkg1\", \"pkg2\"))'"
            )

    return True
