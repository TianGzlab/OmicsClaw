import numpy as np
import pandas as pd
import pytest
from skills._sdk.notebook import load_skill


def expression():
    rng = np.random.default_rng(9)
    signals = rng.normal(size=(3, 20))
    values = np.vstack([signal + rng.normal(0, 0.05, (20, 20)) for signal in signals])
    return pd.DataFrame(values + 10, index=[f"gene-{i}" for i in range(60)],
                        columns=[f"sample {i}" for i in range(20)])


def test_r_wgcna_accepts_integer_matrices_and_honors_explicit_power():
    api = load_skill("bulkrna-coexpression")
    data = (expression() * 100).round().astype(int)
    try:
        result = api.analyze(data, power=6, min_module_size=10)
    except ImportError as exc:
        pytest.skip(str(exc))
    assert set(result.gene) == set(data.index)
    assert api.run_info(result)["summary"]["soft_power"] == 6
    assert api.run_info(result)["summary"]["n_modules"] >= 2
    assert not api.threshold_fit(result).empty
    assert set(api.hub_genes(result).gene).issubset(data.index)
    assert len(api.module_sizes_figure(result).axes) == 1


def test_too_few_samples_are_rejected_before_backend_execution():
    with pytest.raises(ValueError, match="eight samples"):
        load_skill("bulkrna-coexpression").analyze(expression().iloc[:, :4])
