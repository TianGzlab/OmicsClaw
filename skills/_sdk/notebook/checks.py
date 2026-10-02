"""Checks for a module's validate step.

Each check raises ``AssertionError`` with a message that says what differs,
so a failing check stops the validate step the way a failing ``assert``
does, and it still runs under ``python -O``. A table is a pandas DataFrame
or a dict of columns; a column or a run of labels is anything iterable,
such as a pandas Series, a numpy array or a list. Labels are compared
through :func:`as_labels`, so ``0``, ``0.0`` and ``"0"`` are the same label.
"""

from __future__ import annotations

import math
import numbers
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from skills._sdk.notebook._io import check_output_path, record_input, step_context

__all__ = [
    "as_labels",
    "check_columns",
    "check_rows",
    "check_between",
    "check_same_labels",
    "check_counts",
    "check_files",
]

SHOWN = 5
"""Most differences a failure message lists."""


def _missing(position: int, value: Any) -> AssertionError:
    return AssertionError(f"label {position} is missing ({value!r})")


def _label(value: Any, position: int) -> str:
    if value is None:
        raise _missing(position, value)
    if isinstance(value, str):
        return value
    if isinstance(value, bool) or getattr(getattr(value, "dtype", None), "kind", None) == "b":
        return "True" if value else "False"
    if isinstance(value, numbers.Integral):
        return str(int(value))
    if isinstance(value, numbers.Real):
        number = float(value)
        if math.isnan(number):
            raise _missing(position, value)
        if number.is_integer():
            return str(int(number))
        if getattr(getattr(value, "dtype", None), "kind", None) == "f":
            # numpy prints the shortest decimal that identifies the value at its own precision.
            return repr(float(str(value)))
        return repr(number)
    try:
        if value != value:  # NaN-like values that are not floats
            raise _missing(position, value)
    except TypeError:  # pandas.NA cannot be told true or false
        raise _missing(position, value) from None
    return str(value)


def as_labels(values: Iterable[Any]) -> list[str]:
    """Return the values as label strings, so 0, 0.0, numpy.int64(0) and "0" all become "0".

    Integer-valued numbers lose their decimal part, other numbers keep their
    shortest repr, booleans become "True" or "False", strings pass unchanged.
    A numpy float is read at its own precision, so numpy.float32(0.1) becomes
    "0.1", as a 0.1 read back from a CSV does.
    Use it to look labels up across tables, for example
    ``dict(zip(as_labels(table["leiden"]), table["cell_type"]))``.

    :raises AssertionError: a value is missing (None or NaN).
    :raises TypeError: *values* is a single string rather than a column.
    """
    if isinstance(values, (str, bytes)):
        raise TypeError("as_labels takes a column or a sequence of labels, not one string")
    # A pandas column hands out plain Python floats; its numpy array keeps each value's own precision.
    items = values.to_numpy() if hasattr(values, "to_numpy") else values
    return [_label(value, position) for position, value in enumerate(items)]


def _column_names(table: Any) -> list[str]:
    if hasattr(table, "columns"):
        return [str(name) for name in table.columns]
    if isinstance(table, Mapping):
        return [str(name) for name in table]
    raise TypeError(f"expected a table (a DataFrame or a dict of columns), got {type(table).__name__}")


def _row_count(table: Any) -> int:
    if isinstance(table, Mapping) and not hasattr(table, "columns"):
        lengths = {len(column) for column in table.values()}
        if len(lengths) > 1:
            raise AssertionError(f"the table's columns have different lengths: {sorted(lengths)}")
        return lengths.pop() if lengths else 0
    return len(table)


def _shown(items: list[str]) -> str:
    text = "; ".join(items[:SHOWN])
    return text + (f"; and {len(items) - SHOWN} more" if len(items) > SHOWN else "")


def check_columns(table: Any, columns: Iterable[str] | str) -> None:
    """Check that the table has every one of the columns; the message lists the missing and the present ones."""
    wanted = [columns] if isinstance(columns, str) else list(columns)
    present = _column_names(table)
    missing = [name for name in wanted if name not in present]
    if missing:
        listed = ", ".join(present[:20]) + (", ..." if len(present) > 20 else "")
        raise AssertionError(f"missing column(s) {', '.join(missing)}; the table has {listed or 'no columns'}")


def check_rows(table: Any, *, exactly: int | None = None, at_least: int | None = 1,
               at_most: int | None = None) -> None:
    """Check the table's row count; by default, that it has at least one row.

    *exactly* overrides the two bounds.
    """
    count = _row_count(table)
    if exactly is not None:
        if count != exactly:
            raise AssertionError(f"expected {exactly} rows, the table has {count}")
        return
    if at_least is not None and count < at_least:
        raise AssertionError(f"expected at least {at_least} rows, the table has {count}")
    if at_most is not None and count > at_most:
        raise AssertionError(f"expected at most {at_most} rows, the table has {count}")


def check_between(values: Any, low: float | None = None, high: float | None = None) -> None:
    """Check that a number, or every number in a column or sequence, lies in [low, high]; NaN fails.

    Leave *low* or *high* out for a one-sided bound.
    """
    if low is None and high is None:
        raise ValueError("check_between needs low, high or both")
    items = [values] if isinstance(values, numbers.Real) or not isinstance(values, Iterable) else list(values)
    bad: list[str] = []
    for position, value in enumerate(items):
        number = float(value)
        if math.isnan(number) or (low is not None and number < low) or (high is not None and number > high):
            bad.append(f"{value!r} at position {position}")
    if bad:
        bounds = f"[{'-inf' if low is None else low}, {'inf' if high is None else high}]"
        raise AssertionError(f"{len(bad)} of {len(items)} values outside {bounds}: {_shown(bad)}")


def check_same_labels(left: Iterable[Any], right: Iterable[Any], *, ignore_order: bool = False) -> None:
    """Check that two label columns hold the same labels, compared through as_labels.

    By default they must agree position by position. With *ignore_order*
    they must hold the same labels the same number of times, in any order.
    """
    first, second = as_labels(left), as_labels(right)
    if ignore_order:
        a, b = Counter(first), Counter(second)
        differences = [
            f"{label!r}: {a[label]} on the left, {b[label]} on the right"
            for label in sorted(set(a) | set(b)) if a[label] != b[label]
        ]
        if differences:
            raise AssertionError(f"the labels differ in {len(differences)} label(s): {_shown(differences)}")
        return
    if len(first) != len(second):
        raise AssertionError(f"the columns have {len(first)} and {len(second)} labels")
    differences = [
        f"position {position}: {x!r} vs {y!r}"
        for position, (x, y) in enumerate(zip(first, second)) if x != y
    ]
    if differences:
        raise AssertionError(f"{len(differences)} of {len(first)} labels differ: {_shown(differences)}")


def check_counts(labels: Iterable[Any], table: Any, *, key: str, count: str) -> None:
    """Check that table[count] gives, for each label in table[key], how many times it occurs in labels.

    Both sides go through as_labels, so a cluster column read back from a CSV
    as integers matches the categorical strings in adata.obs. The table must
    list every label once and no other; a listed label with a count of 0
    may be absent from labels.
    """
    check_columns(table, [key, count])
    tally = Counter(as_labels(labels))
    keys = as_labels(table[key])
    problems: list[str] = []
    listed: dict[str, int] = {}
    for label, raw in zip(keys, list(table[count])):
        number = float(raw)
        if math.isnan(number) or not number.is_integer():
            problems.append(f"{label!r}: count {raw!r} is not a whole number")
            continue
        if label in listed:
            problems.append(f"{label!r} is listed twice")
            continue
        listed[label] = int(number)
    for label, expected in listed.items():
        if tally.get(label, 0) != expected:
            problems.append(f"{label!r}: the table says {expected}, the labels hold {tally.get(label, 0)}")
    for label in sorted(set(tally) - set(listed)):
        problems.append(f"{label!r}: {tally[label]} in the labels, not in the table")
    if problems:
        raise AssertionError(f"the counts in {count!r} do not match the labels: {_shown(problems)}")


def check_files(*paths: str) -> list[Path]:
    """Check that each output exists and is not empty, and record it as an input of the step.

    Paths are relative to this module's results, as for write_output, for
    example figures/umap_leiden.png. Returns the absolute paths.

    :raises ValueError: no path, or a path outside figures/, tables/,
        intermediate/ and logs/.
    :raises RuntimeError: not running in a step of a module.
    """
    if not paths:
        raise ValueError("check_files needs at least one path, for example figures/umap.png")
    ctx = step_context()
    module = ctx.require_module("check outputs")
    targets = [check_output_path(module, path) for path in paths]
    problems = []
    for path, target in zip(paths, targets):
        if not target.is_file():
            problems.append(f"{path} does not exist" if not target.exists() else f"{path} is not a file")
        elif target.stat().st_size == 0:
            problems.append(f"{path} is empty")
    if problems:
        raise AssertionError(f"results/{module.name}/: {_shown(problems)}")
    for target in targets:
        record_input(ctx, target, via="check_files", contract_checked=False)
    return targets
