"""Sample merging keeps counts and reports the labels actually present."""

import anndata as ad
import numpy as np
import pandas as pd

from skills._sdk.notebook import load_skill


def test_merge_aligns_features_preserves_existing_labels_and_leaves_inputs_untouched():
    library = load_skill("sc-multi-count")
    first = ad.AnnData(np.array([[2, 3]], dtype=float), obs=pd.DataFrame({"sample_id": ["existing"]}, index=["c"]),
                       var=pd.DataFrame(index=["a", "b"]))
    second = ad.AnnData(np.array([[7, 11]], dtype=float), obs=pd.DataFrame(index=["c"]),
                        var=pd.DataFrame(index=["b", "d"]))
    merged = library.merge_samples([first, second], sample_ids=["one", "two"])
    assert list(merged.obs_names) == ["one_c", "two_c"]
    assert list(merged.obs["sample_id"]) == ["existing", "two"]
    np.testing.assert_array_equal(merged.X, [[2, 3, 0], [0, 7, 11]])
    np.testing.assert_array_equal(merged.layers["counts"], merged.X)
    assert list(first.obs_names) == ["c"] and "sample_id" not in second.obs
    assert "counts" not in first.layers
    table = library.per_sample_summary(merged).set_index("sample_id")
    assert table.loc["existing", "total_umis"] == 5
    assert table.loc["two", "total_umis"] == 18
    assert library.barcode_metrics(merged).iloc[0]["barcode"] == "two_c"
