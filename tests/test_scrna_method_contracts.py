import importlib.util
import sys
import types
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd
import pytest

# The skill modules import the shared plotting helpers, which need seaborn.
pytest.importorskip("seaborn")


ROOT = Path(__file__).resolve().parent.parent


def _load_module(name: str, relative_path: str):
    path = ROOT / relative_path
    original_scanpy = sys.modules.get("scanpy")
    sys.modules["scanpy"] = types.ModuleType("scanpy")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    try:
        spec.loader.exec_module(module)
    finally:
        if original_scanpy is None:
            sys.modules.pop("scanpy", None)
        else:
            sys.modules["scanpy"] = original_scanpy
    return module


def test_scanvi_fallback_records_requested_and_executed_method(monkeypatch):
    # Integration loads scanpy lazily; keep the substitute through execution.
    monkeypatch.setitem(sys.modules, "scanpy", types.ModuleType("scanpy"))
    module = _load_module(
        "sc_integrate_contract_test",
        "skills/singlecell/scrna/sc-batch-integration/_api.py",
    )
    adata = ad.AnnData(
        X=np.ones((2, 2)),
        obs=pd.DataFrame({"batch": ["a", "b"]}, index=["c1", "c2"]),
        var=pd.DataFrame(index=["g1", "g2"]),
    )

    class Model:
        history = {}

        @staticmethod
        def setup_anndata(*args, **kwargs):
            pass

        def __init__(self, *args, **kwargs):
            pass

        def train(self, **kwargs):
            pass

        def get_latent_representation(self):
            return np.ones((2, 2))

    from skills._sdk import deps
    deps._try_import.cache_clear()
    monkeypatch.setitem(sys.modules, "scvi", types.SimpleNamespace(
        settings=types.SimpleNamespace(seed=None), model=types.SimpleNamespace(SCVI=Model)))
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(cuda=types.SimpleNamespace()))
    adata.var["highly_variable"] = True
    adata.layers["counts"] = adata.X.copy()
    try:
        result = module.integrate(adata, method="scanvi", batch_key="batch", use_gpu=False)
    finally:
        deps._try_import.cache_clear()
    summary = module.run_info(result)["summary"]

    assert summary["requested_method"] == "scanvi"
    assert summary["executed_method"] == "scvi"
    assert summary["fallback_used"] is True
    assert "requires existing labels" in summary["fallback_reason"]


def test_doubletfinder_fallback_records_requested_and_executed_method(monkeypatch):
    module = _load_module(
        "sc_doublet_contract_test",
        "skills/singlecell/scrna/sc-doublet-detection/_api.py",
    )
    adata = ad.AnnData(
        X=np.ones((2, 2)),
        obs=pd.DataFrame(index=["c1", "c2"]),
        var=pd.DataFrame(index=["g1", "g2"]),
    )

    monkeypatch.setattr(module, "run_doubletfinder", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(
        module,
        "run_scdblfinder",
        lambda *_args, **_kwargs: pd.DataFrame(
            {
                "doublet_score": [0.9, 0.1],
                "classification": ["Doublet", "Singlet"],
                "predicted_doublet": [True, False],
            },
            index=["c1", "c2"],
        ),
    )

    summary = module.detect_doublets_doubletfinder(adata, expected_doublet_rate=0.08)

    assert summary["requested_method"] == "doubletfinder"
    assert summary["executed_method"] == "scdblfinder"
    assert summary["fallback_used"] is True
    assert "fell back to scDblFinder" in summary["fallback_reason"]


def test_builtin_communication_marks_non_statistical_significance():
    module = _load_module(
        "sc_communication_contract_test",
        "skills/singlecell/scrna/sc-cell-communication/_api.py",
    )
    adata = ad.AnnData(
        X=np.array([[3.0, 2.0], [1.0, 4.0]]),
        obs=pd.DataFrame({"cell_type": ["A", "B"]}, index=["c1", "c2"]),
        var=pd.DataFrame(index=["TGFB1", "TGFBR1"]),
    )

    table = module.communicate(
        adata,
        method="builtin",
        cell_type_key="cell_type",
        species="human",
    )

    summary = module.run_info(table)
    assert summary["requested_method"] == "builtin"
    assert summary["executed_method"] == "builtin"
    assert summary["n_significant"] == 0
    assert summary["pvalue_available"] is False
    assert table["pvalue"].isna().all()
    assert "leave pvalue empty" in summary["significance_semantics"]


def test_de_runtime_dependency_validation_uses_expected_r_stacks(monkeypatch):
    module = _load_module(
        "sc_de_contract_test",
        "skills/singlecell/scrna/sc-de/sc_de.py",
    )
    seen = []

    def fake_validate_r_environment(*, required_r_packages):
        seen.append(tuple(required_r_packages))

    monkeypatch.setattr(module, "validate_r_environment", fake_validate_r_environment)

    module._validate_runtime_dependencies("mast")
    module._validate_runtime_dependencies("deseq2_r")

    assert ("MAST", "SingleCellExperiment", "Matrix") in seen
    assert ("DESeq2", "SingleCellExperiment", "zellkonverter") in seen
