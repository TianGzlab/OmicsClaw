"""The one dependency registry, ``skills/_sdk/deps.py`` (plan 0062 §3.4, §3.9, case 22).

It replaced four per-domain ``_lib/dependency_manager.py`` files. Plan 0061
reads ``DEPENDENCIES`` with ``ast.literal_eval`` and never imports it, so the
table must stay a pure literal with the field contract pinned here.

Name resolution is fixed: exact key, then PEP 503-normalised key, then an
exact ``module`` match, then a fallback. The last step exists only for
backends added later; every name skill code passes today resolves through
the first three, and ``FALLBACK_ALLOWED`` freezes that: a new call name that
only the fallback can resolve turns this red until it is registered here or
listed with a reason. At the time of the merge the scan found 32 call names;
``scvi``, ``tangram`` and ``paste`` resolve only through the module step —
without it they would fall back to the wrong PyPI projects.
"""

from __future__ import annotations

import ast
import re
import subprocess

import pytest

from skills._sdk import deps
from skills._sdk import external_env
from skills._sdk import r_script_runner
from tests.sdk._scan import REPO_ROOT, is_test_path, python_files

DEPS_PATH = REPO_ROOT / "skills" / "_sdk" / "deps.py"
REQUIRED_FIELDS = {"module", "kind", "install", "description"}
OPTIONAL_FIELDS = {"also", "alt_env"}
API = {"require", "get", "is_available", "install_hint", "get_dependency"}

FALLBACK_ALLOWED: dict[str, str] = {}
"""Call names allowed to resolve only through the fallback, each with a reason."""


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _literal():
    tree = ast.parse(DEPS_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        target = node.target if isinstance(node, ast.AnnAssign) else (
            node.targets[0] if isinstance(node, ast.Assign) else None)
        if isinstance(target, ast.Name) and target.id == "DEPENDENCIES":
            assert isinstance(node, ast.AnnAssign), "DEPENDENCIES must be an annotated assignment"
            return ast.literal_eval(node.value)
    raise AssertionError("no DEPENDENCIES assignment")


def test_the_registry_is_a_literal_equal_to_the_import():
    assert _literal() == deps.DEPENDENCIES


def test_size_keys_and_uniqueness():
    table = deps.DEPENDENCIES
    assert len(table) == 61
    normalised = [_norm(k) for k in table]
    assert len(set(normalised)) == len(normalised)
    modules = [v["module"] for v in table.values()]
    assert len(set(modules)) == len(modules)
    module_owner = {v["module"]: k for k, v in table.items()}
    key_of_norm = {_norm(k): k for k in table}
    ambiguous = {
        m: (module_owner[m], key_of_norm[_norm(m)])
        for m in module_owner
        if _norm(m) in key_of_norm and key_of_norm[_norm(m)] != module_owner[m]
    }
    assert ambiguous == {}
    assert "SpatialDE" in table and "spatialde" not in table
    assert "mzmine" not in table and "pymzml" in table


def test_every_entry_follows_the_field_contract():
    for key, value in deps.DEPENDENCIES.items():
        assert isinstance(value, dict), key
        assert REQUIRED_FIELDS <= set(value), key
        assert set(value) - REQUIRED_FIELDS <= OPTIONAL_FIELDS, key
        assert value["kind"] in {"pip", "git", "r"}, key
        assert all(isinstance(value[f], str) and value[f] for f in REQUIRED_FIELDS), key
        if "also" in value:
            assert isinstance(value["also"], list) and all(isinstance(x, str) for x in value["also"])
        if value["kind"] == "pip":
            assert value["install"] == "pip install " + " ".join([key, *value.get("also", [])]), key
        assert '-e ".[' not in value["install"], key


def test_the_special_entries_are_exactly_these():
    table = deps.DEPENDENCIES
    assert {k for k, v in table.items() if v["kind"] == "git"} == {"STAGATE-pyG", "pybanksy", "STalign"}
    assert {k for k, v in table.items() if v["kind"] == "r"} == {"xcms", "metaboanalyst"}
    assert {k for k, v in table.items() if "also" in v} == {"singler"}
    assert table["singler"]["also"] == ["singlecellexperiment"]
    assert {k for k, v in table.items() if "alt_env" in v} == {"pybanksy"}
    assert table["pybanksy"]["alt_env"] == "omicsclaw_banksy"


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("scvi", "scvi-tools"),
        ("tangram", "tangram-sc"),
        ("paste", "paste-bio"),
        ("STAGATE_pyG", "STAGATE-pyG"),
        ("spatialde", "SpatialDE"),
        ("scvi-tools", "scvi-tools"),
        ("mzmine", None),
    ],
)
def test_resolution_order(name, key):
    resolved_key, _entry = deps._resolve(name)
    assert resolved_key == key


def _call_names() -> set[str]:
    """String first arguments of dependency-API calls in skill code (the plan's F29 rule)."""
    names: set[str] = set()
    for path in python_files("skills"):
        if is_test_path(path) or path.parts[-2:] == ("_sdk", "deps.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases, direct = {"dm", "sc_dep_manager"}, set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "skills._sdk" and node.level == 0:
                aliases |= {a.asname or a.name for a in node.names if a.name == "deps"}
            elif isinstance(node, ast.ImportFrom) and node.module == "skills._sdk.deps":
                direct |= {a.asname or a.name for a in node.names}
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                continue
            f = node.func
            if isinstance(f, ast.Name) and (f.id in API or f.id in direct):
                names.add(node.args[0].value)
            elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in aliases:
                names.add(node.args[0].value)
    return names


def test_no_call_name_needs_the_fallback():
    names = _call_names()
    assert {"scvi", "tangram", "paste", "STAGATE_pyG", "spatialde"} <= names
    fallback = {n for n in names if deps._resolve(n)[0] is None}
    assert fallback == set(FALLBACK_ALLOWED)


def test_unknown_names_fall_back_to_pip():
    assert deps.install_hint("no-such-pkg").endswith("`pip install no-such-pkg`")
    with pytest.raises(ImportError, match="pip install no-such-pkg"):
        deps.require("no-such-pkg")


def test_require_names_the_install_command_and_the_feature(monkeypatch):
    monkeypatch.setattr(deps, "_try_import", lambda module: None)
    with pytest.raises(ImportError) as info:
        deps.require("scvi", feature="batch integration")
    assert "pip install scvi-tools" in str(info.value)
    assert "batch integration" in str(info.value)


def _fresh_caches():
    for name in ("_check_spec", "_try_import", "_r_package_available"):
        getattr(deps, name).cache_clear()


def test_r_entries_are_probed_through_rscript(monkeypatch):
    missing: list[str] = []
    monkeypatch.setattr(deps, "_check_r_available", lambda: True)
    monkeypatch.setattr(
        r_script_runner.RScriptRunner, "get_missing_packages", lambda self, pkgs: list(missing)
    )
    _fresh_caches()
    assert deps.is_available("xcms") is True
    missing.append("xcms")
    _fresh_caches()
    assert deps.is_available("xcms") is False
    _fresh_caches()


def test_r_entries_without_rscript_are_unavailable_not_errors(monkeypatch):
    def no_r(*args, **kwargs):
        raise FileNotFoundError("Rscript")

    monkeypatch.setattr(deps.subprocess, "run", no_r)
    monkeypatch.setattr(r_script_runner.subprocess, "run", no_r)
    _fresh_caches()
    assert deps.is_available("metaboanalyst") is False
    _fresh_caches()


def test_r_entries_have_no_python_module():
    with pytest.raises(TypeError, match="R package"):
        deps.require("xcms")
    with pytest.raises(TypeError, match="R package"):
        deps.get("xcms")


@pytest.mark.parametrize(
    ("env_answer", "expected"),
    [(lambda env: True, True), (lambda env: False, False), ("raise", False)],
    ids=["env-present", "env-absent", "env-probe-raises"],
)
def test_alt_env_is_consulted_when_the_module_is_missing(monkeypatch, env_answer, expected):
    asked: list[str] = []

    def probe(env):
        asked.append(env)
        if env_answer == "raise":
            raise subprocess.SubprocessError("conda broke")
        return env_answer(env)

    monkeypatch.setattr(deps, "_check_spec", lambda module: False)
    monkeypatch.setattr(external_env, "is_env_available", probe)
    assert deps.is_available("pybanksy") is expected
    assert asked == ["omicsclaw_banksy"]


def test_the_four_domain_managers_are_gone():
    for domain in ("spatial", "singlecell", "proteomics", "metabolomics"):
        assert not (REPO_ROOT / "skills" / domain / "_lib" / "dependency_manager.py").exists()
