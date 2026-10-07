"""Diagnostics and input checks for bulk RNA table results."""
from copy import deepcopy
import numpy as np
import pandas as pd


def attach_info(table, info):
    result = table.copy(deep=True)
    result.attrs['run_info'] = deepcopy(info)
    return result


def read_info(result, *, keep=True):
    return deepcopy(result.attrs.get('run_info', {}) if keep else result.attrs.pop('run_info', {}))


def require_matrix(data, *, counts=False, positive_libraries=False):
    if not isinstance(data, pd.DataFrame) or data.empty:
        raise ValueError('Provide a nonempty feature-by-sample DataFrame')
    if data.index.has_duplicates or data.columns.has_duplicates:
        raise ValueError('Feature and sample identifiers must be unique')
    values = data.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError('Expression must be finite and nonnegative')
    if counts and not np.equal(values, np.floor(values)).all():
        raise ValueError('Raw counts must be integers')
    if positive_libraries and (values.sum(axis=0) <= 0).any():
        raise ValueError('Every sample needs a positive library size')
