"""In-kernel variable inspection scripts and payload parsing.

The FastAPI notebook layer talks to a real Jupyter kernel over
``jupyter_client``. To look inside user objects (DataFrames, AnnData
slots, scalars) we have to run a snippet in the kernel and read the
payload back from stdout.

This module is the single home for:

* Strict input validation (variable names must be dotted identifiers)
* Script construction (`build_var_detail_script`, `build_adata_slot_script`)
* Payload parsing (`parse_var_detail_payload`)

Both builders emit Python source that prints a JSON payload between
``PAYLOAD_BEGIN``/``PAYLOAD_END`` markers. The payload schema is
stable across both flows so the router layer can treat them uniformly.
"""

from __future__ import annotations

import json
import re
from typing import Any

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

PAYLOAD_BEGIN = "__OMICSCLAW_VAR_PAYLOAD_BEGIN__"
PAYLOAD_END = "__OMICSCLAW_VAR_PAYLOAD_END__"

#: AnnData slot names supported by ``build_adata_slot_script``.
VALID_SLOTS: tuple[str, ...] = (
    "obs",
    "var",
    "obsm",
    "varm",
    "obsp",
    "varp",
    "layers",
    "uns",
)

# Only dotted identifier paths are allowed. This blocks function calls,
# subscripts, attribute chains on expressions, etc — the variable name is
# interpolated into generated Python source, so it has to be validated
# before it ever reaches the kernel.
_VALID_NAME_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$"
)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def _validate_name(name: str) -> None:
    if not isinstance(name, str) or not _VALID_NAME_RE.match(name):
        raise ValueError(
            f"invalid variable name {name!r}: only dotted identifiers are allowed"
        )


def _validate_slot(slot: str) -> None:
    if slot not in VALID_SLOTS:
        raise ValueError(
            f"unsupported AnnData slot {slot!r}; valid: {list(VALID_SLOTS)}"
        )


def _clamp(value: int, *, low: int, high: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(value, high))


# ---------------------------------------------------------------------------
# Script builders
# ---------------------------------------------------------------------------


def build_var_detail_script(
    name: str,
    max_rows: int = 50,
    max_cols: int = 50,
) -> str:
    """Return Python source that emits a JSON summary of ``name``.

    The emitted payload shape is:

    * ``{"type": "dataframe", "name", "shape", "dtypes", "table"}``
    * ``{"type": "series",    "name", "shape", "dtypes", "table"}``
    * ``{"type": "anndata",   "name", "summary": {...}}``
    * ``{"type": "scalar",    "name", "content", "py_type"}``
    * ``{"type": "missing",   "name"}``
    * ``{"type": "error",     "name", "error"}``
    """
    _validate_name(name)
    max_rows = _clamp(max_rows, low=1, high=500)
    max_cols = _clamp(max_cols, low=1, high=200)

    header = "\n".join(
        [
            "def __omicsclaw_var_detail_inner():",
            "    import json as _json",
            f"    _name = {name!r}",
            f"    _begin = {PAYLOAD_BEGIN!r}",
            f"    _end = {PAYLOAD_END!r}",
            f"    _max_rows = {max_rows}",
            f"    _max_cols = {max_cols}",
        ]
    )
    script = f"{header}\n{_VAR_DETAIL_BODY}\n__omicsclaw_var_detail_inner()\ndel __omicsclaw_var_detail_inner\n"
    # Sanity check: if this doesn't compile it's a bug in this module,
    # not in the caller's input.
    compile(script, "<omicsclaw:var_detail>", "exec")
    return script


def build_adata_slot_script(
    var_name: str,
    slot: str,
    key: str,
    max_rows: int = 50,
    max_cols: int = 50,
) -> str:
    """Return Python source that emits a JSON view into ``var.slot[key]``.

    For ``obs``/``var``: omit ``key`` to preview the entire DataFrame, or
    provide a column name to preview that single series.

    For ``obsm``/``varm``/``obsp``/``varp``/``layers``: ``key`` is required
    and the payload previews the first ``max_rows × max_cols`` slice.

    For ``uns``: ``key`` is required; DataFrame values are previewed as
    tables, everything else as their ``repr``.
    """
    _validate_name(var_name)
    _validate_slot(slot)
    if not isinstance(key, str):
        raise ValueError(f"key must be a string, got {type(key).__name__}")
    max_rows = _clamp(max_rows, low=1, high=500)
    max_cols = _clamp(max_cols, low=1, high=200)

    header = "\n".join(
        [
            "def __omicsclaw_adata_slot_inner():",
            "    import json as _json",
            f"    _name = {var_name!r}",
            f"    _slot = {slot!r}",
            f"    _key = {key!r}",
            f"    _begin = {PAYLOAD_BEGIN!r}",
            f"    _end = {PAYLOAD_END!r}",
            f"    _max_rows = {max_rows}",
            f"    _max_cols = {max_cols}",
        ]
    )
    script = f"{header}\n{_ADATA_SLOT_BODY}\n__omicsclaw_adata_slot_inner()\ndel __omicsclaw_adata_slot_inner\n"
    compile(script, "<omicsclaw:adata_slot>", "exec")
    return script


# ---------------------------------------------------------------------------
# Payload parsing
# ---------------------------------------------------------------------------


def parse_var_detail_payload(stdout: str) -> dict[str, Any]:
    """Decode the JSON payload emitted by a var-inspection script.

    Returns ``{"type": "missing"}`` for any recoverable failure
    (absent markers, corrupt JSON, non-object payload) so callers do
    not need to special-case the error path.
    """
    if not stdout:
        return {"type": "missing"}
    try:
        start = stdout.index(PAYLOAD_BEGIN) + len(PAYLOAD_BEGIN)
        end = stdout.index(PAYLOAD_END, start)
    except ValueError:
        return {"type": "missing"}
    try:
        result = json.loads(stdout[start:end])
    except json.JSONDecodeError:
        return {"type": "missing"}
    if not isinstance(result, dict):
        return {"type": "missing"}
    return result


# ---------------------------------------------------------------------------
# Generated-script bodies
# ---------------------------------------------------------------------------
#
# These are plain Python source strings appended to a small config header
# produced by the builder functions. They do **not** depend on any
# runtime values other than the leading ``_name``, ``_slot`` etc. locals,
# which is why they can live as module-level constants instead of being
# regenerated per request.

_VAR_DETAIL_BODY = r"""
    def _emit(payload):
        try:
            encoded = _json.dumps(payload, default=str, ensure_ascii=False)
        except Exception as _exc:
            encoded = _json.dumps({
                "type": "error",
                "name": _name,
                "error": "payload serialization failed: " + str(_exc),
            })
        print(_begin + encoded + _end)

    _ns = globals()
    _parts = _name.split(".")
    _head = _parts[0]
    if _head not in _ns:
        _emit({"type": "missing", "name": _name})
        return
    _obj = _ns[_head]
    try:
        for _p in _parts[1:]:
            _obj = getattr(_obj, _p)
    except AttributeError as _exc:
        _emit({"type": "error", "name": _name, "error": str(_exc)})
        return

    # pandas DataFrame / Series
    try:
        import pandas as _pd
        if isinstance(_obj, _pd.DataFrame):
            _sub = _obj.iloc[:_max_rows, :_max_cols].copy()
            _sub = _sub.astype(object).where(_pd.notna(_sub), None)
            _dtypes = {str(c): str(d) for c, d in _obj.dtypes.items()}
            _table = _sub.to_dict(orient="split")
            _table["columns"] = [str(c) for c in _table.get("columns", [])]
            _table["index"] = [str(i) for i in _table.get("index", [])]
            _emit({
                "type": "dataframe",
                "name": _name,
                "shape": [int(_obj.shape[0]), int(_obj.shape[1])],
                "dtypes": _dtypes,
                "table": _table,
            })
            return
        if isinstance(_obj, _pd.Series):
            _col = str(_obj.name) if _obj.name is not None else "value"
            _sub = _obj.iloc[:_max_rows].to_frame(name=_col)
            _sub = _sub.astype(object).where(_pd.notna(_sub), None)
            _table = _sub.to_dict(orient="split")
            _table["columns"] = [str(c) for c in _table.get("columns", [])]
            _table["index"] = [str(i) for i in _table.get("index", [])]
            _emit({
                "type": "series",
                "name": _name,
                "shape": [int(_obj.shape[0]), 1],
                "dtypes": {_col: str(_obj.dtype)},
                "table": _table,
            })
            return
    except ImportError:
        pass
    except Exception as _exc:
        _emit({"type": "error", "name": _name, "error": str(_exc)})
        return

    # AnnData
    try:
        if type(_obj).__name__ == "AnnData":
            def _keys(container, limit=200):
                try:
                    items = [str(k) for k in container]
                except Exception:
                    items = []
                kept = items[:limit]
                return {
                    "keys": kept,
                    "total": len(items),
                    "more": max(0, len(items) - len(kept)),
                }

            _obs_cols = getattr(_obj.obs, "columns", [])
            _var_cols = getattr(_obj.var, "columns", [])
            _obsm = getattr(_obj, "obsm", None)
            _varm = getattr(_obj, "varm", None)
            _obsp = getattr(_obj, "obsp", None)
            _varp = getattr(_obj, "varp", None)
            _layers = getattr(_obj, "layers", None)
            _uns = getattr(_obj, "uns", None)
            _obs_pack = _keys(_obs_cols)
            _var_pack = _keys(_var_cols)
            _obsm_pack = _keys(list(_obsm.keys()) if _obsm is not None else [])
            _varm_pack = _keys(list(_varm.keys()) if _varm is not None else [])
            _obsp_pack = _keys(list(_obsp.keys()) if _obsp is not None else [])
            _varp_pack = _keys(list(_varp.keys()) if _varp is not None else [])
            _layers_pack = _keys(list(_layers.keys()) if _layers is not None else [])
            _uns_pack = _keys(list(_uns.keys()) if _uns is not None else [])
            _emit({
                "type": "anndata",
                "name": _name,
                "summary": {
                    "shape": [int(_obj.shape[0]), int(_obj.shape[1])],
                    "obs_columns": _obs_pack["keys"],
                    "obs_columns_total": _obs_pack["total"],
                    "var_columns": _var_pack["keys"],
                    "var_columns_total": _var_pack["total"],
                    "obsm_keys": _obsm_pack["keys"],
                    "varm_keys": _varm_pack["keys"],
                    "obsp_keys": _obsp_pack["keys"],
                    "varp_keys": _varp_pack["keys"],
                    "layers": _layers_pack["keys"],
                    "uns_keys": _uns_pack["keys"],
                },
            })
            return
    except Exception as _exc:
        _emit({"type": "error", "name": _name, "error": str(_exc)})
        return

    # Scalar / repr fallback
    try:
        _repr = repr(_obj)
        if len(_repr) > 10000:
            _repr = _repr[:10000] + "..."
        _emit({
            "type": "scalar",
            "name": _name,
            "content": _repr,
            "py_type": type(_obj).__name__,
        })
    except Exception as _exc:
        _emit({"type": "error", "name": _name, "error": str(_exc)})
"""


_ADATA_SLOT_BODY = r"""
    def _emit(payload):
        try:
            encoded = _json.dumps(payload, default=str, ensure_ascii=False)
        except Exception as _exc:
            encoded = _json.dumps({
                "type": "error",
                "name": _name,
                "error": "payload serialization failed: " + str(_exc),
            })
        print(_begin + encoded + _end)

    _ns = globals()
    if _name not in _ns:
        _emit({"type": "missing", "name": _name})
        return
    _obj = _ns[_name]
    if type(_obj).__name__ != "AnnData":
        _emit({
            "type": "error",
            "name": _name,
            "error": _name + " is not an AnnData (got " + type(_obj).__name__ + ")",
        })
        return

    _slot_obj = getattr(_obj, _slot, None)
    if _slot_obj is None:
        _emit({
            "type": "error",
            "name": _name,
            "error": "slot " + _slot + " not found",
        })
        return

    try:
        import pandas as _pd
        import numpy as _np

        if _slot in ("obs", "var"):
            if _key:
                try:
                    _series = _slot_obj[_key]
                except Exception as _exc:
                    _emit({
                        "type": "error",
                        "name": _name,
                        "error": "key " + _key + " not in " + _slot,
                    })
                    return
                _df = _series.iloc[:_max_rows].to_frame(name=str(_key))
                _df = _df.astype(object).where(_pd.notna(_df), None)
                _table = _df.to_dict(orient="split")
                _table["columns"] = [str(c) for c in _table.get("columns", [])]
                _table["index"] = [str(i) for i in _table.get("index", [])]
                _emit({
                    "type": "dataframe",
                    "name": _name + "." + _slot + "[" + repr(_key) + "]",
                    "shape": [int(len(_slot_obj)), 1],
                    "dtypes": {str(_key): str(_series.dtype)},
                    "table": _table,
                })
            else:
                _sub = _slot_obj.iloc[:_max_rows, :_max_cols].copy()
                _sub = _sub.astype(object).where(_pd.notna(_sub), None)
                _dtypes = {str(c): str(d) for c, d in _slot_obj.dtypes.items()}
                _table = _sub.to_dict(orient="split")
                _table["columns"] = [str(c) for c in _table.get("columns", [])]
                _table["index"] = [str(i) for i in _table.get("index", [])]
                _emit({
                    "type": "dataframe",
                    "name": _name + "." + _slot,
                    "shape": [int(_slot_obj.shape[0]), int(_slot_obj.shape[1])],
                    "dtypes": _dtypes,
                    "table": _table,
                })
            return

        if _slot in ("obsm", "varm", "obsp", "varp"):
            if not _key:
                _keys = list(_slot_obj.keys()) if _slot_obj is not None else []
                _emit({
                    "type": "content",
                    "name": _name + "." + _slot,
                    "content": "keys: " + ", ".join(str(k) for k in _keys[:50]),
                })
                return
            _arr = _slot_obj[_key]
            _shape = list(_arr.shape) if hasattr(_arr, "shape") else []
            if hasattr(_arr, "toarray"):
                _preview = _arr[:10, :10].toarray()
            elif isinstance(_arr, _np.ndarray):
                _preview = _arr[: min(10, _arr.shape[0]), : min(10, _arr.shape[1] if _arr.ndim > 1 else 1)]
                if _arr.ndim == 1:
                    _preview = _preview.reshape(-1, 1)
            else:
                _preview = None
            if _preview is not None:
                _cols = [str(i) for i in range(_preview.shape[1])]
                _idx = [str(i) for i in range(_preview.shape[0])]
                _emit({
                    "type": "dataframe",
                    "name": _name + "." + _slot + "[" + repr(_key) + "]",
                    "shape": _shape,
                    "dtypes": {},
                    "table": {
                        "columns": _cols,
                        "index": _idx,
                        "data": _preview.tolist(),
                    },
                })
                return
            _emit({
                "type": "content",
                "name": _name + "." + _slot + "[" + repr(_key) + "]",
                "content": "shape=" + str(_shape),
            })
            return

        if _slot == "layers":
            if not _key:
                _keys = list(_slot_obj.keys()) if _slot_obj is not None else []
                _emit({
                    "type": "content",
                    "name": _name + ".layers",
                    "content": "keys: " + ", ".join(str(k) for k in _keys[:50]),
                })
                return
            _layer = _slot_obj[_key]
            _shape = list(_layer.shape) if hasattr(_layer, "shape") else []
            if hasattr(_layer, "toarray"):
                _preview = _layer[:10, :10].toarray()
            elif isinstance(_layer, _np.ndarray):
                _preview = _layer[:10, :10]
            else:
                _preview = None
            if _preview is not None:
                _emit({
                    "type": "dataframe",
                    "name": _name + ".layers[" + repr(_key) + "]",
                    "shape": _shape,
                    "dtypes": {},
                    "table": {
                        "columns": [str(i) for i in range(_preview.shape[1])],
                        "index": [str(i) for i in range(_preview.shape[0])],
                        "data": _preview.tolist(),
                    },
                })
                return
            _emit({
                "type": "content",
                "name": _name + ".layers[" + repr(_key) + "]",
                "content": "shape=" + str(_shape),
            })
            return

        if _slot == "uns":
            if not _key:
                _keys = list(_slot_obj.keys()) if _slot_obj is not None else []
                _emit({
                    "type": "content",
                    "name": _name + ".uns",
                    "content": "keys: " + ", ".join(str(k) for k in _keys[:50]),
                })
                return
            _val = _slot_obj[_key]
            if isinstance(_val, _pd.DataFrame):
                _sub = _val.iloc[:_max_rows, :_max_cols].copy()
                _sub = _sub.astype(object).where(_pd.notna(_sub), None)
                _dtypes = {str(c): str(d) for c, d in _val.dtypes.items()}
                _table = _sub.to_dict(orient="split")
                _table["columns"] = [str(c) for c in _table.get("columns", [])]
                _table["index"] = [str(i) for i in _table.get("index", [])]
                _emit({
                    "type": "dataframe",
                    "name": _name + ".uns[" + repr(_key) + "]",
                    "shape": list(_val.shape),
                    "dtypes": _dtypes,
                    "table": _table,
                })
                return
            _repr = repr(_val)
            if len(_repr) > 5000:
                _repr = _repr[:5000] + "..."
            _emit({
                "type": "content",
                "name": _name + ".uns[" + repr(_key) + "]",
                "content": _repr,
            })
            return
    except Exception as _exc:
        _emit({"type": "error", "name": _name, "error": str(_exc)})
        return

    _emit({"type": "error", "name": _name, "error": "unhandled slot"})
"""
