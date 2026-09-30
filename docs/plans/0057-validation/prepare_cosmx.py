"""CosMx human liver blocks for the 0057 hold-out: list, warm-up block, extraction and preprocessing.

A unit is one (slide, FOV) block: ``slide_id`` and ``donor_id`` (which holds
the FOV number) in the source file; coordinates are local to the FOV. A block
is eligible with at least 500 cells. Nothing here reads ``author_niche`` or
``author_cell_type``; the population split that needs niche counts is
``define_population.py``.

Stages::

    blocks     list eligible blocks with their cell counts -> blocks.json
    warmup     draw the warm-up block from slide 1's eligible blocks (seed 20260926)
    extract    blocks named in population.json (or the warm-up) -> raw h5ad, X = counts, obs dropped
    units      preprocess (--data-type generic --species human), obs -> batch, opaque uids c01..
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import SKILL_PYTHON, preprocess, read_json, sha256, strip_obs, write_json  # noqa: E402

SOURCE = Path("/workspace/dataset/private/spFoundation_SpatialCorpus/spFoundation_SpatialCorpus_by_species/"
              "Homo_sapiens/nanostring_cosmx_human_liver.h5ad")
MIN_CELLS = 500
SEED = 20260926
TISSUE = "human liver"
QC_LOSS_LIMIT = 0.20


def blocks(root: Path) -> dict:
    code = r'''
import sys, json, anndata
a = anndata.read_h5ad(sys.argv[1], backed="r")
o = a.obs[["slide_id", "donor_id"]].astype(str)
n = o.groupby(["slide_id", "donor_id"]).size()
print(json.dumps([{"slide": s, "fov": f, "n": int(c)} for (s, f), c in n.items()]))
'''
    done = subprocess.run([SKILL_PYTHON, "-c", code, str(SOURCE)], capture_output=True, text=True, check=True)
    table = json.loads(done.stdout.strip().splitlines()[-1])
    eligible = [b for b in table if b["n"] >= MIN_CELLS]
    document = {"source": str(SOURCE), "min_cells": MIN_CELLS, "eligible": eligible,
                "slides": sorted({b["slide"] for b in table}, key=int)}
    write_json(root / "cosmx_blocks.json", document)
    return document


def warmup(root: Path) -> dict:
    document = read_json(root / "cosmx_blocks.json")
    slide1 = document["slides"][0]
    candidates = sorted((b for b in document["eligible"] if b["slide"] == slide1), key=lambda b: int(b["fov"]))
    chosen = random.Random(SEED).choice(candidates)
    write_json(root / "cosmx_warmup.json", chosen)
    return chosen


def extract(root: Path, block: dict, name: str) -> Path:
    target = root / "cosmx_raw" / f"{name}.h5ad"
    if target.exists():
        return target
    code = r'''
import sys, anndata, pandas as pd
a = anndata.read_h5ad(sys.argv[1], backed="r")
o = a.obs[["slide_id", "donor_id"]].astype(str)
mask = ((o["slide_id"] == sys.argv[2]) & (o["donor_id"] == sys.argv[3])).to_numpy()
b = a[mask].to_memory()
x = b.layers["counts"]
out = anndata.AnnData(X=x, var=pd.DataFrame(index=b.var_names))
out.obs_names = b.obs_names
out.obsm["spatial"] = b.obsm["spatial"]
out.write_h5ad(sys.argv[4])
print(out.n_obs)
'''
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([SKILL_PYTHON, "-c", code, str(SOURCE), block["slide"], block["fov"], str(target)], check=True)
    return target


def make_unit(root: Path, uid: str, block: dict) -> dict:
    raw = extract(root, block, uid)
    target = root / "units" / uid / "input.h5ad"
    if not target.exists():
        processed = preprocess(raw, root / "pre" / uid, data_type="generic", species="human", max_mt_pct=None)
        result = read_json(processed.parent / "result.json")
        kept = result["summary"]["n_cells_filtered"] / max(1, result["summary"]["n_cells_raw"])
        if 1 - kept > QC_LOSS_LIMIT:
            raise SystemExit(f"{uid}: QC removed {100 * (1 - kept):.1f}% of cells; stop and report to the owner")
        strip_obs(processed, target)
    return {"input": str(target), "tissue": TISSUE, "data_type": "generic", "sha256": sha256(target)}


def units(root: Path, *, warmup_only: bool = False) -> dict:
    table = read_json(root / "units.json") if (root / "units.json").exists() else {}
    mapping = read_json(root / "holdout_map.json") if (root / "holdout_map.json").exists() else {}
    if warmup_only:
        chosen = read_json(root / "cosmx_warmup.json")
        table["w01"] = make_unit(root, "w01", chosen)
        mapping["w01"] = {"dataset": "CosMx", "role": "warmup", **chosen}
    else:
        population = read_json(root / "population.json")
        for index, block in enumerate(population["units"], start=1):
            uid = f"c{index:02d}"
            table[uid] = make_unit(root, uid, block)
            mapping[uid] = {"dataset": "CosMx", **block}
    write_json(root / "units.json", table)
    write_json(root / "holdout_map.json", mapping)
    return table


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("stage", choices=["blocks", "warmup", "warmup-unit", "units"])
    args = parser.parse_args(argv)
    if args.stage == "blocks":
        document = blocks(args.root)
        print({s: sum(b["slide"] == s for b in document["eligible"]) for s in document["slides"]})
    elif args.stage == "warmup":
        print(warmup(args.root))
    elif args.stage == "warmup-unit":
        print(units(args.root, warmup_only=True))
    else:
        print(json.dumps(units(args.root), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
