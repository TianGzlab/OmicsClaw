"""Survival comparisons on expression and clinical DataFrames."""
from pathlib import Path
import warnings
import numpy as np
import pandas as pd
from skills.bulkrna._lib.survival import analyze_gene
from skills.bulkrna._lib.survival_r import _run_survival_r
from skills.bulkrna._lib.results import attach_info, read_info, require_matrix
from skills._sdk.r_script_runner import RScriptError

__all__ = ["analyze", "run_info", "km_table", "curve_figure"]


def analyze(data: pd.DataFrame, *, clinical: pd.DataFrame, genes: list[str] | None = None,
            cutoff_method: str = "median", backend: str = "auto") -> pd.DataFrame:
    """Return gene-wise survival comparisons without modifying expression.

    :param data: Nonnegative feature-by-sample expression.
    :param clinical: Clinical table with unique sample, nonnegative time and binary event columns.
    :param genes: Genes to test; None uses every row. Missing genes raise.
    :param cutoff_method: CLI default median; optimal scans cuts with unadjusted p-values.
    :param backend: auto prefers R survival with Cox HR, as the CLI did; python uses an events/person-time ratio.
    :returns: Per-gene table with diagnostics and KM points attached in attrs.
    :raises ValueError: Identifiers, clinical values, requested genes or comparison groups are invalid.
    :raises ImportError: Explicit R backend lacks survival or Matrix.
    :raises RuntimeError: The requested R method fails or returns incomplete results.
    """
    require_matrix(data)
    if backend not in {"auto", "r", "python"} or cutoff_method not in {"median", "optimal"}:
        raise ValueError("Invalid backend or cutoff_method")
    if not {"sample", "time", "event"}.issubset(clinical.columns) or clinical["sample"].duplicated().any():
        raise ValueError("clinical requires unique sample, time and event columns")
    shared = sorted(set(data.columns) & set(clinical["sample"]))
    if len(shared) < 4:
        raise ValueError("Need at least four matched clinical samples")
    expression = data.loc[:, shared]
    metadata = clinical.set_index("sample").loc[shared]
    times = metadata.time.to_numpy(dtype=float)
    events = metadata.event.to_numpy(dtype=float)
    if not np.isfinite(times).all() or (times < 0).any() or not np.isin(events, [0, 1]).all():
        raise ValueError("Clinical time must be finite/nonnegative and event must be binary")
    genes = list(data.index) if genes is None else list(genes)
    missing = set(genes) - set(data.index)
    if missing or not genes or len(genes) != len(set(genes)):
        raise ValueError("Missing genes or empty/duplicate gene list: " + ", ".join(map(str, sorted(missing))))
    reason = None
    executed = "r-survival"
    if backend != "python":
        try:
            records = _run_survival_r(expression, metadata.reset_index(), genes, cutoff_method,
                                      scripts_dir=Path(__file__).with_name("rscripts"))
        except (ImportError, RuntimeError, RScriptError, FileNotFoundError, pd.errors.EmptyDataError) as exc:
            if backend == "r":
                raise
            reason = str(exc)
            warnings.warn("R survival failed; using Python log-rank and events/person-time ratios: " + reason, RuntimeWarning)
            executed = "python-logrank"
    if backend == "python" or executed == "python-logrank":
        executed = "python-logrank"
        records = [analyze_gene(gene, expression.loc[gene].to_numpy(dtype=float), times,
                                events.astype(int), cutoff_method) for gene in genes]
    if {record["gene"] for record in records} != set(genes) or any(record["status"] != "ok" for record in records):
        raise ValueError("Some genes have insufficient high/low comparison samples")
    points = []
    for record in records:
        for group in ("high", "low"):
            curve_times, survival = record["km_" + group]
            points.extend({"gene": record["gene"], "group": group, "time": float(t),
                           "survival": float(s)} for t, s in zip(curve_times, survival))
    summaries = [{key: value for key, value in record.items() if key not in {"km_high", "km_low"}} for record in records]
    columns = ["gene", "cutoff", "n_high", "n_low", "hazard_ratio", "log_rank_chi2",
               "log_rank_pval", "median_survival_high", "median_survival_low"]
    table = pd.DataFrame(summaries)[columns]
    table = attach_info(table, {"requested_method": backend, "executed_method": executed,
                               "fallback_reason": reason,
                               "hazard_estimator": "cox-ph" if executed == "r-survival" else "events-per-person-time",
                               "dropped_expression_samples": len(data.columns) - len(shared),
                               "summary": {"n_genes": len(records), "results": summaries}})
    table.attrs["km_points"] = points
    return table


def run_info(data: pd.DataFrame, *, keep: bool = True) -> dict:
    """Return actual backend, HR estimator and summary.

    :param data: Result from analyze.
    :param keep: Keep diagnostics by default; the CLI passes False.
    :returns: Diagnostics dictionary.
    :raises ValueError: The table has no analysis diagnostics.
    """
    if "run_info" not in data.attrs:
        raise ValueError("Run analyze first")
    return read_info(data, keep=keep)


def km_table(data: pd.DataFrame) -> pd.DataFrame:
    """Return the fitted Kaplan-Meier points for both expression strata.

    :param data: Result from analyze.
    :returns: New table with gene, group, time and survival columns.
    :raises ValueError: The result lacks stored curves.
    """
    if "km_points" not in data.attrs:
        raise ValueError("Run analyze first")
    return pd.DataFrame(data.attrs["km_points"])


def curve_figure(data: pd.DataFrame, *, gene: str):
    """Plot the stored Kaplan-Meier curves for one analyzed gene.

    :param data: Result from analyze.
    :param gene: Exact gene identifier in the result.
    :returns: Matplotlib Figure.
    :raises ValueError: No curve exists for the requested gene.
    """
    from matplotlib.figure import Figure
    points = km_table(data)
    points = points[points.gene == gene]
    if points.empty:
        raise ValueError("No curve for gene " + gene)
    figure = Figure(figsize=(6, 4))
    ax = figure.subplots()
    for group, rows in points.groupby("group"):
        ax.step(rows.time, rows.survival, where="post", label=group)
    ax.set(xlabel="Time", ylabel="Survival probability", ylim=(0, 1.05))
    ax.legend()
    return figure
