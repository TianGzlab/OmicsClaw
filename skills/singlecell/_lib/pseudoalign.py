"""Helpers for pseudoalignment-based single-cell counting backends."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import anndata as ad
import pandas as pd
import scanpy as sc
from scipy import sparse
from scipy.io import mmread

from .upstream import FastqSample, run_command, tool_available

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PseudoalignArtifacts:
    """Stable artifact paths for a pseudoalign-count run."""

    method: str
    run_dir: Path
    h5ad_path: Path | None
    matrix_dir: Path | None


def _slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower() or "pseudoalign"


def _find_first_h5ad(path: Path) -> Path | None:
    if path.is_file() and path.suffix.lower() == ".h5ad":
        return path
    candidates = sorted(path.rglob("*.h5ad"))
    return candidates[0] if candidates else None


def _find_quants_matrix_dir(path: Path) -> Path | None:
    for candidate in [path, *path.rglob("*")]:
        if not candidate.is_dir():
            continue
        if (
            (candidate / "quants_mat.mtx").exists()
            and (candidate / "quants_mat_rows.txt").exists()
            and (candidate / "quants_mat_cols.txt").exists()
        ):
            return candidate
        if (
            (candidate / "matrix.mtx").exists()
            and ((candidate / "features.tsv").exists() or (candidate / "genes.tsv").exists())
            and (candidate / "barcodes.tsv").exists()
        ):
            return candidate
    return None


def inspect_pseudoalign_output(path: str | Path, method: str | None = None) -> PseudoalignArtifacts:
    """Resolve an existing pseudoalign output directory or file."""
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"Pseudoalign output not found: {target}")
    h5ad_path = _find_first_h5ad(target)
    matrix_dir = _find_quants_matrix_dir(target) if target.is_dir() else None
    resolved_method = method or ("simpleaf" if "simpleaf" in target.as_posix().lower() else "kb_python")
    if h5ad_path is None and matrix_dir is None:
        raise FileNotFoundError(f"Could not locate an importable pseudoalign result under: {target}")
    return PseudoalignArtifacts(
        method=resolved_method,
        run_dir=target if target.is_dir() else target.parent,
        h5ad_path=h5ad_path,
        matrix_dir=matrix_dir,
    )


def load_pseudoalign_adata(artifacts: PseudoalignArtifacts):
    """Load AnnData from a pseudoalign backend output."""
    if artifacts.h5ad_path is not None and artifacts.h5ad_path.exists():
        return sc.read_h5ad(artifacts.h5ad_path)

    if artifacts.matrix_dir is None:
        raise FileNotFoundError(f"No H5AD or matrix directory was found for {artifacts.method}")

    path = artifacts.matrix_dir
    if (path / "quants_mat.mtx").exists():
        matrix = sparse.csr_matrix(mmread(path / "quants_mat.mtx")).transpose().tocsr()
        rows = pd.read_csv(path / "quants_mat_rows.txt", header=None)[0].astype(str).tolist()
        cols = pd.read_csv(path / "quants_mat_cols.txt", header=None)[0].astype(str).tolist()
        adata = ad.AnnData(X=matrix)
        adata.obs_names = pd.Index(cols, dtype="object")
        adata.var_names = pd.Index(rows, dtype="object")
        return adata

    try:
        return sc.read_10x_mtx(path, var_names="gene_symbols", cache=False)
    except Exception:
        return sc.read_10x_mtx(path, var_names="gene_ids", cache=False)


def run_simpleaf_quant(
    sample: FastqSample,
    *,
    index_path: str | Path,
    chemistry: str,
    output_dir: str | Path,
    threads: int = 8,
) -> tuple[PseudoalignArtifacts, tuple[str, ...]]:
    """Run `simpleaf quant` with direct AnnData export."""
    if not tool_available("simpleaf"):
        raise RuntimeError("`simpleaf` is not installed or not on PATH.")
    if not sample.is_paired:
        raise ValueError("The current simpleaf wrapper expects paired-end droplet FASTQ input.")

    out_dir = Path(output_dir) / "artifacts" / "simpleaf" / _slugify(sample.sample_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "simpleaf",
        "quant",
        "--index",
        str(Path(index_path).resolve()),
        "--reads1",
        ",".join(str(path.resolve()) for path in sample.read1_files),
        "--reads2",
        ",".join(str(path.resolve()) for path in sample.read2_files),
        "--chemistry",
        chemistry,
        "--threads",
        str(max(int(threads), 1)),
        "--output",
        str(out_dir.resolve()),
        "--anndata-out",
    ]
    execution = run_command(command, cwd=out_dir)
    return inspect_pseudoalign_output(out_dir, method="simpleaf"), execution.command


def run_kb_count(
    sample: FastqSample,
    *,
    index_path: str | Path,
    t2g_path: str | Path,
    technology: str,
    output_dir: str | Path,
    threads: int = 8,
) -> tuple[PseudoalignArtifacts, tuple[str, ...]]:
    """Run `kb count` with H5AD export when available."""
    if not tool_available("kb"):
        raise RuntimeError("`kb` is not installed or not on PATH.")
    if not sample.is_paired:
        raise ValueError("The current kb-python wrapper expects paired-end droplet FASTQ input.")

    out_dir = Path(output_dir) / "artifacts" / "kb_python" / _slugify(sample.sample_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "kb",
        "count",
        "-i",
        str(Path(index_path).resolve()),
        "-g",
        str(Path(t2g_path).resolve()),
        "-x",
        technology,
        "-o",
        str(out_dir.resolve()),
        "-t",
        str(max(int(threads), 1)),
        "--workflow",
        "standard",
        "--h5ad",
    ]
    command.extend(str(path.resolve()) for path in sample.read1_files)
    command.extend(str(path.resolve()) for path in sample.read2_files)
    execution = run_command(command, cwd=out_dir)
    return inspect_pseudoalign_output(out_dir, method="kb_python"), execution.command

