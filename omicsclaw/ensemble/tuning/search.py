"""Where to look at a fixed K: search dimensions and candidate parameter sets.

Every function here is deterministic given its arguments. Numeric parameters
are handled on a unit scale: ``0`` is ``low`` and ``1`` is ``high``, linear or
logarithmic as the parameter declares; integers are rounded after mapping
back. Parameter sets are compared by :func:`config_key`.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence

from omicsclaw.ensemble.space import MethodSpec, ParamSpec, SpecError, TuningSpec, validate_params

__all__ = [
    "GRID_POINTS",
    "MAX_DIMENSIONS",
    "NEIGHBOURHOOD_STEP",
    "SearchPlan",
    "config_key",
    "deviation",
    "far_endpoint",
    "fixed_values",
    "full_key",
    "grid_values",
    "neighbourhood_points",
    "random_configs",
    "search_plan",
    "stage1_seed",
    "sweep_points",
    "to_unit",
    "from_unit",
]

MAX_DIMENSIONS = 3
"""Search dimensions at most; further parameters keep their defaults."""

GRID_POINTS = 13
"""Points of a one-dimensional grid over a numeric parameter with many values."""

NEIGHBOURHOOD_STEP = 1 / 8
"""Stage-2 step, as a fraction of a parameter's range on its unit scale."""


# ---- scales ---------------------------------------------------------------------------


def to_unit(param: ParamSpec, value: Any) -> float:
    """Position of a numeric *value* in *param*'s range, in ``[0, 1]`` when inside it."""
    low, high = float(param.low), float(param.high)
    if param.log:
        return (math.log(float(value)) - math.log(low)) / (math.log(high) - math.log(low))
    return (float(value) - low) / (high - low)


def from_unit(param: ParamSpec, position: float) -> Any:
    """The value at *position* (clipped to ``[0, 1]``) of a numeric *param*."""
    position = min(1.0, max(0.0, position))
    low, high = float(param.low), float(param.high)
    if param.log:
        value = math.exp(math.log(low) + position * (math.log(high) - math.log(low)))
    else:
        value = low + position * (high - low)
    if param.type == "int":
        return int(min(param.high, max(param.low, round(value))))
    return round(min(high, max(low, value)), 6)


def config_key(params: Mapping[str, Any]) -> str:
    """A canonical string for a parameter set; equal sets give equal keys."""
    canonical: dict[str, Any] = {}
    for name, value in params.items():
        if isinstance(value, float):
            value = float(f"{value:.10g}")
        canonical[name] = value
    return json.dumps(canonical, sort_keys=True)


# ---- dimensions -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SearchPlan:
    """How one method is searched at a fixed K.

    :ivar dimensions: The searched parameters, by priority.
    :ivar truncated: Active parameters left at their defaults because of
        :data:`MAX_DIMENSIONS`.
    :ivar strategy: ``"grid"`` (one dimension), ``"two_stage"`` (two or
        three) or ``"none"`` (nothing to search).
    """

    method: str
    dimensions: tuple[ParamSpec, ...]
    truncated: tuple[str, ...]
    strategy: str


def fixed_values(method_spec: MethodSpec, k: int | None = None) -> dict[str, Any]:
    """The parameters held fixed while tuning: the pins, and K for an exact method."""
    control = method_spec.k_control
    if control is None:
        return {}
    values = dict(control.pin)
    if control.kind == "exact" and k is not None:
        values[control.param] = int(k)
    return values


def search_plan(spec: TuningSpec, method: str) -> SearchPlan:
    """The search dimensions of *method*: parameters active under the defaults
    and the pins, not controlling K and not pinned, by priority, at most
    :data:`MAX_DIMENSIONS`.

    :raises SpecError: *method* has no ``k_control``.
    """
    method_spec = spec.method(method)
    control = method_spec.k_control
    if control is None:
        raise SpecError(f"method {method!r} of {spec.skill} has no k_control and cannot be tuned at a fixed K")
    active = validate_params(spec, method, dict(control.pin))
    candidates = [
        param
        for param in method_spec.ordered_params()
        if param.name in active and param.name != control.param and param.name not in control.pin
    ]
    dimensions = tuple(candidates[:MAX_DIMENSIONS])
    truncated = tuple(param.name for param in candidates[MAX_DIMENSIONS:])
    if not dimensions:
        strategy = "none"
    elif len(dimensions) == 1:
        strategy = "grid"
    else:
        strategy = "two_stage"
    return SearchPlan(method=method, dimensions=dimensions, truncated=truncated, strategy=strategy)


# ---- one-dimensional grid ------------------------------------------------------------------


def grid_values(param: ParamSpec) -> list[Any]:
    """Every value of a categorical or boolean *param*, every integer of a
    short integer range, else :data:`GRID_POINTS` evenly spaced values (on the
    log scale for a log parameter), ascending and distinct."""
    if param.type == "bool":
        return [False, True]
    if param.type == "categorical":
        return list(param.choices)
    if param.type == "int" and int(param.high) - int(param.low) + 1 <= GRID_POINTS:
        return list(range(int(param.low), int(param.high) + 1))
    values: list[Any] = []
    for index in range(GRID_POINTS):
        value = from_unit(param, index / (GRID_POINTS - 1))
        if value not in values:
            values.append(value)
    return values


# ---- stage 1: one-parameter sweeps ---------------------------------------------------------


def far_endpoint(param: ParamSpec, default: Any) -> Any:
    """The end of *param*'s range farthest from *default*; a tie takes the larger value."""
    if param.type == "bool":
        return not default
    if param.type == "categorical":
        choices = list(param.choices)
        index = choices.index(default)
        first, last = choices[0], choices[-1]
        if index > len(choices) - 1 - index:
            return first
        if index < len(choices) - 1 - index:
            return last
        return max(first, last)
    position = to_unit(param, default)
    return param.low if position > 1 - position else param.high


def _endpoints(param: ParamSpec) -> list[Any]:
    if param.type == "bool":
        return [False, True]
    if param.type == "categorical":
        return [param.choices[0], param.choices[-1]]
    return [param.low if param.type != "float" else float(param.low),
            param.high if param.type != "float" else float(param.high)]


def sweep_points(dimensions: Sequence[ParamSpec], defaults: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The one-parameter sweeps of stage 1, each changing one parameter from its default.

    Three dimensions: each parameter's far endpoint. Two dimensions: both
    endpoints of the first, the far endpoint of the second. An endpoint equal
    to the default is left out.
    """
    points: list[dict[str, Any]] = []
    if len(dimensions) >= 3:
        for param in dimensions[:3]:
            points.append({param.name: _typed(param, far_endpoint(param, defaults[param.name]))})
    elif len(dimensions) == 2:
        first, second = dimensions
        for value in _endpoints(first):
            points.append({first.name: _typed(first, value)})
        points.append({second.name: _typed(second, far_endpoint(second, defaults[second.name]))})
    return [
        point for point in points
        if all(defaults.get(name) != value for name, value in point.items())
    ]


def _typed(param: ParamSpec, value: Any) -> Any:
    if param.type == "int":
        return int(value)
    if param.type == "float":
        return float(value)
    return value


# ---- stage 2: neighbourhood -----------------------------------------------------------------


def _move(param: ParamSpec, value: Any, steps: int) -> Any:
    """*value* moved by *steps* neighbourhood steps, clipped to the range."""
    if param.type == "bool":
        return (not value) if steps % 2 else value
    if param.type == "categorical":
        choices = list(param.choices)
        index = min(len(choices) - 1, max(0, choices.index(value) + steps))
        return choices[index]
    moved = from_unit(param, to_unit(param, value) + steps * NEIGHBOURHOOD_STEP)
    if param.type == "int" and abs(moved - value) < abs(steps):
        moved = int(min(param.high, max(param.low, value + steps)))
    return moved


def _direction(param: ParamSpec, centre: Any, default: Any) -> int:
    if param.type == "bool":
        return 1
    if param.type == "categorical":
        choices = list(param.choices)
        difference = choices.index(centre) - choices.index(default)
    else:
        difference = to_unit(param, centre) - to_unit(param, default)
    return -1 if difference < 0 else 1


def full_key(spec: TuningSpec, method: str, params: Mapping[str, Any]) -> str | None:
    """:func:`config_key` of *params* after :func:`validate_params`, or ``None`` if invalid."""
    try:
        return config_key(validate_params(spec, method, params))
    except SpecError:
        return None


def neighbourhood_points(
    spec: TuningSpec,
    method: str,
    dimensions: Sequence[ParamSpec],
    centre: Mapping[str, Any],
    defaults: Mapping[str, Any],
    taken: Iterable[str],
    *,
    key: Callable[[Mapping[str, Any]], str] | None = None,
) -> list[dict[str, Any]]:
    """Stage-2 parameter sets around *centre*.

    Three dimensions: one step up and down along each (six points). Two
    dimensions: the four axis points, and two diagonal points one step along
    and one step against the direction from the default to the centre (a
    dimension where the centre equals the default counts as positive). A
    point clipped onto one already taken is replaced by the point two steps
    the other way along the same dimensions, and dropped if that is taken too.

    :param centre: The explicit parameters of the centre trial; it must hold
        a value for every dimension. Each point is *centre* with some
        dimensions moved; a parameter the move makes inactive is dropped.
    :param defaults: The default value of every dimension.
    :param taken: The key of every parameter set already run or planned.
    :param key: How a parameter set is keyed; :func:`full_key` by default.
        A point is kept only if it is valid (:func:`full_key` is not ``None``)
        and its key is new.
    :returns: The new points, as explicit parameter sets.
    """
    keyer = key or (lambda params: full_key(spec, method, params) or "")
    seen = set(taken)
    moves: list[dict[str, int]] = []
    names = [param.name for param in dimensions]
    if len(dimensions) >= 3:
        for name in names[:3]:
            moves.append({name: 1})
            moves.append({name: -1})
    elif len(dimensions) == 2:
        for name in names:
            moves.append({name: 1})
            moves.append({name: -1})
        signs = {param.name: _direction(param, centre[param.name], defaults[param.name]) for param in dimensions}
        moves.append({name: signs[name] for name in names})
        moves.append({name: -signs[name] for name in names})
    by_name = {param.name: param for param in dimensions}
    points: list[dict[str, Any]] = []
    for move in moves:
        for attempt in (move, {name: -2 * step for name, step in move.items()}):
            point = dict(centre)
            for name, steps in attempt.items():
                point[name] = _move(by_name[name], centre[name], steps)
            if full_key(spec, method, point) is None:
                point = _drop_inactive(spec, method, point, keep=set(by_name))
                if full_key(spec, method, point) is None:
                    continue
            identity = keyer(point)
            if identity not in seen:
                seen.add(identity)
                points.append(point)
                break
    return points


def _drop_inactive(spec: TuningSpec, method: str, point: dict[str, Any], *, keep: set[str]) -> dict[str, Any]:
    """*point* without the parameters, outside *keep*, whose activation condition fails."""
    method_spec = spec.method(method)
    trimmed = dict(point)
    for name in list(trimmed):
        if name in keep:
            continue
        param = method_spec.params.get(name)
        if param is None or not param.active_when:
            continue
        if not all(pred.param in trimmed and pred.holds(trimmed[pred.param]) for pred in param.active_when):
            trimmed.pop(name)
    return trimmed


# ---- random search --------------------------------------------------------------------------


def stage1_seed(run_id: str, method: str, index: int | None = None) -> int:
    """The random-search seed of one method's stage 1: ``sha256(run_id|method|stage1[|index])``."""
    text = f"{run_id}|{method}|stage1" + (f"|{index}" if index is not None else "")
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (2**63)


def random_configs(
    spec: TuningSpec,
    method: str,
    dimensions: Sequence[ParamSpec],
    count: int,
    seed: int,
    *,
    fixed: Mapping[str, Any],
    taken: Iterable[str],
    attempts: int = 1000,
    key: Callable[[Mapping[str, Any]], str] | None = None,
) -> list[dict[str, Any]]:
    """*count* distinct valid parameter sets drawn uniformly over *dimensions*.

    Numeric parameters are uniform on their unit scale (log-uniform for a log
    parameter), categorical and boolean ones uniform over their values; the
    rest are *fixed* and the defaults. Sets whose key is in *taken* are
    redrawn. Fewer than *count* sets are returned only when *attempts* draws
    were not enough.

    :param key: How a parameter set (fixed values included) is keyed against
        *taken*; :func:`full_key` by default.
    :returns: Each set's searched values (``{name: value}`` for *dimensions*).
    """
    rng = random.Random(seed)
    seen = set(taken)
    drawn: list[dict[str, Any]] = []
    for _ in range(attempts):
        if len(drawn) >= count:
            break
        point: dict[str, Any] = {}
        for param in dimensions:
            if param.type == "bool":
                point[param.name] = rng.random() < 0.5
            elif param.type == "categorical":
                point[param.name] = param.choices[rng.randrange(len(param.choices))]
            else:
                point[param.name] = from_unit(param, rng.random())
        full = {**fixed, **point}
        if full_key(spec, method, full) is None:
            continue
        identity = key(full) if key is not None else full_key(spec, method, full)
        if identity in seen:
            continue
        seen.add(identity)
        drawn.append(point)
    return drawn


# ---- deviation from the defaults ---------------------------------------------------------------


def deviation(
    values: Mapping[str, Any],
    method_spec: MethodSpec,
    *,
    ignore: Iterable[str] = (),
) -> tuple[int, float]:
    """How far *values* are from *method_spec*'s defaults.

    :returns: The number of parameters that differ from their default, and
        the sum of their distances: ``|x - default|`` on the unit scale for a
        numeric parameter, 1 for any other. A parameter present in *values*
        and not active under the defaults counts as differing. Parameters in
        *ignore* (K and the pins) are not counted.
    """
    skip = set(ignore)
    count = 0
    distance = 0.0
    for name, value in values.items():
        if name in skip:
            continue
        param = method_spec.params.get(name)
        if param is None:
            continue
        default = param.default
        if value == default and type(value) is type(default):
            continue
        if param.type in ("float", "int") and default is not None:
            gap = abs(to_unit(param, value) - to_unit(param, default))
            if gap == 0:
                continue
            count += 1
            distance += gap
        else:
            count += 1
            distance += 1.0
    return count, distance
