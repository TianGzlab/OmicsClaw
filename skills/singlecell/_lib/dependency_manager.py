"""Dependency management for single-cell analysis methods."""

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

    module_name: str
    install_cmd: str
    description: str = ""


DEPENDENCY_REGISTRY: dict[str, DependencyInfo] = {
    # Deep learning
    "scvi-tools": DependencyInfo("scvi", "pip install scvi-tools", "scVI variational inference"),
    "torch": DependencyInfo("torch", "pip install torch", "PyTorch"),
    "cellbender": DependencyInfo("cellbender", "pip install cellbender", "CellBender ambient RNA removal"),

    # Integration
    "harmonypy": DependencyInfo("harmonypy", "pip install harmonypy", "Harmony batch correction"),
    "bbknn": DependencyInfo("bbknn", "pip install bbknn", "BBKNN batch correction"),
    "scanorama": DependencyInfo("scanorama", "pip install scanorama", "Scanorama integration"),
    "louvain": DependencyInfo("louvain", "pip install louvain", "Louvain graph clustering"),
    "phate": DependencyInfo("phate", "pip install phate", "PHATE nonlinear embedding"),

    # Annotation
    "celltypist": DependencyInfo("celltypist", "pip install celltypist", "CellTypist annotation"),

    # Doublet detection
    "scrublet": DependencyInfo("scrublet", "pip install scrublet", "Scrublet doublet detection"),

    # Communication
    "liana": DependencyInfo("liana", "pip install liana", "LIANA+ L-R analysis"),
    "seaborn": DependencyInfo("seaborn", "pip install seaborn", "Statistical plotting"),

    # GRN
    "arboreto": DependencyInfo("arboreto", "pip install arboreto", "GRNBoost2 inference"),

    # Trajectory
    "scvelo": DependencyInfo("scvelo", "pip install scvelo", "RNA velocity"),
    "cellrank": DependencyInfo("cellrank", "pip install cellrank", "CellRank trajectory"),
    "palantir": DependencyInfo("palantir", "pip install palantir", "Palantir pseudotime"),

    # Multiome
    "muon": DependencyInfo("muon", "pip install muon", "Multi-omics analysis"),
    "mofapy2": DependencyInfo("mofapy2", "pip install mofapy2", "MOFA+ factor analysis"),

    # DE
    "pydeseq2": DependencyInfo("pydeseq2", "pip install pydeseq2", "DESeq2 in Python"),
}


@lru_cache(maxsize=256)
def _try_import(module_name: str) -> Optional[Any]:
    """Import module with caching."""
    try:
        return importlib.import_module(module_name)
    except ImportError:
        return None


@lru_cache(maxsize=256)
def _check_spec(module_name: str) -> bool:
    """Fast availability check."""
    return importlib.util.find_spec(module_name) is not None



def _get_info(name: str) -> DependencyInfo:
    """Get dependency info."""
    if name in DEPENDENCY_REGISTRY:
        return DEPENDENCY_REGISTRY[name]
    for info in DEPENDENCY_REGISTRY.values():
        if info.module_name == name:
            return info
    return DependencyInfo(name, f"pip install {name}", f"Optional: {name}")



def is_available(name: str) -> bool:
    """Check if dependency is available."""
    return _check_spec(_get_info(name).module_name)



def get(name: str, *, warn_if_missing: bool = False) -> Optional[Any]:
    """Get module or None."""
    info = _get_info(name)
    module = _try_import(info.module_name)
    if module is None and warn_if_missing:
        warnings.warn(f"{name} not available. Install: {info.install_cmd}", stacklevel=2)
    return module



def require(name: str, *, feature: str = "") -> Any:
    """Require module or raise."""
    info = _get_info(name)
    module = _try_import(info.module_name)
    if module is not None:
        return module
    context = f" for {feature}" if feature else ""
    raise ImportError(
        f"'{name}' is required{context} but not installed.\n\n"
        f"Install: {info.install_cmd}\n"
        f"Description: {info.description}"
    )


def install_hint(name: str) -> str:
    """Return a human-readable install hint for an optional dependency."""
    info = _get_info(name)
    return f"{info.description or name}: install with `{info.install_cmd}`"



def validate_r_environment(
    required_r_packages: Optional[list[str]] = None,
) -> bool:
    """Validate that R is available and required packages are installed.

    Uses subprocess (not rpy2) — consistent with the native R script approach.

    Returns True if R and all required packages are available.
    Raises ImportError if R or required packages are missing.
    """
    import subprocess

    # Check R availability
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
