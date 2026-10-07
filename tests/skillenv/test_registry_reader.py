"""Reading ``skills/_sdk/deps.py`` as a file, and resolving names against it (plan 0061 case 6).

The framework never imports ``skills``: the registry is a file contract,
read with ``ast.literal_eval`` and checked here against the same field
rules plan 0062 case 22 pins on the writing side. Name resolution follows
plan 0062 §3.4 — exact key, PEP 503-normalised key, exact ``module`` — and
only the fallback differs: this side derives the import name from a two-entry
table (``PyYAML`` → ``yaml``, ``scikit-learn`` → ``sklearn``) or by turning
``-`` into ``_``, because 0062's fallback (the name itself) gets exactly those
two wrong. The declared names that fall back are frozen in
``DECLARED_FALLBACK``: a new declaration that only the fallback can resolve
turns this red until it is registered or listed here with a reason. At the
time of writing they are the 16 names plan 0061 F64 found, re-measured at P1
start.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap

import pytest

from omicsclaw.skillenv.registry import (
    RegistryFormatError,
    parse_dependencies,
    probe_plan,
    read_registry,
    resolve,
)

from .conftest import REAL_REGISTRY, REPO

DECLARED_FALLBACK = {
    # Base scientific stack and general-purpose libraries, not optional backends.
    "adjustText", "anndata", "dask", "filelock", "joblib", "matplotlib", "networkx", "numpy",
    "pandas", "psutil", "PyYAML", "requests", "scanpy", "scikit-learn", "scipy",
    "statsmodels",
    # Declared by genomics-variant-annotation; not in any domain registry before 0062.
    "mygene",
    # Declared by literature; its PDF parser imports it, and no registry lists it.
    "pypdf",
}


@pytest.fixture(scope="module")
def real():
    return read_registry(REAL_REGISTRY)


# ---- the real file -----------------------------------------------------------------------


def test_the_real_registry_has_70_entries_with_the_expected_kinds(real):
    assert len(real) == 70
    assert {k for k, v in real.items() if v["kind"] == "git"} == {"STAGATE-pyG", "pybanksy", "STalign"}
    assert {k for k, v in real.items() if v["kind"] == "r"} == {"xcms", "metaboanalyst", "Matrix", "numbat", "CellChat", "DESeq2", "sva", "survival", "WGCNA"}
    assert {k for k, v in real.items() if "also" in v} == {"singler"}
    assert {k for k, v in real.items() if "alt_env" in v} == {"pybanksy"}


def test_reading_imports_nothing_from_skills():
    code = textwrap.dedent(
        f"""
        import json, sys
        from omicsclaw.skillenv.registry import read_registry
        entries = read_registry({str(REAL_REGISTRY)!r})
        print(json.dumps([len(entries), sorted(m for m in sys.modules if m == "skills" or m.startswith("skills."))]))
        """
    )
    env = {**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run([sys.executable, "-B", "-c", code], cwd=REPO, env=env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip().splitlines()[-1]) == [70, []]


def test_what_is_read_equals_what_the_module_defines(real):
    """Tests may import both sides (plan 0062 §3.6); the framework may not."""
    from skills._sdk.deps import DEPENDENCIES

    assert real == DEPENDENCIES


# ---- resolution order --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "key", "module"),
    [
        ("SpatialDE", "SpatialDE", "NaiveDE"),
        ("spatialde", "SpatialDE", "NaiveDE"),
        ("scvi", "scvi-tools", "scvi"),
        ("tangram", "tangram-sc", "tangram"),
        ("paste", "paste-bio", "paste"),
        ("STAGATE_pyG", "STAGATE-pyG", "STAGATE_pyG"),
        ("scikit-misc", "scikit-misc", "skmisc"),
        ("skmisc", "scikit-misc", "skmisc"),
        ("umap-learn", "umap-learn", "umap"),
        ("umap", "umap-learn", "umap"),
    ],
)
def test_resolution_through_the_registry(real, name, key, module):
    found = resolve(name, real)
    assert (found.key, found.module) == (key, module)


@pytest.mark.parametrize(
    ("name", "module"),
    [("PyYAML", "yaml"), ("scikit-learn", "sklearn"), ("adjustText", "adjustText"), ("a-b", "a_b")],
)
def test_the_fallback_derives_the_import_name_on_this_side(real, name, module):
    found = resolve(name, real)
    assert found.key is None
    assert found.module == module
    assert found.kind == "pip"
    assert found.distributions == (name,)


def test_the_declared_fallback_names_are_frozen(real):
    declared = {
        name
        for path in sorted((REPO / "skills").rglob("SKILL.md"))
        for name in parse_dependencies(path.read_text(encoding="utf-8"), source=path)
    }
    assert {name for name in declared if resolve(name, real).key is None} == DECLARED_FALLBACK


def test_normalised_match_comes_before_the_module_lookup():
    """With a legal registry the order of steps 2 and 3 is unobservable: 0062's
    ambiguity ban forbids a name that is both a normalised key and another
    entry's module. This fixture breaks the ban on purpose and is handed to the
    pure function directly, bypassing the reader, so the implementation stays
    pinned to the documented order if the ban is ever relaxed."""
    entries = {
        "Foo-Bar": {"module": "foobar", "kind": "pip", "install": "pip install Foo-Bar", "description": "a"},
        "other": {"module": "foo_bar", "kind": "pip", "install": "pip install other", "description": "b"},
    }
    assert resolve("foo_bar", entries).key == "Foo-Bar"


# ---- the file contract --------------------------------------------------------------------


def _write(tmp_path, body: str):
    path = tmp_path / "deps.py"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


_OK = '"a": {"module": "a", "kind": "pip", "install": "pip install a", "description": "d"}'


def test_plain_and_annotated_assignments_both_read(tmp_path):
    assert set(read_registry(_write(tmp_path, f"DEPENDENCIES = {{{_OK}}}\n"))) == {"a"}
    assert set(read_registry(_write(tmp_path, f"DEPENDENCIES: dict = {{{_OK}}}\n"))) == {"a"}


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ("OTHER = {}\n", "no module-level DEPENDENCIES"),
        ('DEPENDENCIES = {"a": DependencyInfo("a", "pip install a")}\n', "not a literal"),
        ('DEPENDENCIES = {"a": {"module": "a", "kind": "pip", "install": "x", "description": "d", "check": lambda: 1}}\n', "not a literal"),
        ('DEPENDENCIES = {"a": {"module": "a", "kind": "pip", "install": "x"}}\n', "missing"),
        ('DEPENDENCIES = {"a": {"module": "a", "kind": "pip", "install": "x", "description": "d", "extra": 1}}\n', "unknown"),
        ('DEPENDENCIES = {"a": {"module": "a", "kind": "conda", "install": "x", "description": "d"}}\n', "kind"),
        ('DEPENDENCIES = {"a": {"module": "a", "kind": "pip", "install": "x", "description": "d", "also": "b"}}\n', "also"),
        ('DEPENDENCIES = {"a": {"module": "a", "kind": "pip", "install": "x", "description": "d", "also": [1]}}\n', "also"),
        ('DEPENDENCIES = {"A_b": {"module": "x", "kind": "pip", "install": "x", "description": "d"}, "a-B": {"module": "y", "kind": "pip", "install": "y", "description": "d"}}\n', "normalise"),
        ('DEPENDENCIES = {"a": {"module": "m", "kind": "pip", "install": "x", "description": "d"}, "b": {"module": "m", "kind": "pip", "install": "y", "description": "d"}}\n', "module"),
        ('DEPENDENCIES = {"a": {"module": "b", "kind": "pip", "install": "x", "description": "d"}, "b": {"module": "c", "kind": "pip", "install": "y", "description": "d"}}\n', "ambiguous"),
        ('DEPENDENCIES = ["a"]\n', "dict"),
    ],
    ids=["absent", "call", "lambda", "missing-field", "unknown-field", "kind", "also-str",
         "also-int", "dup-normalised", "dup-module", "ambiguous", "not-dict"],
)
def test_contract_violations_are_refused_with_file_and_line(tmp_path, body, fragment):
    path = _write(tmp_path, body)
    with pytest.raises(RegistryFormatError) as info:
        read_registry(path)
    message = str(info.value)
    assert str(path) in message
    assert fragment in message
    if fragment != "no module-level DEPENDENCIES":
        assert ":1" in message


def test_a_missing_file_says_the_skills_dir_is_not_a_skills_tree(tmp_path):
    with pytest.raises(RegistryFormatError, match="not an OmicsClaw skills tree") as info:
        read_registry(tmp_path / "_sdk" / "deps.py")
    assert "install_skill_deps" not in str(info.value)
    assert "no dependency registry to read" in str(info.value)


# ---- expansion and categories come from fields, never from `install` --------------------


def test_expansion_ignores_the_install_string():
    entries = {
        "singler": {"module": "singler", "kind": "pip", "also": ["singlecellexperiment"],
                    "install": "echo something unrelated", "description": "d"},
        "plain": {"module": "plain", "kind": "pip", "install": "pip install totally-different", "description": "d"},
    }
    assert resolve("singler", entries).distributions == ("singler", "singlecellexperiment")
    assert resolve("plain", entries).distributions == ("plain",)


def test_the_category_is_the_kind_field():
    entries = {
        "p": {"module": "p", "kind": "pip", "install": "Rscript -e 'install.packages(\"p\")'", "description": "d"},
        "g": {"module": "g", "kind": "git", "install": "pip install g", "description": "d"},
    }
    assert resolve("p", entries).kind == "pip"
    assert resolve("g", entries).kind == "git"


def test_probe_inputs_skip_r_packages_and_use_modules(real):
    plan = probe_plan(["xcms", "pybanksy", "numpy"], real)
    assert plan.imports == ("banksy", "numpy")
    assert [r.key for r in plan.r_packages] == ["xcms"]
    assert [r.name for r in plan.resolved] == ["xcms", "pybanksy", "numpy"]
