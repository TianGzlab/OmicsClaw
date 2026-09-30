"""Search dimensions and candidate points at a fixed K.

Once K is fixed, what is left to search differs by method: leiden and
louvain have ``spatial_weight`` left (``resolution`` is spent reaching K),
cellcharter has ``n_layers``, spagcn and graphst have two parameters each.
A one-dimensional space is cheap to cover exhaustively, so it gets a grid and
no model call; two or three dimensions get stage 1 (one-parameter sweeps plus
proposals) and a deterministic neighbourhood in stage 2. The neighbourhood
step is 1/8 of the range on each parameter's own scale, a heuristic fixed
before any development data was scored.
"""

from __future__ import annotations

import math

import pytest

from omicsclaw.ensemble.space import validate_params
from omicsclaw.ensemble.tuning.search import (
    GRID_POINTS,
    config_key,
    deviation,
    far_endpoint,
    fixed_values,
    full_key,
    grid_values,
    neighbourhood_points,
    random_configs,
    search_plan,
    stage1_seed,
    sweep_points,
)


@pytest.mark.parametrize(
    "method, dimensions, strategy",
    [
        ("leiden", ["spatial_weight"], "grid"),
        ("louvain", ["spatial_weight"], "grid"),
        ("cellcharter", ["n_layers"], "grid"),
        ("spagcn", ["spagcn_p", "epochs"], "two_stage"),
        ("graphst", ["epochs", "dim_output"], "two_stage"),
        ("stagate", ["k_nn", "stagate_alpha", "epochs"], "two_stage"),
        ("banksy", ["lambda_param", "num_neighbours"], "two_stage"),
    ],
)
def test_the_dimensions_left_once_k_is_fixed(domains_spec, method, dimensions, strategy):
    """K's own parameter and the pins are not searched; ``pre_resolution``
    (active only when ``stagate_alpha > 0``) and cellcharter's ``auto_k_*``
    (inactive with ``auto_k`` pinned off) do not count."""
    plan = search_plan(domains_spec, method)
    assert [p.name for p in plan.dimensions] == dimensions
    assert plan.strategy == strategy and plan.truncated == ()


def test_fixed_values_pin_k_only_for_exact_methods(domains_spec):
    assert fixed_values(domains_spec.method("cellcharter"), 9) == {"auto_k": False, "n_domains": 9}
    assert fixed_values(domains_spec.method("leiden"), 9) == {}


def test_the_spatial_weight_grid_has_thirteen_points_and_contains_the_default():
    """``[round(0.075 * i, 3) for i in range(13)]``: 0.3 is the fifth point,
    so the grid spends 12 new runs, exactly the per-method budget."""
    from omicsclaw.ensemble.space import ParamSpec

    param = ParamSpec(name="spatial_weight", type="float", flag="--w", default=0.3, low=0.0, high=0.9)
    values = grid_values(param)
    assert values == [round(0.075 * i, 3) for i in range(13)]
    assert len(values) == GRID_POINTS and values[4] == 0.3


def test_n_layers_is_covered_completely(domains_spec):
    assert grid_values(domains_spec.method("cellcharter").params["n_layers"]) == [1, 2, 3, 4, 5]


def test_long_integer_and_log_ranges_get_thirteen_points(domains_spec):
    epochs = domains_spec.method("graphst").params["epochs"]
    values = grid_values(epochs)
    assert values[0] == 50 and values[-1] == 600 and len(values) == 13
    ratios = [values[i + 1] / values[i] for i in range(12)]
    assert max(ratios) / min(ratios) < 1.1


@pytest.mark.parametrize(
    "method, expected",
    [
        ("spagcn", [{"spagcn_p": 0.1}, {"spagcn_p": 0.9}, {"epochs": 400}]),
        ("graphst", [{"epochs": 50}, {"epochs": 600}, {"dim_output": 128}]),
        ("stagate", [{"k_nn": 15}, {"stagate_alpha": 1.0}, {"epochs": 1000}]),
        ("banksy", [{"lambda_param": 0.0}, {"lambda_param": 1.0}, {"num_neighbours": 30}]),
    ],
)
def test_stage1_sweeps_change_one_parameter_each(domains_spec, method, expected):
    """Two dimensions: both ends of the first, the far end of the second.
    Three: the far end of each. Each sweep leaves every other parameter at its
    default, so a sweep that moved two parameters would be a proposal in
    disguise."""
    plan = search_plan(domains_spec, method)
    defaults = validate_params(domains_spec, method, {})
    points = sweep_points(plan.dimensions, defaults)
    assert points == expected
    assert all(len(point) == 1 for point in points)


def test_the_far_endpoint_breaks_ties_upwards(domains_spec):
    from omicsclaw.ensemble.space import ParamSpec

    linear = ParamSpec(name="x", type="float", flag="--x", default=0.5, low=0.0, high=1.0)
    assert far_endpoint(linear, 0.5) == 1.0
    assert far_endpoint(linear, 0.7) == 0.0
    choice = ParamSpec(name="c", type="categorical", flag="--c", default=64, choices=(32, 64, 128))
    assert far_endpoint(choice, 64) == 128
    assert far_endpoint(choice, 128) == 32


def test_neighbourhood_steps_and_diagonals(domains_spec):
    """Centre (0.3, 200) against default (0.5, 100): ``spagcn_p`` moved down
    and ``epochs`` up, so the diagonals are (-, +) and (+, -). The epochs step
    is 1/8 of log(400/50), a factor of 8**(1/8)."""
    plan = search_plan(domains_spec, "spagcn")
    defaults = validate_params(domains_spec, "spagcn", {})
    centre = {"n_domains": 7, "spagcn_p": 0.3, "epochs": 200}
    points = neighbourhood_points(
        domains_spec, "spagcn", plan.dimensions, centre, defaults, [full_key(domains_spec, "spagcn", centre)]
    )
    factor = 8 ** (1 / 8)
    up, down = round(200 * factor), round(200 / factor)
    assert (up, down) == (259, 154)
    pairs = [(p["spagcn_p"], p["epochs"]) for p in points]
    assert pairs == [(0.4, 200), (0.2, 200), (0.3, up), (0.3, down), (0.2, up), (0.4, down)]
    assert all(p["n_domains"] == 7 for p in points)


def test_a_clipped_point_that_repeats_one_taken_moves_two_steps_the_other_way(domains_spec):
    plan = search_plan(domains_spec, "spagcn")
    defaults = validate_params(domains_spec, "spagcn", {})
    centre = {"n_domains": 7, "spagcn_p": 0.1, "epochs": 100}
    points = neighbourhood_points(
        domains_spec, "spagcn", plan.dimensions, centre, defaults, [full_key(domains_spec, "spagcn", centre)]
    )
    pairs = [(p["spagcn_p"], p["epochs"]) for p in points]
    # spagcn_p - 0.1 clips onto the centre: replaced by +2 steps (0.3).
    assert pairs[1] == (0.3, 100)
    # the (+, +) diagonal from default (0.5, 100) is (-, +): (0.0 -> 0.1, 130)
    # repeats the epochs axis point, so it becomes (0.3, two steps down).
    assert pairs[2] == (0.1, 130)
    assert pairs[4][0] == 0.3 and pairs[4][1] < 77
    assert len({config_key(p) for p in points}) == len(points) == 6


def test_a_point_repeated_twice_is_dropped(domains_spec):
    plan = search_plan(domains_spec, "graphst")
    defaults = validate_params(domains_spec, "graphst", {})
    centre = {"n_domains": 7, "epochs": 600, "dim_output": 128}
    everything = [
        full_key(domains_spec, "graphst", {"n_domains": 7, "epochs": e, "dim_output": d})
        for e in (322, 440, 600) for d in (32, 64, 128)
    ]
    assert neighbourhood_points(domains_spec, "graphst", plan.dimensions, centre, defaults, everything) == []


def test_three_dimensions_move_one_parameter_at_a_time(domains_spec):
    plan = search_plan(domains_spec, "stagate")
    defaults = validate_params(domains_spec, "stagate", {})
    centre = {"n_domains": 7, "k_nn": 8, "stagate_alpha": 0.5, "epochs": 200}
    points = neighbourhood_points(
        domains_spec, "stagate", plan.dimensions, centre, defaults, [full_key(domains_spec, "stagate", centre)]
    )
    assert len(points) == 6
    for point in points:
        moved = [name for name in ("k_nn", "stagate_alpha", "epochs") if point[name] != centre[name]]
        assert len(moved) == 1
    alphas = sorted(p["stagate_alpha"] for p in points if p["stagate_alpha"] != 0.5)
    assert alphas == [0.375, 0.625]


def test_random_search_is_reproducible_and_avoids_taken_sets(domains_spec):
    plan = search_plan(domains_spec, "spagcn")
    fixed = {"n_domains": 7}
    seed = stage1_seed("u01-a1", "spagcn")
    first = random_configs(domains_spec, "spagcn", plan.dimensions, 3, seed, fixed=fixed, taken=[])
    again = random_configs(domains_spec, "spagcn", plan.dimensions, 3, seed, fixed=fixed, taken=[])
    assert first == again and len(first) == 3
    other = random_configs(domains_spec, "spagcn", plan.dimensions, 3, stage1_seed("u01-a1", "spagcn", 2),
                           fixed=fixed, taken=[])
    assert other != first
    taken = [full_key(domains_spec, "spagcn", {**fixed, **first[0]})]
    avoided = random_configs(domains_spec, "spagcn", plan.dimensions, 3, seed, fixed=fixed, taken=taken)
    assert first[0] not in avoided
    for point in first:
        assert 0.1 <= point["spagcn_p"] <= 0.9 and 50 <= point["epochs"] <= 400


def test_the_seed_is_derived_from_run_method_and_stage():
    import hashlib

    expected = int(hashlib.sha256(b"r1|graphst|stage1").hexdigest(), 16) % (2**63)
    assert stage1_seed("r1", "graphst") == expected


def test_deviation_counts_parameters_and_their_normalised_distance(domains_spec):
    spec = domains_spec.method("spagcn")
    assert deviation({"n_domains": 9, "spagcn_p": 0.5, "epochs": 100}, spec, ignore=("n_domains",)) == (0, 0.0)
    count, distance = deviation({"n_domains": 9, "spagcn_p": 0.7, "epochs": 100}, spec, ignore=("n_domains",))
    assert count == 1 and distance == pytest.approx(0.25)
    count, distance = deviation({"spagcn_p": 0.5, "epochs": 400}, spec)
    assert count == 1 and distance == pytest.approx(math.log(4) / math.log(8))
    graphst = domains_spec.method("graphst")
    assert deviation({"dim_output": 128}, graphst) == (1, 1.0)
