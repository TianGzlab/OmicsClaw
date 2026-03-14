"""Metabolomics data loader (mzML, XCMS)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_metabolomics_data(path: str | Path, data_type: str | None = None) -> Any:
    """Load metabolomics data from mzML or XCMS files.

    Returns file path for downstream processing by specific skills.
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Metabolomics data file not found: {path}")

    # Return path for downstream processing
    return str(path)
