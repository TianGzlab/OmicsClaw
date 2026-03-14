"""Proteomics data loader (mzML, MaxQuant)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_proteomics_data(path: str | Path, data_type: str | None = None) -> Any:
    """Load proteomics data from mzML or MaxQuant files.

    Returns file path for downstream processing by specific skills.
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Proteomics data file not found: {path}")

    # Return path for downstream processing
    return str(path)
