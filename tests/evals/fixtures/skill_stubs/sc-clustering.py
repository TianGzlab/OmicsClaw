"""Stand-in for sc-clustering's function library in scripted evals."""


def cluster(adata, *, resolution=1.0, **_):
    """Return the input with a fixed two-cluster labelling."""
    cells = adata["cells"]
    return {**adata, "leiden": [str(i % 2) for i in range(len(cells))], "resolution": resolution}


def cluster_summary(adata, *, key="leiden"):
    """Count cells per cluster."""
    counts = {}
    for label in adata[key]:
        counts[label] = counts.get(label, 0) + 1
    return counts
