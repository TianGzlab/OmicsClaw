"""Attach diagnostics without adding columns to scientific tables."""
from copy import deepcopy


def attach(table, **info):
    table.attrs['run_info'] = deepcopy(info)
    return table


def read_info(table, *, keep=True):
    import pandas as pd
    if not isinstance(table, pd.DataFrame):
        raise TypeError('Expected a pandas DataFrame')
    info = deepcopy(table.attrs.get('run_info', {}))
    if not keep:
        table.attrs.pop('run_info', None)
    return info
