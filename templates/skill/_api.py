"""REPLACE_SKILL_NAME's function library: what a step calls through ``load_skill``.

Replace the placeholder below with the skill's real computations. Functions
return objects; the step owns I/O through ``read_input``/``write_output``.
A ``read_*`` adapter may read files when passed as ``reader=`` to
``read_input``. Import optional backends inside the method that uses them.
See this directory's README for seeds, fallbacks and R data exchange.
"""

from __future__ import annotations

import pandas as pd

__all__ = ["run_method"]

METHODS = ("default",)


def run_method(frame: pd.DataFrame, *, method: str = "default") -> pd.DataFrame:
    """Placeholder computation: return a copy of the table with a ``method`` column.

    :param frame: The input table.
    :param method: The backend to run. Default ``"default"``, the only one so far;
        say here where each default comes from and when to change it.
    :returns: A new DataFrame: *frame* plus a ``method`` column.
    :raises ValueError: *method* is not one of ``METHODS``.
    """
    if method not in METHODS:
        raise ValueError(f"method {method!r} not in {METHODS}")
    out = frame.copy()
    out["method"] = method
    return out
