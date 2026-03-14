"""Genomics data loader (VCF, BAM, FASTA, FASTQ)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_genomics_data(path: str | Path, data_type: str | None = None) -> Any:
    """Load genomics data from VCF, BAM, FASTA, or FASTQ files.

    Returns file path for downstream processing by specific skills.
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Genomics data file not found: {path}")

    # Return path for downstream processing
    # Actual parsing done by skills using pysam/cyvcf2/biopython
    return str(path)
