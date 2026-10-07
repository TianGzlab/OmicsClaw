"""Registration contracts, including unequal source/reference spot counts."""

import anndata as ad
import numpy as np
import pytest

from skills._sdk.notebook import load_skill


def slices():
    data = ad.AnnData(np.array([[1, 3], [3, 1], [1, 4], [4, 1], [2, 2]], dtype=float))
    data.obs["slice"] = ["ref", "ref", "src", "src", "src"]
    data.obsm["spatial"] = np.array([[0, 0], [10, 0], [30, 5], [35, 5], [40, 5]], dtype=float)
    return data


def test_paste_transports_source_to_reference_with_unequal_counts(monkeypatch):
    import paste
    from skills.spatial._lib.register import run_registration

    transport = np.array([[.2, .1, .1], [.1, .2, .3]])
    monkeypatch.setattr(paste, "pairwise_align", lambda *args, **kwargs: transport)
    data = slices()
    original = data.obsm["spatial"].copy()
    run_registration(data, slice_key="slice", reference_slice="ref")
    expected = transport.T @ original[:2] / transport.sum(axis=0)[:, None]
    np.testing.assert_allclose(data.obsm["spatial_aligned"][2:], expected)
    np.testing.assert_array_equal(data.obsm["spatial"], original)


def test_backend_failure_is_not_reported_as_success(monkeypatch):
    import paste
    from skills.spatial._lib.register import run_registration

    def fail(*args, **kwargs):
        raise RuntimeError("solver failure")
    monkeypatch.setattr(paste, "pairwise_align", fail)
    with pytest.raises(RuntimeError, match="solver failure"):
        run_registration(slices(), slice_key="slice", reference_slice="ref")


def test_public_registration_and_shift_table():
    library = load_skill("spatial-register")
    data = slices()
    assert library.register(data, reference_slice="ref") is data
    assert library.run_info(data)["n_slices"] == 2
    table = library.shift_table(data)
    assert len(table) == data.n_obs
    assert table["shift_distance"].iloc[:2].eq(0).all()
    assert library.run_info(data, keep=False)
    assert library.run_info(data) == {}


def test_single_slice_is_rejected():
    with pytest.raises(ValueError, match="two slices"):
        load_skill("spatial-register").register(slices()[:2].copy(), slice_key="slice")
