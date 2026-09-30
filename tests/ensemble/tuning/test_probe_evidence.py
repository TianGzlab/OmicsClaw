"""The probe design, the stable peaks and the fallback K.

The resolution grid is MultiK's 0.05-2.00 in steps of 0.05, cut at the
search space's lower bound 0.1; generated with ``round`` because
accumulating 0.05 in floating point would miss 1.00, the default, whose
probe trial is the baseline. A stable peak needs a peak frequency of at least
0.5 over the bootstrap, not a single computation: with 5 subsamples the set
of "stable" K flipped between draws. The fallback K may only come from a K
where at least two curves are defined: allowing a single curve let 151674
fall back to K=16, where only the agreement curve existed.
"""

from __future__ import annotations

import asyncio

import pytest

from omicsclaw.ensemble.tuning.calibrate import calibrate, initial_value
from omicsclaw.ensemble.tuning.evidence import fallback_k, load_evidence, ranks
from omicsclaw.ensemble.tuning.probe import (
    K_GRID,
    RESOLUTION_GRID,
    SUBSAMPLE_SEEDS,
    probe_design,
    probe_run_id,
    sub_run_id,
)

RUNNABLE = ["leiden", "louvain", "spagcn", "graphst", "cellcharter"]


def test_the_resolution_grid_contains_one_exactly():
    assert len(RESOLUTION_GRID) == 39
    assert RESOLUTION_GRID[0] == 0.1 and RESOLUTION_GRID[-1] == 2.0
    assert 1.0 in RESOLUTION_GRID and RESOLUTION_GRID.index(1.0) == 18
    accumulated = [0.1]
    for _ in range(38):
        accumulated.append(accumulated[-1] + 0.05)
    assert 1.0 not in accumulated


def test_the_probe_of_the_runnable_methods(domains_spec):
    """42 exact runs (3 methods x 14 K), 78 full runs, 1560 subsample runs."""
    items = probe_design(domains_spec, RUNNABLE)
    kinds = {kind: [i for i in items if i.kind == kind] for kind in ("exact", "full", "sub")}
    assert (len(kinds["exact"]), len(kinds["full"]), len(kinds["sub"])) == (42, 78, 1560)
    assert K_GRID == tuple(range(3, 17)) and len(SUBSAMPLE_SEEDS) == 20
    cellcharter = [i for i in kinds["exact"] if i.method == "cellcharter"]
    assert all(i.params["auto_k"] is False for i in cellcharter)
    assert sorted(i.params["n_domains"] for i in cellcharter) == list(K_GRID)
    defaults = [i for i in kinds["full"] if i.params["resolution"] == 1.0]
    assert {i.method for i in defaults} == {"leiden", "louvain"}
    assert {i.b for i in kinds["sub"]} == set(range(1, 21))
    assert probe_run_id("u01") == "u01-probe" and sub_run_id("u01", 3) == "u01-sub03"


def test_no_method_is_told_a_number_of_domains_other_than_the_grid(domains_spec):
    items = probe_design(domains_spec, RUNNABLE)
    for item in items:
        if item.kind == "exact":
            assert set(item.params) <= {"n_domains", "auto_k"}
        else:
            assert set(item.params) == {"resolution"}


def _row(f=None, c=None, a=None, pf=(0.0, 0.0, 0.0)):
    return {"f": f, "c": c, "a": a, "runs": 1, "a_members": [],
            "peak_frequency": {"f": pf[0], "c": pf[1], "a": pf[2]}}


def test_ranks_share_ties():
    assert ranks({3: 0.5, 4: 0.9, 5: 0.5}) == {4: 1.0, 3: 2.5, 5: 2.5}


def test_the_fallback_needs_two_defined_curves():
    """K=16 has only ``a`` (f below the 2.5% gate makes f and c undefined) and
    is top of ``a``; it must not win on a mean of one rank."""
    rows = {
        4: _row(f=0.30, c=0.50, a=0.50),
        10: _row(f=0.10, c=0.80, a=0.60),
        16: _row(f=0.01, c=0.99, a=0.95),
    }
    assert fallback_k(rows, 0.025) == 10


@pytest.mark.parametrize(
    "rows, expected",
    [
        ({4: _row(f=0.3, c=0.5, a=0.5), 10: _row(f=0.1, c=0.8, a=0.6)}, 10),
        ({4: _row(f=0.3, c=0.8, a=0.5), 10: _row(f=0.1, c=0.5, a=0.6)}, 4),
        ({4: _row(f=0.3, c=0.5), 10: _row(f=0.1, c=0.8)}, 4),
        ({4: _row(f=0.3, c=0.8, a=0.6), 10: _row(f=0.1, c=0.5, a=0.5)}, 4),
        ({5: _row(f=0.3, c=0.8, a=0.5), 7: _row(f=0.3, c=0.8, a=0.5)}, 5),
        ({5: _row(f=0.01), 7: _row(a=0.4)}, None),
    ],
)
def test_the_fallback_table(rows, expected):
    """Mean rank first; on a tie the larger ``a``, then the smaller K."""
    assert fallback_k(rows, 0.025) == expected


def test_stable_peaks_need_half_the_resamples():
    document = {
        "grid": [3, 4, 5, 6], "min_f": 0.025,
        "per_k": {
            "3": _row(f=0.5, c=0.9, a=0.5, pf=(0.49, 0.2, 0.0)),
            "4": _row(f=0.2, c=0.7, a=0.6, pf=(0.1, 0.5, 0.0)),
            "5": _row(f=0.1, c=0.6, a=0.7, pf=(0.0, 0.0, 0.8)),
            "6": _row(f=0.01, c=None, a=None, pf=(0.0, 0.0, 0.0)),
        },
    }
    evidence = load_evidence(document)
    assert evidence.stable_peaks == [4, 5]
    assert evidence.rows[4].in_stable_peaks and not evidence.rows[3].in_stable_peaks
    assert evidence.rows[6].defined == {"f": False, "c": False, "a": False}
    assert evidence.rows[3].ranks["f"] == 1.0 and evidence.rows[6].ranks["f"] is None


# ---- calibration -----------------------------------------------------------------------------


def _runner(mapping_fn, calls):
    async def run(value):
        calls.append(value)
        return mapping_fn(value), {"value": value}
    return run


def _run(coro):
    return asyncio.run(coro)


def test_calibration_bisects_on_the_log_scale():
    calls = []
    result = _run(calibrate(7, _runner(lambda r: int(r * 7), calls), initial=0.5, low=0.1, high=2.0))
    assert result.status == "ok" and result.hit[1] == 7
    assert calls[0] == 0.5 and calls[1] == 2.0
    assert calls[2] == pytest.approx(1.0, abs=1e-4)


def test_history_brackets_without_rerunning():
    calls = []
    result = _run(calibrate(
        7, _runner(lambda r: int(r * 7), calls), initial=0.9, low=0.1, high=2.0,
        history=[(0.5, 3), (1.5, 10)],
    ))
    assert calls[0] == 0.9 and calls[1] == pytest.approx(round((0.9 * 1.5) ** 0.5, 4))
    assert result.status == "ok"


def test_calibration_gives_up_after_four_extra_runs():
    calls = []
    result = _run(calibrate(7, _runner(lambda r: 6 if r < 1.0 else 8, calls), initial=0.5, low=0.1, high=2.0))
    assert result.status == "off_k" and len(calls) == 5
    assert result.closest[1] in (6, 8)


def test_an_unreachable_target_is_reported():
    calls = []
    result = _run(calibrate(20, _runner(lambda r: 5, calls), initial=1.0, low=0.1, high=2.0))
    assert result.status == "unreachable_k" and calls == [1.0, 2.0]


def test_a_failed_run_stops_calibration():
    result = _run(calibrate(7, _runner(lambda r: None, []), initial=1.0, low=0.1, high=2.0))
    assert result.status == "failed" and len(result.runs) == 1


def test_the_initial_value_comes_from_the_probe_mapping():
    mapping = {0.5: 5, 0.8: 7, 0.9: 7, 1.0: 7, 1.5: 9}
    assert initial_value(mapping, 7, low=0.1, high=2.0) == 0.9
    assert initial_value(mapping, 8, low=0.1, high=2.0) == pytest.approx((1.0 * 1.5) ** 0.5, abs=1e-4)
    assert initial_value(mapping, 12, low=0.1, high=2.0) == pytest.approx((1.5 * 2.0) ** 0.5, abs=1e-4)
    assert initial_value({}, 7, low=0.1, high=2.0) == 1.0
