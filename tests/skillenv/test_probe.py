"""The probe: one fixed Python program run under the interpreter ``bash`` would use (plan 0061 case 8).

It must not execute workspace code. ``python -c`` puts ``''`` at the front
of ``sys.path``, so a ``json.py`` in the working directory would run when the
probe imports ``json``, and an empty ``cellbender/`` directory would make
``find_spec("cellbender")`` report a namespace package that a real
``python <skill>/x.py`` run cannot import (plan 0061 F45). The probe drops
``''`` and ``'.'`` before importing anything and puts the skill directory
first instead, as running the script would.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys

import pytest

from omicsclaw.skillenv.probe import ProbeError, parse_probe, probe_argv, probe_command


def _run_shell(command: str, cwd, env=None):
    proc = subprocess.run(["bash", "-c", command], cwd=cwd, capture_output=True, text=True, timeout=60, env=env)
    assert proc.returncode == 0, proc.stderr
    return parse_probe(proc.stdout)


def _command(imports, dists, skill_dir):
    return probe_command(imports, dists, str(skill_dir)).replace("python -B", f"{shlex.quote(sys.executable)} -B", 1)


def test_present_and_missing(tmp_path):
    result = _run_shell(_command(["json", "oc_surely_missing_mod"], [], tmp_path), tmp_path)
    assert result.missing == ("oc_surely_missing_mod",)
    assert result.executable
    assert result.version.count(".") == 2


def test_a_find_spec_that_raises_counts_as_present(tmp_path):
    pkg = tmp_path / "skill" / "ocboom"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("raise RuntimeError('boom')\n")
    result = _run_shell(_command(["ocboom.sub"], [], tmp_path / "skill"), tmp_path)
    assert result.missing == ()


def test_versions_and_unknown_distributions(tmp_path):
    result = _run_shell(_command([], ["pip", "oc-no-such-dist"], tmp_path), tmp_path)
    assert result.versions["pip"]
    assert result.versions["oc-no-such-dist"] is None


def test_output_that_is_not_json_is_an_error():
    with pytest.raises(ProbeError):
        parse_probe("Traceback (most recent call last):\n  boom\n")
    with pytest.raises(ProbeError):
        parse_probe('{"executable": "x"}')


def test_no_bytecode_is_written(tmp_path):
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "ocmod.py").write_text("X = 1\n")
    _run_shell(_command(["ocmod"], [], skill), tmp_path)
    assert not (skill / "__pycache__").exists()


def test_quoting_survives_single_quotes_in_the_payload(tmp_path):
    odd = tmp_path / "it's here"
    odd.mkdir()
    result = _run_shell(_command(["json"], [], odd), tmp_path)
    assert result.missing == ()


def test_workspace_code_is_not_executed(tmp_path):
    marker = tmp_path / "executed"
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "json.py").write_text(f"open({str(marker)!r}, 'w').write('x')\n")
    (workspace / "cellbender").mkdir()
    result = _run_shell(_command(["json", "cellbender"], [], tmp_path / "no-such-skill-dir"), workspace)
    assert not marker.exists()
    assert result.missing == ("cellbender",)


def test_the_skill_directory_is_first_on_the_path(tmp_path):
    skill = tmp_path / "skill"
    skill.mkdir()
    (skill / "oc_local_helper.py").write_text("")
    result = _run_shell(_command(["oc_local_helper"], [], skill), tmp_path)
    assert result.missing == ()


def test_base_prefix_and_user_site(tmp_path):
    user_site = tmp_path / "usersite"
    (user_site / "oc_user_only").mkdir(parents=True)
    (user_site / "oc_user_only" / "__init__.py").write_text("")
    sitecustom = tmp_path / "custom"
    sitecustom.mkdir()
    (sitecustom / "sitecustomize.py").write_text(
        "import site, sys\n"
        f"site.getusersitepackages = lambda: {str(user_site)!r}\n"
        f"sys.path.append({str(user_site)!r})\n"
    )
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(sitecustom)}
    result = _run_shell(_command(["oc_user_only", "json"], [], tmp_path), tmp_path, env=env)
    assert result.from_user_site == ("oc_user_only",)
    assert result.base_prefix == sys.base_prefix
    assert result.prefix == sys.prefix


def test_argv_form_matches_the_shell_form(tmp_path):
    argv = probe_argv(sys.executable, ["json", "oc_surely_missing_mod"], ["pip"], str(tmp_path))
    assert argv[:3] == [sys.executable, "-B", "-c"]
    proc = subprocess.run(argv, cwd=tmp_path, capture_output=True, text=True, timeout=60)
    from_argv = parse_probe(proc.stdout)
    from_shell = _run_shell(_command(["json", "oc_surely_missing_mod"], ["pip"], tmp_path), tmp_path)
    assert from_argv == from_shell
    assert json.loads(argv[4])["imports"] == ["json", "oc_surely_missing_mod"]
