"""Score one trial: ``python -m omicsclaw.ensemble.metrics.score``.

Reads ``<trial>/labels.csv.gz`` (columns ``obs_id,label``) and the reference
arrays of the input ``.h5ad`` (read ``backed='r'``), aligns them by observation
id, runs the registered panel and writes ``<trial>/metrics.json``.

With ``--describe-input PATH`` it instead prints ``DESCRIBE=`` and a JSON
object with the ``.h5ad``'s ``n_obs``, ``n_vars``, ``obs_columns`` and
``obsm_keys``.

Exits 0 on success. Exits 2, with the reason on stderr and nothing written, when
the label set does not cover exactly the input's observations, a reference array
the skill declares (coordinates, or the expression embedding) is missing, or the
analysis has no panel.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from omicsclaw.ensemble.metrics import get_panel

LABELS_FILENAME = "labels.csv.gz"
METRICS_FILENAME = "metrics.json"


class ScoreError(Exception):
    """The trial cannot be scored; the message says why."""


def load_reference(input_path: Path, reference: Dict[str, str]) -> Dict[str, Any]:
    """The observation ids and reference arrays of the input ``.h5ad``.

    :raises ScoreError: The coordinates, or the expression embedding named by
        ``reference["expression_obsm"]``, are not in the input's ``obsm``.
    """
    import anndata
    import numpy as np

    adata = anndata.read_h5ad(input_path, backed="r")
    try:
        obs_ids = np.asarray(adata.obs_names).astype(str)
        coords_key = reference.get("coords_obsm", "spatial")
        if coords_key not in adata.obsm:
            raise ScoreError(f"the input has no obsm[{coords_key!r}]")
        loaded: Dict[str, Any] = {
            "obs_ids": obs_ids,
            "coords": np.asarray(adata.obsm[coords_key], dtype=np.float64)[:, :2],
        }
        expression_key = reference.get("expression_obsm")
        if expression_key:
            if expression_key not in adata.obsm:
                raise ScoreError(
                    f"the input has no obsm[{expression_key!r}]; run the preprocessing "
                    "skill first so the panel can score expression coherence"
                )
            loaded["expression"] = np.asarray(adata.obsm[expression_key], dtype=np.float64)
        return loaded
    finally:
        if getattr(adata, "file", None) is not None:
            adata.file.close()


def aligned_labels(trial: Path, obs_ids) -> Any:
    """The trial's labels in the input's observation order."""
    import pandas as pd

    table = pd.read_csv(trial / LABELS_FILENAME, dtype=str, keep_default_na=False)
    if list(table.columns[:2]) != ["obs_id", "label"]:
        raise ScoreError(f"{LABELS_FILENAME} must have columns obs_id,label")
    if table["obs_id"].duplicated().any():
        raise ScoreError(f"{LABELS_FILENAME} repeats an obs_id")
    wanted = set(obs_ids)
    have = set(table["obs_id"])
    if wanted != have:
        missing = len(wanted - have)
        extra = len(have - wanted)
        raise ScoreError(
            f"the labels cover {len(have)} observations and the input has {len(wanted)} "
            f"({missing} missing, {extra} not in the input)"
        )
    return table.set_index("obs_id").loc[list(obs_ids), "label"].to_numpy()


def score_trial(
    trial: Path,
    input_path: Path,
    analysis: str,
    *,
    cache_dir: Optional[Path] = None,
    reference: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Compute and write ``metrics.json`` for *trial*; return the document."""
    panel = get_panel(analysis)
    if panel is None:
        raise ScoreError(f"no panel is registered for {analysis!r}")
    module_name, _, function_name = panel.compute.partition(":")
    module = importlib.import_module(module_name)
    began = time.monotonic()
    loaded = load_reference(input_path, reference or {})
    labels = aligned_labels(trial, loaded["obs_ids"])
    cache = module.ReferenceCache(cache_dir)
    document = getattr(module, function_name)(labels, loaded, cache)
    document["elapsed_s"] = round(time.monotonic() - began, 3)
    _write_json(trial / METRICS_FILENAME, document)
    return document


def _write_json(path: Path, document: Dict[str, Any]) -> None:
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    with os.fdopen(handle, "w", encoding="utf-8") as sink:
        json.dump(document, sink, indent=1, sort_keys=True)
    os.replace(temporary, path)


def describe_input(input_path: Path) -> Dict[str, Any]:
    """The observation and variable counts, ``obs`` column names and ``obsm`` keys of an ``.h5ad``."""
    import anndata

    adata = anndata.read_h5ad(input_path, backed="r")
    try:
        return {
            "n_obs": int(adata.n_obs),
            "n_vars": int(adata.n_vars),
            "obs_columns": [str(c) for c in adata.obs.columns],
            "obsm_keys": sorted(str(k) for k in adata.obsm.keys()),
        }
    finally:
        if getattr(adata, "file", None) is not None:
            adata.file.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Score one ensemble trial.")
    parser.add_argument("--describe-input", type=Path, default=None,
                        help="print n_obs, n_vars, obs columns and obsm keys of this .h5ad as JSON and exit")
    parser.add_argument("--trial", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--analysis")
    parser.add_argument("--cache", type=Path, default=None)
    parser.add_argument("--reference-json", default="{}")
    args = parser.parse_args(argv)
    if args.describe_input is not None:
        print("DESCRIBE=" + json.dumps(describe_input(args.describe_input)))
        return 0
    if args.trial is None or args.input is None or args.analysis is None:
        parser.error("--trial, --input and --analysis are required")
    try:
        reference = json.loads(args.reference_json)
        document = score_trial(
            args.trial, args.input, args.analysis, cache_dir=args.cache, reference=reference
        )
    except ScoreError as exc:
        print(f"score: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"score": document.get("score"), "n_labels": document.get("n_labels")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
