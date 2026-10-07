"""DataFrame diagnostics shared by genomic file analyses."""
from copy import deepcopy
import pandas as pd


def attach_info(data, summary, *, method):
    data.attrs["run_info"] = {"requested_method": method, "executed_method": method,
                              "fallback_reason": None, "summary": summary}
    return data


def read_info(data, *, keep=True):
    if "run_info" not in data.attrs:
        raise ValueError("Run analyze before requesting run_info")
    value = deepcopy(data.attrs["run_info"])
    if not keep:
        data.attrs.pop("run_info")
    return value


def require_columns(data, columns):
    if not isinstance(data, pd.DataFrame):
        raise TypeError("data must be a pandas DataFrame")
    missing = set(columns) - set(data.columns)
    if missing:
        raise ValueError("Missing columns: " + ", ".join(sorted(missing)))
    if data.empty:
        raise ValueError("Input contains no records")
