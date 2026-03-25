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

    # R interface
    "rpy2": DependencyInfo("rpy2", "pip install rpy2", "R-Python interface (requires R installed)"),
    "anndata2ri": DependencyInfo("anndata2ri", "pip install anndata2ri", "AnnData-R bridge"),

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



def validate_r_environment(
    required_r_packages: Optional[list[str]] = None,
) -> tuple[Any, ...]:
    """Validate R + rpy2 + anndata2ri and return commonly used bridge objects."""
    require("rpy2", feature="R-based single-cell methods")
    require("anndata2ri", feature="R-based single-cell methods")

    try:
        import anndata2ri
        import rpy2.robjects as robjects
        from rpy2.rinterface_lib import openrlib
        from rpy2.robjects import conversion, default_converter, numpy2ri, pandas2ri
        from rpy2.robjects.conversion import localconverter
        from rpy2.robjects.packages import importr

        with openrlib.rlock:
            with conversion.localconverter(default_converter):
                robjects.r("R.version")

        if required_r_packages:
            missing = []
            for pkg in required_r_packages:
                try:
                    with openrlib.rlock:
                        with conversion.localconverter(default_converter):
                            importr(pkg)
                except Exception:
                    missing.append(pkg)
            if missing:
                pkg_list = ", ".join(f"'{p}'" for p in missing)
                raise ImportError(
                    "Missing R packages: "
                    f"{pkg_list}\n"
                    "Install the Python bridge with:\n"
                    "  pip install rpy2 anndata2ri\n"
                    "Install the R dependencies with:\n"
                    "  Rscript install_r_dependencies.R"
                )

        return (
            robjects,
            pandas2ri,
            numpy2ri,
            importr,
            localconverter,
            default_converter,
            openrlib,
            anndata2ri,
        )
    except ImportError:
        raise
    except Exception as exc:
        raise ImportError(
            "Failed to initialise the R bridge for single-cell methods.\n"
            "Make sure R is installed and visible on PATH, then install:\n"
            "  pip install rpy2 anndata2ri\n"
            "  Rscript install_r_dependencies.R\n"
            f"Original error: {exc}"
        ) from exc
