"""Helpers for single-cell perturbation analysis and preparation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scanpy as sc
from anndata import AnnData

from .adata_utils import matrix_looks_count_like

logger = logging.getLogger(__name__)

GENE_EXPRESSION_FEATURE_TYPES = {"Gene Expression", "gene_expression", "Gene"}
DEFAULT_CONTROL_PATTERNS = ("NT", "NTC", "NON-TARGET", "NON_TARGET", "NEGATIVE_CONTROL", "NEG_CTRL")


def make_demo_perturb_adata(seed: int = 0) -> AnnData:
    """Create a small perturbation demo dataset with controls and two perturbations."""
    rng = np.random.default_rng(seed)
    n_cells, n_genes = 180, 80
    genes = [f"Gene{i}" for i in range(n_genes)]
    perts = []
    reps = []
    rows = []

    ctrl = rng.gamma(2.0, 1.0, size=n_genes)
    ko_a = ctrl.copy()
    ko_b = ctrl.copy()
    ko_a[:10] += 4
    ko_b[10:20] += 4

    for pert_name, base in [("NT", ctrl), ("KO_A", ko_a), ("KO_B", ko_b)]:
        for rep in ("r1", "r2"):
            for _ in range(30):
                lib = rng.integers(1500, 3200)
                mu = base / base.sum() * lib
                rows.append(rng.poisson(np.clip(mu, 0.05, None)))
                perts.append(pert_name)
                reps.append(rep)

    adata = AnnData(np.asarray(rows, dtype=float))
    adata.var_names = genes
    adata.obs_names = [f"cell_{i}" for i in range(adata.n_obs)]
    adata.obs["perturbation"] = pd.Categorical(perts)
    adata.obs["replicate"] = pd.Categorical(reps)
    adata.layers["counts"] = adata.X.copy()
    sc.pp.normalize_total(adata)
    sc.pp.log1p(adata)
    sc.pp.pca(adata, n_comps=20)
    return adata


def make_demo_perturb_mapping(adata: AnnData) -> pd.DataFrame:
    """Create a synthetic barcode-to-guide assignment table for demo mode."""
    if "perturbation" not in adata.obs.columns:
        raise ValueError("Demo perturbation metadata missing from AnnData.")

    mapping = pd.DataFrame(index=adata.obs_names.astype(str))
    mapping["barcode"] = adata.obs_names.astype(str)
    pert = adata.obs["perturbation"].astype(str)
    mapping["sgRNA"] = np.where(pert == "NT", "NT_sg1", pert + "_sg1")
    mapping["target_gene"] = np.where(pert == "NT", "NT", pert)
    return mapping.reset_index(drop=True)


def keep_gene_expression_features(adata: AnnData) -> tuple[AnnData, dict[str, Any]]:
    """Keep gene-expression features when feature types are available."""
    summary = {
        "had_feature_types": False,
        "feature_types": [],
        "n_features_before": int(adata.n_vars),
        "n_features_after": int(adata.n_vars),
        "n_non_gene_features_removed": 0,
    }
    if "feature_types" not in adata.var.columns:
        return adata.copy(), summary

    feature_types = adata.var["feature_types"].astype(str)
    summary["had_feature_types"] = True
    summary["feature_types"] = sorted(feature_types.unique().tolist())
    gene_mask = feature_types.isin(GENE_EXPRESSION_FEATURE_TYPES).to_numpy()
    if not gene_mask.any():
        return adata.copy(), summary

    filtered = adata[:, gene_mask].copy()
    summary["n_features_after"] = int(filtered.n_vars)
    summary["n_non_gene_features_removed"] = int((~gene_mask).sum())
    return filtered, summary


def _read_mapping_table(mapping_path: str | Path, sep: str | None = None) -> pd.DataFrame:
    mapping_path = Path(mapping_path)
    if not mapping_path.exists():
        raise FileNotFoundError(f"Mapping file not found: {mapping_path}")

    if sep:
        return pd.read_csv(mapping_path, sep=sep, dtype=str)

    # Try header-aware parsing first; fall back to headerless two-column parsing.
    header_df = pd.read_csv(mapping_path, sep=None, engine="python", dtype=str)
    common = {str(col).strip().lower() for col in header_df.columns}
    if common & {
        "barcode",
        "cell_barcode",
        "cell",
        "cell_id",
        "sgrna",
        "guide",
        "guide_id",
        "target_gene",
        "gene",
    }:
        return header_df

    return pd.read_csv(mapping_path, sep=None, engine="python", dtype=str, header=None)


def load_sgrna_mapping(
    mapping_path: str | Path,
    *,
    barcode_column: str | None = None,
    sgrna_column: str | None = None,
    target_column: str | None = None,
    sep: str | None = None,
) -> pd.DataFrame:
    """Load a cell-barcode to sgRNA mapping table into a standard schema."""
    df = _read_mapping_table(mapping_path, sep=sep)
    if df.shape[1] < 2:
        raise ValueError("Mapping table must contain at least barcode and sgRNA columns.")

    normalized = {str(col).strip().lower(): col for col in df.columns}

    def _resolve(explicit: str | None, candidates: tuple[str, ...], fallback_index: int) -> str:
        if explicit:
            if explicit in df.columns:
                return explicit
            lowered = explicit.strip().lower()
            if lowered in normalized:
                return normalized[lowered]
            raise ValueError(f"Column '{explicit}' not found in mapping file.")
        for candidate in candidates:
            if candidate in normalized:
                return normalized[candidate]
        return df.columns[fallback_index]

    barcode_col = _resolve(barcode_column, ("barcode", "cell_barcode", "cell", "cell_id"), 0)
    sgrna_col = _resolve(sgrna_column, ("sgrna", "sgRNA", "guide", "guide_id", "perturbation"), 1)
    target_col = None
    if target_column:
        target_col = _resolve(target_column, ("target_gene", "gene", "target"), min(2, df.shape[1] - 1))
    else:
        for candidate in ("target_gene", "gene", "target"):
            if candidate in normalized:
                target_col = normalized[candidate]
                break
        if target_col is None and df.shape[1] >= 3 and isinstance(df.columns[0], int):
            target_col = df.columns[2]

    out = pd.DataFrame(
        {
            "barcode": df[barcode_col].astype(str).str.strip(),
            "sgRNA": df[sgrna_col].astype(str).str.strip(),
        }
    )
    if target_col is not None:
        out["target_gene"] = df[target_col].astype(str).str.strip()
    else:
        out["target_gene"] = ""
    out = out.replace({"nan": "", "None": ""})
    out = out[(out["barcode"] != "") & (out["sgRNA"] != "")]
    return out.drop_duplicates().reset_index(drop=True)


def collapse_sgrna_assignments(
    mapping_df: pd.DataFrame,
    *,
    delimiter: str = "_",
    gene_position: int = 0,
    control_patterns: tuple[str, ...] = DEFAULT_CONTROL_PATTERNS,
    control_label: str = "NT",
    drop_multi_guide: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Collapse barcode-level sgRNA assignments into one row per cell."""
    if mapping_df.empty:
        raise ValueError("Mapping table is empty after loading.")

    control_patterns_upper = tuple(str(pattern).strip().upper() for pattern in control_patterns if str(pattern).strip())
    assigned_rows: list[dict[str, Any]] = []
    dropped_rows: list[dict[str, Any]] = []

    for barcode, group in mapping_df.groupby("barcode", sort=False):
        sgrnas = sorted({val for val in group["sgRNA"].astype(str) if val})
        raw_targets = [val for val in group["target_gene"].astype(str) if val]
        inferred_targets = []
        if not raw_targets:
            for sgrna in sgrnas:
                parts = str(sgrna).split(delimiter)
                if 0 <= gene_position < len(parts):
                    inferred_targets.append(parts[gene_position])
        targets = sorted({val for val in raw_targets + inferred_targets if val})
        target_gene = targets[0] if targets else ""
        is_control = False
        if sgrnas:
            joined = " ".join(sgrnas + ([target_gene] if target_gene else [])).upper()
            is_control = any(token in joined for token in control_patterns_upper)

        record = {
            "barcode": str(barcode),
            "sgRNA": ";".join(sgrnas),
            "target_gene": control_label if is_control else target_gene,
            "n_sgrnas": int(len(sgrnas)),
            "assignment_status": "control" if is_control else "assigned",
            "perturbation": control_label if is_control else (target_gene or (sgrnas[0] if len(sgrnas) == 1 else "")),
        }

        if len(sgrnas) == 0:
            record["assignment_status"] = "unassigned"
            dropped_rows.append(record)
            continue

        if len(sgrnas) > 1:
            record["assignment_status"] = "multi_guide"
            if drop_multi_guide:
                dropped_rows.append(record)
                continue
            if not record["perturbation"]:
                record["perturbation"] = "MULTI_GUIDE"

        assigned_rows.append(record)

    assigned_df = pd.DataFrame(assigned_rows)
    dropped_df = pd.DataFrame(dropped_rows)
    return assigned_df, dropped_df


def annotate_perturbation_obs(
    adata: AnnData,
    assignments: pd.DataFrame,
    *,
    pert_key: str = "perturbation",
    sgrna_key: str = "sgRNA",
    target_key: str = "target_gene",
) -> AnnData:
    """Attach perturbation assignments to `adata.obs` and keep mapped cells only."""
    if assignments.empty:
        raise ValueError("No assigned cells remained after collapsing the mapping table.")

    adata = adata.copy()
    adata.obs_names = adata.obs_names.astype(str)
    assignments = assignments.copy()
    assignments["barcode"] = assignments["barcode"].astype(str)

    keep = adata.obs_names.isin(assignments["barcode"])
    filtered = adata[keep].copy()
    overlap_cols = [col for col in assignments.columns if col != "barcode" and col in filtered.obs.columns]
    if overlap_cols:
        filtered.obs = filtered.obs.drop(columns=overlap_cols)
    filtered.obs = filtered.obs.join(assignments.set_index("barcode"), how="left")
    filtered.obs[pert_key] = filtered.obs["perturbation"].astype(str)
    filtered.obs[sgrna_key] = filtered.obs["sgRNA"].astype(str)
    filtered.obs[target_key] = filtered.obs["target_gene"].astype(str)
    filtered.obs["assignment_status"] = filtered.obs["assignment_status"].astype(str)
    filtered.obs["n_sgrnas"] = filtered.obs["n_sgrnas"].astype(int)
    return filtered


def prepare_perturbation_matrix(adata: AnnData) -> str:
    """Ensure Mixscape sees a normalized matrix and report the source used."""
    if matrix_looks_count_like(adata.X):
        counts = adata.X.copy()
        adata.layers["counts"] = counts
        sc.pp.normalize_total(adata)
        sc.pp.log1p(adata)
        return "adata.X(counts->log1p)"
    return "adata.X"


def run_mixscape_workflow(
    adata: AnnData,
    *,
    pert_key: str,
    control: str,
    split_by: str | None = None,
    n_neighbors: int = 20,
    logfc_threshold: float = 0.25,
    pval_cutoff: float = 0.05,
    perturbation_type: str = "KO",
) -> dict[str, Any]:
    import pertpy as pt

    matrix_source = prepare_perturbation_matrix(adata)
    mixscape = pt.tl.Mixscape()
    mixscape.perturbation_signature(
        adata,
        pert_key=pert_key,
        control=control,
        ref_selection_mode="split_by" if split_by else "nn",
        split_by=split_by,
        n_neighbors=n_neighbors,
    )
    mixscape.mixscape(
        adata,
        pert_key=pert_key,
        control=control,
        split_by=split_by,
        logfc_threshold=logfc_threshold,
        pval_cutoff=pval_cutoff,
        perturbation_type=perturbation_type,
    )

    class_col = "mixscape_class"
    global_col = "mixscape_class_global"
    prob_col = f"mixscape_class_p_{perturbation_type.lower()}"
    class_counts = adata.obs[class_col].astype(str).value_counts().rename_axis("class").reset_index(name="n_cells")
    global_counts = adata.obs[global_col].astype(str).value_counts().rename_axis("global_class").reset_index(name="n_cells")

    adata.uns["mixscape_summary"] = {
        "matrix_source": matrix_source,
        "perturbation_key": pert_key,
        "control": control,
        "split_by": split_by,
        "class_column": class_col,
        "global_class_column": global_col,
        "probability_column": prob_col,
    }
    return {
        "method": "mixscape",
        "matrix_source": matrix_source,
        "class_column": class_col,
        "global_class_column": global_col,
        "probability_column": prob_col,
        "class_counts": class_counts,
        "global_counts": global_counts,
    }
