"""A skill's machine-readable search space: ``tuning.yaml``.

:func:`load_tuning_spec` reads and validates one file; :class:`TuningCatalog`
holds every valid file of a skill index; :func:`validate_params` checks one
method's parameters and fills in defaults; :func:`render_cli_args` turns the
result into the script's command-line flags.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from omicsclaw.ensemble.metrics import PANELS

__all__ = [
    "Constraint",
    "K_CONTROL_KINDS",
    "KControl",
    "MethodSpec",
    "OutputSpec",
    "ParamSpec",
    "Predicate",
    "ResourceSpec",
    "SkippedTuning",
    "SpecError",
    "TUNING_FILENAME",
    "TuningCatalog",
    "TuningSpec",
    "load_tuning_spec",
    "render_cli_args",
    "validate_params",
]

TUNING_FILENAME = "tuning.yaml"

PARAM_TYPES = ("float", "int", "bool", "categorical")
GPU_MODES = ("none", "preferred", "required")
PREDICATE_OPS = ("eq", "ne", "gt", "ge", "lt", "le", "in")
CONSTRAINT_OPS = ("lt", "le", "gt", "ge", "ne")
RESERVED_FLAGS = ("--input", "--output", "--demo")
OUTPUT_KINDS = ("labels", "embedding")
K_CONTROL_KINDS = ("exact", "calibrate")

_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_TOP_KEYS = {
    "schema_version",
    "skill",
    "script",
    "analysis",
    "method_flag",
    "output",
    "reference",
    "defaults",
    "context",
    "methods",
    "note",
}
_PARAM_KEYS = {
    "type",
    "flag",
    "low",
    "high",
    "choices",
    "default",
    "log",
    "priority",
    "active_when",
    "note",
    "switch",
}
_METHOD_KEYS = {"params", "resources", "constraints", "note", "k_control"}
_K_CONTROL_KEYS = {"kind", "param", "pin"}
_RESOURCE_KEYS = {"gpu", "memory_gb", "cpus", "timeout_s"}
_OP_SYMBOLS = {"eq": "==", "ne": "!=", "gt": ">", "ge": ">=", "lt": "<", "le": "<=", "in": "in"}


class SpecError(ValueError):
    """A ``tuning.yaml`` or a parameter set that does not satisfy it."""


def _compare(op: str, left: Any, right: Any) -> bool:
    if op == "eq":
        return left == right
    if op == "ne":
        return left != right
    if op == "in":
        return left in right
    if op == "gt":
        return left > right
    if op == "ge":
        return left >= right
    if op == "lt":
        return left < right
    if op == "le":
        return left <= right
    raise ValueError(f"unknown operator {op!r}")


@dataclass(frozen=True, slots=True)
class Predicate:
    """``param op value``, the condition under which another parameter is active."""

    param: str
    op: str
    value: Any

    def holds(self, value: Any) -> bool:
        """Whether the condition is true for *value* of :attr:`param`."""
        try:
            return _compare(self.op, value, self.value)
        except TypeError:
            return False

    def describe(self) -> str:
        return f"{self.param} {_OP_SYMBOLS[self.op]} {_literal(self.value)}"


@dataclass(frozen=True, slots=True)
class Constraint:
    """``lhs op rhs`` between two parameters, or a parameter and a literal."""

    lhs: Any
    op: str
    rhs: Any
    lhs_is_param: bool
    rhs_is_param: bool

    def describe(self) -> str:
        return f"{_literal(self.lhs)} {_OP_SYMBOLS[self.op]} {_literal(self.rhs)}"


@dataclass(frozen=True, slots=True)
class ParamSpec:
    """One tunable parameter of one method, or a context parameter of the skill."""

    name: str
    type: str
    flag: str
    default: Any
    low: float | None = None
    high: float | None = None
    choices: tuple[Any, ...] = ()
    log: bool = False
    priority: int | None = None
    active_when: tuple[Predicate, ...] = ()
    note: str = ""
    switch: bool = False

    def describe(self) -> str:
        """One line: type, domain, default and activation condition."""
        if self.type in ("float", "int"):
            domain = f"{self.type} in [{_literal(self.low)}, {_literal(self.high)}]"
            if self.log:
                domain += " (log scale)"
        elif self.type == "categorical":
            domain = "one of [" + ", ".join(_literal(choice) for choice in self.choices) + "]"
        else:
            domain = "bool"
        default = "not passed" if self.default is None else _literal(self.default)
        parts = [f"{self.name}: {domain}, default {default}"]
        if self.priority is not None:
            parts.append(f"priority {self.priority}")
        if self.active_when:
            parts.append("only when " + " and ".join(p.describe() for p in self.active_when))
        line = "; ".join(parts)
        if self.note:
            line += f" — {self.note}"
        return line


@dataclass(frozen=True, slots=True)
class ResourceSpec:
    """What one trial of a method asks the resource pool for."""

    gpu: str
    memory_gb: float
    cpus: int
    timeout_s: float


@dataclass(frozen=True, slots=True)
class KControl:
    """How a method's number of output labels is controlled.

    ``exact``: :attr:`param` is the number of labels. ``calibrate``: :attr:`param`
    moves the number of labels monotonically and is searched until it hits
    the target. :attr:`pin` holds parameter values fixed while tuning.
    """

    kind: str
    param: str
    pin: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MethodSpec:
    """One method's parameters, constraints and resources.

    ``k_control`` is ``None`` for a method that does not take part in
    fixed-K tuning.
    """

    name: str
    params: Mapping[str, ParamSpec]
    constraints: tuple[Constraint, ...]
    resources: ResourceSpec
    note: str = ""
    k_control: KControl | None = None

    def ordered_params(self) -> tuple[ParamSpec, ...]:
        """Parameters by priority (unprioritised last), then declaration order."""
        indexed = list(enumerate(self.params.values()))
        indexed.sort(key=lambda item: (item[1].priority is None, item[1].priority or 0, item[0]))
        return tuple(param for _, param in indexed)

    def summary(self, *, omit: Sequence[str] = ()) -> str:
        """The method's search space in a few lines, for error messages and prompts.

        :param omit: Parameter names to leave out, for example those held fixed.
        """
        resources = self.resources
        head = (
            f"method {self.name} (gpu {resources.gpu}, {_literal(resources.memory_gb)} GB, "
            f"{resources.cpus} CPUs, timeout {_literal(resources.timeout_s)} s)"
        )
        lines = [head + ":"]
        shown = [param for param in self.ordered_params() if param.name not in omit]
        if not shown:
            lines.append("  (no tunable parameters)")
        for param in shown:
            lines.append(f"  {param.describe()}")
        for constraint in self.constraints:
            lines.append(f"  constraint: {constraint.describe()}")
        if self.note:
            lines.append(f"  note: {self.note}")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class OutputSpec:
    """Where a trial's result is read from."""

    kind: str
    labels_table: str | None = None
    id_column: str | None = None
    label_column: str | None = None
    h5ad: str | None = None
    embedding: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TuningSpec:
    """One validated ``tuning.yaml``."""

    path: Path
    skill: str
    script: str
    analysis: str
    method_flag: str | None
    output: OutputSpec
    reference: Mapping[str, str]
    context: Mapping[str, ParamSpec]
    methods: Mapping[str, MethodSpec]
    sha256: str
    note: str = ""

    @property
    def directory(self) -> Path:
        return self.path.parent

    @property
    def script_path(self) -> Path:
        return self.directory / self.script

    def method(self, name: str) -> MethodSpec:
        """The named method, or :exc:`SpecError` listing the ones that exist."""
        try:
            return self.methods[name]
        except KeyError:
            known = ", ".join(self.methods)
            raise SpecError(
                f"skill {self.skill!r} has no method {name!r}; methods: {known}"
            ) from None

    def summary(self) -> str:
        """Every method's search space, then the context parameters."""
        blocks = [method.summary() for method in self.methods.values()]
        if self.context:
            lines = ["context (any method; describes the data, not searched):"]
            lines += [f"  {param.describe()}" for param in self.context.values()]
            blocks.append("\n".join(lines))
        return "\n".join(blocks)


# ---- loading ----------------------------------------------------------------


class _Where:
    """The file and field path an error is reported against."""

    def __init__(self, path: Path, parts: tuple[str, ...] = ()) -> None:
        self.path = path
        self.parts = parts

    def __truediv__(self, part: str) -> "_Where":
        return _Where(self.path, (*self.parts, str(part)))

    def error(self, message: str) -> SpecError:
        field_path = ".".join(self.parts) or "<root>"
        return SpecError(f"{self.path}: {field_path}: {message}")


def _mapping(where: _Where, value: Any, *, required: bool = True) -> Mapping[str, Any]:
    if value is None and not required:
        return {}
    if not isinstance(value, Mapping):
        raise where.error(f"must be a mapping, got {_type_name(value)}")
    for key in value:
        if not isinstance(key, str):
            raise where.error(f"keys must be strings, got {key!r}")
    return value


def _unknown_keys(where: _Where, value: Mapping[str, Any], allowed: set[str]) -> None:
    extra = sorted(set(value) - allowed)
    if extra:
        raise (where / extra[0]).error(f"unknown key; allowed: {', '.join(sorted(allowed))}")


def _string(where: _Where, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise where.error("must be a non-empty string")
    return value


def _number(where: _Where, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise where.error(f"must be a finite number, got {value!r}")
    return value


def load_tuning_spec(
    path: str | Path,
    *,
    skill_name: str | None = None,
) -> TuningSpec:
    """Read and validate one ``tuning.yaml``.

    :param path: The file.
    :param skill_name: The ``name`` of the ``SKILL.md`` beside it; when given,
        the file's ``skill`` must equal it.
    :returns: The validated spec.
    :raises SpecError: The file cannot be read or breaks a rule; the message
        names the file and the field path.
    """
    import yaml

    file = Path(path)
    where = _Where(file)
    try:
        raw_bytes = file.read_bytes()
    except OSError as exc:
        raise where.error(f"cannot be read: {exc}") from exc
    try:
        document = yaml.safe_load(raw_bytes.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise where.error(f"is not valid YAML: {exc}") from exc

    top = _mapping(where, document)
    _unknown_keys(where, top, _TOP_KEYS)

    if top.get("schema_version") != 1:
        raise (where / "schema_version").error(
            f"must be 1, got {top.get('schema_version')!r}"
        )
    skill = _string(where / "skill", top.get("skill"))
    if skill_name is not None and skill != skill_name:
        raise (where / "skill").error(
            f"is {skill!r} but the SKILL.md beside it is named {skill_name!r}"
        )
    script = _string(where / "script", top.get("script"))
    script_path = (file.parent / script).resolve()
    if file.parent.resolve() not in script_path.parents:
        raise (where / "script").error("must name a file inside the skill directory")
    if not script_path.is_file():
        raise (where / "script").error(f"{script} does not exist")
    analysis = _string(where / "analysis", top.get("analysis"))
    if analysis not in PANELS:
        raise (where / "analysis").error(
            f"{analysis!r} is not a registered panel; registered: {', '.join(sorted(PANELS))}"
        )
    method_flag = top.get("method_flag")
    if method_flag is not None:
        method_flag = _string(where / "method_flag", method_flag)
        if not method_flag.startswith("--"):
            raise (where / "method_flag").error("must start with '--'")

    output = _load_output(where / "output", top.get("output"))
    reference = _mapping(where / "reference", top.get("reference"), required=False)
    for key, value in reference.items():
        _string(where / "reference" / key, value)

    defaults = _mapping(where / "defaults", top.get("defaults"), required=False)
    _unknown_keys(where / "defaults", defaults, {"resources"})
    default_resources = _mapping(
        where / "defaults" / "resources", defaults.get("resources"), required=False
    )

    reserved = set(RESERVED_FLAGS)
    if method_flag is not None:
        reserved.add(method_flag)

    context_raw = _mapping(where / "context", top.get("context"), required=False)
    context: dict[str, ParamSpec] = {}
    for name, raw in context_raw.items():
        context[name] = _load_param(
            where / "context" / name, name, raw, reserved=reserved, is_context=True
        )
    for name, param in context.items():
        if param.active_when:
            raise (where / "context" / name / "active_when").error(
                "context parameters are always active"
            )

    methods_raw = _mapping(where / "methods", top.get("methods"))
    if not methods_raw:
        raise (where / "methods").error("must name at least one method")
    if method_flag is None and len(methods_raw) != 1:
        raise (where / "methods").error("a skill without method_flag has exactly one method")
    methods: dict[str, MethodSpec] = {}
    for name, raw in methods_raw.items():
        methods[name] = _load_method(
            where / "methods" / name,
            name,
            raw,
            default_resources=default_resources,
            context=context,
            reserved=reserved,
        )

    note = top.get("note") or ""
    if note:
        _string(where / "note", note)

    spec = TuningSpec(
        path=file,
        skill=skill,
        script=script,
        analysis=analysis,
        method_flag=method_flag,
        output=output,
        reference=dict(reference),
        context=context,
        methods=methods,
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        note=note,
    )
    for name, method_spec in methods.items():
        try:
            validate_params(spec, name, {})
        except SpecError as exc:
            raise (where / "methods" / name).error(f"the defaults are not valid: {exc}") from exc
        control = method_spec.k_control
        if control is not None and control.pin:
            try:
                validate_params(spec, name, control.pin)
            except SpecError as exc:
                first = str(exc).split("\n", 1)[0]
                raise (where / "methods" / name / "k_control" / "pin").error(
                    f"the pinned values are not valid: {first}"
                ) from None
    return spec


def _load_output(where: _Where, value: Any) -> OutputSpec:
    raw = _mapping(where, value)
    _unknown_keys(where, raw, {"kind", "labels", "embedding", "h5ad"})
    kind = raw.get("kind")
    if kind not in OUTPUT_KINDS:
        raise (where / "kind").error(f"must be one of {', '.join(OUTPUT_KINDS)}, got {kind!r}")
    h5ad = raw.get("h5ad")
    if h5ad is not None:
        _string(where / "h5ad", h5ad)
    labels = raw.get("labels")
    table = id_column = label_column = None
    if labels is not None or kind == "labels":
        block = _mapping(where / "labels", labels)
        _unknown_keys(where / "labels", block, {"table", "id_column", "label_column"})
        table = _string(where / "labels" / "table", block.get("table"))
        label_column = _string(where / "labels" / "label_column", block.get("label_column"))
        if block.get("id_column") is not None:
            id_column = _string(where / "labels" / "id_column", block.get("id_column"))
    embedding: Mapping[str, Any] = {}
    if kind == "embedding":
        embedding = dict(_mapping(where / "embedding", raw.get("embedding")))
    return OutputSpec(
        kind=kind,
        labels_table=table,
        id_column=id_column,
        label_column=label_column,
        h5ad=h5ad,
        embedding=embedding,
    )


def _load_resources(where: _Where, merged: Mapping[str, Any]) -> ResourceSpec:
    _unknown_keys(where, merged, _RESOURCE_KEYS)
    missing = sorted(_RESOURCE_KEYS - set(merged))
    if missing:
        raise (where / missing[0]).error("is required (in defaults.resources or the method)")
    gpu = merged["gpu"]
    if gpu not in GPU_MODES:
        raise (where / "gpu").error(f"must be one of {', '.join(GPU_MODES)}, got {gpu!r}")
    memory = _number(where / "memory_gb", merged["memory_gb"])
    if memory <= 0:
        raise (where / "memory_gb").error("must be > 0")
    cpus = merged["cpus"]
    if isinstance(cpus, bool) or not isinstance(cpus, int) or cpus < 1:
        raise (where / "cpus").error(f"must be an integer >= 1, got {cpus!r}")
    timeout = _number(where / "timeout_s", merged["timeout_s"])
    if timeout <= 0:
        raise (where / "timeout_s").error("must be > 0")
    return ResourceSpec(gpu=gpu, memory_gb=float(memory), cpus=cpus, timeout_s=float(timeout))


def _load_method(
    where: _Where,
    name: str,
    value: Any,
    *,
    default_resources: Mapping[str, Any],
    context: Mapping[str, ParamSpec],
    reserved: set[str],
) -> MethodSpec:
    raw = _mapping(where, value if value is not None else {})
    _unknown_keys(where, raw, _METHOD_KEYS)
    params_raw = _mapping(where / "params", raw.get("params"), required=False)
    params: dict[str, ParamSpec] = {}
    for param_name, param_raw in params_raw.items():
        if param_name in context:
            raise (where / "params" / param_name).error("is already a context parameter")
        params[param_name] = _load_param(
            where / "params" / param_name, param_name, param_raw, reserved=reserved,
            is_context=False,
        )
    flags: dict[str, str] = {}
    for param in (*context.values(), *params.values()):
        if param.flag in flags:
            raise (where / "params" / param.name / "flag").error(
                f"{param.flag} is also the flag of {flags[param.flag]}"
            )
        flags[param.flag] = param.name
    for param in params.values():
        for predicate in param.active_when:
            target = params.get(predicate.param)
            if target is None:
                raise (where / "params" / param.name / "active_when" / predicate.param).error(
                    "names no parameter of this method"
                )
            if predicate.op in ("gt", "ge", "lt", "le") and target.type not in ("float", "int"):
                raise (where / "params" / param.name / "active_when" / predicate.param).error(
                    f"{predicate.op} needs a numeric parameter"
                )
    _check_acyclic(where, params)

    constraints: list[Constraint] = []
    raw_constraints = raw.get("constraints") or []
    if not isinstance(raw_constraints, list):
        raise (where / "constraints").error("must be a list")
    for index, item in enumerate(raw_constraints):
        constraint = _load_constraint(where / "constraints" / str(index), item, params)
        left = params[constraint.lhs].default if constraint.lhs_is_param else constraint.lhs
        right = params[constraint.rhs].default if constraint.rhs_is_param else constraint.rhs
        if not _compare(constraint.op, left, right):
            raise (where / "constraints" / str(index)).error(
                f"the defaults are not valid: {constraint.describe()} is false for "
                f"{_literal(left)} and {_literal(right)}"
            )
        constraints.append(constraint)

    merged = dict(default_resources)
    merged.update(_mapping(where / "resources", raw.get("resources"), required=False))
    resources = _load_resources(where / "resources", merged)
    note = raw.get("note") or ""
    if note:
        _string(where / "note", note)
    k_control = None
    if raw.get("k_control") is not None:
        k_control = _load_k_control(where / "k_control", raw["k_control"], params)
    return MethodSpec(
        name=name,
        params=params,
        constraints=tuple(constraints),
        resources=resources,
        note=note,
        k_control=k_control,
    )


def _load_k_control(where: _Where, value: Any, params: Mapping[str, ParamSpec]) -> KControl:
    raw = _mapping(where, value)
    _unknown_keys(where, raw, _K_CONTROL_KEYS)
    kind = raw.get("kind")
    if kind not in K_CONTROL_KINDS:
        raise (where / "kind").error(f"must be one of {', '.join(K_CONTROL_KINDS)}, got {kind!r}")
    name = _string(where / "param", raw.get("param"))
    param = params.get(name)
    if param is None:
        raise (where / "param").error(f"{name!r} names no parameter of this method")
    if kind == "exact" and param.type != "int":
        raise (where / "param").error(f"an exact k_control needs an int parameter, {name} is {param.type}")
    if kind == "calibrate" and param.type not in ("float", "int"):
        raise (where / "param").error(f"a calibrate k_control needs a numeric parameter, {name} is {param.type}")
    pin_raw = _mapping(where / "pin", raw.get("pin"), required=False)
    pin: dict[str, Any] = {}
    for key, pinned in pin_raw.items():
        target = params.get(key)
        if target is None:
            raise (where / "pin" / key).error("names no parameter of this method")
        if key == name:
            raise (where / "pin" / key).error("the controlled parameter cannot be pinned")
        try:
            pin[key] = _coerce(target, pinned)
        except SpecError as exc:
            raise (where / "pin" / key).error(str(exc)) from None
    return KControl(kind=kind, param=name, pin=pin)


def _check_acyclic(where: _Where, params: Mapping[str, ParamSpec]) -> None:
    state: dict[str, int] = {}

    def visit(name: str, trail: tuple[str, ...]) -> None:
        if state.get(name) == 2:
            return
        if state.get(name) == 1:
            cycle = " -> ".join((*trail, name))
            raise (where / "params" / name / "active_when").error(f"forms a cycle: {cycle}")
        state[name] = 1
        for predicate in params[name].active_when:
            visit(predicate.param, (*trail, name))
        state[name] = 2

    for name in params:
        visit(name, ())


def _load_constraint(where: _Where, value: Any, params: Mapping[str, ParamSpec]) -> Constraint:
    raw = _mapping(where, value)
    _unknown_keys(where, raw, {"lhs", "op", "rhs"})
    op = raw.get("op")
    if op not in CONSTRAINT_OPS:
        raise (where / "op").error(f"must be one of {', '.join(CONSTRAINT_OPS)}, got {op!r}")
    sides = []
    for side in ("lhs", "rhs"):
        item = raw.get(side)
        if isinstance(item, str):
            if item not in params:
                raise (where / side).error(f"{item!r} names no parameter of this method")
            sides.append((item, True))
        else:
            _number(where / side, item)
            sides.append((item, False))
    if not sides[0][1] and not sides[1][1]:
        raise where.error("at least one side must name a parameter")
    return Constraint(
        lhs=sides[0][0],
        op=op,
        rhs=sides[1][0],
        lhs_is_param=sides[0][1],
        rhs_is_param=sides[1][1],
    )


def _load_param(
    where: _Where,
    name: str,
    value: Any,
    *,
    reserved: set[str],
    is_context: bool,
) -> ParamSpec:
    if not _NAME.match(name):
        raise where.error("parameter names are snake_case")
    raw = _mapping(where, value)
    _unknown_keys(where, raw, _PARAM_KEYS)
    kind = raw.get("type")
    if kind not in PARAM_TYPES:
        raise (where / "type").error(f"must be one of {', '.join(PARAM_TYPES)}, got {kind!r}")
    flag = _string(where / "flag", raw.get("flag"))
    if not flag.startswith("--"):
        raise (where / "flag").error("must start with '--'")
    if flag in reserved:
        raise (where / "flag").error(f"{flag} is reserved and cannot be a parameter")

    low = high = None
    choices: tuple[Any, ...] = ()
    if kind in ("float", "int"):
        for bound in ("low", "high"):
            if bound not in raw:
                raise (where / bound).error(f"is required for {kind} parameters")
        low = _number(where / "low", raw["low"])
        high = _number(where / "high", raw["high"])
        if kind == "int" and (not isinstance(low, int) or not isinstance(high, int)):
            raise where.error("int bounds must be integers")
        if not low < high:
            raise (where / "low").error(f"must be below high ({low!r} >= {high!r})")
    elif "low" in raw or "high" in raw:
        raise where.error(f"low/high only apply to numeric parameters, not {kind}")
    if kind == "categorical":
        raw_choices = raw.get("choices")
        if not isinstance(raw_choices, list) or not raw_choices:
            raise (where / "choices").error("is required for categorical parameters and must be a non-empty list")
        types = {type(choice) for choice in raw_choices}
        if len(types) != 1 or bool in types or not types <= {str, int, float}:
            raise (where / "choices").error("elements must all be strings, or all integers, or all floats")
        if len(set(raw_choices)) != len(raw_choices):
            raise (where / "choices").error("elements must be distinct")
        choices = tuple(raw_choices)
    elif "choices" in raw:
        raise (where / "choices").error(f"only applies to categorical parameters, not {kind}")

    log = raw.get("log", False)
    if not isinstance(log, bool):
        raise (where / "log").error("must be true or false")
    if log and (kind not in ("float", "int") or low is None or low <= 0):
        raise (where / "log").error("needs a numeric parameter with low > 0")

    switch = raw.get("switch", False)
    if not isinstance(switch, bool):
        raise (where / "switch").error("must be true or false")
    if switch and kind != "bool":
        raise (where / "switch").error("only applies to bool parameters")

    priority = raw.get("priority")
    if priority is not None and (isinstance(priority, bool) or not isinstance(priority, int) or priority < 1):
        raise (where / "priority").error(f"must be a positive integer, got {priority!r}")

    note = raw.get("note") or ""
    if note:
        _string(where / "note", note)

    predicates: list[Predicate] = []
    active_when = _mapping(where / "active_when", raw.get("active_when"), required=False)
    for target, condition in active_when.items():
        cond = _mapping(where / "active_when" / target, condition)
        if not cond:
            raise (where / "active_when" / target).error("needs at least one operator")
        for op, operand in cond.items():
            if op not in PREDICATE_OPS:
                raise (where / "active_when" / target / op).error(
                    f"unknown operator; allowed: {', '.join(PREDICATE_OPS)}"
                )
            if op == "in" and not isinstance(operand, list):
                raise (where / "active_when" / target / op).error("the value of 'in' is a list")
            predicates.append(
                Predicate(param=target, op=op, value=tuple(operand) if op == "in" else operand)
            )
        if target == name:
            raise (where / "active_when" / target).error(f"forms a cycle: {name} -> {name}")

    spec = ParamSpec(
        name=name,
        type=kind,
        flag=flag,
        default=None,
        low=low,
        high=high,
        choices=choices,
        log=log,
        priority=priority,
        active_when=tuple(predicates),
        note=note,
        switch=switch,
    )
    if "default" not in raw:
        raise (where / "default").error("is required")
    default = raw["default"]
    if default is None:
        if not is_context:
            raise (where / "default").error("null is allowed only for context parameters")
    else:
        try:
            default = _coerce(spec, default)
        except SpecError as exc:
            raise (where / "default").error(str(exc)) from None
    object.__setattr__(spec, "default", default)
    return spec


# ---- validating and rendering ------------------------------------------------


def _coerce(param: ParamSpec, value: Any) -> Any:
    """*value* as *param*'s type, or :exc:`SpecError` saying why not."""
    if param.type == "bool":
        if not isinstance(value, bool):
            raise SpecError(f"{param.name} must be true or false, got {value!r}")
        return value
    if param.type == "categorical":
        for choice in param.choices:
            if type(choice) is type(value) and choice == value:
                return choice
        options = ", ".join(_literal(choice) for choice in param.choices)
        raise SpecError(f"{param.name} must be one of [{options}], got {_literal(value)}")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpecError(f"{param.name} must be a number, got {_literal(value)}")
    if not math.isfinite(value):
        raise SpecError(f"{param.name} must be finite, got {value!r}")
    if param.type == "int":
        if isinstance(value, float):
            if not value.is_integer():
                raise SpecError(f"{param.name} must be an integer, got {value!r}")
            value = int(value)
    else:
        value = float(value)
    assert param.low is not None and param.high is not None
    if not param.low <= value <= param.high:
        raise SpecError(
            f"{param.name}={_literal(value)} is outside [{_literal(param.low)}, {_literal(param.high)}]"
        )
    return value


def _active(param: ParamSpec, values: Mapping[str, Any]) -> bool:
    for predicate in param.active_when:
        if predicate.param not in values:
            return False
        if not predicate.holds(values[predicate.param]):
            return False
    return True


def _resolution_order(params: Mapping[str, ParamSpec]) -> list[str]:
    order: list[str] = []
    seen: set[str] = set()

    def visit(name: str) -> None:
        if name in seen:
            return
        seen.add(name)
        for predicate in params[name].active_when:
            visit(predicate.param)
        order.append(name)

    for name in params:
        visit(name)
    return order


def validate_params(
    spec: TuningSpec,
    method: str,
    params: Mapping[str, Any],
) -> dict[str, Any]:
    """Check *params* against one method and fill in every active default.

    Context parameters are accepted for any method. A parameter whose
    ``active_when`` does not hold must not be given; one that holds and is
    not given takes its default. Context parameters whose default is null and
    that are not given are left out.

    :returns: The active parameters in rendering order: context first, then the
        method's own in declaration order.
    :raises SpecError: An unknown name, a parameter of another method, a wrong
        type, a value out of range, an inactive parameter that was given, or a
        violated constraint. The message ends with the method's search space.
    """
    method_spec = spec.method(method)
    try:
        return _validated(spec, method_spec, params)
    except SpecError as exc:
        raise SpecError(
            f"{exc}\n\nSearch space of {spec.skill}:\n{method_spec.summary()}"
            + _context_summary(spec)
        ) from None


def _context_summary(spec: TuningSpec) -> str:
    if not spec.context:
        return ""
    lines = ["\ncontext (any method):"]
    lines += [f"  {param.describe()}" for param in spec.context.values()]
    return "\n".join(lines)


def _validated(
    spec: TuningSpec,
    method_spec: MethodSpec,
    params: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(params, Mapping):
        raise SpecError("params must be an object of parameter names to values")
    given: dict[str, Any] = {}
    for name, value in params.items():
        param = method_spec.params.get(name) or spec.context.get(name)
        if param is None:
            owners = [m for m, other in spec.methods.items() if name in other.params]
            if owners:
                raise SpecError(
                    f"{name} is a parameter of {', '.join(owners)}, not of {method_spec.name}"
                )
            if name.startswith("-") or name.replace("-", "_") != name:
                raise SpecError(f"{name!r} is not a parameter name; use the snake_case name, not the flag")
            raise SpecError(f"{name} is not a parameter of {method_spec.name}")
        if value is None and name in spec.context:
            continue
        given[name] = _coerce(param, value)

    values: dict[str, Any] = {}
    for name, param in spec.context.items():
        value = given.get(name, param.default)
        if value is not None:
            values[name] = value
    own: dict[str, Any] = {}
    for name in _resolution_order(method_spec.params):
        param = method_spec.params[name]
        if not _active(param, own):
            if name in given:
                reason = " and ".join(p.describe() for p in param.active_when)
                raise SpecError(f"{name} applies only when {reason}")
            continue
        own[name] = given.get(name, param.default)

    for constraint in method_spec.constraints:
        left = own.get(constraint.lhs) if constraint.lhs_is_param else constraint.lhs
        right = own.get(constraint.rhs) if constraint.rhs_is_param else constraint.rhs
        if (constraint.lhs_is_param and constraint.lhs not in own) or (
            constraint.rhs_is_param and constraint.rhs not in own
        ):
            continue
        if not _compare(constraint.op, left, right):
            raise SpecError(
                f"constraint {constraint.describe()} is violated "
                f"({_literal(left)} {_OP_SYMBOLS[constraint.op]} {_literal(right)} is false)"
            )

    for name in method_spec.params:
        if name in own:
            values[name] = own[name]
    return values


def render_cli_args(spec: TuningSpec, method: str, params: Mapping[str, Any]) -> list[str]:
    """The script flags for *method* with *params*, which must already be validated.

    The method flag comes first when the skill has one; every parameter in
    *params* is rendered, defaults included. A bool renders as ``--flag
    true|false``, or as a bare ``--flag`` (only when true) for a ``switch``.
    """
    method_spec = spec.method(method)
    args: list[str] = []
    if spec.method_flag is not None:
        args += [spec.method_flag, method]
    for name, value in params.items():
        param = method_spec.params.get(name) or spec.context.get(name)
        if param is None:
            raise SpecError(f"{name} is not a parameter of {method}")
        if param.type == "bool":
            if param.switch:
                if value:
                    args.append(param.flag)
                continue
            args += [param.flag, "true" if value else "false"]
            continue
        args += [param.flag, _render_value(value)]
    return args


def _render_value(value: Any) -> str:
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return repr(value)
    if isinstance(value, (tuple, list)):
        return "[" + ", ".join(_literal(item) for item in value) + "]"
    if isinstance(value, str):
        return value
    return repr(value)


def _type_name(value: Any) -> str:
    return "null" if value is None else type(value).__name__


# ---- the catalogue -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SkippedTuning:
    """A ``tuning.yaml`` that was found and could not be used."""

    path: Path
    reason: str


class TuningCatalog:
    """Every valid ``tuning.yaml`` beside an indexed skill.

    Built once from a skill index; a file that fails validation is recorded in
    :attr:`skipped` and its skill is not runnable.
    """

    def __init__(self, specs: Sequence[TuningSpec], skipped: Sequence[SkippedTuning] = ()) -> None:
        self._specs = {spec.skill: spec for spec in specs}
        self.skipped: tuple[SkippedTuning, ...] = tuple(skipped)

    @classmethod
    def from_skills(cls, skills: Any) -> "TuningCatalog":
        """Load the ``tuning.yaml`` of every skill in *skills* (a ``SkillIndex``)."""
        specs: list[TuningSpec] = []
        skipped: list[SkippedTuning] = []
        for name in skills.names():
            skill = skills.get(name)
            if skill is None:
                continue
            path = Path(skill.directory) / TUNING_FILENAME
            if not path.is_file():
                continue
            try:
                specs.append(load_tuning_spec(path, skill_name=skill.name))
            except SpecError as exc:
                skipped.append(SkippedTuning(path=path, reason=str(exc)))
        return cls(specs, skipped)

    def __len__(self) -> int:
        return len(self._specs)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))

    def get(self, skill: str) -> TuningSpec | None:
        return self._specs.get(skill)

    def specs(self) -> tuple[TuningSpec, ...]:
        return tuple(self._specs[name] for name in self.names())
