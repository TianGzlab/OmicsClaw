"""Temporary matrix exchange for bulk RNA R analyses."""
from pathlib import Path
import pandas as pd
from scipy import sparse
from scipy.io import mmwrite


def write_matrix(data, directory):
    directory = Path(directory)
    for labels in (data.index.astype(str), data.columns.astype(str)):
        if labels.has_duplicates or any(any(character in label for character in "\t\r\n") for label in labels):
            raise ValueError("R matrix identifiers must be unique text without tabs or newlines")
    mmwrite(directory / "matrix.mtx", sparse.coo_matrix(data.to_numpy(dtype=float)))
    pd.Series(data.index.astype(str)).to_csv(directory / "features.tsv", index=False, header=False, sep="\t")
    pd.Series(data.columns.astype(str)).to_csv(directory / "barcodes.tsv", index=False, header=False, sep="\t")


def require_r(packages):
    from skills._sdk.deps import validate_r_environment
    try:
        validate_r_environment(required_r_packages=packages)
    except Exception as exc:
        raise ImportError("R packages " + ", ".join(packages) +
                          " are required; use the documented R install commands. "
                          "install_skill_deps reports R requirements but does not install R packages.") from exc
