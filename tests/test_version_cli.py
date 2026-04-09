from __future__ import annotations

import importlib.util
import sys
import tomllib
from pathlib import Path

import pytest

from omicsclaw import __version__


ROOT = Path(__file__).resolve().parent.parent


def _load_omicsclaw_script():
    spec = importlib.util.spec_from_file_location(
        "omicsclaw_main_version_cli_test",
        ROOT / "omicsclaw.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_package_exports_single_version_source():
    from omicsclaw.version import __version__ as module_version

    assert __version__ == module_version


def test_pyproject_version_matches_version_module():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["version"] == __version__


def test_version_subcommand_prints_project_version(monkeypatch, capsys):
    oc = _load_omicsclaw_script()
    monkeypatch.setattr(sys, "argv", ["omicsclaw.py", "version"])

    with pytest.raises(SystemExit) as excinfo:
        oc.main()

    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"OmicsClaw {__version__}"


def test_global_version_flag_prints_project_version(monkeypatch, capsys):
    oc = _load_omicsclaw_script()
    monkeypatch.setattr(sys, "argv", ["omicsclaw.py", "--version"])

    with pytest.raises(SystemExit) as excinfo:
        oc.main()

    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"OmicsClaw {__version__}"


def test_app_and_memory_servers_share_project_version():
    pytest.importorskip("fastapi")

    from omicsclaw.app import server as app_server
    from omicsclaw.memory.server import _build_app

    assert app_server.__version__ == __version__
    app = _build_app()
    assert app is not None
    assert app.version == __version__
