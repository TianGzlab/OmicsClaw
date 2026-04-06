import importlib.util
import sys
import types
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd


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
    module = _load_module(
        "sc_integrate_contract_test",
        "skills/singlecell/scrna/sc-batch-integration/sc_integrate.py",
    )
    adata = ad.AnnData(
        X=np.ones((2, 2)),
        obs=pd.DataFrame({"batch": ["a", "b"]}, index=["c1", "c2"]),
        var=pd.DataFrame(index=["g1", "g2"]),
    )

    def fake_integrate_scvi(_adata, **_kwargs):
        return {"method": "scvi", "embedding_key": "X_scvi", "n_batches": 2}

    monkeypatch.setattr(module, "integrate_scvi", fake_integrate_scvi)

    summary = module.integrate_scanvi(adata, batch_key="batch")

    assert summary["requested_method"] == "scanvi"
    assert summary["executed_method"] == "scvi"
    assert summary["fallback_used"] is True
    assert "requires existing labels" in summary["fallback_reason"]


def test_doubletfinder_fallback_records_requested_and_executed_method(monkeypatch):
    module = _load_module(
        "sc_doublet_contract_test",
        "skills/singlecell/scrna/sc-doublet-detection/sc_doublet.py",
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
        "skills/singlecell/scrna/sc-cell-communication/sc_cell_communication.py",
    )
    adata = ad.AnnData(
        X=np.array([[3.0, 2.0], [1.0, 4.0]]),
        obs=pd.DataFrame({"cell_type": ["A", "B"]}, index=["c1", "c2"]),
        var=pd.DataFrame(index=["TGFB1", "TGFBR1"]),
    )

    summary = module.run_communication(
        adata,
        method="builtin",
        cell_type_key="cell_type",
        species="human",
    )

    assert summary["requested_method"] == "builtin"
    assert summary["executed_method"] == "builtin"
    assert summary["n_significant"] == 0
    assert summary["pvalue_available"] is False
    assert summary["lr_df"]["pvalue"].isna().all()
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

    assert ("MAST", "SingleCellExperiment", "zellkonverter") in seen
    assert ("DESeq2", "SingleCellExperiment", "zellkonverter") in seen
