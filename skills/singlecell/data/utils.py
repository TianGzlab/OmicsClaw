#!/usr/bin/env python3
"""Data utilities for single-cell omics skills."""

from pathlib import Path

_DATA_DIR = Path(__file__).parent


def get_demo_data(skill_name=None):
    """Get path to demo data.

    Args:
        skill_name: Skill name (unused, for API compatibility)

    Returns:
        Path to pbmc3k_processed.h5ad
    """
    return _DATA_DIR / "demo" / "pbmc3k_processed.h5ad"


def get_raw_demo_data():
    """Get path to raw demo data.

    Returns:
        Path to pbmc3k_raw.h5ad
    """
    return _DATA_DIR / "demo" / "pbmc3k_raw.h5ad"


def list_available_data():
    """List available datasets."""
    demo_dir = _DATA_DIR / "demo"
    return [f.name for f in demo_dir.glob("*.h5ad")]
