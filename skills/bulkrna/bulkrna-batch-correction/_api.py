"""Batch correction of in-memory feature-by-sample expression matrices."""
from pathlib import Path
import tempfile
import warnings
import numpy as np
import pandas as pd
from skills.bulkrna._lib.batch_correction import _combat_correct, _run_pca, _silhouette_score
from skills.bulkrna._lib.results import attach_info, read_info, require_matrix
from skills.bulkrna._lib.r_matrix import require_r, write_matrix
from skills._sdk.r_script_runner import RScriptError

__all__ = ["correct", "run_info", "pca_figure"]


def _r_correct(data, metadata, *, parametric):
    from skills._sdk.r_script_runner import RScriptRunner
    require_r(["sva", "Matrix"])
    runner = RScriptRunner(scripts_dir=Path(__file__).with_name("rscripts"))
    with tempfile.TemporaryDirectory(prefix="omicsclaw_combat_") as scratch:
        directory = Path(scratch)
        write_matrix(data, directory)
        metadata.to_csv(directory / "obs.csv", index=False)
        runner.run_script("combat.R", args=[str(directory), str(directory), str(parametric).upper()],
                          expected_outputs=["corrected.csv"], output_dir=directory)
        corrected = pd.read_csv(directory / "corrected.csv", dtype=str)
        corrected = corrected.set_index(corrected.columns[0]).apply(pd.to_numeric)
    if list(corrected.index.astype(str)) != list(data.index.astype(str)) or list(corrected.columns) != list(data.columns.astype(str)):
        raise RuntimeError("R ComBat changed feature or sample identifiers")
    corrected.index, corrected.columns = data.index, data.columns
    return corrected


def correct(data: pd.DataFrame, *, batches: pd.DataFrame, mode: str = "parametric",
            backend: str = "auto") -> pd.DataFrame:
    """Return corrected expression, leaving the input unchanged.

    :param data: Finite nonnegative expression, features by samples; correction uses this scale directly.
    :param batches: Metadata with sample and batch columns, and optional biological condition.
    :param mode: CLI default parametric, or non-parametric (requires R sva).
    :param backend: auto prefers R as the CLI did; r requires R, python uses the legacy parametric approximation.
    :returns: Corrected DataFrame with run_info diagnostics; values can be negative.
    :raises ValueError: Data, metadata, mode or backend is invalid.
    :raises ImportError: An explicitly requested R backend is unavailable.
    :raises RuntimeError: R fails and the requested mode/design has no Python fallback.
    """
    require_matrix(data)
    if backend not in {"auto", "r", "python"} or mode not in {"parametric", "non-parametric"}:
        raise ValueError("Invalid backend or mode")
    if not {"sample", "batch"}.issubset(batches.columns) or batches["sample"].duplicated().any():
        raise ValueError("batches needs unique sample identifiers and a batch column")
    metadata = batches.set_index("sample").reindex(data.columns)
    if metadata["batch"].isna().any():
        raise ValueError("Every expression sample needs a batch label")
    labels = metadata["batch"]
    if labels.nunique() < 2 or labels.value_counts().min() < 2 or len(data) < 2:
        raise ValueError("Need two batches, two samples per batch and two genes")
    can_fallback = mode == "parametric" and "condition" not in metadata.columns
    if backend == "python" and not can_fallback:
        raise ValueError("Python does not support non-parametric mode or condition covariates")
    reason = None
    executed = "r-" + mode
    if backend != "python":
        try:
            corrected = _r_correct(data, metadata.reset_index(names="sample"), parametric=mode == "parametric")
        except (ImportError, RuntimeError, RScriptError, FileNotFoundError) as exc:
            if backend == "r" or not can_fallback:
                raise
            reason = str(exc)
            warnings.warn("R ComBat failed; using the Python parametric approximation: " + reason, RuntimeWarning)
            corrected = _combat_correct(data, labels)
            executed = "python-parametric"
    else:
        corrected = _combat_correct(data, labels)
        executed = "python-parametric"
    if not np.isfinite(corrected.to_numpy()).all():
        raise RuntimeError("Batch correction returned nonfinite values")
    before = _silhouette_score(_run_pca(data), labels.to_numpy())
    after = _silhouette_score(_run_pca(corrected), labels.to_numpy())
    summary = {"n_genes": data.shape[0], "n_samples": data.shape[1],
               "n_batches": int(labels.nunique()), "batch_names": sorted(labels.unique().tolist()),
               "mode": mode, "silhouette_before": round(before, 4), "silhouette_after": round(after, 4)}
    return attach_info(corrected, {"requested_method": backend + "-" + mode,
                                  "executed_method": executed, "fallback_reason": reason, "summary": summary})


def run_info(data: pd.DataFrame, *, keep: bool = True) -> dict:
    """Return backend diagnostics and before/after batch metrics.

    :param data: Result of correct.
    :param keep: Keep diagnostics by default; the CLI passes False.
    :returns: Diagnostics dictionary.
    :raises ValueError: No correction diagnostics are attached.
    """
    if "run_info" not in data.attrs:
        raise ValueError("Run correct first")
    return read_info(data, keep=keep)


def pca_figure(data: pd.DataFrame, *, batches: pd.DataFrame):
    """Plot PCA after signed log2(1+abs(x)), accepting negative corrections.

    :param data: Original or corrected feature-by-sample expression.
    :param batches: Metadata containing sample and batch.
    :returns: Matplotlib Figure.
    :raises ValueError: Samples lack batch metadata.
    """
    from matplotlib.figure import Figure
    labels = batches.set_index("sample").reindex(data.columns)["batch"]
    if labels.isna().any():
        raise ValueError("Every sample needs batch metadata")
    coordinates = _run_pca(data)
    figure = Figure(figsize=(6, 4))
    ax = figure.subplots()
    for batch in sorted(labels.unique()):
        mask = labels.to_numpy() == batch
        ax.scatter(coordinates[mask, 0], coordinates[mask, 1], label=str(batch))
    ax.set(xlabel="PC1", ylabel="PC2")
    ax.legend()
    return figure
