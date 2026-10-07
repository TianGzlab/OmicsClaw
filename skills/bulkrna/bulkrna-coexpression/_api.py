"""WGCNA modules from in-memory bulk expression matrices."""
from pathlib import Path
import json
import tempfile
import warnings
import pandas as pd
from skills.bulkrna._lib.results import attach_info, read_info, require_matrix
from skills.bulkrna._lib.r_matrix import require_r, write_matrix

__all__ = ["analyze", "run_info", "threshold_fit", "hub_genes", "module_sizes_figure"]


def analyze(data: pd.DataFrame, *, power: int | None = None, min_module_size: int = 10,
            random_state: int = 54321) -> pd.DataFrame:
    """Return R WGCNA gene-module assignments, leaving expression unchanged.

    :param data: Nonnegative feature-by-sample expression; provide normalized data on the intended correlation scale.
    :param power: CLI default None selects the soft threshold; set a positive integer to override it.
    :param min_module_size: CLI default 10 genes per module.
    :param random_state: WGCNA blockwiseModules default seed 54321; fixes its preclustering.
    :returns: Gene/module DataFrame with diagnostics, hub genes and threshold fit in attrs.
    :raises ValueError: Input, sample count, power or module size is invalid.
    :raises ImportError: R WGCNA or Matrix is unavailable.
    :raises RuntimeError: R analysis fails.
    """
    require_matrix(data)
    if data.shape[1] < 8:
        raise ValueError("WGCNA requires at least eight samples")
    if min_module_size < 2 or (power is not None and (power < 1 or int(power) != power)):
        raise ValueError("power must be a positive integer and min_module_size at least two")
    if data.shape[1] < 15:
        warnings.warn("Fewer than 15 samples: WGCNA modules are exploratory", RuntimeWarning)
    require_r(["WGCNA", "Matrix"])
    from skills._sdk.r_script_runner import RScriptRunner
    runner = RScriptRunner(scripts_dir=Path(__file__).with_name("rscripts"))
    with tempfile.TemporaryDirectory(prefix="omicsclaw_wgcna_") as scratch:
        directory = Path(scratch)
        write_matrix(data, directory)
        runner.run_script("wgcna.R", args=[str(directory), str(directory), str(min_module_size),
                                          "0.25", str(power) if power is not None else "auto", str(random_state)],
                          expected_outputs=["gene_modules.csv", "hub_genes.csv", "soft_power_table.csv", "wgcna_info.json"],
                          output_dir=directory)
        assignments = pd.read_csv(directory / "gene_modules.csv", dtype={"gene": str, "module": str})
        hubs = pd.read_csv(directory / "hub_genes.csv")
        fit = pd.read_csv(directory / "soft_power_table.csv")
        info = json.loads((directory / "wgcna_info.json").read_text())
    sizes = assignments.module.value_counts()
    summary = {"n_genes_used": len(assignments), "n_samples": info["n_samples"],
               "soft_power": info["soft_power"], "n_modules": info["n_modules"],
               "module_sizes": {name: int(count) for name, count in sizes.items() if name != "grey"},
               "hub_genes": {name: rows.gene.tolist() for name, rows in hubs.groupby("module")},
               "module_assignments": dict(zip(assignments.gene, assignments.module)), "method_used": "wgcna"}
    result = attach_info(assignments, {"requested_method": "wgcna", "executed_method": "wgcna",
                                      "fallback_reason": None, "random_state": random_state,
                                      "filtered_genes": sorted(set(data.index.astype(str)) - set(assignments.gene)),
                                      "summary": summary})
    result.attrs["threshold_fit"] = fit.to_dict("records")
    result.attrs["hub_genes"] = hubs.to_dict("records")
    return result


def run_info(data: pd.DataFrame, *, keep: bool = True) -> dict:
    """Return WGCNA method diagnostics and summary.

    :param data: Result from analyze.
    :param keep: Keep diagnostics by default; the CLI passes False.
    :returns: Independent diagnostics dictionary.
    :raises ValueError: No WGCNA diagnostics are present.
    """
    if "run_info" not in data.attrs:
        raise ValueError("Run analyze first")
    return read_info(data, keep=keep)


def threshold_fit(data: pd.DataFrame) -> pd.DataFrame:
    """Return the signed scale-free fit for each tested soft threshold.

    :param data: Result from analyze.
    :returns: Table containing power, r_squared and mean_connectivity.
    :raises ValueError: No fit table is stored.
    """
    if "threshold_fit" not in data.attrs:
        raise ValueError("Run analyze first")
    return pd.DataFrame(data.attrs["threshold_fit"])


def hub_genes(data: pd.DataFrame) -> pd.DataFrame:
    """Return the highest absolute module-membership genes per non-grey module.

    :param data: Result from analyze.
    :returns: Table with gene, module and kME columns.
    :raises ValueError: No hub table is stored.
    """
    if "hub_genes" not in data.attrs:
        raise ValueError("Run analyze first")
    return pd.DataFrame(data.attrs["hub_genes"], columns=["gene", "module", "kME"])


def module_sizes_figure(data: pd.DataFrame):
    """Plot assignment counts, including grey unassigned genes.

    :param data: Gene/module table from analyze.
    :returns: Matplotlib Figure.
    :raises ValueError: The module column is missing.
    """
    from matplotlib.figure import Figure
    if "module" not in data:
        raise ValueError("Missing module column")
    counts = data.module.value_counts()
    figure = Figure(figsize=(7, 4))
    ax = figure.subplots()
    ax.bar(counts.index, counts.to_numpy())
    ax.set(xlabel="Module", ylabel="Genes")
    ax.tick_params(axis="x", rotation=45)
    return figure
