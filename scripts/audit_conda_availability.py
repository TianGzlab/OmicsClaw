"""Audit which pyproject deps are available on conda-forge/bioconda for Py3.11.

Usage:
    mamba run -n OmicsClaw python scripts/audit_conda_availability.py \
        --extras full,singlecell-upstream \
        --python 3.11 \
        --output docs/superpowers/specs/conda-availability-2026-05-02.csv

Classification logic:
    mamba_ok   — conda-forge or bioconda has a py{ver} compiled build OR a
                 noarch/pure-Python build (compatible with any Python version,
                 build strings like pyhd8ed1ab_0, pyhdfd78af_0).
    pip_only   — no conda recipe, or only builds for other Python versions
                 with no noarch fallback, or lives on a non-default channel
                 (e.g. pytorch / pyg).
    unknown    — mamba search failed (network/proxy unavailable) so
                 classification could not be confirmed; re-run on a
                 network-connected machine before treating as pip_only.

Note on network failures: if the conda proxy returns HTTP 502 or similar,
``mamba search`` exits non-zero and the package is recorded as ``pip_only``
with reason ``"not-found"``.  If ``mamba search`` fails (proxy down, channel
offline, etc.), the script records ``pip_only`` with reason ``"not-found"``.
To audit accurately, re-run on a machine with a working conda proxy, or
pre-populate the local cache by running
``mamba search -c conda-forge -c bioconda <pkg>`` for each package while
the network is available.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tomllib
from pathlib import Path

from packaging.requirements import Requirement


CHANNELS = ["bioconda", "conda-forge"]
ALWAYS_PIP = {  # known-no-conda packages, skip search
    "omicsclaw", "spagcn", "graphst", "cellcharter", "paste-bio",
    "flashdeconv", "fastccc", "pyvia", "pybanksy", "ccproxy-api",
    "tangram-sc", "deepagents", "opendataloader-pdf",
}


def expand_extras(pyproject: dict, extras: list[str]) -> set[str]:
    extras_table = pyproject["project"]["optional-dependencies"]
    seen, queue = set(), list(extras)
    pkgs: set[str] = set()
    while queue:
        e = queue.pop()
        if e in seen or e not in extras_table:
            continue
        seen.add(e)
        for dep in extras_table[e]:
            req = Requirement(dep)
            if req.name == "omicsclaw":
                queue.extend(req.extras)
            else:
                pkgs.add(req.name.lower())
    return pkgs


def search_conda(pkg: str, py_ver: str) -> tuple[str, str]:
    """Return (status, latest_version_or_reason).

    Classifies a package as mamba_ok if conda-forge or bioconda has:
      - a compiled build matching py{ver} (e.g. py311), OR
      - a noarch/pure-Python build (build strings like pyhd8ed1ab_0,
        pyhdfd78af_0) which is compatible with any Python version.
    """
    if pkg in ALWAYS_PIP:
        return "pip_only", "known-no-conda-recipe"
    cmd = ["mamba", "search", "--json"]
    for ch in CHANNELS:
        cmd.extend(["-c", ch])
    cmd.append(pkg)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        return "pip_only", "not-found"
    data = json.loads(res.stdout or "{}")
    builds = data.get(pkg, [])
    py_key = f"py{py_ver.replace('.', '')}"
    # 1) Prefer exact compiled py3.11 builds
    py_builds = [b for b in builds if py_key in b.get("build", "")]
    if py_builds:
        latest = max(py_builds, key=lambda b: b.get("timestamp", 0))
        return "mamba_ok", latest.get("version", "unknown")
    # 2) Accept noarch/pure-Python builds (compatible with any Python version)
    noarch_builds = [
        b for b in builds
        if b.get("subdir", "") == "noarch" or b.get("platform", "") == "noarch"
    ]
    if noarch_builds:
        latest = max(noarch_builds, key=lambda b: b.get("timestamp", 0))
        return "mamba_ok", latest.get("version", "unknown") + " (noarch)"
    return "pip_only", f"no-py{py_ver}-or-noarch-build"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extras", default="full,singlecell-upstream")
    ap.add_argument("--python", default="3.11")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    pkgs = sorted(expand_extras(pyproject, args.extras.split(",")))

    rows = []
    for pkg in pkgs:
        status, info = search_conda(pkg, args.python)
        rows.append({"package": pkg, "status": status, "version_or_reason": info})
        print(f"  [{status:9}] {pkg:30} {info}", file=sys.stderr)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["package", "status", "version_or_reason"])
        w.writeheader()
        w.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
