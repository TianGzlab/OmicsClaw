"""The installed ``oc`` / ``omicsclaw`` console scripts land on the shell.

Guards the "stale wrapper script" failure mode: setuptools writes the console
scripts and ``*.dist-info/entry_points.txt`` at install time only, so an
environment that was installed before a module move keeps importing the old
path and crashes with ``ModuleNotFoundError`` before ``main()`` runs. That
happened for real —— ``oc`` pointed at ``omicsclaw.surfaces.cli.launcher``,
which has been unimportable since ``omicsclaw/skill/`` was deleted.

**Updated for plan 0037.** :data:`EXPECTED` used to assert the pre-rebuild
contract —— both names on ``omicsclaw.surfaces.cli.launcher:main``, plus
``oc-chat`` / ``omicsclaw-chat`` on ``omicsclaw.surfaces.cli:main`` —— while
``tests/launch/test_grammar.py::test_the_console_scripts_land_on_this_shell``
asserted the new one from ``pyproject.toml``. Two guards over one property,
each calling the other wrong, is worse than one: whichever fails, the reading
is "the other one is stale", and that reading is available every time.

The two are not redundant now that they agree. That one reads the manifest
—— what will be installed —— and this one reads the installed metadata ——
what *is*. Both are needed precisely because the gap between them is the
failure mode.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
from importlib.metadata import entry_points

import pytest

EXPECTED = {
    "oc": "omicsclaw.launch:main",
    "omicsclaw": "omicsclaw.launch:main",
}
"""Two names, one landing point (plan 0037 §6).

``oc-chat`` / ``omicsclaw-chat`` are deliberately absent rather than
repointed: ``oc cli`` is the same thing, and a fourth name for it is what the
redesign removes. Their absence is asserted below, because a console script
that is not supposed to exist is not covered by checking the ones that are.
"""

RETIRED = ("oc-chat", "omicsclaw-chat")


def _console_script(name: str):
    for ep in entry_points(group="console_scripts"):
        if ep.name == name:
            return ep
    return None


def _installed() -> bool:
    return _console_script("oc") is not None or _console_script("omicsclaw") is not None


needs_install = pytest.mark.skipif(
    not _installed(),
    reason="this checkout is not pip-installed, so there is no metadata to read",
)
"""Skipped rather than failed in a source checkout.

The property is about *installed* metadata. In a tree that was never
``pip install``-ed there is none, and a red test there would say "the
entry points are wrong" when what is true is "there are none" ——
``tests/launch/test_grammar.py`` covers the manifest for that case.
"""


@needs_install
@pytest.mark.parametrize("name,target", sorted(EXPECTED.items()))
def test_console_script_metadata_matches_pyproject(name: str, target: str) -> None:
    ep = _console_script(name)
    assert ep is not None, f"console script {name!r} is not registered"
    assert ep.value == target, (
        f"{name!r} entry point is {ep.value!r}; expected {target!r}. "
        "Run `pip install -e .` to refresh after a module move."
    )


@needs_install
@pytest.mark.parametrize("name", RETIRED)
def test_the_retired_chat_scripts_are_gone(name: str) -> None:
    """A stale install keeps them, and they land on a deleted package."""
    assert _console_script(name) is None, (
        f"{name!r} is still registered; it was removed by plan 0037 §6. "
        "Run `pip install -e .` to refresh."
    )


@pytest.mark.parametrize("target", sorted(set(EXPECTED.values())))
def test_console_script_target_imports(target: str) -> None:
    """Checked in every checkout, installed or not: the target must exist."""
    module_path, _, attr = target.partition(":")
    module = importlib.import_module(module_path)
    assert callable(getattr(module, attr)), f"{target} is not callable"


@pytest.mark.skipif(shutil.which("oc") is None, reason="oc not on PATH")
def test_oc_wrapper_runs_without_import_error() -> None:
    """The installed ``oc`` wrapper must import its target module cleanly."""
    result = subprocess.run(
        ["oc", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    combined = result.stdout + result.stderr
    assert "ModuleNotFoundError" not in combined, (
        "oc wrapper imports a stale module (run `pip install -e .`):\n"
        f"{combined[-800:]}"
    )
