"""Download, verify and convert the DLPFC slices of the 0057 hold-out.

Stages (each idempotent)::

    download   counts (S3), spot positions (HumanPilot GitHub), the spatialLIBD sce object (Dropbox)
    verify     S3 multipart ETag, GitHub git-blob SHA-1, sha256 of everything -> manifest.json
    convert    counts + in-tissue positions -> raw/<slice>.h5ad (no annotation)
    rebuild    the same conversion for 151673/151674, compared with the development files
    units      spatial-preprocess (--max-mt-pct 100) and obs -> batch; opaque uids u01..u10
    truth      layer labels from the sce object into truth/ and truth_map.json (after the runs)

The sce object holds the layer annotation; it is opened only by the truth
stage, after the hold-out runs.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import DEV_DATA, DLPFC_TISSUE, SKILL_PYTHON, preprocess, read_json, sha256, strip_obs, write_json  # noqa: E402

HOLDOUT = ("151507", "151508", "151509", "151510", "151669", "151670", "151671", "151672", "151675", "151676")
DEV = ("151673", "151674")
EXPECTED_SPOTS = {"151507": 4226, "151508": 4384, "151509": 4789, "151510": 4634, "151669": 3661,
                  "151670": 3498, "151671": 4110, "151672": 4015, "151675": 3592, "151676": 3460}
COUNTS_URL = "https://spatial-dlpfc.s3.us-east-2.amazonaws.com/h5/{id}_filtered_feature_bc_matrix.h5"
POSITIONS_URL = "https://raw.githubusercontent.com/LieberInstitute/HumanPilot/master/10X/{id}/tissue_positions_list.txt"
POSITIONS_API = "https://api.github.com/repos/LieberInstitute/HumanPilot/contents/10X/{id}/tissue_positions_list.txt"
SCE_URL = "https://www.dropbox.com/s/f4wcvtdq428y73p/Human_DLPFC_Visium_processedData_sce_scran_spatialLIBD.Rdata?dl=1"
SCE_NAME = "Human_DLPFC_Visium_processedData_sce_scran_spatialLIBD.Rdata"


def _fetch(url: str, target: Path) -> None:
    if target.is_file() and target.stat().st_size > 0:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    subprocess.run(["curl", "-sSL", "--retry", "5", "-o", str(tmp), url], check=True)
    tmp.rename(target)


def _head_etag(url: str) -> str:
    done = subprocess.run(["curl", "-sI", url], capture_output=True, text=True, check=True)
    for line in done.stdout.splitlines():
        if line.lower().startswith("etag:"):
            return line.split(":", 1)[1].strip().strip('"')
    raise RuntimeError(f"no ETag for {url}")


def multipart_etag(path: Path, part_mib: int) -> str:
    """The S3 ETag of *path* uploaded in parts of *part_mib* MiB."""
    size = part_mib * 1024 * 1024
    digests = []
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(size), b""):
            digests.append(hashlib.md5(block).digest())
    if len(digests) == 1:
        return digests[0].hex()
    return hashlib.md5(b"".join(digests)).hexdigest() + f"-{len(digests)}"


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def download(root: Path, slices=HOLDOUT + DEV) -> None:
    for slice_id in slices:
        _fetch(COUNTS_URL.format(id=slice_id), root / "download" / f"{slice_id}_counts.h5")
        _fetch(POSITIONS_URL.format(id=slice_id), root / "download" / f"{slice_id}_positions.txt")
    _fetch(SCE_URL, root / "download" / SCE_NAME)


def verify(root: Path, slices=HOLDOUT + DEV) -> dict:
    manifest = read_json(root / "manifest.json") if (root / "manifest.json").exists() else {"files": {}}
    problems = []
    for slice_id in slices:
        counts = root / "download" / f"{slice_id}_counts.h5"
        etag = _head_etag(COUNTS_URL.format(id=slice_id))
        matched = next((p for p in (8, 5, 16) if multipart_etag(counts, p) == etag), None)
        if matched is None:
            problems.append(f"{counts.name}: ETag {etag} matches no part size")
        manifest["files"][counts.name] = {"sha256": sha256(counts), "etag": etag, "etag_part_mib": matched}
        positions = root / "download" / f"{slice_id}_positions.txt"
        blob = git_blob_sha1(positions)
        remote = json.loads(subprocess.run(["curl", "-sSL", POSITIONS_API.format(id=slice_id)],
                                           capture_output=True, text=True, check=True).stdout).get("sha")
        if remote != blob:
            problems.append(f"{positions.name}: git blob {blob} != {remote}")
        manifest["files"][positions.name] = {"sha256": sha256(positions), "git_blob_sha1": blob, "remote": remote}
    sce = root / "download" / SCE_NAME
    recorded = manifest["files"].get(SCE_NAME, {}).get("sha256")
    digest = sha256(sce)
    if recorded and recorded != digest:
        problems.append(f"{SCE_NAME}: sha256 changed since first download (TOFU)")
    manifest["files"][SCE_NAME] = {"sha256": digest, "tofu": True, "size": sce.stat().st_size}
    manifest["problems"] = problems
    write_json(root / "manifest.json", manifest)
    return manifest


def convert(root: Path, slice_id: str) -> Path:
    """Counts and in-tissue positions of one slice as an ``.h5ad`` without any annotation."""
    target = root / "raw" / f"{slice_id}.h5ad"
    if target.exists():
        return target
    code = r'''
import sys, pandas as pd, scanpy as sc, numpy as np
counts, positions, out = sys.argv[1:4]
a = sc.read_10x_h5(counts)
a.var_names_make_unique()
pos = pd.read_csv(positions, header=None, index_col=0,
                  names=["barcode", "in_tissue", "array_row", "array_col", "pxl_row", "pxl_col"])
pos = pos.loc[pos["in_tissue"] == 1]
a = a[a.obs_names.isin(pos.index)].copy()
pos = pos.loc[a.obs_names]
a.obs["in_tissue"] = pos["in_tissue"].values
a.obs["array_row"] = pos["array_row"].values
a.obs["array_col"] = pos["array_col"].values
a.obsm["spatial"] = pos[["pxl_col", "pxl_row"]].to_numpy(dtype=float)
a.write_h5ad(out)
print(a.n_obs)
'''
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([SKILL_PYTHON, "-c", code, str(root / "download" / f"{slice_id}_counts.h5"),
                    str(root / "download" / f"{slice_id}_positions.txt"), str(target)], check=True)
    return target


def rebuild_check(root: Path) -> dict:
    """Rebuild 151673/151674 from the downloads and compare barcodes, genes and counts with the dev files."""
    report = {}
    code = r'''
import sys, anndata, numpy as np, json
a = anndata.read_h5ad(sys.argv[1]); b = anndata.read_h5ad(sys.argv[2])
common = a.obs_names.intersection(b.obs_names)
same_obs = set(a.obs_names) == set(b.obs_names)
x = a[common].X; y = b[common][:, a.var_names].X if set(a.var_names) <= set(b.var_names) else None
equal = bool(y is not None and abs(x - y).sum() == 0)
print(json.dumps({"n_rebuilt": int(a.n_obs), "n_dev": int(b.n_obs), "same_obs": bool(same_obs), "same_counts": equal}))
'''
    for slice_id in DEV:
        rebuilt = convert(root, slice_id)
        done = subprocess.run([SKILL_PYTHON, "-c", code, str(rebuilt), str(DEV_DATA / f"{slice_id}.h5ad")],
                              capture_output=True, text=True)
        report[slice_id] = json.loads(done.stdout.strip().splitlines()[-1]) if done.returncode == 0 else done.stderr[-1000:]
    write_json(root / "rebuild_check.json", report)
    return report


def units(root: Path) -> dict:
    table = read_json(root / "units.json") if (root / "units.json").exists() else {}
    mapping = read_json(root / "holdout_map.json") if (root / "holdout_map.json").exists() else {}
    for index, slice_id in enumerate(HOLDOUT, start=1):
        uid = f"u{index:02d}"
        target = root / "units" / uid / "input.h5ad"
        if not target.exists():
            raw = convert(root, slice_id)
            processed = preprocess(raw, root / "pre" / uid, data_type="visium", species="human", max_mt_pct=100)
            strip_obs(processed, target)
        table[uid] = {"input": str(target), "tissue": DLPFC_TISSUE, "data_type": "visium", "sha256": sha256(target)}
        mapping[uid] = {"dataset": "DLPFC", "slice": slice_id}
    write_json(root / "units.json", table)
    write_json(root / "holdout_map.json", mapping)
    return table


RSCRIPT = "/opt/conda/envs/OmicsClaw/bin/Rscript"
TRUTH_COLUMN = "layer_guess"
_EXTRACT_R = r"""
args <- commandArgs(trailingOnly = TRUE)
suppressMessages(library(SingleCellExperiment))
env <- new.env()
load(args[1], envir = env)
sce <- env[["sce"]]
cd <- as.data.frame(colData(sce))
out <- data.frame(sample = as.character(cd$sample_name), barcode = as.character(cd$barcode),
                  label = as.character(cd[[args[3]]]), stringsAsFactors = FALSE)
write.csv(out, args[2], row.names = FALSE)
"""


def extract_truth(rdata: Path, out_dir: Path, mapping: dict, column: str = TRUTH_COLUMN) -> dict:
    """Layer labels of every hold-out slice from the sce object; returns the truth map.

    Writes ``<out_dir>/<uid>.csv`` (``obs_id,label``) per DLPFC unit of *mapping*.
    """
    import csv

    out_dir.mkdir(parents=True, exist_ok=True)
    script = out_dir / "extract.R"
    script.write_text(_EXTRACT_R, encoding="utf-8")
    table = out_dir / "all_labels.csv"
    subprocess.run([RSCRIPT, str(script), str(rdata), str(table), column], check=True, capture_output=True)
    rows: dict[str, list[tuple[str, str]]] = {}
    with open(table, newline="", encoding="utf-8") as source:
        for row in csv.DictReader(source):
            rows.setdefault(row["sample"], []).append((row["barcode"], row["label"]))
    truth_map = {}
    for uid, entry in mapping.items():
        if entry.get("dataset") != "DLPFC":
            continue
        target = out_dir / f"{uid}.csv"
        with open(target, "w", newline="", encoding="utf-8") as sink:
            writer = csv.writer(sink)
            writer.writerow(["obs_id", "label"])
            for barcode, label in rows.get(entry["slice"], []):
                if label not in ("", "NA"):
                    writer.writerow([barcode, label])
        truth_map[uid] = {"path": str(target), "format": "csv", "holdout": True}
    table.unlink()
    return truth_map


def truth_stage(root: Path) -> dict:
    """Extract the hold-out truth into ``<root>/truth`` and merge it into ``truth_map.json``."""
    truth_map = extract_truth(root / "download" / SCE_NAME, root / "truth", read_json(root / "holdout_map.json"))
    existing = read_json(root / "truth_map.json") if (root / "truth_map.json").exists() else {}
    write_json(root / "truth_map.json", {**existing, **truth_map})
    return truth_map


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("stage", choices=["download", "verify", "convert", "rebuild", "units", "truth"])
    args = parser.parse_args(argv)
    if args.stage == "download":
        download(args.root)
    elif args.stage == "verify":
        print(json.dumps(verify(args.root)["problems"], indent=1))
    elif args.stage == "convert":
        counts = {s: convert(args.root, s) for s in HOLDOUT}
        print({s: str(p) for s, p in counts.items()})
    elif args.stage == "rebuild":
        print(json.dumps(rebuild_check(args.root), indent=1))
    elif args.stage == "units":
        print(json.dumps(units(args.root), indent=1))
    else:
        print(json.dumps(truth_stage(args.root), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
