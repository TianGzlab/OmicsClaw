"""JSON diagnostics for spatial methods that also return labeled tables."""

import json

import numpy as np
import pandas as pd


def _encode(value):
    if isinstance(value, pd.DataFrame):
        return {"__table__": value.to_dict(orient="split"), "index_name": value.index.name}
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Cannot serialize diagnostics value {type(value).__name__}")


def _decode(value):
    if "__table__" in value:
        table = pd.DataFrame(**value["__table__"])
        table.index.name = value["index_name"]
        return table
    return value


def store_info(adata, key, summary):
    adata.uns[key] = json.dumps(summary, default=_encode)


def read_info(adata, key, *, keep=True):
    raw = adata.uns.get(key) if keep else adata.uns.pop(key, None)
    return json.loads(raw, object_hook=_decode) if raw else {}
