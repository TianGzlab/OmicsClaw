"""``tuning.yaml``: loading, validation, parameter checking and rendering.

Every loader rule has one counter-example whose error must name the field
path, because the person reading it is editing a YAML file and needs to know
which line. Parameter checking is strict on purpose: an out-of-range value is
refused rather than clamped, so a tuning loop can never silently run a trial
other than the one it asked for, and every active default is rendered so the
script's own silent defaults (``n_domains=7``, ``auto_k_max=None``) never
decide a trial behind the spec's back.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from omicsclaw.ensemble.space import (
    SpecError,
    TuningCatalog,
    load_tuning_spec,
    render_cli_args,
    validate_params,
)
from omicsclaw.skills import load_skills


def _base() -> dict:
    return {
        "schema_version": 1,
        "skill": "demo",
        "script": "demo.py",
        "analysis": "spatial_domains",
        "method_flag": "--method",
        "output": {
            "kind": "labels",
            "labels": {"table": "tables/a.csv", "id_column": "observation", "label_column": "label"},
            "h5ad": "processed.h5ad",
        },
        "reference": {"coords_obsm": "spatial"},
        "defaults": {"resources": {"gpu": "none", "memory_gb": 4, "cpus": 2, "timeout_s": 60}},
        "context": {
            "data_type": {
                "type": "categorical",
                "flag": "--data-type",
                "choices": ["visium", "slide_seq"],
                "default": None,
            }
        },
        "methods": {
            "alpha": {
                "params": {
                    "resolution": {
                        "type": "float", "flag": "--resolution", "low": 0.1, "high": 2.0,
                        "log": True, "default": 1.0, "priority": 1,
                    },
                    "n": {"type": "int", "flag": "--n", "low": 3, "high": 20, "default": 7},
                    "mode": {"type": "categorical", "flag": "--mode", "choices": [32, 64], "default": 64},
                    "auto": {"type": "bool", "flag": "--auto", "default": False},
                    "kmin": {
                        "type": "int", "flag": "--kmin", "low": 2, "high": 10, "default": 2,
                        "active_when": {"auto": {"eq": True}},
                    },
                    "kmax": {
                        "type": "int", "flag": "--kmax", "low": 4, "high": 20, "default": 10,
                        "active_when": {"auto": {"eq": True}},
                    },
                },
                "constraints": [{"lhs": "kmin", "op": "lt", "rhs": "kmax"}],
            },
            "beta": {
                "resources": {"gpu": "preferred", "memory_gb": 8},
                "params": {
                    "weight": {"type": "float", "flag": "--weight", "low": 0.0, "high": 1.0, "default": 0.0},
                    "pre": {
                        "type": "float", "flag": "--pre", "low": 0.05, "high": 1.0, "default": 0.2,
                        "active_when": {"weight": {"gt": 0}},
                    },
                },
            },
        },
    }


def _write(tmp_path: Path, document: dict) -> Path:
    (tmp_path / "demo.py").write_text("print('hi')\n")
    path = tmp_path / "tuning.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False))
    return path


def _load(tmp_path: Path, document: dict | None = None):
    return load_tuning_spec(_write(tmp_path, document or _base()))


def _refused(tmp_path: Path, mutate, *fragments: str) -> str:
    document = _base()
    mutate(document)
    with pytest.raises(SpecError) as raised:
        _load(tmp_path, document)
    message = str(raised.value)
    assert "tuning.yaml" in message
    for fragment in fragments:
        assert fragment in message, message
    return message


# ---- loading -----------------------------------------------------------------


def test_a_valid_file_loads_with_merged_resources(tmp_path):
    spec = _load(tmp_path)
    assert spec.skill == "demo" and spec.analysis == "spatial_domains"
    assert set(spec.methods) == {"alpha", "beta"}
    beta = spec.methods["beta"].resources
    assert (beta.gpu, beta.memory_gb, beta.cpus, beta.timeout_s) == ("preferred", 8.0, 2, 60.0)
    assert spec.output.id_column == "observation"
    assert spec.script_path == tmp_path / "demo.py"
    assert len(spec.sha256) == 64


@pytest.mark.parametrize(
    "mutate, fragments",
    [
        (lambda d: d.update(schema_version=2), ("schema_version",)),
        (lambda d: d.update(skill=""), ("skill",)),
        (lambda d: d.update(script="missing.py"), ("script", "does not exist")),
        (lambda d: d.update(script="../escape.py"), ("script", "inside the skill directory")),
        (lambda d: d.update(analysis="nope"), ("analysis", "registered")),
        (lambda d: d.update(method_flag="method"), ("method_flag",)),
        (lambda d: d.update(extra=1), ("extra", "unknown key")),
        (lambda d: d["output"].update(kind="table"), ("output.kind",)),
        (lambda d: d["output"]["labels"].pop("label_column"), ("output.labels.label_column",)),
        (lambda d: d["defaults"]["resources"].update(gpu="maybe"), ("methods.alpha.resources.gpu",)),
        (lambda d: d["defaults"]["resources"].update(memory_gb=0), ("resources.memory_gb",)),
        (lambda d: d["defaults"]["resources"].update(cpus=0), ("resources.cpus",)),
        (lambda d: d["defaults"]["resources"].update(timeout_s=-1), ("resources.timeout_s",)),
        (lambda d: d["defaults"]["resources"].pop("cpus"), ("resources.cpus", "required")),
        (lambda d: d["methods"]["alpha"]["params"]["n"].update(type="str"), ("params.n.type",)),
        (lambda d: d["methods"]["alpha"]["params"]["n"].update(flag="n"), ("params.n.flag",)),
        (lambda d: d["methods"]["alpha"]["params"]["n"].update(flag="--output"), ("params.n.flag", "reserved")),
        (lambda d: d["methods"]["alpha"]["params"]["n"].update(flag="--method"), ("params.n.flag", "reserved")),
        (lambda d: d["methods"]["alpha"]["params"]["n"].update(flag="--mode"), ("flag", "also the flag")),
        (lambda d: d["methods"]["alpha"]["params"]["n"].pop("low"), ("params.n.low", "required")),
        (lambda d: d["methods"]["alpha"]["params"]["n"].update(low=30), ("params.n.low", "below high")),
        (lambda d: d["methods"]["alpha"]["params"]["n"].update(low=3.5), ("params.n", "integers")),
        (lambda d: d["methods"]["alpha"]["params"]["mode"].update(choices=[]), ("params.mode.choices",)),
        (lambda d: d["methods"]["alpha"]["params"]["mode"].update(choices=[32, "64"]), ("params.mode.choices",)),
        (lambda d: d["methods"]["alpha"]["params"]["n"].update(default=99), ("params.n.default", "outside")),
        (lambda d: d["methods"]["alpha"]["params"]["mode"].update(default=48), ("params.mode.default",)),
        (lambda d: d["methods"]["alpha"]["params"]["n"].update(default=None), ("params.n.default", "null")),
        (lambda d: d["methods"]["alpha"]["params"]["n"].pop("default"), ("params.n.default", "required")),
        (lambda d: d["methods"]["beta"]["params"]["weight"].update(log=True), ("params.weight.log",)),
        (lambda d: d["methods"]["alpha"]["params"]["mode"].update(log=True), ("params.mode.log",)),
        (lambda d: d["methods"]["alpha"]["params"]["n"].update(priority=0), ("params.n.priority",)),
        (lambda d: d["methods"]["alpha"]["params"]["kmin"].update(active_when={"auto": {"is": True}}),
         ("active_when.auto.is", "unknown operator")),
        (lambda d: d["methods"]["alpha"]["params"]["kmin"].update(active_when={"auto": {"in": True}}),
         ("active_when.auto.in", "list")),
        (lambda d: d["methods"]["alpha"]["params"]["kmin"].update(active_when={"ghost": {"eq": 1}}),
         ("active_when.ghost", "names no parameter")),
        (lambda d: d["methods"]["alpha"]["params"]["kmin"].update(active_when={"kmin": {"eq": 1}}),
         ("cycle",)),
        (lambda d: (d["methods"]["alpha"]["params"]["n"].update(active_when={"kmin": {"gt": 2}}),
                    d["methods"]["alpha"]["params"]["kmin"].update(active_when={"n": {"gt": 2}})),
         ("cycle",)),
        (lambda d: d["methods"]["alpha"].update(constraints=[{"lhs": "kmin", "op": "eq", "rhs": "kmax"}]),
         ("constraints.0.op",)),
        (lambda d: d["methods"]["alpha"].update(constraints=[{"lhs": "ghost", "op": "lt", "rhs": "kmax"}]),
         ("constraints.0.lhs",)),
        (lambda d: d["methods"]["alpha"]["params"]["kmin"].update(default=15, high=20),
         ("methods.alpha.constraints.0", "defaults are not valid", "kmin < kmax")),
        (lambda d: d["methods"]["alpha"]["params"].update({"Bad-Name": {"type": "bool", "flag": "--b", "default": True}}),
         ("snake_case",)),
        (lambda d: d.update(methods={}), ("methods", "at least one")),
        (lambda d: d.update(method_flag=None), ("methods", "exactly one")),
    ],
)
def test_each_rule_has_a_counter_example_naming_its_field(tmp_path, mutate, fragments):
    _refused(tmp_path, mutate, *fragments)


def test_the_skill_must_match_the_skill_md_name(tmp_path):
    path = _write(tmp_path, _base())
    with pytest.raises(SpecError, match="SKILL.md beside it is named 'other'"):
        load_tuning_spec(path, skill_name="other")


def test_an_unreadable_yaml_names_the_file(tmp_path):
    path = tmp_path / "tuning.yaml"
    path.write_text("a: [unclosed\n")
    with pytest.raises(SpecError, match="not valid YAML"):
        load_tuning_spec(path)


def test_the_id_column_is_optional(tmp_path):
    document = _base()
    document["output"]["labels"].pop("id_column")
    assert _load(tmp_path, document).output.id_column is None


# ---- predicates ----------------------------------------------------------------


@pytest.mark.parametrize(
    "op, operand, weight, active",
    [
        ("eq", 0.5, 0.5, True),
        ("eq", 0.5, 0.6, False),
        ("ne", 0.5, 0.6, True),
        ("ne", 0.5, 0.5, False),
        ("gt", 0.5, 0.5, False),
        ("gt", 0.5, 0.6, True),
        ("ge", 0.5, 0.5, True),
        ("ge", 0.5, 0.4, False),
        ("lt", 0.5, 0.5, False),
        ("lt", 0.5, 0.4, True),
        ("le", 0.5, 0.5, True),
        ("le", 0.5, 0.6, False),
        ("in", [0.2, 0.5], 0.5, True),
        ("in", [0.2, 0.5], 0.6, False),
    ],
)
def test_every_predicate_operator(tmp_path, op, operand, weight, active):
    document = _base()
    beta = document["methods"]["beta"]["params"]
    beta["weight"]["default"] = 0.5
    beta["pre"]["active_when"] = {"weight": {op: operand}}
    spec = _load(tmp_path, document)
    values = validate_params(spec, "beta", {"weight": weight})
    assert ("pre" in values) is active


def test_a_parameter_whose_condition_fails_is_refused_when_given(tmp_path):
    spec = _load(tmp_path)
    with pytest.raises(SpecError, match="pre applies only when weight > 0"):
        validate_params(spec, "beta", {"pre": 0.5})


def test_an_inactive_parameter_is_not_rendered(tmp_path):
    spec = _load(tmp_path)
    args = render_cli_args(spec, "beta", validate_params(spec, "beta", {}))
    assert "--pre" not in args
    args = render_cli_args(spec, "beta", validate_params(spec, "beta", {"weight": 0.5}))
    assert args[args.index("--pre") + 1] == "0.2"


def test_gt_is_strict_at_the_boundary(tmp_path):
    spec = _load(tmp_path)
    assert "pre" not in validate_params(spec, "beta", {"weight": 0.0})


# ---- constraints, defaults, refusals --------------------------------------------


def test_a_violated_constraint_is_refused(tmp_path):
    spec = _load(tmp_path)
    with pytest.raises(SpecError, match=r"kmin < kmax is violated"):
        validate_params(spec, "alpha", {"auto": True, "kmin": 8, "kmax": 8})


def test_a_constraint_between_inactive_parameters_is_not_checked(tmp_path):
    spec = _load(tmp_path)
    assert "kmin" not in validate_params(spec, "alpha", {"auto": False})


def test_every_active_default_is_filled_in(tmp_path):
    spec = _load(tmp_path)
    assert validate_params(spec, "alpha", {}) == {
        "resolution": 1.0, "n": 7, "mode": 64, "auto": False,
    }
    assert validate_params(spec, "alpha", {"auto": True, "data_type": "visium"}) == {
        "data_type": "visium", "resolution": 1.0, "n": 7, "mode": 64, "auto": True,
        "kmin": 2, "kmax": 10,
    }


@pytest.mark.parametrize(
    "params, fragment",
    [
        ({"resolution": 5.0}, "outside [0.1, 2.0]"),
        ({"resolution": 0.05}, "outside"),
        ({"n": 2}, "outside [3, 20]"),
        ({"n": 7.5}, "must be an integer"),
        ({"n": "7"}, "must be a number"),
        ({"n": True}, "must be a number"),
        ({"auto": "yes"}, "true or false"),
        ({"mode": "64"}, "must be one of [32, 64]"),
        ({"ghost": 1}, "ghost is not a parameter of alpha"),
        ({"weight": 0.5}, "weight is a parameter of beta, not of alpha"),
        ({"--resolution": 1.0}, "snake_case name, not the flag"),
        ({"data_type": "stereo"}, "must be one of [visium, slide_seq]"),
    ],
)
def test_bad_parameters_are_refused_with_the_search_space(tmp_path, params, fragment):
    spec = _load(tmp_path)
    with pytest.raises(SpecError) as raised:
        validate_params(spec, "alpha", params)
    message = str(raised.value)
    assert fragment in message
    assert "Search space of demo" in message and "method alpha" in message


def test_an_unknown_method_lists_the_known_ones(tmp_path):
    spec = _load(tmp_path)
    with pytest.raises(SpecError, match="methods: alpha, beta"):
        validate_params(spec, "gamma", {})


def test_integral_floats_are_accepted_for_integers(tmp_path):
    spec = _load(tmp_path)
    assert validate_params(spec, "alpha", {"n": 9.0})["n"] == 9


# ---- rendering -------------------------------------------------------------------


def test_the_four_types_render(tmp_path):
    spec = _load(tmp_path)
    values = validate_params(
        spec, "alpha", {"resolution": 0.5, "n": 4, "mode": 32, "auto": True, "data_type": "slide_seq"}
    )
    assert render_cli_args(spec, "alpha", values) == [
        "--method", "alpha",
        "--data-type", "slide_seq",
        "--resolution", "0.5",
        "--n", "4",
        "--mode", "32",
        "--auto", "true",
        "--kmin", "2",
        "--kmax", "10",
    ]


def test_a_switch_renders_only_when_true(tmp_path):
    document = _base()
    document["methods"]["alpha"]["params"]["auto"]["switch"] = True
    spec = _load(tmp_path, document)
    off = render_cli_args(spec, "alpha", validate_params(spec, "alpha", {}))
    on = render_cli_args(spec, "alpha", validate_params(spec, "alpha", {"auto": True}))
    assert "--auto" not in off
    assert on[on.index("--auto") + 1] == "--kmin"


def test_the_summary_orders_by_priority(tmp_path):
    summary = _load(tmp_path).methods["alpha"].summary()
    lines = summary.splitlines()
    assert lines[1].strip().startswith("resolution:")
    assert "constraint: kmin < kmax" in summary
    assert "only when auto == true" in summary


# ---- the catalogue -----------------------------------------------------------------


def test_the_catalogue_loads_valid_files_and_records_bad_ones(tmp_path):
    good = tmp_path / "domain" / "demo"
    bad = tmp_path / "domain" / "broken"
    for directory, name in ((good, "demo"), (bad, "broken")):
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: a test skill\n---\nbody\n"
        )
    _write(good, _base())
    broken = copy.deepcopy(_base())
    broken["skill"] = "broken"
    broken["schema_version"] = 3
    _write(bad, broken)
    catalogue = TuningCatalog.from_skills(load_skills(tmp_path))
    assert catalogue.names() == ("demo",)
    assert len(catalogue.skipped) == 1 and "schema_version" in catalogue.skipped[0].reason


def test_the_repository_catalogue_has_spatial_domains():
    root = Path(__file__).resolve().parents[2] / "skills"
    catalogue = TuningCatalog.from_skills(load_skills(root))
    assert "spatial-domains" in catalogue.names()
    assert not catalogue.skipped
    spec = catalogue.get("spatial-domains")
    assert set(spec.methods) == {
        "leiden", "louvain", "spagcn", "stagate", "graphst", "banksy", "cellcharter",
    }


# ---- k_control ---------------------------------------------------------------------------


def _with_k_control(document: dict, method: str, control: dict) -> dict:
    document["methods"][method]["k_control"] = control
    return document


def test_k_control_loads_for_exact_and_calibrate_methods(tmp_path):
    document = _with_k_control(_base(), "alpha", {"kind": "exact", "param": "n", "pin": {"auto": False}})
    spec = _load(tmp_path, document)
    control = spec.methods["alpha"].k_control
    assert (control.kind, control.param, dict(control.pin)) == ("exact", "n", {"auto": False})
    assert spec.methods["beta"].k_control is None


@pytest.mark.parametrize(
    "method, control, fragments",
    [
        ("alpha", {"kind": "guess", "param": "n"}, ("k_control.kind",)),
        ("alpha", {"kind": "exact", "param": "ghost"}, ("k_control.param", "names no parameter")),
        ("alpha", {"kind": "exact", "param": "resolution"}, ("k_control.param", "int parameter")),
        ("alpha", {"kind": "calibrate", "param": "mode"}, ("k_control.param", "numeric")),
        ("alpha", {"kind": "exact", "param": "n", "pin": {"ghost": 1}}, ("k_control.pin.ghost",)),
        ("alpha", {"kind": "exact", "param": "n", "pin": {"n": 5}}, ("k_control.pin.n", "cannot be pinned")),
        ("alpha", {"kind": "exact", "param": "n", "pin": {"auto": "no"}}, ("k_control.pin.auto",)),
        ("alpha", {"kind": "exact", "param": "n", "extra": 1}, ("k_control.extra", "unknown key")),
        ("beta", {"kind": "exact", "param": "pre", "pin": {}}, ("k_control.param",)),
    ],
)
def test_each_k_control_rule_has_a_counter_example(tmp_path, method, control, fragments):
    _refused(tmp_path, lambda d: _with_k_control(d, method, control), *fragments)


def test_pinned_values_are_checked_together_against_the_constraints(tmp_path):
    """Each pinned value can be in range while the pinned set breaks a
    constraint; tuning would then fail every trial it tried to run."""
    _refused(
        tmp_path,
        lambda d: _with_k_control(
            d, "alpha", {"kind": "exact", "param": "n", "pin": {"auto": True, "kmin": 10}}
        ),
        "k_control.pin", "kmin < kmax",
    )


REPO_SKILLS = Path(__file__).resolve().parents[2] / "skills"


def test_every_spatial_domains_method_declares_how_its_k_is_controlled():
    """Both calibrate and exact methods must be able to reach every K of the
    grid 3-16 the tuning pipeline probes; an exact parameter whose range
    stopped short of 16 would silently leave the top of the grid unprobed."""
    spec = TuningCatalog.from_skills(load_skills(REPO_SKILLS)).get("spatial-domains")
    kinds = {name: method.k_control.kind for name, method in spec.methods.items()}
    assert kinds == {
        "leiden": "calibrate", "louvain": "calibrate", "banksy": "calibrate",
        "spagcn": "exact", "stagate": "exact", "graphst": "exact", "cellcharter": "exact",
    }
    for name, method in spec.methods.items():
        control = method.k_control
        param = method.params[control.param]
        if control.kind == "exact":
            assert param.type == "int" and param.low <= 3 and param.high >= 16, name
        else:
            assert param.type in ("float", "int"), name
    assert dict(spec.methods["cellcharter"].k_control.pin) == {"auto_k": False}
    assert spec.methods["leiden"].resources.cpus == 2
    assert spec.methods["louvain"].resources.cpus == 2


def test_summary_can_leave_out_pinned_parameters(tmp_path):
    spec = _load(tmp_path)
    text = spec.methods["alpha"].summary(omit=("n", "auto"))
    lines = [line.strip() for line in text.splitlines()]
    assert not any(line.startswith(("n:", "auto:")) for line in lines)
    assert "resolution:" in text
