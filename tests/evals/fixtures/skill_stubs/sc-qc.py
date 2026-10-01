"""Stand-in for sc-qc's function library in scripted evals."""


def calculate_qc(adata, *, species="human", **_):
    """Return the input with a fixed gene count per cell."""
    cells = adata["cells"]
    return {**adata, "n_genes": [100 + i for i in range(len(cells))], "species": species}


def qc_summary(adata):
    """The number of cells and their median gene count."""
    values = sorted(adata["n_genes"])
    return {"n_cells": len(values), "median_genes": values[len(values) // 2]}
