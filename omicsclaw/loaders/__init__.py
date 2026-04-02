"""Domain-detection helpers for OmicsClaw input files.

This package used to carry experimental runtime data loaders that duplicated
the maintained loader implementations under ``skills/.../_lib``. The runtime
only relies on extension-to-domain detection, so the public surface is kept
small and explicit here.
"""

from __future__ import annotations

from pathlib import Path

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
    ".fastq.gz": "genomics",
    ".fq": "genomics",
    ".fq.gz": "genomics",
    ".mzml": "proteomics",
    ".mzxml": "proteomics",
    ".cdf": "metabolomics",
}


def detect_domain_from_extension(ext: str, *, fallback: str = "spatial") -> str:
    """Detect an omics domain from a file extension string."""
    normalized = str(ext or "").strip().lower()
    if not normalized:
        return fallback
    return EXTENSION_TO_DOMAIN.get(normalized, fallback)


def detect_domain_from_path(path: str | Path, *, fallback: str = "spatial") -> str:
    """Detect an omics domain from a file path.

    Handles multi-suffix files such as ``.vcf.gz`` and ``.fastq.gz``.
    """
    suffixes = [suffix.lower() for suffix in Path(path).suffixes]
    for start in range(len(suffixes)):
        candidate = "".join(suffixes[start:])
        if candidate in EXTENSION_TO_DOMAIN:
            return EXTENSION_TO_DOMAIN[candidate]

    if suffixes:
        return detect_domain_from_extension(suffixes[-1], fallback=fallback)
    return fallback


__all__ = [
    "EXTENSION_TO_DOMAIN",
    "detect_domain_from_extension",
    "detect_domain_from_path",
]
