"""Prepare the development units (DLPFC 151673 and 151674) for the 0057 arms.

Each slice is preprocessed with ``--data-type visium --species human
--max-mt-pct 100`` (and, for the sensitivity check, with the default 20),
``obs`` is reduced to ``batch="b0"`` and the input is written under
``<root>/units/<uid>/``. The slice-to-uid map is written outside the units
(``<root>/dev_map.json``); ground truth is not copied anywhere.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import DEV_DATA, DEV_SLICES, DLPFC_TISSUE, preprocess, read_json, sha256, strip_obs, write_json  # noqa: E402

UIDS = {("151673", 100): "d1", ("151674", 100): "d2", ("151673", 20): "d1m20", ("151674", 20): "d2m20"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--preprocessed", type=Path, default=None,
                        help="directory holding <slice>_mt<pct>/processed.h5ad from an earlier run")
    args = parser.parse_args(argv)
    units = read_json(args.root / "units.json") if (args.root / "units.json").exists() else {}
    mapping = {}
    for (slice_id, mt), uid in UIDS.items():
        target = args.root / "units" / uid / "input.h5ad"
        if not target.exists():
            existing = args.preprocessed / f"{slice_id}_mt{mt}" / "processed.h5ad" if args.preprocessed else None
            if existing is None or not existing.is_file():
                existing = preprocess(DEV_DATA / f"{slice_id}.h5ad", args.root / "pre" / f"{slice_id}_mt{mt}",
                                      data_type="visium", species="human", max_mt_pct=mt)
            strip_obs(existing, target)
        units[uid] = {"input": str(target), "tissue": DLPFC_TISSUE, "data_type": "visium",
                      "sha256": sha256(target)}
        mapping[uid] = {"slice": slice_id, "max_mt_pct": mt, "raw": str(DEV_DATA / f"{slice_id}.h5ad")}
    write_json(args.root / "units.json", units)
    write_json(args.root / "dev_map.json", mapping)
    print(units)
    return 0


if __name__ == "__main__":
    sys.exit(main())
