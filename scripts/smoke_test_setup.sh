#!/usr/bin/env bash
# End-to-end smoke test for 0_setup_env.sh.
# Builds a fresh env in a throwaway name, runs core demos, verifies imports.
# Run on a clean machine before tagging a release.
#
# Usage:
#   bash scripts/smoke_test_setup.sh                   # auto-named throwaway env
#   bash scripts/smoke_test_setup.sh OmicsClaw_my      # custom env name
#
# Side effects: creates and removes one or two conda envs (the main test env
# and optionally omicsclaw_banksy if Stage 4 runs). Both are cleaned up on
# exit via trap.

set -euo pipefail

ENV_NAME="${1:-OmicsClaw_smoketest_$(date +%s)}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cleanup() {
    echo "[smoke] removing test env $ENV_NAME"
    mamba env remove -n "$ENV_NAME" -y >/dev/null 2>&1 || true
    mamba env remove -n omicsclaw_banksy -y >/dev/null 2>&1 || true
}
trap cleanup EXIT

cd "$PROJECT_ROOT"

echo "[smoke] === Stage 1: bash 0_setup_env.sh $ENV_NAME ==="
time bash 0_setup_env.sh "$ENV_NAME"

echo "[smoke] === Stage 2: import smoke ==="
mamba run -n "$ENV_NAME" python - <<'PY'
import importlib
mods = [
    "scanpy", "anndata", "squidpy", "scvi", "scvelo", "cellrank",
    "torch", "harmonypy", "bbknn", "scanorama",
    "celltypist", "cellphonedb", "gseapy", "pydeseq2",
    "scrublet", "doubletdetection", "arboreto", "palantir",
    "multiqc", "kb_python",
    "esda", "libpysal", "pysal", "ot",
    # thin pip residue (some are optional / may not import without input)
    "spagcn", "GraphST", "tangram",
    # omicsclaw itself
    "omicsclaw",
]
failed = []
for m in mods:
    try:
        importlib.import_module(m)
        print(f"  OK  {m}")
    except Exception as exc:  # noqa: BLE001 — we want all failures listed
        print(f"  FAIL {m}: {exc}")
        failed.append(m)
if failed:
    raise SystemExit(f"{len(failed)} import(s) failed: {failed}")
PY

echo "[smoke] === Stage 3: demo skills ==="
mamba run -n "$ENV_NAME" python omicsclaw.py run spatial-preprocess --demo
mamba run -n "$ENV_NAME" python omicsclaw.py run spatial-domains --demo --method leiden
mamba run -n "$ENV_NAME" python omicsclaw.py run bulkrna-de --demo

echo "[smoke] === Stage 4: banksy sub-env (opt-in) ==="
OMICSCLAW_WITH_BANKSY=1 bash 0_setup_env.sh "$ENV_NAME"
mamba env list | awk '{print $1}' | grep -qx 'omicsclaw_banksy' \
    || { echo "[smoke] FAIL: omicsclaw_banksy not created"; exit 1; }
mamba run -n "$ENV_NAME" python omicsclaw.py run spatial-domains --demo --method banksy

echo "[smoke] ✔ all stages passed"
