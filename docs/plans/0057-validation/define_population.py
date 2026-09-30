"""Split the CosMx blocks into the hold-out populations and draw the units.

Reads, per eligible block, only how many ``author_niche`` values occur and
their shares, before any method runs. The warm-up block is removed
first. Per slide: 12 blocks without replacement from the primary population
(``K* >= 3``) and 4 from the single population (``K* == 2``), seed 20260926.
``K*`` is the number of niches present; the sensitivity version counts niches
with a share of at least 5%.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import SKILL_PYTHON, read_json, write_json  # noqa: E402
from prepare_cosmx import SEED, SOURCE  # noqa: E402

PRIMARY = 12
SINGLE = 4


def niche_counts(root: Path) -> list[dict]:
    code = r'''
import sys, json, anndata
a = anndata.read_h5ad(sys.argv[1], backed="r")
o = a.obs[["slide_id", "donor_id", "author_niche"]].astype(str)
out = []
for (s, f), d in o.groupby(["slide_id", "donor_id"]):
    share = d["author_niche"].value_counts(normalize=True)
    out.append({"slide": s, "fov": f, "n": int(len(d)), "k_star": int((share > 0).sum()),
                "k_star_5pct": int((share >= 0.05).sum())})
print(json.dumps(out))
'''
    done = subprocess.run([SKILL_PYTHON, "-c", code, str(SOURCE)], capture_output=True, text=True, check=True)
    return json.loads(done.stdout.strip().splitlines()[-1])


def define(root: Path) -> dict:
    blocks = read_json(root / "cosmx_blocks.json")
    warm = read_json(root / "cosmx_warmup.json")
    eligible = {(b["slide"], b["fov"]) for b in blocks["eligible"]}
    counts = [c for c in niche_counts(root) if (c["slide"], c["fov"]) in eligible
              and not (c["slide"] == warm["slide"] and c["fov"] == warm["fov"])]
    rng = random.Random(SEED)
    units = []
    for slide in blocks["slides"]:
        mine = sorted((c for c in counts if c["slide"] == slide), key=lambda c: int(c["fov"]))
        primary = [c for c in mine if c["k_star"] >= 3]
        single = [c for c in mine if c["k_star"] == 2]
        units += [{**c, "population": "primary"} for c in rng.sample(primary, min(PRIMARY, len(primary)))]
        units += [{**c, "population": "single"} for c in rng.sample(single, min(SINGLE, len(single)))]
    document = {"seed": SEED, "warmup": warm, "units": units}
    write_json(root / "population.json", document)
    return document


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args(argv)
    document = define(args.root)
    print(json.dumps({"units": len(document["units"])}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
