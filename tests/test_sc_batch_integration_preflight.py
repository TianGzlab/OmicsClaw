from __future__ import annotations

import numpy as np
import pandas as pd
from anndata import AnnData

from skills.singlecell._lib.preflight import preflight_sc_batch_integration


def _adata_with_obs(obs: pd.DataFrame) -> AnnData:
    adata = AnnData(
        X=np.ones((len(obs), 5), dtype=float),
        obs=obs.copy(),
        var=pd.DataFrame(index=[f"gene_{i}" for i in range(5)]),
    )
    adata.layers["counts"] = adata.X.copy()
    return adata


def test_preflight_blocks_near_unique_batch_key():
    obs = pd.DataFrame(
        {
            "cell_id_like": [f"cell_{i}" for i in range(80)],
        },
        index=[f"cell_{i}" for i in range(80)],
    )
    adata = _adata_with_obs(obs)

    decision = preflight_sc_batch_integration(
        adata,
        method="harmony",
        batch_key="cell_id_like",
    )

    assert decision.status == "blocked"
    assert any("per-cell identifier" in line for line in decision.missing_requirements)


def test_preflight_requires_confirmation_for_many_tiny_batches():
    obs = pd.DataFrame(
        {
            "sample_id": [f"S{i // 2}" for i in range(50)],
        },
        index=[f"cell_{i}" for i in range(50)],
    )
    adata = _adata_with_obs(obs)

    decision = preflight_sc_batch_integration(
        adata,
        method="harmony",
        batch_key="sample_id",
    )

    assert decision.status == "needs_user_input"
    assert any("many small groups" in line for line in decision.confirmations)


def test_preflight_adds_workflow_guidance_for_unprocessed_object():
    obs = pd.DataFrame(
        {
            "sample_id": ["S1", "S1", "S2", "S2"],
        },
        index=[f"cell_{i}" for i in range(4)],
    )
    adata = _adata_with_obs(obs)

    decision = preflight_sc_batch_integration(
        adata,
        method="harmony",
        batch_key="sample_id",
    )

    assert decision.status == "proceed_with_guidance"
    assert any("sc-standardize-input" in line for line in decision.guidance)
    assert any("sc-preprocessing" in line for line in decision.guidance)
