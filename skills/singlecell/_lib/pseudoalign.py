"""Helpers for pseudoalignment-based single-cell counting backends."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import anndata as ad
import pandas as pd
import scanpy as sc
from scipy import sparse
from scipy.io import mmread

from .upstream import CommandExecution, FastqSample, run_command, tool_available

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


def _resolve_simpleaf_index_dir(path: str | Path) -> Path:
    """Normalize a simpleaf reference path to the directory expected by `simpleaf quant`."""
    target = Path(path).resolve()
    if (target / "simpleaf_index.json").exists():
        return target
    if (target / "index" / "simpleaf_index.json").exists():
        return target / "index"
    return target


def _infer_simpleaf_t2g(index_path: str | Path) -> Path | None:
    """Best-effort lookup of a t2g file for a simpleaf index directory."""
    index_dir = _resolve_simpleaf_index_dir(index_path)
    metadata_path = index_dir / "simpleaf_index.json"
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text())
        except Exception:
            metadata = {}
        t2g_field = metadata.get("t2g_file")
        if t2g_field:
            candidate = Path(t2g_field)
            if not candidate.is_absolute():
                candidate = (index_dir / candidate).resolve()
            if candidate.exists():
                return candidate

    candidates = sorted(
        path
        for path in [index_dir, index_dir.parent, index_dir.parent / "ref"]
        if path.exists()
        for path in path.rglob("*")
        if path.is_file() and "t2g" in path.name.lower()
    )
    return candidates[0] if candidates else None


def _normalize_simpleaf_t2g(t2g_path: str | Path, output_dir: str | Path) -> Path:
    """Create a simpleaf/alevin-fry-safe 3-column t2g file."""
    source = Path(t2g_path).resolve()
    rows: list[str] = []
    valid_regions = {"S", "U", "spliced", "unspliced"}
    for line in source.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        fields = line.rstrip("\n").split("\t")
        if len(fields) < 2:
            continue
        region = "S"
        if len(fields) >= 3 and fields[2]:
            candidate = fields[2].strip()
            if candidate in valid_regions:
                region = candidate
        rows.append(f"{fields[0]}\t{fields[1]}\t{region}")
    if not rows:
        raise RuntimeError(f"Could not derive a 3-column t2g map from: {source}")
    target = Path(output_dir) / "simpleaf_t2g.tsv"
    target.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return target.resolve()


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
        # kb-python count outputs often use cells_x_genes.* naming.
        if (
            (candidate / "cells_x_genes.mtx").exists()
            and (candidate / "cells_x_genes.genes.txt").exists()
            and (candidate / "cells_x_genes.barcodes.txt").exists()
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

    if (path / "cells_x_genes.mtx").exists():
        # kb-python matrix market output is cell x gene orientation already.
        matrix = sparse.csr_matrix(mmread(path / "cells_x_genes.mtx")).tocsr()
        genes = pd.read_csv(path / "cells_x_genes.genes.txt", header=None)[0].astype(str).tolist()
        barcodes = pd.read_csv(path / "cells_x_genes.barcodes.txt", header=None)[0].astype(str).tolist()
        adata = ad.AnnData(X=matrix)
        adata.obs_names = pd.Index(barcodes, dtype="object")
        adata.var_names = pd.Index(genes, dtype="object")
        adata.var["gene_symbols"] = adata.var_names.astype(str)
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
    t2g_path: str | Path | None,
    output_dir: str | Path,
    whitelist_path: str | Path | None = None,
    threads: int = 8,
) -> tuple[PseudoalignArtifacts, CommandExecution]:
    """Run `simpleaf quant` with direct AnnData export."""
    if not tool_available("simpleaf"):
        raise RuntimeError("`simpleaf` is not installed or not on PATH.")
    if not sample.is_paired:
        raise ValueError("The current simpleaf wrapper expects paired-end droplet FASTQ input.")

    resolved_index = _resolve_simpleaf_index_dir(index_path)
    out_dir = Path(output_dir) / "artifacts" / "simpleaf" / _slugify(sample.sample_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    resolved_t2g = Path(t2g_path).resolve() if t2g_path else _infer_simpleaf_t2g(resolved_index)
    if resolved_t2g is None:
        raise RuntimeError(
            "simpleaf quant requires a transcript-to-gene map. "
            "Pass `--t2g /abs/path/to/t2g.tsv`, or keep a matching t2g file inside the simpleaf reference directory."
        )
    normalized_t2g = _normalize_simpleaf_t2g(resolved_t2g, out_dir)

    command = [
        "simpleaf",
        "quant",
        "--index",
        str(resolved_index),
        "--reads1",
        ",".join(str(path.resolve()) for path in sample.read1_files),
        "--reads2",
        ",".join(str(path.resolve()) for path in sample.read2_files),
        "--chemistry",
        chemistry,
        "--resolution",
        "cr-like",
        "--t2g-map",
        str(normalized_t2g),
        "--threads",
        str(max(int(threads), 1)),
        "--output",
        str(out_dir.resolve()),
        "--anndata-out",
    ]
    if whitelist_path is not None:
        command.extend(["--explicit-pl", str(Path(whitelist_path).resolve())])
    else:
        command.append("--knee")
    execution = run_command(command, cwd=out_dir)
    try:
        artifacts = inspect_pseudoalign_output(out_dir, method="simpleaf")
    except FileNotFoundError as exc:
        raise RuntimeError(
            "simpleaf finished without producing an importable H5AD or matrix directory. "
            f"Inspect `{out_dir}` and the backend logs to confirm whether quantification actually completed.\n{exc}"
        ) from exc
    return artifacts, execution


def run_kb_count(
    sample: FastqSample,
    *,
    index_path: str | Path,
    t2g_path: str | Path,
    technology: str,
    output_dir: str | Path,
    whitelist_path: str | Path | None = None,
    threads: int = 8,
) -> tuple[PseudoalignArtifacts, CommandExecution]:
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
    if whitelist_path is not None:
        command.extend(["-w", str(Path(whitelist_path).resolve())])
    command.extend(str(path.resolve()) for path in sample.read1_files)
    command.extend(str(path.resolve()) for path in sample.read2_files)
    execution = run_command(command, cwd=out_dir)
    try:
        artifacts = inspect_pseudoalign_output(out_dir, method="kb_python")
    except FileNotFoundError as exc:
        raise RuntimeError(
            "kb-python finished without producing an importable H5AD or matrix directory. "
            f"Inspect `{out_dir}` plus `run_info.json` to see whether reads were retained and matrices were written.\n{exc}"
        ) from exc
    return artifacts, execution
