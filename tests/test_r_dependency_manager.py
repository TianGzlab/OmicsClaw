"""Tests for R dependency tier management.

Validates tier definitions, install command generation, and the mapping
structure — does NOT require R to be installed.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from omicsclaw.core.r_dependency_manager import (
    R_TIER_PACKAGES,
    R_PACKAGE_TO_TIER,
    suggest_r_install,
    suggest_r_install_for_tier,
    _classify_source,
)


# ---------------------------------------------------------------------------
# Tier definition integrity
# ---------------------------------------------------------------------------


def test_all_tiers_have_packages():
    """Every tier must define at least one package."""
    for tier, packages in R_TIER_PACKAGES.items():
        assert len(packages) > 0, f"Tier '{tier}' has no packages"


def test_reverse_mapping_covers_all_packages():
    """Every package in every tier should appear in the reverse mapping."""
    for tier, packages in R_TIER_PACKAGES.items():
        for pkg in packages:
            assert pkg in R_PACKAGE_TO_TIER, (
                f"Package '{pkg}' from tier '{tier}' missing in R_PACKAGE_TO_TIER"
            )


def test_known_tiers_exist():
    """Key tiers expected by skills should be defined."""
    expected = [
        "bulkrna-de",
        "bulkrna-enrichment",
        "singlecell-core",
        "spatial-deconv",
    ]
    for tier in expected:
        assert tier in R_TIER_PACKAGES, f"Expected tier '{tier}' not found"


def test_deseq2_in_bulkrna_de():
    """DESeq2 should be in the bulkrna-de tier."""
    assert "DESeq2" in R_TIER_PACKAGES["bulkrna-de"]


def test_seurat_in_singlecell():
    """Seurat should be in the singlecell-core tier."""
    assert "Seurat" in R_TIER_PACKAGES["singlecell-core"]


# ---------------------------------------------------------------------------
# Source classification
# ---------------------------------------------------------------------------


def test_classify_bioconductor():
    assert _classify_source("DESeq2") == "bioc"
    assert _classify_source("SingleCellExperiment") == "bioc"


def test_classify_cran():
    assert _classify_source("Seurat") == "cran"
    assert _classify_source("survival") == "cran"


# ---------------------------------------------------------------------------
# Install command generation
# ---------------------------------------------------------------------------


def test_suggest_r_install_empty():
    """Empty list should produce empty string."""
    assert suggest_r_install([]) == ""


def test_suggest_r_install_cran():
    """CRAN packages should produce install.packages() command."""
    result = suggest_r_install(["Seurat"])
    assert "install.packages" in result
    assert "Seurat" in result


def test_suggest_r_install_bioc():
    """Bioconductor packages should produce BiocManager::install() command."""
    result = suggest_r_install(["DESeq2"])
    assert "BiocManager::install" in result
    assert "DESeq2" in result


def test_suggest_r_install_mixed():
    """Mixed sources should produce both CRAN and Bioconductor commands."""
    result = suggest_r_install(["Seurat", "DESeq2"])
    assert "install.packages" in result
    assert "BiocManager::install" in result


def test_suggest_for_tier():
    """suggest_r_install_for_tier should mention the tier name."""
    result = suggest_r_install_for_tier("bulkrna-de")
    assert "bulkrna-de" in result
