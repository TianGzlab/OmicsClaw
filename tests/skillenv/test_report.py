"""The environment-check note appended to ``use_skill`` (plan 0061 case 10, §4.4).

Pure rendering over a probe result. git-only entries are named with their
registry ``install`` command verbatim (and the conda env when the entry has
``alt_env``); R packages are never probed and get one sentence. In the
sandbox the wording depends on whether it has a network, and host overlays
are never mentioned there because the container cannot see them. The note is
capped at 1500 characters: past that, missing packages are listed by name
only.
"""

from __future__ import annotations

from omicsclaw.skillenv.probe import ProbeResult
from omicsclaw.skillenv.registry import probe_plan
from omicsclaw.skillenv.report import MAX_CHARS, SandboxContext, render_annotation

REGISTRY = {
    "pybanksy": {"module": "banksy", "kind": "git", "alt_env": "omicsclaw_banksy",
                 "install": "pip install git+https://github.com/prabhakarlab/Banksy_py.git", "description": "b"},
    "STAGATE-pyG": {"module": "STAGATE_pyG", "kind": "git",
                    "install": "pip install git+https://github.com/RucDongLab/STAGATE_pyG.git", "description": "s"},
    "xcms": {"module": "xcms", "kind": "r", "install": "Rscript -e 'BiocManager::install(\"xcms\")'", "description": "x"},
    "mygene": {"module": "mygene", "kind": "pip", "install": "pip install mygene", "description": "m"},
}


def _result(missing=(), user=()):
    return ProbeResult(
        executable="/opt/conda/envs/OmicsClaw/bin/python", version="3.11.15",
        prefix="/opt/conda/envs/OmicsClaw", base_prefix="/opt/conda/envs/OmicsClaw",
        missing=tuple(missing), from_user_site=tuple(user), versions={},
    )


def test_everything_present():
    plan = probe_plan(["numpy", "mygene"], REGISTRY)
    text = render_annotation(plan, _result())
    assert text.startswith("---\nEnvironment check (the `python` bash runs here: /opt/conda/envs/OmicsClaw/bin/python, Python 3.11.15)")
    assert '2 of 2 packages under "## Dependencies" are importable.' in text
    assert "Missing" not in text
    assert "unaffected" not in text


def test_git_only_missing_quotes_the_registry_command_and_the_conda_env():
    plan = probe_plan(["pybanksy", "STAGATE-pyG", "numpy"], REGISTRY)
    text = render_annotation(plan, _result(missing=["banksy", "STAGATE_pyG"]))
    assert "1 of 3 packages" in text
    assert "Missing, git-only (install_skill_deps cannot install these):" in text
    assert "pybanksy (import banksy) — pip install git+https://github.com/prabhakarlab/Banksy_py.git, or the conda env `omicsclaw_banksy`" in text
    assert "STAGATE-pyG (import STAGATE_pyG) — pip install git+https://github.com/RucDongLab/STAGATE_pyG.git" in text
    assert text.rstrip().endswith("Methods that do not use a missing package are unaffected.")


def test_r_packages_are_named_and_not_probed():
    plan = probe_plan(["xcms", "numpy"], REGISTRY)
    assert plan.imports == ("numpy",)
    text = render_annotation(plan, _result())
    assert "1 of 1 packages" in text
    assert "R package, not checked here; the script's `validate_r_environment` reports it: xcms" in text


def test_pip_missing_with_and_without_the_install_tool():
    plan = probe_plan(["mygene", "numpy"], REGISTRY)
    without = render_annotation(plan, _result(missing=["mygene"]))
    assert "Missing: mygene (import mygene)" in without
    assert "install_skill_deps can add" not in without
    with_tool = render_annotation(plan, _result(missing=["mygene"]), install_tool=True)
    assert "install_skill_deps can add the ones your method needs to an isolated overlay; the base environment is never changed." in with_tool


def test_an_existing_overlay_is_named_locally_only():
    plan = probe_plan(["mygene"], REGISTRY)
    local = render_annotation(plan, _result(missing=["mygene"]), overlays=["/cache/envs/abc/.venv/bin/python"])
    assert "/cache/envs/abc/.venv/bin/python" in local
    boxed = render_annotation(
        plan, _result(missing=["mygene"]), overlays=["/cache/envs/abc/.venv/bin/python"],
        sandbox=SandboxContext(image="omics:1", isolated=True, network="none"),
    )
    assert "/cache/envs/abc" not in boxed


def test_user_site_packages_are_called_out():
    plan = probe_plan(["mygene"], REGISTRY)
    text = render_annotation(plan, _result(user=["mygene"]))
    assert "found only in the user site (~/.local); an overlay command with PYTHONNOUSERSITE=1 will not see it: mygene" in text


def test_sandbox_wording_without_and_with_network():
    plan = probe_plan(["mygene"], REGISTRY)
    isolated = render_annotation(plan, _result(missing=["mygene"]),
                                 sandbox=SandboxContext(image="omics:1", isolated=True, network="none"))
    assert "the `python` bash runs in the sandbox" in isolated
    assert ("This runs inside the sandbox image `omics:1`, which has no network: missing packages have to "
            "be added to the image by whoever maintains it.") in isolated
    networked = render_annotation(plan, _result(missing=["mygene"]),
                                  sandbox=SandboxContext(image="omics:1", isolated=False, network="bridge"))
    assert "The sandbox can reach network `bridge`; install_skill_deps is not available inside the sandbox." in networked


def test_an_unavailable_probe_is_one_line():
    plan = probe_plan(["mygene"], REGISTRY)
    text = render_annotation(plan, None, error="python: command not found")
    assert text == "---\nEnvironment check unavailable: python: command not found"


def test_an_unreadable_registry_is_still_said_when_the_probe_fails():
    plan = probe_plan(["mygene"], {})
    text = render_annotation(plan, None, error="timed out", registry_error="deps.py: no DEPENDENCIES")
    assert text == (
        "---\ndependency registry unreadable: deps.py: no DEPENDENCIES\n"
        "Environment check unavailable: timed out"
    )


def test_an_unreadable_registry_is_said_first():
    plan = probe_plan(["mygene"], {})
    text = render_annotation(plan, _result(missing=["mygene"]), registry_error="deps.py: no DEPENDENCIES")
    assert text.splitlines()[1] == "dependency registry unreadable: deps.py: no DEPENDENCIES"
    assert "Missing: mygene" in text


def test_the_note_is_capped_and_long_lists_keep_only_names():
    registry = {
        f"pkg{i:03d}": {"module": f"m{i:03d}", "kind": "git",
                        "install": f"pip install git+https://example.invalid/some/long/path/pkg{i:03d}.git",
                        "description": "d"}
        for i in range(60)
    }
    plan = probe_plan(list(registry), registry)
    text = render_annotation(plan, _result(missing=[f"m{i:03d}" for i in range(60)]))
    assert len(text) <= MAX_CHARS
    assert "pkg000" in text
    assert "example.invalid" not in text
