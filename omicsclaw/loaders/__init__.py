"""Unified data loader for all omics domains."""

from __future__ import annotations

from pathlib import Path
from typing import Any

EXTENSION_TO_DOMAIN = {
    ".h5ad": "spatial",
    ".h5": "spatial",
    ".zarr": "spatial",
    ".loom": "singlecell",
    ".mtx": "singlecell",
    ".vcf": "genomics",
    ".vcf.gz": "genomics",
    ".bam": "genomics",
    ".cram": "genomics",
    ".fasta": "genomics",
    ".fa": "genomics",
    ".fastq": "genomics",
    ".fq": "genomics",
    ".mzml": "proteomics",
    ".mzxml": "proteomics",
    ".cdf": "metabolomics",
}


def detect_domain_from_extension(ext: str) -> str:
    """Detect omics domain from file extension."""
    ext = ext.lower()
    return EXTENSION_TO_DOMAIN.get(ext, "spatial")


def load_omics_data(
    path: str | Path,
    domain: str | None = None,
    data_type: str | None = None,
) -> Any:
    """Unified data loader for all omics domains."""
    path = Path(path)

    if domain is None:
        domain = detect_domain_from_extension(path.suffix)

    if domain == "spatial":
        from .spatial import load_spatial_data
        return load_spatial_data(path, data_type)
    elif domain == "singlecell":
        from .spatial import load_spatial_data  # Reuse for now
        return load_spatial_data(path, data_type)
    elif domain == "genomics":
        raise NotImplementedError("Genomics loader not yet implemented")
    elif domain == "proteomics":
        raise NotImplementedError("Proteomics loader not yet implemented")
    elif domain == "metabolomics":
        raise NotImplementedError("Metabolomics loader not yet implemented")
    else:
        raise ValueError(f"Unknown domain: {domain}")
