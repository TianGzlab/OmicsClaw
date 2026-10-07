"""Synthetic reference/spatial inputs for deconvolution migration parity."""
from pathlib import Path

REFERENCE = Path(__file__).resolve().parent / "golden/spatial-deconv/reference.h5ad"


def _input(path):
    from skills._sdk.notebook import load_demo
    data = load_demo("spatial_synthetic")
    reference = data.copy()
    reference.obs["cell_type"] = reference.obs["domain_ground_truth"]
    REFERENCE.parent.mkdir(parents=True, exist_ok=True)
    reference.write_h5ad(REFERENCE)
    data.write_h5ad(path)


def register(Case, Skill):
    environment = {name: "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS")}
    environment["PYTHONHASHSEED"] = "0"
    return {"spatial-deconv": Skill("skills/spatial/spatial-deconv/spatial_deconv.py",
        "tests.parity.spatial_deconv:run", {
            "flashdeconv": Case(("--method", "flashdeconv", "--reference", str(REFERENCE), "--flashdeconv-n-hvg", "150", "--flashdeconv-sketch-dim", "32"), input=_input, environment=environment),
        })}


def run(case, *, input_path):
    import scanpy as sc
    from skills._sdk.notebook import load_skill
    api = load_skill("spatial-deconv")
    adata = sc.read_h5ad(input_path)
    api.deconvolve(adata, reference=sc.read_h5ad(REFERENCE), method="flashdeconv", sketch_dim=32, n_hvg=150)
    table = api.proportions(adata)
    table.insert(0, "spot", table.index.astype(str))
    return {"adata": adata, "tables": {"proportions.csv": table}}
