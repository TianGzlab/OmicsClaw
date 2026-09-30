"""What ``inspect_trials`` computes: ``python -m omicsclaw.ensemble.tuning.inspect``.

For a list of trials of one run: each trial's number of labels, the pairwise
adjusted mutual information between them, and, for one trial, its top marker
genes per domain (Wilcoxon on the input's ``X``).

Input: ``--spec`` JSON ``{input, trials: [{key, labels}], markers_for?: key,
top_n}``. Prints ``INSPECT=`` and a JSON object. Runs under the skill
interpreter.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

__all__ = ["compute", "main"]


def compute(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Label counts, pairwise AMI and optional markers for the trials in *spec*."""
    import numpy as np
    import pandas as pd
    from sklearn.metrics import adjusted_mutual_info_score

    tables = {}
    for item in spec["trials"]:
        table = pd.read_csv(item["labels"], dtype=str, keep_default_na=False)
        tables[item["key"]] = dict(zip(table["obs_id"], table["label"]))
    keys = list(tables)
    counts = {key: len(set(tables[key].values())) for key in keys}
    pairs = []
    for left, right in itertools.combinations(keys, 2):
        shared = sorted(set(tables[left]) & set(tables[right]))
        if not shared:
            continue
        a = [tables[left][name] for name in shared]
        b = [tables[right][name] for name in shared]
        pairs.append({"a": left, "b": right, "ami": round(float(adjusted_mutual_info_score(a, b)), 4)})
    document: dict[str, Any] = {"n_labels": counts, "ami": pairs}
    target = spec.get("markers_for")
    if target:
        import anndata

        from omicsclaw.ensemble.tuning.markers import rank_markers, stratified_sample

        adata = anndata.read_h5ad(spec["input"])
        obs_ids = [str(x) for x in adata.obs_names]
        labels = np.asarray([tables[target].get(name, "") for name in obs_ids]).astype(str)
        chosen = stratified_sample(labels, 20_000)
        top = int(spec.get("top_n", 5))
        document["markers"] = {"trial": target, "domains": rank_markers(adata[chosen], labels[chosen], top)}
    return document


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare trials of one run.")
    parser.add_argument("--spec", type=Path, required=True)
    args = parser.parse_args(argv)
    document = compute(json.loads(args.spec.read_text(encoding="utf-8")))
    print("INSPECT=" + json.dumps(document))
    return 0


if __name__ == "__main__":
    sys.exit(main())
