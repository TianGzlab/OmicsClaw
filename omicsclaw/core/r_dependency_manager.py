"""R package dependency management for OmicsClaw.

Mirrors the Python ``DOMAIN_TIERS`` pattern: maps R packages to skill tiers,
checks installation status via ``RScriptRunner``, and generates install
commands that distinguish CRAN from Bioconductor sources.

Usage::

    from omicsclaw.core.r_dependency_manager import (
        check_r_tier, get_r_tier_status, suggest_r_install,
    )

    # Check one tier
    installed, missing = check_r_tier("bulkrna-de")
    if missing:
        print(suggest_r_install(missing))

    # Overview of all tiers
    for tier, info in get_r_tier_status().items():
        print(f"{tier}: {info['status']}")
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tier definitions — which R packages each skill tier requires
# ---------------------------------------------------------------------------

R_TIER_PACKAGES: dict[str, list[str]] = {
    # Single-cell
    "singlecell-preprocessing": [
        "Seurat",
        "SingleCellExperiment",
        "zellkonverter",
    ],
    "singlecell-doublet-detection": [
        "Seurat",
        "DoubletFinder",
        "scDblFinder",
        "scds",
        "SingleCellExperiment",
        "zellkonverter",
    ],
    "singlecell-cell-annotation": [
        "SingleR",
        "scmap",
        "celldex",
        "SingleCellExperiment",
        "zellkonverter",
    ],
    "singlecell-ambient": [
        "Seurat",
        "SoupX",
    ],
    "singlecell-batch-integration": [
        "Seurat",
        "batchelor",
        "SingleCellExperiment",
        "zellkonverter",
    ],
    "singlecell-communication": [
        "CellChat",
        "SingleCellExperiment",
        "zellkonverter",
        "nichenetr",
        "Seurat",
    ],
    "singlecell-de": [
        "MAST",
        "DESeq2",
        "SingleCellExperiment",
        "zellkonverter",
    ],
    "singlecell-pathway-scoring": [
        "AUCell",
        "GSEABase",
    ],
    "singlecell-pseudotime": [
        "slingshot",
        "SingleCellExperiment",
        "zellkonverter",
    ],
    "singlecell-enrichment": [
        "clusterProfiler",
        "enrichplot",
    ],
    # Spatial
    "spatial-deconv": [
        "spacexr",
        "SPOTlight",
        "CARD",
    ],
    "spatial-genes": [
        "SPARK",
    ],
    "spatial-cnv": [
        "numbat",
    ],
    # Bulk RNA-seq
    "bulkrna-de": [
        "DESeq2",
        "S4Vectors",
        "IRanges",
        "GenomicRanges",
    ],
    "bulkrna-enrichment": [
        "clusterProfiler",
        "msigdbr",
        "org.Hs.eg.db",
        "org.Mm.eg.db",
    ],
    "bulkrna-coexpression": [
        "WGCNA",
    ],
    "bulkrna-survival": [
        "survival",
        "survminer",
    ],
    "bulkrna-batch": [
        "sva",
    ],
}

# Legacy aliases kept for compatibility with older tests / callers.
R_TIER_PACKAGES.setdefault("singlecell-core", R_TIER_PACKAGES["singlecell-preprocessing"])
R_TIER_PACKAGES.setdefault("singlecell-doublet", R_TIER_PACKAGES["singlecell-doublet-detection"])
R_TIER_PACKAGES.setdefault("singlecell-annotation", R_TIER_PACKAGES["singlecell-cell-annotation"])
R_TIER_PACKAGES.setdefault("singlecell-integration", R_TIER_PACKAGES["singlecell-batch-integration"])

# Reverse mapping: R package → tier
R_PACKAGE_TO_TIER: dict[str, str] = {}
for _tier, _pkgs in R_TIER_PACKAGES.items():
    for _pkg in _pkgs:
        R_PACKAGE_TO_TIER.setdefault(_pkg, _tier)

# ---------------------------------------------------------------------------
# Installation source classification
# ---------------------------------------------------------------------------

# Packages that must be installed via BiocManager::install()
_BIOCONDUCTOR_PACKAGES: set[str] = {
    "DESeq2", "SingleCellExperiment", "SingleR", "celldex",
    "S4Vectors", "IRanges", "GenomicRanges",
    "clusterProfiler", "org.Hs.eg.db", "org.Mm.eg.db",
    "scDblFinder", "scds", "batchelor", "sva", "SPARK", "slingshot",
    "spacexr", "SPOTlight", "CARD", "numbat",
    "SoupX", "scmap", "MAST", "AUCell", "GSEABase", "graph", "annotate",
}

# Packages installable from CRAN
_CRAN_PACKAGES: set[str] = {
    "Seurat", "DoubletFinder", "CellChat",
    "WGCNA", "survival", "survminer", "msigdbr",
}


def _classify_source(pkg: str) -> str:
    """Return 'bioc' or 'cran' for an R package."""
    if pkg in _BIOCONDUCTOR_PACKAGES:
        return "bioc"
    return "cran"


# ---------------------------------------------------------------------------
# Check / status API
# ---------------------------------------------------------------------------


def check_r_tier(tier: str) -> tuple[list[str], list[str]]:
    """Check installation status of all R packages in a tier.

    Returns ``(installed, missing)`` lists.  If R is not available,
    all packages are reported as missing.
    """
    packages = R_TIER_PACKAGES.get(tier, [])
    if not packages:
        return [], []

    try:
        from omicsclaw.core.r_script_runner import RScriptRunner
        runner = RScriptRunner(verbose=False)
        if not runner.check_r_available():
            return [], packages.copy()
        status = runner.check_r_packages(packages)
    except Exception:
        return [], packages.copy()

    installed = [p for p in packages if status.get(p, False)]
    missing = [p for p in packages if not status.get(p, False)]
    return installed, missing


def get_r_tier_status() -> dict[str, dict[str, Any]]:
    """Return installation status summary for all R tiers.

    Returns a dict keyed by tier name, each value containing:
    - ``packages``: list of required R packages
    - ``installed``: list of installed packages
    - ``missing``: list of missing packages
    - ``status``: ``"ok"`` | ``"partial"`` | ``"missing"`` | ``"r_unavailable"``
    """
    # Check R availability once
    try:
        from omicsclaw.core.r_script_runner import RScriptRunner
        runner = RScriptRunner(verbose=False)
        r_available = runner.check_r_available()
    except Exception:
        r_available = False

    result: dict[str, dict[str, Any]] = {}

    if not r_available:
        for tier, packages in R_TIER_PACKAGES.items():
            result[tier] = {
                "packages": packages,
                "installed": [],
                "missing": packages.copy(),
                "status": "r_unavailable",
            }
        return result

    # Collect all unique packages and check once
    all_packages = sorted({p for pkgs in R_TIER_PACKAGES.values() for p in pkgs})
    try:
        status_map = runner.check_r_packages(all_packages)
    except Exception:
        status_map = {}

    for tier, packages in R_TIER_PACKAGES.items():
        installed = [p for p in packages if status_map.get(p, False)]
        missing = [p for p in packages if not status_map.get(p, False)]
        if not missing:
            status = "ok"
        elif not installed:
            status = "missing"
        else:
            status = "partial"
        result[tier] = {
            "packages": packages,
            "installed": installed,
            "missing": missing,
            "status": status,
        }

    return result


# ---------------------------------------------------------------------------
# Install command generation
# ---------------------------------------------------------------------------


def suggest_r_install(packages: list[str]) -> str:
    """Generate R install commands for a list of missing packages.

    Separates CRAN and Bioconductor packages into distinct commands.
    """
    if not packages:
        return ""

    cran = sorted(p for p in packages if _classify_source(p) == "cran")
    bioc = sorted(p for p in packages if _classify_source(p) == "bioc")

    lines: list[str] = []
    if bioc:
        pkg_str = ", ".join(f'"{p}"' for p in bioc)
        lines.append(
            "# Bioconductor packages\n"
            'Rscript -e \'if (!requireNamespace("BiocManager", quietly=TRUE)) '
            "install.packages(\"BiocManager\"); "
            f"BiocManager::install(c({pkg_str}))'"
        )
    if cran:
        pkg_str = ", ".join(f'"{p}"' for p in cran)
        lines.append(
            "# CRAN packages\n"
            f"Rscript -e 'install.packages(c({pkg_str}))'"
        )

    return "\n\n".join(lines)


def suggest_r_install_for_tier(tier: str) -> str:
    """Generate install commands for all missing packages in a tier."""
    _, missing = check_r_tier(tier)
    if not missing:
        return f"# Tier '{tier}': all R packages installed"
    return f"# Install R packages for tier: {tier}\n{suggest_r_install(missing)}"
